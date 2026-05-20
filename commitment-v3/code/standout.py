#!/usr/bin/env python3
"""
The deterministic, read-only standout-events report generator (142 §8 + the
145 §6 / 146 §3 deltas). Downstream content tool. It is NOT part of the sealed
machine and cannot make the agent trade for the highlight reel: it reads ONLY
the A5-stripped broadcast-safe projection and never council internals, audit
fields, or the per-wake bright-line fault CLASS. Standard library only.

Deltas applied:
  - MF-7: no per-wake bright-line fault CLASS label; only the coarse generic
    "a bright-line HALT occurred this wake".
  - S-COUNCIL-CONTESTED dropped from the type enum (Q5 resolved).
  - Q3 vocabulary: plain neutral, no softening words for losses; symmetric.
  - Q4 model-prose pass: OFF by default (deterministic templates, ~$0).
  - honest-number: exact, unrounded; truthful empty state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# Q1 thresholds (146 §3 recommended defaults; sealed content tuning).
C_PCT = 0.60        # bold-concentration: >=60% of equity in one symbol
M_PCT = 0.10        # large P&L move: +/-10% either direction
F_BUFFER = 0.10     # near-floor: within 10% of the 0.45*E0 floor

TYPE_ENUM = ("S-BOLD-CONCENTRATION", "S-LARGE-PNL-MOVE", "S-NEAR-FLOOR",
             "S-HALT")  # S-COUNCIL-CONTESTED intentionally absent (Q5)


def build_standout(projection: dict, equity: float, e0_floor: float | None,
                   pnl_pct_since_start: float | None,
                   top_concentration_frac: float | None) -> dict:
    """Pure function. `projection` is the broadcast-safe projection only.
    Returns the stable JSON document (one per wake)."""
    events: list[dict] = []

    if (top_concentration_frac is not None
            and top_concentration_frac >= C_PCT):
        events.append({"type": "S-BOLD-CONCENTRATION",
                       "detail": f"single-symbol weight {top_concentration_frac*100:.6f}% of equity"})

    if pnl_pct_since_start is not None and abs(pnl_pct_since_start) >= M_PCT:
        events.append({"type": "S-LARGE-PNL-MOVE",
                       "detail": f"the account moved {pnl_pct_since_start*100:+.6f}%"})

    if e0_floor is not None and equity <= e0_floor * (1 + F_BUFFER):
        events.append({"type": "S-NEAR-FLOOR",
                       "detail": "equity is within the near-floor buffer"})

    # MF-7: coarse generic only. No fired class label, ever.
    if projection.get("bright_line_halt_occurred"):
        events.append({"type": "S-HALT",
                       "detail": "the sealed machine's own bright-line check stopped it this wake"})

    for ev in events:
        if ev["type"] not in TYPE_ENUM:
            raise ValueError(f"standout type not in enum: {ev['type']}")

    return {
        "schema": "standout-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_wake_at": projection.get("assembled_at"),
        "feed_state": "ok",
        "standout_events": events,          # may be empty (honest quiet state)
        "model_prose_pass": False,          # Q4 OFF by default
    }


def write_standout(path, doc: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, ensure_ascii=False, indent=2)
