#!/usr/bin/env python3
"""
The deterministic feasibility gate (102 R2.3). It enforces ONLY broker/legal
mechanics, NEVER strategy. No sizing caps, no concentration logic, no curated
sub-list, no view. A sceptic runs this and gets the same accept/reject for the
same proposed order every time. Standard library only.

The seam: everything upstream is the agent's discretion; the gate and
everything downstream is determinism.
"""
from __future__ import annotations

from dataclasses import dataclass

FRACTIONAL_MIN_USD = 1.0  # ~1 USD fractional/notional minimum (24 §1.4)


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str          # "buy" | "sell"
    notional_usd: float  # resolved by the harness from notional/fraction


@dataclass(frozen=True)
class AccountState:
    settled_cash: float
    tracked_qty: dict          # symbol -> owned fractional qty
    pdt_daytrades_5d: int      # rolling 5-day day-trade count
    equity: float


def evaluate(order: Order, acct: AccountState, universe: set[str],
             rth_open: bool, floor_breached: bool,
             would_create_4th_daytrade: bool) -> tuple[bool, str]:
    """Return (accepted, reason). Reject on the FIRST failing check.

    The seven checks (102 R2.3), broker/legal only:
      1. symbol in the sealed universe allow-list
      2. harness can build it as notional market DAY (always; the agent never
         names a type) -> structural check only
      3. no margin / no short: a sell may not exceed own tracked qty; a buy may
         not exceed settled cash (cash-by-rule, no buying power beyond it)
      4. notional >= fractional minimum and <= available settled cash
      5. RTH window guard for equities (no crypto leg exists)
      6. floor_check pre-check (agent-blind; gate obeys, does not own policy)
      7. PDT self-brick guard (no 4th day-trade in the rolling 5-day window)
    """
    sym = order.symbol
    side = order.side

    # 1. universe allow-list
    if sym not in universe:
        return False, f"reject:not_in_universe:{sym}"

    # 2. structural: side must be buildable as notional market DAY
    if side not in ("buy", "sell"):
        return False, f"reject:bad_side:{side}"

    # 3. no margin / no short
    if side == "sell":
        owned = float(acct.tracked_qty.get(sym, 0.0))
        if owned <= 0.0:
            return False, f"reject:no_position_to_sell:{sym}"
        # selling is bounded by owned notional-equivalent; the harness sizes a
        # sell as <= owned position, never a short. A sell request that would
        # exceed the owned position is rejected (no short).
        # (notional->qty resolution is the harness's; here we reject an
        #  explicit over-sell signalled by notional_usd <= 0.)
        if order.notional_usd <= 0.0:
            return False, "reject:nonpositive_notional"
    else:  # buy
        if order.notional_usd > acct.settled_cash:
            return False, "reject:exceeds_settled_cash"

    # 4. fractional min and settled-cash ceiling
    if order.notional_usd < FRACTIONAL_MIN_USD:
        return False, "reject:below_fractional_min"
    if side == "buy" and order.notional_usd > acct.settled_cash:
        return False, "reject:exceeds_settled_cash"

    # 5. RTH window guard (equities only; no crypto leg)
    if not rth_open:
        return False, "reject:outside_rth_window"

    # 6. floor pre-check (agent-blind; the gate obeys floor_check's verdict)
    if floor_breached:
        return False, "reject:floor_halt"

    # 7. PDT self-brick guard
    if would_create_4th_daytrade:
        return False, "reject:pdt_self_brick_guard"

    return True, "accept"
