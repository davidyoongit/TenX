"""
자동매매 하네스 — 메인 진입점.

실행:
    python harness.py

흐름:
    1. 토큰 초기화
    2. strategy_selector.select() → 당일 최적 전략 선택
    3. 매매 루프 (trader.py 로직 + trade_logger 기록)
    4. 장 종료 후 reporter.send_daily_report()
"""
import sys
import io
import time
import os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)
from dotenv import load_dotenv
import requests

import kis_api
import trade_logger
import reporter
from strategy_selector import select_multi
from strategy_orb import OpeningRangeBreakout

load_dotenv()

SLACK_TOKEN      = os.environ["SLACK_TOKEN"]
SYMBOL_LIST      = [
    "251340", "233740", "114800", "122630",
    "229200", "069500", "250780", "148020",
    "005930", "000660",
    "091160", "102780", "494310", "488080",
    "226490", "494890",
]
TARGET_BUY_COUNT = 3
BUY_PERCENT      = 0.33
STRATEGY_REFRESH_SEC = 600  # 10분마다 시장 재분석 후 전략 갱신

# 오버나이트 갭다운 가드: 이월 보유 종목이 개장 시점에 평단 대비
# 이 임계 이하로 갭다운되어 있으면 SL(-1.5%, 장중용)을 우회해 즉시 청산한다.
GAP_DOWN_EXIT_PCT = -3.0

# 전일 미청산 이월 종목 기록 파일 (익일 개장 직후 최우선 청산용)
CARRYOVER_FLAG_PATH = "carryover_liquidation.json"


# ──────────────────────────────────────────────
# 알림
# ──────────────────────────────────────────────

def _log(msg: str) -> None:
    print(datetime.now().strftime("[%m/%d %H:%M:%S]"), msg)


def _notify(msg: str) -> None:
    _log(msg)
    try:
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            data={"channel": "stock",
                  "text": datetime.now().strftime("[%m/%d %H:%M:%S]") + " " + msg},
            timeout=5,
        )
    except Exception as e:
        _log(f"slack error: {e}")


# ──────────────────────────────────────────────
# 이월 미청산 플래그 (전일 _sell_all 잔량 → 익일 최우선 청산)
# ──────────────────────────────────────────────

import json


def _write_carryover_flag(codes: dict) -> None:
    """전일 청산 실패로 이월된 종목을 기록한다. codes = {code: qty}"""
    try:
        payload = {
            "date":  datetime.now().strftime("%Y%m%d"),
            "codes": codes,
        }
        with open(CARRYOVER_FLAG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log(f"carryover flag write error: {e}")


def _read_carryover_flag() -> dict:
    """이전 영업일 이월 청산 플래그를 읽는다. {code: qty}"""
    try:
        if not os.path.exists(CARRYOVER_FLAG_PATH):
            return {}
        with open(CARRYOVER_FLAG_PATH, encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("codes", {})
    except Exception as e:
        _log(f"carryover flag read error: {e}")
        return {}


def _clear_carryover_flag() -> None:
    try:
        if os.path.exists(CARRYOVER_FLAG_PATH):
            os.remove(CARRYOVER_FLAG_PATH)
    except Exception as e:
        _log(f"carryover flag clear error: {e}")


# ──────────────────────────────────────────────
# 단일 인스턴스 잠금
# ──────────────────────────────────────────────

LOCK_FILE = "harness.pid"


def _pid_alive(pid: int) -> bool:
    """해당 PID 프로세스가 살아있는지 확인 (Windows)."""
    try:
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _acquire_lock() -> None:
    """중복 실행 방지 — 이미 실행 중인 인스턴스가 있으면 즉시 종료."""
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE, encoding="utf-8").read().strip())
            if _pid_alive(pid):
                print(f"[harness] 이미 실행 중입니다 (PID {pid}). 종료합니다.")
                sys.exit(0)
        except Exception:
            pass  # 잠금 파일 손상 또는 PID 읽기 실패 → 덮어쓰기
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    import atexit
    atexit.register(_release_lock)


def _release_lock() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


# ──────────────────────────────────────────────
# 매수 시도
# ──────────────────────────────────────────────

def _try_buy(code: str, strategy, bought: set,
             buy_amount: float, buy_prices: dict,
             bought_strategy: dict = None) -> None:
    try:
        if code in bought:
            return

        _now = datetime.now()
        _t = lambda h, m: _now.replace(hour=h, minute=m, second=0, microsecond=0)
        if not (_t(9, 5) < _now < _t(14, 15)):
            return

        current_price, ask_price, _ = kis_api.get_asking_price(code)

        # ORB 전략은 update_range 호출 필요
        if isinstance(strategy, OpeningRangeBreakout):
            strategy.update_range(code, current_price)

        buy_qty = int(buy_amount // ask_price) if ask_price > 0 else 0

        _log(f"{code}  현재가={current_price:,}  수량={buy_qty}  "
             f"전략={strategy.__class__.__name__}")

        if not strategy.should_buy(code, current_price, ask_price):
            return
        if buy_qty < 1:
            _log(f"{code} 매수 수량 부족")
            return

        _notify(f"📥 {code} 매수 조건 충족 — {buy_qty}주 @ {current_price:,}")
        kis_api.buy(code, buy_qty)

        holdings = kis_api.get_holdings()
        h = holdings.get(code)
        if h and h["qty"] > 0:
            bought.add(code)
            buy_prices[code] = current_price
            if bought_strategy is not None:
                bought_strategy[code] = strategy
            trade_logger.log_buy(code, h["name"], h["qty"], current_price,
                                 strategy=strategy.__class__.__name__)
            _notify(f"✅ {code} {h['qty']}주 매수 완료")

    except Exception as e:
        _log(f"buy error [{code}]: {e}")


# ──────────────────────────────────────────────
# 장중 익절/손절
# ──────────────────────────────────────────────

def _try_intraday_sell(bought_strategy: dict, bought: set, buy_prices: dict) -> None:
    try:
        holdings = kis_api.get_holdings()
        for code in list(bought):
            h = holdings.get(code)
            if not h or h["qty"] == 0:
                continue
            strategy = bought_strategy.get(code)
            if strategy is None or not strategy.should_sell(code, h):
                continue

            reason = "tp" if h["evlu_pfls_rt"] >= 0 else "sl"
            _notify(f"📤 {code} {reason.upper()} — {h['evlu_pfls_rt']:.2f}% → {h['qty']}주 매도")
            kis_api.sell(code, h["qty"])

            cur, _, _ = kis_api.get_asking_price(code)
            trade_logger.log_sell(
                code, h["name"], h["qty"], cur,
                buy_prices.get(code, cur), reason=reason
            )
    except Exception as e:
        _log(f"intraday sell error: {e}")


# ──────────────────────────────────────────────
# 전량 매도
# ──────────────────────────────────────────────

def _sell_all(bought: set, buy_prices: dict) -> bool:
    pending: set[str] = set()  # 이미 주문 전송한 코드 — 체결 전 재주문 방지
    for _ in range(10):
        holdings = kis_api.get_holdings()
        targets  = {c: h for c, h in holdings.items()
                    if c in SYMBOL_LIST and h["qty"] > 0 and c not in pending}
        if not targets and not pending:
            return True
        if not targets:
            time.sleep(30)
            pending.clear()  # 30초 후 미체결 잔량만 재시도
            continue
        for code, h in targets.items():
            _notify(f"📤 {code} {h['qty']}주 EOD 매도")
            kis_api.sell(code, h["qty"], order_type="15")
            cur, _, _ = kis_api.get_asking_price(code)
            trade_logger.log_sell(
                code, h["name"], h["qty"], cur,
                buy_prices.get(code, cur), reason="eod"
            )
            pending.add(code)
            time.sleep(1)
        time.sleep(30)
        pending.clear()

    # 10회 재시도 후에도 잔량이 남음 → 명시적 경고 + 익일 최우선 청산 플래그
    leftover = {c: h["qty"] for c, h in kis_api.get_holdings().items()
                if c in SYMBOL_LIST and h["qty"] > 0}
    if leftover:
        _notify(f"🚨 EOD 청산 실패 — 잔량 이월 위험! 익일 개장 직후 최우선 청산 기록: {leftover}")
        _write_carryover_flag(leftover)
        return False
    return True


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────

def main() -> None:
    _acquire_lock()
    kis_api.init_token()

    cash_start = kis_api.get_cash()
    buy_amount = cash_start * BUY_PERCENT

    # ── 전략 선택 (종목별 다중 전략) ──────────────
    from collections import Counter
    code_strategy = select_multi(SYMBOL_LIST)

    unique_descs = sorted(set(s.describe() for s in code_strategy.values()))
    strat_label  = unique_descs[0] if len(unique_descs) == 1 else "Multi | " + " | ".join(unique_descs)
    trade_logger.set_strategy(strat_label)

    counts = Counter(s.__class__.__name__ for s in code_strategy.values())
    strat_summary = ", ".join(f"{cls}×{n}" for cls, n in sorted(counts.items()))
    _notify(f"🚀 하네스 시작 — 전략: {strat_summary}")
    _notify(f"예수금: {cash_start:,}원  종목별 주문금액: {buy_amount:,.0f}원")

    bought: set[str]      = set()
    buy_prices: dict      = {}
    bought_strategy: dict = {}  # 종목별 매수 시점 전략 — 매도 기준으로 사용
    init_flag             = False
    last_strategy_refresh = time.time()

    while True:
        try:
            now     = datetime.now()
            weekday = now.weekday()
            if weekday >= 5:
                _log("주말 — 종료")
                sys.exit(0)

            def t(h, m):
                return now.replace(hour=h, minute=m, second=0, microsecond=0)

            T_OPEN       = t(9,  0)
            T_START      = t(9,  5)
            T_SELL_START = t(14, 15)
            T_SELL_END   = t(14, 20)

            # 기존 보유 등록 + 오버나이트 갭다운 가드 (당일 최초 1회)
            #   정상: 09:00~09:05. 단, 09:05 이후 늦게 기동된 경우에도
            #   EOD 매도 전(<14:15)이면 init이 스킵되지 않도록 윈도우를 확장한다.
            #   (init_flag로 1회만 실행 → 갭다운/이월 가드가 누락되지 않음)
            if T_OPEN < now < T_SELL_START and not init_flag:
                init_flag = True
                carryover = _read_carryover_flag()  # 전일 미청산 이월 플래그
                if carryover:
                    _notify(f"⚠️ 전일 미청산 이월 종목 감지(최우선 청산 대상): {carryover}")

                for code, h in kis_api.get_holdings().items():
                    if code in SYMBOL_LIST and h["qty"] > 0:
                        avg = h["avg_price"]

                        # 현재가 평가 → 평단 대비 갭 손익
                        try:
                            cur, _, _ = kis_api.get_asking_price(code)
                        except Exception as e:
                            _log(f"gap guard price fetch error [{code}]: {e}")
                            cur = 0

                        gap_pnl = (cur - avg) / avg * 100 if (avg and cur) else 0.0
                        forced  = code in carryover  # 전일 청산 실패분은 무조건 청산

                        # 갭다운 가드: 임계 초과 손실 또는 이월 청산 대상이면 개장 직후 즉시 청산
                        if cur > 0 and (gap_pnl <= GAP_DOWN_EXIT_PCT or forced):
                            tag = "이월 강제청산" if forced else f"갭다운 {gap_pnl:.2f}%"
                            _notify(f"🛑 {code} {tag} (평단 {avg:,} / 현재 {cur:,}) "
                                    f"— 개장 직후 즉시 청산 {h['qty']}주")
                            try:
                                kis_api.sell(code, h["qty"], order_type="15")
                                trade_logger.log_sell(
                                    code, h["name"], h["qty"], cur, avg, reason="gap"
                                )
                            except Exception as e:
                                _notify(f"❌ {code} 갭다운 청산 주문 실패: {e}")
                                # 청산 실패 시에도 추적 위해 등록
                                bought.add(code)
                                buy_prices[code] = avg
                            continue

                        # 가드 통과 → 정상 보유 등록
                        bought.add(code)
                        buy_prices[code] = avg
                        bought_strategy[code] = code_strategy.get(code)

                _clear_carryover_flag()  # 이월 플래그 처리 완료
                _log(f"기존 보유 등록(가드 통과분): {bought}")

            # 09:05~14:15 — 매수 + 장중 청산
            elif T_START < now < T_SELL_START:
                # 10분마다 시장 재분석 → code_strategy 갱신
                if time.time() - last_strategy_refresh >= STRATEGY_REFRESH_SEC:
                    try:
                        code_strategy = select_multi(SYMBOL_LIST)
                        counts = Counter(s.__class__.__name__ for s in code_strategy.values())
                        summary = ", ".join(f"{cls}×{n}" for cls, n in sorted(counts.items()))
                        _notify(f"🔄 전략 갱신 — {summary}")
                    except Exception as refresh_err:
                        _log(f"전략 갱신 실패, 기존 전략 유지: {refresh_err}")
                    last_strategy_refresh = time.time()

                # 매도: 매수 시점 전략 기준 (SL/TP 일관성)
                _try_intraday_sell(bought_strategy, bought, buy_prices)
                # 매수: 최신 전략 기준
                if len(bought) < TARGET_BUY_COUNT:
                    for sym in SYMBOL_LIST:
                        if sym not in bought and len(bought) < TARGET_BUY_COUNT:
                            _try_buy(sym, code_strategy[sym], bought, buy_amount,
                                     buy_prices, bought_strategy)
                            time.sleep(5)

            # 14:15~ — 전량 EOD 매도 후 종료 (시간 상한 없음)
            elif now >= T_SELL_START:
                _sell_all(bought, buy_prices)
                cash_end = kis_api.get_cash()
                summary  = trade_logger.finalize(cash_start, cash_end)
                reporter.send_daily_report(summary)
                _notify("📴 전량 매도 완료 — 프로그램 종료")
                sys.exit(0)

        except Exception as e:
            _notify(f"❌ harness error: {e}")

        time.sleep(30)


if __name__ == "__main__":
    main()
