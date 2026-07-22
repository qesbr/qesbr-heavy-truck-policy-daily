from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RequestConfig(BaseModel):
    timeout_seconds: int = 20
    retries: int = 2
    rate_limit_seconds: float = 0.5
    user_agent: str


class DeepSeekConfig(BaseModel):
    endpoint: str
    model: str = "deepseek-chat"
    retries: int = 2
    mock_without_key: bool = True


class SiteConfig(BaseModel):
    title: str
    base_path: str


class EmailConfig(BaseModel):
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    sender_name: str = "政策法规日报"


class Settings(BaseModel):
    timezone: str = "Asia/Shanghai"
    window_hours: int = Field(default=24, gt=0)
    highlight_threshold: int = Field(default=75, ge=0, le=100)
    request: RequestConfig
    deepseek: DeepSeekConfig
    site: SiteConfig
    email: EmailConfig


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(root: Path) -> Settings:
    return Settings.model_validate(read_yaml(root / "config" / "settings.yaml"))

