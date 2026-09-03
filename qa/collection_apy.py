"""Open the local Anki collection via apyanki (same engine as the `apy` CLI).

Anki desktop must **not** be running — the collection SQLite file must be unlocked.

Install: ``pip install apyanki`` (see requirements-apy.txt).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

def _load_apy():
    try:
        from apyanki.anki import Anki
        from apyanki.config import cfg as apy_cfg
    except ImportError as exc:
        raise RuntimeError(
            "The apyanki package is required (e.g. pip install -r requirements-apy.txt). "
            "See https://github.com/lervag/apy"
        ) from exc
    return Anki, apy_cfg


@contextmanager
def open_collection(
    base_path: str,
    profile_name: str | None,
) -> Generator[Any, None, None]:
    """
    Yield an apyanki ``Anki`` instance. Disables ``auto_sync`` on exit so unattended
    jobs do not trigger AnkiWeb sync; set ``auto_sync`` in ~/.config/apy/apy.json if you want it.
    """
    Anki, apy_cfg = _load_apy()
    # apyanki: ``cfg`` is the dict itself; older forks may expose ``cfg.cfg``.
    cfg: dict[str, Any] = apy_cfg if isinstance(apy_cfg, dict) else apy_cfg.cfg
    prev_auto = cfg.get("auto_sync", True)
    cfg["auto_sync"] = False
    try:
        kwargs: dict[str, Any] = {"base_path": base_path}
        if profile_name:
            kwargs["profile_name"] = profile_name
        with Anki(**kwargs) as a:
            yield a
    finally:
        cfg["auto_sync"] = prev_auto


def deck_exists(a: Any, deck_name: str) -> bool:
    return deck_name in a.deck_name_to_id


def find_note_ids(a: Any, query: str) -> list[int]:
    return list(a.col.find_notes(query))


def _note_mod_or_mtime(raw: Any) -> int:
    m = getattr(raw, "mod", None)
    if m is not None:
        return int(m)
    m2 = getattr(raw, "mtime", None)
    if m2 is not None:
        return int(m2)
    return 0


def note_as_info_dict(a: Any, nid: int) -> dict[str, Any] | None:
    """Anki note shaped like AnkiConnect ``notesInfo`` for pull/push."""
    from anki.notes import NoteId

    try:
        raw = a.col.get_note(NoteId(int(nid)))
    except Exception:
        return None
    model = raw.note_type()
    if not model:
        return None
    fields: dict[str, dict[str, Any]] = {}
    for i, fld in enumerate(model["flds"]):
        name = str(fld.get("name") or "")
        val = raw.fields[i] if i < len(raw.fields) else ""
        fields[name] = {"value": val, "order": i}
    return {
        "noteId": int(raw.id),
        "mod": int(
            _note_mod_or_mtime(raw),
        ),
        "tags": list(raw.tags),
        "fields": fields,
    }


def _notetype_by_name(a: Any, model_name: str) -> dict[str, Any]:
    for nt in a.col.models.all():
        if str(nt.get("name") or "") == model_name:
            return nt
    raise RuntimeError(f"Anki note type not found: {model_name!r}")


def _field_values_for_model(a: Any, model_name: str, front: str, back: str) -> list[str]:
    """One string per model field (order matches ``flds``); only ``Front`` / ``Back`` are set."""
    nt = _notetype_by_name(a, model_name)
    flds = nt.get("flds")
    if not isinstance(flds, list):
        return [front, back]
    vals = [""] * len(flds)
    for i, fld in enumerate(flds):
        if not isinstance(fld, dict):
            continue
        name = str(fld.get("name") or "")
        if name == "Front":
            vals[i] = front
        elif name == "Back":
            vals[i] = back
    return vals


def apy_add_note(
    a: Any,
    deck: str,
    model: str,
    front: str,
    back: str,
    tags: list[str],
) -> int:
    """Add a note; returns note id. Writes field strings as-is (no apy markdown→HTML)."""
    from anki.decks import DeckId
    from anki.models import NotetypeId

    nt = _notetype_by_name(a, model)
    vals = _field_values_for_model(a, model, front, back)
    n = a.col.new_note(NotetypeId(int(nt["id"])))
    if len(vals) != len(n.fields):
        raise RuntimeError(
            f"field count mismatch for model {model!r}: got {len(vals)}, note expects {len(n.fields)}",
        )
    for i, text in enumerate(vals):
        n.fields[i] = text
    for t in tags:
        t = str(t).strip()
        if t:
            n.add_tag(t)
    did = int(a.deck_name_to_id[deck])
    a.col.add_note(n, DeckId(did))
    a.modified = True
    return int(n.id)


def apy_update_note_fields(a: Any, nid: int, front: str, back: str) -> None:
    from anki.notes import NoteId

    n = a.col.get_note(NoteId(int(nid)))
    model = n.note_type()
    if not model:
        return
    for i, fld in enumerate(model["flds"]):
        name = str(fld.get("name") or "")
        if name == "Front":
            n.fields[i] = front
        elif name == "Back":
            n.fields[i] = back
    a.col.update_note(n)
    a.modified = True


def fetch_notes_info(a: Any, note_ids: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for nid in note_ids:
        info = note_as_info_dict(a, int(nid))
        if info:
            out.append(info)
    return out
