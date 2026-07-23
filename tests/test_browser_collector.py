from pathlib import Path

from policy_daily.collectors.browser import _RenderedClient
from policy_daily.config import load_sources


class FakeNavigation:
    status = 200


class FakePage:
    def goto(self, url, wait_until, timeout):
        assert url == "https://example.com/public"
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        return FakeNavigation()

    def content(self):
        return "<html><main>Public regulation text</main></html>"


def test_rendered_client_returns_httpx_compatible_response():
    response = _RenderedClient(FakePage(), 30000).get("https://example.com/public")
    response.raise_for_status()
    assert "Public regulation text" in response.text


def test_only_failed_public_sources_use_browser_collection():
    registry = load_sources(Path(__file__).parents[1])
    browser_ids = {source.id for source in registry.sources if source.adapter == "browser_site"}
    assert browser_ids == {"unece_wp29", "carb_heavy_duty"}
