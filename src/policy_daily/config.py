from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator


class RequestConfig(BaseModel):
    timeout_seconds: int = 20
    retries: int = 2
    rate_limit_seconds: float = 0.5
    max_candidates_per_source: int = 100
    user_agent: str


class DeepSeekConfig(BaseModel):
    endpoint: str
    model: str = "deepseek-chat"
    retries: int = 2
    mock_without_key: bool = True


class SiteConfig(BaseModel):
    title: str
    base_path: str


class EmailConfig(BaseModel):
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    sender_name: str = "政策法规日报"


class Settings(BaseModel):
    timezone: str = "Asia/Shanghai"
    window_hours: int = Field(default=24, gt=0)
    highlight_threshold: int = Field(default=75, ge=0, le=100)
    request: RequestConfig
    deepseek: DeepSeekConfig
    site: SiteConfig
    email: EmailConfig


class SourceDefinition(BaseModel):
    id: str
    name: str
    adapter: Literal["official_site", "html_list", "rss", "api", "sitemap", "page_watch"]
    url: HttpUrl
    source_type: str
    authority: int = Field(ge=0, le=100)
    evidence_level: Literal["S", "A", "B", "C", "D", "E"]
    region: str
    enabled: bool = True
    channel: str
    document_types: list[str] = Field(default_factory=list)
    url_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    link_selector: str = "a[href]"
    content_selector: str = "article, main, .article, .content, .TRS_Editor"
    date_selector: str = ""
    api_kind: str = ""
    query: dict[str, Any] = Field(default_factory=dict)
    min_content_chars: int = 200
    max_candidates: int = 100
    fallback_urls: list[HttpUrl] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_api_kind(self) -> "SourceDefinition":
        if self.adapter == "api" and not self.api_kind:
            raise ValueError("API来源必须指定 api_kind")
        return self


class SourceRegistry(BaseModel):
    sources: list[SourceDefinition]

    @model_validator(mode="after")
    def unique_ids(self) -> "SourceRegistry":
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("来源ID不能重复")
        return self


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(root: Path) -> Settings:
    return Settings.model_validate(read_yaml(root / "config" / "settings.yaml"))


def load_sources(root: Path) -> SourceRegistry:
    return SourceRegistry.model_validate(read_yaml(root / "config" / "sources.yaml"))
