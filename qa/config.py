"""Load ``settings.yaml`` + ``.env`` (secrets only). Env vars still override for CI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required. pip install pyyaml") from exc

QA_DIR = Path(__file__).resolve().parent
REPO_ROOT = QA_DIR.parent
SETTINGS_PATH = REPO_ROOT / "settings.yaml"
DOTENV_PATH = REPO_ROOT / ".env"

DEFAULT_APY_BASE = str(Path.home() / "Library/Application Support/Anki2")
DEFAULT_ANKI_DECK = "Ai-Convo-QA"
DEFAULT_ANKI_MODEL = "Better Markdown : Basic"
DEFAULT_CLEANUP_PROMPT = (
    "You are being provided the back of an Anki flashcard. Please CLEAN the input up "
    "with minimal edits. Ensure the latex is all inline, the code is marked correctly "
    "with backticks and the bullet points are properly formatted as markdown with minimal edits."
)


def load_qa_dotenv() -> None:
    """Load repo-root ``.env`` (OPENROUTER_API_KEY). Does not override existing env."""
    if DOTENV_PATH.is_file():
        load_dotenv(DOTENV_PATH, override=False)


def load_settings_dict() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return {}
    raw = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"settings.yaml must be a mapping: {SETTINGS_PATH}")
    return raw


def _expand(val: Any) -> str:
    return str(Path(os.path.expandvars(os.path.expanduser(str(val).strip())))).rstrip("/")


def _env_str(key: str, default: str) -> str:
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        return default
    return _expand(v)


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        return default
    try:
        return max(1, int(str(v).strip()))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str, default: list[str]) -> list[str]:
    v = os.environ.get(key)
    if v is None or not str(v).strip():
        return default
    out = [x.strip() for x in str(v).split(",") if x.strip()]
    return out or default


def _nested(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _parse_hhmm(raw: Any, fallback: tuple[int, int]) -> tuple[int, int]:
    text = str(raw or "").strip()
    if not text:
        return fallback
    if ":" not in text:
        return fallback
    h_s, m_s = text.split(":", 1)
    try:
        h, m = int(h_s), int(m_s)
    except ValueError:
        return fallback
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return fallback
    return h, m


def _parse_slots(raw: Any, fallback: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not isinstance(raw, list) or not raw:
        return fallback
    out: list[tuple[int, int]] = []
    for item in raw:
        out.append(_parse_hhmm(item, (0, 0)))
    return out or fallback


@dataclass
class MergeConfig:
    apy_base_path: str
    apy_profile_name: str
    anki_deck: str
    anki_model: str
    git_repo: str
    git_qa_subdir: str
    anki_presync: str
    schedule_tz: str
    todo_subdir: str
    cleaned_subdir: str
    openrouter_models: list[str]
    openrouter_sleep_seconds: int
    openrouter_reset_every_n: int
    openrouter_rotation_file: str
    cleanup_prompt: str
    extract_slots: list[tuple[int, int]]
    extract_no_git: bool
    extract_lookback_days: int
    cleanup_dry_run: bool
    test_stage: str
    test_mock_anki: str
    log_root: str
    export_dir: str
    data_repo: str
    merge_hour: int
    merge_minute: int
    extract_poll_seconds: int


def load_merge_config(root: Path) -> MergeConfig:
    """Build settings from ``settings.yaml``, then env overrides. ``root`` is unused (API compat)."""
    _ = root
    s = load_settings_dict()
    merge_h, merge_m = _parse_hhmm(_nested(s, "schedule", "merge"), (5, 15))
    slots = _parse_slots(_nested(s, "schedule", "extract"), [(15, 0), (18, 0), (21, 0)])
    pres = _env_str(
        "READ_CHAT_GUI_ANKI_PRESYNC",
        str(_nested(s, "anki", "presync", default="guard") or "guard"),
    ).strip().lower()

    yaml_models = _nested(s, "openrouter", "models", default=None)
    default_models = (
        [str(m).strip() for m in yaml_models if str(m).strip()]
        if isinstance(yaml_models, list)
        else ["nvidia/nemotron-3-super-120b-a12b:free", "openai/gpt-oss-120b:free"]
    )
    prompt = str(_nested(s, "openrouter", "cleanup_prompt", default="") or "").strip() or DEFAULT_CLEANUP_PROMPT

    return MergeConfig(
        apy_base_path=_env_str("APY_BASE", _expand(_nested(s, "anki", "base", default=DEFAULT_APY_BASE))),
        apy_profile_name=_env_str("APY_PROFILE", str(_nested(s, "anki", "profile", default="") or "")),
        anki_deck=_env_str("ANKI_DECK", str(_nested(s, "anki", "deck", default=DEFAULT_ANKI_DECK) or DEFAULT_ANKI_DECK)),
        anki_model=_env_str(
            "ANKI_MODEL",
            str(_nested(s, "anki", "model", default=DEFAULT_ANKI_MODEL) or DEFAULT_ANKI_MODEL),
        ),
        git_repo=_env_str(
            "READ_CHAT_GUI_GIT_REPO",
            _expand(_nested(s, "paths", "git_repo", default="")),
        ),
        git_qa_subdir=_env_str(
            "READ_CHAT_GUI_GIT_QA_SUBDIR",
            str(_nested(s, "paths", "git_qa_subdir", default="qa_pairs") or "qa_pairs"),
        ),
        anki_presync=pres or "guard",
        schedule_tz=_env_str(
            "READ_CHAT_GUI_SCHEDULE_TZ",
            str(_nested(s, "schedule", "timezone", default="America/Los_Angeles") or "America/Los_Angeles"),
        ),
        todo_subdir=_env_str(
            "READ_CHAT_GUI_TODO_SUBDIR",
            str(_nested(s, "paths", "todo_subdir", default="qa/todo") or "qa/todo"),
        ),
        cleaned_subdir=_env_str(
            "READ_CHAT_GUI_CLEANED_SUBDIR",
            str(_nested(s, "paths", "cleaned_subdir", default="qa/cleaned") or "qa/cleaned"),
        ),
        openrouter_models=_env_list("READ_CHAT_GUI_OPENROUTER_MODELS", default_models),
        openrouter_sleep_seconds=_env_int(
            "READ_CHAT_GUI_OPENROUTER_SLEEP_SECONDS",
            int(_nested(s, "openrouter", "sleep_seconds", default=5) or 5),
        ),
        openrouter_reset_every_n=_env_int(
            "READ_CHAT_GUI_OPENROUTER_RESET_EVERY_N",
            int(_nested(s, "openrouter", "reset_every_n", default=10) or 10),
        ),
        openrouter_rotation_file=_env_str(
            "READ_CHAT_GUI_OPENROUTER_ROTATION_FILE",
            str(_nested(s, "paths", "rotation_file", default="qa/cleaned/.rotation.json") or "qa/cleaned/.rotation.json"),
        ),
        cleanup_prompt=os.environ.get("READ_CHAT_GUI_CLEANUP_PROMPT", "").strip() or prompt,
        extract_slots=slots,
        extract_no_git=_env_bool(
            "READ_CHAT_GUI_EXTRACT_NO_GIT",
            bool(_nested(s, "extract", "no_git", default=False)),
        ),
        extract_lookback_days=_env_int(
            "READ_CHAT_GUI_LOOKBACK_DAYS",
            int(_nested(s, "extract", "lookback_days", default=7) or 7),
        ),
        cleanup_dry_run=_env_bool(
            "READ_CHAT_GUI_CLEANUP_DRY_RUN",
            bool(_nested(s, "cleanup", "dry_run", default=False)),
        ),
        test_stage=_env_str("READ_CHAT_GUI_TEST_STAGE", "both").lower(),
        test_mock_anki=_env_str("READ_CHAT_GUI_TEST_MOCK_ANKI", ""),
        log_root=_env_str(
            "READ_CHAT_GUI_LOG_ROOT",
            _expand(_nested(s, "paths", "log_root", default=str(Path.home() / ".cache/qa_flashcards_repo/qa_pairs/Ai-Convo-QA"))),
        ),
        export_dir=_expand(_nested(s, "paths", "export_dir", default=str(Path.home() / "Desktop/QA"))),
        data_repo=str(_nested(s, "data_repo", default="") or ""),
        merge_hour=merge_h,
        merge_minute=merge_m,
        extract_poll_seconds=int(_nested(s, "schedule", "extract_poll_seconds", default=900) or 900),
    )
