"""
당일 시장 상황을 분석해 최적 전략을 자동 선택한다.

분석 지표:
  - 갭 크기     : 시가/전일종가 비율
  - 전일 변동성  : (고가-저가)/종가 비율
  - 추세 강도    : MA5 vs MA20 기울기 (골든/데드크로스)
  - 최근 전략 성과: trade_logger 10일 히스토리

선택 로직 (우선순위 순):
  1. 갭업 >= 0.5%                → GapFollow
  2. 전일 변동성 낮음 (< 1.5%)   → OpeningRangeBreakout (레인지 장)
  3. 추세 상승 + 변동성 보통      → VolatilityBreakout (기본)
  4. 추세 상승 + 모멘텀 확인      → DualMomentum
  5. RSI 과매도 감지              → RSIOversoldBounce
  6. 그 외                       → VolatilityBreakout (기본 폴백)
"""
from datetime import datetime
import kis_api
import trade_logger

# 전략 임포트
from strategy            import VolatilityBreakout
from strategy_gap        import GapFollow
from strategy_orb        import OpeningRangeBreakout
from strategy_dual_momentum import DualMomentum
from strategy_rsi        import RSIOversoldBounce
from strategy_bollinger  import BollingerBreakout
from strategy_momentum   import MomentumVolumeSurge


# ──────────────────────────────────────────────
# 시장 상황 분석
# ──────────────────────────────────────────────

# KODEX 200 (069500)을 시장 대표 지수로 사용
MARKET_CODE = "069500"


def _analyze_market() -> dict:
    """시장 지표 계산. 실패 시 빈 dict 반환."""
    try:
        df = kis_api.get_ohlcv(MARKET_CODE)
        today = datetime.now().strftime('%Y-%m-%d')

        if str(df.iloc[0].name)[:10] == today:
            today_open = float(df.iloc[0]['open'])
            prev       = df.iloc[1]
            df_hist    = df.iloc[1:]
        else:
            today_open = float(df.iloc[0]['close'])
            prev       = df.iloc[0]
            df_hist    = df

        prev_close  = float(prev['close'])
        prev_high   = float(prev['high'])
        prev_low    = float(prev['low'])

        gap_pct       = (today_open - prev_close) / prev_close * 100
        prev_range_pct = (prev_high - prev_low) / prev_close * 100

        closes = df_hist['close'].astype(float).sort_index()
        ma5    = float(closes.rolling(5).mean().iloc[-1])
        ma20   = float(closes.rolling(20).mean().iloc[-1])
        ma5_2  = float(closes.rolling(5).mean().iloc[-2])  # 전전일 MA5
        trend  = "up" if ma5 > ma20 else "down"
        ma5_slope = (ma5 - ma5_2) / ma5_2 * 100  # MA5 기울기(%)

        return {
            "gap_pct":        round(gap_pct, 2),
            "prev_range_pct": round(prev_range_pct, 2),
            "trend":          trend,
            "ma5_slope":      round(ma5_slope, 2),
            "ma5":            ma5,
            "ma20":           ma20,
        }
    except Exception as e:
        print(f"[selector] market analysis failed: {e}")
        return {}


def _best_recent_strategy() -> str | None:
    """최근 10일 히스토리에서 수익률 평균이 가장 높은 전략 이름 반환"""
    history = trade_logger.load_history(10)
    if not history:
        return None
    perf: dict[str, list[float]] = {}
    for h in history:
        s = h.get("strategy")
        p = h.get("total_pnl_pct", 0)
        if s:
            perf.setdefault(s, []).append(p)
    if not perf:
        return None
    avg = {s: sum(v) / len(v) for s, v in perf.items()}
    return max(avg, key=lambda s: avg[s])


# ──────────────────────────────────────────────
# 전략 선택
# ──────────────────────────────────────────────

def select() -> object:
    """
    당일 최적 전략 인스턴스를 반환하고 선택 이유를 출력한다.
    """
    market = _analyze_market()
    gap    = market.get("gap_pct", 0)
    rng    = market.get("prev_range_pct", 2.0)
    trend  = market.get("trend", "up")
    slope  = market.get("ma5_slope", 0)

    reason = ""
    strategy = None

    # 1. 갭업 강함 → 갭 추종
    if gap >= 0.5:
        strategy = GapFollow(gap_pct=0.3, take_profit_pct=2.0, stop_loss_pct=-1.5)
        reason   = f"갭업 {gap:.2f}% → GapFollow"

    # 2. 전일 변동성 작음 → 레인지 브레이크아웃
    elif rng < 1.5:
        strategy = OpeningRangeBreakout(orb_minutes=30, take_profit_pct=2.0, stop_loss_pct=-1.5)
        reason   = f"전일 레인지 {rng:.2f}% (좁음) → ORB"

    # 3. 추세 상승 + MA5 기울기 가파름 → 듀얼 모멘텀
    elif trend == "up" and slope >= 0.3:
        strategy = DualMomentum(abs_days=5, top_n=3, take_profit_pct=2.5, stop_loss_pct=-1.5)
        reason   = f"상승 추세 + MA5 기울기 {slope:.2f}% → DualMomentum"

    # 4. 추세 상승 + 기본 변동성 → 변동성 돌파
    elif trend == "up":
        strategy = VolatilityBreakout(k=0.5, take_profit_pct=2.0, stop_loss_pct=-1.5)
        reason   = f"상승 추세 (MA5>{market.get('ma5',0):.0f}) → VolatilityBreakout"

    # 5. 하락 추세 → RSI 과매도 반등 시도
    elif trend == "down" and slope <= -0.3:
        strategy = RSIOversoldBounce(period=14, oversold_level=30,
                                     take_profit_pct=1.5, stop_loss_pct=-1.0)
        reason   = f"하락 추세 + MA5 기울기 {slope:.2f}% → RSIOversoldBounce"

    # 6. 시장 데이터 없거나 판단 불가 → 기본 폴백
    else:
        strategy = VolatilityBreakout(k=0.5, take_profit_pct=2.0)
        reason   = "조건 미해당 → VolatilityBreakout (fallback)"

    # 최근 성과가 좋은 전략이 있으면 메모만 남김
    best = _best_recent_strategy()
    if best:
        print(f"[selector] 최근 10일 최고 성과 전략: {best}")

    print(f"[selector] 선택 전략: {strategy.describe()}")
    print(f"[selector] 선택 이유: {reason}")
    print(f"[selector] 시장 지표: {market}")

    return strategy
