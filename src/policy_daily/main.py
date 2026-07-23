from __future__ import annotations

import argparse
import json
import os
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from policy_daily.collectors import ApiCollector, BrowserSiteCollector, HtmlListCollector, OfficialSiteCollector, RssCollector
from policy_daily.config import load_settings, load_sources, read_yaml
from policy_daily.emailer import deliver
from policy_daily.intelligence_store import save_leads, save_official
from policy_daily.models import Article, EvidenceLevel, LeadCandidate, Report, SourceStatus
from policy_daily.processor import DeepSeekProcessor, ProcessorConfig
from policy_daily.reports import build_report
from policy_daily.screening import eligible_for_official_store
from policy_daily.site_builder import build_site
from policy_daily.utils import configure_logging, json_dump

ROOT = Path(__file__).resolve().parents[2]
LOGGER = configure_logging()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="政策法规日报")
    parser.add_argument("--report-type", choices=["daily", "weekly", "monthly"], default="daily")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--send-email", action="store_true")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site-dist")
    parser.add_argument("--base-path", default=None)
    return parser.parse_args(argv)


def period(report_type: str, now: datetime, start_arg: str | None, end_arg: str | None) -> tuple[datetime, datetime]:
    tz = now.tzinfo
    end = datetime.combine(date.fromisoformat(end_arg), time.max, tzinfo=tz) if end_arg else now
    if start_arg:
        start = datetime.combine(date.fromisoformat(start_arg), time.min, tzinfo=tz)
    elif report_type == "daily":
        start = end - timedelta(hours=24)
    elif report_type == "weekly":
        start = end - timedelta(days=7)
    else:
        previous = (end.replace(day=1) - timedelta(days=1)).date()
        start = datetime(previous.year, previous.month, 1, tzinfo=tz)
        end = datetime(previous.year, previous.month, monthrange(previous.year, previous.month)[1], 23, 59, 59, tzinfo=tz)
    return start, end


def load_articles(data_dir: Path) -> list[Article]:
    output: list[Article] = []
    for path in (data_dir / "processed").glob("*.json"):
        try:
            output.extend(Article.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            LOGGER.warning("跳过损坏数据 %s: %s", path.name, exc)
    return output


def collect(root: Path, start: datetime, end: datetime, data_dir: Path) -> list[Article]:
    settings = load_settings(root)
    registry = load_sources(root)
    tags = read_yaml(root / "config" / "tags.yaml")
    processor_config = ProcessorConfig(
        endpoint=settings.deepseek.endpoint,
        model=settings.deepseek.model,
        retries=settings.deepseek.retries,
        highlight_threshold=settings.highlight_threshold,
        core_tags=tags["core_tags"],
        aliases=tags.get("aliases", {}),
    )
    processed: list[Article] = []
    raw_candidates = []
    leads: list[LeadCandidate] = []
    statuses: list[SourceStatus] = []
    transport = httpx.HTTPTransport(retries=settings.request.retries)
    with httpx.Client(
        timeout=httpx.Timeout(settings.request.timeout_seconds),
        transport=transport,
        headers={"User-Agent": settings.request.user_agent},
        follow_redirects=True,
    ) as client:
        processor = DeepSeekProcessor(processor_config, client)
        for definition in registry.sources:
            source = definition.model_dump(mode="json")
            source.setdefault("max_candidates", settings.request.max_candidates_per_source)
            status = SourceStatus(
                id=source["id"], name=source["name"], url=source["url"],
                source_type=source["source_type"], first_discovered_at=end,
                status="disabled" if not source.get("enabled", True) else "pending",
            )
            if not source.get("enabled", True):
                statuses.append(status)
                continue
            collector_cls = {
                "api": ApiCollector,
                "rss": RssCollector,
                "browser_site": BrowserSiteCollector,
                "official_site": OfficialSiteCollector,
            }.get(source.get("adapter"), HtmlListCollector)
            result = collector_cls(source, client).collect(start, end)
            raw_candidates.extend(result.articles)
            status.candidates_found = len(result.articles)
            accepted_before = len(processed)
            ai_failures = 0
            if result.error:
                status.status, status.message = "error", result.error[:240]
                LOGGER.warning("来源采集异常 %s: %s", source["name"], result.error)
            else:
                status.status, status.last_success_at = "ok", end
            for raw in result.articles:
                try:
                    raw.source_id = source["id"]
                    raw.document_type = raw.document_type or ", ".join(source.get("document_types", []))
                    raw.evidence_level = EvidenceLevel(source["evidence_level"])
                    article = processor.process(raw)
                    if not article:
                        continue
                    if eligible_for_official_store(article):
                        processed.append(article)
                    else:
                        leads.append(LeadCandidate(
                            id=article.id, title=article.title_zh, source_name=article.source_name,
                            source_url=article.source_url, published_at=article.published_at,
                            collected_at=article.collected_at,
                            reason=f"相关等级={article.relevance_level.value}，证据等级={article.evidence_level.value}",
                            evidence_level=article.evidence_level,
                        ))
                except Exception as exc:
                    ai_failures += 1
                    LOGGER.warning("AI处理失败 %s: %s", raw.source_name, exc)
            status.accepted_count = len(processed) - accepted_before
            details = [status.message, f"候选{status.candidates_found}条", f"收录{status.accepted_count}条"]
            if ai_failures:
                details.append(f"AI失败{ai_failures}条")
            status.message = "；".join(filter(None, details))
            statuses.append(status)
    save_official(data_dir, end, processed)
    save_leads(data_dir, end, leads)
    json_dump(data_dir / "sources.json", [item.model_dump(mode="json") for item in statuses])
    json_dump(data_dir / "raw" / f"{end.date()}.json", [item.model_dump(mode="json") for item in raw_candidates])
    if processed:
        json_dump(data_dir / "processed" / f"{end.date()}.json", [item.model_dump(mode="json") for item in processed])
    return processed


def report_path(data_dir: Path, report: Report) -> Path:
    return data_dir / report.report_type / f"{report.report_id}.json"


def build_manifest(data_dir: Path) -> None:
    reports = []
    for kind in ("daily", "weekly", "monthly"):
        for path in sorted((data_dir / kind).glob("*.json"), reverse=True):
            try:
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
    json_dump(data_dir / "manifest.json", {"generated_at": datetime.now().astimezone().isoformat(), "reports": reports})
    index = []
    for report in reports:
        for item in report.get("articles", []):
            index.append({"id": item["id"], "text": " ".join([
                item.get("title_zh", ""), item.get("title_original", ""),
                item.get("summary_zh", ""), " ".join(item.get("tags", [])),
            ])})
    json_dump(data_dir / "search-index.json", index)


def load_recipients(path: Path = Path("recipients.yaml")) -> list[str]:
    if not path.exists():
        return []
    return [str(value).strip() for value in read_yaml(path).get("recipients", []) if "@" in str(value)]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(ROOT)
    start, end = period(args.report_type, datetime.now(ZoneInfo(settings.timezone)), args.start, args.end)
    destination = args.data_dir / args.report_type / f"{args.report_type}-{end.date()}.json"
    if destination.exists() and not args.force:
        report = Report.model_validate_json(destination.read_text(encoding="utf-8"))
        LOGGER.info("报告已存在，复用 %s", report.report_id)
    else:
        if not args.skip_collect:
            collect(ROOT, start, end, args.data_dir)
        report = build_report(args.report_type, start, end, load_articles(args.data_dir))
        json_dump(report_path(args.data_dir, report), report.model_dump(mode="json"))
    build_manifest(args.data_dir)
    base_path = args.base_path or settings.site.base_path
    build_site(ROOT, args.data_dir, args.output_dir, base_path)
    send = bool(args.send_email and not args.dry_run)
    email_status = deliver(
        report, load_recipients(), os.getenv("SMTP_USERNAME", ""), os.getenv("SMTP_AUTH_CODE", ""),
        f"https://qesbr.github.io{base_path}", args.output_dir / "email-preview.html", send,
        settings.email.smtp_host, settings.email.smtp_port,
    ) if args.send_email or args.report_type == "daily" else "未请求邮件"
    LOGGER.info(email_status)
    LOGGER.info("完成 %s：%d 条，网站输出 %s", report.report_id, len(report.articles), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
