---
name: flashcard-qa-json-export
description: >-
  Persists each flashcard Q/A pair as one JSON file under EXPORT_DIR whenever
  knowledge-mode cards are produced—default behavior, no /export flag needed.
  Skip when flashcard-qa-core classifies the turn as shallow (no Q/A output).
---

# JSON file export for Q/A pairs

## When to apply

- Apply (same turn, after the in-chat `Q:` / `A:` text): whenever **flashcard-qa-core** outputs one or more `Q:` / `A:` pairs (knowledge / flashcard mode).
- Do not write JSON files when the turn is shallow / ephemeral (no `Q:` / `A:` in the reply—e.g. quick fix, trivial patch).

## Where to write (path configuration)

- **Config file** (one line = absolute directory for JSON files). Try in order:
  1. `~/.cursor/flashcard-qa/EXPORT_DIR` (written by `flashcard-qa/install.sh`)
  2. `~/.cursor/skills/flashcard-qa-json-export/EXPORT_DIR`
  3. If the **flashcard-qa** repo is in the workspace: repo-root **`EXPORT_DIR`**
- **Rules**:
  1. Read the **first non-empty line**; trim whitespace; ignore lines starting with `#`.
  2. That line must be an **absolute path** to the **target directory** for JSON files.
  3. If none of the files can be read, **do not write files** and say so briefly.
  4. **Create the target directory** with `mkdir -p` (or equivalent) if it does not exist before writing.

## File layout

- **One JSON file per Q/A pair** (including each of Q, Q2, Q3… as its own file).
- **Filename** (avoid collisions, filesystem-safe):

  `qa-<YYYYMMDD>-<HHMMSS>-<pairIndex>-<shortSlug>.json`

  - `pairIndex`: `1` for the first pair in the message, `2` for Q2/A2, etc.
  - `shortSlug`: first **40 chars** of the question, lowercased, non-alphanumeric → `-`, strip repeats (or omit slug if tools unavailable—then use only timestamp + index).

## LaTeX and math — preserve for Anki (critical)

The user imports these JSON files into **Anki** (or similar). **Inline and block LaTeX must survive the round-trip** unchanged in meaning.

- **Copy verbatim** into JSON string fields the same math the user saw in chat: **`$...$`**, **`\\(...\\)`**, **`\\[...\\]`**, `\frac`, `\sigma`, subscripts, etc.
- **Never** strip `$` delimiters, **never** replace LaTeX with Unicode-only math unless the **source** card already did that.
- **Never** HTML-encode (`&lt;`, `&amp;`, etc.) inside these strings—plain text for Anki/MathJax.
- **`walkthrough`**, **`question`**, and each **`answerBullets`** entry may all contain LaTeX; preserve it in **each** field independently.

### JSON escaping (required)

Valid JSON **must** escape backslashes inside strings: each `\` in LaTeX becomes `\\` in the JSON file (e.g. `\frac{a}{b}` → `\\frac{a}{b}`, `\mathbb{R}` → `\\mathbb{R}`). Double quotes inside a string become `\"`.

- When using a **serializer** (code, tool), it does this automatically.
- When **writing JSON by hand**, **every** LaTeX backslash must be doubled or the file is invalid and LaTeX breaks.

### Optional standalone LaTeX from `/latex`

- If **flashcard-qa-slash-commands** produced a **`LaTeX (copy):`** fenced **`latex`** block for this pair, also store the **full raw snippet** in **`latexCopyBlock`** (same escaping rules). That gives Anki a **paste-ready** block separate from inline `$...$` in bullets.

## JSON schema (required fields)

Use **UTF-8**, pretty-printed with 2-space indent:

```json
{
  "question": "string (LaTeX preserved; JSON-escaped)",
  "answerBullets": [
    "string (LaTeX preserved; JSON-escaped)"
  ],
  "exportedAt": "2026-04-15T12:34:56.000Z",
}
```

- **`answerBullets`**: one string per bullet line from `A:` (prefer **strip** leading `- ` only; **do not** strip or alter LaTeX).
- **`exportedAt`**: ISO-8601 UTC **when the file is written**.

### Example (valid JSON with inline LaTeX)

```json
{
  "question": "What is the softmax of $z_i$ in $\\mathbb{R}^K$?",
  "answerBullets": [
    "$\\displaystyle \\mathrm{softmax}(z)_i = \\frac{e^{z_i}}{\\sum_j e^{z_j}}$"
  ],
  "exportedAt": "2026-04-15T12:00:00.000Z",
}
```

## Execution

- Use the workspace **write** tool (or run a small shell heredoc) so files land on disk **inside the configured absolute path**.
- If the active workspace root is **not** the flashcard-qa repo, still write to the **absolute path** from `EXPORT_DIR`.

## Errors

- If writing fails, report the error briefly and still show the **in-chat** Q/A as usual.
