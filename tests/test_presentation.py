"""Report presentation is an inspection surface, not a marketing page."""

import json
import unittest
from importlib.resources import files

from solana_flow.ledger import analyze
from solana_flow.report import html_text


class PresentationTests(unittest.TestCase):
    def test_report_names_its_task_and_has_description(self):
        snapshot = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
        page = html_text(analyze(snapshot))
        self.assertIn("Wallet movement report</h1>", page)
        self.assertIn('<meta name="description"', page)
        self.assertNotIn('class="eyebrow"', page)
        self.assertIn("SYNTHETIC", page)
        self.assertIn("Scroll horizontally to inspect all ledger columns.", page)
