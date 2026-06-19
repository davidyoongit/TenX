"""
갭 방향 추종 전략 (Gap Follow)

매수: 당일 시가가 전일 종가 대비 gap_pct% 이상 갭업
      AND 현재가 > 시가  (갭업 방향 유지 확인)
      AND 현재가 > MA(ma_period)  (추세 필터)
익절: 수익률 >= take_profit_pct
손절: 수익률 <= stop_loss_pct  OR  현재가 < 시가 (갭 방향 이탈)

갭다운 종목은 완전히 패스한다 (인버스 ETF와 혼용 시 방향 혼동 방지).
"""
import pandas as pd
from strategy import Strategy
import kis_api


class GapFollow(Strategy):

    def __init__(
        self,
        gap_pct: float = 0.5,        # 최소 갭업 비율 (%)
        ma_period: int = 20,
        take_profit_pct: float = 2.0,
        stop_loss_pct: float = -1.5,
        exit_below_open: bool = True, # 현재가 < 시가 시 청산
    ):
        self.gap_pct         = gap_pct
        self.ma_period       = ma_period
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct
        self.exit_below_open = exit_below_open
        self._cache: dict[str, dict] = {}

    # ── 내부 헬퍼 ────────────────────────────

    def _ohlcv(self, code: str) -> pd.DataFrame:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if self._cache.get(code, {}).get('date') == today:
            return self._cache[code]['df']
        df = kis_api.get_ohlcv(code)
        self._cache[code] = {'date': today, 'df': df}
        return df

    def _today_open_and_prev_close(self, code: str) -> tuple[float, float]:
        """(당일 시가, 전일 종가) 반환"""
        from datetime import datetime
        df = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            today_open = float(df.iloc[0]['open'])
            prev_close = float(df.iloc[1]['close'])
        else:
            # 장 시작 전이면 전전일/전일로 대체
            today_open = float(df.iloc[0]['close'])
            prev_close = float(df.iloc[1]['close'])
        return today_open, prev_close

    def _ma(self, code: str) -> float:
        from datetime import datetime
        df = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        last = df.iloc[1].name if str(df.iloc[0].name)[:10] == today else df.iloc[0].name
        closes = df['close'].astype(float).sort_index()
        return float(closes.rolling(self.ma_period).mean().loc[last])

    def gap_ratio(self, code: str) -> float:
        """갭 비율 (%) = (시가 - 전일종가) / 전일종가 × 100"""
        today_open, prev_close = self._today_open_and_prev_close(code)
        return (today_open - prev_close) / prev_close * 100

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        today_open, prev_close = self._today_open_and_prev_close(code)
        gap = (today_open - prev_close) / prev_close * 100

        # 갭업 최소치 미달 → 패스
        if gap < self.gap_pct:
            return False

        # 현재가가 시가 위에 있어야 갭업 방향 유지
        if current_price <= today_open:
            return False

        # 추세 필터
        return current_price > self._ma(code)

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        if self.exit_below_open:
            try:
                today_open, _ = self._today_open_and_prev_close(code)
                cur, _, _     = kis_api.get_asking_price(code)
                if cur < today_open:
                    return True
            except Exception:
                pass
        return False

    def describe(self) -> str:
        return (f"GapFollow(gap≥{self.gap_pct}%, MA{self.ma_period}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%, "
                f"exit_below_open={self.exit_below_open})")
