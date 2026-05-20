#!/usr/bin/env python3
"""
v3 end-to-end smoke wake (staging). Runs one real wake of the sealed v3
agent_loop with the seven new live adapters wired in. PAPER MODE +
STAGING LEDGER (not /var/lib/kuwai/ledger.log) -> no real fill, no
contamination of the live v2 or any future live v3 chain. Stub HOLD-only
decider so no Anthropic quota is consumed and no order is ever proposed;
the smoke wake's load-bearing demonstration is REAL PERCEPTION DATA
FLOWING into the payload from all eight blocks.

Usage: smoke_wake_v3.py     # reads ~/.config/kuwai-agent.env, runs once
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEALED = REPO / "commitment-v3"
DEPLOY = REPO / "deploy"
SECRETS = Path.home() / ".config" / "kuwai-agent.env"


def _load_env():
    """Load KEY=VALUE pairs from the local secrets env (chmod 600)."""
    if not SECRETS.is_file():
        sys.stderr.write(f"[smoke] missing secrets file {SECRETS}\n")
        sys.exit(2)
    for ln in SECRETS.read_text("utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        os.environ[k.strip()] = v.split("#", 1)[0].strip()


def _stub_decider_hold(payload, sealed_prompt):
    """Decision-blind HOLD. Returns no proposed orders so the wake exercises
    PERCEPTION END-TO-END but submits nothing, even on paper."""
    return {"reasoning_envelope": {
                "text": "smoke wake — staging observation only, no orders",
                "payload_refs": [],
                "critique": "smoke staging wake; decider stubbed"},
            "proposed_orders": []}


def _stub_synth(attempt: int = 1, **_) -> str:
    raise AssertionError("synth must not be called on a HOLD wake")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _block_summary(label: str, block: dict) -> dict:
    if not isinstance(block, dict):
        return {"label": label, "block": repr(block)[:200]}
    val = block.get("value")
    rows = []
    rowcount = None
    if isinstance(val, list):
        rowcount = len(val)
        rows = val[:2]
    elif isinstance(val, dict):
        # O_own_account.value is a single dict; treat as 1 row
        rowcount = 1
        rows = [val]
    return {
        "label": label,
        "source": block.get("source"),
        "status": block.get("status"),
        "as_of": block.get("as_of"),
        "fetched_at": block.get("fetched_at"),
        "row_count": rowcount,
        "first_rows": rows,
        "audit": block.get("audit"),  # block_n surfaces an audit dict
    }


def main() -> int:
    # 1) load secrets BEFORE we import clients (clients reads env at init)
    _load_env()
    # 2) staging knobs
    os.environ["KUWAI_MODE"] = "paper"            # paper Alpaca trading
    os.environ["SEALED_TREE"] = str(SEALED)       # local v3 tree
    os.environ["KUWAI_LIVE_BLOCK_N"] = "1"        # exercise Apify Block N
    os.environ["KUWAI_E0"] = "200.0"
    staging_ledger = Path(tempfile.gettempdir()) / "staging_v3_smoke.log"
    if staging_ledger.exists():
        staging_ledger.unlink()
    os.environ["KUWAI_LEDGER"] = str(staging_ledger)

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(SEALED / "code"))
    sys.path.insert(0, str(DEPLOY))

    import agent_loop                              # sealed v3 module
    import clients                                 # extended deploy-side

    # 3) build deps — REAL adapters, stub decider/synth
    bars_ad = clients.AlpacaMarketDataBars()
    news_ad = clients.AlpacaNews()
    edgar_ad = clients.SecEdgar()
    corp_ad = clients.AlpacaCorporateActions()
    own_ad = clients.OwnHistory()
    block_n_ad = clients.BlockNApify()
    derived_ad = clients.DerivedTransforms()
    deps = {
        "broker":       clients.AlpacaBroker(),
        "clock":        clients.Clock(),
        "decider":      _stub_decider_hold,
        "synth":        _stub_synth,
        "now":          _now,
        "bars":         bars_ad,
        "news":         news_ad,
        "edgar":        edgar_ad,
        "corp_actions": corp_ad,
        "own_history":  own_ad,
        "block_n":      block_n_ad,
        "derived":      derived_ad,
    }

    # 3a) direct raw-output capture per adapter (preserves audit dicts that
    # the sealed perception._datum strips). Independent demonstration that
    # each adapter actually fetched data, with the server's error surfaced
    # when a fetch failed.
    raw_dumps = {}

    def _safe_call(name, fn, *args):
        try:
            out = fn(*args)
        except Exception as e:
            return {"adapter_exception": repr(e)}
        if out is None:
            return {"value": None, "status": "RETURNED_NONE",
                    "note": "adapter returned None -> perception sentinels UNAVAILABLE"}
        return out

    raw_dumps["bars"]         = _safe_call("bars", bars_ad)
    raw_dumps["news"]         = _safe_call("news", news_ad)
    raw_dumps["edgar"]        = _safe_call("edgar", edgar_ad)
    raw_dumps["corp_actions"] = _safe_call("corp_actions", corp_ad)
    raw_dumps["own_history"]  = _safe_call("own_history", own_ad)
    raw_dumps["block_n"]      = _safe_call("block_n", block_n_ad)

    started = _now().isoformat()
    res = agent_loop.run_wake(deps, staging_ledger, e0=174.28,
                               live_block_n=True)
    finished = _now().isoformat()

    payload = res.get("payload") or {}
    blocks = payload.get("blocks") or {}

    # truncate huge row arrays in the raw dump to keep the audit file
    # readable (keep first 2 rows per adapter for evidence).
    def _truncate(d):
        if not isinstance(d, dict):
            return d
        out = dict(d)
        v = out.get("value")
        if isinstance(v, list):
            out["row_count"] = len(v)
            out["value"] = v[:2]
        return out
    raw_dumps = {k: _truncate(v) for k, v in raw_dumps.items()}

    summary = {
        "wake_started_utc":  started,
        "wake_finished_utc": finished,
        "state":             res.get("state"),
        "staging_ledger":    str(staging_ledger),
        "sealed_tree":       str(SEALED),
        "live_block_n":      True,
        "raw_adapter_dumps": raw_dumps,
        "blocks": {},
    }
    for label in ("O_own_account", "A_market_bars", "C_news_catalyst",
                  "E_edgar_primary", "C2_corporate_actions",
                  "FGHIJKL_derived", "M_own_history", "N_social"):
        summary["blocks"][label] = _block_summary(label, blocks.get(label))

    # also surface any ledger entries written by the wake (chain check)
    summary["ledger_entries"] = []
    if staging_ledger.is_file():
        for ln in staging_ledger.read_text("utf-8").splitlines():
            if ln.strip():
                summary["ledger_entries"].append(json.loads(ln).get("kind"))

    out = Path("/tmp/smoke_wake_v3_result.json")
    out.write_text(json.dumps(summary, default=str, indent=2,
                                ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
