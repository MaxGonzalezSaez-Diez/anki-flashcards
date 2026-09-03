#!/usr/bin/env python3
"""LaunchAgent entry for extract_todo: run once per missed schedule slot (3pm/6pm/9pm local)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment, misc]

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_qa_dotenv
from jobs import _resolve_root, extract_gate_should_run, main_extract
from pipeline import heal_configured_repo

_NO_FCNTL = object()


def _try_lock(root: Path) -> Any | None:
    if fcntl is None:
        return _NO_FCNTL
    qa = root.expanduser() / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    fp = open(qa / ".extract_todo_launch.lock", "w")
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", help="override READ_CHAT_GUI_LOG_ROOT")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    load_qa_dotenv()
    if args.root:
        os.environ["READ_CHAT_GUI_LOG_ROOT"] = args.root.strip()

    root = _resolve_root()
    lock_fp = _try_lock(root)
    if lock_fp is None:
        return 0

    try:
        # Every 15-minute tick: rebase leftover local commits onto nightly
        # cleaned commits and push. Do this even when extract itself is skipped.
        heal_configured_repo(root)
        if not extract_gate_should_run(root, force=args.force):
            return 0
        return main_extract()
    finally:
        _unlock(lock_fp)


if __name__ == "__main__":
    raise SystemExit(main())
