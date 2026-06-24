"""
듀얼 모멘텀 전략 (Dual Momentum)

절대 모멘텀: 현재가가 N일 전 종가 대비 abs_pct% 이상 상승
상대 모멘텀: symbol_list 중 당일 수익률(현재가/전일종가 - 1) 상위 top_n개에 속할 때만 매수

두 조건을 모두 만족하는 종목만 매수 → 그날 가장 강한 ETF에 집중.
trader.py가 symbol_list 순서로 buy_etf()를 호출하므로,
should_buy() 내부에서 전체 심볼의 당일 수익률을 비교해 상대 순위를 판단한다.

매수: 절대 모멘텀 OK  AND  상대 순위 <= top_n  AND  현재가 > MA(ma_period)
익절: 수익률 >= take_profit_pct
손절: 수익률 <= stop_loss_pct
"""
import pandas as pd
from datetime import datetime
from strategy import Strategy
import kis_api


# trader.py와 동일한 심볼 리스트 (상대 순위 계산 대상)
DEFAULT_SYMBOL_LIST = [
    '252670', '251340', '233740', '114800', '122630',
    '229200', '069500', '250780', '148020', '305540',
]


class DualMomentum(Strategy):

    def __init__(
        self,
        symbol_list: list[str] = None,
        abs_days: int = 5,
        abs_pct: float = 0.5,
        top_n: int = 3,
        ma_period: int = 20,
        take_profit_pct: float = 1.5,
        stop_loss_pct: float = -1.5,
    ):
        self.symbol_list     = symbol_list or DEFAULT_SYMBOL_LIST
        self.abs_days        = abs_days
        self.abs_pct         = abs_pct
        self.top_n           = top_n
        self.ma_period       = ma_period
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct   = stop_loss_pct

        self._ohlcv_cache: dict[str, dict] = {}
        # 상대 모멘텀 순위 캐시 (분 단위로 갱신)
        self._rank_cache: dict = {'minute': -1, 'ranks': {}}

    # ── 내부 헬퍼 ────────────────────────────

    def _ohlcv(self, code: str) -> pd.DataFrame:
        today = datetime.now().strftime('%Y-%m-%d')
        if self._ohlcv_cache.get(code, {}).get('date') == today:
            return self._ohlcv_cache[code]['df']
        df = kis_api.get_ohlcv(code)
        self._ohlcv_cache[code] = {'date': today, 'df': df}
        return df

    def _prev_close(self, code: str) -> float:
        df    = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        if str(df.iloc[0].name)[:10] == today:
            return float(df.iloc[1]['close'])
        return float(df.iloc[0]['close'])

    def _base_close(self, code: str) -> float:
        """abs_days 전 종가"""
        df    = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        start = 1 if str(df.iloc[0].name)[:10] == today else 0
        df_hist = df.iloc[start:].sort_index()
        if len(df_hist) < self.abs_days:
            return float(df_hist.iloc[0]['close'])
        return float(df_hist.iloc[-(self.abs_days)]['close'])

    def _ma(self, code: str) -> float:
        df    = self._ohlcv(code)
        today = datetime.now().strftime('%Y-%m-%d')
        last  = df.iloc[1].name if str(df.iloc[0].name)[:10] == today else df.iloc[0].name
        closes = df['close'].astype(float).sort_index()
        return float(closes.rolling(self.ma_period).mean().loc[last])

    # ── 상대 모멘텀 순위 계산 ─────────────────

    def _relative_ranks(self) -> dict[str, int]:
        """
        symbol_list 전체의 당일 수익률(현재가/전일종가)을 계산해
        {code: rank} 딕셔너리 반환 (rank 1 = 가장 강함).
        1분 캐시로 API 호출 최소화.
        """
        now_min = datetime.now().hour * 60 + datetime.now().minute
        if self._rank_cache['minute'] == now_min:
            return self._rank_cache['ranks']

        scores = {}
        for code in self.symbol_list:
            try:
                cur, _, _ = kis_api.get_asking_price(code)
                prev      = self._prev_close(code)
                scores[code] = (cur - prev) / prev * 100
            except Exception:
                scores[code] = -999.0

        sorted_codes = sorted(scores, key=lambda c: scores[c], reverse=True)
        ranks = {code: rank + 1 for rank, code in enumerate(sorted_codes)}
        self._rank_cache = {'minute': now_min, 'ranks': ranks}
        return ranks

    # ── 인터페이스 구현 ───────────────────────

    def should_buy(self, code: str, current_price: int, ask_price: int) -> bool:
        # 절대 모멘텀 확인
        base   = self._base_close(code)
        abs_ok = current_price > base * (1 + self.abs_pct / 100)
        if not abs_ok:
            return False

        # MA 필터
        if current_price <= self._ma(code):
            return False

        # 상대 모멘텀: 상위 top_n에 속하는지
        ranks = self._relative_ranks()
        rank  = ranks.get(code, 999)
        return rank <= self.top_n

    def should_sell(self, code: str, holding: dict) -> bool:
        pnl = holding['evlu_pfls_rt']
        if pnl >= self.take_profit_pct:
            return True
        if pnl <= self.stop_loss_pct:
            return True
        return False

    def describe(self) -> str:
        return (f"DualMomentum(abs={self.abs_days}d+{self.abs_pct}%, "
                f"top{self.top_n}/{len(self.symbol_list)}, "
                f"MA{self.ma_period}, "
                f"TP={self.take_profit_pct}%, SL={self.stop_loss_pct}%)")
