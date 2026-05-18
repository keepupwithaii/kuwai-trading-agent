#!/usr/bin/env python3
"""
The grounding linter (102 R2.4 / 131 §2.4). A deterministic, total, sealed
pure function: it resolves every cited payload_ref / datum_id in the trader's
reasoning envelope against the SAME wake's logged payload snapshot, and writes
a binary `grounded` plus `ungrounded_reason` plus the resolved citation map.

It NEVER blocks an order (the feasibility gate, broker/legal only, is the sole
blocker). It is externally reproducible from the sealed linter code + the
sealed payload schema + one logged triple. Standard library only.
"""
from __future__ import annotations


def _collect_refs(blocks: dict) -> set[str]:
    """The set of citable datum ids present in this wake's payload snapshot."""
    return set(blocks.keys())


def lint(reasoning_envelope: dict, payload: dict) -> dict:
    """Return {grounded: bool, ungrounded_reason: str, citation_map: {...}}.
    Total: any structural surprise yields grounded=False with a reason, never
    an exception that could break the loop.
    """
    try:
        blocks = payload.get("blocks", {})
        available = _collect_refs(blocks)
        cited = reasoning_envelope.get("payload_refs", [])
        if not isinstance(cited, list):
            return {"grounded": False,
                    "ungrounded_reason": "payload_refs not a list",
                    "citation_map": {}}
        citation_map = {}
        missing = []
        for ref in cited:
            ok = ref in available
            citation_map[str(ref)] = ok
            if not ok:
                missing.append(str(ref))
        # A move with no citation at all is ungrounded by definition.
        if not cited:
            return {"grounded": False,
                    "ungrounded_reason": "no payload_refs cited",
                    "citation_map": {}}
        if missing:
            return {"grounded": False,
                    "ungrounded_reason": f"cited refs not in payload: {missing}",
                    "citation_map": citation_map}
        return {"grounded": True, "ungrounded_reason": "",
                "citation_map": citation_map}
    except Exception as exc:  # totality: never raise into the loop
        return {"grounded": False,
                "ungrounded_reason": f"linter_internal:{exc!r}",
                "citation_map": {}}
