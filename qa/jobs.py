"""Small job runners for extract, nightly cleanup, and dry-run testing (env-driven, no argparse)."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from config import load_merge_config, load_qa_dotenv
from event_io import iter_assistant_structured_events_range, utc_day_strings_ending_today
from hashing import deck_slug, q_front_key, q_hash
from jsonl_store import cards_jsonl_path, load_jsonl_rows, write_jsonl_rows_atomic
from merged_ledger import load_merged_hashes
from parse_qa import markdown_back, parse_qa
from pipeline import apply_cleaned_cards, heal_repo



def _resolve_root() -> Path:
    er = os.environ.get("READ_CHAT_GUI_LOG_ROOT", "").strip()
    if er:
        return Path(er).expanduser().resolve()
    return Path(load_merge_config(Path(".")).log_root).expanduser().resolve()


_EXTRACT_LAST_SUCCESS = ".extract_todo_last_success"
_EXTRACT_DEBOUNCE_SEC = 120


def extract_last_success_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "qa" / _EXTRACT_LAST_SUCCESS


def read_extract_last_success(root: Path) -> datetime | None:
    p = extract_last_success_path(root)
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8").strip().splitlines()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[0].strip())
    except ValueError:
        return None


def write_extract_last_success(root: Path, when: datetime | None = None) -> None:
    dt = when or datetime.now().astimezone()
    p = extract_last_success_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dt.isoformat() + "\n", encoding="utf-8")


def missed_scheduled_slots_since(
    last: datetime | None,
    now: datetime,
    slots: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None,
) -> bool:
    """True if at least one scheduled extract time passed strictly after ``last`` and before ``now``."""
    if last is None:
        return True
    tz = now.tzinfo
    if tz is None:
        raise ValueError("now must be timezone-aware")
    if last.tzinfo is None:
        last = last.replace(tzinfo=tz)
    last = last.astimezone(tz)
    now = now.astimezone(tz)
    if not slots:
        slots = load_merge_config(Path(".")).extract_slots
    d = last.date()
    end_d = now.date()
    while d <= end_d:
        for hour, minute in slots:
            slot = datetime.combine(d, dt_time(hour, minute), tzinfo=tz)
            if last < slot < now:
                return True
        d = d + timedelta(days=1)
    return False


def extract_gate_should_run(root: Path, *, force: bool = False) -> bool:
    """Whether to run extract now (missed slot catch-up or ``force``). Call under extract launch lock."""
    if force:
        return True
    last = read_extract_last_success(root)
    now = datetime.now().astimezone()
    if last is not None:
        tz = now.tzinfo
        if last.tzinfo is None:
            last = last.replace(tzinfo=tz)
        last = last.astimezone(tz)
        if (now - last).total_seconds() < _EXTRACT_DEBOUNCE_SEC:
            return False
    slots = load_merge_config(root).extract_slots
    return missed_scheduled_slots_since(last, now, slots)


def _git_sync_push(repo: Path, rel: str, message: str) -> bool:
    """Heal remote, commit local path even if pull failed, then heal/push again."""
    heal_repo(repo)
    subprocess.run(["git", "-C", str(repo), "add", "--", rel], capture_output=True, check=False)
    st = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"], capture_output=True, check=False)
    if st.returncode != 0:
        subprocess.run(["git", "-C", str(repo), "commit", "-m", message], capture_output=True, check=False)
    return heal_repo(repo)


def _add_seen_hash(raw_hash: str, seen_full: set[str], seen_short: set[str]) -> None:
    h = str(raw_hash or "").strip().lower()
    if not h:
        return
    if len(h) >= 32:
        seen_full.add(h[:32])
        seen_short.add(h[:16])
        return
    if len(h) >= 16:
        seen_short.add(h[:16])


def _prepull_extract_repo(cfg) -> tuple[Path | None, bool]:
    repo_s = str(cfg.git_repo or "").strip()
    if not repo_s:
        return None, False
    repo = Path(repo_s).expanduser().resolve()
    if not (repo / ".git").is_dir():
        return None, False
    return repo, heal_repo(repo)


def _history_all_hashes_path(cfg, repo: Path | None) -> Path | None:
    if repo is None:
        return None
    sub = (cfg.git_qa_subdir or "qa_pairs").strip().strip("/\\").replace("\\", "/")
    return repo / sub / deck_slug(cfg.anki_deck) / "history" / "all_hashes.jsonl"


def _deck_root(cfg, repo: Path | None) -> Path | None:
    if repo is None:
        return None
    sub = (cfg.git_qa_subdir or "qa_pairs").strip().strip("/\\").replace("\\", "/")
    return repo / sub / deck_slug(cfg.anki_deck)


def _add_seen_from_row(
    row: dict,
    seen_full: set[str],
    seen_short: set[str],
    seen_fronts: set[str],
) -> None:
    _add_seen_hash(str(row.get("qahash") or row.get("qahash16") or ""), seen_full, seen_short)
    q = str(row.get("question") or "").strip()
    if q:
        seen_fronts.add(q_front_key(q))
    b = str(row.get("answerBack") or "").strip()
    if not q or not b:
        return
    tags = row.get("tags")
    _add_seen_hash(q_hash(q, b, tags if tags is not None else ["qa-import"]), seen_full, seen_short)


def _seed_seen_from_jsonl_files(
    paths: list[Path],
    seen_full: set[str],
    seen_short: set[str],
    seen_fronts: set[str],
) -> None:
    for path in paths:
        for row in load_jsonl_rows(path):
            if isinstance(row, dict):
                _add_seen_from_row(row, seen_full, seen_short, seen_fronts)


def _seed_seen_from_root(
    root: Path,
    cfg,
    seen_full: set[str],
    seen_short: set[str],
    seen_fronts: set[str],
) -> None:
    """Skip anything already queued, cleaned, or merged under the log root."""
    root = Path(root).expanduser()
    todo_dir = root / cfg.todo_subdir
    cleaned_dir = root / cfg.cleaned_subdir
    if todo_dir.is_dir():
        _seed_seen_from_jsonl_files(
            sorted(todo_dir.glob("*.jsonl")), seen_full, seen_short, seen_fronts
        )
    if cleaned_dir.is_dir():
        _seed_seen_from_jsonl_files(
            sorted(cleaned_dir.glob("*.jsonl")), seen_full, seen_short, seen_fronts
        )
    cards_path = cards_jsonl_path(root)
    if cards_path.is_file():
        _seed_seen_from_jsonl_files([cards_path], seen_full, seen_short, seen_fronts)
    for h in load_merged_hashes(root):
        _add_seen_hash(h, seen_full, seen_short)


def _seed_seen_from_deck_rows(
    cfg,
    repo: Path | None,
    seen_full: set[str],
    seen_short: set[str],
    seen_fronts: set[str],
) -> None:
    deck_root = _deck_root(cfg, repo)
    if deck_root is None:
        return

    current_dir = deck_root / "current_cards"
    history_dir = deck_root / "history"

    if current_dir.is_dir():
        _seed_seen_from_jsonl_files(
            [current_dir / "current_state.jsonl", *sorted(current_dir.glob("cards-*.jsonl"))],
            seen_full,
            seen_short,
            seen_fronts,
        )

    if history_dir.is_dir():
        _seed_seen_from_jsonl_files(
            sorted(history_dir.glob("cards-*.jsonl")), seen_full, seen_short, seen_fronts
        )

    _seed_seen_from_root(deck_root, cfg, seen_full, seen_short, seen_fronts)


def _load_remote_all_hashes(cfg, repo: Path | None) -> list[str]:
    if repo is None:
        return []
    sub = (cfg.git_qa_subdir or "qa_pairs").strip().strip("/\\").replace("\\", "/")
    rel = f"{sub}/{deck_slug(cfg.anki_deck)}/history/all_hashes.jsonl"
    rb = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    branch = (rb.stdout or "").strip() if rb.returncode == 0 else ""
    if not branch:
        return []
    rs = subprocess.run(
        ["git", "-C", str(repo), "show", f"origin/{branch}:{rel}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rs.returncode != 0:
        return []
    out: list[str] = []
    for line in rs.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        h = str(obj.get("qahash") or obj.get("qahash16") or "").strip().lower()
        if h:
            out.append(h)
    return out


def run_extract(root: Path) -> int:
    cfg = load_merge_config(root)
    repo, pulled_ok = _prepull_extract_repo(cfg)
    tz = ZoneInfo(cfg.schedule_tz)
    day_local = datetime.now(tz).date().isoformat()

    todo_dir = root / cfg.todo_subdir
    todo_dir.mkdir(parents=True, exist_ok=True)
    todo_path = todo_dir / f"{day_local}.jsonl"

    rows = load_jsonl_rows(todo_path)
    seen_full: set[str] = set()
    seen_short: set[str] = set()
    seen_fronts: set[str] = set()
    for r in rows:
        _add_seen_from_row(r, seen_full, seen_short, seen_fronts)

    _seed_seen_from_root(root, cfg, seen_full, seen_short, seen_fronts)
    _seed_seen_from_deck_rows(cfg, repo, seen_full, seen_short, seen_fronts)

    hist_path = _history_all_hashes_path(cfg, repo)
    if hist_path is not None and hist_path.is_file():
        for r in load_jsonl_rows(hist_path):
            _add_seen_hash(str(r.get("qahash") or r.get("qahash16") or ""), seen_full, seen_short)
    if not pulled_ok:
        for h in _load_remote_all_hashes(cfg, repo):
            _add_seen_hash(h, seen_full, seen_short)

    added = 0
    lookback = max(1, int(cfg.extract_lookback_days))

    for _day_iso, site, event in iter_assistant_structured_events_range(
        root, utc_day_strings_ending_today(lookback)
    ):
        text = str(event.get("text") or "")
        for q, bullets in parse_qa(text):
            back = markdown_back([str(b) for b in bullets])
            qh = q_hash(q, back, ["qa-import"])
            front = q_front_key(q)
            if qh in seen_full or qh[:16] in seen_short or front in seen_fronts:
                continue
            rows.append(
                {
                    "qahash16": qh,
                    "question": q,
                    "answerBack": back,
                    "site": site,
                    "eventId": str(event.get("eventId") or ""),
                    "tsIso": str(event.get("tsIso") or ""),
                    "status": "todo",
                }
            )
            _add_seen_hash(qh, seen_full, seen_short)
            seen_fronts.add(front)
            added += 1

    write_jsonl_rows_atomic(todo_path, rows)

    if not cfg.extract_no_git and cfg.git_repo:
        repo = Path(cfg.git_repo).expanduser().resolve()
        rel = str(todo_path.resolve().relative_to(repo)) if todo_path.resolve().is_relative_to(repo) else ""
        if rel:
            stamp = datetime.now(tz).strftime("%Y%m%d_%H%M")
            _git_sync_push(repo, rel, f"extract_date_{stamp}")

    return added


def _write_rotation(path: Path, idx: int, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "nextModelIndex": idx,
                "lastModel": model,
                "updatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _clean_one(
    question: str,
    answer_back: str,
    model: str,
    api_key: str,
    prompt_template: str,
) -> tuple[str, str]:
    template = (prompt_template or "").strip()
    if "{answer}" in template:
        prompt = template.replace("{answer}", answer_back)
    else:
        prompt = template + answer_back
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = str(raw["choices"][0]["message"].get("content") or "").strip()
    q = question.strip()
    b = str(content or answer_back).strip()
    return q or question, b or answer_back


def run_cleanup(root: Path, *, force_dry_run: bool | None = None) -> dict[str, int]:
    """Read each ``qa/todo/*.jsonl`` and write a cleaned counterpart in ``qa/cleaned/``.

    Intentionally leaves ``qa/todo/*.jsonl`` untouched so this job (typically run
    on GitHub) and local ``extract_todo`` write to a disjoint set of paths. The
    matching todo file is deleted by the morning merge once its cleaned form has
    been pushed to Anki — see ``pipeline._clear_processed_jsonl``.
    """
    cfg = load_merge_config(root)
    todo_dir = root / cfg.todo_subdir
    todo_files = sorted(todo_dir.glob("*.jsonl")) if todo_dir.is_dir() else []

    totals = {"input": 0, "cleaned": 0, "failed": 0}

    for todo_path in todo_files:
        day = todo_path.stem
        out_path = root / cfg.cleaned_subdir / f"{day}.jsonl"
        stats = _run_single_todo_cleanup(root, todo_path, out_path, cfg, force_dry_run)
        totals["input"] += stats["input"]
        totals["cleaned"] += stats["cleaned"]
        totals["failed"] += stats["failed"]

    return totals


def _run_single_todo_cleanup(
    root: Path,
    todo_path: Path,
    out_path: Path,
    cfg,
    force_dry_run: bool | None = None,
) -> dict[str, int]:
    rows = load_jsonl_rows(todo_path)
    models = [m for m in cfg.openrouter_models if m.strip()]
    if not models:
        return {"input": len(rows), "cleaned": 0, "failed": len(rows)}

    day = todo_path.stem
    rotation_path = root / cfg.openrouter_rotation_file
    sticky_idx = 0
    reset_every = max(1, int(cfg.openrouter_reset_every_n))
    successes_since_reset = 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    dry = cfg.cleanup_dry_run if force_dry_run is None else force_dry_run
    cleaned = 0
    failed = 0
    out_rows: list[dict] = []
    first_call = True

    for row in rows:
        q = str(row.get("question") or "").strip()
        b = str(row.get("answerBack") or "").strip()
        if not q or not b:
            continue
        cq, cb = q, b
        ok = False
        used_idx = sticky_idx

        for step in range(len(models)):
            idx = (sticky_idx + step) % len(models)
            model = models[idx]
            try:
                if dry:
                    ok = True
                    used_idx = idx
                    break
                if not api_key:
                    raise RuntimeError("OPENROUTER_API_KEY missing")
                if not first_call:
                    time.sleep(max(0, cfg.openrouter_sleep_seconds))
                first_call = False
                cq, cb = _clean_one(q, b, model, api_key, cfg.cleanup_prompt)
                ok = True
                used_idx = idx
                break
            except Exception:
                continue

        if ok:
            cleaned += 1
            if not dry:
                sticky_idx = used_idx
                successes_since_reset += 1
                if successes_since_reset >= reset_every:
                    sticky_idx = 0
                    successes_since_reset = 0
        else:
            failed += 1

        out_rows.append(
            {
                "qahash16": q_hash(cq, cb, ["qa-import"]),
                "question": cq,
                "answerBack": cb,
                "sourceDay": day,
                "status": "cleaned",
            }
        )

    write_jsonl_rows_atomic(out_path, out_rows)
    _write_rotation(rotation_path, sticky_idx, models[sticky_idx] if models else "")
    return {"input": len(rows), "cleaned": cleaned, "failed": failed}


def _load_mock_anki(path: Path) -> dict[str, dict]:
    cards: dict[str, dict] = {}
    for row in load_jsonl_rows(path):
        q = str(row.get("question") or "").strip()
        b = str(row.get("answerBack") or "").strip()
        if not q or not b:
            continue
        h = q_hash(q, b, ["qa-import"])
        cards[h] = {
            "qahash16": h,
            "question": q,
            "answerBack": b,
            "source": "mock-anki",
        }
    return cards


def run_small_test(root: Path) -> None:
    cfg = load_merge_config(root)
    stage = cfg.test_stage if cfg.test_stage in {"cleanup", "morning", "both"} else "both"

    if stage in {"cleanup", "both"}:
        cleanup_stats = run_cleanup(root, force_dry_run=True)
        print("cleanup", " ".join(f"{k}={v}" for k, v in cleanup_stats.items()))

    if stage in {"morning", "both"}:
        cards = _load_mock_anki(Path(cfg.test_mock_anki).expanduser().resolve()) if cfg.test_mock_anki else {}
        cleaned_dir = root / cfg.cleaned_subdir
        files = sorted(cleaned_dir.glob("*.jsonl"))
        cleaned_cards = {}
        if files:
            for row in load_jsonl_rows(files[-1]):
                h = str(row.get("qahash") or row.get("qahash16") or "").strip().lower()
                if h:
                    cleaned_cards[h] = row
        stats: dict[str, int] = {}
        apply_cleaned_cards(cards, cleaned_cards, stats)
        print(f"morning merged={stats.get('cleaned_applied', 0)} total_cards={len(cards)}")


def main_extract() -> int:
    load_qa_dotenv()
    root = _resolve_root()
    print(f"added={run_extract(root)}")
    write_extract_last_success(root)
    return 0


def main_cleanup() -> int:
    load_qa_dotenv()
    root = _resolve_root()
    stats = run_cleanup(root)
    print(" ".join(f"{k}={v}" for k, v in stats.items()))
    return 0


def main_test() -> int:
    load_qa_dotenv()
    root = _resolve_root()
    run_small_test(root)
    return 0
