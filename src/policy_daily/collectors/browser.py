from __future__ import annotations

import httpx

from policy_daily.collectors.base import Collector, CollectorResult
from policy_daily.collectors.official import OfficialSiteCollector


class _RenderedClient:
    """Minimal httpx-compatible client backed by a public Chromium page."""

    def __init__(self, page, timeout_ms: int):
        self.page = page
        self.timeout_ms = timeout_ms

    def get(self, url: str, **_: object) -> httpx.Response:
        navigation = self.page.goto(
            url, wait_until="domcontentloaded", timeout=self.timeout_ms
        )
        status = navigation.status if navigation else 200
        return httpx.Response(
            status,
            text=self.page.content(),
            request=httpx.Request("GET", url),
        )


class BrowserSiteCollector(Collector):
    """Render public JavaScript pages and reuse the conservative official parser."""

    def collect(self, start, end) -> CollectorResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return CollectorResult(error="浏览器采集依赖未安装（playwright）")

        timeout_ms = int(self.source.get("browser_timeout_seconds", 30)) * 1000
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.source.get("browser_user_agent")
                    or "PolicyDaily/0.1 (+https://github.com/qesbr/qesbr-heavy-truck-policy-daily)",
                    locale="en-US",
                )
                page = context.new_page()
                result = OfficialSiteCollector(
                    self.source, _RenderedClient(page, timeout_ms)
                ).collect(start, end)
                context.close()
                browser.close()
                return result
        except Exception as exc:
            return CollectorResult(error=f"{type(exc).__name__}: {exc}")
