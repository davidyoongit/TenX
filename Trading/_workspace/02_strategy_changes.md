# 전략/하네스 변경 내역 — 2026-06-24

근거: `_workspace/04_trade_analysis.md` (TradeAnalyst)
검증: risk-guard **PASS** (전 항목) — `_workspace/03_risk_report.md`

진단 요약: 2026-06-24 -11,443원(-7.72%) 손실은 당일 진입 실패가 아니라,
06-22 매수한 RISE 200(148020)이 정규장에서 청산되지 않고 이월된 뒤
06-23 -11% 급락 반전 + 오버나이트 갭다운으로 개장 시점에 이미 -7.72% 상태로 시작했기 때문.
SL -1.5%는 장중 정상 작동했으나 갭 손실을 막을 위치에 없었음.
**SL 파라미터(stop_loss_pct -1.5%)는 변경하지 않음 — 이번 손실 원인이 아님.**

---

## 변경 1 — 오버나이트 갭다운 가드 (harness.py, 최우선)

- 신설 상수: `GAP_DOWN_EXIT_PCT = -3.0`
- 위치: init 블록(기존 보유 등록부).
- 동작: 이월 보유 종목 등록 시 `get_asking_price`로 현재가를 가져와 평단 대비 갭 손익(`gap_pnl`) 계산.
  `gap_pnl <= -3.0%` 이거나 전일 이월 플래그 대상이면 개장 직후 `kis_api.sell(order_type="15")`로 즉시 청산,
  `trade_logger.log_sell(reason="gap")` 기록. 청산분은 `bought`에 등록하지 않아 장중 루프 재매도 없음.
- 가드 통과분만 정상 보유 등록(`bought` + `buy_prices=avg_price`).
- 예외 안전: 시세 조회 실패 시 `cur=0` → 맹목 청산 회피(스킵). sell 예외 시 추적용으로만 등록.
- SL(-1.5%, 장중 틱 손절)과 별개의 깊은(완화된) 임계 — 오버나이트 갭 전용 차단막.

## 변경 2 — EOD 미청산 이월 차단 (harness.py `_sell_all` + 플래그 파일)

- `_sell_all`이 10회 재시도 후에도 잔량이 남으면:
  - 명시적 경고 `_notify("🚨 EOD 청산 실패 — 잔량 이월 위험! ...")`
  - `carryover_liquidation.json`에 이월 종목 기록(`_write_carryover_flag`) 후 `return False`.
  - 잔량 0이면 `return True`.
- 익일 개장 시 init 블록이 `_read_carryover_flag`로 읽어 해당 종목을 **무조건 강제 청산**(`forced`), 처리 후 `_clear_carryover_flag`.
- 신규 헬퍼: `_write_carryover_flag` / `_read_carryover_flag` / `_clear_carryover_flag`.
- 근거: 06-22 RISE 200 "eod" 기록이 17:10~17:15 장외 시각 + 10회 중복 = 미청산/로깅 아티팩트. 이월 자체를 차단하는 것이 갭다운 손실의 근본 대응.

## 변경 3 — 반전일 VolatilityBreakout 선택 억제 (strategy_selector.py)

- `select()` 4번 분기 가드 추가:
  - 기존: `elif trend == "up":` → VolatilityBreakout
  - 변경: `elif trend == "up" and slope >= 0 and rng < 5.0:` → VolatilityBreakout
  - 신규 4b: 상승추세이나 모멘텀 불일치(기울기 음수 또는 전일 레인지 ≥ 5%, 즉 급락 반전일)이면
    `RSIOversoldBounce(TP=1.5%, SL=-1.5%)` 보수 폴백.
- 근거: 06-24는 MA5 기울기 -0.93%, 전일 레인지 12.57%인 급락 반전일임에도 "up" 판정으로 VB 선택.
  당일 진입 0건이라 직접 피해는 없었으나 신호 발생 시 추격매수 위험 → selector가 추세-모멘텀 불일치를 차단.

---

## 추가 보강 (risk-guard 모니터링 권고 반영)

- init 윈도우 확장: `T_OPEN < now < T_START`(09:00~09:05) → `T_OPEN < now < T_SELL_START`(09:00~14:15).
  - 사유: 09:05 이후 늦게 기동되면 init 블록이 스킵되어 갭다운/이월 강제청산이 모두 누락되던 문제.
  - `init_flag`로 당일 1회만 실행되므로 정상 기동 동작은 불변, 늦은 기동 시에만 가드가 살아남.

## 미반영 (의도적)

- `stop_loss_pct -1.5%` 수치 변경 — 이번 손실 원인 아님(장중 정상 작동). 변경 시 무관/역효과(손절 지연).

## 검증/주의

- `ast.parse` 구문 검사 통과(harness.py, strategy_selector.py).
- 총 투자 비중 5 × 0.19 = 0.95 (상한 경계). 파라미터 상향 시 초과 주의.
- 정시(09:00 전후) 기동을 기본 운영 전제로 유지 권장.
