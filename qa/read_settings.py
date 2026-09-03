#!/usr/bin/env python3
"""Print settings values for install.sh. Usage: read_settings.py KEY"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_merge_config, load_qa_dotenv


def main() -> int:
    load_qa_dotenv()
    cfg = load_merge_config(Path("."))
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    mapping = {
        "log_root": cfg.log_root,
        "git_repo": cfg.git_repo,
        "data_repo": cfg.data_repo,
        "export_dir": cfg.export_dir,
        "merge_hour": str(cfg.merge_hour),
        "merge_minute": str(cfg.merge_minute),
        "extract_poll_seconds": str(cfg.extract_poll_seconds),
        "extract_slots_json": json.dumps(cfg.extract_slots),
        "extract_plist": "\n".join(
            f"    <dict><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>"
            for h, m in cfg.extract_slots
        ),
        "schedule_tz": cfg.schedule_tz,
    }
    if key not in mapping:
        print(f"unknown key: {key}", file=sys.stderr)
        return 1
    print(mapping[key], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
