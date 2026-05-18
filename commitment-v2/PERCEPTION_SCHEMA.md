# PERCEPTION_SCHEMA.md — the sealed perception-bundle schema

Sealed. The harness assembles the bundle deterministically to this schema; the
agent perceives it and cannot choose its contents. Every datum is stamped with
the moment it was true and its source. The agent does NOT perceive its own
floor distance. Sources: 102 R2.2, 131 §1.2 / §2.2, 94 C2.1, 127/128 Block-N
fixes.

## Common per-datum envelope

Every datum carries: `value`, `as_of` (UTC ISO-8601, the moment it was true),
`fetched_at` (UTC ISO-8601), `source` (see source enum), `status` in
`{OK | STALE | UNAVAILABLE}`. Missing or out-of-date data is stated plainly as
`STALE`/`UNAVAILABLE` with a visible reason; it is never silently filled.

`source` enum (closed): `alpaca_account`, `alpaca_md_iex`, `alpaca_news`,
`benzinga`, `sec_edgar`, `corporate_actions`, `derived_transform`,
`own_log`, `block_n_social`, `harness_sentinel`.

## Own-account state (block O)

`equity`, `cash`, `settled_cash`, `positions[]` (symbol, tracked_qty,
avg_entry), `prior_wake_orders[]` (intent, status, filled_qty,
filled_avg_price, gate_rejection_reason if any), `pdt_daytrade_count` (rolling
5-day). Reconciled broker truth only. No floor distance field exists.

## Market data and the ~13 deterministic blocks

Same-template-new-symbols / deterministic-transform / own-log only; no new
free-text surface beyond Block N.

- A-E: prior-session daily bars, recent intraday bars, last trade per universe
  symbol (Alpaca IEX, staleness/sanity-bounded), own-account context, the
  news/catalyst block (present-and-sealed switch state recorded here).
- F: macro / regime context (derived transform).
- G: sector cross-section (derived transform, frozen sector map).
- H: index / ETF constituent (frozen constituent map).
- I: regime classification (sealed REGIME_RULE transform).
- J: volatility (realised-only fallback explicitly named).
- K: liquidity (derived transform).
- L: catalyst calendar (sealed, dated public scheduled events only).
- M: own-decision history (read-only deterministic cross-wake own-log).
- Multi-horizon B widening; conditional fundamentals (SEC EDGAR / XBRL primary
  facts only, `sec_edgar` source).

## Block N — sealed named-account / named-subreddit social

Governed by RESEARCH/SCRAPE_CHANNELS.txt (pinned Actor IDs + pinned builds,
closed literal named list, parameter-free input template with NO
searchTerms/query field ever populated, sealed cadence/recency/per-entity
N_max/token ceiling). Same A-M envelope (`status`, `as_of`, `fetched_at`,
visible-missing, first-wake = normal-wake).

Per-item N-CONTEXT fields (127 §1.2): `author_id`, `post_id`, `captured_at`,
`edit_state` in `{as_captured | edited_after_capture_unknown |
deleted_after_capture}` (harness sets only `as_captured` at capture; later
states are reconstruction annotations, never a silent in-place update). Any
embedded/quoted third-party content is excluded or delivered in a separately
fenced, lower-ranked `embedded_untrusted` field. Replies / mentions-of
harvesting is excluded.

Free-text social is delivered inside an `untrusted_text` fence. The agent is
instructed (sealed prompt) that authenticity of authorship is not evidence of
truth of content.

### Block-N audit fields — INPUT-SIDE SEALED-LOG ONLY, NEVER BROADCAST (A5)

`corroboration` (annotation state), `single_source_social`,
`multi_social_uncorroborated`, `social_cross_pump_pattern` (bool),
`truncated`, `dropped_count`, `edit_state`. These are written to the
input-side sealed log only. They MUST NEVER render to the broadcast or the
standout JSON (A5, binding hand-off to the broadcast owner).

Corroboration trust-root (sealed predicate, mirror of RESEARCH/PLAN.txt
§1.1): a Block-N social claim's annotation can be lifted out of
`single_source_social` ONLY by a same-symbol, same-sealed-window datum from
SEC EDGAR (Block E), corporate actions (Block C), or a Block-B price move not
plausibly caused by the post itself. Agreement among any number of Block-N
social entities is deterministically NOT corroboration; N social sources with
the same claim and no authenticated corroborator are annotated
`multi_social_uncorroborated` (treated no stronger than
`single_source_social`). A same-wake price move concurrent with the assessed
post is `price_move_concurrent_not_independent`, never `price_confirmed`.
`social_cross_pump_pattern: true` when the same claim (mechanical match: same
symbol, same sealed window, social-only) appears across >=2 sealed Block-N
entities with no authenticated corroborator. Non-blocking; the feasibility
gate remains the sole order blocker.

## record_reasoning envelope

The agent's `record_reasoning` output carries its first-person reasoning plus
the mandatory in-context `critique` field. The `council` sub-record is
appended by the harness after the council stage (sealed-log only, A5; not
agent-authored).
