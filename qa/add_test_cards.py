#!/usr/bin/env python3
"""Add one custom note for local testing. Anki must be quit; uses ``qa/.env`` like merge.

  cd "$(dirname "$0")" && python3 add_test_cards.py
  python3 add_test_cards.py --front 'Q?' --back '- A' --deck 'My Deck'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_QA = Path(__file__).resolve().parent
if str(_QA) not in sys.path:
    sys.path.insert(0, str(_QA))

from collection_apy import apy_add_note, deck_exists, open_collection
from config import load_merge_config, load_qa_dotenv


def main() -> None:
    load_qa_dotenv()
    cfg = load_merge_config(_QA)
    ap = argparse.ArgumentParser(description="Add a single Anki note (smoke test).")
    ap.add_argument("--deck", default=cfg.anki_deck)
    ap.add_argument("--model", default=cfg.anki_model)
    ap.add_argument("--front", default="read_chat_gui test card")
    ap.add_argument("--back", default="- **answer** line")
    ap.add_argument("--tags", default="qa-import read-chat-gui-test", help="space-separated")
    args = ap.parse_args()
    tags = [t for t in args.tags.split() if t]

    profile = cfg.apy_profile_name.strip() or None
    with open_collection(cfg.apy_base_path, profile) as a:
        if not deck_exists(a, args.deck):
            raise SystemExit(f"deck not found: {args.deck!r}")
        nid = apy_add_note(a, args.deck, args.model, args.front, args.back, tags)
    print(nid)


if __name__ == "__main__":
    main()
