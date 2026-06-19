"""
볼린저밴드 돌파 전략

매수: 현재가 > 상단밴드 (Upper Band) 돌파  AND  현재가 > MA(long_ma)
      (추세 상승 확인 후 밴드 상단 돌파 시 모멘텀 진입)
익절: 수익률 >= take_profit_pct
손절: 수익률 <= stop_loss_pct  OR  현재가 < 중간밴드(MA) 이탈
"""
import pandas as pd
from strategy import Strategy
import kis_api


class BollingerBreakout(Strategy):

    def __init__(
        self,
        period: int = 20,
        std_mult: float = 2.0,
        long_ma: int = 60,
        take_profit_pct: float = 3.0,
        stop_loss_pct: float = -2.0,
        exit_on_midband: bool = True,
    ):
        self.period          = period
        self.std_mult        = std_mult
        self.long_ma         = long_ma
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct
        self.exit_on_midband = exit_on_midband
        self._cache: dict[str, dict] = {}
        self._entry_price: dict[str, float] = {}  # 밴드 이탈 판단용

    # ── 내부 헬퍼 ────────────────────────────

    def _ohlcv(self, code: str) -> pd.DataFrame:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if self._cache.get(code, {}).get('date') == today:
            return self._cache[code]['df']
        df = kis_api.get_ohlcv(code)
        self._cache[code] = {'date': today, 'df': df}
        return df

    def _bands(self, code: str) -> tuple[float, float, float]:
        """(upper, mid, lower) 전일 기준 볼린저밴드"""
        from datetime import datetime
        df = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            last = df.iloc[1].name
            df = df.iloc[1:]
        else:
            last = df.iloc[0].name

        closes = df['close'].astype(float).sort_index()
        mid    = closes.rolling(self.period).mean()
        std    = closes.rolling(self.period).std()
        upper  = mid + self.std_mult * std
        lower  = mid - self.std_mult * std

        return float(upper.loc[last]), float(mid.loc[last]), float(lower.loc[last])

    def _long_ma(self, code: str) -> float:
        from datetime import datetime
        df = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        last = df.iloc[1].name if str(df.iloc[0].name)[:10] == today else df.iloc[0].name
        closes = df['close'].astype(float).sort_index()
        return float(closes.rolling(self.long_ma).mean().loc[last])

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        upper, mid, lower = self._bands(code)
        ma_long = self._long_ma(code)
        # 상단밴드 돌파 + 장기 이동평균 위
        return current_price > upper and current_price > ma_long

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        # 중간밴드 이탈 시 청산 (옵션)
        if self.exit_on_midband:
            try:
                _, mid, _ = self._bands(code)
                cur, _, _ = kis_api.get_asking_price(code)
                if cur < mid:
                    return True
            except Exception:
                pass
        return False

    def describe(self) -> str:
        return (f"BollingerBreakout(period={self.period}, "
                f"std×{self.std_mult}, MA{self.long_ma}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%, "
                f"midband_exit={self.exit_on_midband})")
