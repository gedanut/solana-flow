"""Bounded, read-only Solana JSON-RPC transport and snapshot capture."""

import json
import math
import re
import time
from datetime import UTC, datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .jsonio import loads as strict_loads
from .ledger import ValidationError, analyze, integer, require

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MAX_RESPONSE = 16 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
DISCOVERY = "wallet-account-keys-only"


class RPCError(ValueError):
    """Safe diagnostic: never includes the endpoint or server-controlled text."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RPCError("RPC redirect refused.")


# No redirect can forward credentials to a different destination.
urlopen = build_opener(_NoRedirect).open


def validate_address(address):
    require(
        isinstance(address, str)
        and 32 <= len(address) <= 44
        and all(c in ALPHABET for c in address),
        "Address must be a base58 public key.",
    )
    number = 0
    for char in address:
        number = number * 58 + ALPHABET.index(char)
    size = (number.bit_length() + 7) // 8 + len(address) - len(address.lstrip("1"))
    require(size == 32, "Address must decode to 32 bytes.")


def valid_signature(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,88}", value)


class RPCClient:
    def __init__(self, url, *, timeout=20, retries=3):
        try:
            require(
                isinstance(url, str) and all(33 <= ord(char) <= 126 for char in url),
                "Invalid RPC URL; percent-encode whitespace and non-ASCII characters.",
            )
            parts = urlsplit(url)
            require(
                parts.scheme in ("http", "https") and parts.hostname and not parts.fragment,
                "RPC URL must be HTTP(S) without a fragment.",
            )
            _ = parts.port
        except (TypeError, ValueError):
            raise ValidationError("Invalid RPC URL.") from None
        require(type(timeout) in (int, float) and 0 < timeout <= 120, "Invalid RPC timeout.")
        require(type(retries) is int and 0 <= retries <= 5, "Invalid retry count.")
        self._url, self.timeout, self.retries = url, timeout, retries

    def call(self, method, params):
        require(
            method in ("getSignaturesForAddress", "getTransaction"),
            "Only read-only history methods are supported.",
        )
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "solana-flow/1.0"},
        )
        for attempt in range(self.retries + 1):
            delay = min(0.5 * 2**attempt, 8)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise RPCError("RPC response exceeds size limit.")
                try:
                    payload = strict_loads(raw)
                except (ValueError, UnicodeError, RecursionError):
                    raise RPCError("Invalid JSON-RPC response.") from None
                if (
                    not isinstance(payload, dict)
                    or payload.get("jsonrpc") != "2.0"
                    or type(payload.get("id")) is not int
                    or payload["id"] != 1
                ):
                    raise RPCError("Invalid JSON-RPC response envelope.")
                if "error" in payload:
                    error = payload["error"]
                    code = error.get("code") if isinstance(error, dict) else None
                    if code not in (429, -32005, -32004, -32603):
                        raise RPCError("RPC request rejected by server.")
                    if attempt == self.retries:
                        raise RPCError("RPC temporarily unavailable after bounded retries.")
                elif "result" in payload:
                    return payload["result"]
                else:
                    raise RPCError("JSON-RPC result missing.")
            except HTTPError as exc:
                exc.close()
                if exc.code not in (408, 429, 500, 502, 503, 504):
                    raise RPCError("RPC HTTP request rejected.") from None
                try:
                    retry_after = float(exc.headers.get("Retry-After", delay))
                    if math.isfinite(retry_after):
                        delay = min(max(retry_after, 0), 8)
                except (TypeError, ValueError, AttributeError):
                    pass
                if attempt == self.retries:
                    raise RPCError("RPC HTTP failure after bounded retries.") from None
            except (URLError, OSError, HTTPException, ValueError) as exc:
                if isinstance(exc, RPCError):
                    raise
                if attempt == self.retries:
                    raise RPCError("RPC transport unavailable after bounded retries.") from None
            if attempt < self.retries:
                time.sleep(delay)
        raise RPCError("RPC retries exhausted.")  # Defensive, all terminal paths above raise.


def _analysis_transaction(result):
    """Keep only validated balance evidence; discard logs and provider extensions."""
    transaction = result["transaction"]
    keys = transaction.get("message", {}).get("accountKeys", [])
    normalized = {
        "slot": result["slot"],
        "blockTime": result["blockTime"],
        "transaction": {
            "signatures": [transaction["signatures"][0]],
            "message": {
                "accountKeys": [
                    {"pubkey": key["pubkey"]} if isinstance(key, dict) else key for key in keys
                ]
            },
        },
        "meta": None,
    }
    version = result.get("version")
    if type(version) is int or version == "legacy":
        normalized["version"] = version
    meta = result["meta"]
    if meta is not None:
        normalized["meta"] = {
            "err": None if meta["err"] is None else {"failed": True},
            "fee": meta["fee"],
            "preBalances": list(meta["preBalances"]),
            "postBalances": list(meta["postBalances"]),
        }
        for side in ("preTokenBalances", "postTokenBalances"):
            records = meta.get(side)
            normalized["meta"][side] = (
                None
                if records is None
                else [
                    {
                        "accountIndex": record["accountIndex"],
                        "mint": record["mint"],
                        "uiTokenAmount": {
                            "amount": record["uiTokenAmount"]["amount"],
                            "decimals": record["uiTokenAmount"]["decimals"],
                        },
                        **({"owner": record["owner"]} if "owner" in record else {}),
                    }
                    for record in records
                ]
            )
        if "loadedAddresses" in meta:
            loaded = meta["loadedAddresses"]
            normalized["meta"]["loadedAddresses"] = (
                None
                if loaded is None
                else {side: list(loaded[side]) for side in ("writable", "readonly")}
            )
    return normalized


def fetch(wallet: str, client: RPCClient, *, limit=100, cluster="custom") -> dict:
    """Capture at most limit unique address-referencing signatures.

    Returns partial snapshots on transport/data failures. Check coverage.partial;
    reached_history means an empty provider page, never complete wallet history.
    """
    validate_address(wallet)
    integer(limit, "limit", 1)
    require(limit <= 10000, "Limit must be between 1 and 10000.")
    require(cluster in ("mainnet-beta", "devnet", "testnet", "custom"), "Invalid cluster.")
    snapshot = {
        "schema_version": 1,
        "wallet": wallet,
        "cluster": cluster,
        "synthetic": False,
        "captured_at": datetime.now(UTC).isoformat(),
        "coverage": {
            "limit": limit,
            "pages": 0,
            "cap_reached": False,
            "reached_history": False,
            "partial": False,
            "discovery": DISCOVERY,
        },
        "transactions": [],
        "unavailable_signatures": [],
        "warnings": [],
    }
    coverage = snapshot["coverage"]
    seen, cursors = set(), set()
    mint_decimals = {}
    captured_bytes = 0
    size_stopped = False
    cursor = None
    while len(seen) < limit:
        options = {"limit": min(1000, limit - len(seen)), "commitment": "finalized"}
        if cursor:
            options["before"] = cursor
        try:
            page = client.call("getSignaturesForAddress", [wallet, options])
        except RPCError:
            snapshot["warnings"].append("Signature discovery interrupted by RPC failure.")
            coverage["partial"] = True
            break
        coverage["pages"] += 1
        if not isinstance(page, list) or any(
            not isinstance(r, dict) or not valid_signature(r.get("signature")) for r in page
        ):
            snapshot["warnings"].append("Invalid signature page returned by RPC.")
            coverage["partial"] = True
            break
        if not page:
            coverage["reached_history"] = True
            break
        new = 0
        for record in page:
            signature = record["signature"]
            if signature in seen:
                continue
            seen.add(signature)
            new += 1
            try:
                result = client.call(
                    "getTransaction",
                    [
                        signature,
                        {
                            "encoding": "jsonParsed",
                            "maxSupportedTransactionVersion": 0,
                            "commitment": "finalized",
                        },
                    ],
                )
                if result is None:
                    raise RPCError("Transaction unavailable.")
                if (
                    not isinstance(result, dict)
                    or result.get("transaction", {}).get("signatures", [None])[0] != signature
                ):
                    raise RPCError("Transaction signature mismatch.")
                size = len(json.dumps(result, ensure_ascii=True, allow_nan=False)) + 2
                if captured_bytes + size > MAX_CAPTURE_BYTES:
                    size_stopped = True
                    snapshot["warnings"].append(
                        "Capture size budget reached; discovery stopped early."
                    )
                    raise RPCError("Capture size budget reached.")
                candidate = dict(snapshot, transactions=[result])
                checked = analyze(candidate)
                # Validate each result once, then enforce snapshot-wide mint consistency.
                meta = result.get("meta") or {}
                current_decimals = {
                    record["mint"]: record["uiTokenAmount"]["decimals"]
                    for side in ("preTokenBalances", "postTokenBalances")
                    for record in (meta.get(side) or [])
                }
                require(
                    all(
                        mint not in mint_decimals or mint_decimals[mint] == decimals
                        for mint, decimals in current_decimals.items()
                    ),
                    "Conflicting decimals for a mint.",
                )
                mint_decimals.update(current_decimals)
                if checked["gaps"]:
                    coverage["partial"] = True
                snapshot["transactions"].append(_analysis_transaction(result))
                captured_bytes += size
            except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
                snapshot["unavailable_signatures"].append(signature)
                coverage["partial"] = True
            if len(seen) == limit:
                coverage["cap_reached"] = True
                break
            if size_stopped:
                break
        if size_stopped:
            break
        next_cursor = page[-1]["signature"]
        if not coverage["cap_reached"] and (new == 0 or next_cursor in cursors):
            coverage["partial"] = True
            snapshot["warnings"].append("Signature pagination stalled; capture stopped.")
            break
        cursors.add(next_cursor)
        cursor = next_cursor
    if snapshot["unavailable_signatures"]:
        snapshot["warnings"].append("Some transactions were null, pruned, invalid or unavailable.")
    return snapshot
