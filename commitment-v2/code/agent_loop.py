#!/usr/bin/env python3
"""
The deterministic harness loop (102 R2.1 / 27). One single-program runtime on
the one isolated real-money account. The agent's only reach is the three
tools; everything safety / idempotency / floor / change-surface is in this
unreachable harness. Standard library only.

Determinism seam: everything upstream of the feasibility gate is the agent's
discretion; the gate and everything downstream is deterministic.

Order of a wake:
  flock -> auth/clock/data health gates -> reconcile-before-decide ->
  assemble perception (deterministic) -> ONE model decision call ->
  record_reasoning (logged verbatim) -> grounding linter -> council ->
  feasibility gate -> deterministic client_order_id idempotent submit ->
  hash-chained log -> heartbeat -> broadcast-safe projection -> standout.

Injected dependencies (so the conformance gate can STUB the model and broker
with no real inference, no order, no network, and the paper cycle can use the
real model on the PAPER key):
  deps = {
    "broker":   object with .account(), .reconcile(), .submit(order,coid),
    "decider":  callable(payload, sealed_prompt) -> reasoning_envelope
                + proposed_orders   (the ONE model call; stubbed in gate),
    "synth":    callable(attempt=) -> raw council-v1 (stubbed in gate),
    "clock":    object with .rth_open() -> bool,
    "now":      callable() -> datetime,
  }
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# The runtime must not write __pycache__ into the sealed tree (keeps the
# canonical-tree hash stable; C-MANIFEST demands an exact member set).
sys.dont_write_bytecode = True

import council as council_mod
import feasibility_gate as fg
import floor as floor_mod
import grounding_linter
import manifest_io
import perception as perception_mod
from hashlog import HashLog

SEALED_ROOT = Path(__file__).resolve().parent.parent


def deterministic_client_order_id(strategy_id: str, trade_date: str,
                                  intent: dict) -> str:
    raw = f"{strategy_id}|{trade_date}|{sorted(intent.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def run_wake(deps: dict, log_path: Path, *, e0, strategy_id="commitment-v2",
             live_block_n: bool = False) -> dict:
    """Run exactly one wake. Returns a summary dict. Never raises into the
    scheduler: any unhandled condition becomes a terminal HALT (fail-safe,
    27 §5 doctrine: skip-and-reconcile or halt-and-alert, never improvise).
    """
    log = HashLog(log_path)
    if log.is_halted():
        return {"state": "ALREADY_HALTED", "action": "none"}

    broker = deps["broker"]
    clock = deps["clock"]
    try:
        # Health gates (27 §1): auth + account ACTIVE, clock, data freshness.
        acct = broker.account()
        if acct is None or acct.get("status") not in ("ACTIVE", "OK"):
            log.append_halt("AUTH_FAIL_OR_INACTIVE", {"acct": acct})
            return {"state": "HALT", "reason": "auth_fail"}

        # Reconcile-before-decide: broker truth is ground truth.
        recon = broker.reconcile()

        rth_open = clock.rth_open()

        # B1 fix (defined bug class per WEEKLY-POLICY: harness was assembling
        # the perception payload without the full own-account state, so the
        # sealed prompt's "you are shown your account's real balance" promise
        # was not met). Merge broker.account() into recon["raw"]["account"]
        # so perception.assemble sees ALL SIX spec-required own-account keys:
        # equity, cash, settled_cash, positions, prior_wake_orders,
        # pdt_daytrade_count. Positions arrive from reconcile; the other
        # five come from the account() call.
        raw = recon.get("raw", {}) or {}
        raw_acct = raw.get("account", {}) or {}
        raw["account"] = {
            "equity": acct.get("equity", 0.0),
            "cash": acct.get("cash", acct.get("settled_cash", 0.0)),
            "settled_cash": acct.get("settled_cash", 0.0),
            "positions": raw_acct.get("positions", []),
            "prior_wake_orders": acct.get("prior_wake_orders", []),
            "pdt_daytrade_count": acct.get("pdt_daytrade_count", 0),
            "as_of": acct.get("as_of"),
            "status": acct.get("status", "OK"),
        }
        recon["raw"] = raw

        # Assemble the deterministic perception payload (no floor distance).
        payload = perception_mod.assemble(raw, live_block_n=live_block_n)
        log.append("PAYLOAD", {"schema": payload.get("schema")})

        # The ONE model decision call (STUBBED in the conformance gate).
        sealed_prompt = (SEALED_ROOT / "SYSTEM_PROMPT.md").read_text("utf-8")
        decision = deps["decider"](payload, sealed_prompt)
        reasoning_envelope = decision.get("reasoning_envelope", {})
        proposed = decision.get("proposed_orders", [])

        # record_reasoning logged verbatim (narration/audit; never gates).
        log.append("RECORD_REASONING", {"envelope": reasoning_envelope})

        # Grounding linter (never blocks an order; binary grounded in chain).
        lint = grounding_linter.lint(reasoning_envelope, payload)
        log.append("GROUNDING", lint)

        # Floor pre-check (agent-blind; harness owns it). e0 must be captured.
        equity = float(acct.get("equity", 0.0))
        floor_breached, floor_detail = floor_mod.floor_check(equity, e0)
        if floor_breached:
            log.append_halt("FLOOR_BREACH", {"detail": floor_detail})
            return {"state": "HALT", "reason": "floor_breach"}

        results = []
        bright_line_halt = False
        if proposed:
            # Council runs on trade-intent wakes only, before any order.
            cres = council_mod.run_council(
                payload, reasoning_envelope, lint, deps["synth"])
            log.append("COUNCIL", {
                "disposition": cres.disposition,
                "overall": cres.overall,
                "retries_consumed": cres.retries_consumed,
                "halt_reason": cres.halt_reason,
                "advisory": cres.advisory,
            })
            if cres.disposition == "halt":
                bright_line_halt = True
                log.append_halt("COUNCIL_HALT", {"reason": cres.halt_reason})
                proj = perception_mod.broadcast_safe_projection(
                    payload, cres.disposition, bright_line_halt)
                return {"state": "HALT", "reason": "council_halt",
                        "projection": proj}

            # Feasibility gate per proposed order (deterministic).
            acct_state = fg.AccountState(
                settled_cash=float(acct.get("settled_cash", 0.0)),
                tracked_qty=acct.get("tracked_qty", {}),
                pdt_daytrades_5d=int(acct.get("pdt_daytrade_count", 0)),
                equity=equity)
            for o in proposed:
                order = fg.Order(symbol=o["symbol"], side=o["side"],
                                 notional_usd=float(o["notional_usd"]))
                accepted, reason = fg.evaluate(
                    order, acct_state,
                    set(manifest_io.read_universe()),
                    rth_open=rth_open, floor_breached=False,
                    would_create_4th_daytrade=bool(
                        o.get("would_create_4th_daytrade", False)))
                if accepted:
                    coid = deterministic_client_order_id(
                        strategy_id, recon.get("trade_date", ""), o)
                    sub = broker.submit(order, coid)  # idempotent
                    log.append("ORDER_SUBMIT",
                               {"coid": coid, "result": sub})
                    results.append({"order": o, "coid": coid, "sub": sub})
                else:
                    log.append("ORDER_REJECT", {"order": o, "reason": reason})
                    results.append({"order": o, "rejected": reason})
            disposition = cres.disposition
        else:
            log.append("HOLD", {"note": "no order proposed this wake"})
            disposition = "proceed"

        log.append("HEARTBEAT", {"equity": equity, "state": "OK"})
        proj = perception_mod.broadcast_safe_projection(
            payload, disposition, bright_line_halt)
        return {"state": "OK", "results": results, "projection": proj}

    except Exception as exc:  # fail-safe: never improvise, HALT-and-log
        try:
            HashLog(log_path).append_halt("LOOP_FAILSAFE", {"err": repr(exc)})
        except Exception:
            pass
        return {"state": "HALT", "reason": f"failsafe:{exc!r}"}
