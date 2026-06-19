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
import time
import os
from datetime import datetime
from dotenv import load_dotenv
import requests

import kis_api
import trade_logger
import reporter
from strategy_selector import select
from strategy_orb import OpeningRangeBreakout

load_dotenv()

SLACK_TOKEN      = os.environ["SLACK_TOKEN"]
SYMBOL_LIST      = [
    "251340", "233740", "114800", "122630",
    "229200", "069500", "250780", "148020", "305540",
]
TARGET_BUY_COUNT = 5
BUY_PERCENT      = 0.19


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
# 매수 시도
# ──────────────────────────────────────────────

def _try_buy(code: str, strategy, bought: set,
             buy_amount: float, buy_prices: dict) -> None:
    try:
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
            trade_logger.log_buy(code, h["name"], h["qty"], current_price)
            _notify(f"✅ {code} {h['qty']}주 매수 완료")

    except Exception as e:
        _log(f"buy error [{code}]: {e}")


# ──────────────────────────────────────────────
# 장중 익절/손절
# ──────────────────────────────────────────────

def _try_intraday_sell(strategy, bought: set, buy_prices: dict) -> None:
    try:
        holdings = kis_api.get_holdings()
        for code in list(bought):
            h = holdings.get(code)
            if not h or h["qty"] == 0:
                continue
            if not strategy.should_sell(code, h):
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
    for _ in range(10):
        holdings = kis_api.get_holdings()
        targets  = {c: h for c, h in holdings.items()
                    if c in SYMBOL_LIST and h["qty"] > 0}
        if not targets:
            return True
        for code, h in targets.items():
            _notify(f"📤 {code} {h['qty']}주 EOD 매도")
            kis_api.sell(code, h["qty"], order_type="15")
            cur, _, _ = kis_api.get_asking_price(code)
            trade_logger.log_sell(
                code, h["name"], h["qty"], cur,
                buy_prices.get(code, cur), reason="eod"
            )
            time.sleep(1)
        time.sleep(30)
    return False


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────

def main() -> None:
    kis_api.init_token()

    cash_start = kis_api.get_cash()
    buy_amount = cash_start * BUY_PERCENT

    # ── 전략 선택 ──────────────────────────────
    strategy = select()
    trade_logger.set_strategy(strategy.describe())

    _notify(f"🚀 하네스 시작 — 전략: {strategy.describe()}")
    _notify(f"예수금: {cash_start:,}원  종목별 주문금액: {buy_amount:,.0f}원")

    bought: set[str]      = set()
    buy_prices: dict      = {}
    init_flag             = False

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

            # 09:00~09:05 — 기존 보유 등록
            if T_OPEN < now < T_START and not init_flag:
                init_flag = True
                for code, h in kis_api.get_holdings().items():
                    if code in SYMBOL_LIST and h["qty"] > 0:
                        bought.add(code)
                _log(f"기존 보유 등록: {bought}")

            # 09:05~14:15 — 매수 + 장중 청산
            elif T_START < now < T_SELL_START:
                _try_intraday_sell(strategy, bought, buy_prices)
                if len(bought) < TARGET_BUY_COUNT:
                    for sym in SYMBOL_LIST:
                        if sym not in bought and len(bought) < TARGET_BUY_COUNT:
                            _try_buy(sym, strategy, bought, buy_amount, buy_prices)
                            time.sleep(5)

            # 14:15~14:20 — 전량 EOD 매도
            elif T_SELL_START < now < T_SELL_END:
                if _sell_all(bought, buy_prices):
                    cash_end = kis_api.get_cash()
                    summary  = trade_logger.finalize(cash_start, cash_end)
                    reporter.send_daily_report(summary)
                    _notify("📴 전량 매도 완료 — 프로그램 종료")
                    sys.exit(0)

            # 14:20~ — 강제 종료
            elif now > T_SELL_END:
                cash_end = kis_api.get_cash()
                summary  = trade_logger.finalize(cash_start, cash_end)
                reporter.send_daily_report(summary)
                _notify("장 마감 — 프로그램 종료")
                sys.exit(0)

        except Exception as e:
            _notify(f"❌ harness error: {e}")

        time.sleep(10)


if __name__ == "__main__":
    main()
