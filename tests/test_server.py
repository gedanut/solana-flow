"""Real loopback HTTP boundary tests, no browser or RPC required."""

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from solana_flow import server


class EmptyWorkspace:
    def list_wallets(self):
        return []

    def add_wallet(self, **kwargs):
        return dict(kwargs, id=1)

    def import_snapshot(self, snapshot, label=""):
        return {"id": 2, "label": label, "partial": False}

    def list_captures(self, wallet_id=None):
        return [{"id": 2, "wallet_id": wallet_id}]

    def get_capture(self, capture_id):
        return {"id": capture_id, "snapshot": {}, "ledger": {"rows": []}}

    def movements(self, **kwargs):
        return {"rows": [], "total": 0, **kwargs}

    def analytics(self, **kwargs):
        return {"assets": [], **kwargs}

    def compare_captures(self, before, after):
        return {"added_signatures": [], "before": before, "after": after}

    def list_jobs(self):
        return []

    def get_job(self, job_id):
        return {"id": job_id}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.http = server.create_server(EmptyWorkspace(), port=0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(5)

    def request(self, path, *, data=None, headers=None):
        req = Request(self.url + path, data=data, headers=headers or {})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, dict(response.headers), response.read()

    def test_session_and_wallets(self):
        status, headers, body = self.request("/api/session")
        self.assertEqual(status, 200)
        session = json.loads(body)
        self.assertEqual(session["mode"], "local")
        self.assertGreaterEqual(len(session["token"]), 32)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(self.request("/api/wallets")[2]), {"wallets": []})

    def test_non_ascii_mutation_token_is_refused_without_thread_failure(self):
        import contextlib
        import io

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status, _, _ = self.request(
                "/api/wallets", data=b"{}", headers={"X-Solana-Flow-Token": "\xe9"}
            )
        self.assertEqual(status, 403)
        self.assertEqual(errors.getvalue(), "")

    def test_rejects_foreign_host_and_origin(self):
        for headers in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/session", headers=headers)[0], 403)

    def test_post_requires_token_and_json(self):
        self.assertEqual(self.request("/api/wallets", data=b"{}")[0], 403)
        token = json.loads(self.request("/api/session")[2])["token"]
        headers = {"X-Solana-Flow-Token": token, "Content-Type": "application/json"}
        for body in (b'{"address":1,"address":2}', b'{"address":NaN}', b"[]", b"{"):
            with self.subTest(body=body):
                self.assertEqual(self.request("/api/wallets", data=body, headers=headers)[0], 400)
        self.assertEqual(
            self.request("/api/wallets", data=b"{}", headers={"X-Solana-Flow-Token": token})[0], 415
        )

    def test_packaged_workbench_assets_are_served_with_csp(self):
        self.assertTrue(
            b'rel="icon"' in self.request("/")[2], "Application must not request a missing favicon."
        )
        for path, content_type, marker in (
            ("/", "text/html", b"Investigation"),
            ("/workbench.js", "text/javascript", b"use strict"),
            ("/workbench.css", "text/css", b"--"),
        ):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn(content_type, headers["Content-Type"])
                self.assertIn(marker, body)
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_routes_preserve_scope_and_exports(self):
        cases = {
            "/api/captures?wallet_id=3": {"captures": [{"id": 2, "wallet_id": 3}]},
            "/api/captures/2": {"id": 2, "snapshot": {}, "ledger": {"rows": []}},
            "/api/analytics?capture_id=2": {"assets": [], "capture_id": 2},
            "/api/compare?before=1&after=2": {"added_signatures": [], "before": 1, "after": 2},
            "/api/jobs": {"jobs": []},
            "/api/jobs/1": {"id": 1},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), expected)
        status, _, body = self.request("/api/movements?capture_id=2&search=%25&limit=10&offset=1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["search"], "%")
        status, headers, body = self.request("/api/export?capture_id=2&format=csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertTrue(body.startswith(b"signature,"))

    def test_mutations_and_query_validation(self):
        token = json.loads(self.request("/api/session")[2])["token"]
        headers = {"X-Solana-Flow-Token": token, "Content-Type": "application/json"}
        status, _, body = self.request(
            "/api/wallets",
            data=json.dumps({"address": "a", "cluster": "devnet", "label": "x"}).encode(),
            headers=headers,
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["id"], 1)
        status, _, body = self.request(
            "/api/import", data=b'{"snapshot":{},"label":"test"}', headers=headers
        )
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["id"], 2)
        for path in (
            "/api/captures?wallet_id=-1",
            "/api/movements?limit=1&limit=2",
            "/api/captures?secret=x",
            "/api/compare?before=1",
            "/api/export?capture_id=2&format=exe",
        ):
            self.assertEqual(self.request(path)[0], 400, path)
        status, _, _ = self.request("/api/jobs", data=b'{"wallet_id":1}', headers=headers)
        self.assertEqual(status, 409)

    def test_no_arbitrary_file_or_unbounded_bind(self):
        for path in ("/../pyproject.toml", "/.git/config", "/api/session?token=secret"):
            self.assertIn(self.request(path)[0], (400, 404))
        with self.assertRaises(ValueError):
            server.create_server(EmptyWorkspace(), host="0.0.0.0")
