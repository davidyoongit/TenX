---
name: etf-trading
description: "ETF 자동매매 하네스 오케스트레이터. 시장 분석 → 매매 로그 분석 → 전략 개발 → 리스크 검증 → 매매 일지 작성 파이프라인을 에이전트 팀으로 조율한다. '하네스 실행', '오늘 전략', '전략 분석', '매매 하네스', '자동매매 점검', '전략 바꿔줘', '전략 수정해줘', '다시 분석', '재실행', '업데이트', '하네스 돌려줘', '오늘 매매 준비', '로그 보고 전략 수정', '매매 결과 기반으로 개선', '오늘 매매 일지 써줘', '매매 결과 정리해줘', '장 끝났는데 결과 기록해줘', '일지 업데이트' 등 ETF 자동매매 관련 작업 요청 시 반드시 이 스킬을 사용할 것. 단, 단순 파일 열기·코드 설명·일반 질문은 직접 응답하고 이 스킬을 트리거하지 말 것."
---

## Phase 0: 컨텍스트 확인

`_workspace/` 디렉토리 존재 여부로 실행 모드를 결정한다:

| 상황 | 실행 모드 |
|------|---------|
| `_workspace/` 없음 | 초기 실행 — Phase 1부터 전체 |
| `_workspace/` 있음 + 부분 수정 요청 | 부분 재실행 — 해당 Phase 에이전트만 |
| `_workspace/` 있음 + 새 분석 요청 | 새 실행 — 기존을 `_workspace_prev/`로 이동 후 전체 |

## Phase 1: 시장 분석

**실행 모드:** 단일 에이전트 (MarketAnalyst)

MarketAnalyst를 호출해 당일 시장 지표를 분석하고 전략을 선택한다.

- 에이전트: `market-analyst`
- 스킬: `market-analysis`
- 산출물: `_workspace/01_market_analysis.md`
- 모델: `opus`

## Phase 1-B: 매매 로그 분석 (조건부)


**실행 모드:** 단일 에이전트 (TradeAnalyst) — 로그 기반 전략 수정 요청이 있을 때만 실행

TradeAnalyst를 호출해 오늘(또는 지정 날짜) 체결 로그를 분석하고 전략 수정 권고를 생성한다.

- 에이전트: `trade-analyst`
- 스킬: `trade-analysis`
- 입력: `trades/YYYYMMDD.json`, `_workspace/01_market_analysis.md` (있으면 참조)
- 산출물: `_workspace/04_trade_analysis.md`
- 모델: `opus`

Phase 1과 Phase 1-B는 독립적으로 실행 가능하며, 둘 다 요청되면 병렬 실행한다.

## Phase 2: 전략 개발 (조건부)

**실행 모드:** 단일 에이전트 (StrategyEngineer) — 코드 변경 요청이 있을 때만 실행

StrategyEngineer를 호출해 전략 코드를 작성/수정한다.

- 에이전트: `strategy-engineer`
- 스킬: `strategy-dev`
- 입력: `_workspace/01_market_analysis.md` + `_workspace/04_trade_analysis.md` (있으면) + 사용자 요청
- 산출물: 수정된 `strategy_*.py`, `_workspace/02_strategy_changes.md`
- 모델: `opus`

코드 변경 요청이 없으면 Phase 2를 건너뛰고 Phase 3으로 넘어간다.

## Phase 3: 리스크 검증 (조건부)

**실행 모드:** 단일 에이전트 (RiskGuard) — Phase 2 실행 시 필수, 분석만이면 선택

RiskGuard를 호출해 전략 파라미터와 실계좌 안전을 검증한다.

- 에이전트: `risk-guard`
- 스킬: `risk-check`
- 입력: `_workspace/02_strategy_changes.md` + 실제 코드 파일
- 산출물: `_workspace/03_risk_report.md`
- 모델: `opus`

판정별 후속 처리:
- **BLOCK**: 즉시 사용자에게 차단 내역 보고 후 중단
- **WARN**: 경고 내역 보고 후 사용자 확인 요청
- **PASS**: Phase 4로 진행

## Phase 5: 매매 일지 기록 (조건부)

**실행 모드:** 단일 에이전트 (DailyReporter) — 장 마감 후 매매 결과 기록 요청 시 실행

DailyReporter를 호출해 당일 체결 로그를 분석하고 index.html 5번째 탭을 업데이트한다.

- 에이전트: `daily-reporter`
- 스킬: `daily-report`
- 입력: `trades/YYYYMMDD.json`, `_workspace/01_market_analysis.md` (있으면)
- 산출물: `index.html` 5번째 탭 업데이트, `_workspace/05_daily_report_{날짜}.md`
- 모델: `opus`

트리거 조건: "매매 일지", "결과 기록", "일지 써줘", "오늘 성과 정리", "장 끝났는데" 등 장 마감 후 기록 요청

## Phase 4: 종합 보고

세 에이전트의 산출물을 종합해 사용자에게 보고한다:

1. 오늘의 시장 지표 요약 (`_workspace/01_market_analysis.md` 기반)
2. 선택된 전략 + 이유
3. 코드 변경 내역 (Phase 2 실행 시, `_workspace/02_strategy_changes.md` 기반)
4. 리스크 검증 결과 (Phase 3 실행 시, `_workspace/03_risk_report.md` 기반)
5. 매매 일지 업데이트 결과 (Phase 5 실행 시, `_workspace/05_daily_report_{날짜}.md` 기반)

## 에러 핸들링

| 에러 상황 | 처리 방식 |
|----------|---------|
| MarketAnalyst API 실패 | VolatilityBreakout fallback 권고 명시 후 계속 |
| StrategyEngineer 파일 읽기 실패 | 해당 파일 누락 명시, RiskGuard에 전달 |
| RiskGuard BLOCK 판정 | 즉시 사용자 보고 후 중단 |
| 에이전트 무응답 | 1회 재시도 후 해당 결과 없이 진행, 누락 명시 |
| DailyReporter index.html 미존재 | 에러 명시 + 파일 경로 확인 요청 |

## 테스트 시나리오

**정상 흐름 1 — 분석만:**
- 입력: "오늘 어떤 전략으로 매매해야 해?"
- 실행: Phase 0 → Phase 1 → Phase 4
- 기대 출력: 시장 지표 + 전략 선택 이유

**정상 흐름 2 — 분석 + 코드 수정:**
- 입력: "RSI 전략 손절 -0.8%로 변경해줘"
- 실행: Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4
- 기대 출력: 변경된 파라미터 + PASS/WARN 판정

**에러 흐름 1 — BLOCK:**
- 상황: StrategyEngineer가 전략 코드에 `kis_api.buy()` 추가
- 기대 처리: RiskGuard BLOCK → 즉시 사용자 보고 + 수정 요청

**에러 흐름 2 — API 실패:**
- 상황: MarketAnalyst가 `EGW00133` 에러
- 기대 처리: fallback 권고 기록, Phase 2/3 계속 진행
