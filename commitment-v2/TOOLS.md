# TOOLS.md — the exact action contract (sealed, 102 R2.2)

The agent's entire reach is exactly these three tools and no others. This is
the most important deterministic boundary. Judgement is unconstrained; reach is
three tools. Sealed verbatim; no tool may be widened post-hoc.

## perceive()

Returns the deterministic sealed-schema perception bundle (see
PERCEPTION_SCHEMA.md): own-account state (reconciled equity, cash, settled
cash, positions and tracked qty, prior-wake order outcomes including any gate
rejection reason, PDT day-trade count), market data (prior-session daily bars +
recent intraday bars + last trade for every universe symbol, staleness- and
sanity-bounded by the harness so a bad print never reaches the agent), the
news/catalyst block and the ~13 blocks A-M plus Block N exactly as
PERCEPTION_SCHEMA.md fixes them. Read-only.

Hard bound: the agent cannot choose what is in the bundle. The harness
assembles it deterministically; the schema is sealed. The agent does NOT
perceive its own floor distance (the floor is agent-blind and agent-unreachable).

## propose_orders(list)

The ONLY action tool. The agent returns a list. Per order: a symbol (must be in
UNIVERSE.txt), a side (buy or sell), and a size expressed as notional USD, or as
a fraction of settled cash, or as a fraction of the current tracked position.

Hard bound: every proposed order passes the deterministic feasibility gate
(broker/legal feasibility only, never strategy) before any order reaches the
broker. A rejected order is logged with its reason and never submitted; the
agent is told on the next wake that it was rejected and why. The agent never
names an order type; the harness always builds notional market DAY.

## record_reasoning(text)

Writes the agent's stated reason for this wake into the hash-chained log.
Bounded length. Written whether or not an order was proposed. It is the agent's
own first-person voice.

Hard bound: narration and audit only. It never gates an order and never writes
a numeric result. It includes the mandatory in-context `critique` field in the
record_reasoning envelope (X2 self-critique instruction).

## What the agent cannot do, by absence of any tool (not by instruction)

Cancel or replace at the broker API outside propose_orders; set server-side
brackets / OCO / trailing stops; trade on margin, short, options, or
extended-hours equities; change its own schedule; read or write its own code,
prompt, corpus, schema, or universe; read, alter, or disable the floor; see the
operator's inputs; or call the broker directly. Every one is absent by
construction.
