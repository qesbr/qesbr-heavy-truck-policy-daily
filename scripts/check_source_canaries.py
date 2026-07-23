from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from policy_daily.collectors.api import ApiCollector
from policy_daily.config import load_settings, load_sources


ROOT = Path(__file__).resolve().parents[1]


def collect_canary(source_id: str, start: datetime, end: datetime, client):
    source = next(
        item for item in load_sources(ROOT).sources if item.id == source_id
    ).model_dump(mode="json")
    return ApiCollector(source, client).collect(start, end)


def main() -> int:
    settings = load_settings(ROOT)
    timezone = ZoneInfo(settings.timezone)
    with httpx.Client(
        timeout=httpx.Timeout(60),
        follow_redirects=True,
        headers={"User-Agent": settings.request.user_agent},
    ) as client:
        result = collect_canary(
            "eurlex_oj",
            datetime(2026, 2, 15, tzinfo=timezone),
            datetime(2026, 2, 25, 23, 59, 59, tzinfo=timezone),
            client,
        )
        california = collect_canary(
            "california_oal_vehicle",
            datetime(2026, 4, 10, tzinfo=timezone),
            datetime(2026, 4, 10, 23, 59, 59, tzinfo=timezone),
            client,
        )
    if result.error:
        raise RuntimeError(f"EUR-Lex canary collection failed: {result.error}")
    documents = {article.document_id: article for article in result.articles}
    expected = "32026R0361"
    if expected not in documents:
        raise RuntimeError(
            f"EUR-Lex canary {expected} missing. {result.message}"
        )
    article = documents[expected]
    if len(article.content) < 500:
        raise RuntimeError(f"EUR-Lex canary text too short: {len(article.content)}")
    print(
        f"EUR-Lex canary passed: {expected}, "
        f"{len(article.content)} text characters. {result.message}"
    )
    if california.error:
        raise RuntimeError(f"California register canary failed: {california.error}")
    if "2026-15-Z" not in {article.document_id for article in california.articles}:
        raise RuntimeError(
            f"California register canary 2026-15-Z missing. {california.message}"
        )
    print(f"California register canary passed. {california.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
