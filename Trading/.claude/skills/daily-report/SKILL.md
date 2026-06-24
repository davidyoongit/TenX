---
name: daily-report
description: "장 마감 후 당일 trades/YYYYMMDD.json을 분석해 성과·반성·개선점을 index.html 5번째 탭(매매 일지)에 날짜별 카드로 기록하는 스킬. '오늘 매매 일지 써줘', '매매 결과 정리해줘', '일지 업데이트', '오늘 성과 기록', '반성 써줘', '일별 리포트 작성', '매매 일지 추가', '오늘 개선점 정리', '장 끝났는데 결과 정리', '매매 결과 index.html에 써줘' 등 매매 결과 기록·정리·일지 작성 요청 시 반드시 이 스킬을 사용할 것. 단, 전략 코드 수정(strategy-dev)이나 리스크 검증(risk-check)은 이 스킬 범위가 아니다."
---

## 목적

하루 매매가 끝나면 체결 로그를 읽어 성과를 수치로 정리하고, 실패·성공 원인을 분석해 다음 거래에 반영 가능한 개선점을 도출한다. 결과는 `index.html` 5번째 탭에 날짜별 카드로 누적한다.

## 실행 절차

### 1. 파일 읽기

```
Read: trades/{날짜}.json
Read (선택): _workspace/01_market_analysis.md
```

날짜가 지정되지 않으면 오늘 날짜(YYYYMMDD)를 사용한다.

### 2. 핵심 지표 계산

`summary` 필드가 있으면 그대로 사용. 없으면 `trades` 배열에서 직접 계산:

```
sell_trades = [t for t in trades if t.action == "sell"]
win = count(t.pnl_amt > 0)
lose = count(t.pnl_amt <= 0)
win_rate = win / (win + lose) * 100
total_pnl_amt = sum(t.pnl_amt)
total_pnl_pct = total_pnl_amt / cash_start * 100  # summary 없으면 생략
```

### 3. 종목별 집계

동일 종목의 여러 거래가 있으면 합산:
```
by_code[code] = {name, total_pnl_amt: sum, count: n, reasons: [tp/sl/eod]}
```

### 4. 4차원 분석 → 인사이트 도출

| 차원 | 체크 | 인사이트 방향 |
|------|------|------------|
| 매도 이유 | sl > 40% | stop_loss_pct 완화 권고 |
| 매도 이유 | tp = 0 | take_profit_pct 하향 권고 |
| 종목 집중 | 특정 code에 sl 2건+ | 해당 종목 제외 또는 조건 강화 |
| 전략 적합 | 전략 vs 시장 상황 | 전략 선택 기준 조정 권고 |
| 이상 패턴 | 중복 거래·미매도 잔량 | 버그 의심, 로그 확인 권고 |

### 5. index.html 5번째 탭 업데이트

`index.html` 파일을 Read한 뒤, `id="journal-entries"` div 내부에 카드를 삽입(Edit)한다.

**이미 해당 날짜 카드 존재 시:** 기존 카드 전체를 새 내용으로 교체  
**새 날짜:** `id="journal-entries"` 바로 아래에 prepend

카드 스타일은 index.html에 정의된 `.journal-*` CSS 클래스를 사용한다.

### 6. _workspace 저장

`_workspace/05_daily_report_{날짜}.md`에 전체 분석 원본을 저장한다.

## 출력 형식 (index.html 카드)

```html
<div class="journal-card" id="journal-20260619">
  <div class="journal-header">
    <div class="journal-date">2026년 06월 19일</div>
    <div class="journal-strategy"><i class="fas fa-chess-knight"></i> GapFollow</div>
    <div class="journal-pnl pos">+137,680원 (+0.76%)</div>
  </div>
  
  <div class="journal-stats">
    <table class="journal-table">
      <thead><tr><th>종목</th><th>매도사유</th><th>손익(원)</th><th>손익(%)</th></tr></thead>
      <tbody>
        <tr class="win-row"><td>KODEX 코스닥150레버리지</td><td><span class="reason-tp">익절</span></td><td>+30,240</td><td>+3.67%</td></tr>
        ...
      </tbody>
    </table>
  </div>

  <div class="journal-section">
    <div class="journal-section-title">📊 성과</div>
    <div class="journal-section-body">
      거래 8건 | 승률 75% | 총 손익 +137,680원 (+0.76%)
      베스트: KODEX 코스닥150레버리지 +3.67% (익절)
      워스트: KODEX 200 -0.35% (손절)
    </div>
  </div>

  <div class="journal-section">
    <div class="journal-section-title">🔍 반성</div>
    <div class="journal-section-body">...</div>
  </div>

  <div class="journal-section">
    <div class="journal-section-title">✅ 개선점</div>
    <div class="journal-section-body">...</div>
  </div>
</div>
```

## 손익 표기 규칙

- 양수: `class="pos"`, 앞에 `+` 붙임
- 음수: `class="neg"`, 그대로 표기 (pnl_amt가 이미 음수)
- 숫자 포맷: 1,000단위 콤마

## 이전 실행 재활용

`_workspace/05_daily_report_{날짜}.md`가 존재하면 "이전 분석 결과 있음"을 확인하고 재사용 여부를 판단한다. 사용자가 "다시 분석"을 요청하면 새로 계산한다.
