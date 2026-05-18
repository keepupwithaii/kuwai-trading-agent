#!/usr/bin/env python3
"""
The mandatory binary build-conformance gate (139 §2 + 144 §6.1 six council
assertions + 151 §1.4 two R-1 fixtures + C-MODEL/C-CONCESSION/C-MANIFEST/
C-SECRETS/C-LOCKFILE/C-RELATIONSHIP). Decision-blind: the model is STUBBED,
no order is placed, no network call is made, no seal artefact is produced, no
live key is touched. It crosses no pause point.

Binary: ALL assertions pass or the gate FAILS. On any fail, fix the BUILD to
conform and rerun. NEVER weaken an assertion to make it pass.

Usage: gate.py SPEC_ROOT BUILD_REPO
"""
from __future__ import annotations

import json
import sys

# Keep the sealed tree pristine: importing sealed code must never write
# __pycache__ into commitment-v2/ (C-MANIFEST demands an exact member set).
sys.dont_write_bytecode = True

from pathlib import Path

REPO = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.cwd()
SPEC_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
SEALED = REPO / "commitment-v2"
sys.path.insert(0, str(REPO / "commitment-v2" / "code"))
sys.path.insert(0, str(REPO / "build_tools"))
sys.path.insert(0, str(REPO / "conformance"))

import council as council_mod          # noqa: E402
import perception as perception_mod    # noqa: E402
import standout as standout_mod        # noqa: E402
from council_prompt_extract import extract_sealed_system_prompt  # noqa: E402
import secret_scan                     # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    def deco(fn):
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"exception: {exc!r}"
        RESULTS.append((name, ok, detail))
        return fn
    return deco


# ---- C-MODEL -------------------------------------------------------------
# Amendment 2026-05-19 (reason class 'broker or API change' per WEEKLY-POLICY):
# Anthropic deprecated temperature/top_p/top_k for claude-opus-4-7. MODEL.txt
# now records what is used (native sampling), not what was intended. The
# C-MODEL target is the byte-exact two-line content Maran approved; the
# assertion is corrected, not weakened.
EXPECTED_MODEL_LINES = [
    "claude-opus-4-7",
    "sampling: native (the Anthropic API does not accept temperature, top_p, "
    "or top_k for this snapshot; adaptive thinking + the model's native "
    "sampling)",
]


@check("C-MODEL")
def _c_model():
    lines = [l for l in (SEALED / "MODEL.txt").read_text("utf-8").splitlines()
             if l.strip()]
    if lines != EXPECTED_MODEL_LINES:
        return False, f"MODEL.txt lines do not byte-match expected ({lines!r})"
    # Banned residues that would smuggle the stale operator-temperature framing
    # back in: no '0.7', no '1.0' as a temperature value.
    raw = (SEALED / "MODEL.txt").read_text("utf-8")
    if "0.7" in raw or "1.0" in raw:
        return False, "MODEL.txt contains a stale temperature residue"
    return True, "claude-opus-4-7 / native sampling, byte-exact"


# ---- C-COUNCIL-PROMPT (replaces C-PROMPT): byte-identity ----------------
@check("C-COUNCIL-PROMPT")
def _c_prompt():
    if SPEC_ROOT is None:
        return False, "SPEC_ROOT not given"
    src = (SPEC_ROOT / "151-wave15-terminal.md").read_text("utf-8")
    expected = extract_sealed_system_prompt(src, "January 2026")
    built = (SEALED / "SYSTEM_PROMPT.md").read_text("utf-8")
    if built != expected:
        return False, "SYSTEM_PROMPT.md NOT byte-identical to 151 §4 re-derive"
    low = built.lower()
    for banned in ("temperature", "no safety net", "1.0", "0.7", "floor",
                   "0.45"):
        if banned in low:
            return False, f"residue {banned!r} in sealed prompt"
    if built.count("January 2026") != 1 or "{MODEL_CUTOFF_DATE}" in built:
        return False, "cutoff fill incorrect"
    return True, f"byte-identical ({len(built)} bytes)"


# ---- C-MANIFEST: membership exactly the enumerated set ------------------
@check("C-MANIFEST")
def _c_manifest():
    required = {
        "SYSTEM_PROMPT.md", "MODEL.txt", "TOOLS.md", "PERCEPTION_SCHEMA.md",
        "UNIVERSE.txt", "SCHEDULE.txt", "RELATIONSHIP.md", "WEEKLY-POLICY.md",
        "LOCKFILE.txt", "MANIFEST.txt",
        "corpus/README.md", "corpus/NO-EDGE.md",
        "COUNCIL/SCHEMA.md", "COUNCIL/FAULT_LIST.txt", "COUNCIL/PRO_PROMPT.md",
        "COUNCIL/CON_PROMPT.md", "COUNCIL/SYNTHESISER_PROMPT.md",
        "RESEARCH/PLAN.txt", "RESEARCH/SOURCES.txt",
        "RESEARCH/QUERY_TEMPLATE.txt", "RESEARCH/RECENCY.txt",
        "RESEARCH/MISSING_POLICY.txt", "RESEARCH/FUNDING.txt",
        "RESEARCH/RECONSTRUCTION.md", "RESEARCH/SCRAPE_CHANNELS.txt",
        "RESEARCH/REGIME_RULE.txt", "RESEARCH/TRANSFORMS.txt",
        "code/manifest_io.py", "code/hashlog.py", "code/feasibility_gate.py",
        "code/floor.py", "code/perception.py", "code/grounding_linter.py",
        "code/council.py", "code/amendment_loader.py", "code/standout.py",
        "code/agent_loop.py",
    }
    actual = {p.relative_to(SEALED).as_posix()
              for p in SEALED.rglob("*") if p.is_file()}
    missing = required - actual
    extra = actual - required
    if missing:
        return False, f"missing sealed members: {sorted(missing)}"
    if extra:
        return False, f"unexpected sealed members: {sorted(extra)}"
    # README/.gitignore must NOT be inside the sealed tree
    if (SEALED / "README.md").exists() or (SEALED / ".gitignore").exists():
        return False, "README/.gitignore must not be inside commitment-v2/"
    return True, f"{len(actual)} members, exact"


# ---- C-SECRETS ----------------------------------------------------------
@check("C-SECRETS")
def _c_secrets():
    out = REPO / "conformance" / "secret-scan-report.txt"
    rc = secret_scan.run(SEALED, REPO, out)
    if not out.exists():
        return False, "no secret-scan report emitted"
    if out.resolve().is_relative_to(SEALED.resolve()):
        return False, "report must be OUTSIDE the sealed tree"
    if rc != 0 or "result = CLEAN" not in out.read_text("utf-8"):
        return False, "secret scan not clean"
    return True, "clean, report outside sealed tree"


# ---- C-LOCKFILE ---------------------------------------------------------
@check("C-LOCKFILE")
def _c_lockfile():
    lf = SEALED / "LOCKFILE.txt"
    if not lf.is_file():
        return False, "LOCKFILE.txt absent from sealed tree"
    t = lf.read_text("utf-8")
    if "third_party_dependencies = NONE" not in t:
        return False, "lockfile does not pin an empty closure"
    rec = (SEALED / "RESEARCH" / "RECONSTRUCTION.md").read_text("utf-8")
    if "Reproducible build" not in rec:
        return False, "reproducible-build procedure not stated"
    return True, "stdlib-only, empty closure pinned, reproducible-build stated"


# ---- C-RELATIONSHIP -----------------------------------------------------
@check("C-RELATIONSHIP")
def _c_relationship():
    t = (SEALED / "RELATIONSHIP.md").read_text("utf-8")
    need = ["trades cash only", "cannot borrow", "cannot go below zero",
            "true by Alpaca rule"]
    if not all(s in t for s in need):
        return False, "clause-4 clean-correction wording incomplete"
    # must NOT be the accept-and-disclose posture as the operative clause-4
    if "accept-and-disclose" in t and "clause-4 must be replaced" not in t:
        return False, "clause-4 reads as accept-and-disclose"
    return True, "clause-4 = single V1-resolved clean-correction text"


# ---- C-CONCESSION: no 1.0 / no temperature-1.0 framing residue ----------
@check("C-CONCESSION")
def _c_concession():
    for p in SEALED.rglob("*"):
        if not p.is_file():
            continue
        t = p.read_text("utf-8", errors="ignore")
        if "temperature-1.0 operator choice" in t:
            return False, f"forbidden concession framing in {p}"
    return True, "no temperature-1.0 framing; count discipline backstop holds"


# ---- C-COUNCIL-SEAL -----------------------------------------------------
@check("C-COUNCIL-SEAL")
def _c_council_seal():
    need = ["COUNCIL/SCHEMA.md", "COUNCIL/FAULT_LIST.txt",
            "COUNCIL/PRO_PROMPT.md", "COUNCIL/CON_PROMPT.md",
            "COUNCIL/SYNTHESISER_PROMPT.md", "code/council.py"]
    for n in need:
        if not (SEALED / n).is_file():
            return False, f"sealed council member missing: {n}"
    return True, "5 council files + council code module sealed"


# ---- C-COUNCIL-SCHEMA-GUARD + the two R-1 fixtures ----------------------
@check("C-COUNCIL-SCHEMA-GUARD")
def _c_schema_guard():
    DIMS = council_mod.DIMS
    # Fixture A: parse-valid, g-fault violating the bound shape ->
    # SUBSTANTIVE rejection, immediate HALT, ZERO retries.
    a = {"dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS}}
    a["dimensions"]["g_reasoning_holds"] = {
        "verdict": "fault",
        "why": "the position is too large and risky, be more careful"}
    ra = council_mod.run_council({}, {}, {}, lambda attempt: json.dumps(a))
    if not (ra.disposition == "halt" and ra.retries_consumed == 0):
        return False, f"Fixture A wrong: {ra.disposition},{ra.retries_consumed}"
    # Fixture B: schema-structural garble both attempts -> exactly 1 retry,
    # terminal HALT.
    rb = council_mod.run_council({}, {}, {}, lambda attempt: "{ not json")
    if not (rb.disposition == "halt" and rb.retries_consumed == 1):
        return False, f"Fixture B wrong: {rb.disposition},{rb.retries_consumed}"
    return True, "Fixture A halt/0 retries; Fixture B halt/1 retry"


# ---- C-COUNCIL-HALT-SAFE -----------------------------------------------
@check("C-COUNCIL-HALT-SAFE")
def _c_halt_safe():
    DIMS = council_mod.DIMS

    def raiser(attempt):
        raise RuntimeError("synth crash")
    r = council_mod.run_council({}, {}, {}, raiser)
    if r.disposition != "halt":
        return False, "fail-safe did not HALT on synth crash"
    # a-f fault that names no closed token = schema-structural -> retry path,
    # not a silent pass.
    bad = {"dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS}}
    bad["dimensions"]["a_grounded"] = {"verdict": "fault",
                                       "why": "looks weak to me"}
    r2 = council_mod.run_council({}, {}, {},
                                 lambda attempt: json.dumps(bad))
    if r2.disposition != "halt" or r2.retries_consumed != 1:
        return False, "a-f untokened fault not routed as schema garble"
    # bright-line a-fault with token -> hard HALT, 0 retries.
    good = {"dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS}}
    good["dimensions"]["a_grounded"] = {"verdict": "fault",
                                        "why": "UNGROUNDED no cite"}
    r3 = council_mod.run_council({}, {}, {},
                                 lambda attempt: json.dumps(good))
    if r3.disposition != "halt" or r3.retries_consumed != 0:
        return False, "bright-line a-fault not hard-HALT/0-retry"
    return True, "fail-safe-to-HALT; retry trigger scope correct; one-cap"


# ---- C-COUNCIL-A5 -------------------------------------------------------
@check("C-COUNCIL-A5")
def _c_council_a5():
    payload = {"assembled_at": "t", "blocks": {}}
    proj = perception_mod.broadcast_safe_projection(payload, "proceed", True)
    allowed = {"council_ran", "council_disposition",
               "bright_line_halt_occurred", "assembled_at"}
    if set(proj.keys()) - allowed:
        return False, f"projection leaks keys {set(proj)-allowed}"
    blob = json.dumps(proj).lower()
    for forbidden in ("fault", "advisory", "why", "fault_list", "fired",
                      "single_source", "social_cross_pump", "corroboration",
                      "class"):
        if forbidden in blob:
            return False, f"A5 leak token {forbidden!r} in projection"
    return True, "projection is coarse-only, no council internals/audit/class"


# ---- C-STANDOUT-ISOLATION ----------------------------------------------
@check("C-STANDOUT-ISOLATION")
def _c_standout():
    if "S-COUNCIL-CONTESTED" in standout_mod.TYPE_ENUM:
        return False, "S-COUNCIL-CONTESTED not dropped"
    proj = {"council_ran": True, "council_disposition": "halt",
            "bright_line_halt_occurred": True, "assembled_at": "t"}
    doc = standout_mod.build_standout(proj, equity=100.0, e0_floor=50.0,
                                      pnl_pct_since_start=-0.12,
                                      top_concentration_frac=0.8)
    blob = json.dumps(doc).lower()
    for forbidden in ("council", "advisory", "fault_list", "fired_class",
                      "corroboration", "single_source", "audit"):
        if forbidden in blob:
            return False, f"standout leaks {forbidden!r}"
    types = {e["type"] for e in doc["standout_events"]}
    if "S-COUNCIL-CONTESTED" in types:
        return False, "contested type emitted"
    if doc.get("model_prose_pass") is not False:
        return False, "model prose pass not OFF by default"
    # MF-7: only the coarse S-HALT, no per-wake fault class label
    for e in doc["standout_events"]:
        if e["type"] == "S-HALT" and "class" in json.dumps(e).lower():
            return False, "per-wake bright-line fault class leaked"
    return True, "read-only, coarse, no contested, prose OFF, MF-7 held"


# ---- C-PAYLOAD-OWN-ACCOUNT (B1 backstop) -------------------------------
# The agent's perception payload's O_own_account block MUST carry all six
# spec-required keys (equity, cash, settled_cash, positions,
# prior_wake_orders, pdt_daytrade_count). The sealed system prompt promises
# the agent "you are shown your account's real balance". A blank payload is
# a defined bug class (harness/conformance not assembling the sealed spec).
@check("C-PAYLOAD-OWN-ACCOUNT")
def _c_payload_own_account():
    # Stub a representative merged account state (the shape agent_loop now
    # passes into perception.assemble after the B1 fix), and assert all six
    # required keys arrive in the assembled payload's value dict.
    stub_account = {
        "equity": 153.42,
        "cash": 102.10,
        "settled_cash": 102.10,
        "positions": [{"symbol": "AAPL", "tracked_qty": 0.5,
                        "avg_entry": 195.00}],
        "prior_wake_orders": [],
        "pdt_daytrade_count": 0,
        "as_of": "2026-05-19T00:00:00+00:00",
        "status": "ACTIVE",
    }
    payload = perception_mod.assemble({"account": stub_account},
                                      live_block_n=False)
    o = payload.get("blocks", {}).get("O_own_account", {})
    value = o.get("value", {})
    if not isinstance(value, dict):
        return False, "O_own_account.value not a dict"
    required = {"equity", "cash", "settled_cash", "positions",
                "prior_wake_orders", "pdt_daytrade_count"}
    missing = required - set(value.keys())
    if missing:
        return False, f"missing keys in O_own_account.value: {sorted(missing)}"
    # Spot-check the values flow through unchanged (the sealed prompt's
    # 'shown balance is the truth' promise).
    if value["equity"] != 153.42 or value["cash"] != 102.10:
        return False, "stubbed equity/cash did not flow into the payload"
    if not value["positions"] or value["positions"][0]["symbol"] != "AAPL":
        return False, "positions did not flow into the payload"
    return True, "all 6 spec-required own-account keys present and flowing"


# ---- C-MANIFEST-IO-PARSE (M4 backstop) ---------------------------------
# manifest_io.read_model must parse MODEL.txt to (model_id, sampling_note)
# without raising, independent of C-MODEL's byte-match. Catches a code
# regression in the loader that C-MODEL alone wouldn't catch.
@check("C-MANIFEST-IO-PARSE")
def _c_manifest_io():
    sys.path.insert(0, str(SEALED / "code"))
    import manifest_io as mio
    try:
        model_id, sampling_note = mio.read_model(SEALED)
    except Exception as e:
        return False, f"read_model raised: {e!r}"
    if model_id != "claude-opus-4-7":
        return False, f"model_id wrong: {model_id!r}"
    if not sampling_note or "native" not in sampling_note.lower():
        return False, "sampling_note missing or doesn't carry 'native'"
    # universe + schedule readers should also parse without raising
    u = mio.read_universe(SEALED)
    if not u or len(u) < 10:
        return False, "read_universe returned too few entries"
    s = mio.read_schedule(SEALED)
    if s.get("crypto_leg") != "absent_sealed":
        return False, "schedule crypto_leg not absent_sealed"
    return True, f"read_model OK ({model_id}); read_universe {len(u)}; read_schedule OK"


# ---- Plumbing (139 §2.1): decision-blind one-shot, stubbed --------------
@check("PLUMBING-DECISION-BLIND")
def _plumbing():
    import agent_loop
    from hashlog import HashLog
    submitted = []

    class StubBroker:
        def account(self):
            return {"status": "ACTIVE", "equity": 200.0,
                    "settled_cash": 200.0, "tracked_qty": {},
                    "pdt_daytrade_count": 0}

        def reconcile(self):
            return {"trade_date": "2026-05-19", "raw": {}}

        def submit(self, order, coid):
            submitted.append((order, coid))
            return {"stub": True}

    class StubClock:
        def rth_open(self):
            return True

    def stub_decider(payload, sealed_prompt):
        # decision-blind: propose nothing (HOLD). No real inference.
        return {"reasoning_envelope": {"payload_refs": []},
                "proposed_orders": []}

    def stub_synth(attempt):
        raise AssertionError("synth must not be called on a HOLD wake")

    logp = REPO / "conformance" / "_plumbing_run.log"
    if logp.exists():
        logp.unlink()
    deps = {"broker": StubBroker(), "clock": StubClock(),
            "decider": stub_decider, "synth": stub_synth}
    res = agent_loop.run_wake(deps, logp, e0=180.0)  # synthetic E0
    if res["state"] != "OK":
        return False, f"plumbing wake not OK: {res}"
    if submitted:
        return False, "an order was submitted in a decision-blind run"
    if not HashLog(logp).verify_chain():
        return False, "hash chain does not verify"
    # no seal artefact produced anywhere
    for art in ("commitment-v2.zip", "commitment-v2.zip.ots"):
        if (REPO / art).exists():
            return False, f"seal artefact {art} was produced"
    logp.unlink(missing_ok=True)
    return True, "decision-blind wake OK, chain verifies, no order, no seal"


def main() -> int:
    print("=== KUWAI commitment-v2 BINARY CONFORMANCE GATE ===")
    all_pass = True
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        all_pass = all_pass and ok
    print("=== GATE", "GREEN (all assertions pass)" if all_pass
          else "RED (a build defect; fix the BUILD, never weaken)", "===")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
