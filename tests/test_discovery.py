"""Bounded current-token-account history capture; no external RPC endpoints."""

import importlib
import importlib.util
import unittest

from test_ledger import W, tx
from test_rpc import SIG, FakeRPC

from solana_flow.ledger import analyze
from solana_flow.rpc import fetch

CLASSIC = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
A = "So11111111111111111111111111111111111111112"
B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def owned(address, program=CLASSIC, owner=W):
    return {
        "pubkey": address,
        "account": {
            "owner": program,
            "data": {"parsed": {"type": "account", "info": {"owner": owner}}},
        },
    }


class TokenRPC:
    def __init__(self, accounts=None, histories=None, results=None):
        self.accounts = accounts or {}
        self.histories = histories or {}
        self.results = results or {}
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "getTokenAccountsByOwner":
            result = self.accounts.get(params[1]["programId"], [])
            if isinstance(result, list):
                return {"context": {"slot": 7}, "value": result}
        elif method == "getSignaturesForAddress":
            history = self.histories.get(params[0], [])
            options = params[1]
            start = history.index(options["before"]) + 1 if "before" in options else 0
            return [{"signature": s} for s in history[start : start + options["limit"]]]
        else:
            result = self.results.get(params[0])
        if isinstance(result, Exception):
            raise result
        return result


class ScriptedRPC(TokenRPC):
    def __init__(self, pages, **kwargs):
        super().__init__(**kwargs)
        self.pages = {address: iter(values) for address, values in pages.items()}

    def call(self, method, params):
        if method == "getSignaturesForAddress" and params[0] in self.pages:
            self.calls.append((method, params))
            result = next(self.pages[params[0]])
            if isinstance(result, Exception):
                raise result
            return result
        return super().call(method, params)


class DiscoveryTests(unittest.TestCase):
    def test_failed_source_is_not_labeled_as_budget_capped(self):
        from solana_flow.discovery import capture
        from solana_flow.rpc import RPCError

        rpc = ScriptedRPC(
            {W: [RPCError("SECRET")]},
            accounts={CLASSIC: [owned(A)]},
            histories={A: [SIG]},
            results={SIG: tx(SIG)},
        )
        result = capture(W, rpc, include_tokens=True, limit=1)
        self.assertTrue(result["coverage"]["cap_reached"])
        self.assertFalse(result["coverage"]["sources"][0]["cap_reached"])
        self.assertTrue(result["coverage"]["sources"][0]["partial"])
        self.assertTrue(result["coverage"]["sources"][1]["cap_reached"])
        analyze(result)

    def test_scope_never_substitutes_current_ownership_for_historical_balance_owners(self):
        from test_ledger import token

        from solana_flow.discovery import capture

        for historical_owner in (None, B, W):
            with self.subTest(historical_owner=historical_owner):
                receipt = tx(SIG)
                receipt["transaction"]["message"]["accountKeys"] = [B, A, "account2"]
                receipt["meta"]["postTokenBalances"] = [token(owner=historical_owner)]
                record = owned(A)
                record["account"]["data"]["parsed"]["info"].pop("owner")
                rpc = TokenRPC({CLASSIC: [record, record]}, {A: [SIG]}, {SIG: receipt})
                result = capture(W, rpc, include_tokens=True, limit=2)
                ledger = analyze(result)
                self.assertEqual(result["coverage"]["token_accounts"], [A])
                self.assertEqual(len(result["warnings"]), 1)
                self.assertEqual(len(ledger["rows"]), int(historical_owner == W))
                self.assertEqual(bool(ledger["gaps"]), historical_owner is None)
                self.assertEqual(
                    result["transactions"][0]["meta"]["postTokenBalances"],
                    receipt["meta"]["postTokenBalances"],
                )
                self.assertEqual(ledger["wallet_paid_fees_base_units"], "0")

    def test_ledger_rejects_invalid_multi_source_coverage(self):
        import copy

        from solana_flow.discovery import capture
        from solana_flow.ledger import ValidationError

        base = capture(W, TokenRPC({CLASSIC: [owned(A)]}), include_tokens=True)
        mutations = [
            lambda c: c.pop("sources"),
            lambda c: c.update(token_accounts=["https://SECRET.invalid"]),
            lambda c: c.update(token_accounts=[A, A]),
            lambda c: c.update(sources=c["sources"] + [c["sources"][0]]),
            lambda c: c["sources"][0].update(address=B),
            lambda c: c["sources"][0].update(pages=True),
            lambda c: c["sources"][0].update(partial="yes"),
            lambda c: c["sources"][0].update(cap_reached=True),
            lambda c: c["sources"][0].update(providerEndpoint="SECRET"),
            lambda c: c.update(pages=c["pages"] + 1),
            lambda c: c["sources"][0].update(reached_history=False),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                snapshot = copy.deepcopy(base)
                mutate(snapshot["coverage"])
                with self.assertRaises(ValidationError):
                    analyze(snapshot)

    def test_real_http_capture_allows_only_read_only_token_discovery(self):
        import json
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from solana_flow.discovery import capture
        from solana_flow.rpc import RPCClient

        requests = []
        backend = TokenRPC({CLASSIC: [owned(A)]}, {A: [SIG]}, {SIG: tx(SIG)})

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(request)
                if len(requests) == 1:
                    self.send_response(429)
                    self.send_header("Retry-After", "0")
                    self.end_headers()
                    return
                result = backend.call(request["method"], request["params"])
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode())

        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except OSError:
            if os.environ.get("SOLANA_FLOW_REQUIRE_LOCAL_HTTP") == "1":
                raise
            self.skipTest("Local socket binding is unavailable")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = RPCClient(f"http://127.0.0.1:{server.server_port}/?key=LOCAL_TEST_MARKER")
            result = capture(W, client, include_tokens=True, limit=2)
            self.assertEqual(result["coverage"]["token_accounts"], [A])
            self.assertEqual(analyze(result)["transaction_count"], 1)
            self.assertEqual(
                [
                    r["params"][1]["programId"]
                    for r in requests
                    if r["method"] == "getTokenAccountsByOwner"
                ],
                [CLASSIC, CLASSIC, TOKEN_2022],
            )
            self.assertNotIn("LOCAL_TEST_MARKER", str(result))
            for forbidden in ("sendTransaction", "requestAirdrop", "getBalance"):
                with self.assertRaises(ValueError):
                    client.call(forbidden, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_capture_byte_budget_stops_all_sources_without_retaining_oversized_result(self):
        from unittest.mock import patch

        from solana_flow.discovery import capture

        rpc = TokenRPC({CLASSIC: [owned(A)]}, {W: [SIG], A: ["3" * 88]}, {SIG: tx(SIG)})
        with patch("solana_flow.discovery.MAX_CAPTURE_BYTES", 1, create=True):
            result = capture(W, rpc, include_tokens=True, limit=10)
        self.assertEqual(result["transactions"], [])
        self.assertEqual(result["unavailable_signatures"], [SIG])
        self.assertEqual([p[0] for m, p in rpc.calls if m == "getSignaturesForAddress"], [W])
        self.assertFalse(result["coverage"]["reached_history"])
        self.assertTrue(any("size budget" in w for w in result["warnings"]))
        self.assertTrue(all(s["partial"] for s in result["coverage"]["sources"]))
        analyze(result)

    def test_conflicting_mint_decimals_across_sources_leave_valid_partial_snapshot(self):
        from test_ledger import token

        from solana_flow.discovery import capture

        second = "3" * 88
        first_tx, second_tx = tx(SIG), tx(second)
        first_tx["meta"]["postTokenBalances"] = [token(decimals=2)]
        second_tx["meta"]["postTokenBalances"] = [token(decimals=3)]
        rpc = TokenRPC(
            {CLASSIC: [owned(A)]}, {W: [SIG], A: [second]}, {SIG: first_tx, second: second_tx}
        )
        result = capture(W, rpc, include_tokens=True, limit=3)
        self.assertEqual(result["unavailable_signatures"], [second])
        self.assertEqual(len(result["transactions"]), 1)
        self.assertEqual(analyze(result)["transaction_count"], 1)

    def test_mismatched_transaction_is_unavailable_and_never_replaces_requested_signature(self):
        from solana_flow.discovery import capture

        wrong = tx("3" * 88)
        rpc = TokenRPC(histories={W: [SIG]}, results={SIG: wrong})
        result = capture(W, rpc, include_tokens=True, limit=1)
        self.assertEqual(result["transactions"], [])
        self.assertEqual(result["unavailable_signatures"], [SIG])
        self.assertTrue(result["coverage"]["cap_reached"])
        analyze(result)

    def test_global_cap_counts_unavailable_and_fetches_each_overlap_only_once(self):
        from solana_flow.discovery import capture
        from solana_flow.rpc import RPCError

        second, third = "3" * 88, "4" * 88
        rpc = TokenRPC(
            {CLASSIC: [owned(A), owned(B)]},
            {W: [SIG, third], B: [SIG, third], A: [second]},
            {SIG: tx(SIG), second: None, third: RPCError("https://SECRET.invalid")},
        )
        result = capture(W, rpc, include_tokens=True, limit=3)
        self.assertEqual(
            [p[0] for m, p in rpc.calls if m == "getSignaturesForAddress"], [W, B, A, W]
        )
        self.assertEqual(
            [p[0] for m, p in rpc.calls if m == "getTransaction"], [SIG, second, third]
        )
        self.assertEqual(result["unavailable_signatures"], [second, third])
        self.assertEqual(len(result["transactions"]), 1)
        self.assertTrue(result["coverage"]["cap_reached"])
        self.assertTrue(all(s["cap_reached"] for s in result["coverage"]["sources"]))
        self.assertFalse(result["coverage"]["reached_history"])
        self.assertNotIn("SECRET", str(result))
        self.assertTrue(any("unavailable" in w for w in result["warnings"]))
        analyze(result)

    def test_invalid_or_failed_signature_source_does_not_hide_other_sources(self):
        from solana_flow.discovery import capture
        from solana_flow.rpc import RPCError

        invalid = [
            None,
            {},
            [{"signature": "https://SECRET.invalid"}],
            [None],
            [{"signature": SIG}, {"signature": "3" * 88}],
            RPCError("SECRET"),
        ]
        for response in invalid:
            with self.subTest(response=response):
                rpc = ScriptedRPC(
                    {W: [response]},
                    accounts={CLASSIC: [owned(A)]},
                    histories={A: [SIG]},
                    results={SIG: tx(SIG)},
                )
                result = capture(W, rpc, include_tokens=True, limit=2)
                self.assertEqual(len(result["transactions"]), 1)
                self.assertEqual(
                    result["coverage"]["sources"][0],
                    {
                        "address": W,
                        "pages": 0 if isinstance(response, RPCError) else 1,
                        "partial": True,
                        "cap_reached": False,
                        "reached_history": False,
                    },
                )
                self.assertFalse(result["coverage"]["reached_history"])
                self.assertNotIn("SECRET", str(result))
                self.assertTrue(any("Signature discovery" in w for w in result["warnings"]))
                analyze(result)

    def test_local_stall_does_not_stop_other_sources_or_mistake_overlap_for_stall(self):
        from solana_flow.discovery import capture

        second, third = "3" * 88, "4" * 88
        rpc = ScriptedRPC(
            {
                W: [[{"signature": SIG}], [{"signature": SIG}]],
                B: [[{"signature": SIG}], [{"signature": second}], []],
                A: [[{"signature": third}], []],
            },
            accounts={CLASSIC: [owned(A), owned(B)]},
            results={s: tx(s) for s in (SIG, second, third)},
        )
        result = capture(W, rpc, include_tokens=True, limit=10)
        self.assertEqual(
            [t["transaction"]["signatures"][0] for t in result["transactions"]],
            [SIG, third, second],
        )
        self.assertEqual(
            [p[0] for m, p in rpc.calls if m == "getTransaction"], [SIG, third, second]
        )
        self.assertEqual(
            [p[0] for m, p in rpc.calls if m == "getSignaturesForAddress"], [W, B, A, W, B, A, B]
        )
        self.assertEqual(result["coverage"]["pages"], 7)
        self.assertFalse(result["coverage"]["reached_history"])
        self.assertTrue(result["coverage"]["sources"][0]["partial"])
        self.assertTrue(any("stalled" in w for w in result["warnings"]))
        analyze(result)

    def test_account_enumeration_is_bounded_and_still_queries_both_programs(self):
        from solana_flow.discovery import capture

        rpc = TokenRPC({CLASSIC: [owned(A), owned(B)] * 1000, TOKEN_2022: [owned(B, TOKEN_2022)]})
        result = capture(W, rpc, include_tokens=True, max_token_accounts=1)
        self.assertEqual(result["coverage"]["token_accounts"], [B])
        self.assertEqual(
            [p[1]["programId"] for m, p in rpc.calls if m == "getTokenAccountsByOwner"],
            [CLASSIC, TOKEN_2022],
        )
        self.assertFalse(result["coverage"]["reached_history"])
        self.assertTrue(any("bound" in w.lower() for w in result["warnings"]))
        self.assertFalse(any("failed" in w.lower() for w in result["warnings"]))
        self.assertEqual(len(result["warnings"]), 2)
        self.assertEqual(len(result["coverage"]["sources"]), 2)
        analyze(result)

    def test_discovery_rejects_malformed_or_unowned_accounts_without_leaking(self):
        from solana_flow.discovery import capture
        from solana_flow.rpc import RPCError

        bad_records = [
            None,
            {"pubkey": "https://SECRET.invalid"},
            owned("1" * 33),
            owned(A, TOKEN_2022),
            owned(A, owner=B),
            owned(W),
            {"pubkey": A, "account": {"owner": CLASSIC, "data": []}},
        ]
        invalid = [None, {"value": "SECRET"}, RPCError("https://SECRET.invalid")]
        invalid += [[record] for record in bad_records]
        for response in invalid:
            with self.subTest(response=response):
                rpc = TokenRPC({CLASSIC: response, TOKEN_2022: [owned(B, TOKEN_2022)]})
                result = capture(W, rpc, include_tokens=True)
                self.assertEqual(result["coverage"]["token_accounts"], [B])
                self.assertTrue(result["coverage"]["partial"])
                self.assertFalse(result["coverage"]["reached_history"])
                self.assertTrue(all(s["reached_history"] for s in result["coverage"]["sources"]))
                self.assertNotIn("SECRET", str(result))
                self.assertTrue(any("discovery" in w.lower() for w in result["warnings"]))
                analyze(result)

    def test_invalid_options_fail_before_rpc(self):
        from solana_flow.discovery import capture

        invalid = [
            {"wallet": "0" * 32},
            {"wallet": "1" * 33},
            {"limit": 0},
            {"limit": 10001},
            {"limit": True},
            {"limit": 1.5},
            {"cluster": "secret"},
            {"include_tokens": "yes"},
            {"max_token_accounts": 0},
            {"max_token_accounts": 1001},
            {"max_token_accounts": True},
        ]
        for options in invalid:
            with self.subTest(options=options):
                rpc = TokenRPC()
                kwargs = dict(wallet=W, include_tokens=True)
                kwargs.update(options)
                with self.assertRaises(ValueError):
                    capture(client=rpc, **kwargs)
                self.assertEqual(rpc.calls, [])

    def test_both_programs_discover_passive_receipt_and_preserve_balance_evidence(self):
        from test_ledger import token

        from solana_flow.discovery import capture

        receipt = tx(SIG)
        receipt["transaction"]["message"]["accountKeys"] = [B, A, "account2"]
        receipt["meta"]["postTokenBalances"] = [token(1, "125")]
        receipt["providerEndpoint"] = "https://SECRET.invalid"
        receipt["meta"]["logMessages"] = ["SECRET"]
        rpc = TokenRPC(
            {CLASSIC: [owned(A)], TOKEN_2022: [owned(B, TOKEN_2022)]},
            {A: [SIG]},
            {SIG: receipt},
        )
        result = capture(W, rpc, include_tokens=True, limit=10)
        self.assertEqual(result["coverage"]["discovery"], "wallet-and-current-token-accounts")
        self.assertEqual(result["coverage"]["token_accounts"], sorted([A, B]))
        self.assertEqual(
            [c[1] for c in rpc.calls[:2]],
            [
                [W, {"programId": program}, {"encoding": "jsonParsed", "commitment": "finalized"}]
                for program in (CLASSIC, TOKEN_2022)
            ],
        )
        self.assertTrue(result["coverage"]["reached_history"])
        self.assertEqual(result["coverage"]["pages"], 4)
        self.assertEqual(
            result["coverage"]["sources"],
            [
                {
                    "address": address,
                    "pages": 2 if address == A else 1,
                    "cap_reached": False,
                    "reached_history": True,
                    "partial": False,
                }
                for address in [W] + sorted([A, B])
            ],
        )
        ledger = analyze(result)
        self.assertEqual(
            [(r["asset"], r["amount_base_units"]) for r in ledger["rows"]], [("SPL", "125")]
        )
        self.assertEqual(ledger["wallet_paid_fees_base_units"], "0")
        self.assertNotIn("SECRET", str(result))
        self.assertIn("closed", " ".join(result["warnings"]).lower())
        self.assertIn("transferred", " ".join(result["warnings"]).lower())
        self.assertIn("prior ownership", " ".join(result["warnings"]).lower())
        self.assertEqual(result["coverage"]["partial"], ledger["coverage"]["partial"])

    def test_default_capture_preserves_wallet_only_fetch(self):
        self.assertIsNotNone(importlib.util.find_spec("solana_flow.discovery"))
        capture = importlib.import_module("solana_flow.discovery").capture
        pages = [[{"signature": SIG}], []]
        expected = fetch(W, FakeRPC(pages, {SIG: tx(SIG)}), limit=2)
        client = FakeRPC(pages, {SIG: tx(SIG)})
        actual = capture(W, client, limit=2)
        actual.pop("captured_at")
        expected.pop("captured_at")
        self.assertEqual(actual, expected)
        self.assertFalse(any(method == "getTokenAccountsByOwner" for method, _ in client.calls))
