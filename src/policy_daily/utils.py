from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import bleach

TRACKING_KEYS = {"fbclid", "gclid", "spm", "from", "source"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def clean_text(value: str) -> str:
    text = bleach.clean(value, tags=[], strip=True)
    return re.sub(r"\s+", " ", text).strip()


def stable_id(*values: str, length: int = 16) -> str:
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()[:length]


def json_dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


class RedactingFilter(logging.Filter):
    patterns = [
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        re.compile(r"(?i)(api[_ -]?key|token|auth[_ -]?code)(\s*[:=]\s*)\S+"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self.patterns:
            message = pattern.sub(lambda m: "***" if "@" in m.group(0) else f"{m.group(1)}{m.group(2)}***", message)
        record.msg, record.args = message, ()
        return True


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("policy_daily")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(RedactingFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def within_window(value: datetime, start: datetime, end: datetime) -> bool:
    return start <= value <= end

