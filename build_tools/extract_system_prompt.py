#!/usr/bin/env python3
"""
Deterministically extract the composed whole sealed system prompt from
151-wave15-terminal.md section 4 and write commitment-v2/SYSTEM_PROMPT.md
byte-verbatim, the ONLY substitution being {MODEL_CUTOFF_DATE} -> January 2026.

This is a BUILD TOOL, not part of the sealed tree. The binary conformance gate
(C-COUNCIL-PROMPT) independently re-derives the same text from SPEC_ROOT and
asserts byte-identity against the built SYSTEM_PROMPT.md. This tool and the gate
share the extraction logic in council_prompt_extract.py so there is one
authoritative algorithm.

Usage: extract_system_prompt.py SPEC_ROOT OUT_PATH
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from council_prompt_extract import extract_sealed_system_prompt  # noqa: E402

MODEL_CUTOFF_DATE = "January 2026"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract_system_prompt.py SPEC_ROOT OUT_PATH", file=sys.stderr)
        return 2
    spec_root = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    src = spec_root / "151-wave15-terminal.md"
    if not src.is_file():
        print(f"FATAL: spec file not found: {src}", file=sys.stderr)
        return 1
    text = extract_sealed_system_prompt(src.read_text(encoding="utf-8"),
                                        model_cutoff_date=MODEL_CUTOFF_DATE)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path} ({len(text)} bytes, "
          f"{text.count(chr(10))} newlines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
