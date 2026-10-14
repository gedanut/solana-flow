import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from test_ledger import W, tx

from solana_flow.rpc import RPCClient, RPCError, fetch, validate_address

SIG = "2" * 88


class FakeRPC:
    def __init__(self, pages, results=None):
        self.pages = iter(pages)
        self.results = results or {}
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "getSignaturesForAddress":
            result = next(self.pages)
        else:
            result = self.results.get(params[0])
        if isinstance(result, Exception):
            raise result
        return result


class RPCTests(unittest.TestCase):
    def test_address_validation(self):
        validate_address(W)
        for address in ["bad", "0" * 32, "1" * 33, "2" * 100]:
            with self.assertRaises(ValueError):
                validate_address(address)

    def test_pagination_and_dedup(self):
        rpc = FakeRPC(
            [[{"signature": SIG}], [{"signature": SIG}, {"signature": "3" * 88}], []],
            {SIG: tx(SIG), "3" * 88: tx("3" * 88)},
        )
        s = fetch(W, rpc, limit=4)
        self.assertEqual(len(s["transactions"]), 2)
        self.assertTrue(s["coverage"]["reached_history"])
        self.assertFalse(s["coverage"]["partial"])
        self.assertEqual(rpc.calls[2][1][1]["before"], SIG)
        self.assertEqual(rpc.calls[1][1][1]["maxSupportedTransactionVersion"], 0)

    def test_cap_null_and_stalled_page(self):
        rpc = FakeRPC([[{"signature": SIG}]])
        s = fetch(W, rpc, limit=1)
        self.assertTrue(s["coverage"]["cap_reached"])
        self.assertTrue(s["coverage"]["partial"])
        self.assertEqual(s["unavailable_signatures"], [SIG])
        rpc = FakeRPC([[{"signature": SIG}], [{"signature": SIG}]], {SIG: tx(SIG)})
        s = fetch(W, rpc, limit=10)
        self.assertTrue(s["coverage"]["partial"])
        self.assertFalse(s["coverage"]["reached_history"])

    def test_capture_transport_failure(self):
        rpc = FakeRPC([RPCError("Transport unavailable.")])
        s = fetch(W, rpc, limit=2)
        self.assertTrue(s["coverage"]["partial"])
        self.assertTrue(s["warnings"])

    @patch("solana_flow.rpc.time.sleep")
    @patch("solana_flow.rpc.urlopen")
    def test_retry_and_secret_redaction(self, opening, sleeping):
        secret = "https://user:SECRET@example.invalid/private?key=SECRET"
        opening.side_effect = URLError(secret)
        client = RPCClient(secret, retries=2)
        with self.assertRaises(RPCError) as ctx:
            client.call("getTransaction", [SIG])
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertEqual(opening.call_count, 3)
        self.assertEqual(sleeping.call_count, 2)

    @patch("solana_flow.rpc.time.sleep")
    @patch("solana_flow.rpc.urlopen")
    def test_http_rate_limit_then_success(self, opening, sleeping):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": []}
        ).encode()
        opening.side_effect = [
            HTTPError("secret", 429, "secret", {"Retry-After": "1"}, None),
            response,
        ]
        self.assertEqual(
            RPCClient("https://example.invalid").call("getSignaturesForAddress", [W]), []
        )
        sleeping.assert_called_once_with(1.0)
