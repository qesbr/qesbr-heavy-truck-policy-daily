from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

from policy_daily.models import Article, RawArticle
from policy_daily.utils import clean_text, normalize_url, stable_id

KEYWORDS = ("重卡", "重型车", "heavy-duty", "truck", "动力电池", "充电", "换电", "排放", "carbon", "emission", "自动驾驶", "市场准入", "vehicle regulation")


class AIResult(BaseModel):
    relevant: bool
    title_zh: str = ""
    summary_zh: str = Field(default="", max_length=300)
    primary_category: str = "政策"
    region: str = ""
    tags: list[str] = []
    importance_score: int = Field(default=50, ge=0, le=100)
    event_key: str = ""
    language: str = "unknown"


@dataclass
class ProcessorConfig:
    endpoint: str
    model: str
    retries: int
    highlight_threshold: int
    core_tags: list[str]
    aliases: dict[str, str]


class DeepSeekProcessor:
    def __init__(self, config: ProcessorConfig, client: httpx.Client):
        self.config = config
        self.client = client
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")

    def process(self, raw: RawArticle) -> Article | None:
        result = self._remote(raw) if self.api_key else self._mock(raw)
        if not result.relevant:
            return None
        title_zh = clean_text(result.title_zh or raw.title)
        summary_zh = clean_text(result.summary_zh)
        if len(summary_zh) < 150:
            evidence = clean_text(raw.content)
            summary_zh = clean_text(f"{summary_zh} {evidence[:300]}")[:300]
        if len(summary_zh) < 150:
            summary_zh = (summary_zh + " 原文正文和发布时间已核验，本摘要仅复述公开信息。")[:300]
        categories = {"政策", "法规", "标准", "市场", "企业"}
        category = result.primary_category if result.primary_category in categories else "政策"
        tags = self._normalize_tags(result.tags)
        normalized = normalize_url(str(raw.source_url))
        content_hash = stable_id(clean_text(raw.content), length=32)
        title_original = "" if result.language.startswith("zh") else raw.title
        return Article(
            id=stable_id(normalized), title_zh=title_zh, title_original=clean_text(title_original),
            summary_zh=summary_zh, source_name=raw.source_name, source_type=raw.source_type,
            source_url=normalized, published_at=raw.published_at, collected_at=raw.collected_at,
            region=result.region or raw.region_hint, primary_category=category, tags=tags,
            importance_score=result.importance_score,
            is_highlight=result.importance_score >= self.config.highlight_threshold,
            content_hash=content_hash, event_id=stable_id(result.event_key or title_zh),
            content_evidence=clean_text(raw.content[:1000]), language=result.language, authority=raw.authority,
        )

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        output = []
        for tag in tags:
            normalized = self.config.aliases.get(tag, tag)
            if normalized not in output:
                output.append(normalized)
        output.sort(key=lambda x: (x not in self.config.core_tags, self.config.core_tags.index(x) if x in self.config.core_tags else 999))
        return output[:3]

    def _remote(self, raw: RawArticle) -> AIResult:
        schema = AIResult.model_json_schema()
        prompt = (
            "你是政策信息核验编辑。只依据给定正文，返回严格JSON。摘要150至300个汉字，包含核心内容、主要变化、适用对象和明确时间节点；"
            "禁止建议和正文外推断。主分类只能是政策/法规/标准/市场/企业，标签最多3个。\n"
            f"JSON Schema: {json.dumps(schema, ensure_ascii=False)}\n标题:{raw.title}\n来源:{raw.source_name}\n正文:{raw.content[:12000]}"
        )
        last_error: Exception | None = None
        for _ in range(self.config.retries + 1):
            try:
                response = self.client.post(self.config.endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, json={
                    "model": self.config.model, "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                })
                response.raise_for_status()
                payload = response.json()["choices"][0]["message"]["content"]
                return AIResult.model_validate_json(payload)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"DeepSeek结构化输出失败: {last_error}")

    def _mock(self, raw: RawArticle) -> AIResult:
        haystack = f"{raw.title} {raw.content}".lower()
        relevant = any(word.lower() in haystack for word in KEYWORDS)
        mapping = [("标准", "标准"), ("法规", "法规"), ("条例", "法规"), ("市场", "市场"), ("企业", "企业")]
        category = next((value for word, value in mapping if word in haystack), "政策")
        tag_rules = {
            "纯电重卡": ("纯电", "electric truck", "zero-emission truck"), "动力电池": ("电池", "battery"),
            "充电": ("充电", "charging"), "换电": ("换电",), "排放": ("排放", "emission"),
            "碳排放": ("碳", "co2", "carbon"), "智能驾驶": ("自动驾驶", "智能驾驶", "autonomous"),
            "市场准入": ("准入", "认证", "type approval"),
        }
        tags = [tag for tag, words in tag_rules.items() if any(word in haystack for word in words)][:3]
        excerpt = clean_text(raw.content)[:240]
        summary = f"该信息由{raw.source_name}发布，主要涉及{raw.title}。{excerpt}"
        summary = summary[:300]
        if len(summary) < 150:
            summary += " 原文已核验正文及发布时间；本摘要仅复述公开内容，不增加行动建议或原文未载明的结论。"
        return AIResult(
            relevant=relevant, title_zh=raw.title, summary_zh=summary[:300], primary_category=category,
            region=raw.region_hint, tags=tags, importance_score=80 if category in {"法规", "标准"} else 60,
            event_key=re.sub(r"\W+", "", raw.title.lower())[:80], language="zh" if re.search(r"[\u4e00-\u9fff]", raw.title) else "other",
        )
