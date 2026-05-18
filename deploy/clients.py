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
import urllib.request
import urllib.error
import ssl
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
            return {
                "status": a.get("status", "UNKNOWN"),
                "equity": float(a.get("equity", 0)),
                "settled_cash": float(a.get("cash", 0)),
                "tracked_qty": {},  # populated by reconcile()
                "pdt_daytrade_count": int(a.get("daytrade_count", 0)),
                "as_of": a.get("created_at"),
            }
        except urllib.error.HTTPError as e:
            return {"status": "AUTH_FAIL" if e.code in (401, 403) else "ERROR"}

    def reconcile(self) -> dict:
        # Pull positions; the harness uses tracked_qty to bound sells.
        pos = _http_json("GET", f"{self.base}/v2/positions", self._h)
        tracked = {p["symbol"]: float(p["qty"]) for p in pos}
        return {"trade_date": "", "raw": {"account": {"tracked_qty": tracked}}}

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
        model_file = (Path(__file__).resolve().parent.parent /
                      "commitment-v2" / "MODEL.txt")
        # also handle the deployed path
        if not model_file.is_file():
            model_file = Path("/opt/kuwai/commitment-v2/MODEL.txt")
        lines = [l for l in model_file.read_text("utf-8").splitlines()
                 if l.strip()]
        self.model = lines[0]
        # temperature/top_p/top_k deprecated for this model; native sampling

    def __call__(self, payload: dict, sealed_prompt: str) -> dict:
        # Anthropic deprecated temperature / top_p / top_k for claude-opus-4-7.
        # Adaptive thinking is automatic; do not pass thinking.type. The
        # agent runs at the model's native sampling (see MODEL.txt and the
        # seventh on-camera concession line).
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": sealed_prompt,
            "tools": _TOOLS,
            "messages": [
                {"role": "user", "content": json.dumps(payload)[:60000]},
            ],
        }
        r = _http_json("POST", ANTHROPIC_URL, _anthropic_headers(), body,
                       timeout=120)
        envelope = {"text": "", "payload_refs": [], "critique": ""}
        orders = []
        for blk in r.get("content", []):
            t = blk.get("type")
            if t == "text":
                envelope["text"] += blk.get("text", "")
            elif t == "tool_use":
                if blk.get("name") == "record_reasoning":
                    i = blk.get("input", {})
                    envelope["text"] = i.get("text", envelope["text"])
                    envelope["payload_refs"] = i.get("payload_refs", [])
                    envelope["critique"] = i.get("critique", "")
                elif blk.get("name") == "propose_orders":
                    orders = blk.get("input", {}).get("orders", []) or []
        return {"reasoning_envelope": envelope, "proposed_orders": orders}


class AnthropicSynth:
    """The council SYNTHESISER call. Returns raw council-v1 JSON string."""

    def __init__(self):
        model_file = Path("/opt/kuwai/commitment-v2/MODEL.txt")
        if not model_file.is_file():
            model_file = (Path(__file__).resolve().parent.parent /
                           "commitment-v2" / "MODEL.txt")
        lines = [l for l in model_file.read_text("utf-8").splitlines()
                 if l.strip()]
        self.model = lines[0]
        # temperature/top_p/top_k deprecated for this model; native sampling
        seal = Path("/opt/kuwai/commitment-v2")
        if not seal.is_dir():
            seal = (Path(__file__).resolve().parent.parent / "commitment-v2")
        self.synth_prompt = (seal / "COUNCIL" / "SYNTHESISER_PROMPT.md"
                              ).read_text("utf-8")

    def __call__(self, attempt: int = 1, **_) -> str:
        # No temperature / top_p / top_k on claude-opus-4-7 (Anthropic
        # deprecated). The synthesiser runs at the model's native sampling.
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": self.synth_prompt,
            "messages": [
                {"role": "user", "content": "emit council-v1 report only"},
            ],
        }
        r = _http_json("POST", ANTHROPIC_URL, _anthropic_headers(), body,
                       timeout=60)
        for blk in r.get("content", []):
            if blk.get("type") == "text":
                return blk.get("text", "")
        return ""
