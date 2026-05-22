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
  populate perception adapters (8 blocks) -> assemble perception
  (deterministic) -> ONE model decision call -> record_reasoning (logged
  verbatim) -> grounding linter -> council -> feasibility gate ->
  deterministic client_order_id idempotent submit -> hash-chained log ->
  heartbeat -> broadcast-safe projection -> standout.

Injected dependencies (so the conformance gate can STUB the model, broker,
and per-block adapters with no real inference, no order, no network):
  deps = {
    "broker":   object with .account(), .reconcile(), .submit(order,coid),
    "decider":  callable(payload, sealed_prompt) -> reasoning_envelope
                + proposed_orders   (the ONE model call; stubbed in gate),
    "synth":    callable(attempt=) -> raw council-v1 (stubbed in gate),
    "clock":    object with .rth_open() -> bool,
    "now":      callable() -> datetime (optional; used for O_own_account
                staleness gate and adapter as_of timestamps),
    "bars":         callable() -> {value, as_of, status} | None,
    "news":         callable() -> {value, as_of, status} | None,
    "edgar":        callable() -> {value, as_of, status} | None,
    "corp_actions": callable() -> {value, as_of, status} | None,
    "derived":      callable(payload_so_far) -> {value, as_of, status} | None,
    "own_history":  callable() -> {value, as_of, status} | None,
    "block_n":      callable() -> {value, as_of, status} | None,
  }

v3 amendments to v2 (closed-reason "defined bug class", architect-authorised
2026-05-20):

  1. PERCEPTION-ADAPTER WIRING (defined bug class). v2 only populated
     raw["account"]; the other seven perception blocks were never wired and
     fell back to UNAVAILABLE sentinels every wake. v3 calls a deps adapter
     for each block (bars, news, edgar, corp_actions, derived, own_history,
     block_n) and merges the parsed rows into `raw` before perception
     assembly. The channels, pinned Apify build hashes, perception schema,
     and the sentinel discipline for genuinely-absent data are unchanged;
     the fix is wiring only, never membership.

  2. O_OWN_ACCOUNT FRESHNESS GATE. If broker.account()'s as_of is older
     than wake_now - 60s, mark the block status=STALE rather than passing
     stale data as current. The sealed prompt's "you are shown your
     account's real balance" promise: STALE is honest, silent-stale is not.

  3. LOOP_FAILSAFE BOUNDED RETRY (defined bug class). v2 committed terminal
     HALT on any unhandled exception, including transient provider 5xx
     (a single Anthropic 529 took the agent down for the week). v3 retries
     transient 5xx (502, 503, 504, 529) up to three times per wake with
     backoff 5s, 30s, 120s. On retry-budget exhaustion the wake exits
     WITHOUT committing terminal HALT (a non-HALT TRANSIENT_FAIL entry is
     logged instead), and the next scheduled wake proceeds normally. Auth
     (401/403), other 4xx, parse errors, and model-side fatals still
     commit terminal HALT immediately, no change.
"""
from __future__ import annotations

import hashlib
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone
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

# -- LOOP_FAILSAFE bounded-retry policy (v3 amendment, sealed) -----------
TRANSIENT_5XX = (502, 503, 504, 529)
BACKOFFS_S = (5, 30, 120)     # three retries, three backoffs
OWN_ACCOUNT_STALE_S = 60      # O_own_account freshness gate per spec


class TransientExhausted(Exception):
    """Three retries against transient provider 5xx all failed. The wake
    exits without committing terminal HALT; next wake proceeds normally."""


def _is_transient_5xx(exc: BaseException) -> bool:
    return (isinstance(exc, urllib.error.HTTPError)
            and getattr(exc, "code", None) in TRANSIENT_5XX)


def _with_retry(fn, *args, **kwargs):
    """Call fn with up to len(BACKOFFS_S) retries on transient 5xx. Non-5xx
    exceptions propagate unchanged (4xx/auth/parse/model-fatal still HALT).
    On retry-budget exhaustion raises TransientExhausted, which the loop
    catches to exit-without-HALT.

    time.sleep is referenced through the module (not via a default arg) so
    the conformance gate can monkey-patch it for fast deterministic runs.
    """
    last = None
    for delay in (0, *BACKOFFS_S):
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except urllib.error.HTTPError as e:
            if _is_transient_5xx(e):
                last = e
                continue
            raise
    raise TransientExhausted(repr(last))


def deterministic_client_order_id(strategy_id: str, trade_date: str,
                                  intent: dict) -> str:
    raw = f"{strategy_id}|{trade_date}|{sorted(intent.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# -- Perception-adapter wiring (v3 amendment, sealed) --------------------
# Maps deps key -> (raw[] key used by perception.assemble, human label for
# logging). The seven non-account blocks; O_own_account is wired separately
# because it carries the freshness gate.
_ADAPTER_KEYS = (
    ("bars",         "bars",         "A_market_bars"),
    ("news",         "news",         "C_news_catalyst"),
    ("edgar",        "edgar",        "E_edgar_primary"),
    ("corp_actions", "corp_actions", "C2_corporate_actions"),
    ("own_history",  "own_history",  "M_own_history"),
    ("block_n",      "block_n",      "N_social"),
)


def _now_utc(deps: dict) -> datetime:
    now_fn = deps.get("now")
    if callable(now_fn):
        return now_fn()
    return datetime.now(timezone.utc)


def _parse_iso(ts) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    s = str(ts)
    # handle trailing Z (Python 3.10 fromisoformat doesn't accept it
    # without rstrip until 3.11; be conservative).
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _gate_account_freshness(acct: dict, wake_now: datetime) -> dict:
    """If acct.as_of is older than wake_now - OWN_ACCOUNT_STALE_S, mark the
    block STALE. Honest STALE rather than silent stale-as-current."""
    as_of_dt = _parse_iso(acct.get("as_of"))
    if as_of_dt is None:
        # no as_of at all is itself stale: status STALE so the model sees it.
        acct = dict(acct)
        acct["status"] = "STALE"
        return acct
    if wake_now - as_of_dt > timedelta(seconds=OWN_ACCOUNT_STALE_S):
        acct = dict(acct)
        acct["status"] = "STALE"
    return acct


def _call_adapter(fn, *args):
    """Call an adapter callable through the retry helper. None return,
    AttributeError on missing fn, or non-transient exception -> block is
    sentinelled UNAVAILABLE by perception.assemble. TransientExhausted
    bubbles up so the loop can exit-without-HALT (it is a wake-level
    decision-path failure, not a per-block missing-data condition)."""
    if not callable(fn):
        return None
    try:
        v = _with_retry(fn, *args)
    except TransientExhausted:
        raise
    except Exception:
        return None
    return v


def run_wake(deps: dict, log_path: Path, *, e0, strategy_id="commitment-v3",
             live_block_n: bool = False) -> dict:
    """Run exactly one wake. Returns a summary dict. Never raises into the
    scheduler: non-transient unhandled conditions become a terminal HALT
    (fail-safe, 27 §5 doctrine). Transient provider 5xx do NOT HALT after
    the v3 bounded-retry amendment.
    """
    log = HashLog(log_path)
    if log.is_halted():
        return {"state": "ALREADY_HALTED", "action": "none"}

    broker = deps["broker"]
    clock = deps["clock"]
    try:
        wake_now = _now_utc(deps)

        # Health gates (27 §1): auth + account ACTIVE, clock, data freshness.
        # broker.account is wrapped in _with_retry so a transient Alpaca 5xx
        # retries inside the wake instead of halting the run.
        acct = _with_retry(broker.account)
        if acct is None or acct.get("status") not in ("ACTIVE", "OK"):
            log.append_halt("AUTH_FAIL_OR_INACTIVE", {"acct": acct})
            return {"state": "HALT", "reason": "auth_fail"}

        # Reconcile-before-decide: broker truth is ground truth.
        recon = _with_retry(broker.reconcile)

        rth_open = clock.rth_open()

        # B1 fix (carried from v2): merge broker.account() into
        # recon["raw"]["account"] so perception.assemble sees ALL SIX
        # spec-required own-account keys.
        raw = recon.get("raw", {}) or {}
        raw_acct = raw.get("account", {}) or {}
        merged_acct = {
            "equity": acct.get("equity", 0.0),
            "cash": acct.get("cash", acct.get("settled_cash", 0.0)),
            "settled_cash": acct.get("settled_cash", 0.0),
            "positions": raw_acct.get("positions", []),
            "prior_wake_orders": acct.get("prior_wake_orders", []),
            "pdt_daytrade_count": acct.get("pdt_daytrade_count", 0),
            "as_of": acct.get("as_of"),
            "status": acct.get("status", "OK"),
        }
        # v3 #2: STALE gate (>60s old -> status STALE, never silent stale).
        merged_acct = _gate_account_freshness(merged_acct, wake_now)
        raw["account"] = merged_acct
        recon["raw"] = raw

        # v3 #1: PERCEPTION-ADAPTER WIRING. Call each per-block adapter; map
        # parsed result into raw[<key>] so perception.assemble produces
        # populated blocks. Adapter failure or absence -> raw[key] stays
        # None and perception sentinels UNAVAILABLE (honest, not fake).
        for dep_key, raw_key, _label in _ADAPTER_KEYS:
            if dep_key == "block_n" and not live_block_n:
                # SCRAPE_CHANNELS.txt: scrape_in_paper_cycle=never,
                # scrape_in_conformance=never. live_block_n False -> skip.
                continue
            v = _call_adapter(deps.get(dep_key))
            if v is not None:
                raw[raw_key] = v

        # Assemble the deterministic perception payload (no floor distance).
        payload = perception_mod.assemble(raw, live_block_n=live_block_n)

        # FGHIJKL_derived runs on the assembled payload (it transforms the
        # upstream blocks). Call it last and re-assemble if it returned a
        # populated result, so the derived block reaches the model.
        derived_fn = deps.get("derived")
        if callable(derived_fn):
            v = _call_adapter(lambda: derived_fn(payload))
            if v is not None:
                raw["derived"] = v
                payload = perception_mod.assemble(raw,
                                                  live_block_n=live_block_n)

        log.append("PAYLOAD", {"schema": payload.get("schema")})

        # The ONE model decision call (STUBBED in the conformance gate).
        # Wrapped in _with_retry so a transient Anthropic 5xx (e.g. 529)
        # retries within the wake; non-transient still propagates -> HALT.
        sealed_prompt = (SEALED_ROOT / "SYSTEM_PROMPT.md").read_text("utf-8")
        decision = _with_retry(deps["decider"], payload, sealed_prompt)
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
            # synth wrapped so a transient 5xx in the synth path is retried
            # inside the council (council's own halt-safe still triggers on
            # crashes/garble that aren't 5xx).
            synth_raw = deps["synth"]

            def _wrapped_synth(attempt):
                return _with_retry(synth_raw, attempt)

            cres = council_mod.run_council(
                payload, reasoning_envelope, lint, _wrapped_synth)
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
                        "projection": proj, "payload": payload}

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
                    sub = _with_retry(broker.submit, order, coid)
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
        return {"state": "OK", "results": results, "projection": proj,
                "payload": payload}

    except TransientExhausted as exc:
        # v3 #3: bounded-retry budget exhausted on a transient provider 5xx.
        # Do NOT commit terminal HALT. Log a non-HALT TRANSIENT_FAIL entry
        # so the chain records the event, and let the next scheduled wake
        # proceed normally.
        try:
            HashLog(log_path).append("TRANSIENT_FAIL", {"err": repr(exc)})
        except Exception:
            pass
        return {"state": "TRANSIENT_FAIL", "reason": repr(exc)}

    except Exception as exc:  # fail-safe: never improvise, HALT-and-log
        try:
            HashLog(log_path).append_halt("LOOP_FAILSAFE", {"err": repr(exc)})
        except Exception:
            pass
        return {"state": "HALT", "reason": f"failsafe:{exc!r}"}
