from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from policy_daily.deduplicator import deduplicate
from policy_daily.main import period
from policy_daily.models import Article
from policy_daily.utils import RedactingFilter, normalize_url, within_window


TZ = ZoneInfo("Asia/Shanghai")


def article(**changes):
    values = dict(
        id="a", title_zh="重型车辆排放标准正式发布", summary_zh="这是一个足够长的测试摘要，用于验证信息模型、排序和多来源合并逻辑。",
        source_name="政府", source_type="政府", source_url="https://example.com/a", published_at=datetime(2026, 7, 22, tzinfo=TZ),
        collected_at=datetime(2026, 7, 22, tzinfo=TZ), region="中国", primary_category="标准", tags=["排放"],
        importance_score=85, is_highlight=True, content_hash="hash", event_id="event", content_evidence="正文证据" * 100, authority=100,
    )
    values.update(changes)
    return Article(**values)


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url("HTTPS://Example.COM/a/?utm_source=x&b=2#top") == "https://example.com/a?b=2"


def test_window_is_inclusive():
    end = datetime(2026, 7, 22, 8, 30, tzinfo=TZ)
    assert within_window(end - timedelta(hours=24), end - timedelta(hours=24), end)
    assert not within_window(end - timedelta(hours=25), end - timedelta(hours=24), end)


def test_periods():
    now = datetime(2026, 7, 22, 8, 30, tzinfo=TZ)
    start, end = period("daily", now, None, None)
    assert end - start == timedelta(hours=24)
    start, end = period("monthly", now, None, None)
    assert (start.date().isoformat(), end.date().isoformat()) == ("2026-06-01", "2026-06-30")


def test_authoritative_source_becomes_primary():
    low = article(id="low", source_name="媒体", source_url="https://media.example/a", authority=50)
    high = article(id="high", source_name="政府", source_url="https://gov.example/a", authority=100)
    merged = deduplicate([low, high])
    assert len(merged) == 1
    assert merged[0].source_name == "政府"
    assert merged[0].related_sources[0].source_name == "媒体"


def test_tags_are_unique_and_limited():
    item = article(tags=["排放", "排放", "充电"])
    assert item.tags == ["排放", "充电"]


def test_redaction_filter():
    import logging
    record = logging.LogRecord("x", logging.INFO, "", 1, "token=secret user@example.com", (), None)
    RedactingFilter().filter(record)
    assert "secret" not in record.msg and "user@example.com" not in record.msg

