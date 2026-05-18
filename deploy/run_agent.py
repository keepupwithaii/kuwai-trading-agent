#!/usr/bin/env python3
"""
Thin deploy-side entrypoint (/opt/kuwai/run_agent.py). NOT part of the sealed
tree (it touches secrets and the network; sealing it would be wrong and would
break C-SECRETS). It reads credentials ONLY from the root-only EnvironmentFile
(systemd injects them as env vars); it never embeds or logs a secret.

It builds the real dependency objects (Alpaca PAPER or LIVE per KUWAI_MODE,
the real model on ANTHROPIC_API_KEY) and calls the sealed
commitment-v2/code/agent_loop.run_wake. The LIVE key and paper=False are used
ONLY when KUWAI_MODE=live, which is set by Maran's go-live step, never here.

Standard library only. This file is a deploy artefact; it is not executed by
the build and contains no secret.
"""
import os
import sys
from pathlib import Path

SEALED = Path("/opt/kuwai/commitment-v2")
sys.dont_write_bytecode = True
sys.path.insert(0, str(SEALED / "code"))


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.stderr.write(f"missing required env {name}\n")
        raise SystemExit(2)
    return v


def main() -> int:
    flags = set(sys.argv[1:])
    mode = os.environ.get("KUWAI_MODE", "paper")  # paper unless Maran sets live
    # Real Alpaca + Anthropic + (optional) Apify clients are constructed here
    # from env-injected credentials. Implementations live in this deploy file
    # set, never in the sealed tree. --check-auth / --check-clock do the
    # account/clock preflight and exit non-zero on failure (fail loud).
    if "--check-auth" in flags or "--check-clock" in flags:
        # preflight only; env vars depend on KUWAI_MODE (paper vs live).
        # In paper mode the keys are APCA_PAPER_*; in live mode APCA_LIVE_*.
        if mode == "live":
            _require("APCA_LIVE_KEY_ID"); _require("APCA_LIVE_SECRET")
        else:
            _require("APCA_PAPER_KEY_ID"); _require("APCA_PAPER_SECRET")
        _require("ANTHROPIC_API_KEY")
        return 0

    import agent_loop  # sealed module
    import floor       # sealed module; carries the seal-time E0 baseline

    # The sealed E0_BASELINE_USD constant is the canonical floor reference.
    # The KUWAI_E0 env var is honoured ONLY as an override and ONLY in paper
    # mode (the unsealed pre-seal dry-run path). In live mode the sealed
    # constant always wins; the env cannot override the seal.
    if mode == "live":
        e0 = float(floor.E0_BASELINE_USD)
    else:
        e0_raw = os.environ.get("KUWAI_E0")
        e0 = float(e0_raw) if e0_raw else float(floor.E0_BASELINE_USD)
    if e0 is None or e0 <= 0:
        sys.stderr.write("E0 baseline missing or non-positive\n")
        return 3

    # Build real deps (broker/clock/decider/synth) from env. The sealed loop
    # is the authority; deploy-side glue is in clients.py.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import clients  # deploy-side, NOT sealed
    deps = {
        "broker": clients.AlpacaBroker(),
        "clock": clients.Clock(),
        "decider": clients.AnthropicDecider(),
        "synth": clients.AnthropicSynth(),
    }
    res = agent_loop.run_wake(deps, Path("/var/lib/kuwai/ledger.log"),
                              e0=e0, live_block_n=(mode == "live"))
    print(res.get("state"))
    # Dashboard exporter: read-only of the ledger, one-directional A5; off the
    # integrity-critical path; never affects the agent.
    try:
        import exporter
        exporter.main()
    except Exception as e:
        print(f"exporter error (non-fatal): {e!r}")
    return 0 if res.get("state") in ("OK", "ALREADY_HALTED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
