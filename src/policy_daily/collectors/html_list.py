from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import RawArticle
from policy_daily.utils import clean_text, within_window


def _date_from_node(node) -> datetime | None:
    candidates = [node.get("datetime", ""), node.get_text(" ", strip=True)]
    for parent in list(node.parents)[:3]:
        candidates.append(parent.get_text(" ", strip=True))
    for value in candidates:
        try:
            parsed = date_parser.parse(value, fuzzy=True)
            if 2000 <= parsed.year <= datetime.now().year + 1:
                return parsed
        except (ValueError, OverflowError, TypeError):
            continue
    return None


class HtmlListCollector(Collector):
    """Conservative generic collector: follows dated links, then verifies full body."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        try:
            response = self.client.get(self.source["url"])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            articles: list[RawArticle] = []
            seen: set[str] = set()
            for link in soup.select("a[href]"):
                title = clean_text(link.get_text(" ", strip=True))
                if len(title) < 8:
                    continue
                published = _date_from_node(link)
                if not published:
                    continue
                if published.tzinfo is None:
                    published = published.replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                url = urljoin(self.source["url"], link["href"])
                if url in seen:
                    continue
                seen.add(url)
                try:
                    detail = self.client.get(url)
                    detail.raise_for_status()
                    body = BeautifulSoup(detail.text, "html.parser")
                    for bad in body.select("script,style,nav,header,footer,aside"):
                        bad.decompose()
                    content = clean_text(body.get_text(" ", strip=True))
                    if len(content) < 200:
                        continue
                    articles.append(RawArticle(
                        title=title, source_name=self.source["name"], source_type=self.source["source_type"],
                        source_url=url, published_at=published, collected_at=end, content=content[:20000],
                        region_hint=self.source.get("region", "其他"), authority=self.source.get("authority", 50),
                    ))
                    time.sleep(float(self.source.get("rate_limit_seconds", 0)))
                except Exception:
                    continue
            return CollectorResult(articles=articles)
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")

