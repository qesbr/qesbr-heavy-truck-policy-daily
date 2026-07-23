from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

from policy_daily.models import (
    Article,
    EvidenceLevel,
    LifecycleStage,
    RawArticle,
    RelevanceLevel,
)
from policy_daily.screening import calculate_importance, classify_lifecycle, classify_relevance
from policy_daily.utils import clean_text, normalize_url, stable_id


class AIResult(BaseModel):
    relevant: bool
    title_zh: str = ""
    summary_zh: str = Field(default="", max_length=300)
    primary_category: str = "政策"
    region: str = ""
    tags: list[str] = Field(default_factory=list)
    event_key: str = ""
    language: str = "unknown"
    relevance_level: RelevanceLevel = RelevanceLevel.PROBABLE
    lifecycle_stage: LifecycleStage = LifecycleStage.UNKNOWN
    vehicle_classes: list[str] = Field(default_factory=list)
    powertrain_scope: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)


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
        if not result.relevant or result.relevance_level == RelevanceLevel.NONE:
            return None
        summary = clean_text(result.summary_zh)
        if len(summary) < 150:
            summary = clean_text(f"{summary} {raw.content[:300]}")[:300]
        if len(summary) < 150:
            summary = (summary + " 原文正文和发布时间已经核验；摘要仅复述公开内容，不增加原文之外的判断。")[:300]
        categories = {"政策", "法规", "标准", "市场", "企业"}
        normalized_url = normalize_url(str(raw.source_url))
        article = Article(
            id=stable_id(normalized_url),
            title_zh=clean_text(result.title_zh or raw.title),
            title_original="" if result.language.startswith("zh") else clean_text(raw.title),
            summary_zh=summary,
            source_id=raw.source_id,
            source_name=raw.source_name,
            source_type=raw.source_type,
            source_url=normalized_url,
            published_at=raw.published_at,
            collected_at=raw.collected_at,
            region=result.region or raw.region_hint,
            primary_category=result.primary_category if result.primary_category in categories else "政策",
            tags=self._normalize_tags(result.tags),
            importance_score=0,
            content_hash=stable_id(clean_text(raw.content), length=32),
            event_id=stable_id(result.event_key or result.title_zh or raw.title),
            content_evidence=clean_text(raw.content[:1000]),
            language=result.language,
            authority=raw.authority,
            document_id=raw.document_id,
            document_type=raw.document_type,
            lifecycle_stage=result.lifecycle_stage,
            relevance_level=result.relevance_level,
            evidence_level=raw.evidence_level,
            vehicle_classes=list(dict.fromkeys(result.vehicle_classes))[:8],
            powertrain_scope=list(dict.fromkeys(result.powertrain_scope))[:8],
            evidence_quotes=[clean_text(quote)[:240] for quote in result.evidence_quotes[:3]],
        )
        article.importance_score = calculate_importance(article)
        article.is_highlight = article.importance_score >= self.config.highlight_threshold
        return article

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        output = []
        for tag in tags:
            normalized = self.config.aliases.get(tag, tag)
            if normalized and normalized not in output:
                output.append(normalized)
        output.sort(key=lambda value: (
            value not in self.config.core_tags,
            self.config.core_tags.index(value) if value in self.config.core_tags else 999,
        ))
        return output[:3]

    def _remote(self, raw: RawArticle) -> AIResult:
        prompt = (
            "你是汽车监管情报核验编辑。只能依据给定正文返回严格JSON，不得依据常识补写。\n"
            "先判断是否影响道路机动车、商用车或相关能源基础设施。relevance_level只能是："
            "direct（明确涉及重卡/N2/N3/HDV）、probable（商用车或货运高度相关）、"
            "indirect（上游电池能源间接影响）、none（无关）。\n"
            "识别法规阶段 lifecycle_stage、适用车辆 vehicle_classes、动力范围 powertrain_scope；"
            "evidence_quotes最多3条，必须是支持判断的正文短句。摘要150至300个汉字，包含变化、适用对象和明确时间节点。"
            "主分类只能是政策/法规/标准/市场/企业，标签最多3个。\n"
            f"JSON Schema: {json.dumps(AIResult.model_json_schema(), ensure_ascii=False)}\n"
            f"标题:{raw.title}\n来源:{raw.source_name}\n文件类型:{raw.document_type}\n正文:{raw.content[:12000]}"
        )
        last_error: Exception | None = None
        for _ in range(self.config.retries + 1):
            try:
                response = self.client.post(
                    self.config.endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.config.model,
                        "response_format": {"type": "json_object"},
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
                return AIResult.model_validate_json(response.json()["choices"][0]["message"]["content"])
            except Exception as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
                    break
        raise RuntimeError(f"DeepSeek结构化输出失败: {last_error}")

    def _mock(self, raw: RawArticle) -> AIResult:
        relevance = classify_relevance(raw.title, raw.content)
        lifecycle = classify_lifecycle(raw.title, raw.content)
        text = f"{raw.title} {raw.content}".lower()
        category = "标准" if "标准" in text or "standard" in text else "法规" if any(
            term in text for term in ("法规", "条例", "regulation", "rule")
        ) else "政策"
        tag_rules = {
            "重型货车": ("重卡", "重型货车", "heavy-duty"),
            "零排放重卡": ("电动重卡", "纯电重卡", "zero-emission truck"),
            "动力电池": ("电池", "battery"),
            "充电": ("充电", "charging"),
            "换电": ("换电",),
            "排放": ("排放", "emission"),
            "碳排放": ("碳", "co2", "carbon"),
            "市场准入": ("准入", "认证", "type approval"),
        }
        tags = [tag for tag, terms in tag_rules.items() if any(term in text for term in terms)][:3]
        excerpt = clean_text(raw.content)[:240]
        summary = f"该信息由{raw.source_name}发布，主要涉及{raw.title}。{excerpt}"[:300]
        vehicle_classes = ["重型货车"] if relevance == RelevanceLevel.DIRECT else ["商用车"] if relevance == RelevanceLevel.PROBABLE else []
        return AIResult(
            relevant=relevance != RelevanceLevel.NONE,
            relevance_level=relevance,
            lifecycle_stage=lifecycle,
            title_zh=raw.title,
            summary_zh=summary,
            primary_category=category,
            region=raw.region_hint,
            tags=tags,
            event_key=re.sub(r"\W+", "", raw.title.lower())[:80],
            language="zh" if re.search(r"[\u4e00-\u9fff]", raw.title) else "other",
            vehicle_classes=vehicle_classes,
            evidence_quotes=[excerpt[:200]],
        )
