#!/usr/bin/env python3
"""
The mandatory binary build-conformance gate for commitment-v5.

Reuses all 15 v2 gates re-targeted at commitment-v5/ (paths swapped only,
assertions unchanged), and adds two v3-specific gates:
  C-PERCEPTION-WIRED:      all 8 perception blocks populated from adapters,
                            including O_own_account STALE freshness gate.
  C-LOOP-FAILSAFE-TRANSIENT: 3x529-then-200 = one OK wake, no HALT;
                            401 = terminal HALT immediately.

Decision-blind. No real inference. No order. No network. No seal artefact.
17/17 GREEN required. Anything red, stop and report; never weaken.

Usage: gate_v3.py SPEC_ROOT BUILD_REPO
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

# Keep the sealed tree pristine: importing sealed code must never write
# __pycache__ into commitment-v5/ (C-MANIFEST demands an exact member set).
sys.dont_write_bytecode = True

from pathlib import Path

REPO = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path.cwd()
SPEC_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
SEALED = REPO / "commitment-v5"
sys.path.insert(0, str(REPO / "commitment-v5" / "code"))
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
    raw = (SEALED / "MODEL.txt").read_text("utf-8")
    if "0.7" in raw or "1.0" in raw:
        return False, "MODEL.txt contains a stale temperature residue"
    return True, "claude-opus-4-7 / native sampling, byte-exact"


# ---- C-COUNCIL-PROMPT (byte-identity) -----------------------------------
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
    if (SEALED / "README.md").exists() or (SEALED / ".gitignore").exists():
        return False, "README/.gitignore must not be inside commitment-v5/"
    return True, f"{len(actual)} members, exact"


# ---- C-SECRETS ----------------------------------------------------------
@check("C-SECRETS")
def _c_secrets():
    out = REPO / "conformance" / "secret-scan-report-v5.txt"
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
    if "accept-and-disclose" in t and "clause-4 must be replaced" not in t:
        return False, "clause-4 reads as accept-and-disclose"
    return True, "clause-4 = single V1-resolved clean-correction text"


# ---- C-CONCESSION -------------------------------------------------------
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


# ---- C-COUNCIL-SCHEMA-GUARD + R-1 fixtures ------------------------------
@check("C-COUNCIL-SCHEMA-GUARD")
def _c_schema_guard():
    DIMS = council_mod.DIMS
    a = {"dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS}}
    a["dimensions"]["g_reasoning_holds"] = {
        "verdict": "fault",
        "why": "the position is too large and risky, be more careful"}
    ra = council_mod.run_council({}, {}, {}, lambda attempt: json.dumps(a))
    if not (ra.disposition == "halt" and ra.retries_consumed == 0):
        return False, f"Fixture A wrong: {ra.disposition},{ra.retries_consumed}"
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
    bad = {"dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS}}
    bad["dimensions"]["a_grounded"] = {"verdict": "fault",
                                       "why": "looks weak to me"}
    r2 = council_mod.run_council({}, {}, {},
                                 lambda attempt: json.dumps(bad))
    if r2.disposition != "halt" or r2.retries_consumed != 1:
        return False, "a-f untokened fault not routed as schema garble"
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
    for e in doc["standout_events"]:
        if e["type"] == "S-HALT" and "class" in json.dumps(e).lower():
            return False, "per-wake bright-line fault class leaked"
    return True, "read-only, coarse, no contested, prose OFF, MF-7 held"


# ---- C-PAYLOAD-OWN-ACCOUNT (B1 backstop, carried from v2) --------------
@check("C-PAYLOAD-OWN-ACCOUNT")
def _c_payload_own_account():
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
    if value["equity"] != 153.42 or value["cash"] != 102.10:
        return False, "stubbed equity/cash did not flow into the payload"
    if not value["positions"] or value["positions"][0]["symbol"] != "AAPL":
        return False, "positions did not flow into the payload"
    return True, "all 6 spec-required own-account keys present and flowing"


# ---- C-MANIFEST-IO-PARSE (M4 backstop) ---------------------------------
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
    u = mio.read_universe(SEALED)
    if not u or len(u) < 10:
        return False, "read_universe returned too few entries"
    s = mio.read_schedule(SEALED)
    if s.get("crypto_leg") != "absent_sealed":
        return False, "schedule crypto_leg not absent_sealed"
    return True, f"read_model OK ({model_id}); read_universe {len(u)}; read_schedule OK"


# ---- helpers for plumbing / wired / failsafe tests ---------------------

def _http_error(code: int, msg: str = "test"):
    return urllib.error.HTTPError(
        "https://test.local/", code, msg, hdrs=None, fp=io.BytesIO(b""))


class StubBroker:
    def __init__(self, account_overrides=None):
        self._acct = {"status": "ACTIVE", "equity": 200.0,
                      "settled_cash": 200.0, "cash": 200.0,
                      "tracked_qty": {}, "prior_wake_orders": [],
                      "pdt_daytrade_count": 0,
                      "as_of": datetime.now(timezone.utc).isoformat()}
        if account_overrides:
            self._acct.update(account_overrides)
        self.submitted = []

    def account(self):
        return dict(self._acct)

    def reconcile(self):
        return {"trade_date": "2026-05-20", "raw": {}}

    def submit(self, order, coid):
        self.submitted.append((order, coid))
        return {"stub": True}


class StubClock:
    def rth_open(self):
        return True


def _stub_decider_hold(payload, sealed_prompt):
    return {"reasoning_envelope": {"payload_refs": []},
            "proposed_orders": []}


def _stub_synth_unused(attempt):
    raise AssertionError("synth must not be called on a HOLD wake")


def _fresh_now():
    return datetime.now(timezone.utc)


# ---- PLUMBING-DECISION-BLIND (carried from v2; uses v3 run_wake) -------
@check("PLUMBING-DECISION-BLIND")
def _plumbing():
    import agent_loop
    from hashlog import HashLog

    logp = REPO / "conformance" / "_plumbing_run_v5.log"
    if logp.exists():
        logp.unlink()
    br = StubBroker()
    deps = {"broker": br, "clock": StubClock(),
            "decider": _stub_decider_hold, "synth": _stub_synth_unused,
            "now": _fresh_now}
    res = agent_loop.run_wake(deps, logp, e0=180.0)
    if res["state"] != "OK":
        return False, f"plumbing wake not OK: {res}"
    if br.submitted:
        return False, "an order was submitted in a decision-blind run"
    if not HashLog(logp).verify_chain():
        return False, "hash chain does not verify"
    for art in ("commitment-v5.zip", "commitment-v5.zip.ots"):
        if (REPO / art).exists():
            return False, f"seal artefact {art} was produced"
    logp.unlink(missing_ok=True)
    return True, "decision-blind wake OK, chain verifies, no order, no seal"


# ---- C-PERCEPTION-WIRED (v3 NEW) ---------------------------------------
# For each of the 8 perception blocks, feed a known-good fixture through the
# wired agent_loop.run_wake adapter pipeline; assert the assembled payload
# carries parsed rows at the right key with the right source/status, and
# (for O_own_account) the freshness gate marks STALE when as_of is too old.
@check("C-PERCEPTION-WIRED")
def _c_perception_wired():
    import agent_loop
    sys.path.insert(0, str(SEALED / "code"))

    logp = REPO / "conformance" / "_wired_run_v5.log"

    def _adapter_fixture(label):
        return lambda *_a, **_kw: {
            "value": [{"label": label, "row": 1}],
            "as_of": _fresh_now().isoformat(),
            "status": "OK",
        }

    # --- sub 1..7: seven non-account blocks, all wired with fixture data
    if logp.exists():
        logp.unlink()
    deps = {
        "broker": StubBroker(),
        "clock": StubClock(),
        "decider": _stub_decider_hold,
        "synth": _stub_synth_unused,
        "now": _fresh_now,
        "bars":         _adapter_fixture("bars"),
        "news":         _adapter_fixture("news"),
        "edgar":        _adapter_fixture("edgar"),
        "corp_actions": _adapter_fixture("corp_actions"),
        "own_history":  _adapter_fixture("own_history"),
        "derived":      lambda _pl: {
            "value": [{"label": "derived", "row": 1}],
            "as_of": _fresh_now().isoformat(),
            "status": "OK",
        },
        "block_n":      _adapter_fixture("block_n"),
    }
    res = agent_loop.run_wake(deps, logp, e0=180.0, live_block_n=True)
    if res["state"] != "OK":
        return False, f"wired wake not OK: {res!r}"
    payload = res.get("payload", {})
    blocks = payload.get("blocks", {})
    expectations = [
        ("A_market_bars",        "alpaca_md_iex",       True),
        ("C_news_catalyst",      "alpaca_news",         True),
        ("E_edgar_primary",      "sec_edgar",           True),
        ("C2_corporate_actions", "corporate_actions",   True),
        ("FGHIJKL_derived",      "derived_transform",   True),
        ("M_own_history",        "own_log",             True),
        ("N_social",             "block_n_social",      True),
    ]
    for label, expected_src, must_have_value in expectations:
        b = blocks.get(label) or {}
        if b.get("status") != "OK":
            return False, f"{label} status not OK: {b.get('status')!r}"
        if b.get("source") != expected_src:
            return False, f"{label} source != {expected_src}: {b.get('source')!r}"
        if must_have_value and b.get("value") is None:
            return False, f"{label} value is None (UNAVAILABLE)"
        if not b.get("as_of"):
            return False, f"{label} as_of missing"

    # sub 8a: O_own_account fresh path -> status NOT STALE (broker's
    # ACTIVE / OK pass through unchanged; the freshness gate only writes
    # STALE when as_of is older than wake_now - 60s) + 6 keys flow through.
    o = blocks.get("O_own_account") or {}
    if o.get("status") in ("STALE", "MISSING", "UNAVAILABLE"):
        return False, (f"O_own_account fresh path wrongly marked "
                       f"{o.get('status')!r}")
    if o.get("status") not in ("OK", "ACTIVE"):
        return False, f"O_own_account fresh status unexpected: {o.get('status')!r}"
    required_keys = {"equity", "cash", "settled_cash", "positions",
                     "prior_wake_orders", "pdt_daytrade_count"}
    missing = required_keys - set((o.get("value") or {}).keys())
    if missing:
        return False, f"O_own_account missing keys: {sorted(missing)}"
    logp.unlink(missing_ok=True)

    # sub 8b: O_own_account STALE gate (as_of older than wake_now - 60s)
    if logp.exists():
        logp.unlink()
    stale_ts = (datetime.now(timezone.utc)
                - timedelta(seconds=300)).isoformat()
    br_stale = StubBroker(account_overrides={"as_of": stale_ts})
    deps_stale = dict(deps)
    deps_stale["broker"] = br_stale
    res2 = agent_loop.run_wake(deps_stale, logp, e0=180.0, live_block_n=True)
    if res2["state"] != "OK":
        return False, f"stale-gate wake not OK: {res2!r}"
    o2 = res2.get("payload", {}).get("blocks", {}).get("O_own_account") or {}
    if o2.get("status") != "STALE":
        return False, (f"O_own_account stale-gate did not mark STALE "
                       f"(got {o2.get('status')!r} for as_of={stale_ts})")
    logp.unlink(missing_ok=True)

    return True, "all 8 blocks wired (7 + O_own_account); STALE gate fires"


# ---- C-LOOP-FAILSAFE-TRANSIENT (v3 NEW) --------------------------------
# (A) three sequential 529s then a 200 -> one successful wake, NO HALT.
# (B) a 401 -> terminal HALT immediately (no retry, no exit-without-HALT).
@check("C-LOOP-FAILSAFE-TRANSIENT")
def _c_loop_failsafe_transient():
    import agent_loop
    from hashlog import HashLog

    # --- (A) transient 529s followed by success ------------------------
    logp_a = REPO / "conformance" / "_failsafe_transient_run_v5.log"
    if logp_a.exists():
        logp_a.unlink()

    call_count = {"n": 0}

    def flaky_decider(payload, sealed_prompt):
        call_count["n"] += 1
        if call_count["n"] <= 3:
            raise _http_error(529, "Overloaded")
        return {"reasoning_envelope": {"payload_refs": []},
                "proposed_orders": []}

    # Speed: replace the real time.sleep so the gate doesn't actually wait
    # 5+30+120s for the backoffs to elapse.
    real_sleep = agent_loop.time.sleep
    agent_loop.time.sleep = lambda s: None
    try:
        deps_a = {"broker": StubBroker(), "clock": StubClock(),
                  "decider": flaky_decider, "synth": _stub_synth_unused,
                  "now": _fresh_now}
        res_a = agent_loop.run_wake(deps_a, logp_a, e0=180.0)
    finally:
        agent_loop.time.sleep = real_sleep

    if res_a["state"] != "OK":
        return False, f"3x529-then-200 did not yield OK: {res_a!r}"
    if call_count["n"] != 4:
        return False, f"decider should have been called 4 times, got {call_count['n']}"
    log_a = HashLog(logp_a)
    if log_a.is_halted():
        return False, "transient 529s wrongly committed terminal HALT"
    if not log_a.verify_chain():
        return False, "chain (transient path) does not verify"
    # the ledger must NOT contain a HALT kind
    halted_kinds = []
    for ln in logp_a.read_text("utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        o = json.loads(ln)
        if o.get("kind") == "HALT":
            halted_kinds.append(o)
    if halted_kinds:
        return False, f"HALT entry present after 3x529-then-200: {halted_kinds}"
    logp_a.unlink(missing_ok=True)

    # --- (B) 401 -> immediate terminal HALT ---------------------------
    logp_b = REPO / "conformance" / "_failsafe_auth_run_v5.log"
    if logp_b.exists():
        logp_b.unlink()
    auth_calls = {"n": 0}

    def auth_decider(payload, sealed_prompt):
        auth_calls["n"] += 1
        raise _http_error(401, "Unauthorized")

    real_sleep2 = agent_loop.time.sleep
    agent_loop.time.sleep = lambda s: None
    try:
        deps_b = {"broker": StubBroker(), "clock": StubClock(),
                  "decider": auth_decider, "synth": _stub_synth_unused,
                  "now": _fresh_now}
        res_b = agent_loop.run_wake(deps_b, logp_b, e0=180.0)
    finally:
        agent_loop.time.sleep = real_sleep2

    if res_b["state"] != "HALT":
        return False, f"401 did not HALT: {res_b!r}"
    if auth_calls["n"] != 1:
        return False, f"401 path retried (called {auth_calls['n']} times)"
    log_b = HashLog(logp_b)
    if not log_b.is_halted():
        return False, "401 did not produce a terminal HALT entry"
    if not log_b.verify_chain():
        return False, "chain (401 path) does not verify"
    logp_b.unlink(missing_ok=True)

    return True, "3x529-then-200 = OK no HALT; 401 = terminal HALT immediately"


# ---- C-SYNTH-SCHEMA-CONTRACT (v5 NEW) ----------------------------------
# Asserts the council parser contract is intact and the v5 prompt-side fix
# targets the right shape:
#   (a) a known-good council-v1 NESTED JSON is accepted (returns rep);
#   (b) a flat-keys JSON (the v4-live-wake failure mode) is REJECTED with
#       SchemaStructuralError "missing dimensions object".
# Decision-blind: stubs the synthesiser via a callable, no real Anthropic
# call, no order. Lives in conformance/ and tests sealed council code.
@check("C-SYNTH-SCHEMA-CONTRACT")
def _c_synth_schema_contract():
    sys.path.insert(0, str(SEALED / "code"))
    import importlib, council as _council
    importlib.reload(_council)
    DIMS = _council.DIMS

    # (a) nested-good: every dimension pass; should produce a clean
    # disposition=proceed, retries_consumed=0, halt_reason="".
    nested_good = {
        "schema": "council-v1",
        "dimensions": {d: {"verdict": "pass", "why": "ok"} for d in DIMS},
    }
    r_good = _council.run_council({}, {}, {},
                                   lambda attempt: json.dumps(nested_good))
    if r_good.disposition != "proceed":
        return False, (f"nested-good rejected: disposition="
                       f"{r_good.disposition!r}, halt_reason="
                       f"{r_good.halt_reason!r}")
    if r_good.overall != "pass":
        return False, f"nested-good overall != pass: {r_good.overall!r}"
    if r_good.retries_consumed != 0:
        return False, (f"nested-good consumed retries unexpectedly: "
                       f"{r_good.retries_consumed}")

    # (b) flat-bad: the v4-live-wake shape exactly (top-level dim keys, no
    # "dimensions" wrapper). The parser's first attempt fails on
    # "missing dimensions object"; the council triggers the R-1 retry; the
    # second attempt (same flat shape) fails the same way; disposition is
    # the unchanged 141 §8 terminal HALT, halt_reason starts with
    # "double_schema_garble:missing dimensions object", retries_consumed=1.
    flat_bad = {"schema": "council-v1"}
    for d in DIMS:
        flat_bad[d] = {"verdict": "pass", "why": "ok"}
    flat_blob = json.dumps(flat_bad)
    r_bad = _council.run_council({}, {}, {}, lambda attempt: flat_blob)
    if r_bad.disposition != "halt":
        return False, (f"flat-bad NOT rejected: disposition="
                       f"{r_bad.disposition!r}, halt_reason="
                       f"{r_bad.halt_reason!r}")
    if "missing dimensions object" not in (r_bad.halt_reason or ""):
        return False, (f"flat-bad halted with wrong reason: "
                       f"{r_bad.halt_reason!r}")
    if r_bad.retries_consumed != 1:
        return False, (f"flat-bad should consume exactly 1 R-1 retry, "
                       f"got {r_bad.retries_consumed}")

    return True, ("nested council-v1 accepted; flat top-level keys "
                  "rejected as 'missing dimensions object' via the "
                  "intended R-1 retry-then-HALT path "
                  f"(retries_consumed={r_bad.retries_consumed})")


# ---- C-LINTER-PREFIX-MATCH (v5 NEW, post-smoke#1) -----------------------
# Asserts grounding_linter.py accepts item-level model citations via
# prefix-match against block keys, and still rejects citations against
# non-existent blocks.
@check("C-LINTER-PREFIX-MATCH")
def _c_linter_prefix_match():
    sys.path.insert(0, str(SEALED / "code"))
    import importlib, grounding_linter as _gl
    importlib.reload(_gl)

    # Synthetic payload with one block key "A_market_bars".
    payload = {"blocks": {"A_market_bars": {"some": "data"},
                          "C_news_catalyst": {"more": "data"},
                          "O_own_account": {"equity": 174.28}}}
    # Fixture (a): item-level cite that starts with a block key
    env_a = {"payload_refs": [
        "A_market_bars AMZN 2026-05-22 close 266.27",
        "C_news_catalyst 52717091 PMI",
        "O_own_account equity 174.28",
    ]}
    v_a = _gl.lint(env_a, payload)
    if not v_a.get("grounded"):
        return False, (f"item-level cites rejected as ungrounded; "
                       f"reason={v_a.get('ungrounded_reason')!r}; "
                       f"map={v_a.get('citation_map')!r}")

    # Fixture (b): cite against non-existent block
    env_b = {"payload_refs": ["Z_nonexistent_block any text here"]}
    v_b = _gl.lint(env_b, payload)
    if v_b.get("grounded"):
        return False, (f"cite against non-existent block accepted: "
                       f"map={v_b.get('citation_map')!r}")
    if "Z_nonexistent_block" not in (v_b.get("ungrounded_reason") or ""):
        return False, (f"non-existent cite rejected for wrong reason: "
                       f"{v_b.get('ungrounded_reason')!r}")

    return True, ("item-level cites accepted via prefix-match; "
                  "non-existent-block cites still rejected")


# ---- C-X-ACTOR-RUNTIME-RESOLUTION (v5 NEW, post-smoke#1) ----------------
# Asserts that with an unpinned sealed X actor identity (no @<build>),
# BlockNApify._resolve_latest_succeeded_build returns a SUCCEEDED build
# matching \d+\.\d+\.\d+, and that the audit dict surface carries
# x_resolved_build + x_resolution_error keys. A live HTTP call to the
# Apify builds API IS made (validates resolution end-to-end), but no
# actor run is triggered, no orders, no ledger writes.
@check("C-X-ACTOR-RUNTIME-RESOLUTION")
def _c_x_actor_runtime_resolution():
    # Read sealed SCRAPE_CHANNELS to confirm the unpinned form
    sc_text = (SEALED / "RESEARCH" / "SCRAPE_CHANNELS.txt"
               ).read_text("utf-8")
    sealed_actor_x = None
    for ln in sc_text.splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln.startswith("actor_x_named"):
            sealed_actor_x = ln.split("=", 1)[1].strip()
            break
    if sealed_actor_x is None:
        return False, "actor_x_named not found in SCRAPE_CHANNELS.txt"
    if "@" in sealed_actor_x:
        return False, (f"actor_x_named is pinned ({sealed_actor_x!r}); "
                       f"v5 expects unpinned actor identity")

    import os
    if not os.environ.get("APIFY_TOKEN"):
        return False, ("APIFY_TOKEN env var absent; conformance gate "
                       "requires it to validate runtime resolution")

    sys.path.insert(0, str(REPO / "deploy"))
    import importlib, clients as _clients
    importlib.reload(_clients)
    block_n = _clients.BlockNApify()
    try:
        resolved = block_n._resolve_latest_succeeded_build(sealed_actor_x)
    except Exception as e:
        return False, f"resolution raised: {e!r}"

    import re
    if not re.match(r"^\d+\.\d+\.\d+$", resolved):
        return False, (f"resolved build {resolved!r} does not match "
                       f"\\d+\\.\\d+\\.\\d+")

    # Audit dict surface check via source inspection (no actor run)
    import inspect
    src = inspect.getsource(_clients.BlockNApify.__call__)
    if "x_resolved_build" not in src:
        return False, ("audit dict missing 'x_resolved_build' key in "
                       "BlockNApify.__call__")
    if "x_resolution_error" not in src:
        return False, ("audit dict missing 'x_resolution_error' key in "
                       "BlockNApify.__call__")

    return True, (f"unpinned actor_x_named={sealed_actor_x!r} resolves "
                  f"to {resolved} (matches \\d+\\.\\d+\\.\\d+); audit "
                  f"dict carries x_resolved_build + x_resolution_error")


def main() -> int:
    print("=== KUWAI commitment-v5 BINARY CONFORMANCE GATE (20 gates) ===")
    all_pass = True
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        all_pass = all_pass and ok
    print(f"=== {len(RESULTS)} gates run ===")
    print("=== GATE", "GREEN (all assertions pass)" if all_pass
          else "RED (a build defect; fix the BUILD, never weaken)", "===")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
