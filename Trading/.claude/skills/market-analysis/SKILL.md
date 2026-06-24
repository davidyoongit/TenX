---
name: market-analysis
description: "ETF 자동매매를 위한 시장 분석 스킬. KODEX 200 OHLCV 데이터로 갭 크기·전일 변동성·MA5/MA20 기울기·추세 방향을 계산하고, strategy_selector.py 로직에 따라 당일 최적 전략을 선택한다. '오늘 어떤 전략?', '시장 분석해줘', '전략 선택', '장전 분석', '오늘 장세', '시장 지표 확인', '최근 성과 좋은 전략' 등 시장 상황 분석이나 전략 선택 요청 시 반드시 이 스킬을 사용할 것. 단, 코드 리뷰·파일 설명·파라미터 수정·리스크 검증은 이 스킬 범위가 아니므로 트리거하지 말 것."
---

## 분석 지표

| 지표 | 계산 방법 | 임계값 |
|------|---------|-------|
| 갭 크기 | (시가 - 전일종가) / 전일종가 × 100 | ≥ 0.5% |
| 전일 변동성 | (전일고가 - 전일저가) / 전일종가 × 100 | < 1.5% |
| MA5 기울기 | (MA5 - 전전일 MA5) / 전전일 MA5 × 100 | ≥ 0.3% / ≤ -0.3% |
| 추세 | MA5 > MA20 → up, MA5 ≤ MA20 → down | - |

## 전략 선택 우선순위

strategy_selector.py의 `select()` 로직을 정확히 반영한다:

1. `gap_pct ≥ 0.5` → `GapFollow(gap_pct=0.3, take_profit_pct=2.0, stop_loss_pct=-1.5)`
2. `prev_range_pct < 1.5` → `OpeningRangeBreakout(orb_minutes=30, take_profit_pct=2.0, stop_loss_pct=-1.5)`
3. `trend == "up" and slope ≥ 0.3` → `DualMomentum(abs_days=5, top_n=3, take_profit_pct=2.5, stop_loss_pct=-1.5)`
4. `trend == "up"` → `VolatilityBreakout(k=0.5, take_profit_pct=2.0, stop_loss_pct=-1.5)`
5. `trend == "down" and slope ≤ -0.3` → `RSIOversoldBounce(period=14, oversold_level=30, take_profit_pct=1.5, stop_loss_pct=-1.0)`
6. 그 외 → `VolatilityBreakout(k=0.5, take_profit_pct=2.0)` (fallback)

## 최근 성과 반영

`trade_logger.load_history(10)`으로 최근 10일 전략별 평균 수익률을 조회한다.
최고 성과 전략이 선택된 전략과 다르면 그 사실을 명시적으로 보고하되 강제 override는 하지 않는다.

## 산출물 형식

`_workspace/01_market_analysis.md`에 저장:

```markdown
## 시장 분석 결과 — {YYYY-MM-DD}

### 시장 지표
- 갭 크기: {gap_pct}%
- 전일 변동성: {prev_range_pct}%
- 추세: {up/down}
- MA5 기울기: {ma5_slope}%
- MA5: {ma5}, MA20: {ma20}

### 전략 선택
- 선택 전략: {전략명 + 파라미터}
- 선택 이유: {우선순위 몇 번 조건에 해당}
- 최근 10일 최고 성과 전략: {전략명 or '기록 없음'}
```

## 에러 처리

- API 호출 실패 시: 빈 dict 반환, VolatilityBreakout fallback 권고 기록
- OHLCV 데이터 < 20행: "데이터 부족, fallback 적용" 명시
