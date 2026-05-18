#!/usr/bin/env python3
"""
Local dashboard bridge. Runs on Maran's Mac, NOT on the VPS.

- scp's /var/lib/kuwai/state.partial.json from the VPS to the dashboard's
  data dir.
- Reads the synced vault agent-ledger.md (read-only) to get the authoritative
  agent count from the last Milestone line.
- Merges into ~/projects/kuwai-gta-agent/dashboard/data/state.json so the
  in-browser dashboard polls a single complete file.

Read-only, one-directional, off the integrity-critical path. The dashboard
never writes anything the agent reads.

Usage: dashboard_bridge.py [--watch]

If invoked with --watch, polls every 30s.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VPS = "root@72.62.241.175"
VPS_FILE = "/var/lib/kuwai/state.partial.json"
SSH_KEY = str(Path.home() / ".ssh" / "kuwai_ed25519")
DASH = Path.home() / "projects" / "kuwai-gta-agent" / "dashboard" / "data"
VAULT_LEDGER = (Path.home() / "Obsidian" / "Big Brain" / "reports" /
                "kuwai-gta-agent" / "agent-ledger.md")

CATALYSTS = [
    {"label": "Take-Two earnings",          "at": "2026-05-22T06:30:00+10:00"},
    {"label": "GTA VI Trailer 3 (expected)", "at": "2026-07-01T00:00:00+10:00"},
    {"label": "Take-Two next earnings",      "at": "2026-08-07T06:30:00+10:00"},
]


def _scp_state() -> dict | None:
    try:
        out = subprocess.check_output([
            "scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "LogLevel=ERROR", f"{VPS}:{VPS_FILE}",
            "/tmp/_kuwai_state_vps.json"
        ], text=True, timeout=20)
        return json.loads(Path("/tmp/_kuwai_state_vps.json").read_text("utf-8"))
    except Exception as e:
        print(f"[bridge] scp failed: {e}", file=sys.stderr)
        return None


def _agent_count() -> int | None:
    """The authoritative count: the last Milestone line in agent-ledger.md.
    Pattern: '**<num> numbered agents / <num> total**'. The displayed count is
    'total' per 00h discipline (headline figure, only grows)."""
    if not VAULT_LEDGER.is_file():
        return None
    txt = VAULT_LEDGER.read_text("utf-8")
    last = None
    for m in re.finditer(r"\*\*(\d+)\s+numbered\s+agents\s*/\s*(\d+)\s+total\*\*",
                          txt):
        last = int(m.group(2))
    return last


def merge_once() -> int:
    DASH.mkdir(parents=True, exist_ok=True)
    out = DASH / "state.json"
    vps = _scp_state()
    agents = _agent_count()
    if vps is None:
        # Keep the in-frame SAMPLE marker on. Write a sample sentinel.
        state = {
            "schema": "kuwai-state-v1",
            "_sample": True,
            "feed_state": "none",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "seed": 150.00,
            "equity": 150.00,
            "since_trade_s": 0,
            "agents": agents if agents else 0,
            "hash": None,
            "next_event": CATALYSTS[0],
            "catalyst_queue": CATALYSTS,
            "gta_launch": "2026-11-19T00:00:00+11:00",
            "log": [{"t": "—", "act": "HOLD",
                      "n": "VPS exporter has not produced state yet"}],
            "last_trade_id": None,
            "standout_events": [],
        }
    else:
        # Merge VPS payload with the vault-derived agent count.
        state = dict(vps)
        state["_sample"] = False
        if agents is not None:
            state["agents"] = agents
        if not state.get("catalyst_queue"):
            state["catalyst_queue"] = CATALYSTS
        if not state.get("next_event"):
            state["next_event"] = CATALYSTS[0]
    out.write_text(json.dumps(state, sort_keys=True, ensure_ascii=False,
                              indent=2) + "\n", encoding="utf-8")
    print(f"[bridge] wrote {out} (agents={state.get('agents')}, "
          f"_sample={state.get('_sample')})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=30)
    a = p.parse_args()
    if a.watch:
        while True:
            merge_once()
            time.sleep(a.interval)
    return merge_once()


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
