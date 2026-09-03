"""Sync Anki deck export to ``<repo>/<subdir>/<deck>/current_cards`` and ``history`` JSONL files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collection_apy import fetch_notes_info, find_note_ids
from config import MergeConfig
from hashing import deck_slug, q_hash


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
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


def _jsonl_rows_from_glob(dir_path: Path, pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted(dir_path.glob(pattern)):
        rows.extend(_jsonl_rows(p))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _field_value(fields: Any, name: str) -> str:
    if not isinstance(fields, dict):
        return ""
    cell = fields.get(name)
    if isinstance(cell, dict):
        return str(cell.get("value") or "")
    if isinstance(cell, str):
        return cell
    return ""


def _note_tags(note_info: dict[str, Any]) -> list[str]:
    tags = note_info.get("tags")
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, str):
        return tags.split()
    return []


def sync_qa_pairs_deck(repo: Path, a: Any, cfg: MergeConfig) -> None:
    """Persist current active cards + append archival history."""
    deck = cfg.anki_deck
    sub = (cfg.git_qa_subdir or "qa_pairs").strip().strip("/\\").replace("\\", "/")
    deck_dir = (repo / sub / deck_slug(deck)).resolve()
    current_dir = deck_dir / "current_cards"
    history_dir = deck_dir / "history"
    current_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    note_ids = find_note_ids(a, f'deck:"{deck}" tag:qa-import') or find_note_ids(
        a,
        f"deck:{deck} tag:qa-import",
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active: dict[str, dict[str, Any]] = {}

    for i in range(0, len(note_ids), 200):
        chunk = note_ids[i : i + 200]
        for info in fetch_notes_info(a, chunk):
            question = _field_value(info.get("fields"), "Front").strip()
            back_markdown = _field_value(info.get("fields"), "Back").rstrip()
            if not question:
                continue
            tags = _note_tags(info)
            qh = q_hash(question, back_markdown, tags)
            active[qh] = {
                "qahash16": qh,
                "question": question,
                "answerBack": back_markdown,
                "ankiNoteId": int(info.get("noteId") or 0),
                "tags": tags,
                "updatedAt": now,
                "status": "active",
            }

    prev_rows = _jsonl_rows_from_glob(current_dir, "cards-*.jsonl")
    if not prev_rows:
        prev_rows = _jsonl_rows(current_dir / "current_state.jsonl")
    prev = {
        str(r.get("qahash16") or "").strip().lower(): r
        for r in prev_rows
        if str(r.get("qahash16") or "").strip()
    }

    for old_path in current_dir.glob("qa-*.jsonl"):
        old_path.unlink(missing_ok=True)
    for old_path in current_dir.glob("cards-*.jsonl"):
        old_path.unlink(missing_ok=True)

    current_rows = [active[h] for h in sorted(active.keys())]
    _write_jsonl(current_dir / "current_state.jsonl", current_rows)
    for idx in range(0, len(current_rows), 100):
        chunk = current_rows[idx : idx + 100]
        name = f"cards-{(idx // 100) + 1:05d}.jsonl"
        _write_jsonl(current_dir / name, chunk)

    history_entries: list[dict[str, Any]] = []
    chunk_files = sorted(history_dir.glob("cards-*.jsonl"))
    for cf in chunk_files:
        history_entries.extend(_jsonl_rows(cf))

    all_hashes = {
        str(r.get("qahash16") or "").strip().lower()
        for r in history_entries
        if str(r.get("qahash16") or "").strip()
    }

    history_hashes = set(all_hashes)

    def _append_if_new(row: dict[str, Any]) -> None:
        h = str(row.get("qahash16") or "").strip().lower()
        if not h or h in history_hashes:
            return
        history_entries.append(row)
        history_hashes.add(h)
        all_hashes.add(h)

    for qh, prev_row in prev.items():
        cur_row = active.get(qh)
        if cur_row is None:
            archived = dict(prev_row)
            archived["status"] = "archived"
            archived["archivedAt"] = now
            _append_if_new(archived)
            continue
        if (
            str(prev_row.get("question") or "") != str(cur_row.get("question") or "")
            or str(prev_row.get("answerBack") or "") != str(cur_row.get("answerBack") or "")
        ):
            archived = dict(prev_row)
            archived["status"] = "archived"
            archived["archivedAt"] = now
            _append_if_new(archived)
            _append_if_new(dict(cur_row))

    for qh, cur_row in active.items():
        if qh not in prev:
            _append_if_new(dict(cur_row))

    for cf in chunk_files:
        cf.unlink(missing_ok=True)
    for idx in range(0, len(history_entries), 100):
        chunk = history_entries[idx : idx + 100]
        name = f"cards-{(idx // 100) + 1:05d}.jsonl"
        _write_jsonl(history_dir / name, chunk)

    all_hash_rows = [{"qahash16": h} for h in sorted(h for h in all_hashes if h)]
    _write_jsonl(history_dir / "all_hashes.jsonl", all_hash_rows)
