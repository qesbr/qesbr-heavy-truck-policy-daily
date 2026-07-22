from __future__ import annotations

from datetime import datetime

from policy_daily.collectors.base import Collector, CollectorResult


class WechatPublicCollector(Collector):
    """Optional public-entry adapter. No scraping occurs without an explicit public RSS/index URL."""

    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        if not self.source.get("url"):
            return CollectorResult(error="未配置稳定、合法的公开入口")
        return CollectorResult(error="公众号入口需专用解析规则，已安全跳过")

