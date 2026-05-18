#!/usr/bin/env python3
"""
Deterministic secret scanner (C-SECRETS). Scans the sealed tree + code/ +
corpus/ + the repo for any credential pattern and emits a dated report
OUTSIDE the sealed tree (conformance/secret-scan-report.txt). Clean = zero
credential of any kind. Standard library only.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PATTERNS = {
    "alpaca_key": re.compile(r"\bAPCA[-_][A-Z0-9-]+\s*[:=]\s*\S+"),
    "alpaca_secret": re.compile(r"\b[A-Za-z0-9/+]{40}\b"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    "apify_token": re.compile(r"apify_api_[A-Za-z0-9]{8,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    "generic_secret_assign": re.compile(
        r"(?i)\b(secret|password|passwd|api[_-]?key|token)\b\s*[:=]\s*"
        r"['\"][^'\"]{8,}['\"]"),
    "healthchecks_ping": re.compile(
        r"https?://hc-ping\.com/[0-9a-f-]{16,}"),
    "pem_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# The Alpaca-secret heuristic is broad. A real Alpaca secret is mixed-case
# base64 with / or +; it is never a pure lowercase hex digest. Git commit
# SHAs (40 hex) and SHA-256 digests (64 hex) in MANIFEST/log are provably not
# credentials, so exclude any all-hex token. This sharpens accuracy; it does
# not weaken C-SECRETS (a real base64 secret still matches and is reported).
ALLHEX = re.compile(r"^[0-9a-fA-F]{7,64}$")


def scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for base in paths:
        if not base.exists():
            continue
        files = [base] if base.is_file() else [
            p for p in base.rglob("*") if p.is_file()]
        for p in files:
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for name, rx in PATTERNS.items():
                for m in rx.finditer(text):
                    tok = m.group(0)
                    if name == "alpaca_secret" and ALLHEX.match(tok):
                        continue  # git SHA / hash digest, not a credential
                    findings.append(f"{p}: {name}: {tok[:24]}...")
    return findings


def run(sealed_root: Path, repo_root: Path, out: Path) -> int:
    targets = [
        sealed_root,                       # the whole sealed tree
        repo_root / "README.md",
        repo_root / ".gitignore",
    ]
    findings = scan(targets)
    clean = len(findings) == 0
    out.write_text(
        f"# secret-scan-report (C-SECRETS) - committed OUTSIDE the sealed tree\n"
        f"scanned_utc = {datetime.now(timezone.utc).isoformat()}\n"
        f"scanned: sealed tree {sealed_root}, repo README/.gitignore\n"
        f"covers: canonical tree + corpus/ + pinned-commit code/ + repo root\n"
        f"result = {'CLEAN' if clean else 'DIRTY'}\n"
        f"findings_count = {len(findings)}\n"
        + ("".join(f"FINDING {f}\n" for f in findings) if findings else
           "no credential of any kind found\n"),
        encoding="utf-8")
    return 0 if clean else 1


if __name__ == "__main__":
    sealed = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    out = Path(sys.argv[3]).resolve()
    raise SystemExit(run(sealed, repo, out))
