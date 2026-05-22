#!/usr/bin/env python3
"""
Deterministic perception assembler (102 R2.2, PERCEPTION_SCHEMA.md). The
agent cannot choose what is in the bundle. Missing/out-of-date data is stated
plainly (MISSING / STALE / UNAVAILABLE), never silently filled. The bundle
NEVER includes floor distance (the floor is agent-blind). Standard library
only.

Block N is sealed-config only in the build, the conformance gate, and the
compressed paper cycle: it is reported UNAVAILABLE there (no live scrape ever
runs in those contexts; SCRAPE_CHANNELS.txt scrape_in_paper_cycle=never,
scrape_in_conformance=never).
"""
from __future__ import annotations

from datetime import datetime, timezone

SOURCES = {"alpaca_account", "alpaca_md_iex", "alpaca_news", "benzinga",
           "sec_edgar", "corporate_actions", "derived_transform", "own_log",
           "block_n_social", "harness_sentinel"}


def _datum(value, as_of, source, status="OK"):
    if source not in SOURCES:
        raise ValueError(f"unsealed source {source!r}")
    return {
        "value": value,
        "as_of": as_of,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "status": status,
    }


def _sentinel(reason, source="harness_sentinel"):
    return _datum(None, None, source, status=reason)  # MISSING/STALE/UNAVAILABLE


def assemble(raw: dict, *, live_block_n: bool) -> dict:
    """Build the schema-conformant payload from already-fetched raw inputs.

    `raw` carries optional keys: account, bars, news, edgar, corp_actions,
    derived, own_history. A missing/failed key becomes a sentinel datum; it is
    never estimated. `live_block_n` is False for build/conformance/paper.
    """
    payload: dict = {"schema": "perception-v1",
                     "assembled_at": datetime.now(timezone.utc).isoformat(),
                     "blocks": {}}
    b = payload["blocks"]

    acct = raw.get("account")
    if acct is None:
        b["O_own_account"] = _sentinel("UNAVAILABLE", "alpaca_account")
    else:
        # NOTE: no floor distance field exists anywhere in the payload.
        b["O_own_account"] = _datum(
            {k: acct[k] for k in ("equity", "cash", "settled_cash",
                                  "positions", "prior_wake_orders",
                                  "pdt_daytrade_count") if k in acct},
            acct.get("as_of"), "alpaca_account",
            status=acct.get("status", "OK"))

    for key, src, label in (
        ("bars", "alpaca_md_iex", "A_market_bars"),
        ("news", "alpaca_news", "C_news_catalyst"),
        ("edgar", "sec_edgar", "E_edgar_primary"),
        ("corp_actions", "corporate_actions", "C2_corporate_actions"),
        ("derived", "derived_transform", "FGHIJKL_derived"),
        ("own_history", "own_log", "M_own_history"),
    ):
        v = raw.get(key)
        if v is None:
            b[label] = _sentinel("UNAVAILABLE", src)
        else:
            b[label] = _datum(v.get("value"), v.get("as_of"), src,
                              status=v.get("status", "OK"))

    # Block N: sealed-config only outside real runtime. Never live-scraped in
    # build/conformance/paper. Audit fields are input-side-sealed-log only and
    # are NOT placed in the broadcast-safe projection (A5).
    if live_block_n:
        n = raw.get("block_n")
        if n is None:
            b["N_social"] = _sentinel("UNAVAILABLE", "block_n_social")
        else:
            b["N_social"] = _datum(n.get("value"), n.get("as_of"),
                                   "block_n_social",
                                   status=n.get("status", "OK"))
    else:
        b["N_social"] = _sentinel("UNAVAILABLE", "block_n_social")

    return payload


def broadcast_safe_projection(payload: dict, council_disposition: str,
                              bright_line_halt: bool) -> dict:
    """The A5-stripped projection the standout report may read. It carries
    NO Block-N audit fields, NO per-wake bright-line fault CLASS label, NO
    council internals. Only: council ran, the coarse disposition, and the
    coarse generic fact that a bright-line HALT occurred this wake (MF-7).
    """
    return {
        "council_ran": True,
        "council_disposition": council_disposition,  # proceed|halt only
        "bright_line_halt_occurred": bool(bright_line_halt),  # coarse, generic
        "assembled_at": payload.get("assembled_at"),
    }
