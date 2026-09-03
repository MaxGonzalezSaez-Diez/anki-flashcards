#!/usr/bin/env python3
"""heal_repo rebases a local-only commit onto remote-only cleaned commits."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import ahead_behind, heal_repo


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _git_init_identity(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


class HealRepoTests(unittest.TestCase):
    def test_rebases_diverged_local_and_remote_and_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin = root / "origin.git"
            local = root / "local"
            remote_writer = root / "nightly"

            subprocess.run(["git", "init", "-b", "main", "--bare", str(origin)], check=True)
            subprocess.run(["git", "clone", str(origin), str(local)], check=True)
            _git_init_identity(local)
            (local / "readme.txt").write_text("base\n", encoding="utf-8")
            _git(local, "add", "readme.txt")
            _git(local, "commit", "-m", "base")
            _git(local, "push", "-u", "origin", "HEAD")

            subprocess.run(["git", "clone", str(origin), str(remote_writer)], check=True)
            _git_init_identity(remote_writer)
            cleaned = remote_writer / "qa" / "cleaned"
            cleaned.mkdir(parents=True)
            (cleaned / "2026-08-16.jsonl").write_text("{}\n", encoding="utf-8")
            _git(remote_writer, "add", "qa/cleaned/2026-08-16.jsonl")
            _git(remote_writer, "commit", "-m", "nightly_cleanup 20260816")
            _git(remote_writer, "push")

            cards = local / "qa" / "current_cards"
            cards.mkdir(parents=True)
            (cards / "current_state.jsonl").write_text("{}\n", encoding="utf-8")
            _git(local, "add", "qa/current_cards/current_state.jsonl")
            _git(local, "commit", "-m", "backup_date_local")
            (local / "qa" / "last_sync.txt").write_text("dirty\n", encoding="utf-8")

            _git(local, "fetch", "origin")
            ahead, behind = ahead_behind(local)
            self.assertEqual((ahead, behind), (1, 1))

            self.assertTrue(heal_repo(local))
            self.assertEqual(ahead_behind(local), (0, 0))
            self.assertEqual((local / "qa" / "last_sync.txt").read_text(encoding="utf-8"), "dirty\n")
            self.assertTrue((local / "qa" / "cleaned" / "2026-08-16.jsonl").is_file())
            self.assertTrue((local / "qa" / "current_cards" / "current_state.jsonl").is_file())

            log = _git(local, "log", "--oneline", "--reverse").stdout
            self.assertIn("nightly_cleanup", log)
            self.assertIn("backup_date_local", log)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
