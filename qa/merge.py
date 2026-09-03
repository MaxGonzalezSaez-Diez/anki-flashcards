#!/usr/bin/env python3
"""Morning QA job: Anki source-of-truth + cleaned merge + git snapshots. Headless (apyanki)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment, misc]

from anki_quit import quit_anki
from config import load_merge_config, load_qa_dotenv
from pipeline import run_morning

_NO_FCNTL = object()

load_qa_dotenv()


def _resolve_log_root() -> Path:
    er = os.environ.get("READ_CHAT_GUI_LOG_ROOT", "").strip()
    if er:
        return Path(er).expanduser()
    return Path(load_merge_config(Path(".")).log_root).expanduser()


def _try_lock(root: Path) -> Any | None:
    if fcntl is None:
        return _NO_FCNTL
    qa = root.expanduser() / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    fp = open(qa / ".merge_run.lock", "w")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fp.close()
        return None
    return fp


def _unlock(fp: Any | None) -> None:
    if fp is None or fp is _NO_FCNTL or fcntl is None:
        return
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fp.close()
    except OSError:
        pass


def main() -> int:
    try:
        quit_anki()
    except Exception as exc:
        print(f"warning: failed to quit Anki: {exc}", file=sys.stderr)
        return 1

    root = _resolve_log_root()
    if not str(root).strip():
        print("error: log_root missing or empty (settings.yaml paths.log_root)", file=sys.stderr)
        return 1

    cfg = load_merge_config(root)
    lock_fp = _try_lock(root)
    if lock_fp is None:
        print("[merge] skipped: lock held", flush=True)
        return 0

    try:
        stats = run_morning(root, cfg=cfg)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        _unlock(lock_fp)

    print(
        f"pull_updates={stats.get('pull_updates', 0)} "
        f"cleaned_applied={stats.get('cleaned_applied', 0)} "
        f"cleaned_skipped_deleted={stats.get('cleaned_skipped_deleted', 0)} "
        f"cleaned_skipped_existing={stats.get('cleaned_skipped_existing', 0)} "
        f"cleaned_cleared={stats.get('cleaned_cleared', 0)} "
        f"anki_added={stats.get('anki_added', 0)} "
        f"anki_updated={stats.get('anki_updated', 0)} "
        f"anki_relinked={stats.get('anki_relinked', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
