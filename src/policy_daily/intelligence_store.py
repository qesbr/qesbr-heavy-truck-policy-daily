from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from policy_daily.models import Article, LeadCandidate, PageSnapshot
from policy_daily.utils import clean_text, json_dump, stable_id


def save_official(data_dir: Path, collected_at: datetime, articles: list[Article]) -> None:
    json_dump(data_dir / "intelligence" / "official" / f"{collected_at.date()}.json", [a.model_dump(mode="json") for a in articles])


def save_leads(data_dir: Path, collected_at: datetime, leads: list[LeadCandidate]) -> None:
    json_dump(data_dir / "intelligence" / "leads" / f"{collected_at.date()}.json", [lead.model_dump(mode="json") for lead in leads])


def snapshot_page(data_dir: Path, source_id: str, url: str, captured_at: datetime, text: str) -> PageSnapshot:
    normalized = clean_text(text)
    content_hash = stable_id(normalized, length=32)
    latest_path = data_dir / "snapshots" / source_id / "latest.json"
    previous_hash = json.loads(latest_path.read_text(encoding="utf-8")).get("content_hash", "") if latest_path.exists() else ""
    snapshot = PageSnapshot(
        source_id=source_id, url=url, captured_at=captured_at, content_hash=content_hash,
        normalized_text=normalized[:50000], previous_hash=previous_hash, changed=content_hash != previous_hash,
    )
    json_dump(latest_path, snapshot.model_dump(mode="json"))
    if snapshot.changed:
        json_dump(data_dir / "snapshots" / source_id / f"{captured_at:%Y%m%dT%H%M%S}.json", snapshot.model_dump(mode="json"))
    return snapshot
