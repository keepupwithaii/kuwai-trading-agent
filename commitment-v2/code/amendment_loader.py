#!/usr/bin/env python3
"""
The amendment loader: a deterministic scheduled gated swap. There is NO
live-patch path of any kind. At a weekly-review boundary the running agent is
stopped, the new artefact's canonical hash is verified against the published
expected hash, and ONLY the verified artefact starts (an ExecStartPre check).
A running artefact whose hash matches no published seal cannot exist by
construction (94 C2.5 / 102 R2.7). Standard library only.

This module exposes a --check-hash preflight; ExecStartPre calls it and a
non-zero exit refuses to start the unit.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SEALED_ROOT = Path(__file__).resolve().parent.parent  # commitment-v2/


def canonical_tree_hash(root: Path) -> str:
    """SHA-256 over the canonical sealed git tree: every file under root in
    sorted POSIX-relative-path order, each contributing its path then its
    bytes. Deterministic and reproducible by a sceptic.
    """
    h = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def preflight(expected_hash: str, root: Path | None = None) -> int:
    """Return 0 iff the on-disk sealed tree hash matches expected_hash.
    No live patching is ever performed; this only verifies-or-refuses.
    """
    root = root or SEALED_ROOT
    got = canonical_tree_hash(root)
    if got != expected_hash:
        sys.stderr.write(
            f"SEAL HASH MISMATCH: expected {expected_hash} got {got}\n")
        return 1
    return 0


if __name__ == "__main__":
    # Usage: amendment_loader.py <expected_hash>
    # The expected hash is provisioned at deploy from the published seal; it is
    # NOT computed or pre-registered by the build (pause point (b)).
    if len(sys.argv) != 2:
        sys.stderr.write("usage: amendment_loader.py <expected_hash>\n")
        raise SystemExit(2)
    raise SystemExit(preflight(sys.argv[1]))
