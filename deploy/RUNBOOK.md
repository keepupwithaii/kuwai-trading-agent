# RUNBOOK.md — KUWAI commitment-v2 unattended ops (27 §3-§6)

One page, pre-written so 3am-self does not improvise. Deployable artefact;
not executed by the build.

## Layout on the VPS

- `/opt/kuwai/commitment-v2/`  the sealed tree at the published tag (read-only)
- `/opt/kuwai/run_agent.py`    thin entrypoint: parse flags, build deps
                               (real Alpaca PAPER or LIVE key, real model on
                               ANTHROPIC_API_KEY), call
                               `commitment-v2/code/agent_loop.run_wake`
- `/opt/kuwai/watchdog.py`     calendar-aware silently-dead test + external
                               dead-man ping
- `/etc/kuwai/agent.env`       root-only EnvironmentFile, chmod 600, NEVER in
                               the repo. Holds APCA key/secret, ANTHROPIC key,
                               APIFY token, SEAL_EXPECTED_HASH, healthchecks
                               ping URL, the captured E0. .gitignored.
- `/var/lib/kuwai/ledger.db`   SQLite system of record (gitignored, off-box
                               nightly backup)

## Host hardening baseline (sealed ops criteria, 27 §3.6, 139 §3 item 9)

Ubuntu 24.04 LTS, UTC pinned (`timedatectl set-timezone UTC`), SSH-key-only,
password login disabled, ufw allowing only SSH out + Alpaca + Anthropic
(+ Apify only if Block N populated), unattended-security-upgrades on. Two
Alpaca keys: primary in the env file, spare in the operator password manager
offline of the VPS. The secret-scan report
(`conformance/secret-scan-report.txt`, committed OUTSIDE the sealed tree) is
referenced here and must read CLEAN before any deploy (C-SECRETS).

## Failure protocol (pre-decided; 27 §5; never improvise)

| Condition | Action |
|---|---|
| Broker 5xx / timeout | SKIP this wake, WARN, retry next fire. No flatten. |
| Data stale / IEX gap | SKIP this wake, WARN. Never act on suspect data. |
| Auth fail / not ACTIVE | HALT, HIGH alert, runbook. Cannot trade anyway. |
| Single order reject | HOLD, classify+log, WARN, re-decide next wake. |
| Repeated rejects (N) | HALT new entries, HIGH alert. Systemic, stop digging.|
| Unhandled exception | run ends; next fire reconciles; M recurrences -> HALT.|
| Position/price discontinuity | HALT + HIGH alert, human verifies (corp action).|
| floor_check breach (<=0.45*E0) | terminal HALT-and-log, no liquidate, exit, no intra-week restart. |
| Council HALT / double garble | no trade, terminal HALT-and-log, await weekly. |
| Catalyst passes while halted | record honestly. No retroactive action. |
| Model endpoint death / sealed MODEL.txt id unresolvable | HALT-and-log, HIGH alert, await weekly. NEVER silently fall back to a different model (a model swap is a seal break, only a public commitment-vN+1). |
| Scrape-actor staleness (Block N thin N consecutive wakes) | watchdog WARN STALE; run continues; Block N is non-load-bearing. |
| Maran missed weekly check-in N weeks | safe-by-default: sealed agent runs unchanged; only no amendment applied. A HALT-class condition during the gap stays HALTed (correct, not a defect). |
| External dead-man itself down | HIGH alert; verify the agent independently. |

Doctrine: flatten ONLY on a pre-registered circuit breaker; everywhere else
skip-and-reconcile or halt-and-alert. The floor HALT does NOT liquidate.

## Recovery steps

1. AUTH_FAIL -> SSH in, swap APCA key/secret to the spare in the env file,
   `systemctl restart kuwai-agent`, `run_agent.py --check-auth`, confirm OK.
2. Silently dead, auth OK -> `systemctl status`/`journalctl`, VPS up?, disk?,
   Alpaca status page. Likely a hung run killed by TimeoutStartSec; verify
   the next fire reconciles cleanly.
3. Discontinuity -> do NOT override the HALT remotely in a panic; verify the
   corporate action, reconcile, only then resume.
4. Out-of-policy change ever needed -> it is a public commitment-vN+1 with its
   own hash/OTS/changelog under the closed WEEKLY-POLICY.md, never a live edit.

## Go-live (Maran-triggered only, per-step; pause point (b))

The deploy of the artefacts and ONE compressed PAPER cycle on the PAPER key
are autonomous. Switching to the LIVE key + `paper=False` on account
258088643 and the first real fill are Maran-triggered, strictly AFTER the
publish-precedes-trade step. See EXECUTION-TERMINAL-HANDOVER §6.
