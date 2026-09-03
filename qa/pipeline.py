"""Morning job: pull Anki (source of truth) → merge latest cleaned JSONL → push → git snapshots.

File ownership in the flashcards repo (kept disjoint so ``git pull --rebase`` never conflicts):

* Local-only writers (``extract_todo`` / ``merge``):
  ``chatgpt/*``, ``claude/*``, ``qa/.extract_todo_last_success``,
  ``qa/cards.jsonl``, ``qa/merged.json``, ``qa/last_sync.txt``,
  ``qa/current_cards/*``, ``qa/history/*``, and additions under ``qa/todo/``.
* Remote-only writer (GitHub ``nightly_cleanup``):
  ``qa/cleaned/*`` and ``qa/cleaned/.rotation.json``.
* Local-only deleter (this morning job):
  ``qa/cleaned/*`` (after applying to Anki) and the matching ``qa/todo/*.jsonl``
  entries (so the same day is not re-cleaned forever).

The nightly cleanup must NOT delete ``qa/todo/*`` — that is reserved for this
job, which only deletes a todo file once its cleaned counterpart has been
consumed locally.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment, misc]

from collection_apy import (
    apy_add_note,
    apy_update_note_fields,
    deck_exists,
    fetch_notes_info,
    find_note_ids,
    open_collection,
)
from backup_repo_sync import sync_qa_pairs_deck
from config import MergeConfig, load_merge_config
from hashing import deck_slug, qa_deck_dir, qa_deck_relpath, q_front_key, q_hash
from merged_ledger import load_merged_hashes, save_merged_hashes
from jsonl_store import cards_jsonl_path, load_latest_cleaned_cards, write_cards_jsonl_atomic
from parse_qa import markdown_back
from state import write_last_sync_epoch


DEFAULT_QA_FLASHCARDS_REPO = Path.home() / "projects" / "anki-cards"


def _field_value(fields: Any, name: str) -> str:
    if not isinstance(fields, dict):
        return ""
    cell = fields.get(name)
    if isinstance(cell, dict):
        return str(cell.get("value") or "")
    if isinstance(cell, str):
        return cell
    return ""


def _desired_back(rec: dict[str, Any]) -> str:
    if rec.get("answerBack") is not None:
        return str(rec.get("answerBack") or "")
    bullets = rec.get("answerBullets")
    if isinstance(bullets, list):
        return markdown_back([str(b) for b in bullets])
    return ""


def _as_int_note_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _hash_seen(qh: str, hashes: set[str]) -> bool:
    h = str(qh or "").strip().lower()
    return bool(h) and (h in hashes or h[:16] in hashes)


def pull_from_anki(
    a: Any,
    deck: str,
    merged_hashes: set[str],
) -> tuple[dict[str, dict[str, Any]], int]:
    note_ids = find_note_ids(a, f'deck:"{deck}" tag:qa-import') or find_note_ids(
        a,
        f"deck:{deck} tag:qa-import",
    )
    cards: dict[str, dict[str, Any]] = {}
    n = 0
    for i in range(0, len(note_ids), 200):
        chunk = note_ids[i : i + 200]
        for info in fetch_notes_info(a, chunk):
            fields = info.get("fields") or {}
            front = _field_value(fields, "Front")
            back = _field_value(fields, "Back")
            nid = int(info.get("noteId") or 0)
            mod = int(info.get("mod") or 0)
            if not nid or not front:
                continue

            qh = q_hash(front, back, info.get("tags"))
            merged_hashes.add(qh)
            n += 1
            prev = cards.get(qh)
            if isinstance(prev, dict) and int(prev.get("ankiMod") or 0) > mod:
                continue
            cards[qh] = {
                "qahash16": qh,
                "question": front,
                "answerBack": back,
                "ankiNoteId": nid,
                "ankiMod": mod,
                "source": "anki",
            }
    return cards, n


def apply_cleaned_cards(
    cards: dict[str, dict[str, Any]],
    cleaned_cards: dict[str, dict[str, Any]],
    stats: dict[str, int],
    merged_hashes: set[str] | None = None,
) -> None:
    applied = 0
    skipped_deleted = 0
    skipped_existing = 0
    previously_merged = merged_hashes or set()
    existing_fronts = {
        q_front_key(str(rec.get("question") or ""))
        for rec in cards.values()
        if str(rec.get("question") or "").strip()
    }
    for rec in cleaned_cards.values():
        question = str(rec.get("question") or "").strip()
        back = str(rec.get("answerBack") or "").strip()
        if not question or not back:
            continue
        qh = q_hash(question, back, ["qa-import"])
        front = q_front_key(question)
        if front in existing_fronts:
            # Anki already has this question (possibly with a user-edited answer).
            skipped_existing += 1
            continue
        if _hash_seen(qh, previously_merged) and qh not in cards:
            skipped_deleted += 1
            continue
        merged = dict(cards.get(qh) or {})
        merged.update(
            {
                "qahash16": qh,
                "question": question,
                "answerBack": back,
                "source": "cleaned",
            }
        )
        merged.pop("answerBullets", None)
        cards[qh] = merged
        existing_fronts.add(front)
        applied += 1
    stats["cleaned_applied"] = applied
    stats["cleaned_skipped_deleted"] = skipped_deleted
    stats["cleaned_skipped_existing"] = skipped_existing


def push_cards_to_anki(
    a: Any,
    deck: str,
    model: str,
    cards: dict[str, dict[str, Any]],
    stats: dict[str, int],
) -> set[str]:
    synced: set[str] = set()
    for qh in sorted(cards.keys()):
        rec = cards[qh]
        front = str(rec.get("question") or "").strip()
        back = _desired_back(rec).strip()
        if not front or not back:
            continue
        qh = q_hash(front, back, ["qa-import"])
        rec["qahash16"] = qh
        tag = f"qahash-{qh}"
        nid = _as_int_note_id(rec.get("ankiNoteId"))

        if nid:
            infos = fetch_notes_info(a, [nid])
            if not infos:
                nid = 0
            else:
                inf = infos[0]
                cur_f = _field_value(inf.get("fields"), "Front").strip()
                cur_b = _field_value(inf.get("fields"), "Back").strip()
                needs_update = cur_f != front or cur_b != back
                if needs_update:
                    stats["anki_updated"] = stats.get("anki_updated", 0) + 1
                    apy_update_note_fields(a, nid, front, back)
                    infos2 = fetch_notes_info(a, [nid])
                    if infos2:
                        rec["ankiMod"] = int(infos2[0].get("mod") or 0)
                synced.add(q_hash(front, back, inf.get("tags")))
                continue

        found = find_note_ids(a, f'deck:"{deck}" tag:{tag}')
        if found:
            nid = _as_int_note_id(found[0])
            stats["anki_relinked"] = stats.get("anki_relinked", 0) + 1
            infos = fetch_notes_info(a, [nid]) if nid else []
            cur_f = _field_value(infos[0].get("fields"), "Front").strip() if infos else ""
            cur_b = _field_value(infos[0].get("fields"), "Back").strip() if infos else ""
            needs_update = bool(infos) and (cur_f != front or cur_b != back)
            if needs_update:
                stats["anki_updated"] = stats.get("anki_updated", 0) + 1
            rec["ankiNoteId"] = nid
            if infos:
                rec["ankiMod"] = int(infos[0].get("mod") or 0)
            if needs_update:
                apy_update_note_fields(a, nid, front, back)
                infos2 = fetch_notes_info(a, [nid])
                if infos2:
                    rec["ankiMod"] = int(infos2[0].get("mod") or 0)
            synced.add(q_hash(front, back, infos[0].get("tags") if infos else ["qa-import"]))
            continue

        stats["anki_added"] = stats.get("anki_added", 0) + 1
        new_id = apy_add_note(
            a,
            deck,
            model,
            front,
            back,
            ["qa-import", tag],
        )
        rec["ankiNoteId"] = new_id
        infos = fetch_notes_info(a, [new_id])
        if infos:
            rec["ankiMod"] = int(infos[0].get("mod") or 0)
        synced.add(q_hash(front, back, ["qa-import"]))

    return synced


def _git_snapshot_targets(root: Path, cfg: MergeConfig) -> tuple[Path | None, list[str]]:
    """Return ``(repo_root, paths_relative_to_repo)`` for ``git add`` (files or one deck directory)."""
    root_r = root.expanduser().resolve()
    override = (cfg.git_repo or "").strip()
    if override:
        repo = Path(override).expanduser().resolve()
        if not (repo / ".git").is_dir():
            return None, []
        return repo, [qa_deck_relpath(cfg)]
    repo = root_r
    if not (repo / ".git").is_dir():
        return None, []
    try:
        rel = root_r.relative_to(repo)
    except ValueError:
        return None, []
    prefix = (Path(rel) / "qa").as_posix()
    return repo, [f"{prefix}/cards.jsonl", f"{prefix}/last_sync.txt", f"{prefix}/merged.json"]


def _resolve_flashcards_repo(cfg: MergeConfig) -> Path | None:
    """Return configured repo root, with qa_flashcards default fallback when available."""
    override = (cfg.git_repo or "").strip()
    candidates = [Path(override)] if override else [DEFAULT_QA_FLASHCARDS_REPO]
    for cand in candidates:
        repo = cand.expanduser().resolve()
        if (repo / ".git").is_dir():
            return repo
    return None


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _current_branch(repo: Path) -> str:
    r = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = (r.stdout or "").strip()
    return "" if not branch or branch == "HEAD" else branch


def ahead_behind(repo: Path, branch: str | None = None) -> tuple[int, int]:
    """Return ``(ahead, behind)`` vs ``origin/<branch>``. ``(-1, -1)`` if unknown."""
    br = branch or _current_branch(repo)
    if not br:
        return -1, -1
    r = _run_git(repo, "rev-list", "--left-right", "--count", f"origin/{br}...HEAD")
    if r.returncode != 0:
        return -1, -1
    parts = (r.stdout or "").strip().split()
    if len(parts) != 2:
        return -1, -1
    try:
        behind, ahead = int(parts[0]), int(parts[1])
    except ValueError:
        return -1, -1
    return ahead, behind


def abort_inflight_git_state(repo: Path) -> None:
    """Abort any in-progress rebase/merge/cherry-pick so pulls can proceed cleanly.

    Without this, a previous run that died mid-rebase would leave ``.git/rebase-merge``
    around and every subsequent ``git pull`` would refuse to run. We always start
    pulls from a clean state so the pipeline can self-recover.
    """
    g = repo / ".git"
    if not g.is_dir():
        return
    if (g / "rebase-merge").is_dir() or (g / "rebase-apply").is_dir():
        subprocess.run(
            ["git", "-C", str(repo), "rebase", "--abort"], capture_output=True, check=False
        )
    if (g / "MERGE_HEAD").is_file():
        subprocess.run(
            ["git", "-C", str(repo), "merge", "--abort"], capture_output=True, check=False
        )
    if (g / "CHERRY_PICK_HEAD").is_file():
        subprocess.run(
            ["git", "-C", str(repo), "cherry-pick", "--abort"],
            capture_output=True,
            check=False,
        )


def _integrate_remote(repo: Path) -> bool:
    """Fetch and fast-forward or rebase onto origin. Never leaves a mid-rebase."""
    abort_inflight_git_state(repo)
    fetched = _run_git(repo, "fetch", "origin")
    if fetched.returncode != 0:
        print(f"[git] fetch failed for {repo}", flush=True)
    abort_inflight_git_state(repo)
    if _run_git(repo, "pull", "--ff-only", "--autostash").returncode == 0:
        return True
    if _run_git(repo, "pull", "--rebase", "--autostash").returncode == 0:
        return True
    _run_git(repo, "rebase", "--abort")
    branch = _current_branch(repo)
    if branch and _run_git(repo, "rebase", "--autostash", f"origin/{branch}").returncode == 0:
        return True
    _run_git(repo, "rebase", "--abort")
    print(f"[git] pull failed for {repo}; aborted rebase to keep repo clean", flush=True)
    return False


def _push_if_ahead(repo: Path) -> bool:
    branch = _current_branch(repo)
    ahead, behind = ahead_behind(repo, branch)
    if ahead < 0:
        return False
    if behind > 0:
        print(f"[git] still behind={behind} ahead={ahead} for {repo}; not pushing", flush=True)
        return False
    if ahead == 0:
        return True
    dest = f"HEAD:{branch}" if branch else "HEAD"
    pushed = _run_git(repo, "push", "origin", dest)
    if pushed.returncode != 0:
        err = (pushed.stderr or "").strip()
        print(f"[git] push failed for {repo} ahead={ahead}: {err}", flush=True)
        return False
    print(f"[git] pushed {ahead} local commit(s) for {repo}", flush=True)
    return True


def heal_repo(repo: Path) -> bool:
    """Fetch + rebase remote commits, then push leftover local commits.

    This is what stops ``ahead 1, behind 75``: a failed morning snapshot used to
    skip both commit and push, then nightly kept adding remote commits. Heal is
    also run on the 15-minute extract tick even when extract itself is skipped.
    """
    repo = Path(repo)
    if not (repo / ".git").is_dir():
        return False

    def _heal() -> bool:
        ok = _integrate_remote(repo)
        ahead, behind = ahead_behind(repo)
        if ahead > 0 or behind > 0:
            print(f"[git] {repo.name} ahead={ahead} behind={behind}", flush=True)
        if not ok:
            return False
        return _push_if_ahead(repo)

    if fcntl is None:
        return _heal()
    lock_path = repo / ".git" / "qa-heal.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fp:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
            return _heal()
        finally:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def heal_configured_repo(root: Path | None = None) -> bool:
    """Heal ``READ_CHAT_GUI_GIT_REPO`` (no-op if unset / missing)."""
    cfg = load_merge_config(root or Path("."))
    repo = _resolve_flashcards_repo(cfg)
    if repo is None:
        return True
    return heal_repo(repo)


def safe_pull(repo: Path) -> bool:
    """Best-effort pull (ff-only → rebase). Aborts a failed rebase before returning."""
    return _integrate_remote(repo)


def _pull_cleaned_repo(cfg: MergeConfig) -> Path | None:
    """Pull latest remote state so cleaned cards are up to date before merge."""
    repo = _resolve_flashcards_repo(cfg)
    if repo is None:
        return None
    heal_repo(repo)
    return repo


def _load_cleaned_cards_for_merge(root: Path, cfg: MergeConfig, repo: Path | None) -> dict[str, dict[str, Any]]:
    """Prefer cleaned JSONL from pulled flashcards repo deck path, fallback to local root."""
    if repo is not None:
        repo_deck_root = qa_deck_dir(repo, cfg)
        repo_cards = load_latest_cleaned_cards(repo_deck_root, cfg.cleaned_subdir)
        if repo_cards:
            return repo_cards
    return load_latest_cleaned_cards(root, cfg.cleaned_subdir)


def _clear_processed_jsonl(root: Path, cfg: MergeConfig, repo: Path | None) -> int:
    """Delete consumed cleaned JSONL files plus their matching todo siblings.

    Cleaned files are produced remotely by nightly cleanup; this job consumes
    them and is the *only* caller allowed to remove them. We also remove the
    todo file with the same day stem, because that day has now been pushed to
    Anki and re-cleaning it would just duplicate work. The deletion is the
    single source of truth for "this day is done" — nightly cleanup must not
    delete todo files itself, otherwise local extract pushes can collide with
    remote deletions during ``git pull --rebase``.
    """
    cleaned_dirs: list[Path] = [Path(root).expanduser() / cfg.cleaned_subdir]
    todo_dirs: list[Path] = [Path(root).expanduser() / cfg.todo_subdir]
    if repo is not None:
        repo_deck_root = qa_deck_dir(repo, cfg)
        cleaned_dirs.append(repo_deck_root / cfg.cleaned_subdir)
        todo_dirs.append(repo_deck_root / cfg.todo_subdir)

    removed = 0
    cleaned_stems: set[str] = set()
    seen_cleaned: set[Path] = set()
    for target in cleaned_dirs:
        tgt = target.expanduser().resolve()
        if tgt in seen_cleaned or not tgt.is_dir():
            continue
        seen_cleaned.add(tgt)
        for p in tgt.glob("*.jsonl"):
            cleaned_stems.add(p.stem)
            p.unlink(missing_ok=True)
            removed += 1

    seen_todo: set[Path] = set()
    for target in todo_dirs:
        tgt = target.expanduser().resolve()
        if tgt in seen_todo or not tgt.is_dir():
            continue
        seen_todo.add(tgt)
        for p in tgt.glob("*.jsonl"):
            if p.stem in cleaned_stems:
                p.unlink(missing_ok=True)
                removed += 1
    return removed


def git_snapshot(
    root: Path,
    message: str,
    *,
    cfg: MergeConfig,
    a: Any | None = None,
) -> None:
    """Heal remote, commit local snapshot even if pull failed, then heal/push again."""
    git_repo, rel_paths = _git_snapshot_targets(root, cfg)
    if git_repo is None or not rel_paths:
        return
    if not heal_repo(git_repo):
        print(f"[git] heal failed for {git_repo}; still committing local snapshot", flush=True)
    if (cfg.git_repo or "").strip() and a is not None:
        sync_qa_pairs_deck(git_repo, a, cfg)
    existing = [p for p in rel_paths if (git_repo / p).is_dir() or (git_repo / p).is_file()]
    if not existing:
        return
    subprocess.run(
        ["git", "-C", str(git_repo), "add", "--all", "--"] + existing,
        capture_output=True,
        check=False,
    )
    st = subprocess.run(
        ["git", "-C", str(git_repo), "diff", "--cached", "--quiet"],
        capture_output=True,
        check=False,
    )
    if st.returncode != 0:
        subprocess.run(["git", "-C", str(git_repo), "commit", "-m", message], capture_output=True, check=False)
    heal_repo(git_repo)


def run_morning(root: Path, *, cfg: MergeConfig | None = None) -> dict[str, int]:
    root = Path(root).expanduser()
    if cfg is None:
        cfg = load_merge_config(root)

    # Step 1: pull latest remote cleaned cards before opening Anki/merge stages.
    cleaned_repo = _pull_cleaned_repo(cfg)

    jsonl_path = cards_jsonl_path(root)
    merged_hashes = load_merged_hashes(root)

    stats: dict[str, int] = {
        "pull_updates": 0,
        "cleaned_applied": 0,
        "anki_added": 0,
        "anki_updated": 0,
        "anki_relinked": 0,
    }

    profile = cfg.apy_profile_name.strip() or None
    with open_collection(cfg.apy_base_path, profile) as a:
        if not deck_exists(a, cfg.anki_deck):
            raise RuntimeError(f"anki deck not found: {cfg.anki_deck!r}")

        cards, stats["pull_updates"] = pull_from_anki(a, cfg.anki_deck, merged_hashes)
        write_cards_jsonl_atomic(jsonl_path, cards)
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        git_snapshot(root, f"backup_date_{stamp}", cfg=cfg, a=a)

        cleaned_cards = _load_cleaned_cards_for_merge(root, cfg, cleaned_repo)
        apply_cleaned_cards(cards, cleaned_cards, stats, merged_hashes)
        pushed = push_cards_to_anki(a, cfg.anki_deck, cfg.anki_model, cards, stats)
        merged_hashes.update(pushed)
        stats["cleaned_cleared"] = _clear_processed_jsonl(root, cfg, cleaned_repo)

        write_cards_jsonl_atomic(jsonl_path, cards)
        git_snapshot(root, f"merged_date_{stamp}", cfg=cfg, a=a)
        save_merged_hashes(root, merged_hashes)
        write_last_sync_epoch(root, int(time.time()))

    return stats
