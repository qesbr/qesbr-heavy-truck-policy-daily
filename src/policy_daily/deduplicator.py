from __future__ import annotations

from difflib import SequenceMatcher

from policy_daily.models import Article, RelatedSource
from policy_daily.utils import normalize_url


def similarity(left: Article, right: Article) -> float:
    title = SequenceMatcher(None, left.title_zh.lower(), right.title_zh.lower()).ratio()
    body = SequenceMatcher(None, left.content_evidence[:800], right.content_evidence[:800]).ratio()
    return title * 0.65 + body * 0.35


def deduplicate(articles: list[Article], threshold: float = 0.82) -> list[Article]:
    groups: list[list[Article]] = []
    seen_urls: set[str] = set()
    for article in sorted(articles, key=lambda x: (-x.authority, x.published_at)):
        url = normalize_url(str(article.source_url))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        match = next((group for group in groups if article.event_id == group[0].event_id or similarity(article, group[0]) >= threshold), None)
        if match is None:
            groups.append([article])
        else:
            match.append(article)
    output = []
    for group in groups:
        primary = max(group, key=lambda x: (x.authority, x.importance_score, x.published_at.timestamp()))
        primary.related_sources = [RelatedSource(title=x.title_original or x.title_zh, source_name=x.source_name, source_url=x.source_url) for x in group if x.id != primary.id]
        output.append(primary)
    return sorted(output, key=lambda x: (not x.is_highlight, x.primary_category, -x.published_at.timestamp()))
