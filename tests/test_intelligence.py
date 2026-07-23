from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from policy_daily.collectors.api import ApiCollector
from policy_daily.config import load_sources
from policy_daily.intelligence_store import snapshot_page
from policy_daily.models import Article, EvidenceLevel, LifecycleStage, RelevanceLevel
from policy_daily.screening import calculate_importance, classify_lifecycle, classify_relevance, eligible_for_official_store

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 23, 8, 30, tzinfo=TZ)


def test_source_registry_is_valid_and_unique():
    registry = load_sources(Path(__file__).parents[1])
    assert len(registry.sources) >= 9
    assert len({source.id for source in registry.sources}) == len(registry.sources)
    assert any(source.api_kind == "federal_register" for source in registry.sources)
    assert all(source.channel and source.document_types for source in registry.sources)
    mot = next(source for source in registry.sources if source.id == "mot_policy")
    unece = next(source for source in registry.sources if source.id == "unece_wp29")
    assert mot.url.host == "xxgk.mot.gov.cn"
    assert str(unece.url).endswith("/transport/vehicle-regulations")


def test_layered_relevance_and_lifecycle():
    assert classify_relevance("N3零排放货车新规", "适用于heavy-duty vehicle") == RelevanceLevel.DIRECT
    assert classify_relevance("商用车大功率充电政策", "面向道路货运") == RelevanceLevel.PROBABLE
    assert classify_relevance("电池回收政策", "动力电池产业") == RelevanceLevel.INDIRECT
    assert classify_relevance("Aviation carbon leakage", "EU ETS rules for international flights") == RelevanceLevel.NONE
    assert classify_relevance("Hours of Service exemption", "Federal Motor Carrier Safety Regulations") == RelevanceLevel.PROBABLE
    assert classify_lifecycle("公开征求意见", "请于月底前反馈") == LifecycleStage.CONSULTATION
    assert classify_lifecycle("法规正式发布", "自明年起实施") == LifecycleStage.EFFECTIVE


def test_rule_based_importance_and_store_gate():
    article = Article(
        id="x", title_zh="重卡法规", summary_zh="重型货车法规正式发布，规定车辆准入、排放限值、实施时间和生产企业合规义务。",
        source_name="官方", source_type="政府", source_url="https://example.com/x",
        published_at=NOW, collected_at=NOW, region="中国", primary_category="法规",
        tags=["重型货车"], importance_score=0, content_hash="h", event_id="e",
        authority=100, relevance_level="direct", lifecycle_stage="published", evidence_level="S",
    )
    assert calculate_importance(article) >= 90
    assert eligible_for_official_store(article)
    article.evidence_level = EvidenceLevel.MEDIA
    assert not eligible_for_official_store(article)


def test_snapshot_only_marks_real_changes(tmp_path):
    first = snapshot_page(tmp_path, "source", "https://example.com/page", NOW, "法规正文 第一版")
    second = snapshot_page(tmp_path, "source", "https://example.com/page", NOW + timedelta(hours=1), "法规正文 第一版")
    third = snapshot_page(tmp_path, "source", "https://example.com/page", NOW + timedelta(hours=2), "法规正文 第二版")
    assert first.changed and not second.changed and third.changed
    assert third.previous_hash == first.content_hash


def test_federal_register_api_collector():
    def handler(request):
        if request.url.path.endswith("documents.json"):
            return httpx.Response(200, json={"results": [{
                "document_number": "2026-10001",
                "title": "Heavy-Duty Vehicle Emissions Final Rule",
                "publication_date": "2026-07-23",
                "type": "Rule",
                "html_url": "https://example.com/rule",
                "raw_text_url": "https://example.com/rule.txt",
            }]})
        return httpx.Response(200, text="Heavy-duty vehicle emissions regulation. " * 30)

    source = {
        "id": "fr", "name": "Federal Register", "source_type": "政府",
        "url": "https://www.federalregister.gov/api/v1/documents.json",
        "api_kind": "federal_register", "query": {"terms": ["heavy-duty vehicle"], "agencies": []},
        "region": "美国", "authority": 100, "evidence_level": "S",
    }
    result = ApiCollector(source, httpx.Client(transport=httpx.MockTransport(handler))).collect(
        NOW - timedelta(days=1), NOW
    )
    assert not result.error and len(result.articles) == 1
    assert result.articles[0].document_id == "2026-10001"


def test_federal_register_excludes_case_specific_notices():
    def handler(request):
        if request.url.path.endswith("documents.json"):
            return httpx.Response(200, json={"results": [{
                "document_number": "2026-EXEMPT",
                "title": "Hours of Service: Example Carrier; Application for Exemption",
                "publication_date": "2026-07-23",
                "type": "Notice",
                "html_url": "https://example.com/exemption",
                "raw_text_url": "https://example.com/exemption.txt",
            }]})
        return httpx.Response(200, text="Federal Motor Carrier Safety Regulations. " * 30)
    source = {
        "id": "fr", "name": "Federal Register", "source_type": "政府",
        "url": "https://www.federalregister.gov/api/v1/documents.json",
        "api_kind": "federal_register", "query": {"terms": ["truck"], "agencies": []},
        "region": "美国", "authority": 100, "evidence_level": "S",
        "exclude_patterns": ["application for exemptions?"],
    }
    result = ApiCollector(source, httpx.Client(transport=httpx.MockTransport(handler))).collect(
        NOW - timedelta(days=1), NOW
    )
    assert result.articles == []
