# RESEARCH/RECONSTRUCTION.md — the four-class reconstruction standard (sealed)

Extended and sealed under the unchanged 94 mechanism (128, the Block-N 3-tier
standard). It is a membership-and-content statement for an already-sealed
object, not a new seal mechanism. It states how a sceptic reconstructs what the
agent saw.

## The four-class block sort

- R1 fresh public-source fetch: a sceptic re-fetches the same public source
  (Alpaca IEX bars, Alpaca/Benzinga news, SEC EDGAR, corporate actions) for
  the sealed window and gets materially the same slice.
- R2 deterministic transform: derived blocks (macro/regime, sector, index,
  volatility, liquidity, calendar) re-derive bit-for-bit from R1 inputs by the
  sealed transform definitions. Strengthened: the transform defs are sealed.
- R3 own sealed hash-chained log: own-account state and own-decision history
  reconstruct from the published hash-chained log.
- R4 ephemeral scraped social (Block N): the one class that can degrade.

## The R4 three-tier standard

- Tier 1: the sealed channel / Actor / account / template definition
  (SCRAPE_CHANNELS.txt) is fully bit-checkable forever via SHA-256/OTS over
  the sealed list. This is the dominant operator-curation gate and does not
  degrade.
- Tier 2: material-not-bit-identical where an independent archive exists;
  declared a larger delta than the Benzinga/news delta.
- Tier 3: degrades to trust-the-sealed-timestamped-capture where a post is
  deleted/edited and unarchived. Conceded plainly. This is the same kind as
  the existing material-not-bit-identical position, declared as a larger delta
  inside the existing eighth concession clause; it adds no new on-camera beat.

A sceptic re-runs R1/R2/R3 deterministically; R4 is honestly named at its tier.
The Tier-1 list-is-sealed SHA-256/OTS check covers SCRAPE_CHANNELS.txt.
