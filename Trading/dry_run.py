"""
드라이런 — 실제 주문 없이 전체 하네스 흐름을 시뮬레이션한다.

1. 가상 시장 데이터로 전략 선택
2. 가상 매매 체결 기록
3. Slack 리포트 전송
"""
import random
import trade_logger
import reporter
from datetime import datetime

random.seed(42)

# ──────────────────────────────────────────────
# 가상 시장 데이터 정의
# ──────────────────────────────────────────────

MOCK_MARKET = {
    "gap_pct":        0.72,   # KODEX200 갭업 0.72%
    "prev_range_pct": 1.85,   # 전일 레인지 1.85% (보통)
    "trend":          "up",   # 상승 추세
    "ma5_slope":      0.41,   # MA5 기울기 0.41% (가파름)
    "ma5":            42380,
    "ma20":           41950,
}

MOCK_TRADES = [
    {"code": "122630", "name": "KODEX 레버리지",        "qty": 85,  "buy": 9820,  "sell": 10060, "reason": "tp"},
    {"code": "233740", "name": "KODEX 코스닥150레버리지","qty": 112, "buy": 7350,  "sell": 7620,  "reason": "tp"},
    {"code": "069500", "name": "KODEX 200",             "qty": 230, "buy": 43200, "sell": 43050, "reason": "sl"},
    {"code": "229200", "name": "KODEX 코스닥150",        "qty": 310, "buy": 6480,  "sell": 6650,  "reason": "eod"},
]

CASH_START = 18_200_000


# ──────────────────────────────────────────────
# 전략 선택 시뮬레이션 (strategy_selector 로직 그대로)
# ──────────────────────────────────────────────

def simulate_selector(market: dict) -> str:
    gap   = market["gap_pct"]
    rng   = market["prev_range_pct"]
    trend = market["trend"]
    slope = market["ma5_slope"]

    if gap >= 0.5:
        name   = "GapFollow(gap≥0.3%, MA20, TP=2.0%, SL=-1.5%)"
        reason = f"갭업 {gap:.2f}% ≥ 0.5% 기준 충족"
    elif rng < 1.5:
        name   = "OpeningRangeBreakout(range=30min, MA20, TP=2.0%, SL=-1.5%)"
        reason = f"전일 레인지 {rng:.2f}% < 1.5% (좁은 레인지)"
    elif trend == "up" and slope >= 0.3:
        name   = "DualMomentum(abs=5d+1.0%, top3/10, MA20, TP=2.5%, SL=-1.5%)"
        reason = f"상승 추세 + MA5 기울기 {slope:.2f}% ≥ 0.3%"
    elif trend == "up":
        name   = "VolatilityBreakout(k=0.5, MA5/MA10, TP=2.0%)"
        reason = f"상승 추세 (MA5={market['ma5']:,} > MA20={market['ma20']:,})"
    else:
        name   = "VolatilityBreakout(k=0.5, MA5/MA10, TP=2.0%)"
        reason = "조건 미해당 (fallback)"

    return name, reason


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────

def main():
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f"  ETF 자동매매 하네스 드라이런  ({now})")
    print(f"{'='*55}\n")

    # ── STEP 1. 시장 분석 ──────────────────────
    print("[ STEP 1 ] 시장 분석")
    print(f"  KODEX200 갭업    : {MOCK_MARKET['gap_pct']:+.2f}%")
    print(f"  전일 레인지      : {MOCK_MARKET['prev_range_pct']:.2f}%")
    print(f"  추세             : {MOCK_MARKET['trend']}")
    print(f"  MA5 기울기       : {MOCK_MARKET['ma5_slope']:+.2f}%")
    print(f"  MA5 / MA20       : {MOCK_MARKET['ma5']:,} / {MOCK_MARKET['ma20']:,}\n")

    # ── STEP 2. 전략 선택 ──────────────────────
    print("[ STEP 2 ] 전략 선택")
    strategy_name, reason = simulate_selector(MOCK_MARKET)
    print(f"  → 선택 전략: {strategy_name}")
    print(f"  → 선택 이유: {reason}\n")

    trade_logger.set_strategy(strategy_name)

    # ── STEP 3. 가상 매매 기록 ─────────────────
    print("[ STEP 3 ] 가상 매매 체결 기록")
    print(f"  {'코드':<8} {'종목명':<22} {'수량':>5} {'매수':>7} {'매도':>7} {'손익':>9} {'사유'}")
    print(f"  {'-'*68}")

    for t in MOCK_TRADES:
        pnl = (t["sell"] - t["buy"]) * t["qty"]
        pnl_pct = (t["sell"] - t["buy"]) / t["buy"] * 100
        sign = "+" if pnl >= 0 else ""
        reason_kr = {"tp": "익절", "sl": "손절", "eod": "EOD"}[t["reason"]]
        print(f"  {t['code']:<8} {t['name']:<22} {t['qty']:>5,} "
              f"{t['buy']:>7,} {t['sell']:>7,} "
              f"{sign}{pnl:>8,.0f}원  {reason_kr}")

        trade_logger.log_buy(t["code"], t["name"], t["qty"], t["buy"])
        trade_logger.log_sell(t["code"], t["name"], t["qty"], t["sell"],
                              t["buy"], reason=t["reason"])
    print()

    # ── STEP 4. 결과 집계 ──────────────────────
    print("[ STEP 4 ] 결과 집계")
    total_pnl = sum((t["sell"] - t["buy"]) * t["qty"] for t in MOCK_TRADES)
    cash_end  = CASH_START + total_pnl
    summary   = trade_logger.finalize(CASH_START, cash_end)
    print(f"  총 수익   : {total_pnl:+,.0f}원")
    print(f"  수익률    : {summary['total_pnl_pct']:+.2f}%")
    print(f"  승률      : {summary['win_rate']:.1f}%  "
          f"({summary['win']}승 {summary['lose']}패)\n")

    # ── STEP 5. Slack 리포트 전송 ──────────────
    print("[ STEP 5 ] Slack 리포트 전송")
    reporter.send_daily_report(summary)
    print("\n  ✅ 드라이런 완료")


if __name__ == "__main__":
    main()
