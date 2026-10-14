import io
import json
import unittest
from http.client import IncompleteRead
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from test_ledger import W, token, tx
from test_rpc import SIG, FakeRPC

from solana_flow.rpc import RPCClient, RPCError, fetch


class RegressionTests(unittest.TestCase):
    @patch("solana_flow.rpc.time.sleep")
    @patch("solana_flow.rpc.urlopen")
    def test_nonfinite_retry_after_uses_bounded_backoff(self, opening, sleeping):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"jsonrpc":"2.0","id":1,"result":[]}'
        opening.side_effect = [
            HTTPError("secret", 429, "secret", {"Retry-After": "NaN"}, io.BytesIO()),
            response,
        ]
        RPCClient("https://example.invalid").call("getTransaction", [])
        sleeping.assert_called_once_with(0.5)

    @patch("solana_flow.rpc.time.sleep")
    @patch("solana_flow.rpc.urlopen")
    def test_truncated_transport_is_safe_and_retried(self, opening, sleeping):
        opening.side_effect = IncompleteRead(b"SECRET", 100)
        with self.assertRaises(RPCError) as error:
            RPCClient("https://example.invalid", retries=1).call("getTransaction", [])
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(opening.call_count, 2)

    def test_capture_cross_transaction_mint_consistency(self):
        a, b = tx(SIG), tx("3" * 88)
        a["meta"]["postTokenBalances"] = [token(owner="someone-else", decimals=2)]
        b["meta"]["postTokenBalances"] = [token(decimals=3)]
        rpc = FakeRPC([[{"signature": SIG}, {"signature": "3" * 88}]], {SIG: a, "3" * 88: b})
        s = fetch(W, rpc, limit=2)
        self.assertEqual(len(s["transactions"]), 1)
        self.assertEqual(s["unavailable_signatures"], ["3" * 88])
        self.assertNotIn("example.invalid", json.dumps(s))

    def test_capture_size_budget_stops_with_explicit_gap(self):
        rpc = FakeRPC([[{"signature": SIG}]], {SIG: tx(SIG)})
        with patch("solana_flow.rpc.MAX_CAPTURE_BYTES", 1):
            s = fetch(W, rpc, limit=3)
        self.assertTrue(s["coverage"]["partial"])
        self.assertFalse(s["coverage"]["reached_history"])
        self.assertEqual(s["unavailable_signatures"], [SIG])
        self.assertTrue(any("size budget" in warning for warning in s["warnings"]))
