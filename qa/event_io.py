"""Read daemon daily JSON files for chatgpt, claude, and gemini."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_ts_epoch(ts_iso: Any) -> int:
    text = str(ts_iso or "").strip()
    if not text:
        return 0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

SITES = ("chatgpt", "claude", "gemini")


def day_file(root: Path, site: str, day_iso: str) -> Path:
    return Path(root).expanduser() / site / f"{day_iso}.json"


def utc_day_strings_ending_today(num_days: int) -> list[str]:
    """Return `num_days` ISO date strings in UTC, starting at today. Matches daemon `_iso_day_from_ts` UTC bucketing."""
    if num_days < 1:
        return []
    today = datetime.now(timezone.utc).date()
    out: list[str] = []
    for i in range(0, num_days):
        out.append((today - timedelta(days=i)).isoformat())
    return out


def _read_day_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def iter_assistant_structured_events(
    root: Path,
    day_iso: str,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (site, event) for assistant structured events for one UTC calendar day.
    """
    root = Path(root).expanduser()
    for site in SITES:
        path = day_file(root, site, day_iso)
    
        for event in _read_day_events(path):
            if str(event.get("role", "")).strip().lower() != "assistant":
                continue
            mode = str(event.get("extractionMode", "plain")).strip().lower()
            if mode != "structured":
                continue
            text = str(event.get("text") or "")
            if "QQQ" not in text and "qqq" not in text:
                continue
            yield site, event


def iter_assistant_structured_events_range(
    root: Path,
    day_iso_list: list[str],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """
    Yield (day_iso, site, event) sorted by tsIso across all sites and days.
    """
    root = Path(root).expanduser()
    rows: list[tuple[str, str, str, dict[str, Any]]] = []
    for day_iso in day_iso_list:
        for site, event in iter_assistant_structured_events(
            root, day_iso
        ):
            ts = str(event.get("tsIso") or "")
            rows.append((ts, day_iso, site, event))

    rows.sort(key=lambda r: r[0])
    for _ts, day_iso, site, event in rows:
        yield day_iso, site, event


def iter_assistant_structured_events_since(
    root: Path,
    day_iso_list: list[str],
    min_event_epoch_exclusive: int,
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Like ``iter_assistant_structured_events_range`` but only events with tsIso epoch > bound."""
    for day_iso, site, event in iter_assistant_structured_events_range(
        root, day_iso_list
    ):
        if parse_ts_epoch(event.get("tsIso")) > min_event_epoch_exclusive:
            yield day_iso, site, event
