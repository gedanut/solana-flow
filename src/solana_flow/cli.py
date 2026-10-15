"""Command line interface; ordinary input failures never expose tracebacks or URLs."""

import argparse
import json
import os
import sqlite3
import sys
from importlib.resources import files
from pathlib import Path

from .jsonio import loads as strict_loads
from .ledger import ValidationError, analyze
from .report import write_report
from .rpc import RPCClient, RPCError, fetch

MAX_SNAPSHOT = 128 * 1024 * 1024


def load_snapshot(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_SNAPSHOT + 1)
    if len(raw) > MAX_SNAPSHOT:
        raise ValidationError("Snapshot exceeds 128 MiB size limit.")
    try:
        return strict_loads(raw)
    except (UnicodeError, ValueError, RecursionError):
        raise ValidationError("Invalid snapshot JSON.") from None


class _SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        # Applies to subparsers too; argparse diagnostics can echo endpoint secrets.
        self.exit(1, "solana-flow: invalid command arguments; use --help.\n")


def _parser():
    parser = _SafeParser(
        prog="solana-flow",
        description=(
            "Read-only Solana net balance analytics. No signing, prices or payment classification."
        ),
    )
    parser.add_argument("--version", action="version", version="solana-flow 2.0.1")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate an offline SYNTHETIC demonstration")
    demo.add_argument("--output", type=Path, required=True, help="Report directory")
    capture = sub.add_parser(
        "fetch", help="Capture wallet-address references (not complete history)"
    )
    capture.add_argument("address")
    capture.add_argument(
        "--include-tokens",
        action="store_true",
        help="Discover current classic SPL and Token-2022 account references",
    )
    capture.add_argument("--rpc-url", required=True, help="HTTP(S) RPC endpoint; never persisted")
    capture.add_argument(
        "--limit", type=int, default=100, help="Signature cap, 1–10000 (default 100)"
    )
    capture.add_argument(
        "--cluster",
        choices=("mainnet-beta", "devnet", "testnet", "custom"),
        default="custom",
        help="Explicit label; endpoint identity is not inferred",
    )
    capture.add_argument("--output", type=Path, required=True, help="Snapshot JSON filename")
    replay = sub.add_parser("analyze", help="Analyze a schema-v1 snapshot offline")
    replay.add_argument("snapshot", type=Path)
    replay.add_argument("--output", type=Path, required=True, help="Report directory")
    ingest = sub.add_parser("import", help="Validate and atomically import a snapshot into SQLite")
    ingest.add_argument("snapshot", type=Path)
    ingest.add_argument("--label", default="", help="Capture label")
    query = sub.add_parser(
        "query", help="Query persistent movements; latest capture per wallet by default"
    )
    query.add_argument("--wallet-id", type=int)
    query.add_argument("--capture-id", type=int)
    query.add_argument("--asset", help="SOL or exact mint identifier")
    query.add_argument("--direction", choices=("in", "out", "zero"))
    query.add_argument("--status", choices=("success", "failed"))
    query.add_argument("--search", default="")
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--offset", type=int, default=0)
    compare = sub.add_parser("compare", help="Compare two immutable same-wallet captures")
    compare.add_argument("before", type=int)
    compare.add_argument("after", type=int)
    serve = sub.add_parser("serve", help="Run the local-first investigation workbench on 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--demo", action="store_true", help="Seed deterministic SYNTHETIC examples")
    serve.add_argument(
        "--rpc-url", help="Optional capture endpoint; prefer SOLANA_FLOW_RPC_URL env"
    )
    for command in (ingest, query, compare, serve):
        command.add_argument(
            "--database", type=Path, required=True, help="Persistent SQLite workspace filename"
        )
    return parser


def _workspace_command(args):
    from .workspace import Workspace

    workspace = Workspace(args.database)
    if args.command == "import":
        result = workspace.import_snapshot(load_snapshot(args.snapshot), label=args.label)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 2 if result["partial"] else 0
    if args.command == "query":
        filters = {
            key: getattr(args, key)
            for key in (
                "wallet_id",
                "capture_id",
                "asset",
                "direction",
                "status",
                "search",
                "limit",
                "offset",
            )
        }
        print(json.dumps(workspace.movements(**filters), ensure_ascii=True, allow_nan=False))
        return 0
    if args.command == "compare":
        print(
            json.dumps(
                workspace.compare_captures(args.before, args.after),
                ensure_ascii=True,
                allow_nan=False,
            )
        )
        return 0
    from .jobs import JobRunner
    from .server import create_server

    if args.demo:
        from .samples import seed_workspace

        seed_workspace(workspace)
    runner = JobRunner(workspace, args.rpc_url or os.environ.get("SOLANA_FLOW_RPC_URL"))
    http = None
    try:
        http = create_server(workspace, port=args.port, runner=runner)
        print(f"Solana Flow workbench: http://127.0.0.1:{http.server_port}/", flush=True)
        print(
            "Local-only. Captures are scoped evidence, never complete wallet history.", flush=True
        )
        http.serve_forever(poll_interval=0.2)
    finally:
        if http is not None:
            http.server_close()
        runner.close(wait=False)
    return 0


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command in ("import", "query", "compare", "serve"):
            return _workspace_command(args)
        if args.command == "fetch":
            client = RPCClient(args.rpc_url)
            if args.include_tokens:
                from .discovery import capture

                snapshot = capture(
                    args.address,
                    client,
                    limit=args.limit,
                    cluster=args.cluster,
                    include_tokens=True,
                )
            else:
                snapshot = fetch(args.address, client, limit=args.limit, cluster=args.cluster)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(snapshot, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8"
            )
            partial = snapshot["coverage"]["partial"]
            print(
                "Snapshot saved. "
                + (
                    "PARTIAL capture; inspect coverage and warnings."
                    if partial
                    else "Scoped capture; not complete wallet history."
                )
            )
            return 2 if partial else 0
        if args.command == "demo":
            snapshot = json.loads(
                files("solana_flow").joinpath("data/demo.json").read_text(encoding="utf-8")
            )
        else:
            snapshot = load_snapshot(args.snapshot)
        result = analyze(snapshot)
        write_report(result, args.output)
        if args.command == "demo":
            (args.output / "snapshot.json").write_text(
                json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
            )
        label = "SYNTHETIC " if result["synthetic"] else ""
        print(
            f"{label}Report written: index.html, ledger.csv, ledger.json. "
            f"{result['transaction_count']} transactions; {len(result['rows'])} ledger rows."
        )
        if result["coverage"]["partial"]:
            print("PARTIAL data: inspect the report’s coverage details.")
            return 2
        return 0
    except (ValidationError, RPCError) as exc:
        print(f"solana-flow: {exc}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, sqlite3.Error):
        print("solana-flow: unable to read or write the requested files.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("solana-flow: interrupted.", file=sys.stderr)
        return 130
