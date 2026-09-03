"""Track merge keys already represented in Anki / pushed, to avoid re-ingesting the same log Q/A."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path



def merged_ledger_path(root: Path) -> Path:
    return Path(root).expanduser() / "qa" / "merged.json"


def _normalize_hash(value: str) -> str:
    h = str(value).strip().lower()
    if len(h) >= 32:
        return h[:32]
    if len(h) >= 16:
        return h
    return h


def load_merged_hashes(root: Path) -> set[str]:
    p = merged_ledger_path(root)
    if not p.is_file():
        return set()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(raw, dict):
        return set()
    arr = raw.get("mergedQaHash16")
    if not isinstance(arr, list):
        return set()
    return {_normalize_hash(str(x)) for x in arr if str(x).strip()}


def save_merged_hashes(root: Path, hashes: set[str]) -> None:
    p = merged_ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ordered = sorted({_normalize_hash(h) for h in hashes if h})
    payload = {
        "updatedAt": stamp,
        "mergedQaHash16": ordered,
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
