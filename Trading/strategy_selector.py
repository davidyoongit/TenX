"""
당일 시장 상황을 분석해 최적 전략을 자동 선택한다.

분석 지표:
  - 갭 크기     : 시가/전일종가 비율
  - 전일 변동성  : (고가-저가)/종가 비율
  - 추세 강도    : MA5 vs MA20 기울기 (골든/데드크로스)
  - 최근 전략 성과: trade_logger 10일 히스토리

선택 로직 (우선순위 순):
  시장 기본 전략 (KODEX 200 기준)
  1. 갭업 >= 0.5%                → GapFollow
  2. 전일 변동성 낮음 (< 1.5%)   → OpeningRangeBreakout (레인지 장)
  3. 추세 상승 + 모멘텀 확인      → DualMomentum
  4. 추세 상승 + 변동성 정상      → VolatilityBreakout
  4b. 추세 상승 + 반전 리스크     → RSIOversoldBounce (보수)
  5. 추세 하락 + 기울기 급락      → RSIOversoldBounce
  6. 그 외                       → VolatilityBreakout (기본 폴백)

  종목 개별 오버라이드 (select_multi)
  - 개별 갭업 >= 0.5%    → GapFollow (비레버리지 200ETF 제외)
  - 개별 갭다운 <= -0.5% → RSIOversoldBounce (보수, 당일 진입 억제)
  - 전일 레인지 < 1.5%   → OpeningRangeBreakout
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

MARKET_CODE = "069500"  # KODEX 200 — 시장 대표 지수


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

        gap_pct        = (today_open - prev_close) / prev_close * 100
        prev_range_pct = (prev_high - prev_low) / prev_close * 100

        closes = df_hist['close'].astype(float).sort_index()
        ma5    = float(closes.rolling(5).mean().iloc[-1])
        ma20   = float(closes.rolling(20).mean().iloc[-1])
        ma5_2  = float(closes.rolling(5).mean().iloc[-2])
        trend  = "up" if ma5 > ma20 else "down"
        ma5_slope = (ma5 - ma5_2) / ma5_2 * 100

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
# 전략 선택 (내부)
# ──────────────────────────────────────────────

def _select_from_market(market: dict) -> object:
    """시장 지표에서 기본 전략 인스턴스를 반환한다."""
    gap   = market.get("gap_pct", 0)
    rng   = market.get("prev_range_pct", 2.0)
    trend = market.get("trend", "up")
    slope = market.get("ma5_slope", 0)

    if gap >= 0.5:
        return GapFollow(gap_pct=0.3, take_profit_pct=2.0, stop_loss_pct=-1.5)
    elif rng < 1.5:
        return OpeningRangeBreakout(orb_minutes=30, take_profit_pct=2.0, stop_loss_pct=-1.5)
    elif trend == "up" and slope >= 0.3:
        return DualMomentum(abs_days=5, top_n=3, take_profit_pct=2.5, stop_loss_pct=-1.5)
    elif trend == "up" and slope >= 0 and rng < 5.0:
        return VolatilityBreakout(k=0.5, take_profit_pct=2.0, stop_loss_pct=-1.5)
    elif trend == "up":
        return RSIOversoldBounce(period=14, oversold_level=30,
                                  take_profit_pct=1.5, stop_loss_pct=-1.5)
    elif trend == "down" and slope <= -0.3:
        return RSIOversoldBounce(period=14, oversold_level=30,
                                  take_profit_pct=1.5, stop_loss_pct=-1.0)
    else:
        return VolatilityBreakout(k=0.5, take_profit_pct=2.0)


def _select_for_symbol(code: str, market: dict, base) -> object:
    """
    개별 종목 OHLCV를 분석해 종목별 최적 전략을 선택한다.
    기본 전략과 다른 조건이 감지되면 오버라이드한다.
    분석 실패 시 base 전략 반환.
    """
    try:
        df = kis_api.get_ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            today_open = float(df.iloc[0]['open'])
            prev = df.iloc[1]
        else:
            today_open = float(df.iloc[0]['close'])
            prev = df.iloc[0]

        prev_close = float(prev['close'])
        prev_high  = float(prev['high'])
        prev_low   = float(prev['low'])

        sym_gap = (today_open - prev_close) / prev_close * 100
        sym_rng = (prev_high - prev_low) / prev_close * 100

        # 개별 갭업 강함 → GapFollow
        if sym_gap >= 0.5:
            print(f"[selector] {code}  갭업 {sym_gap:.2f}% → GapFollow (오버라이드)")
            return GapFollow(gap_pct=0.3, take_profit_pct=2.0, stop_loss_pct=-1.5)

        # 개별 갭다운 강함 → 당일 진입 보수 (RSI 반등 대기)
        if sym_gap <= -0.5:
            print(f"[selector] {code}  갭다운 {sym_gap:.2f}% → RSIOversoldBounce 보수 (오버라이드)")
            return RSIOversoldBounce(period=14, oversold_level=35,
                                      take_profit_pct=1.5, stop_loss_pct=-1.0)

        # 전일 레인지 좁음 → ORB
        if sym_rng < 1.5:
            print(f"[selector] {code}  레인지 {sym_rng:.2f}% → ORB (오버라이드)")
            return OpeningRangeBreakout(orb_minutes=30, take_profit_pct=2.0, stop_loss_pct=-1.5)

        return base

    except Exception as e:
        print(f"[selector] {code} 개별 분석 실패, 기본 전략 사용: {e}")
        return base


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def select_multi(symbol_list: list) -> dict:
    """
    각 종목에 대해 최적 전략을 개별 선택한다.

    1. KODEX 200으로 시장 기본 전략 결정
    2. 각 종목 OHLCV 개별 분석 → 갭/변동성 패턴이 다르면 오버라이드
    Returns {code: Strategy}
    """
    market = _analyze_market()
    base   = _select_from_market(market)

    best = _best_recent_strategy()
    if best:
        print(f"[selector] 최근 10일 최고 성과 전략: {best}")
    print(f"[selector] 시장 기본 전략: {base.describe()}")
    print(f"[selector] 시장 지표: {market}")

    result = {}
    for code in symbol_list:
        result[code] = _select_for_symbol(code, market, base)

    from collections import Counter
    counts = Counter(s.__class__.__name__ for s in result.values())
    summary = ", ".join(f"{cls}×{n}" for cls, n in sorted(counts.items()))
    print(f"[selector] 활성 전략: {summary}")
    return result


def select() -> object:
    """하위 호환용: 시장 기본 전략 단일 인스턴스 반환."""
    market   = _analyze_market()
    strategy = _select_from_market(market)

    best = _best_recent_strategy()
    if best:
        print(f"[selector] 최근 10일 최고 성과 전략: {best}")

    gap   = market.get("gap_pct", 0)
    rng   = market.get("prev_range_pct", 2.0)
    trend = market.get("trend", "up")
    slope = market.get("ma5_slope", 0)
    if gap >= 0.5:
        reason = f"갭업 {gap:.2f}% → GapFollow"
    elif rng < 1.5:
        reason = f"전일 레인지 {rng:.2f}% (좁음) → ORB"
    elif trend == "up" and slope >= 0.3:
        reason = f"상승 추세 + MA5 기울기 {slope:.2f}% → DualMomentum"
    elif trend == "up" and slope >= 0 and rng < 5.0:
        reason = f"상승 추세 (기울기 {slope:.2f}%, 레인지 {rng:.2f}%) → VolatilityBreakout"
    elif trend == "up":
        reason = f"상승 추세이나 반전 리스크(기울기 {slope:.2f}%, 레인지 {rng:.2f}%) → RSIOversoldBounce (보수)"
    elif trend == "down" and slope <= -0.3:
        reason = f"하락 추세 + MA5 기울기 {slope:.2f}% → RSIOversoldBounce"
    else:
        reason = "조건 미해당 → VolatilityBreakout (fallback)"

    print(f"[selector] 선택 전략: {strategy.describe()}")
    print(f"[selector] 선택 이유: {reason}")
    print(f"[selector] 시장 지표: {market}")
    return strategy
