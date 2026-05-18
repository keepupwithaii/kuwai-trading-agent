#!/usr/bin/env python3
"""
The sealed, agent-unreachable, agent-blind catastrophic floor (102 R2.4,
95, signed scalar 0.45 per 67 2026-05-18 "happy with 45%").

One input (own reconciled equity), one threshold (0.45 * E0), one action
(HALT), one-directional against E0, NEVER re-based intra-run. The agent has no
tool to read, alter, or disable this, and the perception payload never includes
floor distance. Standard library only.

E0 is the account's settled equity captured ONCE at the publish-precedes-trade
boundary (the seal step, Maran-gated). Until that boundary it is a sealed
placeholder and the harness writes a STATUS note; floor_check is structurally
present and tested with synthetic E0 in the conformance gate, but the real E0
is only ever captured at the Maran-triggered seal, never by the build.
"""
from __future__ import annotations

FLOOR_SCALAR = 0.45  # signed by Maran (67 2026-05-18); sealed constant

# Sentinel meaning "E0 not yet captured at the publish-precedes-trade
# boundary". The build/conformance use a synthetic E0; the real value is
# captured only at the Maran-triggered seal step. Never re-based once set.
E0_UNSET = None


def floor_value(e0: float) -> float:
    return FLOOR_SCALAR * float(e0)


def floor_check(equity: float, e0) -> tuple[bool, str]:
    """Return (breached, detail). breached True => HALT-and-log, submit no
    new orders ever again until a human acts at the next weekly boundary; do
    not liquidate, flatten, re-size, or re-enter. The process exits and does
    not restart intra-week.

    Raises if E0 is unset: a live run must never evaluate the floor without a
    captured E0 (that would be a FLOOR-PREDICATE-FAULT bug class). The
    conformance gate passes a synthetic E0 explicitly.
    """
    if e0 is E0_UNSET:
        raise RuntimeError(
            "floor_check called before E0 captured at the seal boundary")
    f = floor_value(e0)
    if float(equity) <= f:
        return True, f"floor_breach equity={equity} F={f} E0={e0} scalar={FLOOR_SCALAR}"
    return False, f"floor_ok equity={equity} F={f} E0={e0}"
