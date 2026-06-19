"""
오전 레인지 브레이크아웃 전략 (Opening Range Breakout)

09:05 ~ orb_end_time 구간의 고가/저가를 레인지로 확정.
이후 현재가가 레인지 상단을 돌파하면 매수.

레인지는 당일 get_asking_price() 폴링으로 직접 추적한다.
trader.py의 매수 루프(10초 간격)가 자동으로 레인지를 쌓아준다.

매수: 현재가 > orb_high (오전 레인지 고가 돌파)
      AND orb 확정 시간 이후 (orb_end_time 지났을 때만 진입)
      AND 현재가 > MA(ma_period)
익절: 수익률 >= take_profit_pct
손절: 수익률 <= stop_loss_pct  OR  현재가 < orb_low (레인지 하단 이탈)
"""
import time
import pandas as pd
from datetime import datetime
from strategy import Strategy
import kis_api


class OpeningRangeBreakout(Strategy):

    def __init__(
        self,
        orb_minutes: int = 30,          # 장 시작 후 레인지 확정까지 분 수 (기본 30분)
        breakout_pct: float = 0.0,      # 고가 대비 추가 여유 % (0이면 정확히 고가 돌파)
        ma_period: int = 20,
        take_profit_pct: float = 2.5,
        stop_loss_pct: float = -1.5,
        exit_below_orb_low: bool = True,
    ):
        self.orb_minutes        = orb_minutes
        self.breakout_pct       = breakout_pct
        self.ma_period          = ma_period
        self.take_profit_pct    = take_profit_pct
        self.stop_loss_pct      = stop_loss_pct
        self.exit_below_orb_low = exit_below_orb_low

        # 당일 레인지 추적 상태 {code: {high, low, locked, lock_time}}
        self._orb: dict[str, dict] = {}
        self._ohlcv_cache: dict[str, dict] = {}

    # ── 레인지 관리 ───────────────────────────

    def _orb_lock_time(self) -> datetime:
        """레인지 확정 시각 = 09:05 + orb_minutes"""
        now = datetime.now()
        base = now.replace(hour=9, minute=5, second=0, microsecond=0)
        from datetime import timedelta
        return base + timedelta(minutes=self.orb_minutes)

    def update_range(self, code: str, current_price: int) -> None:
        """
        trader.py 매수 루프에서 매 tick마다 호출.
        레인지 확정 전이면 고/저가를 갱신하고,
        확정 이후엔 무시한다.
        """
        now       = datetime.now()
        lock_time = self._orb_lock_time()

        if code not in self._orb:
            self._orb[code] = {'high': current_price, 'low': current_price,
                               'locked': False, 'lock_time': lock_time}
            return

        state = self._orb[code]
        if state['locked']:
            return

        if now >= lock_time:
            state['locked'] = True
            return

        state['high'] = max(state['high'], current_price)
        state['low']  = min(state['low'],  current_price)

    def is_range_locked(self, code: str) -> bool:
        return self._orb.get(code, {}).get('locked', False)

    def orb_high(self, code: str) -> float | None:
        return self._orb.get(code, {}).get('high')

    def orb_low(self, code: str) -> float | None:
        return self._orb.get(code, {}).get('low')

    # ── OHLCV / MA ───────────────────────────

    def _ohlcv(self, code: str) -> pd.DataFrame:
        today = datetime.now().strftime('%Y-%m-%d')
        if self._ohlcv_cache.get(code, {}).get('date') == today:
            return self._ohlcv_cache[code]['df']
        df = kis_api.get_ohlcv(code)
        self._ohlcv_cache[code] = {'date': today, 'df': df}
        return df

    def _ma(self, code: str) -> float:
        df    = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        last  = df.iloc[1].name if str(df.iloc[0].name)[:10] == today else df.iloc[0].name
        closes = df['close'].astype(float).sort_index()
        return float(closes.rolling(self.ma_period).mean().loc[last])

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        # 레인지 갱신
        self.update_range(code, current_price)

        # 레인지 미확정 → 진입 안 함
        if not self.is_range_locked(code):
            return False

        high = self.orb_high(code)
        if high is None:
            return False

        # 돌파 기준: orb_high × (1 + breakout_pct/100)
        threshold = high * (1 + self.breakout_pct / 100)

        return current_price > threshold and current_price > self._ma(code)

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        if self.exit_below_orb_low:
            try:
                low = self.orb_low(code)
                cur, _, _ = kis_api.get_asking_price(code)
                if low is not None and cur < low:
                    return True
            except Exception:
                pass
        return False

    def describe(self) -> str:
        return (f"OpeningRangeBreakout(range={self.orb_minutes}min, "
                f"breakout+{self.breakout_pct}%, MA{self.ma_period}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%)")
