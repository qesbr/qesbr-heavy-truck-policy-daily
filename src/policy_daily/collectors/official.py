from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from trafilatura import bare_extraction

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import RawArticle
from policy_daily.utils import clean_text, normalize_url, within_window

DATE_RE = re.compile(r"(20\d{2})\s*[年./-]\s*(1[0-2]|0?[1-9])\s*[月./-]\s*(3[01]|[12]\d|0?[1-9])\s*日?")


def parse_date(value: str, timezone) -> datetime | None:
    if "T" in (value or "") or ":" in (value or ""):
        try:
            result = date_parser.parse(value, fuzzy=True)
            if 2000 <= result.year <= datetime.now().year + 1:
                return result if result.tzinfo else result.replace(tzinfo=timezone)
        except (ValueError, TypeError, OverflowError):
            pass
    match = DATE_RE.search(value or "")
    if match:
        result = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone)
        return result
    try:
        result = date_parser.parse(value, fuzzy=True)
        if 2000 <= result.year <= datetime.now().year + 1:
            return result if result.tzinfo else result.replace(tzinfo=timezone)
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def extract_jsonld_date(soup: BeautifulSoup, timezone) -> datetime | None:
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.string or "{}")
            values = payload if isinstance(payload, list) else [payload]
            for value in values:
                if isinstance(value, dict):
                    for key in ("datePublished", "dateCreated", "uploadDate"):
                        if value.get(key):
                            parsed = parse_date(str(value[key]), timezone)
                            if parsed:
                                return parsed
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def extract_meta_date(soup: BeautifulSoup, timezone) -> datetime | None:
    keys = {
        "article:published_time", "datepublished", "publishdate", "pubdate",
        "publication_date", "date", "dc.date", "dcterms.date",
    }
    for node in soup.select("meta[content]"):
        key = clean_text(str(node.get("property") or node.get("name") or node.get("itemprop") or "")).lower()
        if key in keys:
            parsed = parse_date(str(node.get("content", "")), timezone)
            if parsed:
                return parsed
    return None


class OfficialSiteCollector(Collector):
    """Configuration-driven official-site adapter with strict detail-page verification."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        try:
            response = self.client.get(self.source["url"])
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            selector = self.source.get("link_selector", "a[href]")
            include = [re.compile(pattern, re.I) for pattern in self.source.get("url_patterns", [])]
            exclude = [re.compile(pattern, re.I) for pattern in self.source.get("exclude_patterns", [])]
            candidates: list[tuple[str, str, datetime | None]] = []
            seen: set[str] = set()
            for link in soup.select(selector):
                href = link.get("href")
                title = clean_text(link.get_text(" ", strip=True))
                if not href or len(title) < 8:
                    continue
                url = normalize_url(urljoin(self.source["url"], href))
                if url in seen or (include and not any(p.search(url) for p in include)) or any(p.search(url) for p in exclude):
                    continue
                if urlsplit(url).scheme not in {"http", "https"}:
                    continue
                nearby = " ".join(parent.get_text(" ", strip=True) for parent in list(link.parents)[:2])
                candidates.append((title, url, parse_date(nearby, end.tzinfo)))
                seen.add(url)
                if len(candidates) >= int(self.source.get("max_candidates", 30)):
                    break

            articles = []
            errors = 0
            rejected_date = 0
            rejected_content = 0
            for list_title, url, list_date in candidates:
                try:
                    detail = self.client.get(url)
                    detail.raise_for_status()
                    detail_soup = BeautifulSoup(detail.content, "html.parser")
                    extracted = bare_extraction(
                        detail.content, url=url, with_metadata=True, include_comments=False,
                        only_with_metadata=False, date_extraction_params={"original_date": True, "extensive_search": True, "max_date": end.date().isoformat()},
                    )
                    extracted_data = extracted.as_dict() if extracted is not None and hasattr(extracted, "as_dict") else (extracted or {})
                    meta_date = parse_date(str(extracted_data.get("date", "")), end.tzinfo)
                    published = extract_meta_date(detail_soup, end.tzinfo) or extract_jsonld_date(detail_soup, end.tzinfo) or meta_date or list_date
                    if not published or not within_window(published, start, end):
                        rejected_date += 1
                        continue
                    content = clean_text(str(extracted_data.get("text", "")))
                    min_content_chars = int(self.source.get("min_content_chars", 200))
                    if len(content) < min_content_chars:
                        container = detail_soup.select_one(self.source.get("content_selector", "article, main, .article, .content, .TRS_Editor"))
                        content = clean_text(container.get_text(" ", strip=True)) if container else ""
                    if len(content) < min_content_chars:
                        rejected_content += 1
                        continue
                    title = clean_text(str(extracted_data.get("title") or list_title))
                    articles.append(RawArticle(
                        title=title, source_name=self.source["name"], source_type=self.source["source_type"],
                        source_url=url, published_at=published, collected_at=end, content=content[:20000],
                        region_hint=self.source.get("region", "其他"), authority=self.source.get("authority", 50),
                    ))
                except Exception:
                    errors += 1
            reasons = []
            if errors:
                reasons.append(f"{errors}个候选详情页失败")
            if not articles and rejected_date:
                reasons.append(f"{rejected_date}条日期不在窗口")
            if not articles and rejected_content:
                reasons.append(f"{rejected_content}条正文不足")
            message = "；".join(reasons)
            return CollectorResult(articles=articles, error=message if candidates else "未发现候选链接")
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
