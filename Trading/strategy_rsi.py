"""
RSI 과매도 반등 전략

매수: RSI(period) <= oversold_level 진입 후 당일 반등 확인
      (전일 RSI 과매도 + 당일 현재가 > 전일 종가)
익절: 수익률 >= take_profit_pct  OR  RSI >= overbought_level
손절: 수익률 <= stop_loss_pct
"""
import pandas as pd
from strategy import Strategy
import kis_api


class RSIOversoldBounce(Strategy):

    def __init__(
        self,
        period: int = 14,
        oversold_level: float = 30.0,
        overbought_level: float = 70.0,
        take_profit_pct: float = 2.0,
        stop_loss_pct: float = -1.5,
    ):
        self.period          = period
        self.oversold_level  = oversold_level
        self.overbought_level = overbought_level
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct
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

    def rsi(self, code: str) -> float:
        """전일 기준 RSI 반환"""
        df = self._ohlcv(code)
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        # 당일 데이터가 포함돼 있으면 제외
        if str(df.iloc[0].name)[:10] == today:
            df = df.iloc[1:]

        closes = df['close'].astype(float).sort_index()  # 오름차순
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        avg_gain = gain.ewm(com=self.period - 1, min_periods=self.period).mean()
        avg_loss = loss.ewm(com=self.period - 1, min_periods=self.period).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi_series = 100 - (100 / (1 + rs))
        return float(rsi_series.iloc[-1])

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        from datetime import datetime
        df = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')

        # 전일 종가
        if str(df.iloc[0].name)[:10] == today:
            prev_close = float(df.iloc[1]['close'])
        else:
            prev_close = float(df.iloc[0]['close'])

        rsi_val = self.rsi(code)
        # 전일 RSI 과매도 + 당일 가격 반등
        return rsi_val <= self.oversold_level and current_price > prev_close

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        # RSI 과매수 도달 시 익절
        try:
            if self.rsi(code) >= self.overbought_level:
                return True
        except Exception:
            pass
        return False

    def describe(self) -> str:
        return (f"RSIOversoldBounce(period={self.period}, "
                f"oversold={self.oversold_level}, overbought={self.overbought_level}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%)")
