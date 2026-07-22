from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from policy_daily.models import RawArticle


@dataclass
class CollectorResult:
    articles: list[RawArticle] = field(default_factory=list)
    error: str = ""


class Collector(ABC):
    def __init__(self, source: dict, client: httpx.Client):
        self.source = source
        self.client = client

    @abstractmethod
    def collect(self, start: datetime, end: datetime) -> CollectorResult:
        raise NotImplementedError

