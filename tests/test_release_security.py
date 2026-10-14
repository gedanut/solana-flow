"""Independent review regression tests."""

import json
import unittest
from unittest.mock import MagicMock, patch

from solana_flow.rpc import RPCClient, RPCError


class ReleaseSecurityTests(unittest.TestCase):
    def test_capture_strips_provider_extensions_and_preserves_ledger(self):
        from test_ledger import W, tx
        from test_rpc import SIG, FakeRPC

        from solana_flow.ledger import analyze
        from solana_flow.rpc import fetch

        original = tx(SIG)
        original["providerDebug"] = {"endpoint": "https://example.invalid/?key=DUMMY_MARKER"}
        original["transaction"]["message"]["instructions"] = [{"data": "DUMMY_MARKER"}]
        original["meta"]["logMessages"] = ["DUMMY_MARKER"]
        original["meta"]["err"] = {"InstructionError": [0, "DUMMY_MARKER"]}
        captured = fetch(W, FakeRPC([[{"signature": SIG}]], {SIG: original}), limit=1)
        self.assertNotIn("DUMMY_MARKER", json.dumps(captured))
        self.assertEqual(
            analyze(captured)["rows"], analyze(dict(captured, transactions=[original]))["rows"]
        )
        self.assertEqual(analyze(captured)["failed_count"], 1)
        self.assertIn("providerDebug", original)

    def test_capture_preserves_versioned_keys_tokens_and_gaps(self):
        from test_ledger import W, token, tx
        from test_rpc import SIG, FakeRPC

        from solana_flow.ledger import analyze
        from solana_flow.rpc import fetch

        for kind in ("parsed", "loaded", "missing-token-side", "missing-meta"):
            original = tx(SIG)
            original["version"] = 0
            original["meta"]["postTokenBalances"] = [token(owner=None)]
            if kind == "parsed":
                original["transaction"]["message"]["accountKeys"] = [
                    {"pubkey": key, "providerDebug": "DUMMY_MARKER"}
                    for key in original["transaction"]["message"]["accountKeys"]
                ]
            elif kind == "loaded":
                original["transaction"]["message"]["accountKeys"] = [W]
                original["meta"]["loadedAddresses"] = {
                    "writable": ["account1"],
                    "readonly": ["account2"],
                }
            elif kind == "missing-token-side":
                del original["meta"]["preTokenBalances"]
            else:
                original["meta"] = None
            captured = fetch(W, FakeRPC([[{"signature": SIG}]], {SIG: original}), limit=1)
            self.assertEqual(captured["transactions"][0]["version"], 0)
            expected = analyze(dict(captured, transactions=[original]))
            actual = analyze(captured)
            self.assertEqual(actual["rows"], expected["rows"])
            self.assertEqual(actual["gaps"], expected["gaps"])
            self.assertNotIn("DUMMY_MARKER", json.dumps(captured))

    def test_malformed_url_rejected_without_echo(self):
        from solana_flow.ledger import ValidationError

        for url in (
            "http://example.invalid/bad path?key=DUMMY_MARKER",
            "https://example.invalid/\n?key=DUMMY_MARKER",
            "https://example.invalid/é?key=DUMMY_MARKER",
        ):
            with self.assertRaises(ValidationError) as caught:
                RPCClient(url, retries=0)
            self.assertNotIn("DUMMY_MARKER", str(caught.exception))

    def test_rpc_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw in (
            b'{"jsonrpc":"2.0","id":1,"result":{"postBalances":[1],"postBalances":[2]}}',
            b'{"jsonrpc":"2.0","id":1,"result":{},"result":{}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"amount":NaN}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"amount":Infinity}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"amount":1e999}}',
            b'{"jsonrpc":"2.0","id":1,"result":{"amount":-1e999}}',
        ):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = raw
            with patch("solana_flow.rpc.urlopen", return_value=response):
                with self.assertRaises(RPCError):
                    RPCClient("https://example.invalid", retries=0).call("getTransaction", [])
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"jsonrpc":"2.0","id":1,"result":{"amount":1.25}}'
        )
        with patch("solana_flow.rpc.urlopen", return_value=response):
            self.assertEqual(
                RPCClient("https://example.invalid", retries=0).call("getTransaction", []),
                {"amount": 1.25},
            )
