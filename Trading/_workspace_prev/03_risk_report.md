# 리스크 검증 리포트 — 2026-06-22

## 판정: PASS (WARN 1건)

## 검증 항목

| 항목 | 값 | 판정 | 비고 |
|------|----|------|------|
| 전략 내 kis_api 직접 호출 | 없음 | PASS | strategy_dual_momentum.py 확인 |
| 손절 조건 존재 | stop_loss_pct=-1.5% | PASS | should_sell() 구현 |
| 익절 조건 존재 | take_profit_pct=1.5% | PASS | |
| TP vs SL 비율 | TP=1.5%, SL=1.5% (1:1) | WARN | TP=|SL| — 슬리피지 고려 시 기댓값 중립 |
| 종목별 투자 비중 | 19% (BUY_PERCENT=0.19) | PASS | 5종목 최대 95% |
| abs_pct | 0.5% (완화) | PASS | 진입 빈도 증가 — 허용 범위 |
| _sell_all 중복 방지 | pending set 추가 | PASS | |
| 전일 보유 buy_price | avg_price 사용 | PASS | |

## WARN 상세

**TP=|SL| (1:1 비율)**
- take_profit_pct=1.5%, stop_loss_pct=-1.5%로 동일 절댓값
- 슬리피지·거래세(0.23%) 고려 시 기댓값이 음수로 전환될 수 있음
- 권고: TP를 1.8~2.0%로 상향하거나 SL을 -1.0%로 완화해 비대칭 구조 권장

## 결론
코드 수정 사항은 실계좌 적용 가능. WARN 사항(TP/SL 비율)은 다음 거래일
성과 확인 후 재조정 권고.
