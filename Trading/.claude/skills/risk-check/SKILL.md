---
name: risk-check
description: "ETF 자동매매 전략의 위험 파라미터를 검증하고 실계좌 안전을 보장하는 스킬. 손익 경계값·투자 비중·직접 API 호출 여부를 PASS/WARN/BLOCK으로 판정한다. '이 전략 안전한가?', '파라미터 검토해줘', '손절 조건 확인', '실계좌 적용 전 검증', '위험 체크', '리스크 점검', '전략 검증', '올려도 돼?', '써도 괜찮아?' 등 가능 여부 판단·안전성 검토 요청 시 반드시 이 스킬을 사용할 것. 단, 파라미터를 실제로 수정하는 요청(바꿔줘·수정해줘)은 strategy-dev 스킬이 담당하므로 이 스킬을 트리거하지 말 것."
---

## 검증 항목 및 기준

| 항목 | 기준 | 판정 |
|------|------|------|
| 실계좌 직접 호출 | strategy_*.py에 `kis_api` import/호출 존재 | BLOCK |
| take_profit_pct | 0.5 ~ 5.0 범위 권장 | 범위 외: WARN |
| stop_loss_pct | -3.0 ~ -0.3 범위 권장 | 범위 외: WARN |
| BUY_PERCENT | 0.05 ~ 0.25 범위 권장 | 범위 외: WARN |
| 총 투자 비중 | TARGET_BUY_COUNT × BUY_PERCENT ≤ 0.95 | 초과: WARN |

## 판정 기준

- **PASS**: 모든 항목 정상 → 실계좌 실행 가능
- **WARN**: 위험하지 않으나 권장 범위 초과 → 사용자에게 내용 보고 후 계속 진행
- **BLOCK**: 실계좌 위험 → 즉시 중단, 수정 후 재검증 필수

`kis_api.sell()`은 실계좌 즉시 주문이므로, strategy_*.py에 이 호출이 단 하나라도 있으면 반드시 BLOCK.

## 검증 절차

1. 변경된 strategy_*.py 파일을 Read
2. `kis_api` 키워드 grep으로 직접 호출 여부 확인
3. 해당 전략이 strategy_selector.py에서 어떤 파라미터로 인스턴스화되는지 확인
4. harness.py의 `BUY_PERCENT`, `TARGET_BUY_COUNT` 확인
5. 체크리스트 작성 후 종합 판정

## 산출물 형식

`_workspace/03_risk_report.md`:
```markdown
## 리스크 검증 보고서 — {날짜}

### 판정: PASS / WARN / BLOCK

### 체크리스트
- [x] 실계좌 직접 호출 없음
- [x] take_profit_pct: {값}% (권장 0.5~5.0)
- [x] stop_loss_pct: {값}% (권장 -3.0~-0.3)
- [x] BUY_PERCENT: {값} (권장 0.05~0.25)
- [x] 총 투자 비중: {TARGET_BUY_COUNT} × {BUY_PERCENT} = {합계} (≤ 0.95)

### 경고/차단 항목
{목록 또는 '없음'}

### 권고 수정 사항
{내용 또는 '없음'}
```
