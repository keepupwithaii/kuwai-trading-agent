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


def _a_grounded_check(rep: dict,
                      linter_verdict: dict) -> tuple[str, str]:
    """v6 (2026-05-29): inspect the a_grounded cell against the
    deterministic grounding-linter verdict.

    Returns one of three statuses:
      ("ok", "")        -- a_grounded.verdict is pass; nothing to do.
      ("genuine", why)  -- a_grounded:fault and its why NAMES (as
                            substring) at least one cite that the
                            linter ALSO flagged as unmatched
                            (citation_map[cite] == False). A genuine
                            grounding fault: the council should
                            terminate via the standard bright-line
                            path.
      ("spurious", why) -- a_grounded:fault but the why names no cite
                            that the linter flagged (or the linter
                            says grounded=true so there are no
                            flagged cites at all). Per v6 design: the
                            stochastic synth has nothing payload-
                            checkable to back this fault with. The
                            council retries up to A_GROUNDED_MAX_-
                            RETRIES times; if still spurious, the
                            fault resolves to pass.

    The substring check is intentional: synth wording is free-form so
    we look for the cite-key string (the citation_map key) verbatim
    inside the why. Identical heuristic style to bound-(g) shape.
    """
    a = (rep.get("dimensions") or {}).get("a_grounded") or {}
    if a.get("verdict") != "fault":
        return "ok", ""
    why = a.get("why") or ""
    citation_map = (linter_verdict or {}).get("citation_map") or {}
    unmatched_cites = [k for k, v in citation_map.items() if not v]
    # Genuine = synth names (substring) at least one cite the linter
    # itself flagged as unmatched. When linter grounded=true,
    # unmatched_cites is empty -> no possible genuine fault here.
    for uc in unmatched_cites:
        if uc and uc in why:
            return "genuine", why
    return "spurious", why


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


# v6 (2026-05-29): a_grounded retry cap. The bright-line a_grounded
# is judged by the stochastic synth (vs the deterministic linter);
# v5 wired it to zero retries with terminal HALT, which on Mon
# 2026-05-25T14:42Z fired terminally on a spurious synth draw
# (linter grounded=true, all 16 cites matched, model reasoning
# sound, but synth emitted a_grounded:fault:UNGROUNDED with no
# named cite). A non-deterministic judge on a zero-retry terminal
# kill cannot survive a trading week. v6 gives the council up to 2
# synth re-rolls on a spurious a_grounded fault (mirroring the R-1
# schema retry shape). A genuine fault -- synth names a specific
# cite the linter also flagged -- still terminates.
A_GROUNDED_MAX_RETRIES = 2


def run_council(payload: dict, reasoning_envelope: dict, linter_verdict: dict,
                synthesiser_callable) -> CouncilResult:
    """Run the council. synthesiser_callable(attempt=N) -> raw SYNTHESISER
    output (str or dict). It is the ONLY model surface here and is STUBBED
    in the conformance gate (no real inference). PRO/CON are folded into
    the synthesiser's sealed inputs by the caller; this function owns the
    deterministic guard, the R-1 schema retry, the v6 a_grounded retry
    cap + spurious-fault reconciliation, and the fail-safe-to-HALT.

    Retry budget (separately counted; both feed into retries_consumed):
      - 1 schema-structural retry (MF-4 half-2) on a garbled report.
      - Up to A_GROUNDED_MAX_RETRIES synth re-rolls on a spurious
        a_grounded fault (v6). After exhaustion, if still spurious,
        a_grounded resolves to pass (the synth had nothing payload-
        checkable to back the fault with; linter remains authoritative
        on the positive case).
    """
    fault_tokens = _load_fault_tokens()
    retries = 0
    attempt_num = 1
    try:
        # ---- Initial synth call + schema R-1 retry ----
        try:
            raw = synthesiser_callable(attempt=attempt_num)
            rep = _parse_and_guard(raw, fault_tokens)
        except SubstantiveRejection as sr:
            return CouncilResult("halt", "fault", 0,
                                  f"substantive_guard_rejection:{sr}",
                                  {}, None)
        except SchemaStructuralError:
            retries = 1
            attempt_num = 2
            try:
                raw = synthesiser_callable(attempt=attempt_num)
                rep = _parse_and_guard(raw, fault_tokens)
            except SubstantiveRejection as sr:
                return CouncilResult("halt", "fault", retries,
                                     f"substantive_guard_rejection:{sr}",
                                     {}, None)
            except SchemaStructuralError as se2:
                return CouncilResult("halt", "fault", retries,
                                     f"double_schema_garble:{se2}", {}, None)

        # ---- v6: a_grounded retry-on-spurious-fault loop ----
        a_retries = 0
        while True:
            status, _why = _a_grounded_check(rep, linter_verdict)
            if status in ("ok", "genuine"):
                # ok: a_grounded=pass; nothing to do.
                # genuine: a_grounded=fault NAMING a linter-flagged
                # cite; proceed to _derive which terminates via the
                # standard bright-line path.
                break
            # status == "spurious": stochastic synth said fault but
            # the linter doesn't back any payload-checkable gap. Try
            # again -- the v6 retry budget exists for this exact case.
            if a_retries >= A_GROUNDED_MAX_RETRIES:
                # Exhausted retries: resolve to pass per v6 spurious-
                # fault reconciliation. Mutate the rep so _derive sees
                # a_grounded=pass.
                rep["dimensions"]["a_grounded"] = {
                    "verdict": "pass",
                    "why": ("a_grounded:fault spurious -- synth named "
                             "no cite that the deterministic linter "
                             "also flagged after "
                             f"{A_GROUNDED_MAX_RETRIES} re-rolls; "
                             "resolved to pass per v6 spurious-fault "
                             "reconciliation"),
                }
                break
            a_retries += 1
            retries += 1
            attempt_num += 1
            try:
                raw = synthesiser_callable(attempt=attempt_num)
                rep = _parse_and_guard(raw, fault_tokens)
            except SubstantiveRejection as sr:
                # If on an a_grounded re-roll the synth violates
                # bound-(g), that is a genuine substantive halt --
                # the wall holds.
                return CouncilResult("halt", "fault", retries,
                                     f"substantive_guard_rejection:{sr}",
                                     {}, None)
            except SchemaStructuralError as se:
                # If on an a_grounded re-roll the synth returns
                # garbled schema, terminal: schema R-1 already used
                # and the wall holds against double garble.
                return CouncilResult("halt", "fault", retries,
                                     f"schema_garble_in_a_grounded_retry:{se}",
                                     {}, None)

        disposition, overall, halt_reason, advisory = _derive(rep)
        return CouncilResult(disposition, overall, retries, halt_reason,
                             advisory, rep)
    except Exception as exc:  # any other error/timeout/crash -> fail-safe HALT
        return CouncilResult("halt", "fault", retries,
                             f"council_failsafe_halt:{exc!r}", {}, None)
