"""Joined HTTP -> worker -> real RPC transport -> SQLite -> query path."""

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from test_discovery import CLASSIC, A, TokenRPC, owned
from test_ledger import W, token, tx
from test_rpc import SIG

from solana_flow.jobs import JobRunner
from solana_flow.server import create_server
from solana_flow.workspace import Workspace


class WorkbenchIntegrationTests(unittest.TestCase):
    def test_malformed_missing_metadata_http_import_is_controlled_and_atomic(self):
        import contextlib
        import io
        from urllib.error import HTTPError

        from test_ledger import snapshot

        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory) / "http.sqlite")
            http = create_server(workspace)
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{http.server_port}"
            try:
                with urlopen(base + "/api/session", timeout=5) as response:
                    token_value = json.load(response)["token"]
                for message in (None, [], "bad", {"accountKeys": [None]}):
                    source = snapshot(tx())
                    source["transactions"][0]["meta"] = None
                    source["transactions"][0]["transaction"]["message"] = message
                    request = Request(
                        base + "/api/import",
                        data=json.dumps({"snapshot": source}).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Solana-Flow-Token": token_value,
                        },
                    )
                    errors = io.StringIO()
                    with self.subTest(message=message), contextlib.redirect_stderr(errors):
                        with self.assertRaises(HTTPError) as caught:
                            urlopen(request, timeout=5)
                        with caught.exception as response:
                            self.assertEqual(response.code, 400)
                            self.assertIn("error", json.load(response))
                    self.assertEqual(errors.getvalue(), "")
                self.assertEqual(workspace.list_wallets(), [])
                self.assertEqual(workspace.list_captures(), [])
            finally:
                http.shutdown()
                http.server_close()
                thread.join(5)

    def test_http_job_captures_passive_token_receipt_and_persists_exact_evidence(self):
        receipt = tx(SIG)
        receipt["transaction"]["message"]["accountKeys"] = ["foreign-payer", A, "other-account"]
        receipt["meta"]["postTokenBalances"] = [token(amount="900719925474099312345")]
        receipt["meta"]["providerExtension"] = "PRIVATE_MARKER"
        backend = TokenRPC({CLASSIC: [owned(A)]}, {A: [SIG]}, {SIG: receipt})
        methods = []

        class RPCHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                methods.append(request["method"])
                result = backend.call(request["method"], request["params"])
                raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        rpc = ThreadingHTTPServer(("127.0.0.1", 0), RPCHandler)
        rpc_thread = threading.Thread(target=rpc.serve_forever, daemon=True)
        rpc_thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "workspace.sqlite"
                workspace = Workspace(path)
                wallet = workspace.add_wallet(
                    W, cluster="devnet", label="Local integration fixture"
                )
                runner = JobRunner(
                    workspace, f"http://127.0.0.1:{rpc.server_port}/?key=ENDPOINT_MARKER"
                )
                http = create_server(workspace, runner=runner)
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{http.server_port}"

                def get(route):
                    with urlopen(base + route, timeout=5) as response:
                        return json.load(response)

                try:
                    session = get("/api/session")
                    self.assertTrue(session["capture_enabled"])
                    request = Request(
                        base + "/api/jobs",
                        data=json.dumps(
                            {"wallet_id": wallet["id"], "limit": 2, "include_tokens": True}
                        ).encode(),
                        headers={
                            "Content-Type": "application/json",
                            "X-Solana-Flow-Token": session["token"],
                        },
                    )
                    with urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, 202)
                        job = json.load(response)
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        job = get(f"/api/jobs/{job['id']}")
                        if job["status"] not in ("queued", "running"):
                            break
                        time.sleep(0.01)
                    self.assertEqual(job["status"], "partial")
                    capture = get(f"/api/captures/{job['capture_id']}")
                    self.assertEqual(capture["transaction_count"], 1)
                    self.assertEqual(capture["row_count"], 1)
                    self.assertEqual(
                        capture["ledger"]["rows"][0]["amount_base_units"], "900719925474099312345"
                    )
                    self.assertEqual(capture["ledger"]["wallet_paid_fees_base_units"], "0")
                    self.assertEqual(capture["snapshot"]["coverage"]["token_accounts"], [A])
                    self.assertEqual(
                        get(f"/api/movements?wallet_id={wallet['id']}&direction=in")["total"], 1
                    )
                    self.assertEqual(
                        get(f"/api/analytics?capture_id={capture['id']}")["assets"][0][
                            "net_base_units"
                        ],
                        "900719925474099312345",
                    )
                    self.assertEqual(methods.count("getTokenAccountsByOwner"), 2)
                    self.assertEqual(methods.count("getTransaction"), 1)
                    self.assertNotIn("MARKER", json.dumps(capture))
                finally:
                    http.shutdown()
                    http.server_close()
                    thread.join(5)
                    runner.close()
                reopened = Workspace(path)
                self.assertEqual(reopened.get_job(job["id"])["status"], "partial")
                self.assertEqual(reopened.get_capture(capture["id"])["ledger"], capture["ledger"])
                self.assertNotIn(b"MARKER", path.read_bytes())
        finally:
            rpc.shutdown()
            rpc.server_close()
            rpc_thread.join(5)
