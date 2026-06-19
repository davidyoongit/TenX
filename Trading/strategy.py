"""
매매 전략 베이스 + 구현체.

새 전략을 추가하려면 Strategy를 상속해서
should_buy() / should_sell() 만 구현하면 된다.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import pandas as pd
import kis_api


# ──────────────────────────────────────────────
# 인터페이스
# ──────────────────────────────────────────────

class Strategy(ABC):
    """trader.py가 의존하는 전략 인터페이스"""

    @abstractmethod
    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        """매수 조건 충족 여부"""

    @abstractmethod
    def should_sell(self, code: str, holding: dict) -> bool:
        """장중 익절/손절 조건 충족 여부 (14:15 일괄 매도와 별개)"""

    def describe(self) -> str:
        return self.__class__.__name__


# ──────────────────────────────────────────────
# 구현체 1 — 변동성 돌파 + 이동평균 필터
# ──────────────────────────────────────────────

class VolatilityBreakout(Strategy):
    """
    매수: 현재가 > 목표가  AND  현재가 > MA(short)  AND  현재가 > MA(long)
         목표가 = 당일 시가 + (전일 고가 - 전일 저가) × k
    익절: 수익률 >= take_profit_pct
    손절: 수익률 <= stop_loss_pct  (None이면 비활성)
    """

    def __init__(self, k: float = 0.5, short_ma: int = 5, long_ma: int = 10,
                 take_profit_pct: float = 2.0, stop_loss_pct: float | None = None):
        self.k               = k
        self.short_ma        = short_ma
        self.long_ma         = long_ma
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct
        self._cache: dict[str, dict] = {}   # ohlcv 캐시 (당일 1회)

    # ── 내부 헬퍼 ────────────────────────────

    def _ohlcv(self, code: str) -> pd.DataFrame:
        today = datetime.now().strftime('%Y-%m-%d')
        if self._cache.get(code, {}).get('date') == today:
            return self._cache[code]['df']
        df = kis_api.get_ohlcv(code)
        self._cache[code] = {'date': today, 'df': df}
        return df

    def target_price(self, code: str) -> float:
        df     = self._ohlcv(code)
        today  = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            today_open = float(df.iloc[0]['open'])
            prev       = df.iloc[1]
        else:
            prev       = df.iloc[0]
            today_open = float(prev['close'])
        return today_open + (float(prev['high']) - float(prev['low'])) * self.k

    def moving_average(self, code: str, window: int) -> float:
        df    = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        last  = df.iloc[1].name if str(df.iloc[0].name)[:10] == today else df.iloc[0].name
        return df['close'].astype(float).sort_index().rolling(window).mean().loc[last]

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        tp   = self.target_price(code)
        ma_s = self.moving_average(code, self.short_ma)
        ma_l = self.moving_average(code, self.long_ma)
        return current_price > tp and current_price > ma_s and current_price > ma_l

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if self.stop_loss_pct is not None and pnl <= self.stop_loss_pct:
            return True
        return False

    def describe(self) -> str:
        return (f"VolatilityBreakout(k={self.k}, "
                f"MA{self.short_ma}/MA{self.long_ma}, "
                f"TP={self.take_profit_pct}%, "
                f"SL={self.stop_loss_pct}%)")


# ──────────────────────────────────────────────
# 여기에 새 전략을 추가한다
# ──────────────────────────────────────────────

# class MomentumStrategy(Strategy):
#     ...
