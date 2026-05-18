#!/usr/bin/env python3
"""
The single authoritative extraction of the composed whole sealed system prompt
from 151-wave15-terminal.md section 4.

Shared by the build tool (extract_system_prompt.py) and the binary conformance
gate (C-COUNCIL-PROMPT). One algorithm so the build and the check can never
diverge. Fail loud: any structural surprise raises, never silently produces a
wrong prompt.

Rules (brief 2A / 151 section 4):
  - Section 4 reproduces the prompt as a markdown blockquote between the exact
    marker lines BEGIN/END below.
  - Strip the leading "> " from each quoted line; a line that is exactly ">"
    becomes an empty line (paragraph break). Preserve every paragraph break.
  - The ONLY substitution is the single literal token {MODEL_CUTOFF_DATE}
    -> the given model_cutoff_date (default "January 2026"). It must occur
    exactly once.
  - No other character edits.
"""
from __future__ import annotations

BEGIN_MARKER = "--- BEGIN SEALED SYSTEM_PROMPT.md (composed whole, verbatim) ---"
END_MARKER = "--- END SEALED SYSTEM_PROMPT.md (composed whole, verbatim) ---"
PLACEHOLDER = "{MODEL_CUTOFF_DATE}"


def extract_sealed_system_prompt(doc_text: str,
                                 model_cutoff_date: str = "January 2026") -> str:
    """Return the byte-verbatim sealed SYSTEM_PROMPT.md text."""
    lines = doc_text.split("\n")

    begin_idx = end_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == BEGIN_MARKER:
            if begin_idx is not None:
                raise ValueError("multiple BEGIN markers in 151")
            begin_idx = i
        elif ln.strip() == END_MARKER:
            if end_idx is not None:
                raise ValueError("multiple END markers in 151")
            end_idx = i
    if begin_idx is None or end_idx is None:
        raise ValueError("BEGIN/END sealed-prompt markers not found in 151")
    if end_idx <= begin_idx:
        raise ValueError("END marker precedes BEGIN marker in 151")

    body = lines[begin_idx + 1:end_idx]

    # Keep only the blockquote lines; the blank separator lines just inside the
    # markers are not blockquoted and are correctly dropped.
    out: list[str] = []
    seen_quote = False
    for ln in body:
        if ln.startswith("> "):
            seen_quote = True
            out.append(ln[2:])
        elif ln == ">":
            seen_quote = True
            out.append("")
        elif ln.strip() == "":
            # separator blank line outside the quote (only valid before the
            # first quoted line or after the last); ignore.
            continue
        else:
            raise ValueError(
                f"unexpected non-blockquote line inside sealed prompt: {ln!r}")
    if not seen_quote:
        raise ValueError("no blockquote content found between markers")

    # Trim a leading/trailing empty line artefact (there should be none, but be
    # deterministic if the doc has an edge blank).
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    text = "\n".join(out) + "\n"

    count = text.count(PLACEHOLDER)
    if count != 1:
        raise ValueError(
            f"expected exactly one {PLACEHOLDER}, found {count}")
    text = text.replace(PLACEHOLDER, model_cutoff_date)

    # Hard invariants the sealed body must satisfy (139 section 1.2 / 151
    # section 4): no temperature string, no safety-net phrasing, no floor
    # mention, no stray placeholder.
    if PLACEHOLDER in text:
        raise ValueError("placeholder still present after substitution")
    low = text.lower()
    for banned in ("temperature", "no safety net", "1.0", "0.7", "floor",
                   "0.45"):
        if banned in low:
            raise ValueError(
                f"sealed prompt body contains banned substring {banned!r}")
    return text
