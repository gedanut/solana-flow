import contextlib
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from test_ledger import W, snapshot, token, tx
from test_rpc import SIG, FakeRPC

from solana_flow.cli import main
from solana_flow.ledger import ValidationError, analyze, decimal_amount
from solana_flow.report import _cell, _when, html_text
from solana_flow.rpc import MAX_RESPONSE, RPCClient, RPCError, fetch


class LedgerHardeningTests(unittest.TestCase):
    def test_unknown_owner_is_not_inferred_from_other_side(self):
        for known_pre in (True, False):
            t = tx()
            t["meta"]["preTokenBalances"] = [token(owner=W if known_pre else None)]
            t["meta"]["postTokenBalances"] = [token(owner=None if known_pre else W)]
            r = analyze(snapshot(t))
            self.assertTrue(r["coverage"]["partial"])
            self.assertEqual(len(r["assets"]), 1)
            self.assertIn("Unknown token owner", r["gaps"][0]["reason"])

    def test_mint_level_uncertainty_omits_all_accounts(self):
        t = tx()
        t["meta"]["postTokenBalances"] = [token(1), token(2, owner=None)]
        self.assertEqual(len(analyze(snapshot(t))["rows"]), 1)

    def test_incoming_ownership_and_no_native_reference(self):
        t = tx()
        t["transaction"]["message"]["accountKeys"][0] = "someone-else"
        t["meta"]["preTokenBalances"] = [token(owner="someone-else")]
        t["meta"]["postTokenBalances"] = [token()]
        r = analyze(snapshot(t))
        self.assertEqual(r["wallet_paid_fees_base_units"], "0")
        self.assertEqual(r["rows"][0]["amount_base_units"], "100")

    def test_missing_metadata_is_explicit(self):
        for key in ("preTokenBalances", "postTokenBalances"):
            t = tx()
            t["meta"].pop(key)
            r = analyze(snapshot(t))
            self.assertTrue(r["gaps"])
            self.assertEqual(len(r["rows"]), 1)
        t = tx()
        t["meta"] = None
        r = analyze(snapshot(t))
        self.assertEqual(r["rows"], [])
        self.assertEqual(r["unknown_status_count"], 1)
        self.assertTrue(r["coverage"]["partial"])

    def test_cross_transaction_decimals_conflict(self):
        a, b = tx("a"), tx("b")
        a["meta"]["postTokenBalances"] = [token(decimals=2)]
        b["meta"]["postTokenBalances"] = [token(decimals=3)]
        with self.assertRaises(ValidationError):
            analyze(snapshot(a, b))

    def test_malformed_structures(self):
        mutations = [
            lambda s: s.update(wallet=""),
            lambda s: s.update(cluster="https://secret"),
            lambda s: s.update(synthetic=1),
            lambda s: s.update(captured_at="yesterday"),
            lambda s: s.update(captured_at="2026-01-01"),
            lambda s: s.update(schema_version=True),
            lambda s: s.update(warnings="bad"),
            lambda s: s.update(unavailable_signatures=["a", "a"]),
            lambda s: s.update(unavailable_signatures=["synthetic-1"]),
            lambda s: s["coverage"].update(cap_reached=True),
            lambda s: s["coverage"].update(limit=0),
            lambda s: s["coverage"].update(partial="false"),
            lambda s: s["transactions"][0].update(blockTime=True),
            lambda s: s["transactions"][0]["meta"].update(fee=-1),
            lambda s: s["transactions"][0]["meta"].update(postBalances=[0]),
            lambda s: s["transactions"][0]["meta"].update(preBalances=[True, 0, 0]),
            lambda s: s["transactions"][0]["meta"].update(postTokenBalances=[token(amount="-1")]),
            lambda s: s["transactions"][0]["meta"].update(postTokenBalances=[token(decimals=256)]),
            lambda s: s["transactions"][0]["meta"].update(postTokenBalances=[token(index=True)]),
            lambda s: s["transactions"][0]["meta"].update(
                preTokenBalances=[token()], postTokenBalances=[token(mint="different")]
            ),
            lambda s: s["transactions"][0]["transaction"]["message"].update(accountKeys=[W, W]),
            lambda s: s["transactions"][0]["transaction"]["message"].update(accountKeys=[W, {}]),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                s = snapshot(tx())
                mutate(s)
                with self.assertRaises(ValidationError):
                    analyze(s)

    def test_assets_never_summed_and_order_independent(self):
        t = tx()
        t["meta"]["postTokenBalances"] = [
            token(1, "123456789012345678901234567890"),
            token(2, "10", mint="different", decimals=0),
        ]
        a = analyze(snapshot(t))
        t["meta"]["postTokenBalances"].reverse()
        b = analyze(snapshot(t))
        self.assertEqual(a, b)
        self.assertEqual(len(a["assets"]), 3)
        self.assertEqual(a["assets"][1]["net"], "1234567890123456789012345678.90")
        self.assertEqual(decimal_amount(0, 0), "0")
        self.assertEqual(decimal_amount(-1, 3), "-0.001")


class RPCHardeningTests(unittest.TestCase):
    def response(self, data):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        return response

    @patch("solana_flow.rpc.urlopen")
    def test_envelope_version_required(self, opening):
        opening.return_value = self.response(b'{"id":1,"result":[]}')
        with self.assertRaises(RPCError):
            RPCClient("https://example.invalid").call("getTransaction", [])

    @patch("solana_flow.rpc.time.sleep")
    @patch("solana_flow.rpc.urlopen")
    def test_rpc_and_http_failure_matrix(self, opening, sleeping):
        cases = [
            b"not json",
            b"[]",
            b'{"id":2,"result":[]}',
            b'{"jsonrpc":"2.0","id":1}',
            b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"SECRET"}}',
            b'{"jsonrpc":"2.0","id":1,"error":{"code":-32005,"message":"SECRET"}}',
            b"x" * (MAX_RESPONSE + 1),
        ]
        for case in cases:
            with self.subTest(case=case[:60]):
                opening.return_value = self.response(case)
                with self.assertRaises(RPCError) as error:
                    RPCClient("https://example.invalid", retries=1).call("getTransaction", [])
                self.assertNotIn("SECRET", str(error.exception))
        for status in (403, 500):
            error = HTTPError("SECRET", status, "SECRET", {}, io.BytesIO())
            opening.side_effect = error
            with self.assertRaises(RPCError):
                RPCClient("https://example.invalid", retries=0).call("getTransaction", [])
            error.close()

    def test_url_and_parameter_validation(self):
        for url in (
            "file:///secret",
            "https://[",
            "https://example.invalid:abc",
            "https://host/#secret",
        ):
            with self.assertRaises(ValidationError):
                RPCClient(url)
        for kwargs in ({"timeout": 0}, {"retries": -1}):
            with self.assertRaises(ValidationError):
                RPCClient("https://example.invalid", **kwargs)
        for limit in (0, -1, 10001, True):
            with self.assertRaises(ValidationError):
                fetch(W, FakeRPC([]), limit=limit)
        with self.assertRaises(ValidationError):
            RPCClient("https://example.invalid").call("sendTransaction", [])

    def test_bad_pages_and_results(self):
        for page in (None, [{}], [{"signature": "bad"}], "bad"):
            self.assertTrue(fetch(W, FakeRPC([page]))["coverage"]["partial"])
        for result in (None, {}, tx("mismatch"), RPCError("failure"), {"transaction": None}):
            s = fetch(W, FakeRPC([[{"signature": SIG}]], {SIG: result}), limit=1)
            self.assertEqual(s["unavailable_signatures"], [SIG])
        t = tx(SIG)
        t["meta"] = None
        s = fetch(W, FakeRPC([[{"signature": SIG}]], {SIG: t}), limit=1)
        self.assertTrue(s["coverage"]["partial"])
        self.assertEqual(len(s["transactions"]), 1)


class OutputHardeningTests(unittest.TestCase):
    def test_partial_report_and_explorer(self):
        s = snapshot(tx(SIG))
        s.update(synthetic=False, cluster="devnet", unavailable_signatures=["unavailable"])
        t = s["transactions"][0]
        t["meta"]["preTokenBalances"] = [token(owner=None)]
        r = analyze(s)
        html = html_text(r)
        self.assertIn("Partial data", html)
        self.assertIn("Unknown token owner", html)
        self.assertIn("?cluster=devnet", html)
        self.assertIn("Unavailable transaction", html)
        r["cluster"] = "custom"
        self.assertNotIn("https://explorer.solana.com/tx/", html_text(r))
        self.assertIn("No attributable asset movements", html_text(analyze(snapshot())))
        self.assertEqual(_when(None), "Unknown time")
        self.assertTrue(_when(10**100).startswith("Unix seconds"))
        for text in ("=1+1", "+1", "-formula", " @bad", "\tfoo", "\rfoo", "\nfoo"):
            self.assertTrue(_cell(text).startswith("'"))
        self.assertEqual(_cell(None), "")

    def test_cli_partial_replay_and_errors(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            path = Path(directory) / "snapshot.json"
            s = snapshot(tx())
            s["transactions"][0]["meta"] = None
            path.write_text(json.dumps(s))
            self.assertEqual(main(["analyze", str(path), "--output", directory]), 2)
            with patch("solana_flow.cli.MAX_SNAPSHOT", 1):
                self.assertEqual(main(["analyze", str(path), "--output", directory]), 1)
            with patch("solana_flow.cli.analyze", side_effect=KeyboardInterrupt):
                self.assertEqual(main(["demo", "--output", directory]), 130)
            with self.assertRaises(SystemExit) as ex:
                main(["fetch", W, "--rpc-url", "https://SECRET", "--limit", "SECRET"])
            self.assertEqual(ex.exception.code, 1)
            self.assertNotIn("SECRET", err.getvalue())
            with patch("sys.argv", ["solana-flow", "demo", "--output", directory]):
                with self.assertRaises(SystemExit) as ex:
                    runpy.run_module("solana_flow", run_name="__main__")
                self.assertEqual(ex.exception.code, 0)
