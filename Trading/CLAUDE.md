# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

한국투자증권 OpenAPI + `mojito` 기반 ETF 자동매매 하네스.
**당일 시장 상황을 분석해 최적 전략을 자동 선택**하고, 매매 결과를 기록·리포팅한다.

## 실행 방법

```bash
python harness.py        # 하네스 (전략 자동 선택 + 리포팅) — 실 운영용
python trader.py         # 단일 전략 수동 지정 — 테스트용
```

의존성 설치:
```bash
pip install mojito2 requests pandas python-dotenv
```

## 파일 구조

```
harness.py                ← 메인 진입점 (전략 선택 → 매매 → 리포트)
strategy_selector.py      ← 시장 상황 분석 → 최적 전략 자동 선택
trade_logger.py           ← 체결 기록 (trades/YYYYMMDD.json)
reporter.py               ← 일일/주간 리포트 생성 + Slack 전송

kis_api.py                ← 한투 API 전용 (토큰·시세·잔고·주문)
strategy.py               ← Strategy 베이스 클래스 + VolatilityBreakout
strategy_gap.py           ← GapFollow (갭 추종)
strategy_orb.py           ← OpeningRangeBreakout (오전 레인지 돌파)
strategy_dual_momentum.py ← DualMomentum (절대+상대 모멘텀)
strategy_rsi.py           ← RSIOversoldBounce (RSI 과매도 반등)
strategy_bollinger.py     ← BollingerBreakout (볼린저밴드 돌파)
strategy_momentum.py      ← MomentumVolumeSurge (모멘텀+거래량)

trader.py                 ← 단일 전략 수동 실행기 (전략 교체 테스트용)
EtfAlgoTrader4.py         ← 레거시 (참고용)
trades/                   ← 일별 매매 기록 JSON
.env                      ← API 키/시크릿/계좌번호
```

## 아키텍처

### 레이어 구조
```
harness.py
    ├─ strategy_selector.py  (시장분석 → 전략 선택)
    ├─ kis_api.py            (순수 I/O)
    ├─ strategy_*.py         (순수 로직, should_buy/should_sell)
    ├─ trade_logger.py       (체결 기록)
    └─ reporter.py           (Slack 리포트)
```

- `kis_api.py` — 조건 판단 없이 API 호출 결과만 반환
- `strategy_*.py` — API 직접 호출 없음, 가격 데이터를 받아 bool 반환
- `strategy_selector.py` — KODEX 200(069500)을 시장 지표로 사용해 전략 선택

### 전략 선택 로직 (`strategy_selector.py`)
| 조건 | 선택 전략 |
|------|----------|
| 갭업 ≥ 0.5% | GapFollow |
| 전일 레인지 < 1.5% (좁음) | OpeningRangeBreakout |
| 상승추세 + MA5 기울기 ≥ 0.3% | DualMomentum |
| 상승추세 | VolatilityBreakout |
| 하락추세 + MA5 기울기 ≤ -0.3% | RSIOversoldBounce |
| 그 외 | VolatilityBreakout (fallback) |

### 새 전략 추가 방법
1. `strategy_XXX.py` 생성, `Strategy` 상속, `should_buy()` / `should_sell()` 구현
2. `strategy_selector.py` 상단 import 추가 후 선택 로직에 조건 삽입

### 매매 타임라인
| 시간 | 동작 |
|------|------|
| 09:00~09:05 | 기존 보유 종목 `bought` set 등록 |
| 09:05~14:15 | 10초 간격, 장중 익절/손절 → 매수 시도 |
| 14:15~14:20 | 전량 EOD 매도 → finalize → 일일 리포트 Slack 전송 |
| 14:20~ | 프로그램 종료 |

### 매매 기록
- 체결 즉시 `trade_logger.log_buy()` / `log_sell()` 호출
- `trades/YYYYMMDD.json` 에 저장
- `trade_logger.load_history(N)` 으로 최근 N일 요약 조회 가능

## 계좌 및 API

- ISA 계좌만 사용 (`KIS_API_KEY_ISA`, `KIS_ACC_NO_ISA`)
- 토큰은 `token.dat`에 pickle 캐시, `init_token()`이 유효성 검사 후 재발급/로드
- 토큰 발급 **1분 1회** 제한 — 연속 호출 시 `EGW00133` 에러
- Slack 알림 채널: `"stock"`

## 주의사항

- `kis_api.sell()` 은 실계좌 즉시 주문 — 테스트 시 호출 금지
- ORB 전략은 `harness.py` 매수 루프에서 `strategy.update_range()` 를 자동 호출함
- 각 전략의 `_cache`는 당일 OHLCV 메모리 캐시 — 자정 넘어 프로세스 유지 시 수동 초기화 필요

---

## 하네스: ETF 자동매매

**목표:** 시장 분석 → 전략 선택 → 코드 수정 → 리스크 검증을 에이전트 팀으로 자동화

**트리거:** ETF 자동매매 관련 작업(시장 분석, 전략 수정, 하네스 실행 등) 요청 시 `etf-trading` 스킬을 사용하라. 단순 코드 질문은 직접 응답 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-19 | 초기 구성 | 전체 | - |
| 2026-06-19 | 트리거 description 보강 | 스킬 4개 | 취약 쿼리 오탐 방지 (경계 조건 명시) |
| 2026-06-19 | TradeAnalyst 에이전트 추가 | agents/trade-analyst.md, skills/trade-analysis/, etf-trading 오케스트레이터 | 로그 기반 전략 수정 기능 공백 보완 |
| 2026-06-19 | DailyReporter 에이전트 추가 | agents/daily-reporter.md, skills/daily-report/, etf-trading 오케스트레이터 Phase 5, index.html 탭 4·5 추가 | 장 마감 후 매매 일지 자동 기록 기능 추가 |
