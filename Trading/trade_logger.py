"""
매매 체결 기록 및 일별 결과 관리.
trades/YYYYMMDD.json 에 저장한다.
"""
import json
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("trades")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _path(date: str = None) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    return LOG_DIR / f"{date or _today()}.json"


def _load(date: str = None) -> dict:
    p = _path(date)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"date": date or _today(), "strategy": None, "trades": [], "summary": {}}


def _save(data: dict, date: str = None) -> None:
    with open(_path(date), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def set_strategy(strategy_name: str) -> None:
    """당일 사용 전략 이름 기록"""
    data = _load()
    data["strategy"] = strategy_name
    _save(data)


def log_buy(code: str, name: str, qty: int, price: int) -> None:
    data = _load()
    data["trades"].append({
        "code":   code,
        "name":   name,
        "action": "buy",
        "qty":    qty,
        "price":  price,
        "time":   datetime.now().strftime("%H:%M:%S"),
    })
    _save(data)


def log_sell(code: str, name: str, qty: int, price: int,
             buy_price: int, reason: str = "eod") -> None:
    """
    reason: 'eod'(장마감 일괄), 'tp'(익절), 'sl'(손절)
    """
    pnl_amt = (price - buy_price) * qty
    pnl_pct = (price - buy_price) / buy_price * 100 if buy_price else 0
    data = _load()
    data["trades"].append({
        "code":      code,
        "name":      name,
        "action":    "sell",
        "qty":       qty,
        "price":     price,
        "buy_price": buy_price,
        "pnl_amt":   pnl_amt,
        "pnl_pct":   round(pnl_pct, 2),
        "reason":    reason,
        "time":      datetime.now().strftime("%H:%M:%S"),
    })
    _save(data)


def finalize(total_cash_start: int, total_cash_end: int) -> dict:
    """장 종료 후 요약 계산 및 저장, 요약 dict 반환"""
    data = _load()
    sells = [t for t in data["trades"] if t["action"] == "sell"]

    total_pnl   = sum(t["pnl_amt"] for t in sells)
    win_trades  = [t for t in sells if t["pnl_amt"] > 0]
    lose_trades = [t for t in sells if t["pnl_amt"] <= 0]
    win_rate    = len(win_trades) / len(sells) * 100 if sells else 0

    summary = {
        "strategy":         data["strategy"],
        "trade_count":      len(sells),
        "win":              len(win_trades),
        "lose":             len(lose_trades),
        "win_rate":         round(win_rate, 1),
        "total_pnl_amt":    total_pnl,
        "total_pnl_pct":    round(total_pnl / total_cash_start * 100, 2) if total_cash_start else 0,
        "cash_start":       total_cash_start,
        "cash_end":         total_cash_end,
        "best_trade":       max(sells, key=lambda t: t["pnl_pct"], default=None),
        "worst_trade":      min(sells, key=lambda t: t["pnl_pct"], default=None),
    }
    data["summary"] = summary
    _save(data)
    return summary


def load_history(days: int = 10) -> list[dict]:
    """최근 N일 요약 리스트 반환 (오늘 포함, 최신순)"""
    results = []
    for p in sorted(LOG_DIR.glob("*.json"), reverse=True)[:days]:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("summary"):
            results.append(d["summary"] | {"date": d["date"]})
    return results
