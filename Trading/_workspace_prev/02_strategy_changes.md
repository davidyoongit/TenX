# 전략 변경 내역 — 2026-06-22

## strategy_dual_momentum.py

| 파라미터 | 이전 | 이후 | 사유 |
|----------|------|------|------|
| abs_pct | 1.0% | 0.5% | 오늘 매수 1건 — 진입 조건 과엄격 |
| take_profit_pct | 2.5% | 1.5% | EOD까지 TP 미달 — 수익 실현 문턱 낮춤 |

## harness.py

### BUG-1 수정: _sell_all 중복 매도 방지
- pending set 도입: 주문 전송한 코드를 추적
- 30초 대기 후 체결 확인 전까지 동일 코드 재주문 차단
- pending.clear() 후 미체결 잔량만 재시도

### BUG-2 수정: 전일 보유 종목 buy_price 설정
- 09:00~09:05 보유 등록 시 `buy_prices[code] = h["avg_price"]` 추가
- 이전: buy_prices 미설정 → log_sell fallback으로 pnl=0% 오기록
- 이후: 실제 평균 매수가 기준 손익 계산
