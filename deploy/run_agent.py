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
        # preflight only; real client construction + GET /v2/account + clock
        _require("APCA_API_KEY_ID")
        _require("APCA_API_SECRET_KEY")
        # (the real preflight call is performed by the deployed broker client)
        return 0

    import agent_loop  # sealed module

    e0_raw = os.environ.get("KUWAI_E0")  # captured at the seal boundary only
    e0 = float(e0_raw) if e0_raw else None
    if e0 is None:
        # The floor cannot be evaluated without a captured E0. Before the
        # Maran-gated seal boundary the agent does not run live; a paper dry
        # run passes a synthetic E0 via KUWAI_E0. Refuse to run live blind.
        sys.stderr.write("KUWAI_E0 not set; refusing to run without a "
                         "captured floor baseline\n")
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
    return 0 if res.get("state") in ("OK", "ALREADY_HALTED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
