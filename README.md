# kuwai-trading-agent

This repository is the public container for the sealed autonomous trading
agent `commitment-v2`. It is published for independent verification of the
seal. Nothing here is financial advice.

This README is a repo-root file. It is deliberately NOT inside the sealed
`commitment-v2/` tree (the sealed tree is the exact closed manifest list).
This repository is empty/unpublished until the operator's explicit seal
trigger; the hash and Release URL below are filled only at that step.

## The seal claim (verbatim, conceded, not stronger)

> "I sealed the AI's mind, set it loose with real money, and I cannot touch
> it between weekly check-ins. Here is the seal: the model, its instructions,
> what it can do, what it can see, and the code, all hashed and
> Bitcoin-stamped public before it traded a cent on its own account. You can
> re-check the hash and the timestamp yourself, trusting nobody. **What this
> proves is that I did not steer it and could not have rewritten it after the
> fact - it is tamper-evident. It does not prove the trades can be replayed:
> there is no fixed seed, an AI run is not bit-for-bit reproducible, and I am
> telling you that openly rather than pretending otherwise. And it proves
> nothing about whether it makes money. The seal is an honesty receipt, not a
> performance claim. Most likely it loses. The seal only means the loss, or
> the win, is the machine's and not mine.**"

## Not advice (ASIC posture)

This is an AI-education project documenting an autonomous experiment. It is
not financial product advice and not a recommendation. No performance is
promised. The agent is the actor; the operator narrates and never recommends.
There are no live actionable signals, no affiliate or referral links. Only the
agent's own-account data is ever shown.

## Verify the seal yourself (trust nobody)

1. Clone this repository at the published tag `commitment-v2`.
2. Recompute the canonical sealed-tree hash:
   for every file under `commitment-v2/` in sorted POSIX-relative-path order,
   feed `path` `NUL` `bytes` `NUL` into SHA-256 (the exact algorithm in
   `commitment-v2/code/amendment_loader.py:canonical_tree_hash`). Confirm it
   equals the 64-character hash in the published Release and the X post.
   `MANIFEST.txt` lists each file's individual SHA-256 so you can find any
   single changed file across versions.
3. Verify the OpenTimestamps proof: `ots verify commitment-v2.zip.ots`
   against `commitment-v2.zip`. This anchors the seal to a Bitcoin block.
4. Confirm the Bitcoin block time of the seal is strictly BEFORE the first
   real fill on the agent's brokerage account. That ordering is the integrity
   claim: the agent was sealed and published before it traded a cent.
5. Read `commitment-v2/SYSTEM_PROMPT.md`, `corpus/`, `RESEARCH/`, `COUNCIL/`
   and `code/` directly. The prompt, corpus, gate, universe, schedule and the
   closed weekly-amendment policy are all public and diffable, at every
   version. `WEEKLY-POLICY.md` is the closed, outcome-blind list of the only
   reasons any change may ever be made.

Seal hash (filled at the seal step): `<64-CHAR-SHA256 - filled at seal>`
Release URL (filled at the seal step): `<RELEASE URL - filled at seal>`
First-fill vs publish timestamps (filled after go-live): `<filled post go-live>`

---

Published for independent verification of the seal, not for reuse. All rights
reserved, SOL Studios.
