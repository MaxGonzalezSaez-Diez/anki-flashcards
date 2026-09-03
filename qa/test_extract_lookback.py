#!/usr/bin/env python3
"""Extract lookback + skip-already-done hashes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hashing import q_hash
from jobs import run_extract
from jsonl_store import load_jsonl_rows
from merged_ledger import save_merged_hashes
from pipeline import apply_cleaned_cards


def _write_day(root: Path, site: str, day: str, text: str) -> None:
    path = root / site / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "site": site,
                "date": day,
                "events": [
                    {
                        "eventId": f"{day}-1",
                        "tsIso": f"{day}T23:00:00.000Z",
                        "site": site,
                        "role": "assistant",
                        "text": text,
                        "extractionMode": "structured",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class ExtractLookbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        os.environ["READ_CHAT_GUI_GIT_REPO"] = ""
        os.environ["READ_CHAT_GUI_EXTRACT_NO_GIT"] = "true"
        os.environ["READ_CHAT_GUI_LOOKBACK_DAYS"] = "7"
        os.environ["READ_CHAT_GUI_TODO_SUBDIR"] = "qa/todo"
        os.environ["READ_CHAT_GUI_CLEANED_SUBDIR"] = "qa/cleaned"
        os.environ["ANKI_DECK"] = "Ai-Convo-QA"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lookback_picks_older_day_once(self) -> None:
        older = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
        qa = (
            "QQQ: What is a unique lookback test question?\n"
            "AAA:\n- Unique lookback test answer.\n"
        )
        _write_day(self.root, "claude", older, qa)

        first = run_extract(self.root)
        self.assertEqual(first, 1)
        second = run_extract(self.root)
        self.assertEqual(second, 0)

        todo_files = list((self.root / "qa" / "todo").glob("*.jsonl"))
        self.assertEqual(len(todo_files), 1)
        rows = load_jsonl_rows(todo_files[0])
        self.assertEqual(len(rows), 1)
        self.assertIn("unique lookback test question", rows[0]["question"].lower())

    def test_skips_same_question_with_different_answer(self) -> None:
        older = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
        q = "What are the key methodological components of RECAP in test?"
        _write_day(self.root, "claude", older, f"QQQ: {q}\nAAA:\n- Raw log answer with a link.\n")
        (self.root / "qa").mkdir(parents=True, exist_ok=True)
        cards = self.root / "qa" / "cards.jsonl"
        cards.write_text(
            json.dumps(
                {
                    "qahash16": q_hash(q, "- Edited Anki answer without the link.", ["qa-import"]),
                    "question": q,
                    "answerBack": "- Edited Anki answer without the link.",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        added = run_extract(self.root)
        self.assertEqual(added, 0)

    def test_skips_already_merged_hash(self) -> None:
        older = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
        q = "What is an already-merged lookback question?"
        back = "- Already merged answer."
        _write_day(self.root, "claude", older, f"QQQ: {q}\nAAA:\n{back}\n")
        save_merged_hashes(self.root, {q_hash(q, back, ["qa-import"])})

        added = run_extract(self.root)
        self.assertEqual(added, 0)
        todo_files = list((self.root / "qa" / "todo").glob("*.jsonl"))
        self.assertTrue(todo_files)
        self.assertEqual(load_jsonl_rows(todo_files[0]), [])


class ApplyCleanedExistingFrontTests(unittest.TestCase):
    def test_does_not_overwrite_anki_answer_for_same_question(self) -> None:
        q = "What are the key methodological components of RECAP in test?"
        anki_back = "- Edited Anki answer without the link."
        cleaned_back = "- Raw cleaned answer with a link."
        anki_h = q_hash(q, anki_back, ["qa-import"])
        cards = {
            anki_h: {
                "qahash16": anki_h,
                "question": q,
                "answerBack": anki_back,
                "source": "anki",
            }
        }
        cleaned_h = q_hash(q, cleaned_back, ["qa-import"])
        stats: dict[str, int] = {}
        apply_cleaned_cards(
            cards,
            {cleaned_h: {"question": q, "answerBack": cleaned_back}},
            stats,
            merged_hashes=set(),
        )
        self.assertEqual(stats.get("cleaned_skipped_existing"), 1)
        self.assertEqual(stats.get("cleaned_applied"), 0)
        self.assertEqual(cards[anki_h]["answerBack"], anki_back)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
