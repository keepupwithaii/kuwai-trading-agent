# commitment-v2 build STATUS (execution terminal, agent #140)

Single standalone execution session. SPEC_ROOT = `/Users/maraneweda/Downloads/kuwai-gta-agent`
(point-in-time snapshot, authoritative for this run; the vault BigBrain path is
remapped to SPEC_ROOT and is not used). agent-ledger.md and SPEC_ROOT are
read-only. The dashboard dir is not touched.

## Confirmed facts (not re-derived)

- Model `claude-opus-4-7`, pinned snapshot, temperature `0.7`.
- `{MODEL_CUTOFF_DATE}` fill = the literal string `January 2026` (the only
  substitution in the sealed prompt).
- Account 258088643 is the LIVE real-money brokerage account.
- Dashboard already built and hardened; not rebuilt here.
- Public repo: `github.com/keepupwithaii/kuwai-trading-agent`. No LICENSE file
  (the README rights line carries that intent).

## v0 / RELATIONSHIP reconciliation (recorded explicitly, not silently chosen)

Per brief section 0 and ARCHITECT-HANDOFF section 5, doc 67 (CURRENT GATE STATE
2026-05-18, AUTHORITATIVE) supersedes the verbatim RELATIONSHIP/v0 text in 92 and
94 C2.4 and in 102, which assume a live, concurrent v0 on `commitment-v1` on
account 258088643 with commitment-v2 on a separate second isolated account.

67-authoritative single-program reality, adopted here:

- v0 was never sealed, never hashed, never OpenTimestamped, never published,
  never run live (V1 = TRUE under 67). There is no concurrent v0 and no
  co-residence.
- commitment-v2 is the only program, on the one funded live account 258088643.
- The "second isolated account" construction in 92/94 collapses (no v0 to be
  separate from). publish-precedes-trade is proven on 258088643's own first
  fill directly.
- `RELATIONSHIP.md` is written to this single-program reality. Clause-4 is the
  V1-resolved clean-correction wording (the accurate Alpaca phrasing: the agent
  trades cash only, cannot borrow or short, so the account cannot go below
  zero), NOT the 94 C2.4 accept-and-disclose text and NOT "read 67 to know
  which half". C-RELATIONSHIP asserts clause-4 is this single authoritative
  V1-resolved text.

### Factual input flagged for Maran's V1 gate at the seal trigger

A local v0 implementation exists in this repo at
`~/projects/kuwai-gta-agent/bot/agent.py` ("Anchor Hold"), and
`~/projects/kuwai-gta-agent/data/state.json` records SPY/TTWO fractional
positions with `entry_done: true` and `last_run_utc: 2026-05-18`. This shows v0
code was run locally. Under 67 and the V1 definition ("v0 was never hashed,
OpenTimestamped, published, or run live"), a local dev/paper run is not "run
live" in the sealed-integrity sense, so V1 remains TRUE and the clean-correction
wording is used. This is surfaced, not silently resolved: at the seal trigger
Maran must affirm V1 verbally. If Maran judges that local run constitutes v0
having "gone live" (e.g. real money on 258088643 under any published claim),
V1 is FALSE and `RELATIONSHIP.md` clause-4 must revert to the 94 C2.4
accept-and-disclose wording BEFORE seal (C-RELATIONSHIP). Not fatal if caught at
the V1 gate; fatal only if frozen wrong. This terminal proceeds on V1 = TRUE per
67-authoritative and holds the reversion ready.

## Hard bounds

Pause point (b) absolute. Build, conformance gate, VPS deploy, one compressed
PAPER cycle on the paper key are autonomous. Hash pre-registration, ots stamp,
public tag, GitHub Release, X post, KUWAI issue, live-key switch, first real
fill: each requires Maran's explicit separate per-step trigger in order. A
general "go" is not a seal trigger.

## Build progress

See RESUME.md for the live next-step anchor.
