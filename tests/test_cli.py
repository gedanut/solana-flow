import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from solana_flow.cli import main


class CLITests(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_demo_and_analyze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, out, err = self.run_cli(["demo", "--output", str(root / "demo")])
            self.assertEqual(code, 0, err)
            self.assertIn("SYNTHETIC", out)
            self.assertTrue((root / "demo/index.html").exists())
            self.assertTrue((root / "demo/snapshot.json").exists())
            code, _, err = self.run_cli(
                ["analyze", str(root / "demo/snapshot.json"), "--output", str(root / "replay")]
            )
            self.assertIn(code, (0, 2), err)
            self.assertEqual(
                (root / "demo/ledger.json").read_bytes(), (root / "replay/ledger.json").read_bytes()
            )

    def test_bad_input_no_traceback_or_path(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / "bad.json"
            for text in ['{"x": 1, "x": 2}', '{"bad":NaN}', "{}", "[]", "{"]:
                f.write_text(text)
                code, _, err = self.run_cli(["analyze", str(f), "--output", directory])
                self.assertEqual(code, 1)
                self.assertNotIn("Traceback", err)
                self.assertNotIn(directory, err)
            code, _, err = self.run_cli(["analyze", str(f / "missing"), "--output", directory])
            self.assertEqual(code, 1)

    @patch("solana_flow.cli.fetch")
    def test_partial_fetch_exit(self, fetch):
        from test_ledger import snapshot

        s = snapshot()
        s["coverage"]["partial"] = True
        fetch.return_value = s
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            code, _, err = self.run_cli(
                [
                    "fetch",
                    s["wallet"],
                    "--rpc-url",
                    "https://example.invalid",
                    "--output",
                    str(path),
                ]
            )
            self.assertEqual(code, 2, err)
            self.assertTrue(json.loads(path.read_text())["coverage"]["partial"])
