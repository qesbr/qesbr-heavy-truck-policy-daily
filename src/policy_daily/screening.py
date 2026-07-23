from __future__ import annotations

from policy_daily.models import Article, EvidenceLevel, LifecycleStage, RelevanceLevel

DIRECT_TERMS = {
    "重型货车", "重卡", "电动重卡", "纯电重卡", "N2", "N3",
    "heavy-duty", "heavy duty", "commercial truck", "electric truck", "e-truck",
}
PROBABLE_TERMS = {
    "商用车", "道路货运", "commercial vehicle", "road freight", "megawatt charging", "大功率充电",
    "motor carrier", "commercial driver's license", "electronic logging device", "hours of service",
    "qualification of drivers", "49 cfr part 575", "truck", "lorry", "tractor-trailer",
    "commercial fleet", "electric bus",
}
EXCLUDED_SECTORS = {"aviation", "aircraft", "airworthiness", "helicopter", "maritime", "shipping", "railway"}
ROAD_TERMS = DIRECT_TERMS | PROBABLE_TERMS | {"road vehicle", "motor vehicle", "truck", "bus"}
LIFECYCLE_RULES = [
    (LifecycleStage.CONSULTATION, ("征求意见", "consultation", "request for comments")),
    (LifecycleStage.DRAFT, ("草案", "draft", "proposal", "proposed rule")),
    (LifecycleStage.AMENDED, ("修订", "amendment", "supplement", "corrigendum")),
    (LifecycleStage.DELAYED, ("延期", "delay", "postpone")),
    (LifecycleStage.REPEALED, ("废止", "repeal", "withdraw")),
    (LifecycleStage.EFFECTIVE, ("生效", "effective", "实施")),
    (LifecycleStage.ENFORCEMENT, ("执法", "enforcement", "penalty")),
    (LifecycleStage.PUBLISHED, ("发布", "公布", "final rule", "regulation")),
]


def classify_relevance(title: str, content: str) -> RelevanceLevel:
    text = f"{title} {content[:5000]}".lower()
    if any(term in text for term in EXCLUDED_SECTORS) and not any(term.lower() in text for term in ROAD_TERMS):
        return RelevanceLevel.NONE
    if any(term.lower() in text for term in DIRECT_TERMS):
        return RelevanceLevel.DIRECT
    if any(term.lower() in text for term in PROBABLE_TERMS):
        return RelevanceLevel.PROBABLE
    if any(term in text for term in ("动力电池", "battery", "充电", "charging", "碳排放", "carbon")):
        return RelevanceLevel.INDIRECT
    return RelevanceLevel.NONE


def classify_lifecycle(title: str, content: str) -> LifecycleStage:
    text = f"{title} {content[:3000]}".lower()
    return next((stage for stage, terms in LIFECYCLE_RULES if any(term.lower() in text for term in terms)), LifecycleStage.UNKNOWN)


def calculate_importance(article: Article) -> int:
    relevance = {RelevanceLevel.DIRECT: 25, RelevanceLevel.PROBABLE: 18, RelevanceLevel.INDIRECT: 8, RelevanceLevel.NONE: 0}[article.relevance_level]
    evidence = {EvidenceLevel.PRIMARY_LAW: 20, EvidenceLevel.OFFICIAL_NOTICE: 18, EvidenceLevel.AUTHORITATIVE_ANALYSIS: 12, EvidenceLevel.COMPANY: 7, EvidenceLevel.MEDIA: 3, EvidenceLevel.UNVERIFIED: 0}[article.evidence_level]
    legal = 20 if article.lifecycle_stage in {LifecycleStage.ADOPTED, LifecycleStage.PUBLISHED, LifecycleStage.AMENDED, LifecycleStage.EFFECTIVE, LifecycleStage.REPEALED} else 13 if article.lifecycle_stage in {LifecycleStage.CONSULTATION, LifecycleStage.DRAFT} else 5
    return min(100, relevance + evidence + legal + round(article.authority * 0.2) + (10 if article.effective_at else 5) + 5)


def eligible_for_official_store(article: Article) -> bool:
    return article.relevance_level in {RelevanceLevel.DIRECT, RelevanceLevel.PROBABLE} and article.evidence_level in {
        EvidenceLevel.PRIMARY_LAW, EvidenceLevel.OFFICIAL_NOTICE, EvidenceLevel.AUTHORITATIVE_ANALYSIS,
    }


def eligible_for_publication(article: Article) -> bool:
    """Publish relevant industry reporting while retaining its evidence label."""
    return article.relevance_level in {
        RelevanceLevel.DIRECT,
        RelevanceLevel.PROBABLE,
    } and article.evidence_level != EvidenceLevel.UNVERIFIED
