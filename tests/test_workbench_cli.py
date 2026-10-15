"""CLI workspace workflows via the installed module entry point."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_ledger import snapshot, tx


class WorkbenchCLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "solana_flow", *map(str, args)],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_version_identifies_second_release(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "solana-flow 2.0.0")

    def test_fetch_can_opt_into_current_token_account_discovery(self):
        from unittest.mock import patch

        from solana_flow.cli import main

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "snapshot.json"
            sample = snapshot(tx())
            with patch("solana_flow.discovery.capture", return_value=sample) as capture:
                result = main(
                    [
                        "fetch",
                        "11111111111111111111111111111111",
                        "--rpc-url",
                        "https://api.devnet.solana.com",
                        "--cluster",
                        "devnet",
                        "--include-tokens",
                        "--output",
                        str(destination),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertTrue(capture.call_args.kwargs["include_tokens"])
            self.assertEqual(
                json.loads(destination.read_text())["transactions"], sample["transactions"]
            )

    def test_malformed_missing_metadata_import_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = snapshot(tx())
            source["transactions"][0]["meta"] = None
            source["transactions"][0]["transaction"]["message"] = None
            file = root / "malformed.json"
            file.write_text(json.dumps(source))
            result = self.run_cli("import", file, "--database", root / "workspace.sqlite")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("solana-flow:", result.stderr)

    def test_import_query_and_compare_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "workspace.sqlite"
            source = root / "capture.json"
            source.write_text(json.dumps(snapshot(tx())), encoding="utf-8")
            result = self.run_cli("import", source, "--database", database, "--label", "baseline")
            self.assertEqual(result.returncode, 0, result.stderr)
            first = json.loads(result.stdout)
            result = self.run_cli("query", "--database", database, "--direction", "out")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["total"], 1)
            self.assertEqual(data["rows"][0]["amount_base_units"], "-5000")
            result = self.run_cli("compare", first["id"], first["id"], "--database", database)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["added_signatures"], [])
            self.assertEqual(os.path.isfile(database), True)
