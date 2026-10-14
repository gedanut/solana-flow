import base64
import hashlib
import json
import re
import runpy
import unittest
from importlib.resources import files
from pathlib import Path

from solana_flow import analyze
from solana_flow.report import html_text


class DemoContractTests(unittest.TestCase):
    def test_packaged_fixture_is_reproducible(self):
        fixture = runpy.run_path(str(Path(__file__).parents[1] / "scripts/generate_fixture.py"))
        actual = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
        self.assertEqual(actual, fixture["fixture"]())

    def test_new_closed_native_accounts_and_conservation(self):
        s = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
        self.assertEqual(s["transactions"][2]["meta"]["preBalances"][2], 0)
        self.assertEqual(s["transactions"][8]["meta"]["postBalances"][2], 0)
        for transaction in s["transactions"]:
            meta = transaction["meta"]
            self.assertEqual(sum(meta["preBalances"]) - sum(meta["postBalances"]), meta["fee"])

    def test_demo_totals_and_csp(self):
        s = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
        result = analyze(s)
        self.assertEqual(result["transaction_count"], 12)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["wallet_paid_fees_base_units"], "55000")
        self.assertEqual(len(result["rows"]), 21)
        self.assertEqual(len(result["assets"]), 4)
        self.assertEqual(
            [a["net"] for a in result["assets"] if a["asset"] == "SPL"],
            ["50.000000", "63.00", "0.250000000"],
        )
        html = html_text(result)
        for tag in ("style", "script"):
            content = re.search(f"<{tag}>(.*?)</{tag}>", html, re.DOTALL).group(1)
            digest = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
            self.assertIn(f"{tag}-src 'sha256-{digest}'", html)
        self.assertIn("connect-src 'none'", html)
