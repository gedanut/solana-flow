"""Real SQLite integration tests; each feature added through a red/green cycle."""

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from test_ledger import M, snapshot, token, tx

from solana_flow.ledger import ValidationError, analyze

W = "11111111111111111111111111111111"


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "investigation.sqlite3"

    def workspace(self):
        from solana_flow.workspace import Workspace

        return Workspace(self.path)

    def test_analytics_never_combines_different_cluster_assets(self):
        workspace = self.workspace()
        records = []
        for cluster in ("devnet", "mainnet-beta"):
            source = snapshot(tx())
            source.update(cluster=cluster, synthetic=False)
            records.append(workspace.import_snapshot(source))
        with self.assertRaisesRegex(ValidationError, "cluster"):
            workspace.analytics()
        for capture in records:
            self.assertEqual(
                workspace.analytics(capture_id=capture["id"])["assets"][0]["net_base_units"],
                "-5000",
            )

    def test_missing_metadata_does_not_bypass_transaction_shape_validation(self):
        workspace = self.workspace()
        for message in (
            None,
            [],
            "bad",
            {"accountKeys": None},
            {"accountKeys": [None]},
            {"accountKeys": [{"wrong": "key"}]},
        ):
            source = snapshot(tx())
            source["transactions"][0]["meta"] = None
            source["transactions"][0]["transaction"]["message"] = message
            with self.subTest(message=message), self.assertRaises(ValidationError):
                workspace.import_snapshot(source)
        self.assertEqual(workspace.list_wallets(), [])
        self.assertEqual(workspace.list_captures(), [])
        source = snapshot(tx())
        source["transactions"][0]["meta"] = None
        saved = workspace.import_snapshot(source)
        self.assertTrue(saved["partial"])
        self.assertEqual(saved["row_count"], 0)

    def test_wallet_survives_reopen_and_schema_is_initialized(self):
        workspace = self.workspace()
        wallet = workspace.add_wallet(W, label="Treasury")
        self.assertEqual(wallet["address"], W)
        self.assertEqual(wallet["cluster"], "custom")
        self.assertEqual(wallet["label"], "Treasury")
        self.assertTrue(wallet["created_at"])
        self.assertEqual(self.workspace().get_wallet(wallet["id"]), wallet)
        self.assertEqual(self.workspace().list_wallets(), [wallet])
        self.assertEqual(workspace.add_wallet(W, label="not overwritten"), wallet)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        with self.assertRaises(ValidationError):
            workspace.get_wallet(999)

    def test_capture_import_is_immutable_deduplicated_and_persistent(self):
        workspace = self.workspace()
        source = snapshot(tx())
        capture = workspace.import_snapshot(source, label="Evidence one")
        self.assertEqual(capture["transaction_count"], 1)
        self.assertEqual(capture["row_count"], 1)
        self.assertFalse(capture["partial"])
        self.assertTrue(capture["synthetic"])
        self.assertEqual(workspace.get_wallet(capture["wallet_id"])["cluster"], "synthetic")
        self.assertEqual(workspace.import_snapshot(source, label="ignored"), capture)
        source["warnings"].append("caller mutation")
        stored = self.workspace().get_capture(capture["id"])
        self.assertEqual(stored["snapshot"], snapshot(tx()))
        self.assertEqual(stored["ledger"], analyze(snapshot(tx())))
        self.assertEqual(stored["label"], "Evidence one")
        self.assertEqual(self.workspace().list_captures(), [capture])
        self.assertEqual(workspace.list_captures(capture["wallet_id"]), [capture])
        self.assertNotIn("snapshot", capture)
        self.assertNotIn("ledger", capture)
        with self.assertRaises(ValidationError):
            workspace.get_capture(999)

    def test_import_normalizes_provider_extensions_and_fingerprints_canonical_evidence(self):
        workspace = self.workspace()
        clean = snapshot(tx())
        source = copy.deepcopy(clean)
        source["endpoint"] = "https://secret.example/?api-key=NEVER-PERSIST"
        source["transactions"][0]["provider_url"] = source["endpoint"]
        source["transactions"][0]["meta"]["logMessages"] = [source["endpoint"]]
        capture = workspace.import_snapshot(source)
        stored = workspace.get_capture(capture["id"])
        self.assertEqual(stored["snapshot"], clean)
        canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False)
        self.assertEqual(capture["fingerprint"], hashlib.sha256(canonical.encode()).hexdigest())
        self.assertEqual(workspace.import_snapshot(clean)["id"], capture["id"])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn("NEVER-PERSIST", " ".join(db.iterdump()))

    def test_invalid_import_does_not_create_wallet_or_capture(self):
        workspace = self.workspace()
        broken = snapshot(tx())
        broken["transactions"][0]["meta"]["postBalances"] = []
        with self.assertRaises(ValidationError):
            workspace.import_snapshot(broken)
        self.assertEqual(workspace.list_wallets(), [])
        self.assertEqual(workspace.list_captures(), [])
        conflict = tx()
        conflict["slot"] += 1
        with self.assertRaises(ValidationError):
            workspace.import_snapshot(snapshot(tx(), conflict))
        self.assertEqual(workspace.list_wallets(), [])

    def test_movements_use_latest_capture_per_wallet_and_filter_paginate_safely(self):
        workspace = self.workspace()
        old = workspace.import_snapshot(snapshot(tx("old")))
        incoming = tx("needle%_literal")
        incoming["slot"] = 8
        incoming["meta"]["postBalances"][0] = 20000
        latest = workspace.import_snapshot(snapshot(tx("outgoing"), incoming))
        alternate = snapshot(tx("other-cluster"))
        alternate.update(cluster="devnet", synthetic=False)
        other = workspace.import_snapshot(alternate)
        result = workspace.movements(limit=1, offset=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["limit"], 1)
        self.assertEqual(result["offset"], 1)
        self.assertEqual(len(result["rows"]), 1)
        rows = workspace.movements(wallet_id=latest["wallet_id"])["rows"]
        self.assertEqual({r["signature"] for r in rows}, {"outgoing", "needle%_literal"})
        self.assertTrue(all(r["capture_id"] == latest["id"] for r in rows))
        self.assertEqual(workspace.movements(capture_id=old["id"])["total"], 1)
        filtered = workspace.movements(
            asset="SOL", direction="in", status="success", search="%_literal"
        )
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["rows"][0]["amount_base_units"], "10000")
        self.assertEqual(workspace.movements(search="' OR 1=1; --")["total"], 0)
        self.assertEqual(workspace.movements(asset="' OR 1=1; --")["total"], 0)
        self.assertEqual(workspace.movements(offset=100)["rows"], [])
        with self.assertRaises(ValidationError):
            workspace.movements(wallet_id=other["wallet_id"], capture_id=old["id"])

    def test_movement_bounds_and_filter_types_are_strict(self):
        workspace = self.workspace()
        for kwargs in (
            {"limit": 0},
            {"limit": 501},
            {"limit": True},
            {"limit": "1"},
            {"offset": -1},
            {"offset": 1.5},
            {"offset": False},
            {"direction": "inbound"},
            {"direction": []},
            {"status": "missing"},
            {"status": {}},
            {"asset": []},
            {"asset": ""},
            {"search": None},
            {"search": "x" * 257},
            {"wallet_id": "1 OR 1=1"},
            {"capture_id": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                workspace.movements(**kwargs)
        self.assertEqual(workspace.movements(limit=500)["total"], 0)

    def test_analytics_preserve_exact_assets_daily_totals_and_unknown_time_counts(self):
        workspace = self.workspace()
        huge = 10**70 + 123
        movement = tx("huge")
        movement["blockTime"] = 1767229200
        movement["meta"]["postBalances"][0] = huge + 10000
        movement["meta"]["postTokenBalances"] = [token(amount=str(huge))]
        failed = tx("failed")
        failed["meta"]["err"] = {"InstructionError": [0, "test"]}
        gap = tx("gap")
        gap["meta"] = None
        source = snapshot(movement, failed, gap)
        capture = workspace.import_snapshot(source)
        ledger = analyze(source)
        result = self.workspace().analytics(capture_id=capture["id"])
        self.assertEqual(result["assets"], ledger["assets"])
        self.assertEqual(result["transaction_count"], 3)
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["gap_count"], 1)
        self.assertEqual(result["wallet_paid_fees_base_units"], "10000")
        self.assertEqual(result["unknown_time_count"], 1)
        self.assertTrue(result["synthetic"])
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["daily"]), 2)
        native = next(item for item in result["daily"] if item["asset"] == "SOL")
        self.assertEqual(native["date"], "2026-01-01")
        self.assertEqual(native["net_base_units"], str(huge))
        self.assertEqual(native["count"], 1)
        self.assertEqual(workspace.movements(asset=M)["rows"][0]["amount_base_units"], str(huge))
        with closing(sqlite3.connect(self.path)) as db:
            types = db.execute(
                "SELECT DISTINCT typeof(amount_base_units) FROM movements"
            ).fetchall()
            self.assertEqual(types, [("text",)])
        empty = workspace.add_wallet(W, cluster="testnet")
        self.assertEqual(workspace.analytics(wallet_id=empty["id"])["assets"], [])

    def test_analytics_reject_conflicting_mint_decimals_across_wallets(self):
        workspace = self.workspace()
        first = tx("shared")
        first["meta"]["postTokenBalances"] = [token(amount="100", decimals=2)]
        one = workspace.import_snapshot(snapshot(first))
        second = copy.deepcopy(first)
        second["meta"]["postTokenBalances"][0]["uiTokenAmount"]["decimals"] = 3
        alternate = snapshot(second)
        other_wallet = "Vote111111111111111111111111111111111111111"
        alternate["wallet"] = other_wallet
        second["transaction"]["message"]["accountKeys"][0] = other_wallet
        second["meta"]["postTokenBalances"][0]["owner"] = other_wallet
        two = workspace.import_snapshot(alternate)
        with self.assertRaisesRegex(ValidationError, "decimals"):
            workspace.analytics()
        self.assertEqual(workspace.analytics(capture_id=one["id"])["row_count"], 2)
        self.assertEqual(workspace.analytics(capture_id=two["id"])["row_count"], 2)

    def test_comparison_reports_sorted_signature_changes_and_exact_window_deltas(self):
        workspace = self.workspace()
        unchanged = tx("same")
        before = workspace.import_snapshot(snapshot(tx("removed"), tx("changed"), unchanged))
        changed = tx("changed")
        changed["meta"]["postBalances"][0] = 20000
        after = workspace.import_snapshot(
            snapshot(unchanged, tx("added-z"), changed, tx("added-a"))
        )
        result = self.workspace().compare_captures(before["id"], after["id"])
        self.assertEqual(result["added_signatures"], ["added-a", "added-z"])
        self.assertEqual(result["removed_signatures"], ["removed"])
        self.assertEqual(result["changed_signatures"], ["changed"])
        native = result["assets"][0]
        self.assertEqual(native["before"], "-15000")
        self.assertEqual(native["after"], "-5000")
        self.assertEqual(native["delta_base_units"], "10000")
        self.assertEqual(native["delta"], "0.000010000")
        self.assertEqual(result, workspace.compare_captures(before["id"], after["id"]))
        self.assertEqual(
            workspace.compare_captures(before["id"], before["id"])["changed_signatures"], []
        )
        alternate = snapshot(tx())
        alternate.update(cluster="devnet", synthetic=False)
        other = workspace.import_snapshot(alternate)
        with self.assertRaises(ValidationError):
            workspace.compare_captures(before["id"], other["id"])

    def test_jobs_are_persisted_with_explicit_bounded_capture_options(self):
        workspace = self.workspace()
        wallet = workspace.add_wallet(W)
        job = workspace.create_job(wallet["id"], limit=17, include_tokens=True)
        self.assertEqual(job["wallet_id"], wallet["id"])
        self.assertEqual(job["limit"], 17)
        self.assertIs(job["include_tokens"], True)
        self.assertEqual(job["status"], "queued")
        self.assertIsNone(job["capture_id"])
        self.assertIsNone(job["error"])
        self.assertEqual(self.workspace().get_job(job["id"]), job)
        newer = workspace.create_job(wallet["id"])
        self.assertEqual(workspace.list_jobs(), [newer, job])
        for kwargs in ({"limit": 0}, {"limit": 10001}, {"limit": True}, {"include_tokens": "true"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                workspace.create_job(wallet["id"], **kwargs)
        with self.assertRaises(ValidationError):
            workspace.create_job(999)
        with self.assertRaises(ValidationError):
            workspace.get_job(999)

    def test_job_state_machine_checks_capture_association_and_terminal_immutability(self):
        workspace = self.workspace()
        capture = workspace.import_snapshot(snapshot(tx()))
        wallet_id = capture["wallet_id"]
        job = workspace.create_job(wallet_id)
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "succeeded", capture_id=capture["id"])
        running = workspace.update_job(job["id"], "running")
        self.assertEqual(running["status"], "running")
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "running")
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "succeeded")
        alternate = snapshot(tx())
        alternate.update(cluster="devnet", synthetic=False)
        other = workspace.import_snapshot(alternate)
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "succeeded", capture_id=other["id"])
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "partial", capture_id=capture["id"])
        self.assertEqual(workspace.get_job(job["id"]), running)
        done = workspace.update_job(job["id"], "succeeded", capture_id=capture["id"])
        self.assertEqual(self.workspace().get_job(job["id"]), done)
        self.assertEqual(done["capture_id"], capture["id"])
        with self.assertRaises(ValidationError):
            workspace.update_job(job["id"], "failed", error="Capture failed.")
        partial_source = snapshot(tx("partial"))
        partial_source["warnings"] = ["Limited coverage."]
        partial = workspace.import_snapshot(partial_source)
        partial_job = workspace.create_job(wallet_id)
        workspace.update_job(partial_job["id"], "running")
        result = workspace.update_job(partial_job["id"], "partial", capture_id=partial["id"])
        self.assertEqual(result["status"], "partial")
        failed_job = workspace.create_job(wallet_id)
        result = workspace.update_job(failed_job["id"], "failed", error="Capture failed.")
        self.assertEqual(result["error"], "Capture failed.")
        for status in ("queued", "nonsense", {}, None):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                workspace.update_job(failed_job["id"], status)

    def test_recover_jobs_fails_only_interrupted_jobs_and_is_idempotent(self):
        workspace = self.workspace()
        capture = workspace.import_snapshot(snapshot(tx()))
        queued = workspace.create_job(capture["wallet_id"])
        running = workspace.create_job(capture["wallet_id"])
        workspace.update_job(running["id"], "running")
        complete = workspace.create_job(capture["wallet_id"])
        workspace.update_job(complete["id"], "running")
        complete = workspace.update_job(complete["id"], "succeeded", capture_id=capture["id"])
        reopened = self.workspace()
        self.assertEqual(reopened.recover_jobs(), 2)
        for job in (queued, running):
            stored = reopened.get_job(job["id"])
            self.assertEqual(stored["status"], "failed")
            self.assertIn("interrupted", stored["error"].lower())
            self.assertIsNone(stored["capture_id"])
        self.assertEqual(reopened.get_job(complete["id"]), complete)
        self.assertEqual(reopened.recover_jobs(), 0)

    def test_schema_migration_refuses_future_versions_on_every_operation(self):
        self.path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)
        workspace = self.workspace()
        wallet = workspace.add_wallet(W)
        with workspace._connection() as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA user_version = 99")
        with self.assertRaisesRegex(ValidationError, "schema"):
            workspace.list_wallets()
        with self.assertRaisesRegex(ValidationError, "schema"):
            self.workspace()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)
            self.assertEqual(
                db.execute("SELECT address FROM wallets WHERE id = ?", (wallet["id"],)).fetchone()[
                    0
                ],
                W,
            )

    def test_database_failure_rolls_back_wallet_capture_and_rows_with_safe_diagnostic(self):
        workspace = self.workspace()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "CREATE TRIGGER reject_row BEFORE INSERT ON movements "
                "BEGIN SELECT RAISE(ABORT, 'private-provider-error'); END"
            )
        with self.assertRaises(ValidationError) as caught:
            workspace.import_snapshot(snapshot(tx()))
        self.assertNotIn("private-provider-error", str(caught.exception))
        self.assertEqual(workspace.list_wallets(), [])
        self.assertEqual(workspace.list_captures(), [])
        self.assertEqual(workspace.movements()["total"], 0)

    def test_normalization_preserves_allowlisted_discovery_evidence_and_failure_status(self):
        workspace = self.workspace()
        failed = tx()
        failed["meta"]["err"] = {"provider": "https://secret.example/?key=NEVER-PERSIST"}
        source = snapshot(failed)
        source["coverage"].update(
            discovery="wallet-and-current-token-accounts",
            token_accounts=["So11111111111111111111111111111111111111112"],
            sources=[
                {
                    "address": W,
                    "pages": 1,
                    "cap_reached": False,
                    "reached_history": True,
                    "partial": False,
                },
                {
                    "address": "So11111111111111111111111111111111111111112",
                    "pages": 0,
                    "cap_reached": False,
                    "reached_history": True,
                    "partial": False,
                },
            ],
            provider_url="NEVER-PERSIST",
        )
        capture = workspace.import_snapshot(source)
        stored = workspace.get_capture(capture["id"])
        coverage = stored["snapshot"]["coverage"]
        self.assertEqual(coverage["token_accounts"], source["coverage"]["token_accounts"])
        self.assertEqual(coverage["sources"][0]["address"], W)
        self.assertNotIn("provider_url", coverage["sources"][0])
        self.assertEqual(stored["snapshot"]["transactions"][0]["meta"]["err"], {"failed": True})
        self.assertEqual(stored["ledger"]["failed_count"], 1)
        self.assertNotIn("NEVER-PERSIST", json.dumps(stored))

    def test_extreme_integer_slots_and_timestamps_do_not_overflow_sqlite_or_dates(self):
        workspace = self.workspace()
        unusual = tx()
        unusual["slot"] = 10**80
        unusual["blockTime"] = 10**80
        capture = workspace.import_snapshot(snapshot(unusual))
        self.assertEqual(workspace.movements()["rows"][0]["slot"], 10**80)
        self.assertEqual(workspace.movements(offset=10**80)["rows"], [])
        result = workspace.analytics(capture_id=capture["id"])
        self.assertEqual(result["daily"], [])
        self.assertEqual(result["unknown_time_count"], 1)
        with self.assertRaises(ValidationError):
            workspace.get_wallet(10**80)

    def test_concurrent_imports_are_one_atomic_deduplicated_capture(self):
        from concurrent.futures import ThreadPoolExecutor

        workspace = self.workspace()
        source = snapshot(tx())
        with ThreadPoolExecutor(max_workers=8) as executor:
            captures = list(executor.map(lambda _: workspace.import_snapshot(source), range(24)))
        self.assertTrue(all(capture == captures[0] for capture in captures))
        self.assertEqual(len(workspace.list_wallets()), 1)
        self.assertEqual(len(workspace.list_captures()), 1)
        self.assertEqual(workspace.movements()["total"], 1)

    def test_wallet_validation_fixture_exception_and_labels_are_parameterized(self):
        workspace = self.workspace()
        demo = workspace.add_wallet("SyntheticWallet111111111111111111111111111111", "synthetic")
        self.assertEqual(demo["cluster"], "synthetic")
        label = "'); DROP TABLE wallets; --"
        wallet = workspace.add_wallet(W, label=label)
        self.assertEqual(workspace.get_wallet(wallet["id"])["label"], label)
        for address, cluster, label in (
            ("SyntheticWallet111111111111111111111111111111", "custom", ""),
            ("not-an-address", "synthetic", ""),
            (W, "https://secret.example", ""),
            (W, [], ""),
            (W, "custom", "bad\nlabel"),
            (W, "custom", None),
        ):
            with self.subTest(address=address, cluster=cluster), self.assertRaises(ValidationError):
                workspace.add_wallet(address, cluster, label)
        with self.assertRaises(ValidationError):
            workspace.list_captures(999)
        with self.assertRaises(ValidationError):
            workspace.analytics(capture_id=999)

    def test_comparison_detects_missing_metadata_resolution_and_rejects_decimal_conflicts(self):
        workspace = self.workspace()
        before_source = snapshot()
        before_source["unavailable_signatures"] = ["resolved"]
        before = workspace.import_snapshot(before_source)
        resolved = tx("resolved")
        after = workspace.import_snapshot(snapshot(resolved))
        difference = workspace.compare_captures(before["id"], after["id"])
        self.assertEqual(difference["changed_signatures"], ["resolved"])
        self.assertEqual(difference["added_signatures"], [])
        resolved["meta"]["postTokenBalances"] = [token(decimals=2)]
        token_before = workspace.import_snapshot(snapshot(resolved))
        resolved["meta"]["postTokenBalances"][0]["uiTokenAmount"]["decimals"] = 3
        token_after = workspace.import_snapshot(snapshot(resolved))
        with self.assertRaisesRegex(ValidationError, "decimals"):
            workspace.compare_captures(token_before["id"], token_after["id"])

    def test_movement_total_and_page_share_a_snapshot_during_concurrent_import(self):
        workspace = self.workspace()
        before = workspace.import_snapshot(snapshot(tx("old")))
        writer = self.workspace()
        original_connection = workspace._connection

        class CountResult:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class ConnectionProxy:
            def __init__(self, db):
                self.db = db

            def execute(self, sql, params=()):
                cursor = self.db.execute(sql, params)
                if sql.startswith("SELECT COUNT(*)"):
                    count = cursor.fetchone()
                    writer.import_snapshot(snapshot(tx("new-a"), tx("new-b")))
                    return CountResult(count)
                return cursor

        @contextmanager
        def interleaved_connection():
            with original_connection() as db:
                yield ConnectionProxy(db)

        with patch.object(workspace, "_connection", interleaved_connection):
            result = workspace.movements()
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["capture_id"], before["id"])
        self.assertEqual(workspace.movements()["total"], 2)

    def test_packaged_synthetic_demo_import_keeps_safe_balance_evidence(self):
        from importlib.resources import files

        source = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
        workspace = self.workspace()
        capture = workspace.import_snapshot(source, label="Packaged synthetic evidence")
        stored = workspace.get_capture(capture["id"])
        self.assertEqual(stored["ledger"], analyze(stored["snapshot"]))

        def key(item):
            return item["asset"], item["mint"] or ""

        self.assertEqual(
            sorted(workspace.analytics()["assets"], key=key),
            sorted(stored["ledger"]["assets"], key=key),
        )
        self.assertTrue(capture["synthetic"])
        self.assertEqual(capture["transaction_count"], analyze(source)["transaction_count"])
        self.assertEqual(workspace.import_snapshot(source), capture)

    def test_analytics_aggregate_latest_wallet_scoped_movements_not_transfer_volume(self):
        workspace = self.workspace()
        workspace.import_snapshot(snapshot(tx("overlapping")))
        latest = workspace.import_snapshot(snapshot(tx("overlapping"), tx("new")))
        other_wallet = "So11111111111111111111111111111111111111112"
        other_source = snapshot(tx("overlapping"))
        other_source["wallet"] = other_wallet
        other_source["transactions"][0]["transaction"]["message"]["accountKeys"][0] = other_wallet
        other = workspace.import_snapshot(other_source)
        total = workspace.analytics()
        self.assertEqual(total["transaction_count"], 3)
        self.assertEqual(total["row_count"], 3)
        self.assertEqual(total["assets"][0]["net_base_units"], "-15000")
        self.assertEqual(total["wallet_paid_fees_base_units"], "15000")
        self.assertEqual(workspace.analytics(wallet_id=latest["wallet_id"])["transaction_count"], 2)
        self.assertEqual(workspace.analytics(capture_id=other["id"])["transaction_count"], 1)

    def test_failed_initialization_does_not_leave_half_a_schema(self):
        self.path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE captures(unrecognized TEXT)")
        with self.assertRaises(ValidationError):
            self.workspace()
        with closing(sqlite3.connect(self.path)) as db:
            tables = [
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            self.assertEqual(tables, ["captures"])
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_job_errors_cannot_persist_endpoint_urls(self):
        workspace = self.workspace()
        wallet = workspace.add_wallet(W)
        job = workspace.create_job(wallet["id"])
        endpoint = "https://rpc.example/?api-key=NEVER-PERSIST"
        with self.assertRaises(ValidationError) as caught:
            workspace.update_job(job["id"], "failed", error=endpoint)
        self.assertNotIn("NEVER-PERSIST", str(caught.exception))
        self.assertEqual(workspace.get_job(job["id"]), job)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn("NEVER-PERSIST", " ".join(db.iterdump()))
