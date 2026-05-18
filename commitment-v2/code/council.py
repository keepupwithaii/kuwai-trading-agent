#!/usr/bin/env python3
"""
The sealed pre-trade council (141/145/146/151). Runs after record_reasoning +
the grounding linter, before the feasibility gate and any order, trade-intent
wakes only. Inputs are exactly the three sealed in-process objects: the sealed
payload snapshot, the trader's recorded reasoning envelope, the linter verdict.
No new external surface. Standard library only.

The R-1 bind (151 §1.2), enforced here:
  - The one bounded SYNTHESISER schema-repair retry fires ONLY on a
    schema-structural malformation (output that fails parsing, enum, or shape
    conformance, or an a-f fault `why` that does not name a closed fault
    token).
  - A parse-valid (g) `why` that fails the bound cited-item-to-step shape is a
    SUBSTANTIVE guard rejection: it HALTs immediately with ZERO retries,
    exactly as it did before MF-4 half-2 was added. The retry never re-asks a
    guard-rejected substantive (g).
  - Double schema-structural garble -> the unchanged 141 §8 terminal HALT.
Fail-safe-to-HALT on every error/timeout/crash, never a silent pass and never
a silent caution brake.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SEALED_ROOT = Path(__file__).resolve().parent.parent

DIMS = ("a_grounded", "b_no_future_bet", "c_not_injection_steered",
        "d_no_must_never_breach", "e_not_account_ending",
        "f_no_self_sabotage", "g_reasoning_holds")
BRIGHT_LINE = ("a_grounded", "b_no_future_bet", "d_no_must_never_breach",
               "e_not_account_ending", "f_no_self_sabotage")  # hard-HALT
ADVISORY = ("c_not_injection_steered", "g_reasoning_holds")

# The closed bound-(g) cited-item-to-step incoherence shape (SCHEMA.md / 146).
_G_SHAPE = re.compile(
    r"^from cited item .+, to action .+, the stated link is .+, "
    r"and .+ is absent or contradicted by cited item .+$",
    re.IGNORECASE | re.DOTALL,
)


def _load_fault_tokens() -> set[str]:
    toks: set[str] = set()
    txt = (SEALED_ROOT / "COUNCIL" / "FAULT_LIST.txt").read_text("utf-8")
    for ln in txt.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        toks.add(s.split("=", 1)[0].strip())
    return toks


@dataclass(frozen=True)
class CouncilResult:
    disposition: str          # "proceed" | "halt"
    overall: str              # "pass" | "fault"
    retries_consumed: int     # R-1: 0 on substantive reject, <=1 on garble
    halt_reason: str          # "" if proceed
    advisory: dict            # advisory (c, g) verdicts surfaced to the trader
    report: dict | None       # the parsed council-v1 report, if any


class SchemaStructuralError(Exception):
    """Output fails parsing, enum, or shape (the retry-eligible case)."""


class SubstantiveRejection(Exception):
    """A parse-valid (g) `why` violates the bound shape: HALT now, 0 retries."""


def _parse_and_guard(raw, fault_tokens: set[str]) -> dict:
    """Deterministic post-parse guard.

    Raises SchemaStructuralError for the retry-eligible class.
    Raises SubstantiveRejection for a parse-valid bound-(g)-violating report
    (immediate HALT, zero retries -- the anti-caution-creep wall working).
    Returns the validated report dict otherwise.
    """
    try:
        rep = raw if isinstance(raw, dict) else json.loads(raw)
    except Exception as exc:  # unparseable
        raise SchemaStructuralError(f"unparseable: {exc}")

    dims = rep.get("dimensions")
    if not isinstance(dims, dict):
        raise SchemaStructuralError("missing dimensions object")
    # No field outside the closed schema (the wall): exactly the 7 dims.
    if set(dims.keys()) != set(DIMS):
        raise SchemaStructuralError("dimension set is not exactly council-v1")
    for d in DIMS:
        cell = dims.get(d)
        if not isinstance(cell, dict):
            raise SchemaStructuralError(f"{d} not an object")
        verdict = cell.get("verdict")
        why = cell.get("why")
        if verdict not in ("pass", "fault"):
            raise SchemaStructuralError(f"{d} verdict enum invalid")
        if not isinstance(why, str) or not why.strip():
            raise SchemaStructuralError(f"{d} why missing")
        if verdict == "fault":
            if d == "g_reasoning_holds":
                # Parse-valid but shape-violating (g) fault == substantive
                # guard rejection: HALT now, ZERO retries (R-1 bind).
                if not _G_SHAPE.match(why.strip()):
                    raise SubstantiveRejection(
                        "bound-(g) shape violated by a parse-valid report")
            else:
                # a-f fault must name a closed fault token, else it is a
                # schema-structural malformation (retry-eligible).
                if not any(tok in why for tok in fault_tokens):
                    raise SchemaStructuralError(
                        f"{d} fault why names no closed fault token")
    # The model must not author overall/disposition; if present they are
    # ignored (harness derives them) but their presence is not a garble.
    return rep


def _derive(rep: dict) -> tuple[str, str, str, dict]:
    dims = rep["dimensions"]
    advisory = {}
    halt_reason = ""
    overall = "pass"
    disposition = "proceed"
    for d in BRIGHT_LINE:
        if dims[d]["verdict"] == "fault":
            overall = "fault"
            disposition = "halt"
            halt_reason = f"bright_line_fault:{d}:{dims[d]['why']}"
            break
    for d in ADVISORY:
        if dims[d]["verdict"] == "fault":
            advisory[d] = dims[d]["why"]
    return disposition, overall, halt_reason, advisory


def run_council(payload: dict, reasoning_envelope: dict, linter_verdict: dict,
                synthesiser_callable) -> CouncilResult:
    """Run the council. synthesiser_callable() -> raw SYNTHESISER output
    (str or dict). It is the ONLY model surface here and is STUBBED in the
    conformance gate (no real inference). PRO/CON are folded into the
    synthesiser's sealed inputs by the caller; this function owns the
    deterministic guard, the R-1 retry routing, and the fail-safe.
    """
    fault_tokens = _load_fault_tokens()
    retries = 0
    try:
        try:
            raw = synthesiser_callable(attempt=1)
            rep = _parse_and_guard(raw, fault_tokens)
        except SubstantiveRejection as sr:
            # R-1: immediate HALT, ZERO retries. The wall did its job.
            return CouncilResult("halt", "fault", 0,
                                  f"substantive_guard_rejection:{sr}",
                                  {}, None)
        except SchemaStructuralError:
            # The one bounded schema-repair retry (MF-4 half-2).
            retries = 1
            try:
                raw = synthesiser_callable(attempt=2)
                rep = _parse_and_guard(raw, fault_tokens)
            except SubstantiveRejection as sr:
                # Even on the repair attempt, a substantive (g) rejection
                # HALTs (still zero further retries; the wall holds).
                return CouncilResult("halt", "fault", retries,
                                     f"substantive_guard_rejection:{sr}",
                                     {}, None)
            except SchemaStructuralError as se2:
                # Double garble -> unchanged 141 §8 terminal HALT.
                return CouncilResult("halt", "fault", retries,
                                     f"double_schema_garble:{se2}", {}, None)
        disposition, overall, halt_reason, advisory = _derive(rep)
        return CouncilResult(disposition, overall, retries, halt_reason,
                             advisory, rep)
    except Exception as exc:  # any other error/timeout/crash -> fail-safe HALT
        return CouncilResult("halt", "fault", retries,
                             f"council_failsafe_halt:{exc!r}", {}, None)
