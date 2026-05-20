#!/usr/bin/env python3
"""
Local dashboard bridge. Runs on Maran's Mac, NOT on the VPS.

- scp's /var/lib/kuwai/state.partial.json from the VPS to the dashboard's
  data dir.
- Uses the architect-confirmed agent count constant (ARCHITECT_CONFIRMED_-
  AGENT_COUNT) as the single source of truth; it is NOT read from the local
  Obsidian vault copy (that has lagged) and must be re-confirmed + bumped
  here whenever the architect ledger increments.
- Merges into ~/projects/kuwai-gta-agent/dashboard/data/state.json
  ATOMICALLY (temp + os.replace) so the in-browser dashboard polls a single
  complete file and can never read a half-written/empty state.

Read-only, one-directional, off the integrity-critical path. The dashboard
never writes anything the agent reads.

Usage: dashboard_bridge.py [--watch]

If invoked with --watch, polls every 30s.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VPS = "root@72.62.241.175"
VPS_FILE = "/var/lib/kuwai/state.partial.json"
SSH_KEY = str(Path.home() / ".ssh" / "kuwai_ed25519")
DASH = Path.home() / "projects" / "kuwai-gta-agent" / "dashboard" / "data"

# --- Authoritative, architect-confirmed constants (fed via state.json, never
#     hardcoded in the dashboard HTML) -----------------------------------
# The real sealed E0_BASELINE_USD (commitment-v2/code/floor.py). Not the $200
# paper synthetic, not the $150 sample. The VPS exporter still reports the
# paper synthetic seed; the bridge OVERRIDES it to this real value.
REAL_E0 = 174.28
# The published canonical sealed-tree hash (git tag commitment-v2). Fed into
# state.json so the dashboard footer shows the real seal, never a placeholder.
SEALED_HASH = "eb574094aac401a0ec19c055f1218a1af77b059ad629d47eadfb3bef0f990ae1"
# Live since the Maran-triggered T-5 go-live (real Alpaca 258088643).
MODE = "live"
# Architect-authoritative on-screen TOTAL agent count (Maran decision
# 2026-05-19; agent-ledger "Authoritative on-screen count" line):
#   140 numbered + 1 pre-research vault-sweep = 141 total.
# NOT read from the local/Obsidian vault copy (it has lagged). This single
# named constant IS the source of truth and MUST be bumped here whenever the
# architect re-confirms a new ledger figure; the dashboard must never show a
# count the architect ledger does not back.
ARCHITECT_CONFIRMED_AGENT_COUNT = 141

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


def _atomic_write(out: Path, payload: str) -> None:
    """Write payload to a temp file in the same dir then os.replace onto out.
    os.replace is atomic on the same filesystem, so a dashboard poll can NEVER
    read a half-written or empty state.json and fall back to sample."""
    tmp = out.with_name(out.name + f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)


def merge_once() -> int:
    DASH.mkdir(parents=True, exist_ok=True)
    out = DASH / "state.json"
    vps = _scp_state()
    if vps is None:
        # Honest NO-FEED state. NEVER fabricate sample numbers: seed is the
        # real sealed E0 (a fixed constant, not a market figure), equity is
        # explicitly null (unknown), feed_state=none so the dashboard renders
        # the truthful STALE / NO FEED state. mode/hash/agents stay
        # authoritative so the footer never regresses to a placeholder.
        state = {
            "schema": "kuwai-state-v1",
            "_sample": False,
            "feed_state": "none",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "mode": MODE,
            "seed": REAL_E0,
            "equity": None,
            "today_open_equity": None,
            "since_trade_s": 0,
            "agents": ARCHITECT_CONFIRMED_AGENT_COUNT,
            "hash": SEALED_HASH,
            "next_event": CATALYSTS[0],
            "catalyst_queue": CATALYSTS,
            "gta_launch": "2026-11-19T00:00:00+11:00",
            "log": [{"t": "—", "act": "—",
                      "n": "VPS exporter has not produced state yet"}],
            "last_trade_id": None,
            "standout_events": [],
        }
    else:
        # Merge the live VPS payload, then OVERRIDE with the architect-
        # authoritative facts. The exporter reports the paper synthetic seed
        # ($200) and no hash; the bridge is the single place those become the
        # real sealed values for display.
        state = dict(vps)
        state["_sample"] = False
        state["mode"] = MODE
        state["seed"] = REAL_E0                 # real sealed E0, not $200/$150
        state["hash"] = SEALED_HASH             # real seal, fed via state.json
        state["agents"] = ARCHITECT_CONFIRMED_AGENT_COUNT
        if not state.get("catalyst_queue"):
            state["catalyst_queue"] = CATALYSTS
        if not state.get("next_event"):
            state["next_event"] = CATALYSTS[0]
    _atomic_write(out, json.dumps(state, sort_keys=True, ensure_ascii=False,
                                  indent=2) + "\n")
    print(f"[bridge] wrote {out} (agents={state.get('agents')}, "
          f"mode={state.get('mode')}, seed={state.get('seed')}, "
          f"feed_state={state.get('feed_state')})")
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
