"""QQQ / AAA flashcard block parsing (ported from anki_cards_generator._generator)."""

from __future__ import annotations

import re
from typing import Any, List, Tuple

_QA_BLOCK = re.compile(
    r"""
    \bQQQ(?P<id>\d*)\s*:\s*
    (?P<q>.*?)                       # question (lazy)
    \bAAA(?P=id)\s*:\s*
    (?P<a>.*?)                       # answer (lazy)
    (?=\bQQQ\d*\s*:|\Z)              # stop at next Q or end
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)

_BULLET = re.compile(r"^\s*[-•]\s*(.*)$")

_CODESTART_BLOCK = re.compile(
    r"CODESTART:\s*(\S+)(?:\s*\n|\s+)(.*?)CODEEND",
    re.IGNORECASE | re.DOTALL,
)


def pair_id_match(qn: str, an: str) -> bool:
    return qn == an or not qn or not an


def _finalize_answer_bullets(bullets: list[str]) -> list[str]:
    """``CODESTART:lang`` … ``CODEEND`` → standard fenced markdown (`` ```lang ``)."""
    if not bullets:
        return bullets
    blob = "\n".join(bullets)
    blob = _CODESTART_BLOCK.sub(
        lambda m: f"```{m.group(1).lower()}\n{m.group(2).rstrip()}\n```",
        blob,
    )
    out = blob.splitlines()
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _split_bullets(answer: str) -> List[str]:
    """
    Turn an answer block into a list of bullet strings.
    - If explicit bullets exist, keep them.
    - Otherwise, return the whole answer as one item.
    """
    lines = answer.strip().splitlines()
    bullets: List[str] = []
    current: List[str] = []

    for line in lines:
        m = _BULLET.match(line)
        if m:
            # start new bullet
            if current:
                bullets.append(" ".join(current).strip())
                current = []
            current.append(m.group(1).strip())
        else:
            if current:
                current.append(line.strip())
            elif line.strip():
                # no bullets at all → treat as single block
                current.append(line.strip())

    if current:
        bullets.append(" ".join(current).strip())

    return bullets


def parse_qa(text: str) -> List[Tuple[str, List[str]]]:
    pairs: List[Tuple[str, List[str]]] = []

    for m in _QA_BLOCK.finditer(text):
        q = m.group("q").strip()
        a = m.group("a").strip()

        if not q or not a:
            continue

        bullets = _split_bullets(a)
        pairs.append((q, bullets if bullets else [a]))

    return pairs


def markdown_back(bullets: list[str]) -> str:
    out: list[str] = []
    for b in bullets:
        line = b.rstrip()
        if re.match(r"^\s*[-*+]\s+", line):
            out.append(line)
        else:
            out.append(f"- {line}")
    return "\n".join(out)


_QAHASH_TAG = re.compile(r"^qahash-([0-9a-f]{8,64})$", re.IGNORECASE)


def tag_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        return value.split()
    return []


def extract_qahash16_from_tags(tags: Any) -> str | None:
    for raw in tag_list(tags):
        m = _QAHASH_TAG.match(str(raw).strip())
        if m:
            return m.group(1).lower()
    return None


