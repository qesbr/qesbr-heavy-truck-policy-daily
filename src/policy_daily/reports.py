from __future__ import annotations

from datetime import datetime

from policy_daily.deduplicator import deduplicate
from policy_daily.models import Article, Report


def build_report(report_type: str, start: datetime, end: datetime, articles: list[Article]) -> Report:
    unique = deduplicate([a for a in articles if start <= a.published_at <= end])
    labels = {"daily": "日报", "weekly": "周报", "monthly": "月报"}
    report_id = f"{report_type}-{end.date().isoformat()}"
    empty = not unique
    summary = "暂无重要更新。" if empty else f"本期共收录{len(unique)}条经正文与发布时间核验的信息，其中今日重点{sum(a.is_highlight for a in unique)}条。"
    return Report(
        report_type=report_type, report_id=report_id, title=f"政策法规{labels[report_type]} · {end.date().isoformat()}",
        period_start=start, period_end=end, generated_at=datetime.now(end.tzinfo), summary=summary, empty=empty, articles=unique,
    )

