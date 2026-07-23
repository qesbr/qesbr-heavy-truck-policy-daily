import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from policy_daily.emailer import deliver, render_email
from policy_daily.models import RawArticle
from policy_daily.processor import DeepSeekProcessor, ProcessorConfig
from policy_daily.reports import build_report
from policy_daily.site_builder import build_site
from policy_daily.main import load_recipients
from policy_daily.collectors.html_list import HtmlListCollector
from policy_daily.collectors.wechat import WechatPublicCollector
from policy_daily.collectors.official import OfficialSiteCollector, extract_meta_date


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 22, 8, 30, tzinfo=TZ)


def raw(title="重型车辆排放标准正式发布"):
    return RawArticle(title=title, source_name="测试政府", source_type="政府", source_url="https://example.com/rule", published_at=NOW, collected_at=NOW, content=("本标准规定重型车辆排放和市场准入要求，适用于相关生产企业，自2027年1月1日起实施。" * 12), region_hint="中国", authority=100)


def raw(title="重型货车排放标准正式发布"):
    return RawArticle(
        title=title,
        source_name="测试政府",
        source_type="政府",
        source_url="https://example.com/rule",
        published_at=NOW,
        collected_at=NOW,
        content=("本标准规定重型货车排放和市场准入要求，适用于相关生产企业，自2027年1月1日起实施。" * 12),
        region_hint="中国",
        authority=100,
        evidence_level="A",
    )


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
    (data / "sources.json").write_text("[]", encoding="utf-8")
    output = tmp_path / "dist"
    build_site(root, data, output, "/qesbr-heavy-truck-policy-daily/")
    assert (output / "index.html").exists()
    html = (output / "index.html").read_text(encoding="utf-8")
    javascript = (output / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'id="archive"' in html
    assert 'data-type="daily"' in html
    assert 'id="search"' not in html
    assert 'id="category"' not in html
    assert "reports.find(report => report.articles?.length)" in javascript
    assert 'qesbr-heavy-truck-policy-daily' in (output / "site-config.js").read_text(encoding="utf-8")
    assert not (output / "data" / "sources.json").exists()


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


def test_official_adapter_verifies_detail_metadata():
    list_html = '<html><body><a href="/news/2026/rule.html">重型车辆排放标准正式发布</a></body></html>'
    detail_html = '''<html><head><title>重型车辆排放标准正式发布</title>
      <meta property="article:published_time" content="2026-07-22T08:00:00+08:00"></head>
      <body><article><p>本标准规定重型车辆排放和市场准入要求，适用于相关生产企业，自2027年1月1日起实施。</p>
      <p>文件明确检测程序、认证范围、实施节点和过渡安排，并公布主管机构及正式生效日期。</p>
      <p>有关要求覆盖车辆生产、检验、登记和监督环节，原文提供完整条款与附件。</p>
      <p>为保障政策平稳落地，主管部门设置了过渡期、信息报送、产品抽查和违规处置要求，并要求企业按照新标准完成技术改造与认证。</p>
      <p>各地有关部门应当加强协同监管，对新生产车辆的电池安全、能耗、排放和充换电兼容性开展检查，及时公开实施情况。</p></article></body></html>'''
    def handler(request):
        return httpx.Response(200, text=detail_html if request.url.path.endswith("rule.html") else list_html)
    source = {"url": "https://example.com/list", "name": "测试政府", "source_type": "政府", "region": "中国", "authority": 100, "url_patterns": ["/news/"], "min_content_chars": 100}
    assert extract_meta_date(BeautifulSoup(detail_html, "html.parser"), TZ) == datetime(2026, 7, 22, 8, 0, tzinfo=TZ)
    result = OfficialSiteCollector(source, httpx.Client(transport=httpx.MockTransport(handler))).collect(NOW - timedelta(hours=24), NOW)
    assert not result.error and len(result.articles) == 1
    assert result.articles[0].title == "重型车辆排放标准正式发布"
    assert result.articles[0].published_at.date().isoformat() == "2026-07-22"
