#!/usr/bin/env python3
"""Run nightly cleanup job using settings.yaml + .env."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobs import main_cleanup


if __name__ == "__main__":
    raise SystemExit(main_cleanup())
