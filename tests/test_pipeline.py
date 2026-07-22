import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from policy_daily.emailer import deliver, render_email
from policy_daily.models import RawArticle
from policy_daily.processor import DeepSeekProcessor, ProcessorConfig
from policy_daily.reports import build_report
from policy_daily.site_builder import build_site
from policy_daily.main import load_recipients
from policy_daily.collectors.html_list import HtmlListCollector
from policy_daily.collectors.wechat import WechatPublicCollector


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 22, 8, 30, tzinfo=TZ)


def raw(title="重型车辆排放标准正式发布"):
    return RawArticle(title=title, source_name="测试政府", source_type="政府", source_url="https://example.com/rule", published_at=NOW, collected_at=NOW, content=("本标准规定重型车辆排放和市场准入要求，适用于相关生产企业，自2027年1月1日起实施。" * 12), region_hint="中国", authority=100)


def processor(transport=None):
    client = httpx.Client(transport=transport) if transport else httpx.Client()
    cfg = ProcessorConfig("https://api.deepseek.com/chat/completions", "deepseek-chat", 1, 75, ["排放", "市场准入"], {})
    return DeepSeekProcessor(cfg, client)


def test_mock_processor_and_daily_report(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    item = processor().process(raw())
    assert item and 150 <= len(item.summary_zh) <= 300
    report = build_report("daily", NOW - timedelta(hours=24), NOW, [item])
    assert not report.empty and report.articles[0].is_highlight


def test_remote_invalid_json_retries(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
    proc = processor(httpx.MockTransport(handler))
    try:
        proc.process(raw())
        assert False, "expected failure"
    except RuntimeError:
        assert calls["n"] == 2


def test_empty_report_never_sends(tmp_path):
    report = build_report("daily", NOW - timedelta(hours=24), NOW, [])
    status = deliver(report, ["nobody@example.com"], "", "", "https://example.com", tmp_path / "preview.html", True)
    assert "无有效内容" in status


def test_weekly_email_is_rejected(tmp_path):
    item = processor().process(raw())
    report = build_report("weekly", NOW - timedelta(days=7), NOW, [item])
    assert "仅日报" in deliver(report, [], "", "", "https://example.com", tmp_path / "preview.html", True)


def test_site_build_supports_subpath(tmp_path):
    root = Path(__file__).parents[1]
    data = tmp_path / "data"
    data.mkdir()
    (data / "manifest.json").write_text(json.dumps({"reports": []}), encoding="utf-8")
    output = tmp_path / "dist"
    build_site(root, data, output, "/qesbr-heavy-truck-policy-daily/")
    assert (output / "index.html").exists()
    assert 'qesbr-heavy-truck-policy-daily' in (output / "site-config.js").read_text(encoding="utf-8")


def test_recipient_config_is_private_and_validated(tmp_path):
    config = tmp_path / "recipients.yaml"
    config.write_text("recipients:\n  - valid@example.com\n  - not-an-address\n", encoding="utf-8")
    assert load_recipients(config) == ["valid@example.com"]


def test_collector_failure_is_isolated():
    def handler(request):
        return httpx.Response(503, text="temporary failure")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = {"url": "https://example.com/list", "name": "故障来源", "source_type": "政府"}
    result = HtmlListCollector(source, client).collect(NOW - timedelta(hours=24), NOW)
    assert result.articles == [] and "503" in result.error


def test_wechat_without_public_entry_is_safe():
    result = WechatPublicCollector({"name": "测试公众号"}, httpx.Client()).collect(NOW - timedelta(hours=24), NOW)
    assert result.articles == [] and "公开入口" in result.error
