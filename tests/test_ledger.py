import copy
import unittest
from decimal import localcontext

from solana_flow.ledger import ValidationError, analyze, decimal_amount

W = "11111111111111111111111111111111"
M = "TokenMintSynthetic"


def token(index=1, amount="100", owner=W, decimals=2, mint=M):
    r = {
        "accountIndex": index,
        "mint": mint,
        "uiTokenAmount": {"amount": amount, "decimals": decimals},
    }
    if owner is not None:
        r["owner"] = owner
    return r


def tx(signature="synthetic-1"):
    return {
        "slot": 7,
        "blockTime": None,
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": [W, "account1", "account2"]},
        },
        "meta": {
            "err": None,
            "fee": 5000,
            "preBalances": [10000, 0, 0],
            "postBalances": [5000, 0, 0],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def snapshot(*transactions):
    return {
        "schema_version": 1,
        "wallet": W,
        "cluster": "synthetic",
        "synthetic": True,
        "captured_at": "2026-01-01T00:00:00Z",
        "coverage": {
            "limit": 10,
            "pages": 1,
            "cap_reached": False,
            "reached_history": True,
            "partial": False,
            "discovery": "wallet-account-keys-only",
        },
        "transactions": list(transactions),
        "unavailable_signatures": [],
        "warnings": [],
    }


class LedgerTests(unittest.TestCase):
    def test_exact_precision_and_fee(self):
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(decimal_amount(123456789012345678901, 9), "123456789012.345678901")
        result = analyze(snapshot(tx()))
        self.assertEqual(result["rows"][0]["amount_base_units"], "-5000")
        self.assertEqual(result["rows"][0]["decimal_amount"], "-0.000005000")
        self.assertIsNone(result["rows"][0]["time"])
        self.assertEqual(result["wallet_paid_fees_base_units"], "5000")

    def test_multiple_accounts_internal_zero(self):
        t = tx()
        t["meta"]["preTokenBalances"] = [token(1, "100"), token(2, "200")]
        t["meta"]["postTokenBalances"] = [token(1, "250"), token(2, "50")]
        rows = analyze(snapshot(t))["rows"]
        self.assertEqual(rows[1]["amount_base_units"], "0")

    def test_ownership_changes_per_side(self):
        t = tx()
        t["meta"]["preTokenBalances"] = [token()]
        t["meta"]["postTokenBalances"] = [token(owner="another-owner")]
        self.assertEqual(analyze(snapshot(t))["rows"][1]["amount_base_units"], "-100")
        t["meta"]["postTokenBalances"] = [token(owner=None)]
        r = analyze(snapshot(t))
        self.assertEqual(len(r["rows"]), 1)
        self.assertTrue(r["gaps"])

    def test_new_closed_accounts(self):
        t = tx()
        t["meta"]["postTokenBalances"] = [token()]
        self.assertEqual(analyze(snapshot(t))["rows"][1]["amount_base_units"], "100")
        t["meta"]["preTokenBalances"], t["meta"]["postTokenBalances"] = [token()], []
        self.assertEqual(analyze(snapshot(t))["rows"][1]["amount_base_units"], "-100")

    def test_failed_and_dedup_conflict(self):
        t = tx()
        t["meta"]["err"] = {"InstructionError": [0, "failure"]}
        r = analyze(snapshot(t, copy.deepcopy(t)))
        self.assertEqual(r["transaction_count"], 1)
        self.assertEqual(r["failed_count"], 1)
        other = copy.deepcopy(t)
        other["slot"] = 8
        with self.assertRaises(ValidationError):
            analyze(snapshot(t, other))

    def test_invalid_records(self):
        mutations = [
            lambda t: t["meta"].pop("preBalances"),
            lambda t: t["meta"].update(preTokenBalances=[token(), token()]),
            lambda t: t["meta"].update(postTokenBalances=[token(index=99)]),
            lambda t: t["meta"].update(postTokenBalances=[token(amount="1.2")]),
            lambda t: t["meta"].update(
                preTokenBalances=[token()], postTokenBalances=[token(decimals=3)]
            ),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                t = tx()
                mutate(t)
                with self.assertRaises(ValidationError):
                    analyze(snapshot(t))

    def test_versioned_keys(self):
        for parsed in [True, False]:
            t = tx()
            keys = t["transaction"]["message"]["accountKeys"]
            t["meta"]["loadedAddresses"] = {"writable": ["account1"], "readonly": ["account2"]}
            t["transaction"]["message"]["accountKeys"] = (
                [
                    {"pubkey": k, "source": "transaction" if i == 0 else "lookupTable"}
                    for i, k in enumerate(keys)
                ]
                if parsed
                else [W]
            )
            t["meta"]["postTokenBalances"] = [token(2)]
            self.assertEqual(analyze(snapshot(t))["rows"][1]["amount_base_units"], "100")
