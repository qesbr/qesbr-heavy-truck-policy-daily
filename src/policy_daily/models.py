from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Category = Literal["政策", "法规", "标准", "市场", "企业"]


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
    related_sources: list[RelatedSource] = []
    content_evidence: str = ""
    language: str = "unknown"
    authority: int = Field(default=50, ge=0, le=100)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))[:3]


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

