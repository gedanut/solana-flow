"""Local HTTP integration. No public endpoints or credentials are used."""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from test_ledger import W, tx
from test_rpc import SIG

from solana_flow.ledger import analyze
from solana_flow.rpc import RPCClient, RPCError, _NoRedirect, fetch


class TransportTests(unittest.TestCase):
    def test_redirect_refused_without_forwarding(self):
        with self.assertRaises(RPCError):
            _NoRedirect().redirect_request(None, None, 302, "secret", {}, "https://secret")

    def test_local_http_rate_limit_capture(self):
        requests = []

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
                method = request["method"]
                if method == "getTransaction":
                    result = tx(SIG)
                elif "before" in request["params"][1]:
                    result = []
                else:
                    result = [{"signature": SIG}]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode())

        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except OSError:
            if os.environ.get("SOLANA_FLOW_REQUIRE_LOCAL_HTTP") == "1":
                raise
            self.skipTest("Local socket binding is unavailable in this environment")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("solana_flow.rpc.time.sleep"):
                snapshot = fetch(W, RPCClient(f"http://127.0.0.1:{server.server_port}"), limit=2)
            result = analyze(snapshot)
            self.assertEqual(result["transaction_count"], 1)
            self.assertTrue(result["coverage"]["reached_history"])
            self.assertFalse(result["coverage"]["partial"])
            self.assertEqual(len(requests), 4)
            self.assertEqual(requests[2]["params"][1]["encoding"], "jsonParsed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
