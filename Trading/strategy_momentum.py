"""
모멘텀 + 거래량 급증 전략

매수: 현재가 > N일 전 종가 × (1 + momentum_pct/100)  — 가격 모멘텀
      AND 당일 거래량 > 과거 avg_volume_days 평균 거래량 × volume_mult  — 거래량 급증
      AND 현재가 > MA(ma_period)  — 추세 필터
익절: 수익률 >= take_profit_pct
손절: 수익률 <= stop_loss_pct

거래량은 OHLCV output2의 acml_vol(누적거래량) 컬럼을 사용한다.
"""
import pandas as pd
from strategy import Strategy
import kis_api


class MomentumVolumeSurge(Strategy):

    def __init__(
        self,
        momentum_days: int = 5,
        momentum_pct: float = 3.0,
        volume_mult: float = 2.0,
        avg_volume_days: int = 20,
        ma_period: int = 20,
        take_profit_pct: float = 3.0,
        stop_loss_pct: float = -2.0,
    ):
        self.momentum_days   = momentum_days
        self.momentum_pct    = momentum_pct
        self.volume_mult     = volume_mult
        self.avg_volume_days = avg_volume_days
        self.ma_period       = ma_period
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct
        self._cache: dict[str, dict] = {}

    # ── 내부 헬퍼 ────────────────────────────

    def _ohlcv_full(self, code: str) -> pd.DataFrame:
        """거래량 포함 풀 OHLCV — mojito output2 직접 파싱"""
        from datetime import datetime
        import kis_api as api
        today = datetime.now().strftime('%Y-%m-%d')
        if self._cache.get(code, {}).get('date') == today:
            return self._cache[code]['df']

        resp = api.broker.fetch_ohlcv(symbol=code, timeframe='D', adj_price=True)
        df = pd.DataFrame(resp['output2'])
        dt = pd.to_datetime(df['stck_bsop_date'], format="%Y%m%d")
        df.set_index(dt, inplace=True)
        df = df[['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr', 'acml_vol']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df.index.name = "date"
        df = df.astype({'open': float, 'high': float, 'low': float,
                        'close': float, 'volume': float})
        self._cache[code] = {'date': today, 'df': df}
        return df

    def _prev_df(self, code: str) -> pd.DataFrame:
        """당일 데이터 제외한 전일 이전 데이터"""
        from datetime import datetime
        df = self._ohlcv_full(code)
        today = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            return df.iloc[1:].sort_index()
        return df.sort_index()

    def momentum_ok(self, code: str, current_price: int) -> bool:
        """현재가가 N일 전 종가 대비 momentum_pct% 이상 상승했는지"""
        df = self._prev_df(code)
        if len(df) < self.momentum_days + 1:
            return False
        base_close = float(df.iloc[-(self.momentum_days)]['close'])
        threshold  = base_close * (1 + self.momentum_pct / 100)
        return current_price > threshold

    def volume_surge_ok(self, code: str) -> bool:
        """당일 거래량이 과거 평균 대비 volume_mult 배 이상인지"""
        df = self._ohlcv_full(code)
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        today_vol = None
        if str(df.iloc[0].name)[:10] == today:
            today_vol = float(df.iloc[0]['volume'])
            hist_df   = df.iloc[1:].sort_index()
        else:
            # 장 마감 후 조회 시 당일 데이터가 없으면 거래량 조건 통과로 처리
            return True

        if today_vol is None or today_vol == 0:
            return False

        avg_vol = float(hist_df['volume'].tail(self.avg_volume_days).mean())
        if avg_vol == 0:
            return False
        return today_vol > avg_vol * self.volume_mult

    def ma_ok(self, code: str, current_price: int) -> bool:
        df = self._prev_df(code)
        if len(df) < self.ma_period:
            return False
        ma = float(df['close'].rolling(self.ma_period).mean().iloc[-1])
        return current_price > ma

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        return (self.momentum_ok(code, current_price)
                and self.volume_surge_ok(code)
                and self.ma_ok(code, current_price))

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        return False

    def describe(self) -> str:
        return (f"MomentumVolumeSurge("
                f"momentum={self.momentum_days}d+{self.momentum_pct}%, "
                f"volume×{self.volume_mult}/{self.avg_volume_days}d, "
                f"MA{self.ma_period}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%)")
