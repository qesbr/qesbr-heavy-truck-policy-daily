from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Category = Literal["政策", "法规", "标准", "市场", "企业"]


class RelevanceLevel(StrEnum):
    DIRECT = "direct"
    PROBABLE = "probable"
    INDIRECT = "indirect"
    NONE = "none"


class EvidenceLevel(StrEnum):
    PRIMARY_LAW = "S"
    OFFICIAL_NOTICE = "A"
    AUTHORITATIVE_ANALYSIS = "B"
    COMPANY = "C"
    MEDIA = "D"
    UNVERIFIED = "E"


class LifecycleStage(StrEnum):
    PRE_NOTICE = "pre_notice"
    CONSULTATION = "consultation"
    DRAFT = "draft"
    ADOPTED = "adopted"
    PUBLISHED = "published"
    AMENDED = "amended"
    EFFECTIVE = "effective"
    DELAYED = "delayed"
    ENFORCEMENT = "enforcement"
    REPEALED = "repealed"
    UNKNOWN = "unknown"


class RelatedSource(BaseModel):
    title: str
    source_name: str
    source_url: HttpUrl


class RawArticle(BaseModel):
    title: str
    source_name: str
    source_type: str
    source_url: HttpUrl
    published_at: datetime
    collected_at: datetime
    content: str = Field(min_length=80)
    region_hint: str = "其他"
    authority: int = Field(default=50, ge=0, le=100)
    language: str = "unknown"
    source_id: str = ""
    document_id: str = ""
    document_type: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.UNVERIFIED
    attachment_urls: list[HttpUrl] = Field(default_factory=list)


class Article(BaseModel):
    id: str
    title_zh: str
    title_original: str = ""
    summary_zh: str = Field(min_length=20, max_length=600)
    source_name: str
    source_type: str
    source_url: HttpUrl
    published_at: datetime
    collected_at: datetime
    region: str
    primary_category: Category
    tags: list[str] = Field(max_length=3)
    importance_score: int = Field(ge=0, le=100)
    is_highlight: bool = False
    content_hash: str
    event_id: str
    related_sources: list[RelatedSource] = Field(default_factory=list)
    content_evidence: str = ""
    language: str = "unknown"
    authority: int = Field(default=50, ge=0, le=100)
    source_id: str = ""
    document_id: str = ""
    document_type: str = ""
    lifecycle_stage: LifecycleStage = LifecycleStage.UNKNOWN
    relevance_level: RelevanceLevel = RelevanceLevel.PROBABLE
    evidence_level: EvidenceLevel = EvidenceLevel.UNVERIFIED
    vehicle_classes: list[str] = Field(default_factory=list)
    powertrain_scope: list[str] = Field(default_factory=list)
    effective_at: datetime | None = None
    evidence_quotes: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))[:3]


class LeadCandidate(BaseModel):
    id: str
    title: str
    source_name: str
    source_url: HttpUrl
    published_at: datetime
    collected_at: datetime
    reason: str
    evidence_level: EvidenceLevel = EvidenceLevel.UNVERIFIED
    status: Literal["pending", "promoted", "rejected"] = "pending"


class PageSnapshot(BaseModel):
    source_id: str
    url: HttpUrl
    captured_at: datetime
    content_hash: str
    normalized_text: str
    previous_hash: str = ""
    changed: bool = True


class Report(BaseModel):
    report_type: Literal["daily", "weekly", "monthly"]
    report_id: str
    title: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    summary: str
    empty: bool
    articles: list[Article]


class SourceStatus(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    first_discovered_at: datetime
    last_success_at: datetime | None = None
    status: Literal["pending", "ok", "error", "disabled"] = "pending"
    message: str = ""
    candidates_found: int = 0
    accepted_count: int = 0
    rejected_date_count: int = 0
    rejected_content_count: int = 0
