---
name: flashcard-qa-math-proofs
description: >-
  Explains proofs, derivations, and technical math for flashcard Q/A with
  step-by-step bullets and inline LaTeX. Use when the topic involves equations,
  proofs, derivations, linear algebra, probability, or the user asks how
  something is shown or derived.
---

# Math, proofs, and LaTeX (flashcard mode)

## When this applies

- Use this skill alongside **flashcard-qa-core** whenever the user needs **proofs**, **derivations**, or **equation-heavy** reasoning (including ML math they may find hard).

## Pedagogy

- **Do not** assume deep math background; name the rule/identity before applying it.
- Expand **step by step**; prefer **one main idea per bullet** for derivation steps.
- Include **intermediate** reasoning, not only the final result.

## LaTeX

- Render **all equations** in **inline LaTeX**: `$...$` (or `\(...\)` if the environment prefers that, but stay consistent within the answer).
- Keep notation **minimal**; define symbols on first use in the card when possible.
- When **flashcard-qa-json-export** runs, **the same LaTeX** (delimiters + commands) must appear **verbatim** in **`question`**, **`walkthrough`**, and **`answerBullets`**, with **valid JSON escaping** for backslashes—so Anki/MathJax imports stay faithful. See that skill for **`latexCopyBlock`** when **`/latex`** adds a separate copy block.

## Structure inside `A:`

- Proof/derivation answers remain **bullets only** (no numbered steps as the list mechanism—use bullets; use “Step 1:” text inside a bullet if needed).
- If a **standalone equation block** is needed for copy-paste, the user should ask with **`/latex`** (see **flashcard-qa-slash-commands**); otherwise stay inline within bullets unless readability truly breaks.

## Examples

- After the core steps, add a **tiny numeric or toy example** bullet when it improves intuition without ballooning length.
