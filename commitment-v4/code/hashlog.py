#!/usr/bin/env python3
"""
Append-only hash-chained log writer. Every decision/event is written at the
instant it happens. Each entry carries the prior entry's hash, so any tamper
is detectable by re-walking the chain. Standard library only.

entry_hash = sha256( canonical_json(entry_without_hash) + prev_hash ).

A terminal HALT entry is the last writable entry of a run; nothing is written
after it until a human acts at a weekly boundary (94 / 102 R2.4 / 27 §5).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _canon(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")


def _hash(entry_without_hash: dict, prev_hash: str) -> str:
    h = hashlib.sha256()
    h.update(_canon(entry_without_hash))
    h.update(prev_hash.encode("ascii"))
    return h.hexdigest()


class HashLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                last = json.loads(line)["entry_hash"]
        return last

    def is_halted(self) -> bool:
        """True if the chain's last entry is a terminal HALT."""
        if not self.path.exists():
            return False
        last_obj = None
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_obj = json.loads(line)
        return bool(last_obj) and last_obj.get("kind") == "HALT"

    def append(self, kind: str, body: dict) -> str:
        """Append an entry. Returns its entry_hash. Refuses to write past a
        terminal HALT (the run is stopped until a human acts)."""
        if self.is_halted():
            raise RuntimeError("chain is terminally HALTed; refuse to append")
        prev = self._last_hash()
        entry = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "prev_hash": prev,
            "body": body,
        }
        entry["entry_hash"] = _hash(entry, prev)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        return entry["entry_hash"]

    def append_halt(self, reason: str, body: dict) -> str:
        """Write the terminal HALT entry. After this nothing more is written."""
        prev = self._last_hash()
        entry = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "HALT",
            "reason": reason,
            "prev_hash": prev,
            "body": body,
        }
        entry["entry_hash"] = _hash(entry, prev)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        return entry["entry_hash"]

    def verify_chain(self) -> bool:
        """Re-walk the chain; True iff every link is intact."""
        if not self.path.exists():
            return True
        prev = GENESIS
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                stated = obj.pop("entry_hash")
                if obj.get("prev_hash") != prev:
                    return False
                if _hash(obj, prev) != stated:
                    return False
                prev = stated
        return True
