from __future__ import annotations

from datetime import datetime

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import RawArticle
from policy_daily.utils import clean_text, within_window


def feed_text(value: str) -> str:
    return clean_text(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True))


class RssCollector(Collector):
    """RSS collector with topic filtering and summary fallback."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        try:
            response = self.client.get(self.source["url"])
            response.raise_for_status()
            feed = feedparser.loads(response.content)
            keywords = [
                value.casefold() for value in self.source.get("include_keywords", [])
            ]
            max_candidates = int(self.source.get("max_candidates", 100))
            minimum = int(self.source.get("min_content_chars", 200))
            articles: list[RawArticle] = []
            for entry in feed.entries:
                raw_date = entry.get("published") or entry.get("updated")
                if not raw_date:
                    continue
                published = date_parser.parse(raw_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                title = clean_text(entry.get("title", ""))
                summary = feed_text(
                    entry.get("summary", "") or entry.get("description", "")
                )
                if keywords and not any(
                    word in f"{title} {summary}".casefold() for word in keywords
                ):
                    continue
                content = summary
                try:
                    detail = self.client.get(entry.link)
                    detail.raise_for_status()
                    soup = BeautifulSoup(detail.text, "html.parser")
                    for bad in soup.select("script,style,nav,header,footer,aside"):
                        bad.decompose()
                    detail_text = clean_text(soup.get_text(" ", strip=True))
                    if len(detail_text) >= minimum:
                        content = detail_text
                except Exception:
                    pass
                if len(content) < 80:
                    continue
                articles.append(RawArticle(
                    title=title,
                    source_name=self.source["name"],
                    source_type=self.source["source_type"],
                    source_url=entry.link,
                    published_at=published,
                    collected_at=end,
                    content=content[:20000],
                    region_hint=self.source.get("region", "其他"),
                    authority=self.source.get("authority", 50),
                ))
                if len(articles) >= max_candidates:
                    break
            return CollectorResult(
                articles=articles,
                message=f"RSS条目{len(feed.entries)}条；相关候选{len(articles)}条",
            )
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
