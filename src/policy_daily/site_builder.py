from __future__ import annotations

import json
import shutil
from pathlib import Path


def build_site(root: Path, data_dir: Path, output: Path, base_path: str) -> None:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(root / "site", output)
    target_data = output / "data"
    shutil.copytree(data_dir, target_data, dirs_exist_ok=True)
    config = {"basePath": base_path.rstrip("/") + "/", "dataPath": "data/manifest.json"}
    (output / "site-config.js").write_text(f"window.SITE_CONFIG = {json.dumps(config, ensure_ascii=False)};\n", encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")

