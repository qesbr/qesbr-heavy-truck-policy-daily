from __future__ import annotations

from datetime import datetime
import re

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import EvidenceLevel, RawArticle
from policy_daily.utils import clean_text, within_window


class ApiCollector(Collector):
    """Collector for stable, structured regulatory APIs."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        api_kind = self.source.get("api_kind")
        if api_kind == "federal_register":
            return self._federal_register(start, end)
        if api_kind == "california_oal":
            return self._california_oal(start, end)
        if api_kind == "eurlex_cellar":
            return self._eurlex_cellar(start, end)
        return CollectorResult(error=f"不支持的API类型: {api_kind}")

    def _eurlex_cellar(self, start: datetime, end: datetime) -> CollectorResult:
        """Query the EU Publications Office's official machine-readable repository."""
        query = self.source.get("query", {})
        sparql = f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?work ?celex ?date ?title ?item ?format WHERE {{
  ?work cdm:work_date_document ?date ;
        owl:sameAs ?celexUri .
  FILTER(STRSTARTS(STR(?celexUri),
    "http://publications.europa.eu/resource/celex/"))
  BIND(STRAFTER(STR(?celexUri),
    "http://publications.europa.eu/resource/celex/") AS ?celex)
  ?expression cdm:expression_belongs_to_work ?work ;
              cdm:expression_uses_language
                <http://publications.europa.eu/resource/authority/language/ENG> ;
              cdm:expression_title ?title .
  ?manifestation cdm:manifestation_manifests_expression ?expression ;
                 cdm:manifestation_type ?format .
  ?item cdm:item_belongs_to_manifestation ?manifestation .
  FILTER(CONTAINS(LCASE(STR(?format)), "html"))
  FILTER(?date >= "{start.date().isoformat()}"^^xsd:date &&
         ?date <= "{end.date().isoformat()}"^^xsd:date)
}}
ORDER BY DESC(?date)
LIMIT {int(query.get("limit", 500))}
"""
        try:
            response = self.client.get(
                self.source["url"],
                params={"query": sparql, "format": "application/sparql-results+json"},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
            terms = [term.casefold() for term in query.get("terms", [])]
            articles: list[RawArticle] = []
            seen: set[str] = set()
            identified = 0
            title_matches = 0
            detail_rejections = 0
            for binding in bindings:
                title = clean_text(binding.get("title", {}).get("value", ""))
                celex = clean_text(binding.get("celex", {}).get("value", ""))
                if not title or not celex or celex in seen:
                    continue
                identified += 1
                if terms and not any(term in title.casefold() for term in terms):
                    continue
                title_matches += 1
                published = date_parser.parse(binding["date"]["value"]).replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                item_url = clean_text(binding.get("item", {}).get("value", ""))
                if not item_url:
                    detail_rejections += 1
                    continue
                detail = self.client.get(item_url)
                detail.raise_for_status()
                content = clean_text(detail.text)
                if len(content) < int(self.source.get("min_content_chars", 200)):
                    detail_rejections += 1
                    continue
                seen.add(celex)
                articles.append(RawArticle(
                    title=title,
                    source_id=self.source["id"],
                    source_name=self.source["name"],
                    source_type=self.source["source_type"],
                    source_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
                    published_at=published,
                    collected_at=end,
                    content=content[:30000],
                    region_hint=self.source.get("region", "欧盟"),
                    authority=self.source.get("authority", 100),
                    document_id=celex,
                    document_type="EU legal act",
                    evidence_level=EvidenceLevel(self.source.get("evidence_level", "S")),
                ))
            return CollectorResult(
                articles=articles,
                message=(
                    f"Cellar原始{len(bindings)}条；有效CELEX及标题{identified}条；"
                    f"标题匹配{title_matches}条；正文拒绝{detail_rejections}条"
                ),
            )
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")

    def _california_oal(self, start: datetime, end: datetime) -> CollectorResult:
        """Read official OAL action tables as a structured regulatory register."""
        try:
            response = self.client.get(self.source["url"])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            agency_pattern = re.compile(
                self.source.get("query", {}).get("agency_pattern", r"Air Resources Board"),
                re.I,
            )
            include_patterns = [
                re.compile(pattern, re.I)
                for pattern in self.source.get("query", {}).get("include_patterns", [])
            ]
            articles: list[RawArticle] = []
            seen: set[str] = set()
            for row in soup.select("table tr"):
                cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
                if len(cells) < 3:
                    continue
                row_text = " | ".join(cells)
                if not agency_pattern.search(row_text):
                    continue
                if include_patterns and not any(pattern.search(row_text) for pattern in include_patterns):
                    continue
                date_match = re.search(
                    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
                    r"\s+\d{1,2},\s+\d{4}\b",
                    row_text,
                    re.I,
                )
                if not date_match:
                    continue
                published = date_parser.parse(date_match.group(0)).replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                document_id = next(
                    (cell for cell in cells if re.fullmatch(r"\d{4}-\d{4}-\d{2}[A-Z]*", cell, re.I)),
                    "",
                )
                subject = next(
                    (cell for cell in cells if cell and not agency_pattern.fullmatch(cell) and cell != document_id),
                    cells[0],
                )
                key = document_id or f"{subject}|{published.date()}"
                if key in seen:
                    continue
                seen.add(key)
                articles.append(RawArticle(
                    title=subject,
                    source_id=self.source["id"],
                    source_name=self.source["name"],
                    source_type=self.source["source_type"],
                    source_url=self.source["url"],
                    published_at=published,
                    collected_at=end,
                    content=row_text[:30000],
                    region_hint=self.source.get("region", "美国-加州"),
                    authority=self.source.get("authority", 100),
                    document_id=document_id,
                    document_type="Regulatory action",
                    evidence_level=EvidenceLevel(self.source.get("evidence_level", "S")),
                ))
            return CollectorResult(articles=articles)
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")

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
                document_number = document.get("document_number", "")
                metadata_url = document.get("json_url") or (
                    f"https://www.federalregister.gov/api/v1/documents/{document_number}.json"
                    if document_number else ""
                )
                metadata = document
                if metadata_url:
                    metadata_response = self.client.get(metadata_url)
                    metadata_response.raise_for_status()
                    metadata = {**document, **metadata_response.json()}
                detail_urls = [
                    metadata.get("full_text_xml_url"),
                    metadata.get("raw_text_url"),
                    metadata.get("body_html_url"),
                ]
                content = ""
                for detail_url in filter(None, detail_urls):
                    detail = self.client.get(detail_url)
                    detail.raise_for_status()
                    candidate = clean_text(detail.text)
                    lowered = candidate.lower()
                    if "request access" in lowered or "aggressive automated scraping" in lowered:
                        continue
                    if len(candidate) >= int(self.source.get("min_content_chars", 200)):
                        content = candidate
                        break
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
                    document_id=document_number,
                    document_type=metadata.get("type", document.get("type", "")),
                    evidence_level=EvidenceLevel(self.source.get("evidence_level", "S")),
                ))
            return CollectorResult(articles=articles)
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
