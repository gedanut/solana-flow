"""Persistent, local investigation evidence. No RPC endpoints or credentials."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .ledger import ValidationError, analyze, decimal_amount, require
from .rpc import _analysis_transaction, validate_address

SCHEMA_VERSION = 1
CLUSTERS = ("mainnet-beta", "devnet", "testnet", "custom", "synthetic")
FIXTURE_WALLET = "SyntheticWallet111111111111111111111111111111"


def _now():
    return datetime.now(UTC).isoformat()


def _id(value):
    require(type(value) is int and 0 < value <= 2**63 - 1, "Invalid identifier.")
    return value


def _label(value):
    require(isinstance(value, str) and len(value) <= 256, "Invalid label.")
    require(not any(ord(char) < 32 for char in value), "Invalid label.")
    return value


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValidationError("Invalid snapshot encoding.") from None


def _normalized(snapshot):
    # Keep balance evidence only, matching RPC capture's normalization boundary.
    result = {
        key: snapshot[key]
        for key in (
            "schema_version",
            "wallet",
            "cluster",
            "synthetic",
            "captured_at",
            "unavailable_signatures",
            "warnings",
        )
    }
    result["coverage"] = {
        key: snapshot["coverage"][key]
        for key in (
            "limit",
            "pages",
            "cap_reached",
            "reached_history",
            "partial",
            "discovery",
        )
    }
    if snapshot["coverage"]["discovery"] == "wallet-and-current-token-accounts":
        result["coverage"]["token_accounts"] = list(snapshot["coverage"]["token_accounts"])
        fields = ("address", "pages", "cap_reached", "reached_history", "partial")
        result["coverage"]["sources"] = [
            {key: source[key] for key in fields} for source in snapshot["coverage"]["sources"]
        ]
    result["transactions"] = [_analysis_transaction(tx) for tx in snapshot["transactions"]]
    return result


def _day(timestamp):
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _totals(rows, daily=False):
    totals = {}
    for row in rows:
        day = None
        if daily:
            day = _day(row["time"])
            if day is None:
                continue
        key = (day or "", row["asset"], row["mint"] or "")
        if key not in totals:
            totals[key] = {
                "asset": row["asset"],
                "mint": row["mint"],
                "decimals": row["decimals"],
                "inflow": 0,
                "outflow": 0,
                "net": 0,
            }
            if daily:
                totals[key].update(date=day, count=0)
        total = totals[key]
        require(total["decimals"] == row["decimals"], "Conflicting decimals for an asset.")
        value = int(row["amount_base_units"])
        total["inflow"] += max(value, 0)
        total["outflow"] += max(-value, 0)
        total["net"] += value
        if daily:
            total["count"] += 1
    result = []
    for key in sorted(totals):
        total = totals[key]
        for field in ("inflow", "outflow", "net"):
            total[field + "_base_units"] = str(total[field])
            total[field] = decimal_amount(total[field], total["decimals"])
        result.append(total)
    return result


class Workspace:
    """A file-backed workspace; connections are never shared across operations."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            require(version <= SCHEMA_VERSION, "Unsupported workspace schema version.")
            if version == 0:
                db.execute("""CREATE TABLE wallets (
                    id INTEGER PRIMARY KEY,
                    address TEXT NOT NULL,
                    cluster TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(address, cluster)
                )""")
                db.execute("""CREATE TABLE captures (
                    id INTEGER PRIMARY KEY,
                    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
                    label TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    transaction_count INTEGER NOT NULL,
                    row_count INTEGER NOT NULL,
                    partial INTEGER NOT NULL,
                    synthetic INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    ledger_json TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX captures_wallet ON captures(wallet_id, id)")
                db.execute("""CREATE TABLE movements (
                    capture_id INTEGER NOT NULL REFERENCES captures(id),
                    row_index INTEGER NOT NULL,
                    signature TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    mint TEXT,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    amount_base_units TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY(capture_id, row_index)
                )""")
                db.execute("""CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    wallet_id INTEGER NOT NULL REFERENCES wallets(id),
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','partial','failed')),
                    capture_limit INTEGER NOT NULL,
                    include_tokens INTEGER NOT NULL,
                    capture_id INTEGER REFERENCES captures(id),
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""")
                db.execute("PRAGMA user_version = 1")

    @contextmanager
    def _connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            version = db.execute("PRAGMA user_version").fetchone()[0]
            require(version <= SCHEMA_VERSION, "Unsupported workspace schema version.")
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute("PRAGMA journal_mode = WAL")
            with db:
                yield db
        except sqlite3.Error:
            raise ValidationError("Workspace database operation failed.") from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _wallet(db, wallet_id):
        row = db.execute("SELECT * FROM wallets WHERE id = ?", (_id(wallet_id),)).fetchone()
        require(row is not None, "Wallet not found.")
        return dict(row)

    def add_wallet(self, address, cluster="custom", label=""):
        require(isinstance(cluster, str) and cluster in CLUSTERS, "Invalid cluster.")
        if not (cluster == "synthetic" and address == FIXTURE_WALLET):
            validate_address(address)
        _label(label)
        with self._connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO wallets(address, cluster, label, created_at) "
                "VALUES (?, ?, ?, ?)",
                (address, cluster, label, _now()),
            )
            return dict(
                db.execute(
                    "SELECT * FROM wallets WHERE address = ? AND cluster = ?", (address, cluster)
                ).fetchone()
            )

    def list_wallets(self):
        with self._connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM wallets ORDER BY id")]

    def get_wallet(self, wallet_id):
        with self._connection() as db:
            return self._wallet(db, wallet_id)

    @staticmethod
    def _capture_metadata(row):
        result = dict(row)
        result.pop("snapshot_json", None)
        result.pop("ledger_json", None)
        for field in ("partial", "synthetic"):
            result[field] = bool(result[field])
        return result

    def import_snapshot(self, snapshot, label=""):
        analyze(snapshot)
        _label(label)
        canonical = _canonical(_normalized(snapshot))
        ledger = analyze(json.loads(canonical))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        address, cluster = ledger["wallet"], ledger["cluster"]
        if not (cluster == "synthetic" and address == FIXTURE_WALLET):
            validate_address(address)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM captures WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing is not None:
                return self._capture_metadata(existing)
            db.execute(
                "INSERT OR IGNORE INTO wallets(address, cluster, label, created_at) "
                "VALUES (?, ?, '', ?)",
                (address, cluster, _now()),
            )
            wallet_id = db.execute(
                "SELECT id FROM wallets WHERE address = ? AND cluster = ?", (address, cluster)
            ).fetchone()[0]
            cursor = db.execute(
                "INSERT INTO captures(wallet_id, label, captured_at, imported_at, fingerprint, "
                "transaction_count, row_count, partial, synthetic, snapshot_json, ledger_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    wallet_id,
                    label,
                    ledger["captured_at"],
                    _now(),
                    fingerprint,
                    ledger["transaction_count"],
                    len(ledger["rows"]),
                    ledger["coverage"]["partial"],
                    ledger["synthetic"],
                    canonical,
                    json.dumps(ledger, allow_nan=False),
                ),
            )
            db.executemany(
                "INSERT INTO movements(capture_id, row_index, signature, slot, asset, mint, "
                "direction, status, amount_base_units, row_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        cursor.lastrowid,
                        index,
                        row["signature"],
                        str(row["slot"]),
                        row["asset"],
                        row["mint"],
                        row["direction"],
                        row["status"],
                        row["amount_base_units"],
                        _canonical(row),
                    )
                    for index, row in enumerate(ledger["rows"])
                ],
            )
            return self._capture_metadata(
                db.execute("SELECT * FROM captures WHERE id = ?", (cursor.lastrowid,)).fetchone()
            )

    def get_capture(self, capture_id):
        with self._connection() as db:
            return self._capture(db, capture_id)

    def _capture(self, db, capture_id):
        row = db.execute("SELECT * FROM captures WHERE id = ?", (_id(capture_id),)).fetchone()
        require(row is not None, "Capture not found.")
        result = self._capture_metadata(row)
        result["snapshot"] = json.loads(row["snapshot_json"])
        result["ledger"] = json.loads(row["ledger_json"])
        return result

    def list_captures(self, wallet_id=None):
        with self._connection() as db:
            where, params = "", ()
            if wallet_id is not None:
                self._wallet(db, wallet_id)
                where, params = " WHERE wallet_id = ?", (wallet_id,)
            return [
                self._capture_metadata(row)
                for row in db.execute(
                    "SELECT * FROM captures" + where + " ORDER BY id DESC", params
                )
            ]

    def _scope(self, db, wallet_id, capture_id):
        clauses, params = [], []
        if wallet_id is not None:
            self._wallet(db, wallet_id)
            clauses.append("c.wallet_id = ?")
            params.append(wallet_id)
        if capture_id is not None:
            row = db.execute(
                "SELECT wallet_id FROM captures WHERE id = ?", (_id(capture_id),)
            ).fetchone()
            require(row is not None, "Capture not found.")
            require(wallet_id is None or row[0] == wallet_id, "Capture wallet mismatch.")
            clauses.append("c.id = ?")
            params.append(capture_id)
        else:
            clauses.append("c.id = (SELECT MAX(id) FROM captures WHERE wallet_id = c.wallet_id)")
        return " AND ".join(clauses), params

    def movements(
        self,
        wallet_id=None,
        capture_id=None,
        asset=None,
        direction=None,
        status=None,
        search="",
        limit=100,
        offset=0,
    ):
        require(type(limit) is int and 1 <= limit <= 500, "Invalid page limit.")
        require(type(offset) is int and offset >= 0, "Invalid page offset.")
        require(direction is None or direction in ("in", "out", "zero"), "Invalid direction.")
        require(status is None or status in ("success", "failed"), "Invalid status.")
        if asset is not None:
            require(isinstance(asset, str) and 0 < len(asset) <= 256, "Invalid asset.")
        _label(search)
        with self._connection() as db:
            db.execute("BEGIN")  # Count and page must see the same latest-capture selection.
            where, params = self._scope(db, wallet_id, capture_id)
            for field, value in (("direction", direction), ("status", status)):
                if value is not None:
                    where += f" AND m.{field} = ?"
                    params.append(value)
            if asset is not None:
                where += " AND (m.asset = 'SOL' AND ? = 'SOL' OR m.mint = ?)"
                params.extend((asset, asset))
            if search:
                where += " AND (instr(lower(m.signature), lower(?)) > 0 "
                where += "OR instr(lower(COALESCE(m.mint, m.asset)), lower(?)) > 0)"
                params.extend((search, search))
            source = " FROM movements m JOIN captures c ON c.id = m.capture_id WHERE " + where
            total = db.execute("SELECT COUNT(*)" + source, params).fetchone()[0]
            rows = db.execute(
                "SELECT m.row_json, c.wallet_id, c.id AS capture_id"
                + source
                + " ORDER BY c.id DESC, length(m.slot) DESC, m.slot DESC, m.signature, m.row_index "
                + "LIMIT ? OFFSET ?",
                [*params, limit, min(offset, 2**63 - 1)],
            )
            return {
                "rows": [
                    {
                        **json.loads(row["row_json"]),
                        "wallet_id": row["wallet_id"],
                        "capture_id": row["capture_id"],
                    }
                    for row in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def analytics(self, wallet_id=None, capture_id=None):
        with self._connection() as db:
            where, params = self._scope(db, wallet_id, capture_id)
            ledgers = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT c.ledger_json FROM captures c WHERE " + where + " ORDER BY c.id", params
                )
            ]
        require(
            len({ledger["cluster"] for ledger in ledgers}) <= 1,
            "Select one cluster before aggregating wallet assets.",
        )
        rows = [row for ledger in ledgers for row in ledger["rows"]]
        return {
            "assets": _totals(rows),
            "daily": _totals(rows, daily=True),
            "transaction_count": sum(ledger["transaction_count"] for ledger in ledgers),
            "row_count": len(rows),
            "failed_count": sum(ledger["failed_count"] for ledger in ledgers),
            "gap_count": sum(len(ledger["gaps"]) for ledger in ledgers),
            "wallet_paid_fees_base_units": str(
                sum(int(ledger["wallet_paid_fees_base_units"]) for ledger in ledgers)
            ),
            "unknown_time_count": sum(_day(row["time"]) is None for row in rows),
            "synthetic": any(ledger["synthetic"] for ledger in ledgers),
            "partial": any(ledger["coverage"]["partial"] for ledger in ledgers),
        }

    def compare_captures(self, before_id, after_id):
        with self._connection() as db:
            before, after = self._capture(db, before_id), self._capture(db, after_id)
        require(before["wallet_id"] == after["wallet_id"], "Capture wallet mismatch.")

        def signatures(capture):
            source = capture["snapshot"]
            result = {signature: None for signature in source["unavailable_signatures"]}
            result.update(
                {
                    tx["transaction"]["signatures"][0]: _canonical(tx)
                    for tx in source["transactions"]
                }
            )
            return result

        a, b = signatures(before), signatures(after)
        before_assets = {(x["asset"], x["mint"]): x for x in before["ledger"]["assets"]}
        after_assets = {(x["asset"], x["mint"]): x for x in after["ledger"]["assets"]}
        assets = []
        for item in _totals(before["ledger"]["rows"] + after["ledger"]["rows"]):
            key = (item["asset"], item["mint"])
            left = before_assets.get(key, {})
            right = after_assets.get(key, {})
            delta = int(right.get("net_base_units", "0")) - int(left.get("net_base_units", "0"))
            assets.append(
                {
                    "asset": item["asset"],
                    "mint": item["mint"],
                    "decimals": item["decimals"],
                    "before": left.get("net_base_units", "0"),
                    "after": right.get("net_base_units", "0"),
                    "delta_base_units": str(delta),
                    "delta": decimal_amount(delta, item["decimals"]),
                }
            )
        return {
            "before_id": before_id,
            "after_id": after_id,
            "wallet_id": before["wallet_id"],
            "added_signatures": sorted(b.keys() - a.keys()),
            "removed_signatures": sorted(a.keys() - b.keys()),
            "changed_signatures": sorted(key for key in a.keys() & b.keys() if a[key] != b[key]),
            "assets": assets,
        }

    @staticmethod
    def _job_metadata(row):
        result = dict(row)
        result["limit"] = result.pop("capture_limit")
        result["include_tokens"] = bool(result["include_tokens"])
        return result

    def _job(self, db, job_id):
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (_id(job_id),)).fetchone()
        require(row is not None, "Job not found.")
        return self._job_metadata(row)

    def create_job(self, wallet_id, limit=100, include_tokens=False):
        require(type(limit) is int and 1 <= limit <= 10000, "Invalid capture limit.")
        require(type(include_tokens) is bool, "Invalid token discovery flag.")
        with self._connection() as db:
            self._wallet(db, wallet_id)
            now = _now()
            cursor = db.execute(
                "INSERT INTO jobs(wallet_id, status, capture_limit, include_tokens, "
                "capture_id, error, created_at, updated_at) VALUES (?, 'queued', ?, ?, NULL, NULL, ?, ?)",
                (wallet_id, limit, include_tokens, now, now),
            )
            return self._job(db, cursor.lastrowid)

    def get_job(self, job_id):
        with self._connection() as db:
            return self._job(db, job_id)

    def update_job(self, job_id, status, capture_id=None, error=None):
        require(
            isinstance(status, str)
            and status
            in (
                "running",
                "succeeded",
                "partial",
                "failed",
            ),
            "Invalid job status.",
        )
        if error is not None:
            _label(error)
            require("://" not in error, "Invalid job error.")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(db, job_id)
            transitions = {
                "queued": ("running", "failed"),
                "running": ("succeeded", "partial", "failed"),
            }
            require(status in transitions.get(job["status"], ()), "Invalid job transition.")
            if status in ("succeeded", "partial"):
                require(capture_id is not None, "Completed job requires a capture.")
                capture = self._capture(db, capture_id)
                require(capture["wallet_id"] == job["wallet_id"], "Capture wallet mismatch.")
                require(capture["partial"] == (status == "partial"), "Capture status mismatch.")
            else:
                require(capture_id is None, "Unexpected job capture.")
            require(
                status not in ("running", "succeeded") or error is None, "Unexpected job error."
            )
            db.execute(
                "UPDATE jobs SET status = ?, capture_id = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, capture_id, error, _now(), job_id),
            )
            return self._job(db, job_id)

    def recover_jobs(self):
        """Run once at exclusive worker startup, never while another runner is live."""
        with self._connection() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = 'failed', capture_id = NULL, error = ?, updated_at = ? "
                "WHERE status IN ('queued', 'running')",
                ("Capture interrupted by process restart. Submit a new job to retry.", _now()),
            )
            return cursor.rowcount

    def list_jobs(self):
        with self._connection() as db:
            return [
                self._job_metadata(row) for row in db.execute("SELECT * FROM jobs ORDER BY id DESC")
            ]
