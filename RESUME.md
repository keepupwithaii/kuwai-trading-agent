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
- [x] `commitment-v2/MODEL.txt` (bare: `claude-opus-4-7` then `0.7`, nothing
      else; C-MODEL backstop)
- [x] `commitment-v2/TOOLS.md` (3-tool contract: perceive / propose_orders /
      record_reasoning, with bounds, 102 R2.2, transcribed)
- [x] `commitment-v2/PERCEPTION_SCHEMA.md` (~13 blocks A-M + Block N + N-CONTEXT
      fields + untrusted_text/embedded_untrusted fencing + source enum + audit
      fields marked sealed-log-only never broadcast A5)
- [x] `commitment-v2/UNIVERSE.txt` (broad all-sector fractional-eligible US
      equities/ETFs, alphabetical non-thesis; crypto EXCLUDED; no subset)
- [x] `commitment-v2/SCHEDULE.txt` (~30-min RTH window-guarded + 1 pre-close
      wake; crypto leg absent-and-sealed; UTC timer Persistent)
- [x] `commitment-v2/RELATIONSHIP.md` (single-program reality per brief §0 / 67;
      clause-4 = V1-resolved clean-correction wording; reversion held ready)
- [x] `commitment-v2/WEEKLY-POLICY.md` (94 C2.5 verbatim closed outcome-blind +
      10 closed BUG-CLASSES)
- [x] `commitment-v2/corpus/` (94 C2.2 closed exclusion set; view-free;
      README + neutral NO-EDGE)
- [x] `commitment-v2/COUNCIL/` (PRO/CON/SYNTHESISER prompts, FAULT_LIST.txt
      closed no-boldness, SCHEMA.md closed council-v1 with bound-(g)
      cited-item-to-step shape + deterministic disposition; MF-2 counterweight
      stays in the SYSTEM_PROMPT clause, not duplicated)
- [x] `commitment-v2/RESEARCH/` (PLAN with N12 trust-root + post-caused-price
      + social_cross_pump; SOURCES, QUERY_TEMPLATE parameter-free, RECENCY,
      MISSING_POLICY, FUNDING, RECONSTRUCTION 4-class+R4 3-tier,
      SCRAPE_CHANNELS scaffolded, REGIME_RULE, TRANSFORMS)
      FLAG: SCRAPE_CHANNELS closed named-entity list is NOT invented
      (integrity-sensitive curation surface, unspecified in spec). Required
      sealed-config input before seal; empty-but-sealed = safe non-load-bearing
      state for build/conformance/paper. Also actor ids/build hashes are the
      execution-terminal-owned pre-seal Apify build-confirms (67).
- [x] `commitment-v2/code/` harness COMPLETE (9 modules, all compile;
      council R-1 bind smoke-verified): manifest_io, hashlog, feasibility_gate,
      floor, perception, grounding_linter, council, amendment_loader, standout,
      agent_loop. Commits 086f866, 7f4a2ac.
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

code/ harness is COMPLETE. Now, in order:
1. `commitment-v2/MANIFEST.txt` (per-file SHA-256 of every sealed file +
   pinned code git commit SHA; BUILD ARTEFACT ONLY; the real pre-registration
   hash is the Maran-gated seal step, not this).
2. repo-root `README.md` (94 C2.6 verbatim seal claim + not-advice/ASIC line +
   verify-hash-and-OTS steps + the SOL rights line; NOT inside commitment-v2/;
   no LICENSE file).
3. `conformance/gate.py` binary suite: 139 §2 plumbing + C-MODEL,
   C-COUNCIL-PROMPT (byte-identity to freshly re-derived 151 §4 + January 2026
   fill, via build_tools/council_prompt_extract), C-COUNCIL-SEAL,
   C-COUNCIL-SCHEMA-GUARD (+ R-1 Fixture A substantive-reject-zero-retry & B
   schema-garble-exactly-one-retry), C-COUNCIL-HALT-SAFE (retry-trigger-scope),
   C-COUNCIL-A5, C-STANDOUT-ISOLATION, C-CONCESSION, C-MANIFEST, C-SECRETS,
   C-LOCKFILE, C-RELATIONSHIP. Model STUBBED, no order, no network, no seal
   artefact. Binary all-pass; on fail fix the BUILD, never weaken an assertion.
4. `deploy/` systemd service+timer, watchdog service+timer, external dead-man
   hook, RUNBOOK (27 §3-§6) -- artefacts only, not executed here.
5. run the binary conformance gate to green.
6. deploy to VPS + ONE compressed PAPER cycle on the PAPER key, observe green.
7. STOP, report, HOLD at pause point (b).

Superseded prior per-module note kept for history:
1. `manifest_io.py` (read MODEL.txt/UNIVERSE/SCHEDULE etc deterministically)
2. `hashlog.py` (append-only hash-chained log writer, prev-hash chain,
   terminal HALT entry)
3. `feasibility_gate.py` (the 7 checks, broker/legal only, never strategy)
4. `floor.py` (agent-blind agent-unreachable floor_check, equity<=0.45*E0,
   E0 captured at publish-precedes-trade boundary; placeholder + STATUS note
   until then; one input/one threshold/one action, never re-based)
5. `perception.py` (deterministic assembler to PERCEPTION_SCHEMA; MISSING/
   STALE sentinels; Block N sealed-config, no live scrape in paper/conformance)
6. `council.py` (PRO/CON/SYNTHESISER; deterministic post-parse guard; bound-(g)
   shape; R-1 bind: schema-structural-only one retry, substantive bound-(g)
   reject HALTs zero-retry; fail-safe-to-HALT)
7. `amendment_loader.py` (ExecStartPre hash-check, no live-patch path)
8. `standout.py` (deterministic read-only standout JSON; MF-7 no per-wake
   class label; S-COUNCIL-CONTESTED dropped; symmetric vocabulary; reads only
   the A5-stripped broadcast-safe projection)
9. `agent_loop.py` (flock, reconcile-before-decide, deterministic
   client_order_id, one model call STUBBED-capable, wires 1-8)
Then MANIFEST.txt, repo-root README.md, conformance/ gate, deploy/.

Old (superseded) prior note retained below for history:
Build `commitment-v2/RESEARCH/`: PLAN.txt (static finite acyclic
deterministic fetch+derive graph with sealed node bound + wall-clock budget;
the corroboration node carrying the §1.1 trust-root + post-caused-price rule +
social_cross_pump_pattern; the read-only cross-wake own-history node),
SOURCES.txt, QUERY_TEMPLATE.txt (parameter-free, NO searchTerms/query),
RECENCY.txt, MISSING_POLICY.txt, FUNDING.txt, RECONSTRUCTION.md (four-class
sort R1-R4 + R4 three-tier standard), SCRAPE_CHANNELS.txt (pinned Actor IDs +
pinned builds, closed literal named list, sealed cadence/recency/per-entity
N_max/token ceiling), REGIME_RULE.txt + the sealed sector/vol/liquidity/
calendar transform defs. Per 131 §2.6, 102 R2.6, 128, 94.
