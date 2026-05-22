# RELATIONSHIP.md — the single-program reality (sealed, dated)

Fixed, dated, not agent-authored, not revisable post-hoc. Written to the
67-authoritative single-program reality per brief section 0 and
ARCHITECT-HANDOFF section 5: where 67 (CURRENT GATE STATE 2026-05-18,
AUTHORITATIVE) and the older 92 / 94 C2.4 / 102 verbatim text disagree, 67
wins. The reconciliation is recorded explicitly in the build STATUS and the
synced EXECUTION-TERMINAL-STATUS; it was not silently chosen.

Dated 2026-05-19.

## Clause 1 — one sealed program, one live account

`commitment-v2` is the only program. It is a single sealed program on the one
funded, isolated, real-money Alpaca account 258088643. There is no concurrent
v0 program and no co-residence. There is no separate "second" account; the
single funded live account is commitment-v2's own. The reconciler tracks only
this program's own positions on its own account and own API key.

## Clause 2 — v0 was never sealed, never went live

The frozen v0 plan ("Anchor Hold") was deliberately superseded at Maran's
direction before any seal. v0 was never hashed, never OpenTimestamped, never
published, and never run live (67, authoritative; V1 = TRUE). It is therefore
not a sealed invariant, because there is no sealed or live v0 to invariant.
The project's only sealed program is `commitment-v2`. (A local development /
paper run of the v0 code is not "run live" in the sealed-integrity sense; this
is surfaced for Maran's V1 verbal gate at the seal trigger and is not resolved
by sealing.)

## Clause 3 — no prior-run conditioning

`commitment-v2` does not condition on any prior-run realised result. No v0 P&L,
equity curve, HALT/exit state, or any prior-run outcome is present in the
sealed prompt or corpus, and nothing in the prompt or corpus branches on a
prior run. The corpus exclusion set (see corpus/README) enforces this and a
sceptic can read SYSTEM_PROMPT.md and corpus/ and confirm no prior-result
dependent branch.

## Clause 4 — the cannot-go-below-zero property (V1-resolved clean correction)

This is the single authoritative V1-resolved text. The accurate statement is:
the agent trades cash only, cannot borrow and cannot short, so the account
cannot go below zero. This is true by Alpaca rule and by the agent never being
permitted to borrow or short: at sub-$2,000 equity Alpaca's own rule restricts
the account to 1x buying power with no margin and no short, and the sealed
feasibility gate independently rejects any order requiring margin or short
exposure. It is true by rule and by the agent's sealed constraints, not because
it is a cash-account product (Alpaca has none). Because v0 was never sealed,
no false "cash-only so it cannot go negative / Structural" line ever enters any
sealed artefact; the accurate wording above is the only sealed wording. (If at
the seal trigger Maran's V1 verbal is FALSE, this clause-4 must be replaced by
the 94 C2.4 accept-and-disclose wording before seal; the build holds that
reversion ready. C-RELATIONSHIP asserts clause-4 is exactly this single
V1-resolved text, not the accept-and-disclose text and not a "read 67 to know
which half" pointer.)

## Clause 5 — the single-program reality is a sealed invariant

No weekly amendment may introduce a v0, a second program, a second account, or
any co-residence, or otherwise revise the single-program reality. The
single-program reality is itself a sealed constant that the closed
outcome-blind weekly process cannot touch (see WEEKLY-POLICY.md).
