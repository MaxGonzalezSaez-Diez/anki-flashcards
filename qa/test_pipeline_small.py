#!/usr/bin/env python3
"""Run small dry-run tester using defaults from qa/.env."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobs import main_test


def main() -> int:
    return main_test()


if __name__ == "__main__":
    raise SystemExit(main())
