## 리스크 검증 보고서 — 2026-06-24

### 판정: PASS

### 체크리스트
- [x] 실계좌 직접 호출(전략 파일): strategy_selector.py / strategy_rsi.py 등 strategy_*.py에 신규 kis_api 매매 호출 없음 (selector의 get_ohlcv는 기존 분석용, 허용 아키텍처)
- [x] take_profit_pct: 1.5~2.5% (권장 0.5~5.0) — 변경분(4b RSI 1.5%) 정상
- [x] stop_loss_pct: -1.5% (권장 -3.0~-0.3) — 기존 SL 미변경 확인
- [x] BUY_PERCENT: 0.19 (권장 0.05~0.25)
- [x] 총 투자 비중: TARGET_BUY_COUNT 5 × BUY_PERCENT 0.19 = 0.95 (≤ 0.95, 경계 충족)

### 중점 검증 결과
1. **SL 파라미터 불변**: strategy_selector.py의 모든 분기 stop_loss_pct가 -1.5(하락추세 분기만 -1.0, 기존값) 유지. 4b 신규 RSIOversoldBounce도 -1.5로 기존 동일. 변경 금지 준수.
2. **GAP_DOWN_EXIT_PCT(-3.0) 합리성**: 장중 SL(-1.5%)보다 깊은 별도 가드로 적정. 오버나이트 갭다운은 장중 틱 SL이 동작할 수 없는 구간이므로, 개장 전 누적 손실을 -3.0%에서 일괄 차단하는 것은 보수적·합리적. 임계가 SL보다 완화(깊음)된 점도 의도대로(빈번한 개장가 휩쓸림 방지).
3. **갭다운 청산 실주문 안전성**:
   - 시간 윈도우: `T_OPEN(09:00) < now < T_START(09:05)` + `init_flag` 1회 가드로 단일 실행 보장. 09:05 이후 재진입 없음.
   - 중복 주문 방지: init 블록 1회성 + IOC 최유리(order_type="15", kis_api.sell 기본값과 동일하며 유효)로 즉시 체결/취소. 청산분은 bought에 등록하지 않아 이후 루프 재매도 없음.
   - 예외 처리: get_asking_price 실패 시 cur=0 → 청산 스킵 후 정상 보유 등록(맹목 청산 회피). sell 예외 시 bought 등록해 장중 추적 — 합리적 폴백.
4. **_sell_all 이월 로직**: pending set으로 체결 전 재주문 방지, 10회 재시도 후 잔량은 carryover_liquidation.json 기록 + _notify 경고 + return False. 익일 개장 직후 forced 청산으로 회수. 잔량 방치 위험 완화됨.
5. **4b 폴백 RSIOversoldBounce(SL -1.5)**: 상승추세이나 기울기 음수/레인지 과대(반전 리스크) 시 VB 추격매수를 억제하고 보수 반등 전략으로 전환 — 갭다운 손실 대응 취지에 부합. TP 1.5% / SL -1.5%로 권장 범위 내.

### 경고/차단 항목
없음

### 권고 사항(비차단, 모니터링용)
- 총 투자 비중이 정확히 0.95로 상한 경계에 위치. 수수료·슬리피지 고려 시 미체결 여지가 작으므로 추후 BUY_PERCENT 또는 TARGET_BUY_COUNT 상향 시 0.95 초과 주의.
- 갭다운 청산은 09:00~09:05 단일 윈도우 의존. 프로세스가 09:05 이후 기동되면 init 블록을 건너뛰어 갭다운 가드가 미작동(이월 forced 청산도 미실행). 정시 기동 운영 전제 유지 권고.
