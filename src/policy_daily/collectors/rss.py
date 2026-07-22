from __future__ import annotations

from datetime import datetime

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.models import RawArticle
from policy_daily.utils import clean_text, within_window


class RssCollector(Collector):
    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        try:
            response = self.client.get(self.source["url"])
            response.raise_for_status()
            feed = feedparser.loads(response.content)
            result = []
            for entry in feed.entries:
                raw_date = entry.get("published") or entry.get("updated")
                if not raw_date:
                    continue
                published = date_parser.parse(raw_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=end.tzinfo)
                if not within_window(published, start, end):
                    continue
                detail = self.client.get(entry.link)
                detail.raise_for_status()
                soup = BeautifulSoup(detail.text, "html.parser")
                content = clean_text(soup.get_text(" ", strip=True))
                if len(content) < 200:
                    continue
                result.append(RawArticle(
                    title=clean_text(entry.title), source_name=self.source["name"],
                    source_type=self.source["source_type"], source_url=entry.link,
                    published_at=published, collected_at=end, content=content[:20000],
                    region_hint=self.source.get("region", "其他"), authority=self.source.get("authority", 50),
                ))
            return CollectorResult(articles=result)
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")

