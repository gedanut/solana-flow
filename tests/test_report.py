import csv
import io
import tempfile
import unittest
from pathlib import Path

from test_ledger import snapshot, token, tx

from solana_flow.ledger import analyze
from solana_flow.report import csv_text, write_report


class ReportTests(unittest.TestCase):
    def test_token_discovery_report_describes_actual_scope(self):
        from test_discovery import TokenRPC

        from solana_flow.discovery import capture
        from solana_flow.ledger import analyze
        from solana_flow.report import html_text

        html = html_text(
            analyze(capture("11111111111111111111111111111111", TokenRPC(), include_tokens=True))
        )
        self.assertIn("currently owned token accounts", html)
        self.assertNotIn("supplied wallet in account keys only", html)

    def test_escape_formula_and_no_synthetic_links(self):
        t = tx('=HYPERLINK("evil")')
        t["meta"]["postTokenBalances"] = [token(mint="<script>alert(1)</script>")]
        result = analyze(snapshot(t))
        with tempfile.TemporaryDirectory() as directory:
            write_report(result, Path(directory))
            html = (Path(directory) / "index.html").read_text()
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("https://explorer.solana.com/tx/", html)
            self.assertIn("SYNTHETIC", html)
            self.assertNotIn("<script src=", html)
            self.assertNotIn("@import", html)
        csv_rows = list(csv.DictReader(io.StringIO(csv_text(result))))
        self.assertTrue(csv_rows[0]["signature"].startswith("'="))
        self.assertEqual(csv_rows[0]["amount_base_units"], "-5000")

    def test_deterministic_outputs(self):
        result = analyze(snapshot(tx()))
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_report(result, Path(a))
            write_report(result, Path(b))
            for name in ("index.html", "ledger.csv", "ledger.json"):
                self.assertEqual((Path(a) / name).read_bytes(), (Path(b) / name).read_bytes())
