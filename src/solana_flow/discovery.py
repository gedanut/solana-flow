"""Bounded wallet and current-token-account history capture."""

import json
from datetime import UTC, datetime

from .ledger import analyze, integer, require
from .rpc import MAX_CAPTURE_BYTES, _analysis_transaction, fetch, valid_signature, validate_address

TOKEN_PROGRAMS = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
)
DISCOVERY = "wallet-and-current-token-accounts"
SCOPE_WARNING = (
    "Current token accounts only: closed or transferred accounts and prior ownership history "
    "may be missing; this is not complete wallet history."
)


def capture(
    wallet, client, *, limit=100, cluster="custom", include_tokens=False, max_token_accounts=50
):
    """Capture schema-v1 balance evidence using read-only RPC methods.

    Token mode searches the wallet and bounded currently owned token accounts,
    not historical ownership. Its scope warning keeps overall partial=True to
    match ledger warning semantics, even after clean provider-page exhaustion.
    See docs/discovery.md for traversal bounds and per-source coverage fields.
    """
    require(type(include_tokens) is bool, "Invalid include_tokens flag.")
    if not include_tokens:
        return fetch(wallet, client, limit=limit, cluster=cluster)
    validate_address(wallet)
    integer(limit, "limit", 1)
    require(limit <= 10000, "Limit must be between 1 and 10000.")
    require(cluster in ("mainnet-beta", "devnet", "testnet", "custom"), "Invalid cluster.")
    integer(max_token_accounts, "maximum token accounts", 1)
    require(max_token_accounts <= 1000, "Maximum token accounts must be between 1 and 1000.")
    accounts = set()
    discovery_incomplete = False
    discovery_bounded = False
    for program in TOKEN_PROGRAMS:
        try:
            response = client.call(
                "getTokenAccountsByOwner",
                [
                    wallet,
                    {"programId": program},
                    {"encoding": "jsonParsed", "commitment": "finalized"},
                ],
            )
            require(isinstance(response, dict), "Invalid discovery response.")
            records = response["value"]
            require(isinstance(records, list), "Invalid discovery account list.")
        except (ValueError, KeyError, TypeError):
            discovery_incomplete = True
            continue
        if len(records) > max_token_accounts + 1:
            discovery_bounded = True
        for record in records[: max_token_accounts + 1]:
            try:
                address = record["pubkey"]
                validate_address(address)
                require(address != wallet, "Invalid token account address.")
                account = record["account"]
                require(account["owner"] == program, "Unexpected token program.")
                parsed = account["data"]["parsed"]
                require(parsed["type"] == "account", "Expected a parsed token account.")
                info = parsed["info"]
                require(isinstance(info, dict), "Invalid token account info.")
                require("owner" not in info or info["owner"] == wallet, "Unexpected token owner.")
                accounts.add(address)
            except (ValueError, KeyError, TypeError):
                discovery_incomplete = True
    if len(accounts) > max_token_accounts:
        discovery_bounded = True

    accounts = sorted(accounts)[:max_token_accounts]
    sources = [
        {
            "address": address,
            "pages": 0,
            "cap_reached": False,
            "reached_history": False,
            "partial": False,
        }
        for address in [wallet] + accounts
    ]
    coverage = {
        "limit": limit,
        "pages": 0,
        "cap_reached": False,
        "reached_history": False,
        "partial": True,
        "discovery": DISCOVERY,
        "token_accounts": accounts,
        "sources": sources,
    }
    snapshot = {
        "schema_version": 1,
        "wallet": wallet,
        "cluster": cluster,
        "synthetic": False,
        "captured_at": datetime.now(UTC).isoformat(),
        "coverage": coverage,
        "transactions": [],
        "unavailable_signatures": [],
        "warnings": [SCOPE_WARNING],
    }
    if discovery_incomplete:
        snapshot["warnings"].append(
            "Token account discovery failed or returned invalid data; some accounts may be missing."
        )
    if discovery_bounded:
        snapshot["warnings"].append(
            "Token account discovery bound reached; some current accounts were not inspected."
        )
    cursors = {}
    source_seen = {s["address"]: set() for s in sources}
    seen = set()
    mint_decimals = {}
    captured_bytes = 0
    size_stopped = False
    while len(seen) < limit and any(not s["reached_history"] and not s["partial"] for s in sources):
        for source in sources:
            if source["reached_history"] or source["partial"]:
                continue
            address = source["address"]
            options = {"limit": 1, "commitment": "finalized"}
            if address in cursors:
                options["before"] = cursors[address]
            try:
                page = client.call("getSignaturesForAddress", [address, options])
                source["pages"] += 1
                coverage["pages"] += 1
                require(isinstance(page, list) and len(page) <= 1, "Invalid signature page.")
                require(
                    all(isinstance(r, dict) and valid_signature(r.get("signature")) for r in page),
                    "Invalid signature record.",
                )
            except (ValueError, KeyError, TypeError):
                source["partial"] = True
                snapshot["warnings"].append(
                    "Signature discovery failed or returned an invalid page; source stopped."
                )
                continue
            if not page:
                source["reached_history"] = True
                continue
            signature = page[0]["signature"]
            if signature in source_seen[address]:
                source["partial"] = True
                snapshot["warnings"].append(
                    "Signature pagination stalled for a source; source stopped."
                )
                continue
            source_seen[address].add(signature)
            cursors[address] = signature
            if signature in seen:
                continue
            seen.add(signature)
            try:
                result = client.call(
                    "getTransaction",
                    [
                        signature,
                        {
                            "encoding": "jsonParsed",
                            "commitment": "finalized",
                            "maxSupportedTransactionVersion": 0,
                        },
                    ],
                )
                require(
                    isinstance(result, dict)
                    and result["transaction"]["signatures"][0] == signature,
                    "Transaction signature mismatch or unavailable result.",
                )
                size = len(json.dumps(result, ensure_ascii=True, allow_nan=False)) + 2
                if captured_bytes + size > MAX_CAPTURE_BYTES:
                    size_stopped = True
                    snapshot["warnings"].append("Capture size budget reached; all sources stopped.")
                    raise ValueError("Capture size budget reached.")
                analyze(dict(snapshot, transactions=[result]))
                meta = result.get("meta") or {}
                current_decimals = {
                    r["mint"]: r["uiTokenAmount"]["decimals"]
                    for side in ("preTokenBalances", "postTokenBalances")
                    for r in (meta.get(side) or [])
                }
                require(
                    all(
                        m not in mint_decimals or mint_decimals[m] == d
                        for m, d in current_decimals.items()
                    ),
                    "Conflicting mint decimals.",
                )
                snapshot["transactions"].append(_analysis_transaction(result))
                mint_decimals.update(current_decimals)
                captured_bytes += size
            except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
                snapshot["unavailable_signatures"].append(signature)
            if len(seen) == limit:
                coverage["cap_reached"] = True
                for remaining in sources:
                    remaining["cap_reached"] = (
                        not remaining["reached_history"] and not remaining["partial"]
                    )
                break
            if size_stopped:
                break
        if size_stopped:
            for remaining in sources:
                if not remaining["reached_history"]:
                    remaining["partial"] = True
            break
    coverage["reached_history"] = (
        not discovery_incomplete
        and not discovery_bounded
        and all(s["reached_history"] for s in sources)
    )
    if snapshot["unavailable_signatures"]:
        snapshot["warnings"].append("Some transactions were null, pruned, invalid or unavailable.")
    return snapshot
