#!/usr/bin/env python3
"""
Deploy-side network clients. NOT inside the sealed tree (they touch the
network and credentials; sealing them would break C-SECRETS). Standard
library only.

- AlpacaBroker: account / reconcile / submit. Paper or live per KUWAI_MODE.
- Clock: rth_open via Alpaca clock endpoint.
- AnthropicDecider: the ONE per-wake model call. Uses tool use so the model
  invokes propose_orders / record_reasoning per TOOLS.md. The system prompt is
  the byte-verbatim sealed SYSTEM_PROMPT.md.
- AnthropicSynth: the council SYNTHESISER call (stub-compatible signature).

Secrets come ONLY from env (systemd EnvironmentFile). Never echoed.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path

CTX = ssl.create_default_context()


def _http_json(method: str, url: str, headers: dict, body: dict | None = None,
               timeout: int = 30) -> dict:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Surface the server's error payload (no secrets in it; the
        # APCA/Anthropic error bodies describe what is wrong with the request).
        try:
            payload = e.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        raise urllib.error.HTTPError(
            e.url, e.code, f"{e.reason} :: {payload[:600]}", e.headers, None)


# ---- Alpaca ----------------------------------------------------------------
class AlpacaBroker:
    def __init__(self):
        mode = os.environ.get("KUWAI_MODE", "paper")
        if mode == "live":
            self.base = "https://api.alpaca.markets"
            self.key = os.environ["APCA_LIVE_KEY_ID"]
            self.sec = os.environ["APCA_LIVE_SECRET"]
        else:
            self.base = "https://paper-api.alpaca.markets"
            self.key = os.environ["APCA_PAPER_KEY_ID"]
            self.sec = os.environ["APCA_PAPER_SECRET"]
        self._h = {"APCA-API-KEY-ID": self.key,
                   "APCA-API-SECRET-KEY": self.sec}

    def account(self) -> dict:
        try:
            a = _http_json("GET", f"{self.base}/v2/account", self._h)
            cash = float(a.get("cash", 0))
            # as_of is the FETCH-NOW time, not Alpaca's `created_at`
            # (account-creation date). The /v2/account REST response
            # represents current state at server-time; the v3 freshness gate
            # (wake_now - 60s) requires a "now" timestamp to be meaningful.
            import datetime as _dt
            return {
                "status": a.get("status", "UNKNOWN"),
                "equity": float(a.get("equity", 0)),
                # B1: surface both 'cash' and 'settled_cash'. On a cash-by-rule
                # sub-$2000 Alpaca account they are the same; the spec carries
                # both fields explicitly.
                "cash": cash,
                "settled_cash": cash,
                "tracked_qty": {},  # populated by reconcile()
                "pdt_daytrade_count": int(a.get("daytrade_count", 0)),
                # prior_wake_orders is harness-side state; the live-runtime
                # version would also pull /v2/orders?status=closed. Empty here
                # is honest until that wiring lands.
                "prior_wake_orders": [],
                "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
        except urllib.error.HTTPError as e:
            return {"status": "AUTH_FAIL" if e.code in (401, 403) else "ERROR"}

    def reconcile(self) -> dict:
        # Pull positions; the harness uses tracked_qty to bound sells.
        # B1: also emit a positions[] list with symbol/tracked_qty/avg_entry,
        # which the perception schema's O_own_account.positions field expects.
        pos = _http_json("GET", f"{self.base}/v2/positions", self._h)
        tracked = {p["symbol"]: float(p["qty"]) for p in pos}
        positions = [
            {
                "symbol": p["symbol"],
                "tracked_qty": float(p["qty"]),
                "avg_entry": float(p.get("avg_entry_price", 0) or 0),
            } for p in pos
        ]
        return {"trade_date": "",
                "raw": {"account": {"tracked_qty": tracked,
                                     "positions": positions}}}

    def submit(self, order, coid: str) -> dict:
        body = {
            "symbol": order.symbol,
            "notional": f"{order.notional_usd:.2f}",
            "side": order.side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": coid,
        }
        try:
            r = _http_json("POST", f"{self.base}/v2/orders", self._h, body)
            return {"id": r.get("id"), "status": r.get("status"),
                    "filled_qty": r.get("filled_qty"),
                    "filled_avg_price": r.get("filled_avg_price")}
        except urllib.error.HTTPError as e:
            return {"error": e.code, "reason": e.read().decode("utf-8")[:200]}


class Clock:
    def __init__(self):
        mode = os.environ.get("KUWAI_MODE", "paper")
        base = ("https://api.alpaca.markets" if mode == "live"
                else "https://paper-api.alpaca.markets")
        self._h = {"APCA-API-KEY-ID": os.environ.get(
                       "APCA_LIVE_KEY_ID" if mode == "live"
                       else "APCA_PAPER_KEY_ID", ""),
                   "APCA-API-SECRET-KEY": os.environ.get(
                       "APCA_LIVE_SECRET" if mode == "live"
                       else "APCA_PAPER_SECRET", "")}
        self._url = f"{base}/v2/clock"

    def rth_open(self) -> bool:
        try:
            r = _http_json("GET", self._url, self._h)
            return bool(r.get("is_open", False))
        except Exception:
            return False


# ---- Anthropic -------------------------------------------------------------
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _anthropic_headers() -> dict:
    return {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": ANTHROPIC_VERSION,
    }


# Tool schemas matching commitment-v2/TOOLS.md
_TOOLS = [
    {
        "name": "propose_orders",
        "description": "Propose a list of orders this wake. Each order has a "
                       "symbol (must be in the sealed universe), a side "
                       "(buy or sell), and a size as notional USD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "orders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "side": {"type": "string",
                                      "enum": ["buy", "sell"]},
                            "notional_usd": {"type": "number"},
                        },
                        "required": ["symbol", "side", "notional_usd"],
                    },
                },
            },
            "required": ["orders"],
        },
    },
    {
        "name": "record_reasoning",
        "description": "Record this wake's first-person reasoning. Include "
                       "the dated payload items cited and the mandatory "
                       "critique field. This narration is logged verbatim "
                       "and never gates an order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "payload_refs": {"type": "array",
                                  "items": {"type": "string"}},
                "critique": {"type": "string"},
            },
            "required": ["text", "payload_refs", "critique"],
        },
    },
]


class AnthropicDecider:
    """The ONE per-wake model call. Returns reasoning_envelope and
    proposed_orders extracted from the model's tool calls."""

    def __init__(self):
        # v5 (2026-05-23): honour SEALED_TREE via _sealed_tree() helper.
        # MODEL.txt is byte-identical across v2..v5 so this is a
        # consistency/correctness fix, not a behaviour change. (Forward
        # ref OK: _sealed_tree is defined below; resolved at __init__
        # call-time, not import-time.)
        seal = _sealed_tree()
        lines = [l for l in (seal / "MODEL.txt").read_text("utf-8").splitlines()
                 if l.strip()]
        self.model = lines[0]
        # temperature/top_p/top_k deprecated for this model; native sampling

    # Multi-turn tool-use loop budget (Fix 5, architect-authorised
    # 2026-05-22 v3). claude-opus-4-7's response stop_reason="tool_use"
    # signals "I called a tool and am waiting for the tool_result before
    # continuing". A single round-trip leaves the model paused after one
    # tool call; propose_orders never lands. The fix is to implement the
    # documented Anthropic multi-turn protocol: round-trip synthetic
    # tool_results until stop_reason is end_turn / max_tokens /
    # stop_sequence, then return a consolidated envelope.
    MAX_TURN_BUDGET = 5

    def __call__(self, payload: dict, sealed_prompt: str) -> dict:
        # Anthropic deprecated temperature / top_p / top_k for claude-opus-4-7.
        # Adaptive thinking is automatic; do not pass thinking.type. The
        # agent runs at the model's native sampling (see MODEL.txt and the
        # seventh on-camera concession line). max_tokens=32768 per request.
        max_tokens = 32768
        messages = [{"role": "user",
                     "content": json.dumps(payload)[:60000]}]
        # Accumulators across turns
        all_text = ""
        all_reasoning = ""
        # ALL tool_use calls across all turns, in order
        all_tool_use_calls = []
        # Final values from the LAST occurrence of each tool across turns
        final_rr_text = None
        final_rr_payload_refs = None
        final_rr_critique = None
        final_orders: list = []
        rr_tool_called_anywhere = False
        propose_orders_called_anywhere = False
        per_turn_meta: list = []
        terminal_stop_reason = None
        last_response = None
        for turn_idx in range(self.MAX_TURN_BUDGET):
            body = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": sealed_prompt,
                "tools": _TOOLS,
                "messages": messages,
            }
            r = _http_json("POST", ANTHROPIC_URL, _anthropic_headers(),
                           body, timeout=420)
            last_response = r
            # per-turn meta + per-turn extraction
            block_type_counts: dict = {}
            tool_names_this_turn: list = []
            tool_use_blocks_this_turn = 0
            tool_uses_this_turn = []  # for building next turn's tool_result
            for blk in r.get("content", []):
                t = blk.get("type")
                block_type_counts[t] = block_type_counts.get(t, 0) + 1
                if t == "text":
                    all_text += blk.get("text", "")
                elif t == "thinking":
                    all_reasoning += blk.get("thinking", "")
                elif t == "tool_use":
                    tool_use_blocks_this_turn += 1
                    tool_name = blk.get("name")
                    tool_id = blk.get("id")
                    tool_input = blk.get("input", {}) or {}
                    tool_names_this_turn.append(tool_name)
                    all_tool_use_calls.append({
                        "turn": turn_idx,
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input,
                    })
                    tool_uses_this_turn.append(blk)
                    if tool_name == "record_reasoning":
                        rr_tool_called_anywhere = True
                        final_rr_text = tool_input.get("text", final_rr_text)
                        final_rr_payload_refs = tool_input.get(
                            "payload_refs", final_rr_payload_refs)
                        final_rr_critique = tool_input.get(
                            "critique", final_rr_critique)
                    elif tool_name == "propose_orders":
                        propose_orders_called_anywhere = True
                        final_orders = tool_input.get("orders", []) or []
            stop_reason = r.get("stop_reason")
            per_turn_meta.append({
                "turn": turn_idx,
                "stop_reason": stop_reason,
                "stop_sequence": r.get("stop_sequence"),
                "usage": r.get("usage") or {},
                "content_block_count": sum(block_type_counts.values()),
                "content_block_type_counts": block_type_counts,
                "tool_use_block_count": tool_use_blocks_this_turn,
                "tool_names_called": tool_names_this_turn,
            })
            if stop_reason in ("end_turn", "max_tokens", "stop_sequence",
                                "refusal"):
                terminal_stop_reason = stop_reason
                break
            if stop_reason != "tool_use":
                # Unknown stop_reason; raise loudly (do not paper over).
                raise RuntimeError(
                    f"AnthropicDecider unknown stop_reason on turn "
                    f"{turn_idx}: {stop_reason!r}; per_turn_meta="
                    f"{per_turn_meta!r}")
            # stop_reason == "tool_use": continue the conversation. Append
            # the assistant turn verbatim (preserve every block, including
            # any thinking-block signature passthrough Anthropic requires)
            # and a user turn carrying synthetic tool_result blocks. The
            # deploy-side wrapper does NOT execute the tool semantically;
            # tool_result content="ok" is an acknowledgement letting the
            # model continue. The sealed harness applies feasibility gate
            # + submit downstream after this entire exchange finishes.
            messages.append({"role": "assistant",
                             "content": r.get("content", [])})
            tool_results = [
                {"type": "tool_result",
                 "tool_use_id": blk.get("id"),
                 "content": "ok"}
                for blk in tool_uses_this_turn
            ]
            messages.append({"role": "user", "content": tool_results})
        else:
            # Loop exhausted without terminal stop_reason. Raise per the
            # architect's "turn budget exhausted -> raise, do not silently
            # truncate" rule.
            raise RuntimeError(
                f"AnthropicDecider turn budget {self.MAX_TURN_BUDGET} "
                f"exhausted without terminal stop_reason. "
                f"per_turn_meta={per_turn_meta!r}")

        # ---- Fail-loud guard on empty extraction (unchanged contract) ----
        has_text = bool(all_text) or bool(final_rr_text)
        has_reasoning = bool(all_reasoning)
        has_tools = bool(all_tool_use_calls)
        if not has_text and not has_reasoning and not has_tools:
            raise RuntimeError(
                "AnthropicDecider empty extraction across all turns: no "
                "text content, no thinking content, no tool calls. "
                f"per_turn_meta={per_turn_meta!r}")

        # ---- Consolidated api_response_meta ----
        # FINAL turn's stop_reason/usage are the load-bearing diagnostic;
        # per_turn_meta carries the full multi-turn trace.
        final_meta = per_turn_meta[-1] if per_turn_meta else {}
        api_response_meta = {
            "stop_reason": final_meta.get("stop_reason"),
            "stop_sequence": final_meta.get("stop_sequence"),
            "usage": final_meta.get("usage") or {},
            "content_block_count": final_meta.get("content_block_count", 0),
            "content_block_type_counts":
                final_meta.get("content_block_type_counts", {}),
            "tool_use_block_count":
                final_meta.get("tool_use_block_count", 0),
            "tool_names_called": final_meta.get("tool_names_called", []),
            "record_reasoning_called": rr_tool_called_anywhere,
            "propose_orders_called": propose_orders_called_anywhere,
            "max_tokens_requested": max_tokens,
            # Multi-turn diagnostic block:
            "total_turns": len(per_turn_meta),
            "turn_budget": self.MAX_TURN_BUDGET,
            "per_turn_meta": per_turn_meta,
            "tool_calls_history": all_tool_use_calls,
            "terminal_stop_reason": terminal_stop_reason,
        }

        # ---- Sealed-harness-compatible envelope (no sealed change) ----
        # text   -> prefer record_reasoning tool input (model's chosen
        #           narrative) over streamed text; sealed grounding_linter
        #           ignores this field, the linter only inspects
        #           payload_refs; ledger logs it verbatim for audit.
        # reasoning -> concatenated "thinking" blocks (if any).
        # payload_refs -> the grounding linter's load-bearing input;
        #                 final record_reasoning tool input wins.
        # critique -> final record_reasoning tool input.
        # api_response_meta -> diagnostic; additive, sealed code ignores.
        envelope = {
            "text": final_rr_text if final_rr_text is not None else all_text,
            "reasoning": all_reasoning,
            "payload_refs": final_rr_payload_refs or [],
            "critique": final_rr_critique or "",
            "api_response_meta": api_response_meta,
        }
        return {"reasoning_envelope": envelope,
                "proposed_orders": final_orders}


class AnthropicSynth:
    """The council SYNTHESISER call. Returns raw council-v1 JSON string.
    Contract is a STRING return (the sealed council parses it); the
    api_response_meta therefore cannot live in the return value without
    breaking the contract. It is attached to self.last_attempt_metas[]
    and surfaced via stderr (journal-captured on the live VPS), so the
    smoke + live operator can read the diagnostic alongside the sealed
    COUNCIL ledger entry. The live ledger COUNCIL entry body is built
    by sealed code from `cres` and cannot carry synth meta without a
    sealed change."""

    def __init__(self):
        # v5 Call-4 fix (2026-05-23): honour SEALED_TREE env so the synth
        # reads the CURRENT sealed prompt (v5) instead of hardcoding v2.
        # Previously the v2/v3/v4 prompts were byte-identical so this
        # silently worked; for the v5 SYNTHESISER_PROMPT.md amendment to
        # actually land at runtime, the synth must read from the current
        # sealed tree. Uses the same _sealed_tree() helper that the
        # perception adapters use.
        seal = _sealed_tree()
        # MODEL.txt is byte-identical across v2..v5, but read from the
        # current sealed tree for consistency.
        lines = [l for l in (seal / "MODEL.txt").read_text("utf-8").splitlines()
                 if l.strip()]
        self.model = lines[0]
        # temperature/top_p/top_k deprecated for this model; native sampling
        self.synth_prompt = (seal / "COUNCIL" /
                              "SYNTHESISER_PROMPT.md").read_text("utf-8")
        # Fix 6 (architect-authorised 2026-05-22 v4): per-attempt meta
        # accumulator. Council retries the synth up to once on schema
        # garble; both attempts' meta land here for diagnostic visibility.
        self.last_attempt_metas: list = []
        self.last_api_meta: dict | None = None

    def __call__(self, attempt: int = 1, **_) -> str:
        # Fix 6: max_tokens 1024 -> 32768. claude-opus-4-7's adaptive
        # thinking consumes small budgets on internal thinking before
        # the parseable council-v1 JSON text block lands; the previous
        # 1024 cap produced empty/garbled responses on both attempts and
        # tripped the sealed council's R-1 bind to terminal HALT. Sealed
        # tree unaffected.
        max_tokens = 32768
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": self.synth_prompt,
            "messages": [
                {"role": "user", "content": "emit council-v1 report only"},
            ],
        }
        r = _http_json("POST", ANTHROPIC_URL, _anthropic_headers(), body,
                       timeout=420)
        # Accumulate per-block text + per-type counts for the meta. The
        # synth has no tools so we only expect text (and possibly thinking).
        text_acc = ""
        reasoning_acc = ""
        block_type_counts: dict = {}
        for blk in r.get("content", []):
            t = blk.get("type")
            block_type_counts[t] = block_type_counts.get(t, 0) + 1
            if t == "text":
                text_acc += blk.get("text", "")
            elif t == "thinking":
                reasoning_acc += blk.get("thinking", "")
        api_response_meta = {
            "attempt": attempt,
            "stop_reason": r.get("stop_reason"),
            "stop_sequence": r.get("stop_sequence"),
            "usage": r.get("usage") or {},
            "content_block_count": sum(block_type_counts.values()),
            "content_block_type_counts": block_type_counts,
            "max_tokens_requested": max_tokens,
            "text_length": len(text_acc),
            "reasoning_length": len(reasoning_acc),
            "contains_dimensions_substring": ("dimensions" in text_acc),
        }
        self.last_attempt_metas.append(api_response_meta)
        self.last_api_meta = api_response_meta
        # Surface to stderr so the live VPS journal captures it next to
        # the COUNCIL ledger entry; the smoke reads self.last_attempt_metas
        # directly.
        sys.stderr.write(
            f"[synth attempt={attempt}] stop={api_response_meta['stop_reason']!r} "
            f"text_len={api_response_meta['text_length']} "
            f"reason_len={api_response_meta['reasoning_length']} "
            f"types={block_type_counts} "
            f"usage={api_response_meta['usage']}\n")
        # v5 refinement (architect-authorised 2026-05-23): fail-loud
        # raises ONLY on truly empty text (zero content blocks). Any
        # non-empty text -- even if malformed or missing the "dimensions"
        # wrapper -- is returned NORMALLY so the sealed council.py
        # _parse_and_guard runs its own SchemaStructuralError detection
        # and the council's intended R-1 retry-then-HALT discipline
        # fires (C-COUNCIL-SCHEMA-GUARD Fixture B). The previous
        # dimensions-substring raise (v3 Fix 6) bypassed that sealed
        # behaviour and caused the v4 live wake to commit
        # council_failsafe_halt with retries_consumed=0 instead of
        # exercising the R-1 path. Sealed council remains the
        # authority for shape validation.
        if not text_acc:
            raise RuntimeError(
                "AnthropicSynth empty text response: no text content "
                "block in API response. "
                f"stop_reason={r.get('stop_reason')!r}; "
                f"usage={r.get('usage')!r}; "
                f"content_block_types={block_type_counts!r}; "
                f"attempt={attempt}")
        return text_acc


# ============================================================================
# v3 PERCEPTION ADAPTERS (deploy-side, unsealed). These are the seven
# fetchers commitment-v3/code/agent_loop.py consumes via deps. Each is a
# callable that returns {"value": <rows>, "as_of": <iso>, "status": "OK"} on
# success or None on failure (agent_loop sentinels UNAVAILABLE).
#
# Sealed-tree reads come from $SEALED_TREE if set (staging), else
# /opt/kuwai/commitment-v3 (production). The sealed tree is NEVER written.
# ============================================================================
from datetime import datetime, timedelta, timezone


def _sealed_tree() -> Path:
    # v5 (2026-05-23): default-fallback bumped v3 -> v5 (the current
    # sealed deploy path). The SEALED_TREE env var remains the
    # authoritative selector; fallback only matters when the env is
    # unset, e.g. during local smoke runs from the build repo.
    p = os.environ.get("SEALED_TREE")
    if p and Path(p).is_dir():
        return Path(p)
    pp = Path("/opt/kuwai/commitment-v5")
    if pp.is_dir():
        return pp
    # last-resort: caller's relative
    return (Path(__file__).resolve().parent.parent / "commitment-v5")


def _read_universe() -> list[str]:
    out = []
    for ln in (_sealed_tree() / "UNIVERSE.txt").read_text("utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _read_scrape_channels() -> dict:
    """Return {actor_x_named, actor_reddit_named, x_handles[], subreddits[]}
    from the sealed RESEARCH/SCRAPE_CHANNELS.txt. Sealed membership; never
    edited at this layer."""
    out = {"actor_x_named": "", "actor_reddit_named": "",
           "x_handles": [], "subreddits": []}
    text = (_sealed_tree() / "RESEARCH" /
            "SCRAPE_CHANNELS.txt").read_text("utf-8")
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            k, _, v = s.partition("=")
            k = k.strip(); v = v.split("#", 1)[0].strip()
            if k == "actor_x_named":
                out["actor_x_named"] = v
            elif k == "actor_reddit_named":
                out["actor_reddit_named"] = v
            continue
        if s.startswith("x_account:"):
            handle = s.split(":", 1)[1].strip().lstrip("@")
            if handle:
                out["x_handles"].append(handle)
        elif s.startswith("reddit_sub:"):
            sub = s.split(":", 1)[1].strip().lstrip("r/").lstrip("/")
            if sub:
                out["subreddits"].append(sub)
    return out


def _alpaca_data_headers() -> dict:
    """The market-data endpoints accept the same APCA-API headers as the
    trading endpoints. Use live keys when KUWAI_MODE=live, else paper."""
    mode = os.environ.get("KUWAI_MODE", "paper")
    if mode == "live":
        kid = os.environ.get("APCA_LIVE_KEY_ID", "")
        sec = os.environ.get("APCA_LIVE_SECRET", "")
    else:
        kid = os.environ.get("APCA_PAPER_KEY_ID", "")
        sec = os.environ.get("APCA_PAPER_SECRET", "")
    return {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------------
# A_market_bars: Alpaca Market Data v2 OHLCV bars, IEX feed (free tier),
# 1-minute bars within the sealed RECENCY window (intraday <=35 min).
# ----------------------------------------------------------------------------
class AlpacaMarketDataBars:
    """1-min IEX bars within RTH (RECENCY <=35min); falls back to last
    completed daily session bars when off-hours produce no intraday rows
    (RECENCY: market_bars_daily = prior completed US session)."""
    BASE = "https://data.alpaca.markets"

    def __init__(self, page_symbols: int = 30):
        self.h = _alpaca_data_headers()
        self.page_symbols = page_symbols

    def _fetch(self, universe, *, timeframe: str, start, end, limit: int):
        # RFC3339 with Z suffix: avoids the '+00:00 -> space' URL-decode trap
        # that Alpaca rejects as a malformed timestamp.
        def _iso(t):
            return t.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z")
        rows = []
        last_err = None
        for i in range(0, len(universe), self.page_symbols):
            chunk = universe[i:i + self.page_symbols]
            url = (f"{self.BASE}/v2/stocks/bars?symbols={','.join(chunk)}"
                   f"&timeframe={timeframe}&start={_iso(start)}"
                   f"&end={_iso(end)}&feed=iex&limit={limit}")
            try:
                r = _http_json("GET", url, self.h, timeout=30)
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.reason}"
                sys.stderr.write(f"[bars {timeframe}] {last_err}\n")
                continue
            except Exception as e:
                last_err = repr(e)
                sys.stderr.write(f"[bars {timeframe}] {last_err}\n")
                continue
            bars = r.get("bars", {}) or {}
            for sym, bs in bars.items():
                if not bs:
                    continue
                last = bs[-1]
                rows.append({
                    "symbol": sym, "timeframe": timeframe,
                    "t": last.get("t"),
                    "o": last.get("o"), "h": last.get("h"),
                    "l": last.get("l"), "c": last.get("c"),
                    "v": last.get("v"),
                })
        if not rows and last_err:
            sys.stderr.write(f"[bars {timeframe}] all pages empty; last err: {last_err}\n")
        return rows

    def __call__(self):
        universe = _read_universe()
        if not universe:
            return None
        end = datetime.now(timezone.utc).replace(microsecond=0)
        # 1) intraday 1-min within last hour
        rows = self._fetch(universe, timeframe="1Min",
                           start=end - timedelta(minutes=60),
                           end=end, limit=600)
        if rows:
            return {"value": rows, "as_of": end.isoformat(), "status": "OK"}
        # 2) fallback: prior completed US session, daily bars
        d_end = end
        d_start = end - timedelta(days=7)  # safe lookback
        rows = self._fetch(universe, timeframe="1Day",
                           start=d_start, end=d_end, limit=10)
        if rows:
            return {"value": rows, "as_of": end.isoformat(),
                    "status": "OK"}
        return None


# ----------------------------------------------------------------------------
# C_news_catalyst: Alpaca News v1beta1 over the sealed universe, sealed
# RECENCY window (<=36h lookback; items dated >36h dropped).
# ----------------------------------------------------------------------------
class AlpacaNews:
    BASE = "https://data.alpaca.markets"

    def __init__(self, max_per_call: int = 50, page_symbols: int = 50):
        self.h = _alpaca_data_headers()
        self.max_per_call = max_per_call
        self.page_symbols = page_symbols

    def __call__(self):
        universe = _read_universe()
        if not universe:
            return None
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=36)  # sealed news_catalyst window
        def _iso(t):
            return t.astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z")
        rows = []
        for i in range(0, len(universe), self.page_symbols):
            chunk = universe[i:i + self.page_symbols]
            url = (f"{self.BASE}/v1beta1/news?symbols={','.join(chunk)}"
                   f"&start={_iso(start)}&end={_iso(end)}"
                   f"&limit={self.max_per_call}&sort=desc")
            try:
                r = _http_json("GET", url, self.h, timeout=30)
            except urllib.error.HTTPError:
                continue
            for n in (r.get("news") or []):
                # 36h cutoff (drop anything older)
                created = n.get("created_at")
                rows.append({
                    "id": n.get("id"),
                    "symbols": n.get("symbols", []),
                    "headline": n.get("headline"),
                    "source": n.get("source"),
                    "url": n.get("url"),
                    "summary": (n.get("summary") or "")[:300],
                    "created_at": created,
                    "updated_at": n.get("updated_at"),
                })
        return {"value": rows, "as_of": end.isoformat(), "status": "OK"}


# ----------------------------------------------------------------------------
# E_edgar_primary: SEC EDGAR submissions API. Free, no auth; mandatory
# User-Agent header. Ticker -> CIK via SEC's public company_tickers.json
# (live SEC reference data; not a sealed map). Most recent primary filing
# per symbol (sealed RECENCY: no recency cap, primary record is the trust
# root regardless of age).
# ----------------------------------------------------------------------------
class SecEdgar:
    UA = ("KUWAI-commitment-v3 research-agent "
          "(contact: maran@solstudiosdigital.com)")
    TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(self, page_symbols: int = 25):
        self.h = {"User-Agent": self.UA, "Accept": "application/json"}
        self.page_symbols = page_symbols
        self._tic_to_cik = None

    def _load_ticker_map(self):
        if self._tic_to_cik is not None:
            return self._tic_to_cik
        try:
            tm = _http_json("GET", self.TICKER_MAP_URL, self.h, timeout=30)
        except urllib.error.HTTPError:
            self._tic_to_cik = {}
            return self._tic_to_cik
        out = {}
        # SEC returns {"0":{"cik_str":...,"ticker":...,"title":...}, ...}
        for v in tm.values():
            t = (v.get("ticker") or "").upper()
            cik = v.get("cik_str")
            if t and cik is not None:
                out[t] = str(cik).zfill(10)
        self._tic_to_cik = out
        return out

    def __call__(self):
        universe = _read_universe()
        if not universe:
            return None
        tmap = self._load_ticker_map()
        rows = []
        # sample first N tickers (paginate full universe later in prod)
        for sym in universe[:self.page_symbols]:
            cik = tmap.get(sym.upper())
            if not cik:
                continue
            try:
                sub = _http_json("GET",
                    self.SUBMISSIONS_URL.format(cik=cik), self.h, timeout=30)
            except urllib.error.HTTPError:
                continue
            recent = (sub.get("filings") or {}).get("recent") or {}
            forms = recent.get("form") or []
            dates = recent.get("filingDate") or []
            accns = recent.get("accessionNumber") or []
            primaryDocs = recent.get("primaryDocument") or []
            # most-recent primary: 10-K, 10-Q, 8-K, 20-F take priority
            PRIORITY = ("10-K", "10-Q", "8-K", "20-F", "6-K")
            best_idx = None
            for i, frm in enumerate(forms):
                if frm in PRIORITY:
                    best_idx = i
                    break
            if best_idx is None and forms:
                best_idx = 0
            if best_idx is None:
                continue
            rows.append({
                "symbol": sym,
                "cik": cik,
                "form": forms[best_idx] if best_idx < len(forms) else None,
                "filingDate": dates[best_idx] if best_idx < len(dates) else None,
                "accessionNumber": accns[best_idx] if best_idx < len(accns) else None,
                "primaryDocument": primaryDocs[best_idx] if best_idx < len(primaryDocs) else None,
            })
        if not rows:
            return None
        return {"value": rows, "as_of": _now_iso(), "status": "OK"}


# ----------------------------------------------------------------------------
# C2_corporate_actions: Alpaca corporate actions v1. Currently declared
# /effective only per sealed RECENCY.
# ----------------------------------------------------------------------------
class AlpacaCorporateActions:
    BASE = "https://data.alpaca.markets"

    def __init__(self):
        self.h = _alpaca_data_headers()
        self.last_err = None

    def __call__(self):
        # Alpaca corporate actions data API: /v1/corporate-actions with
        # symbols (required for the public data plan), start/end dates,
        # and an explicit types filter. Surface the server's error in
        # last_err for the audit when the call fails (rather than silent).
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=30)
        # representative subset of UNIVERSE; the symbols= param is required
        universe = _read_universe()
        symbols = ",".join(universe[:50]) if universe else ""
        # Alpaca's valid corporate-action types (server-enumerated):
        # forward_split, reverse_split, stock_dividend, spin_off,
        # cash_merger, stock_merger, stock_and_cash_merger, unit_split,
        # cash_dividend, redemption, name_change, worthless_removal,
        # rights_distribution, contract_adjustment, partial_call,
        # reorganization
        valid_types = ",".join((
            "forward_split", "reverse_split", "stock_dividend",
            "cash_dividend", "name_change", "worthless_removal",
            "stock_merger", "cash_merger", "stock_and_cash_merger",
            "spin_off", "unit_split", "redemption",
            "rights_distribution", "contract_adjustment",
            "partial_call", "reorganization",
        ))
        url = (f"{self.BASE}/v1/corporate-actions"
               f"?symbols={symbols}"
               f"&start={start.isoformat()}&end={end.isoformat()}"
               f"&types={valid_types}"
               f"&limit=1000")
        try:
            r = _http_json("GET", url, self.h, timeout=30)
        except urllib.error.HTTPError as e:
            self.last_err = f"HTTP {e.code}: {e.reason}"
            sys.stderr.write(f"[corp_actions] {self.last_err}\n")
            return None
        except Exception as e:
            self.last_err = repr(e)
            sys.stderr.write(f"[corp_actions] {self.last_err}\n")
            return None
        ca = r.get("corporate_actions") or {}
        rows = []
        for kind, items in ca.items():
            for it in items:
                rows.append({"type": kind, **it})
        return {"value": rows, "as_of": _now_iso(), "status": "OK"}


# ----------------------------------------------------------------------------
# M_own_history: live Alpaca closed orders + walk the local sealed-ledger.
# ----------------------------------------------------------------------------
class OwnHistory:
    LEDGER_PATH_ENV = "KUWAI_LEDGER"

    def __init__(self):
        self.broker = AlpacaBroker()  # reuse base + headers

    def __call__(self):
        rows = []
        # 1) Alpaca closed orders (paper or live by mode)
        try:
            orders = _http_json(
                "GET",
                f"{self.broker.base}/v2/orders?status=closed&limit=100&direction=desc",
                self.broker._h, timeout=30)
        except urllib.error.HTTPError:
            orders = []
        for o in (orders or []):
            rows.append({
                "src": "alpaca_orders",
                "id": o.get("id"),
                "client_order_id": o.get("client_order_id"),
                "symbol": o.get("symbol"),
                "side": o.get("side"),
                "qty": o.get("filled_qty") or o.get("qty"),
                "filled_avg_price": o.get("filled_avg_price"),
                "status": o.get("status"),
                "submitted_at": o.get("submitted_at"),
                "filled_at": o.get("filled_at"),
            })
        # 2) walk the sealed ledger for past wakes' decisions
        lp = os.environ.get(self.LEDGER_PATH_ENV) or "/var/lib/kuwai/ledger.log"
        try:
            for ln in open(lp, "r", encoding="utf-8"):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get("kind") in ("ORDER_SUBMIT", "HOLD", "HALT",
                                      "COUNCIL", "GROUNDING", "HEARTBEAT"):
                    rows.append({
                        "src": "ledger",
                        "kind": o.get("kind"),
                        "ts_utc": o.get("ts_utc"),
                        "entry_hash": o.get("entry_hash"),
                        "body": o.get("body"),
                    })
        except FileNotFoundError:
            pass
        return {"value": rows, "as_of": _now_iso(), "status": "OK"}


# ----------------------------------------------------------------------------
# N_social (Block N): Apify pinned actors over the sealed channel list.
# X handles via apidojo/tweet-scraper@<sealed build>, subreddits via
# trudax/reddit-scraper-lite@<sealed build>. Channels-only input (no
# searchTerms ever, per SCRAPE_CHANNELS.txt). Sealed 24h lookback, per-
# entity cap 50.
# ----------------------------------------------------------------------------
APIFY_BASE = "https://api.apify.com/v2"


def _apify_run_sync(actor_name: str, build_hash: str, run_input: dict,
                    token: str, timeout: int = 420) -> list:
    """POST run-sync-get-dataset-items; returns the run's dataset rows.
    Raises urllib.error.HTTPError unchanged so callers can surface the
    server's error payload (e.g. 'build-not-found') rather than swallow."""
    actor_id = actor_name.replace("/", "~")
    url = (f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
           f"?token={token}&build={build_hash}")
    data = json.dumps(run_input).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise urllib.error.HTTPError(
            e.url, e.code, f"{e.reason} :: {body[:400]}", e.headers, None)


class BlockNApify:
    PER_ENTITY_MAX = 50              # sealed cap
    LOOKBACK_H = 24                  # sealed window

    def __init__(self):
        self.token = os.environ.get("APIFY_TOKEN", "")
        ch = _read_scrape_channels()
        self.actor_x = ch["actor_x_named"]            # name@build
        self.actor_reddit = ch["actor_reddit_named"]  # name@build
        self.x_handles = ch["x_handles"]
        self.subreddits = ch["subreddits"]

    def _split(self, pinned: str) -> tuple[str, str]:
        if "@" in pinned:
            name, _, build = pinned.partition("@")
            return name, build
        return pinned, ""

    def _resolve_latest_succeeded_build(self, actor_name: str) -> str:
        """v5 (2026-05-23): when the sealed actor identity is unpinned
        (no @<build> suffix), resolve the latest SUCCEEDED build at
        runtime by querying the Apify builds API. Returns the
        buildNumber (e.g. "0.0.1381") on success, raises on failure.
        Honest failure surface -- no stubbing.

        Apify API path uses tilde for the user/actor separator:
          GET https://api.apify.com/v2/acts/{user}~{actor}/builds
              ?token=...&desc=true&limit=20
        """
        # name is "user/actor"; Apify API endpoint is "user~actor"
        if "/" in actor_name:
            api_name = actor_name.replace("/", "~", 1)
        else:
            api_name = actor_name
        url = (f"https://api.apify.com/v2/acts/{api_name}/builds"
               f"?token={self.token}&desc=true&limit=20")
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(
                f"runtime X build resolution failed for {actor_name!r}: "
                f"Apify builds API unreachable: {e!r}")
        items = (payload.get("data") or {}).get("items") or []
        for b in items:
            if b.get("status") == "SUCCEEDED":
                bn = b.get("buildNumber")
                if isinstance(bn, str) and bn:
                    return bn
        raise RuntimeError(
            f"runtime X build resolution found no SUCCEEDED build for "
            f"{actor_name!r} in last {len(items)} builds")

    def __call__(self):
        if not self.token:
            # honest: no token, cannot scrape
            return None
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=self.LOOKBACK_H)
        rows = []
        dropped = 0
        truncated = False

        # ---- X (Twitter) ----
        # v5 (2026-05-23): if the sealed actor identity is unpinned
        # (no @<build> suffix), resolve the latest-SUCCEEDED build at
        # runtime and log the resolved build into the audit dict, so
        # every wake records WHICH build it ran against. Sealed value
        # WITH a @<build> suffix is still honoured as-is (backwards-
        # compat for prior versions). Honest failure surface: a
        # resolution failure surfaces via x_err / x_resolution_error in
        # the audit dict; never stubbed.
        x_err = None
        x_resolution_error = None
        x_resolved_build = None
        if self.actor_x and self.x_handles:
            name, sealed_build = self._split(self.actor_x)
            if sealed_build:
                # backwards-compat: pinned build, use as-is
                build = sealed_build
            else:
                # unpinned actor identity: resolve at runtime
                try:
                    build = self._resolve_latest_succeeded_build(name)
                    x_resolved_build = build
                    sys.stderr.write(
                        f"[block_n X] runtime-resolved build: "
                        f"{name}@{build}\n")
                except Exception as e:
                    x_resolution_error = repr(e)
                    x_err = f"runtime build resolution failed: {e!r}"
                    sys.stderr.write(f"[block_n X] {x_err}\n")
                    build = ""
            x_input = {
                "twitterHandles": self.x_handles,
                "maxItems": self.PER_ENTITY_MAX * len(self.x_handles),
                "sort": "Latest",
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
            tweets = []
            if build:
                try:
                    tweets = _apify_run_sync(name, build, x_input,
                                              self.token)
                except urllib.error.HTTPError as e:
                    x_err = f"HTTP {e.code}: {e.reason}"
                    sys.stderr.write(f"[block_n X] {x_err}\n")
                except Exception as e:
                    x_err = repr(e)
                    sys.stderr.write(f"[block_n X] {x_err}\n")
            # apply 24h recency-only visible truncation per channel
            per_entity = {}
            for t in tweets:
                handle = (t.get("author", {}) or {}).get("userName") or \
                         t.get("user_name") or t.get("username") or ""
                handle = str(handle).lstrip("@")
                created = t.get("createdAt") or t.get("created_at") or ""
                # recency window cut (defensive: actor already filtered)
                try:
                    cdt = datetime.fromisoformat(
                        str(created).replace("Z", "+00:00"))
                    if cdt < start:
                        dropped += 1
                        continue
                except Exception:
                    pass
                if per_entity.get(handle, 0) >= self.PER_ENTITY_MAX:
                    dropped += 1
                    truncated = True
                    continue
                per_entity[handle] = per_entity.get(handle, 0) + 1
                rows.append({
                    "src": "x",
                    "actor": self.actor_x,
                    "handle": handle,
                    "id": t.get("id") or t.get("tweetId"),
                    "url": t.get("url"),
                    "text": (t.get("text") or t.get("fullText") or "")[:280],
                    "created_at": created,
                })

        # ---- Reddit ----
        # v5 (2026-05-23): per-subreddit calls run CONCURRENTLY via a
        # ThreadPoolExecutor instead of the previous sequential loop. The
        # Apify run-sync-get-dataset-items endpoint has a server-side 300s
        # per-run timeout; sequential 4-sub fetches hit ~360-510s wall in
        # v3/v4 smokes (~94% of total wake budget). Parallel target <150s.
        # Per-sub error surfacing preserved (each sub's transient 4xx is
        # recorded in r_errs_per_sub independently; one sub failing does
        # NOT fail the others). futures.as_completed orders by completion.
        import concurrent.futures as _futures
        r_err = None
        r_errs_per_sub = {}
        posts = []
        if self.actor_reddit and self.subreddits:
            name, build = self._split(self.actor_reddit)

            def _fetch_one_sub(sub):
                r_input = {
                    "startUrls": [
                        {"url": f"https://www.reddit.com/r/{sub}/new"}],
                    "maxItems": self.PER_ENTITY_MAX,
                    "maxPostCount": self.PER_ENTITY_MAX,
                    "skipComments": True,
                    "sort": "new",
                    "time": "day",
                    "ignoreStartUrls": False,
                    "proxy": {"useApifyProxy": True,
                               "apifyProxyGroups": ["RESIDENTIAL"]},
                }
                return _apify_run_sync(name, build, r_input, self.token)

            # max_workers = len(subreddits): one thread per sub, all run
            # concurrently. Each Apify run-sync call is bounded server-side
            # at ~300s; the wall-clock for the whole arm now ≈ slowest sub.
            with _futures.ThreadPoolExecutor(
                    max_workers=max(1, len(self.subreddits))) as ex:
                fut_to_sub = {ex.submit(_fetch_one_sub, sub): sub
                              for sub in self.subreddits}
                for fut in _futures.as_completed(fut_to_sub):
                    sub = fut_to_sub[fut]
                    try:
                        posts.extend(fut.result())
                    except urllib.error.HTTPError as e:
                        msg = f"HTTP {e.code}: {e.reason}"
                        r_errs_per_sub[sub] = msg
                        sys.stderr.write(
                            f"[block_n reddit r/{sub}] {msg}\n")
                    except Exception as e:
                        r_errs_per_sub[sub] = repr(e)
                        sys.stderr.write(
                            f"[block_n reddit r/{sub}] "
                            f"{r_errs_per_sub[sub]}\n")
            if r_errs_per_sub:
                r_err = r_errs_per_sub
            per_sub = {}
            for p in posts:
                sub = (p.get("communityName") or p.get("subreddit") or
                       p.get("community") or "").lstrip("r/").lstrip("/")
                created = p.get("createdAt") or p.get("created_at") or ""
                try:
                    cdt = datetime.fromisoformat(
                        str(created).replace("Z", "+00:00"))
                    if cdt < start:
                        dropped += 1
                        continue
                except Exception:
                    pass
                if per_sub.get(sub, 0) >= self.PER_ENTITY_MAX:
                    dropped += 1
                    truncated = True
                    continue
                per_sub[sub] = per_sub.get(sub, 0) + 1
                rows.append({
                    "src": "reddit",
                    "actor": self.actor_reddit,
                    "subreddit": sub,
                    "id": p.get("id"),
                    "url": p.get("url"),
                    "title": (p.get("title") or "")[:280],
                    "score": p.get("score") or p.get("upVotes"),
                    "created_at": created,
                })

        return {
            "value": rows,
            "as_of": end.isoformat(),
            "status": "OK",
            "audit": {
                "x_handles": self.x_handles,
                "subreddits": self.subreddits,
                "actor_x": self.actor_x,
                "actor_reddit": self.actor_reddit,
                "lookback_hours": self.LOOKBACK_H,
                "per_entity_max": self.PER_ENTITY_MAX,
                "dropped_count": dropped,
                "truncated": truncated,
                "x_error": x_err,
                # v5 (2026-05-23): per-wake audit of which X build the
                # adapter ran against. None when actor_x is pinned
                # (backwards-compat) or when runtime resolution failed.
                "x_resolved_build": x_resolved_build,
                "x_resolution_error": x_resolution_error,
                "reddit_error": r_err,
            },
        }


# ----------------------------------------------------------------------------
# FGHIJKL_derived: deterministic transforms over R1 inputs only. Honest
# classification per architect's plain-English review:
#   F macro_regime:        case (b) - deploy-codable. Per REGIME_RULE.txt:
#                          IVV trend_label (SMA50/SMA200) + vol_label
#                          (realised_vol_20d vs 1y median). All inputs are
#                          IVV daily bars from Alpaca; sealed rule lives in
#                          RESEARCH/REGIME_RULE.txt (already in the tree).
#                          Implemented below.
#   G sector_cross:        case (a) - sealed frozen symbol->GICS-sector map
#                          is NOT a member of commitment-v3. Honest
#                          UNAVAILABLE; architect review required before
#                          adding a sealed file to the tree.
#   H index_constituent:   case (a) - sealed frozen index->constituent map
#                          is NOT a member of commitment-v3. Same as G.
#   I regime_classification: case (b) - same REGIME_RULE.txt transform as F
#                          (PERCEPTION_SCHEMA.md names them as a pair).
#                          Implemented below as a shared output.
#   J volatility:          case (b) - deploy-codable. Realised_vol_20d per
#                          symbol from a 25-trading-day window of daily
#                          bars. The previous STALE was a smoke-wake
#                          constraint (only fetched 1Min); now fetched
#                          explicitly. Implemented below.
#   K liquidity:           case (b) - deploy-codable. Median traded notional
#                          per bar over the sealed window. Implemented
#                          below over the available bars from
#                          A_market_bars (intraday RTH; daily off-hours).
#                          A multi-bar window when RTH is open.
#   L calendar:            case (b) PARTIAL - upcoming corp_actions (ex-
#                          dates, splits, payable-dates from Block C2)
#                          surfaced as the calendar. Earnings-dates would
#                          need a separate live source (Alpaca does not
#                          provide it on the free tier); architect
#                          decision needed on whether to add a sealed
#                          earnings-source designator.
# ----------------------------------------------------------------------------
import math as _math


class DerivedTransforms:
    BASE = "https://data.alpaca.markets"
    REGIME_IVV_BARS = 260       # ~1 trading year for SMA200 + 1y median vol
    VOL_WINDOW_DAYS = 25        # 20 daily returns + buffer
    PAGE_SYMBOLS = 30

    def __init__(self):
        self.h = _alpaca_data_headers()

    @staticmethod
    def _iso(t):
        return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _fetch_daily_bars(self, symbols, limit):
        """Return {symbol: [bars sorted ascending by t]} for the given
        symbols. Paginates the universe to keep URLs bounded."""
        out = {}
        end = datetime.now(timezone.utc).replace(microsecond=0)
        # extend start enough to cover `limit` trading days + weekends
        start = end - timedelta(days=int(limit * 1.6) + 5)
        for i in range(0, len(symbols), self.PAGE_SYMBOLS):
            chunk = symbols[i:i + self.PAGE_SYMBOLS]
            url = (f"{self.BASE}/v2/stocks/bars?symbols={','.join(chunk)}"
                   f"&timeframe=1Day&start={self._iso(start)}"
                   f"&end={self._iso(end)}&feed=iex&limit={limit}")
            try:
                r = _http_json("GET", url, self.h, timeout=30)
            except urllib.error.HTTPError as e:
                sys.stderr.write(f"[derived 1Day] HTTP {e.code}: {e.reason}\n")
                continue
            except Exception as e:
                sys.stderr.write(f"[derived 1Day] {e!r}\n")
                continue
            bars = r.get("bars", {}) or {}
            for sym, bs in bars.items():
                if not bs:
                    continue
                out[sym] = sorted(bs, key=lambda b: b.get("t") or "")
        return out

    def _compute_regime(self, ivv_bars):
        """REGIME_RULE.txt deterministic label. IVV daily bars only.
        trend_label from SMA50/SMA200; vol_label from realised_vol_20d vs
        its 1y rolling median. Realised-only (no implied)."""
        closes = [b.get("c") for b in ivv_bars if b.get("c") is not None]
        n = len(closes)
        if n < 200:
            return {"status": "UNAVAILABLE",
                    "reason": f"need >=200 IVV daily closes for SMA200, got {n}"}
        last = closes[-1]
        sma50 = sum(closes[-50:]) / 50
        sma200 = sum(closes[-200:]) / 200
        if last > sma50 and sma50 > sma200:
            trend = "up"
        elif last < sma50 and sma50 < sma200:
            trend = "down"
        else:
            trend = "mixed"
        # daily log returns
        rets = [_math.log(closes[i + 1] / closes[i])
                for i in range(n - 1) if closes[i] > 0]
        if len(rets) < 20:
            return {"status": "OK", "trend_label": trend,
                    "vol_label": "unavailable",
                    "reason_vol": f"need >=20 returns, got {len(rets)}"}
        # latest 20d realised vol, annualised
        last_20 = rets[-20:]
        m20 = sum(last_20) / len(last_20)
        v20 = sum((r - m20) ** 2 for r in last_20) / (len(last_20) - 1)
        vol_20 = _math.sqrt(v20) * _math.sqrt(252)
        # 1y rolling-20d vol median
        rolling = []
        for endp in range(20, len(rets) + 1):
            window = rets[endp - 20:endp]
            mm = sum(window) / 20
            vv = sum((r - mm) ** 2 for r in window) / (20 - 1)
            rolling.append(_math.sqrt(vv) * _math.sqrt(252))
        rolling.sort()
        median_1y = rolling[len(rolling) // 2] if rolling else None
        if median_1y is None:
            vol_label = "unavailable"
        else:
            vol_label = "calm" if vol_20 < median_1y else "elevated"
        return {
            "status": "OK",
            "trend_label": trend,
            "vol_label": vol_label,
            "ivv_last_close": round(last, 2),
            "ivv_sma50": round(sma50, 2),
            "ivv_sma200": round(sma200, 2),
            "realised_vol_20d_annualised": round(vol_20, 4),
            "realised_vol_20d_median_1y": (round(median_1y, 4)
                                            if median_1y else None),
            "n_ivv_bars_used": n,
        }

    @staticmethod
    def _vol_per_symbol(bars_by_sym):
        rows = []
        for sym, bars in bars_by_sym.items():
            closes = [b.get("c") for b in bars if b.get("c") is not None]
            if len(closes) < 21:
                continue
            rets = [_math.log(closes[i + 1] / closes[i])
                    for i in range(len(closes) - 1) if closes[i] > 0]
            window = rets[-20:]
            if len(window) < 20:
                continue
            m = sum(window) / len(window)
            v = sum((r - m) ** 2 for r in window) / (len(window) - 1)
            vol = _math.sqrt(v) * _math.sqrt(252)
            rows.append({
                "symbol": sym,
                "realised_vol_20d_annualised": round(vol, 4),
                "n_bars_used": len(closes),
                "sample_size": len(window),
            })
        return rows

    @staticmethod
    def _liquidity_from_bars(bars_list):
        """Median traded notional per bar over the available window per
        symbol. Falls back to single-bar notional if only one bar is
        available (smoke / post-close)."""
        per_sym = {}
        for b in bars_list:
            s = b.get("symbol"); c = b.get("c"); v = b.get("v")
            if s is None or c is None or v is None:
                continue
            per_sym.setdefault(s, []).append(float(c) * float(v))
        rows = []
        for sym, notionals in per_sym.items():
            notionals.sort()
            n = len(notionals)
            median = (notionals[n // 2] if n % 2 == 1
                      else (notionals[n // 2 - 1] + notionals[n // 2]) / 2)
            rows.append({
                "symbol": sym,
                "notional_usd_median": round(median, 2),
                "n_bars_in_window": n,
                "single_bar_only": (n == 1),
            })
        return rows

    @staticmethod
    def _calendar_from_corp_actions(c2_block):
        """L_calendar partial: upcoming corp-actions (future ex_date or
        payable_date). Earnings-dates need a separate source."""
        if not isinstance(c2_block, dict) or c2_block.get("status") != "OK":
            return None
        today = datetime.now(timezone.utc).date()
        rows = []
        for it in (c2_block.get("value") or []):
            for key in ("ex_date", "payable_date", "effective_date",
                         "record_date"):
                v = it.get(key)
                if not v:
                    continue
                try:
                    d = datetime.fromisoformat(str(v)[:10]).date()
                except Exception:
                    continue
                if d >= today:
                    rows.append({
                        "type": it.get("type"),
                        "symbol": it.get("symbol"),
                        "event": key,
                        "date": str(v)[:10],
                        "rate": it.get("rate"),
                    })
                    break  # one row per item (the soonest future date)
        rows.sort(key=lambda r: r["date"])
        return rows

    def __call__(self, payload: dict):
        blocks = (payload or {}).get("blocks", {}) or {}
        # --- F + I: REGIME_RULE label (IVV daily bars only) -------------
        ivv_map = self._fetch_daily_bars(["IVV"], limit=self.REGIME_IVV_BARS)
        regime = self._compute_regime(ivv_map.get("IVV", []))
        # --- J: per-symbol realised_vol_20d (25-day daily window) -------
        universe = _read_universe()
        bars_by_sym = self._fetch_daily_bars(universe,
                                              limit=self.VOL_WINDOW_DAYS)
        J_rows = self._vol_per_symbol(bars_by_sym)
        # --- K: median notional per bar over the available bars -------
        bars_block = blocks.get("A_market_bars") or {}
        K_rows = (self._liquidity_from_bars(bars_block.get("value") or [])
                  if bars_block.get("status") == "OK" else [])
        # --- L: upcoming corp_actions as calendar approximation -------
        L_rows = self._calendar_from_corp_actions(
            blocks.get("C2_corporate_actions")) or []

        F_out = (regime if regime.get("status") == "OK"
                 else regime)
        I_out = (regime if regime.get("status") == "OK"
                 else regime)
        return {
            "value": {
                "F_macro_regime": F_out,
                "G_sector_cross": {
                    "status": "UNAVAILABLE",
                    "reason": ("case (a): frozen symbol->GICS-sector map "
                               "is not a sealed member of commitment-v3; "
                               "architect review required before adding")},
                "H_index_constituent": {
                    "status": "UNAVAILABLE",
                    "reason": ("case (a): frozen index->constituent map "
                               "is not a sealed member of commitment-v3; "
                               "architect review required before adding")},
                "I_regime_classification": I_out,
                "J_volatility": ({"status": "OK", "rows": J_rows}
                                  if J_rows else
                                  {"status": "UNAVAILABLE",
                                   "reason": "no symbol had >=21 daily closes in window"}),
                "K_liquidity": ({"status": "OK", "rows": K_rows}
                                 if K_rows else
                                 {"status": "UNAVAILABLE",
                                  "reason": "A_market_bars produced no usable rows"}),
                "L_calendar": ({"status": "OK_PARTIAL",
                                 "rows": L_rows,
                                 "note": ("partial: upcoming corp_actions "
                                          "ex/payable dates only. Earnings "
                                          "dates need a separate sealed "
                                          "source; architect decision "
                                          "pending.")}
                                if L_rows else
                                {"status": "UNAVAILABLE",
                                 "reason": ("corp_actions had no future-dated "
                                            "items in window")}),
            },
            "as_of": _now_iso(),
            "status": ("OK" if (regime.get("status") == "OK" and J_rows
                                  and K_rows)
                       else "PARTIAL"),
        }
