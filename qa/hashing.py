"""Question text hashing for dedupe tags (matches anki_cards_generator)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


def deck_slug(deck: str) -> str:
    """Filesystem-safe segment under ``qa_pairs/<slug>/`` (matches ``_backup.deck_slug``)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", deck.strip())
    return slug.strip("-") or "deck"


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or "").strip()))


def _norm_tags(tags: Any) -> list[str]:
    if isinstance(tags, str):
        raw = tags.split()
    elif isinstance(tags, list):
        raw = [str(x) for x in tags]
    else:
        raw = []
    out: list[str] = []
    for t in raw:
        tag = _norm_text(t)
        if not tag:
            continue
        # qahash tags are derived from this hash; exclude to avoid self-reference loops.
        if tag.lower().startswith("qahash-"):
            continue
        out.append(tag)
    return sorted(set(out), key=str.lower)


def q_front_key(question: str) -> str:
    """Stable identity for a card independent of answer edits or cleanup rewrites."""
    return _norm_text(question).casefold()


def q_hash(question: str, answer_back: str = "", tags: Any = None) -> str:
    """Canonical QA hash (32 hex chars) from normalized front, back, and tags."""
    front_n = _norm_text(question)
    back_n = _norm_text(answer_back)
    tags_n = "|".join(_norm_tags(tags))
    payload = f"front:{front_n}\nback:{back_n}\ntags:{tags_n}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
