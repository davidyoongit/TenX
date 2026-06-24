---
name: strategy-dev
description: "ETF 자동매매 전략 코드를 작성·수정·통합하는 스킬. Strategy 베이스 클래스 상속, should_buy/should_sell 구현, strategy_selector.py 연동까지 담당한다. '전략 추가', '전략 수정', '새 전략 만들어줘', 'should_buy 고쳐줘', '파라미터 바꿔줘', '손절 조건 변경', '전략 코드 작성', '다시 실행할 전략 바꿔줘' 등 실제 코드 변경 요청 시 반드시 이 스킬을 사용할 것. 단, 코드 변경 없이 분석·설명·전략 선택만 요청하는 경우는 이 스킬을 트리거하지 말 것 — 코드를 수정하는 동사(바꿔줘, 만들어줘, 고쳐줘, 추가해줘)가 있어야 트리거한다."
---

## 전략 구조

모든 전략은 `strategy.py`의 `Strategy` 베이스 클래스를 상속한다:

```python
from strategy import Strategy

class MyStrategy(Strategy):
    def should_buy(self, code: str, current_price: float, ask_price: float) -> bool:
        ...

    def should_sell(self, code: str, holding_info: dict) -> bool:
        ...

    def describe(self) -> str:
        return f"MyStrategy(param={self.param})"
```

`holding_info` 구조 (`kis_api.get_holdings()` 반환값):
```python
{
    "name": str,           # 종목명
    "qty": int,            # 보유 수량
    "avg_price": float,    # 평균 단가
    "evlu_pfls_rt": float  # 평가손익률 (%)
}
```

## 새 전략 추가 절차

1. `strategy_{name}.py` 생성 — Strategy 상속, 3개 메서드 구현
2. `strategy_selector.py` 수정:
   - 상단에 import 추가
   - `select()` 함수의 적절한 우선순위 위치에 조건 삽입
3. `_workspace/02_strategy_changes.md`에 변경 내역 기록

## 기존 전략 파라미터 수정 시

- 해당 `strategy_*.py` 또는 `strategy_selector.py`의 인스턴스 생성 부분만 수정
- `strategy_selector.py` 내 파라미터 변경이면 해당 전략 클래스 파일은 수정 불필요

## 금지 사항

- 전략 코드(strategy_*.py) 내에 `kis_api` import 또는 호출 금지 — 순수 로직만
- `_cache` 구조 변경 시 "자정 넘어 프로세스 유지 시 초기화 필요" 주석 추가

## ORB 전략 특이사항

`OpeningRangeBreakout`은 `update_range(code, current_price)`를 매 루프에서 호출해야 한다.
harness.py가 이미 처리하므로 전략 코드 내부에서 별도 호출 불필요.

## 산출물

`_workspace/02_strategy_changes.md`:
```markdown
## 전략 변경 내역 — {날짜}

### 변경 대상
- 파일: {파일명}
- 변경 유형: 신규 생성 / 파라미터 수정 / 로직 수정

### 변경 내용
{구체적 변경 사항}

### strategy_selector.py 수정 여부
{수정 있음: 위치와 조건 설명 / 수정 없음}
```
