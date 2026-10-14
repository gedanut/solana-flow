"""Regenerate the deterministic SYNTHETIC demo; no randomness or network."""

import json
from pathlib import Path

WALLET = "SyntheticWallet111111111111111111111111111111"
OTHER = "SyntheticCounterparty11111111111111111111111"
MINT_A = "SyntheticMintA1111111111111111111111111111111"
MINT_B = "SyntheticMintB1111111111111111111111111111111"
WSOL = "So11111111111111111111111111111111111111112"


def token(i, amount, mint=MINT_A, decimals=6, owner=WALLET):
    return {
        "accountIndex": i,
        "mint": mint,
        "owner": owner,
        "uiTokenAmount": {
            "amount": str(amount),
            "decimals": decimals,
            "uiAmount": None,
            "uiAmountString": "unused",
        },
    }


def transaction(n, native, before=(), after=(), *, paid=True, failed=False, versioned=False):
    keys = [WALLET, OTHER, "SyntheticTokenAccountA", "SyntheticTokenAccountB"]
    if not paid:
        keys[0], keys[1] = keys[1], keys[0]
    i = 0 if paid else 1
    pre = [5_000_000_000, 5_000_000_000, 2_039_280, 2_039_280]
    post = pre.copy()
    post[i] += native
    before_by_index = {record["accountIndex"]: record for record in before}
    after_by_index = {record["accountIndex"]: record for record in after}
    for index in before_by_index.keys() | after_by_index.keys():
        for records, balances in ((before_by_index, pre), (after_by_index, post)):
            record = records.get(index)
            balances[index] = 0 if record is None else 2_039_280
            if record and record["mint"] == WSOL:
                balances[index] += int(record["uiTokenAmount"]["amount"])
    # Counterparty funds/receives any remaining movement; lamports conserve minus fee.
    post[1 - i] += sum(pre) - sum(post) - 5000
    meta = {
        "err": {"InstructionError": [0, {"Custom": 1}]} if failed else None,
        "fee": 5000,
        "preBalances": pre,
        "postBalances": post,
        "preTokenBalances": list(before),
        "postTokenBalances": list(after),
    }
    if versioned:
        meta["loadedAddresses"] = {"writable": keys[2:], "readonly": []}
        keys = keys[:2]
    elif n % 2 == 0:
        keys = [
            {"pubkey": k, "signer": j == 0, "writable": True, "source": "transaction"}
            for j, k in enumerate(keys)
        ]
    return {
        "slot": 310000000 + n * 100,
        "blockTime": None if n == 12 else 1767225600 + n * 3600,
        "version": 0 if versioned else "legacy",
        "meta": meta,
        "transaction": {
            "signatures": [f"SYNTHETIC-{n:03d}-not-a-chain-signature"],
            "message": {"accountKeys": keys, "instructions": []},
        },
    }


def fixture():
    txs = [
        transaction(1, 2_500_000_000, paid=False),
        transaction(2, -425_005_000),
        transaction(3, -2_044_280, after=[token(2, 125_000_000)]),
        transaction(4, -5000, [token(2, 125_000_000)], [token(2, 86_250_000)]),
        transaction(
            5,
            -5000,
            [token(2, 86_250_000), token(3, 0)],
            [token(2, 50_000_000), token(3, 36_250_000)],
        ),
        transaction(6, -5000, after=[token(2, 7500, MINT_B, 2)]),
        transaction(7, -5000, [token(2, 7500, MINT_B, 2)], [token(2, 6300, MINT_B, 2)]),
        transaction(8, -5000, failed=True),
        transaction(9, 2_034_280, [token(2, 36_250_000)], [token(3, 36_250_000, owner=OTHER)]),
        transaction(10, -5000, after=[token(2, 20_000_000)], versioned=True),
        transaction(11, -252_044_280, after=[token(2, 250_000_000, WSOL, 9)]),
        transaction(12, -5000, [token(2, 20_000_000)], [token(2, 20_000_000, owner=OTHER)]),
    ]
    return {
        "schema_version": 1,
        "synthetic": True,
        "wallet": WALLET,
        "cluster": "synthetic",
        "captured_at": "2026-01-01T13:00:00Z",
        "coverage": {
            "limit": 12,
            "pages": 1,
            "cap_reached": True,
            "reached_history": False,
            "partial": False,
            "discovery": "wallet-account-keys-only",
        },
        "transactions": txs,
        "unavailable_signatures": [],
        "warnings": [],
    }


if __name__ == "__main__":
    Path("src/solana_flow/data/demo.json").write_text(json.dumps(fixture(), indent=2) + "\n")
