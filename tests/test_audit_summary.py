import json
import subprocess
import sys
from pathlib import Path


def test_audit_summary(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "sources.json").write_text(json.dumps([{
        "name": "测试来源", "status": "ok", "candidates_found": 2,
        "accepted_count": 1, "message": "候选2条；收录1条",
    }], ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "summary.md"
    script = Path(__file__).parents[1] / "scripts" / "summarize_audit.py"
    subprocess.run([sys.executable, str(script), str(data), str(output)], check=True)
    text = output.read_text(encoding="utf-8")
    assert "测试来源" in text
    assert "2/1" in text
