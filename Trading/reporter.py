"""
일일 매매 결과 리포트 생성 및 Slack 전송.
"""
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import trade_logger

load_dotenv()
SLACK_TOKEN = os.environ.get("SLACK_TOKEN", "")
SLACK_CHANNEL = "stock"


def _slack(text: str) -> None:
    if not SLACK_TOKEN:
        return
    try:
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            data={"channel": SLACK_CHANNEL, "text": text},
            timeout=5,
        )
    except Exception as e:
        print(f"[reporter] slack error: {e}")


def _bar(pct: float, width: int = 10) -> str:
    """텍스트 진행바 생성"""
    filled = round(abs(pct) / 5 * width)  # 5% = 전체
    filled = min(filled, width)
    char   = "█" if pct >= 0 else "░"
    return char * filled + "·" * (width - filled)


# ──────────────────────────────────────────────
# 당일 리포트
# ──────────────────────────────────────────────

def send_daily_report(summary: dict) -> None:
    """finalize() 결과 summary를 Slack으로 전송"""
    date     = datetime.now().strftime("%Y/%m/%d")
    strategy = summary.get("strategy", "-")
    trades   = summary.get("trade_count", 0)
    wins     = summary.get("win", 0)
    loses    = summary.get("lose", 0)
    win_rate = summary.get("win_rate", 0)
    pnl_amt  = summary.get("total_pnl_amt", 0)
    pnl_pct  = summary.get("total_pnl_pct", 0)
    cash_s   = summary.get("cash_start", 0)
    cash_e   = summary.get("cash_end", 0)
    best     = summary.get("best_trade")
    worst    = summary.get("worst_trade")

    sign     = "+" if pnl_pct >= 0 else ""
    emoji    = "[수익]" if pnl_pct >= 0 else "[손실]"

    lines = [
        f"==========================",
        f"{emoji} 일일 매매 결과 — {date}",
        f"==========================",
        f"전략         : {strategy}",
        f"총 매매      : {trades}건  (승 {wins} / 패 {loses})",
        f"승률         : {win_rate:.1f}%",
        f"수익         : {sign}{pnl_amt:,.0f}원  ({sign}{pnl_pct:.2f}%)",
        f"             {_bar(pnl_pct)}",
        f"예수금 시작  : {cash_s:,.0f}원",
        f"예수금 종료  : {cash_e:,.0f}원",
    ]

    if best:
        lines.append(f"최고 거래     : {best['name']}({best['code']}) "
                     f"+{best['pnl_pct']:.2f}% / +{best['pnl_amt']:,.0f}원")
    if worst:
        lines.append(f"최악 거래     : {worst['name']}({worst['code']}) "
                     f"{worst['pnl_pct']:.2f}% / {worst['pnl_amt']:,.0f}원")

    lines.append("==========================")

    msg = "\n".join(lines)
    print(msg.encode("utf-8", errors="replace").decode("utf-8"))
    _slack(msg)


# ──────────────────────────────────────────────
# 주간 누적 리포트 (선택)
# ──────────────────────────────────────────────

def send_weekly_summary() -> None:
    history = trade_logger.load_history(5)
    if not history:
        _slack("📊 최근 5일 매매 기록 없음")
        return

    total_pnl = sum(h.get("total_pnl_amt", 0) for h in history)
    total_pct = sum(h.get("total_pnl_pct", 0) for h in history)
    wins      = sum(h.get("win", 0) for h in history)
    trades    = sum(h.get("trade_count", 0) for h in history)
    win_rate  = wins / trades * 100 if trades else 0

    strat_count: dict[str, int] = {}
    for h in history:
        s = h.get("strategy", "-")
        strat_count[s] = strat_count.get(s, 0) + 1

    lines = [
        "==========================",
        "[주간] 매매 요약 (최근 5일)",
        "==========================",
        f"누적 수익    : {total_pnl:+,.0f}원  ({total_pct:+.2f}%)",
        f"총 매매      : {trades}건  승률 {win_rate:.1f}%",
        "사용 전략    :",
    ]
    for s, cnt in sorted(strat_count.items(), key=lambda x: -x[1]):
        lines.append(f"  · {s}: {cnt}일")

    lines.append("==========================")
    msg = "\n".join(lines)
    print(msg.encode("utf-8", errors="replace").decode("utf-8"))
    _slack(msg)
