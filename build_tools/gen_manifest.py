#!/usr/bin/env python3
"""
Generate commitment-v2/MANIFEST.txt: per-file SHA-256 of every sealed file
plus the pinned code git commit SHA. BUILD ARTEFACT ONLY. This is NOT the
pre-registration hash; the real seal hash is computed only at the Maran-gated
seal step (pause point (b)). MANIFEST.txt itself is excluded from its own
listing. Standard library only.

Usage: gen_manifest.py SEALED_ROOT BUILD_REPO
"""
import hashlib
import subprocess
import sys
from pathlib import Path


def main() -> int:
    sealed = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    manifest = sealed / "MANIFEST.txt"
    files = sorted(p for p in sealed.rglob("*")
                   if p.is_file() and p != manifest)
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True).strip()
    except Exception:
        commit = "UNCOMMITTED"
    lines = [
        "# MANIFEST.txt - per-file SHA-256 of the sealed tree (BUILD ARTEFACT).",
        "# NOT the pre-registration hash; the real seal hash is the",
        "# Maran-gated seal step (pause point (b)). MANIFEST.txt excludes",
        "# itself. Paths are POSIX-relative to commitment-v2/.",
        f"pinned_code_git_commit = {commit}",
        "",
    ]
    for p in files:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{digest}  {p.relative_to(sealed).as_posix()}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {manifest} ({len(files)} files, commit {commit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
