from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> int:
    data_dir = Path(sys.argv[1])
    output = Path(sys.argv[2])
    statuses = load(data_dir / "sources.json", [])
    official = []
    leads = []
    for path in (data_dir / "intelligence" / "official").glob("*.json"):
        official.extend(load(path, []))
    for path in (data_dir / "intelligence" / "leads").glob("*.json"):
        leads.extend(load(path, []))

    lines = [
        "# 监管来源审计",
        "",
        f"- 来源总数：{len(statuses)}",
        f"- 正式情报：{len(official)}",
        f"- 待核实线索：{len(leads)}",
        "",
        "| 来源 | 状态 | 候选/收录 | 说明 |",
        "|---|---|---:|---|",
    ]
    for status in statuses:
        message = str(status.get("message", "")).replace("|", "｜").replace("\n", " ")
        lines.append(
            f"| {status.get('name', '')} | {status.get('status', '')} | "
            f"{status.get('candidates_found', 0)}/{status.get('accepted_count', 0)} | {message} |"
        )
    if official:
        lines.extend(["", "## 正式情报", ""])
        lines.extend(f"- {item.get('title_zh', '')}（{item.get('source_name', '')}）" for item in official)
    if leads:
        lines.extend(["", "## 待核实线索", ""])
        lines.extend(f"- {item.get('title', '')}：{item.get('reason', '')}" for item in leads)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
