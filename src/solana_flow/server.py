"""Loopback-only workbench HTTP API. Not a public/multi-user web server."""

import json
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from .jsonio import loads as strict_loads
from .ledger import ValidationError, require
from .report import csv_text

MAX_BODY = 16 * 1024 * 1024
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def create_server(workspace, *, port=0, host="127.0.0.1", runner=None):
    """Bind only IPv4 loopback, with per-process same-origin mutation protection."""
    require(host == "127.0.0.1", "Workbench only binds to 127.0.0.1.")
    require(type(port) is int and 0 <= port <= 65535, "Invalid HTTP port.")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SolanaFlow/2"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            pass  # No request paths, activity or endpoint diagnostics in logs.

        def respond(
            self, payload, status=200, content_type="application/json; charset=utf-8", filename=None
        ):
            raw = (
                payload
                if isinstance(payload, bytes)
                else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def guard(self, mutate=False):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            if (
                host not in hosts
                or len(self.headers.get_all("Host", [])) != 1
                or (origin is not None and origin != f"http://{host}")
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                self.respond({"error": "Only same-origin loopback requests are accepted."}, 403)
                return False
            supplied_token = self.headers.get("X-Solana-Flow-Token", "")
            if mutate and (
                not supplied_token.isascii() or not secrets.compare_digest(supplied_token, token)
            ):
                self.respond({"error": "Session token required; reload the workbench."}, 403)
                return False
            return True

        def route(self):
            parts = urlsplit(self.path)
            require(
                not parts.scheme and not parts.netloc and not parts.fragment,
                "Invalid request target.",
            )
            query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=16)
            require(all(len(v) == 1 for v in query.values()), "Duplicate query parameters.")
            return parts.path, {k: v[0] for k, v in query.items()}

        def body(self):
            if self.headers.get_content_type() != "application/json":
                self.respond({"error": "Use application/json."}, 415)
                return None
            require(not self.headers.get("Transfer-Encoding"), "Chunked bodies are not accepted.")
            lengths = self.headers.get_all("Content-Length", [])
            require(
                len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit(),
                "Content-Length required.",
            )
            size = int(lengths[0])
            require(0 < size <= MAX_BODY, "JSON body must be between 1 byte and 16 MiB.")
            raw = self.rfile.read(size)
            require(len(raw) == size, "Incomplete request body.")
            try:
                payload = strict_loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                raise ValidationError("Invalid JSON body.") from None
            require(isinstance(payload, dict), "JSON body must be an object.")
            return payload

        def query_args(self, query, allowed):
            require(set(query) <= set(allowed), "Unknown query parameter.")
            converted = dict(query)
            for key in ("wallet_id", "capture_id", "before", "after", "limit", "offset"):
                if key in converted:
                    value = converted[key]
                    require(
                        value.isascii() and value.isdigit() and len(value) <= 10,
                        "Invalid integer parameter.",
                    )
                    converted[key] = int(value)
                    require(
                        converted[key] >= (0 if key == "offset" else 1),
                        "Invalid integer parameter.",
                    )
            return converted

        def get_route(self, path, query):
            assets = {
                "/": ("workbench.html", "text/html; charset=utf-8"),
                "/index.html": ("workbench.html", "text/html; charset=utf-8"),
                "/workbench.js": ("workbench.js", "text/javascript; charset=utf-8"),
                "/workbench.css": ("workbench.css", "text/css; charset=utf-8"),
            }
            if path in assets:
                self.query_args(query, ())
                name, content_type = assets[path]
                self.respond(
                    files("solana_flow").joinpath("assets", name).read_bytes(),
                    content_type=content_type,
                )
            elif path == "/api/session":
                self.query_args(query, ())
                self.respond(
                    {
                        "token": token,
                        "mode": "local",
                        "version": "2.0.1",
                        "capture_enabled": runner is not None and runner.enabled,
                    }
                )
            elif path == "/api/wallets":
                self.query_args(query, ())
                self.respond({"wallets": workspace.list_wallets()})
            elif path == "/api/captures":
                self.respond(
                    {"captures": workspace.list_captures(**self.query_args(query, ("wallet_id",)))}
                )
            elif path.startswith("/api/captures/"):
                self.query_args(query, ())
                ident = self.query_args(
                    {"capture_id": path.removeprefix("/api/captures/")}, ("capture_id",)
                )
                self.respond(workspace.get_capture(ident["capture_id"]))
            elif path == "/api/movements":
                self.respond(
                    workspace.movements(
                        **self.query_args(
                            query,
                            (
                                "wallet_id",
                                "capture_id",
                                "asset",
                                "direction",
                                "status",
                                "search",
                                "limit",
                                "offset",
                            ),
                        )
                    )
                )
            elif path == "/api/analytics":
                self.respond(
                    workspace.analytics(**self.query_args(query, ("wallet_id", "capture_id")))
                )
            elif path == "/api/compare":
                args = self.query_args(query, ("before", "after"))
                require(
                    set(args) == {"before", "after"}, "Both comparison capture IDs are required."
                )
                self.respond(workspace.compare_captures(args["before"], args["after"]))
            elif path == "/api/jobs":
                self.query_args(query, ())
                self.respond({"jobs": workspace.list_jobs()})
            elif path.startswith("/api/jobs/"):
                self.query_args(query, ())
                ident = self.query_args(
                    {"capture_id": path.removeprefix("/api/jobs/")}, ("capture_id",)
                )
                self.respond(workspace.get_job(ident["capture_id"]))
            elif path == "/api/export":
                args = self.query_args(query, ("capture_id", "format"))
                require(
                    "capture_id" in args and args.get("format", "json") in ("json", "csv"),
                    "Invalid export request.",
                )
                ledger = workspace.get_capture(args["capture_id"])["ledger"]
                if args.get("format") == "csv":
                    self.respond(
                        csv_text(ledger).encode(),
                        content_type="text/csv; charset=utf-8",
                        filename="ledger.csv",
                    )
                else:
                    self.respond(ledger, filename="ledger.json")
            else:
                self.respond({"error": "Not found."}, 404)

        def do_GET(self):
            if not self.guard():
                return
            try:
                self.get_route(*self.route())
            except (ValidationError, ValueError, TypeError):
                self.respond({"error": "Invalid request parameters or unknown record."}, 400)
            except (sqlite3.Error, OSError):
                self.respond({"error": "Workspace unavailable; check database access."}, 503)

        def do_POST(self):
            if not self.guard(mutate=True):
                return
            try:
                path, query = self.route()
                require(not query, "POST query parameters are not supported.")
                payload = self.body()
                if payload is None:
                    return
                if path == "/api/wallets":
                    require(
                        set(payload) <= {"address", "cluster", "label"} and "address" in payload,
                        "Invalid wallet fields.",
                    )
                    self.respond(workspace.add_wallet(**payload), 201)
                elif path == "/api/import":
                    require(
                        set(payload) <= {"snapshot", "label"} and "snapshot" in payload,
                        "Invalid import fields.",
                    )
                    self.respond(workspace.import_snapshot(**payload), 201)
                elif path == "/api/jobs":
                    if runner is None or not runner.enabled:
                        self.respond(
                            {
                                "error": "Capture unavailable; start serve with --rpc-url or SOLANA_FLOW_RPC_URL."
                            },
                            409,
                        )
                        return
                    require(
                        set(payload) <= {"wallet_id", "limit", "include_tokens"}
                        and "wallet_id" in payload,
                        "Invalid job fields.",
                    )
                    self.respond(runner.submit(**payload), 202)
                else:
                    self.respond({"error": "Not found."}, 404)
            except (ValidationError, ValueError, TypeError):
                self.respond(
                    {"error": "Invalid JSON body, request fields, or unavailable job capacity."},
                    400,
                )
            except (sqlite3.Error, OSError):
                self.respond({"error": "Workspace unavailable; check database access."}, 503)

    return ThreadingHTTPServer((host, port), Handler)
