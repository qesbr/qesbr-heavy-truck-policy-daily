from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from policy_daily.config import load_settings
from policy_daily.main import ROOT, build_manifest, collect, load_articles, report_path
from policy_daily.reports import build_report
from policy_daily.site_builder import build_site
from policy_daily.utils import json_dump


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按自然日回填政策法规日报")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site-dist")
    parser.add_argument("--base-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings(ROOT)
    tz = ZoneInfo(settings.timezone)
    first, last = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if first > last:
        raise SystemExit("开始日期不能晚于结束日期")

    window_start = datetime.combine(first, time.min, tzinfo=tz)
    window_end = datetime.combine(last, time.max, tzinfo=tz)
    collect(ROOT, window_start, window_end, args.data_dir)
    articles = load_articles(args.data_dir)

    current = first
    while current <= last:
        day_start = datetime.combine(current, time.min, tzinfo=tz)
        day_end = datetime.combine(current, time.max, tzinfo=tz)
        report = build_report("daily", day_start, day_end, articles)
        json_dump(report_path(args.data_dir, report), report.model_dump(mode="json"))
        current += timedelta(days=1)

    build_manifest(args.data_dir)
    build_site(ROOT, args.data_dir, args.output_dir, args.base_path or settings.site.base_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
