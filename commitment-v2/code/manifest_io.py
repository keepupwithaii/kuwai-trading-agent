#!/usr/bin/env python3
"""
Deterministic readers for the sealed text manifest files. Standard library
only (nothing pip-installed can rot over a 26-week unattended run; 27 ops).

Sealed code at the pinned commit. The conformance gate imports the same
readers so the build and the check parse identically.
"""
from __future__ import annotations

from pathlib import Path

SEALED_ROOT = Path(__file__).resolve().parent.parent  # commitment-v2/


def read_model(root: Path | None = None) -> tuple[str, str]:
    """Return (model_id, sampling_note) from MODEL.txt. Exactly two
    non-empty lines: line 1 is the pinned snapshot id; line 2 is the
    sampling-note string. Anthropic deprecated temperature/top_p/top_k for
    claude-opus-4-7; the sealed record states what is used, not what was
    intended. (Maran-authorised amendment 2026-05-19, reason class
    'broker or API change' per WEEKLY-POLICY.md.)"""
    root = root or SEALED_ROOT
    lines = (root / "MODEL.txt").read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if ln.strip() != ""]
    if len(lines) != 2:
        raise ValueError(f"MODEL.txt must be exactly two lines, got {len(lines)}")
    model_id, sampling_note = lines[0].strip(), lines[1].strip()
    if not model_id:
        raise ValueError("MODEL.txt model id empty")
    if not sampling_note:
        raise ValueError("MODEL.txt sampling-note line empty")
    return model_id, sampling_note


def read_universe(root: Path | None = None) -> list[str]:
    """Return the sealed allow-list of uppercase tickers (comments stripped)."""
    root = root or SEALED_ROOT
    out: list[str] = []
    for ln in (root / "UNIVERSE.txt").read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    if not out:
        raise ValueError("UNIVERSE.txt is empty")
    # crypto must not be present anywhere (sanity, equities/ETF only)
    return out


def read_schedule(root: Path | None = None) -> dict[str, str]:
    """Return the sealed schedule key=value pairs (comments stripped)."""
    root = root or SEALED_ROOT
    cfg: dict[str, str] = {}
    for ln in (root / "SCHEDULE.txt").read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        cfg[k.strip()] = v.split("#", 1)[0].strip()
    if cfg.get("crypto_leg") != "absent_sealed":
        raise ValueError("SCHEDULE.txt crypto_leg must be absent_sealed")
    return cfg


def read_text(name: str, root: Path | None = None) -> str:
    root = root or SEALED_ROOT
    return (root / name).read_text(encoding="utf-8")
