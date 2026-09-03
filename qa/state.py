"""Cursor for log ingest: ROOT/qa/last_sync.txt (one line ISO-8601 UTC).

Migrates once from legacy ROOT/qa/state.json ``lastSyncEpoch`` if present.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def last_sync_path(root: Path) -> Path:
    return Path(root).expanduser() / "qa" / "last_sync.txt"


def legacy_state_path(root: Path) -> Path:
    return Path(root).expanduser() / "qa" / "state.json"


def read_last_sync_epoch(root: Path) -> int:
    """Unix seconds (exclusive lower bound for event ``tsIso``). ``0`` = no prior sync."""
    root = Path(root).expanduser()
    p = last_sync_path(root)
    if p.is_file():
        try:
            text = p.read_text(encoding="utf-8").strip()
            if not text:
                return 0
            ts = text.replace("Z", "+00:00") if text.endswith("Z") else text
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (OSError, ValueError):
            return 0

    leg = legacy_state_path(root)
    if leg.is_file():
        try:
            data = json.loads(leg.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("lastSyncEpoch") is not None:
                epoch = int(data["lastSyncEpoch"])
                if epoch > 0:
                    write_last_sync_epoch(root, epoch)
                return max(0, epoch)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return 0


def write_last_sync_epoch(root: Path, epoch: int) -> None:
    """Write ``last_sync.txt`` as one line UTC ISO (``Z`` suffix)."""
    dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    _write_last_sync_iso(root, dt)


def _write_last_sync_iso(root: Path, dt: datetime) -> None:
    p = last_sync_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    p.write_text(dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") + "\n", encoding="utf-8")
