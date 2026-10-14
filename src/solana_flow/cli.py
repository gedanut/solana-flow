"""Command line interface; ordinary input failures never expose tracebacks or URLs."""

import argparse
import json
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
    parser.add_argument("--version", action="version", version="solana-flow 1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate an offline SYNTHETIC demonstration")
    demo.add_argument("--output", type=Path, required=True, help="Report directory")
    capture = sub.add_parser(
        "fetch", help="Capture wallet-address references (not complete history)"
    )
    capture.add_argument("address")
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
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "fetch":
            snapshot = fetch(
                args.address, RPCClient(args.rpc_url), limit=args.limit, cluster=args.cluster
            )
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
    except (OSError, UnicodeError):
        print("solana-flow: unable to read or write the requested files.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("solana-flow: interrupted.", file=sys.stderr)
        return 130
