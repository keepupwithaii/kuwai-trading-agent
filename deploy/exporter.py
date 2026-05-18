#!/usr/bin/env python3
"""
Deploy-side dashboard exporter. NOT inside the sealed tree (read-only of the
ledger; writes a downstream JSON the dashboard polls; one-directional A5).

Writes /var/lib/kuwai/state.partial.json after every wake. The local bridge on
Maran's Mac merges in the agent-count from the synced vault agent-ledger.md
and produces the final dashboard/data/state.json. The VPS does NOT know the
authoritative agent count (vault not synced here); writing 'agents' from this
side would breach 'do not invent the number'.

Schema: see dashboard/data/state.json schema notes. Honest-number spine; the
broadcast-safe projection only (A5). Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path(os.environ.get("KUWAI_LEDGER", "/var/lib/kuwai/ledger.log"))
OUT = Path(os.environ.get("KUWAI_STATE_OUT",
                          "/var/lib/kuwai/state.partial.json"))
MAX_LOG_ROWS = 5


def _read_entries() -> list[dict]:
    if not LEDGER.exists():
        return []
    out: list[dict] = []
    with LEDGER.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _format_log_row(e: dict) -> dict | None:
    kind = e.get("kind", "")
    body = e.get("body", {}) or {}
    ts = e.get("ts_utc", "")
    try:
        dt = datetime.fromisoformat(ts).astimezone(timezone.utc)
        # render in plain UTC HH:MM (broadcast-safe; no PII, no full date)
        t = dt.strftime("%d %b · %H:%M UTC")
    except Exception:
        t = ts
    if kind == "ORDER_SUBMIT":
        side = (body.get("order", {}) or {}).get("side", "").upper()
        if side not in ("BUY", "SELL"):
            return None
        sym = (body.get("order", {}) or {}).get("symbol", "")
        # honest: log the action and symbol, no rounded hero figure
        return {"t": t, "act": side,
                "n": f"Submitted {side.lower()} order for {sym}"}
    if kind == "ORDER_REJECT":
        sym = (body.get("order", {}) or {}).get("symbol", "")
        reason = body.get("reason", "")
        return {"t": t, "act": "HOLD",
                "n": f"Order on {sym} rejected by the gate: {reason}"}
    if kind == "HOLD":
        return {"t": t, "act": "HOLD", "n": "Considered the wake, did not act"}
    if kind == "COUNCIL_HALT":
        return {"t": t, "act": "HOLD",
                "n": "Sealed reviewer stopped the trade; HALTed for the weekly"}
    if kind == "FLOOR_BREACH" or kind == "HALT":
        return {"t": t, "act": "HOLD",
                "n": "The sealed machine's own bright-line check stopped it"}
    return None


def main() -> int:
    entries = _read_entries()
    # equity: from the most recent HEARTBEAT body
    equity = None
    for e in reversed(entries):
        if e.get("kind") == "HEARTBEAT":
            equity = float((e.get("body") or {}).get("equity", 0.0))
            break
    # since_trade_s: from the most recent ORDER_SUBMIT
    since = 0
    last_fill_ts = None
    last_trade_id = None
    for e in reversed(entries):
        if e.get("kind") == "ORDER_SUBMIT":
            last_fill_ts = e.get("ts_utc")
            last_trade_id = e.get("entry_hash")
            break
    if last_fill_ts:
        try:
            since = int((datetime.now(timezone.utc) -
                          datetime.fromisoformat(last_fill_ts)).total_seconds())
        except Exception:
            since = 0
    # log: latest N rows that map cleanly
    log_rows: list[dict] = []
    for e in reversed(entries):
        row = _format_log_row(e)
        if row:
            log_rows.append(row)
        if len(log_rows) >= MAX_LOG_ROWS:
            break
    if not log_rows:
        log_rows = [{"t": "—", "act": "HOLD",
                      "n": "First wake; no orders yet"}]

    seed = float(os.environ.get("KUWAI_E0", "150.0"))
    state = {
        "schema": "kuwai-state-v1",
        "_sample": False,
        "feed_state": "ok",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "equity": equity if equity is not None else seed,
        "since_trade_s": since,
        "agents": None,  # the local bridge fills this from agent-ledger.md
        "hash": None,    # filled by the seal step; never a placeholder
        "next_event": None,         # local bridge / catalyst_queue owns this
        "catalyst_queue": None,
        "gta_launch": "2026-11-19T00:00:00+11:00",
        "log": log_rows,
        "last_trade_id": last_trade_id,
        "standout_events": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, sort_keys=True, ensure_ascii=False,
                              indent=2) + "\n", encoding="utf-8")
    print(f"exporter wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
