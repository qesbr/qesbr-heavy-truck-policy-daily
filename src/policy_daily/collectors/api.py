from __future__ import annotations

from datetime import datetime
import re

from dateutil import parser as date_parser

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import EvidenceLevel, RawArticle
from policy_daily.utils import clean_text, within_window


class ApiCollector(Collector):
    """Collector for stable, structured regulatory APIs."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        if self.source.get("api_kind") != "federal_register":
            return CollectorResult(error=f"不支持的API类型: {self.source.get('api_kind')}")
        return self._federal_register(start, end)

    def _federal_register(self, start: datetime, end: datetime) -> CollectorResult:
        query = self.source.get("query", {})
        documents: dict[str, dict] = {}
        try:
            for term in query.get("terms", []):
                params: list[tuple[str, str | int]] = [
                    ("per_page", 100), ("order", "newest"), ("conditions[term]", term),
                    ("conditions[publication_date][gte]", start.date().isoformat()),
                    ("conditions[publication_date][lte]", end.date().isoformat()),
                ]
                params.extend(("conditions[agencies][]", agency) for agency in query.get("agencies", []))
                response = self.client.get(self.source["url"], params=params)
                response.raise_for_status()
                for document in response.json().get("results", []):
                    key = document.get("document_number") or document.get("html_url")
                    if key:
                        documents[key] = document
            articles: list[RawArticle] = []
            excluded_titles = [re.compile(pattern, re.I) for pattern in self.source.get("exclude_patterns", [])]
            for document in documents.values():
                title = clean_text(document.get("title", ""))
                if any(pattern.search(title) for pattern in excluded_titles):
                    continue
                published = date_parser.parse(document["publication_date"]).replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                detail_url = document.get("raw_text_url") or document.get("html_url")
                if not detail_url:
                    continue
                detail = self.client.get(detail_url)
                detail.raise_for_status()
                content = clean_text(detail.text)
                if len(content) < int(self.source.get("min_content_chars", 200)):
                    continue
                articles.append(RawArticle(
                    title=title,
                    source_id=self.source["id"], source_name=self.source["name"],
                    source_type=self.source["source_type"],
                    source_url=document.get("html_url") or detail_url,
                    published_at=published, collected_at=end, content=content[:30000],
                    region_hint=self.source.get("region", "美国"),
                    authority=self.source.get("authority", 100),
                    document_id=document.get("document_number", ""),
                    document_type=document.get("type", ""),
                    evidence_level=EvidenceLevel(self.source.get("evidence_level", "S")),
                ))
            return CollectorResult(articles=articles)
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
