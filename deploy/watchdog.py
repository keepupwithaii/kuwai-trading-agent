#!/usr/bin/env python3
"""
Independent dead-man watchdog (27 §4). Reads the latest hash-chain heartbeat
and applies the calendar-aware silently-dead test, then pings the external
dead-man (healthchecks.io / cronitor). Standard library only. NOT sealed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GRACE_MIN = 90
LOG = Path(os.environ.get("KUWAI_LEDGER", "/var/lib/kuwai/ledger.log"))
DEAD_MAN = os.environ.get("HEALTHCHECKS_PING_URL", "").strip()


def _last_heartbeat_ts() -> str:
    if not LOG.exists():
        return ""
    last = None
    with LOG.open() as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") in ("HEARTBEAT", "HALT"):
                last = e.get("ts_utc")
    return last or ""


def _ping(suffix: str = "") -> None:
    if not DEAD_MAN:
        return
    try:
        urllib.request.urlopen(DEAD_MAN + suffix, timeout=10).read()
    except Exception:
        pass


def main() -> int:
    sys.dont_write_bytecode = True
    hb = _last_heartbeat_ts()
    if not hb:
        _ping("/fail")
        sys.stderr.write("no heartbeat in ledger\n")
        return 1
    age = (datetime.now(timezone.utc)
           - datetime.fromisoformat(hb)).total_seconds() / 60.0
    if age > GRACE_MIN:
        # calendar awareness is delegated to the agent itself (the run is
        # not scheduled outside market hours by the timer + RTH guard); a
        # gap inside the window past GRACE is a silent-death signal.
        _ping("/fail")
        sys.stderr.write(f"heartbeat stale: {age:.1f} min\n")
        return 1
    _ping()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
