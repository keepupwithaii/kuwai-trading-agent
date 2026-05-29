# WEEKLY-POLICY.md — the pre-registered, enumerated, CLOSED, OUTCOME-BLIND weekly-amendment policy

Sealed inside commitment-v2 before the first trade. Verbatim per 94 C2.5 (also
102 R2.7), reconciled only where 67-authoritative single-program reality
supersedes the older live-v0 wording (brief section 0; 67 wins; recorded in
STATUS). This is the legal collar made into sealed text and is the most legally
and integrity load-bearing artefact.

## The only permitted reasons a weekly change may be made (the closed list — nothing outside it is a permitted change)

1. A defined bug class: a named, ahead-of-time-enumerated category of code
   defect where the harness or gate does something other than its sealed
   specification (for example, the gate rejects an order the sealed rules
   permit, the loader fails a hash-check it should pass, the reconciler
   miscounts). The enumerated bug categories are listed in full in the
   BUG-CLASSES section below; a defect not in that list is NOT a permitted
   change.

2. A broker or API change: Alpaca changes an endpoint, an order-type rule, a
   market-data feed, or an account rule, such that the sealed code can no
   longer execute its sealed behaviour. The change is limited to restoring
   sealed behaviour under the new broker reality, never to altering strategy.

3. A legal instruction: counsel or a regulator requires a specific change (for
   example, a mandated minimum publication lag enforced in the harness, a
   perception input removed). The change is exactly what the instruction
   requires and is documented with the instruction reference.

## The explicit bans (the bright line, stated as hard prohibitions)

- A weekly change may NEVER alter what counts as a win or a loss.
- A weekly change may NEVER re-target the agent toward a return, a benchmark,
  or any performance objective after seeing a result.
- A weekly change may NEVER be made because the agent lost, was losing,
  under-performed, or to make it win or perform better. Outcome is not an input
  to the policy at all. The policy is outcome-blind by construction: the
  permitted-reasons list contains no reason that references P&L, performance,
  or any realised result.
- A weekly change may NEVER widen the universe, the tool set, the perception
  inputs, or the risk surface toward a strategy the operator now prefers
  having seen the market.
- No weekly change may introduce a v0, a second program, a second account, or
  any co-residence, or otherwise revise the single-program reality
  (RELATIONSHIP.md clause 5, the sealed invariant).

## Every weekly change is a new sealed version, never an edit

1. There is no live amendment path. The running harness has no
   operator-writable surface, no config reload, no endpoint between weekly
   reviews. Covert intra-week steering requires a channel that does not exist
   by construction.

2. To amend, Maran produces `commitment-vN+1`: the full sealed artefact with
   the change, a plaintext `CHANGELOG.md` stating exactly what changed, which
   closed-list reason authorised it, and why, with its own SHA-256, its own
   OpenTimestamps Bitcoin anchor, its own git tag, its own X post and
   newsletter note. The prior version stays public and unaltered. The chain
   vN -> vN+1 is the audit trail.

3. The amendment loader is a deterministic scheduled gated swap: at a
   weekly-review boundary the running agent is stopped, the new artefact's
   hash is verified against the published `commitment-vN+1` (an
   `ExecStartPre` hash-check), and only the verified artefact starts. A
   running artefact whose hash matches no published seal cannot exist by
   construction.

4. Every amendment is logged into the hash-chained spine with version, hash,
   timestamp, the closed-list reason invoked, and the changelog reference, and
   is disclosed on camera in the episode it takes effect. A change that is, or
   is later found to be, outside the closed list is on-camera-flagged as a
   discretionary operator intervention and the run is narrated as compromised
   from that point, not hidden.

## The one-line honesty test for any weekly change

Could a sceptic, using only public artefacts, reconstruct exactly what
changed, which closed-list reason authorised it, when, and confirm it was
sealed before the next post-amendment trade? If yes, honest amendment. If any
part needs trusting Maran's account, it is cheating and the only honest move is
to say so on camera. A "bug fix" is checkable as honest only if a sceptic can
reproduce the bug from the sealed pre-change code; the sealed pre-change
`code/` at the pinned commit makes that reproduction possible.

## BUG-CLASSES (the closed, ahead-of-time enumerated defect categories)

Only a defect that falls squarely inside one of these named categories is a
permitted "defined bug class" change. Anything else is NOT permitted and is an
on-camera-flagged discretionary intervention.

1. GATE-FALSE-REJECT: the deterministic feasibility gate rejects an order that
   its sealed broker/legal rules permit.
2. GATE-FALSE-ACCEPT: the gate admits an order its sealed broker/legal rules
   forbid (margin/short/over-settled-cash/out-of-universe/out-of-RTH-window).
3. LOADER-HASH-FAULT: the amendment loader passes an artefact whose hash does
   not match a published seal, or fails one that does.
4. RECONCILER-MISCOUNT: reconcile-before-decide derives a position, cash, or
   PDT count that does not match reconciled broker truth.
5. IDEMPOTENCY-FAULT: a deterministic client_order_id is not stable, causing a
   double-submit or a missed submit on restart.
6. FLOOR-PREDICATE-FAULT: floor_check() does not evaluate
   `equity <= 0.45 * E0` exactly once per wake and before each submit, or
   re-bases E0, or is reachable by the agent.
7. COUNCIL-ROUTING-FAULT: the council post-parse guard, the bound-(g) shape
   enforcement, the schema-structural-only retry trigger, or the
   fail-safe-to-HALT path does not behave as the sealed COUNCIL spec and the
   R-1 bind specify.
8. LOG-CHAIN-FAULT: the hash-chained log writer breaks the prev-hash chain or
   fails to write a terminal/HALT entry.
9. SCHEMA-ASSEMBLY-FAULT: the perception assembler emits a datum that does not
   conform to PERCEPTION_SCHEMA.md, or silently fills a missing datum instead
   of marking it STALE/UNAVAILABLE.
10. CLOCK-CALENDAR-FAULT: the harness uses a hardcoded market offset instead
    of the broker clock/calendar API, or fires an equities order outside the
    sealed RTH guard.

A defect outside categories 1-10 is NOT a permitted weekly change.
