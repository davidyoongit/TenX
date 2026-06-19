"""
메인 트레이더. Strategy 인터페이스에만 의존하며 알고리즘을 모른다.

실행:
    python trader.py
"""
import sys, time, os
from datetime import datetime
from dotenv import load_dotenv
import requests

import kis_api
from strategy import VolatilityBreakout  # ← 전략 교체 시 이 줄만 바꾼다

load_dotenv()

SLACK_TOKEN = os.environ['SLACK_TOKEN']
SYMBOL_LIST = [
    '252670', '251340', '233740', '114800', '122630',
    '229200', '069500', '250780', '148020', '305540',
]
TARGET_BUY_COUNT = 5
BUY_PERCENT      = 0.19


# ──────────────────────────────────────────────
# 알림
# ──────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.now().strftime('[%m/%d %H:%M:%S]')
    print(ts, msg)


def _notify(msg: str) -> None:
    _log(msg)
    try:
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            data={"channel": "stock", "text": f"{datetime.now().strftime('[%m/%d %H:%M:%S]')}{msg}"},
            timeout=5,
        )
    except Exception as e:
        _log(f"slack error: {e}")


# ──────────────────────────────────────────────
# 매매 실행
# ──────────────────────────────────────────────

def _try_buy(code: str, strategy, bought: set, buy_amount: float) -> None:
    try:
        current_price, ask_price, _ = kis_api.get_asking_price(code)
        buy_qty = buy_amount // ask_price if ask_price > 0 else 0

        _log(f"{code}  현재가={current_price:,}  매수금액={buy_amount:,.0f}  수량={int(buy_qty)}")

        if not strategy.should_buy(code, current_price, ask_price):
            return

        if buy_qty < 1:
            _log(f"{code} 매수 수량 부족, 건너뜀")
            return

        _notify(f"{code} 매수 조건 충족 — {int(buy_qty)}주 @ {current_price:,}")
        kis_api.buy(code, int(buy_qty))

        holdings = kis_api.get_holdings()
        if code in holdings and holdings[code]['qty'] > 0:
            bought.add(code)
            _notify(f"✅ {code} {holdings[code]['qty']}주 매수 완료")

    except Exception as e:
        _log(f"buy error [{code}]: {e}")


def _try_intraday_sell(strategy, bought: set) -> None:
    try:
        holdings = kis_api.get_holdings()
        for code in list(bought):
            h = holdings.get(code)
            if h is None or h['qty'] == 0:
                continue
            if strategy.should_sell(code, h):
                _notify(f"{code} 장중 매도 조건 충족 (수익률 {h['evlu_pfls_rt']:.2f}%) — {h['qty']}주 매도")
                kis_api.sell(code, h['qty'])
    except Exception as e:
        _log(f"intraday sell error: {e}")


def _sell_all(bought: set) -> bool:
    """보유 종목 전량 IOC 매도. 모두 청산되면 True 반환."""
    for _ in range(10):
        holdings = kis_api.get_holdings()
        targets  = {c: h for c, h in holdings.items() if c in SYMBOL_LIST and h['qty'] > 0}
        if not targets:
            _notify("전량 매도 완료")
            return True
        for code, h in targets.items():
            _notify(f"{code} {h['qty']}주 IOC 매도 시도")
            kis_api.sell(code, h['qty'], order_type='15')
            time.sleep(1)
        time.sleep(30)
    return False


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────

def main() -> None:
    strategy = VolatilityBreakout(
        k=0.5,
        short_ma=5,
        long_ma=10,
        take_profit_pct=2.0,
        stop_loss_pct=None,     # 손절 비활성 → -1.0 으로 바꾸면 활성
    )

    bought: set[str] = set()

    kis_api.init_token()

    total_cash = kis_api.get_cash()
    buy_amount = total_cash * BUY_PERCENT

    _notify(f"🚀 System Trading 시작  전략={strategy.describe()}")
    _notify(f"예수금={total_cash:,}원  종목별 주문금액={buy_amount:,.0f}원")

    sold_flag = False

    while True:
        try:
            now     = datetime.now()
            weekday = now.weekday()
            if weekday >= 5:
                _log("주말 — 종료")
                sys.exit(0)

            t = lambda h, m: now.replace(hour=h, minute=m, second=0, microsecond=0)
            T_OPEN       = t(9,  0)
            T_START      = t(9,  5)
            T_SELL_START = t(14, 15)
            T_SELL_END   = t(14, 20)

            # 09:00~09:05 — 기존 보유 종목 등록
            if T_OPEN < now < T_START and not sold_flag:
                sold_flag = True
                holdings = kis_api.get_holdings()
                for code in SYMBOL_LIST:
                    if code in holdings and holdings[code]['qty'] > 0:
                        bought.add(code)
                _log(f"기존 보유 등록: {bought}")

            # 09:05~14:15 — 매수 + 장중 익절/손절
            elif T_START < now < T_SELL_START:
                _try_intraday_sell(strategy, bought)
                if len(bought) < TARGET_BUY_COUNT:
                    for sym in SYMBOL_LIST:
                        if sym not in bought and len(bought) < TARGET_BUY_COUNT:
                            _try_buy(sym, strategy, bought, buy_amount)
                            time.sleep(5)

            # 14:15~14:20 — 전량 매도
            elif T_SELL_START < now < T_SELL_END:
                if _sell_all(bought):
                    _notify("📴 전량 매도 완료 — 프로그램 종료")
                    sys.exit(0)

            # 14:20~ — 강제 종료
            elif now > T_SELL_END:
                _notify("장 마감 — 프로그램 종료")
                sys.exit(0)

        except Exception as e:
            _notify(f"❌ main loop error: {e}")

        time.sleep(10)


if __name__ == '__main__':
    main()
