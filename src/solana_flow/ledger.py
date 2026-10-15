"""Exact net balance attribution. No instruction or payment classification."""

import json
import re
from datetime import datetime


class ValidationError(ValueError):
    """A snapshot cannot be safely interpreted."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"Invalid {label}.")
    return value


def string(value, label):
    require(isinstance(value, str) and 0 < len(value) <= 256, f"Invalid {label}.")
    require(not any(ord(c) < 32 for c in value), f"Invalid {label}.")
    return value


def decimal_amount(amount: int, decimals: int) -> str:
    """Format using integers only, independent of the Decimal context."""
    integer(decimals, "decimals")
    require(decimals <= 255, "Invalid decimals.")
    sign = "-" if amount < 0 else ""
    digits = str(abs(amount)).zfill(decimals + 1)
    return sign + (digits[:-decimals] + "." + digits[-decimals:] if decimals else digits)


def _keys(transaction, meta):
    keys = transaction["message"]["accountKeys"]
    require(isinstance(keys, list) and keys, "Missing account keys.")
    parsed = all(isinstance(k, dict) for k in keys)
    require(parsed or all(isinstance(k, str) for k in keys), "Mixed account key format.")
    result = [string(k["pubkey"] if parsed else k, "account key") for k in keys]
    loaded = meta.get("loadedAddresses")
    if loaded is not None:
        require(isinstance(loaded, dict), "Invalid loaded addresses.")
        for side in ("writable", "readonly"):
            require(isinstance(loaded.get(side), list), "Invalid loaded addresses.")
            values = [string(k, "loaded address") for k in loaded[side]]
            if not parsed:
                result.extend(values)
    require(len(result) == len(set(result)), "Duplicate account keys.")
    return result


def _tokens(records, key_count, mint_decimals):
    require(isinstance(records, list), "Invalid token balance array.")
    result = {}
    for r in records:
        require(isinstance(r, dict), "Invalid token record.")
        index = integer(r["accountIndex"], "token account index")
        require(index < key_count and index not in result, "Invalid or duplicate token index.")
        mint = string(r["mint"], "mint")
        ui = r["uiTokenAmount"]
        amount = ui["amount"]
        require(
            isinstance(amount, str) and re.fullmatch(r"[0-9]{1,100}", amount),
            "Token amounts must be unsigned integer strings (maximum 100 digits).",
        )
        decimals = integer(ui["decimals"], "token decimals")
        require(decimals <= 255, "Invalid token decimals.")
        require(
            mint not in mint_decimals or mint_decimals[mint] == decimals,
            "Conflicting decimals for a mint.",
        )
        mint_decimals[mint] = decimals
        owner = r.get("owner")
        if owner is not None:
            string(owner, "token owner")
        result[index] = (mint, int(amount), owner)
    return result


def _analyze(snapshot):
    require(isinstance(snapshot, dict), "Snapshot must be an object.")
    require(
        type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 1,
        "Unsupported snapshot schema version.",
    )
    wallet = string(snapshot["wallet"], "wallet")
    cluster = snapshot["cluster"]
    require(
        cluster in ("mainnet-beta", "devnet", "testnet", "custom", "synthetic"), "Invalid cluster."
    )
    require(type(snapshot["synthetic"]) is bool, "Invalid synthetic flag.")
    require((cluster == "synthetic") == snapshot["synthetic"], "Conflicting synthetic label.")
    captured = string(snapshot["captured_at"], "capture time")
    require(
        datetime.fromisoformat(captured).tzinfo is not None, "Capture time must include timezone."
    )
    coverage = snapshot["coverage"]
    require(isinstance(coverage, dict), "Missing coverage.")
    integer(coverage["limit"], "capture limit", 1)
    integer(coverage["pages"], "page count")
    for flag in ("cap_reached", "reached_history", "partial"):
        require(type(coverage[flag]) is bool, "Invalid coverage flag.")
    require(
        coverage["discovery"] in ("wallet-account-keys-only", "wallet-and-current-token-accounts"),
        "Invalid discovery scope.",
    )
    if coverage["discovery"] == "wallet-and-current-token-accounts":
        # Local import avoids a module cycle: RPC reuses the ledger's validation helpers.
        from .rpc import validate_address

        validate_address(wallet)
        accounts = coverage["token_accounts"]
        sources = coverage["sources"]
        require(isinstance(accounts, list) and len(accounts) <= 1000, "Invalid token accounts.")
        for address in accounts:
            validate_address(address)
        require(
            len(accounts) == len(set(accounts)) and wallet not in accounts,
            "Duplicate discovery addresses.",
        )
        require(
            isinstance(sources, list) and len(sources) == len(accounts) + 1,
            "Invalid discovery sources.",
        )
        fields = {"address", "pages", "cap_reached", "reached_history", "partial"}
        for source, address in zip(sources, [wallet] + accounts, strict=True):
            require(isinstance(source, dict) and set(source) == fields, "Invalid discovery source.")
            require(source["address"] == address, "Unexpected discovery source address.")
            integer(source["pages"], "source page count")
            for flag in ("cap_reached", "reached_history", "partial"):
                require(type(source[flag]) is bool, "Invalid source coverage flag.")
            require(
                not source["cap_reached"]
                or (coverage["cap_reached"] and not source["reached_history"]),
                "Conflicting source coverage boundaries.",
            )
        require(
            coverage["pages"] == sum(s["pages"] for s in sources),
            "Source page counts do not match total.",
        )
        require(
            not coverage["reached_history"] or all(s["reached_history"] for s in sources),
            "Source history boundaries do not match total.",
        )
    require(
        not (coverage["cap_reached"] and coverage["reached_history"]),
        "Conflicting coverage boundaries.",
    )
    transactions = snapshot["transactions"]
    unavailable = snapshot["unavailable_signatures"]
    warnings = snapshot["warnings"]
    require(
        isinstance(transactions, list)
        and isinstance(unavailable, list)
        and isinstance(warnings, list),
        "Invalid snapshot lists.",
    )
    for item in unavailable + warnings:
        string(item, "warning or unavailable signature")
    require(len(unavailable) == len(set(unavailable)), "Duplicate unavailable signatures.")
    rows, gaps, seen, mint_decimals = [], [], {}, {}
    fees = failed = 0
    for tx in transactions:
        require(isinstance(tx, dict), "Invalid transaction result.")
        transaction = tx["transaction"]
        signatures = transaction["signatures"]
        require(isinstance(signatures, list) and signatures, "Missing transaction signatures.")
        signature = string(signatures[0], "signature")
        canonical = json.dumps(tx, sort_keys=True, allow_nan=False)
        if signature in seen:
            require(seen[signature] == canonical, "Conflicting duplicate transaction signature.")
            continue
        require(signature not in unavailable, "Available signature also marked unavailable.")
        seen[signature] = canonical
        slot = integer(tx["slot"], "slot")
        block_time = tx["blockTime"]
        if block_time is not None:
            integer(block_time, "block time")
        meta = tx["meta"]
        if meta is None:
            # A missing balance record is a gap, not permission for malformed
            # transaction evidence to bypass the normalization prerequisites.
            _keys(transaction, {})
            gaps.append({"signature": signature, "asset": "all", "reason": "Missing metadata"})
            continue
        require(isinstance(meta, dict), "Invalid transaction metadata.")
        require("err" in meta, "Missing transaction status.")
        status = "failed" if meta["err"] is not None else "success"
        failed += status == "failed"
        fee = integer(meta["fee"], "fee")
        keys = _keys(transaction, meta)
        pre, post = meta["preBalances"], meta["postBalances"]
        for balances in (pre, post):
            require(
                isinstance(balances, list) and len(balances) == len(keys),
                "Native balance arrays must match resolved keys.",
            )
            for value in balances:
                integer(value, "native balance")
        fee_paid = fee if keys[0] == wallet else 0
        fees += fee_paid

        def row(
            asset,
            mint,
            amount,
            decimals,
            *,
            signature=signature,
            slot=slot,
            block_time=block_time,
            status=status,
            fee_paid=fee_paid,
        ):
            rows.append(
                {
                    "signature": signature,
                    "slot": slot,
                    "time": block_time,
                    "status": status,
                    "asset": asset,
                    "mint": mint,
                    "amount_base_units": str(amount),
                    "decimals": decimals,
                    "decimal_amount": decimal_amount(amount, decimals),
                    "direction": "in" if amount > 0 else "out" if amount < 0 else "zero",
                    "wallet_paid_fee_base_units": str(fee_paid) if asset == "SOL" else "",
                    "synthetic": snapshot["synthetic"],
                }
            )

        if wallet in keys:
            i = keys.index(wallet)
            row("SOL", None, post[i] - pre[i], 9)
        token_sides = [meta.get("preTokenBalances"), meta.get("postTokenBalances")]
        if any(side is None for side in token_sides):
            # Validate any supplied side even when the other side is missing.
            for side in token_sides:
                if side is not None:
                    _tokens(side, len(keys), mint_decimals)
            gaps.append(
                {"signature": signature, "asset": "SPL", "reason": "Missing token balance metadata"}
            )
            continue
        before, after = [_tokens(side, len(keys), mint_decimals) for side in token_sides]
        totals, uncertain = {}, set()
        for i in sorted(before.keys() | after.keys()):
            a, b = before.get(i), after.get(i)
            require(
                not (a and b and a[0] != b[0]), "Token account mint changes within transaction."
            )
            for record, sign in ((a, -1), (b, 1)):
                if record is None:
                    continue  # Absent side in a supplied array: newly created or closed account.
                mint, amount, owner = record
                if owner is None:
                    uncertain.add(mint)
                elif owner == wallet:
                    totals[mint] = totals.get(mint, 0) + sign * amount
        for mint in sorted(uncertain):
            gaps.append(
                {
                    "signature": signature,
                    "asset": mint,
                    "reason": "Unknown token owner; mint movement omitted",
                }
            )
        for mint, amount in sorted(totals.items()):
            if mint not in uncertain:
                row("SPL", mint, amount, mint_decimals[mint])
    require(len(seen) + len(unavailable) <= coverage["limit"], "Capture exceeds declared limit.")
    effective_coverage = dict(coverage)
    effective_coverage["partial"] = bool(coverage["partial"] or unavailable or gaps or warnings)
    totals = {}
    for r in rows:
        key = "SOL" if r["asset"] == "SOL" else "SPL:" + r["mint"]
        total = totals.setdefault(
            key,
            {
                "asset": r["asset"],
                "mint": r["mint"],
                "decimals": r["decimals"],
                "inflow": 0,
                "outflow": 0,
                "net": 0,
            },
        )
        value = int(r["amount_base_units"])
        total["net"] += value
        total["inflow"] += max(0, value)
        total["outflow"] += max(0, -value)
    for total in totals.values():
        for field in ("inflow", "outflow", "net"):
            value = total[field]
            total[field + "_base_units"] = str(value)
            total[field] = decimal_amount(value, total["decimals"])
    return {
        "schema_version": 1,
        "wallet": wallet,
        "cluster": cluster,
        "synthetic": snapshot["synthetic"],
        "captured_at": captured,
        "coverage": effective_coverage,
        "warnings": list(warnings),
        "unavailable_signatures": list(unavailable),
        "gaps": gaps,
        "transaction_count": len(seen),
        "failed_count": failed,
        "unknown_status_count": sum(g["asset"] == "all" for g in gaps),
        "wallet_paid_fees_base_units": str(fees),
        "wallet_paid_fees_sol": decimal_amount(fees, 9),
        "rows": rows,
        "assets": list(totals.values()),
    }


def analyze(snapshot: dict) -> dict:
    """Validate schema v1 and return an exact JSON-serializable ledger.

    Malformed data raises ValidationError. Missing metadata/owners create explicit
    gaps and partial coverage, never guessed zero balances.
    """
    try:
        return _analyze(snapshot)
    except ValidationError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError):
        raise ValidationError("Malformed snapshot structure or value.") from None
