"""Load and atomically rewrite ``ROOT/qa/cards.jsonl`` (canonical QA rows)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def cards_jsonl_path(root: Path) -> Path:
    return Path(root).expanduser() / "qa" / "cards.jsonl"


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def write_jsonl_rows_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    temp.replace(path)


def load_latest_cleaned_cards(root: Path, cleaned_subdir: str = "qa/cleaned") -> dict[str, dict[str, Any]]:
    cleaned_dir = Path(root).expanduser() / cleaned_subdir
    if not cleaned_dir.is_dir():
        return {}
    files = sorted(cleaned_dir.glob("*.jsonl"))
    if not files:
        return {}
    latest = files[-1]
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl_rows(latest):
        q = str(row.get("question") or "").strip()
        b = str(row.get("answerBack") or "").strip()
        if not q or not b:
            continue
        h = row.get("qahash") or row.get("qahash16")
        if isinstance(h, str) and h.strip():
            out[h.strip().lower()] = row
    return out


def write_cards_jsonl_atomic(path: Path, cards: dict[str, dict[str, Any]]) -> None:
    """Replace entire cards.jsonl from merged state (stable key order)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    keys = sorted(cards.keys())
    chunks: list[str] = []
    for k in keys:
        rec = cards.get(k)
        if isinstance(rec, dict):
            chunks.append(json.dumps(rec, ensure_ascii=False) + "\n")
    temp.write_text("".join(chunks), encoding="utf-8")
    temp.replace(path)
