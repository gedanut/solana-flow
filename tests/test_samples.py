"""Synthetic workbench examples and reproducible static publishing."""

import json
import unittest
from collections import defaultdict
from importlib.resources import files

from solana_flow.ledger import analyze
from solana_flow.rpc import validate_address


class SampleTests(unittest.TestCase):
    def test_samples_are_independent_valid_synthetic_multiwallet_captures(self):
        from solana_flow.samples import sample_snapshots

        packaged = files("solana_flow").joinpath("data/demo.json").read_text()
        samples = sample_snapshots()
        self.assertEqual(samples, sample_snapshots())
        self.assertEqual(len(samples), 4)
        by_wallet = defaultdict(list)
        for label, snapshot in samples:
            self.assertIn("Synthetic", label)
            validate_address(snapshot["wallet"])
            self.assertEqual(snapshot["cluster"], "synthetic")
            self.assertIs(snapshot["synthetic"], True)
            ledger = analyze(snapshot)
            self.assertGreater(len(ledger["rows"]), 0)
            self.assertTrue(all(row["synthetic"] for row in ledger["rows"]))
            by_wallet[snapshot["wallet"]].append(snapshot)
            self.assertNotIn("https://", json.dumps(snapshot))
            self.assertNotIn("SyntheticWallet", json.dumps(snapshot))
        self.assertEqual(sorted(map(len, by_wallet.values())), [2, 2])
        samples[0][1]["transactions"][0]["meta"]["fee"] = 999
        self.assertNotEqual(samples, sample_snapshots())
        self.assertEqual(files("solana_flow").joinpath("data/demo.json").read_text(), packaged)

    def test_overlapping_windows_show_added_removed_corrected_evidence_and_uncertainty(self):
        from solana_flow.samples import sample_snapshots

        by_wallet = defaultdict(list)
        all_signatures = []
        for _, snapshot in sample_snapshots():
            by_wallet[snapshot["wallet"]].append(snapshot)
        for before, after in by_wallet.values():
            old = {tx["transaction"]["signatures"][0]: tx for tx in before["transactions"]}
            new = {tx["transaction"]["signatures"][0]: tx for tx in after["transactions"]}
            self.assertTrue(old.keys() & new.keys())
            self.assertTrue(new.keys() - old.keys())
            self.assertTrue(old.keys() - new.keys())
            changed = [key for key in old.keys() & new.keys() if old[key] != new[key]]
            self.assertTrue(changed, "a repeated signature has corrected synthetic evidence")
            self.assertNotEqual(analyze(before)["assets"], analyze(after)["assets"])
            ledger = analyze(after)
            self.assertTrue(ledger["coverage"]["partial"])
            self.assertTrue(ledger["unavailable_signatures"])
            self.assertIn("Missing metadata", {gap["reason"] for gap in ledger["gaps"]})
            self.assertTrue(any("Unknown token owner" in gap["reason"] for gap in ledger["gaps"]))
            self.assertTrue(any(row["time"] is None for row in ledger["rows"]))
            self.assertGreater(
                len({row["time"] // 86400 for row in ledger["rows"] if row["time"] is not None}), 1
            )
            self.assertLess(before["captured_at"], after["captured_at"])
            all_signatures.append(set(old) | set(new))
            for snapshot in (before, after):
                for tx in snapshot["transactions"]:
                    meta = tx["meta"]
                    if meta is not None:
                        self.assertEqual(
                            sum(meta["preBalances"]) - sum(meta["postBalances"]), meta["fee"]
                        )
        self.assertFalse(all_signatures[0] & all_signatures[1])

    def test_seed_is_idempotent_persistent_and_uses_analyzer_ledgers(self):
        import tempfile
        from pathlib import Path

        from solana_flow.samples import sample_snapshots, seed_workspace
        from solana_flow.workspace import Workspace

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.sqlite3"
            workspace = Workspace(path)
            metadata = seed_workspace(workspace)
            self.assertEqual(len(workspace.list_wallets()), 2)
            self.assertEqual(len(metadata), 4)
            self.assertTrue(
                all(wallet["label"].startswith("Synthetic") for wallet in workspace.list_wallets())
            )
            self.assertEqual(seed_workspace(Workspace(path)), metadata)
            self.assertEqual(len(workspace.list_captures()), 4)
            for capture, (label, snapshot) in zip(metadata, sample_snapshots(), strict=True):
                stored = workspace.get_capture(capture["id"])
                self.assertEqual(stored["label"], label)
                self.assertEqual(stored["ledger"], analyze(snapshot))
                self.assertEqual(capture["row_count"], len(stored["ledger"]["rows"]))

    def test_static_data_is_byte_deterministic_and_recomputed_from_workspace(self):
        import runpy
        from pathlib import Path
        from unittest.mock import patch

        generator = Path(__file__).parents[1] / "scripts/generate_explorer.py"
        self.assertTrue(generator.is_file(), "static explorer generator is missing")
        build = runpy.run_path(str(generator))["build_demo_data"]
        with patch("solana_flow.workspace._now", return_value="2099-01-01T00:00:00Z"):
            first = build()
        with patch("solana_flow.workspace._now", return_value="2100-01-01T00:00:00Z"):
            second = build()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(set(first), {"wallets", "captures", "jobs"})
        self.assertEqual(first["jobs"], [])
        self.assertEqual(len(first["wallets"]), 2)
        self.assertEqual(len(first["captures"]), 4)
        for capture in first["captures"]:
            self.assertEqual(capture["ledger"], analyze(capture["snapshot"]))
            self.assertEqual(capture["imported_at"], capture["captured_at"])
        self.assertNotIn("2099-", json.dumps(first))
        self.assertNotIn("2100-", json.dumps(second))

    def test_generator_cli_copies_assets_and_repeats_identical_output_without_install(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        script = Path(__file__).parents[1] / "scripts/generate_explorer.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "explorer"
            env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
            command = [sys.executable, str(script), "--output", str(output)]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {"index.html", "workbench.css", "workbench.js", "demo-data.json"}
            self.assertTrue(output.is_dir(), "generator must write its output")
            self.assertEqual({path.name for path in output.iterdir()}, expected)
            first = {path.name: path.read_bytes() for path in output.iterdir()}
            self.assertRegex(first["index.html"].decode(), r'<html[^>]*data-mode="static"')
            for asset in ("workbench.css", "workbench.js"):
                self.assertEqual(
                    first[asset], files("solana_flow").joinpath("assets", asset).read_bytes()
                )
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first, {path.name: path.read_bytes() for path in output.iterdir()})


if __name__ == "__main__":
    unittest.main()
