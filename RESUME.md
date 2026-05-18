# RESUME.md — commitment-v2 build resume anchor

A fresh execution session resumes by reading the same paste-prompt, then
EXECUTION-TERMINAL-HANDOVER.md, then this file. Never restart from scratch.
Never re-derive spec. SPEC_ROOT = `/Users/maraneweda/Downloads/kuwai-gta-agent`.
Synced vault status file:
`/Users/maraneweda/Obsidian/Big Brain/reports/kuwai-gta-agent/EXECUTION-TERMINAL-STATUS.md`.

Build dir: `~/projects/kuwai-gta-agent/commitment-v2-build/` (own local git).
Sealed tree: `commitment-v2/`. Build helpers: `build_tools/` (NOT sealed).
Conformance: `conformance/` (NOT sealed). Deploy artefacts: `deploy/` (NOT sealed).

Stdlib-only Python 3 for the harness (no pip deps -> C-LOCKFILE satisfied by a
declared no-third-party-deps lockfile + reproducible-build note; matches the v0
"nothing pip-installed can rot" discipline and 27 ops).

## Hard bounds (unchanged, absolute)

Pause point (b). Build + conformance gate + VPS deploy + ONE compressed paper
cycle on the PAPER key are autonomous. Hash/OTS/public tag/Release/X/KUWAI/
live-key/first real fill each need Maran's explicit separate per-step trigger,
in order. A general "go" is not a seal trigger.

## Cadence after every component (no exceptions)

1. git commit in this build dir.
2. update this RESUME.md (next-step anchor).
3. update EXECUTION-TERMINAL-STATUS.md in the synced vault (timestamped line).

## Build order (commitment-v2 manifest: 131 §2 + 102 + 94 + Wave-14 + R-1)

- [x] Skeleton + local git + STATUS.md + vault status file
- [x] `commitment-v2/SYSTEM_PROMPT.md` (byte-verbatim from 151 §4, fill
      {MODEL_CUTOFF_DATE} -> January 2026; built via build_tools extraction;
      C-COUNCIL-PROMPT is the byte-identity backstop)
- [ ] `commitment-v2/MODEL.txt` (pinned claude-opus-4-7 id + temperature 0.7)
- [ ] `commitment-v2/TOOLS.md` (3-tool contract: perceive / propose_orders /
      record_reasoning, with bounds, 102 R2.2)
- [ ] `commitment-v2/PERCEPTION_SCHEMA.md` (~13 blocks A-M + Block N + N-CONTEXT
      fields + untrusted_text/embedded_untrusted fencing + source enum)
- [ ] `commitment-v2/UNIVERSE.txt` (broad fractional-eligible US equities/ETFs;
      crypto EXCLUDED everywhere; no crypto subset)
- [ ] `commitment-v2/SCHEDULE.txt` (~30-min RTH window-guarded + 1 pre-close
      wake; NO crypto leg, NO 24/7 timer)
- [ ] `commitment-v2/RELATIONSHIP.md` (single-program reality per brief §0 / 67;
      clause-4 = V1-resolved clean-correction wording)
- [ ] `commitment-v2/WEEKLY-POLICY.md` (94 C2.5 verbatim closed outcome-blind)
- [ ] `commitment-v2/corpus/` (94 C2.2 closed exclusion set; view-free)
- [ ] `commitment-v2/COUNCIL/` (PRO_PROMPT, CON_PROMPT, SYNTHESISER_PROMPT,
      FAULT_LIST.txt, SCHEMA.md; bound-(g) cited-item-to-step shape; MF-2
      symmetric counterweight is in the SYSTEM_PROMPT council clause already)
- [ ] `commitment-v2/RESEARCH/` (PLAN, SOURCES, QUERY_TEMPLATE, RECENCY,
      MISSING_POLICY, FUNDING, RECONSTRUCTION, SCRAPE_CHANNELS, REGIME_RULE +
      sealed transform defs; trust-root + post-caused-price + social_cross_pump)
- [ ] `commitment-v2/code/` harness: loop (flock, reconcile-before-decide,
      deterministic client_order_id), feasibility gate (7 checks, broker/legal
      only), perception assembler, agent-blind floor_check() 0.45*E0,
      council module (post-parse guard, R-1 retry bind), hash-chained log
      writer, amendment loader (ExecStartPre hash-check, no live-patch),
      deterministic standout-report generator
- [ ] `commitment-v2/MANIFEST.txt` (per-file SHA-256 + pinned code commit; build
      artefact only; real pre-registration hash is the seal step, Maran-gated)
- [ ] repo-root `README.md` (94 C2.6 verbatim seal claim + not-advice/ASIC +
      verify-hash-and-OTS steps + the SOL rights line) and `.gitignore`
      (27 §3.6 + C-SECRETS); NOT inside commitment-v2/
- [ ] `conformance/` binary gate: 139 §2 asserts + 6 Wave-14 council asserts +
      C-MODEL/C-CONCESSION/C-MANIFEST/C-SECRETS/C-LOCKFILE/C-RELATIONSHIP +
      two R-1 fixtures; model STUBBED, no order/network/seal; binary all-pass
- [ ] `deploy/` systemd service+timer, watchdog service+timer, external
      dead-man hook, RUNBOOK (27 §3-§6)
- [ ] run binary conformance gate to green
- [ ] deploy to VPS + ONE compressed PAPER cycle, observe green
- [ ] STOP, report, HOLD at pause point (b) for Maran's per-step triggers

## NEXT ACTION

Build `commitment-v2/MODEL.txt`: exactly the pinned `claude-opus-4-7` snapshot
id line and the temperature `0.7` line, nothing else (102 R2.6 / 94 C2.1 /
139 §1.1; the prompt body carries no temperature string).
