# Persistent investigation workspace

`solana_flow.workspace.Workspace(path)` is a local, file-backed SQLite evidence
store. It performs no network calls and accepts no RPC endpoint configuration.
Its runtime dependencies are Python 3.11+ standard-library modules.

## Storage and lifecycle

- Missing parent directories and a new database are created automatically.
- Each public operation opens and closes its own SQLite connection. A `Workspace`
  object can be used by the HTTP thread and a capture-worker thread without
  sharing a connection. Every connection enables foreign keys, a 5,000 ms busy
  timeout, and WAL journaling.
- `PRAGMA user_version` identifies schema version **1**. Empty version-0 databases
  are initialized transactionally. A schema collision rolls back initialization;
  the code does not drop or repair unknown tables. Future versions are refused
  on opening and on subsequent operations, without downgrading the schema.
- Snapshot import and job transitions use `BEGIN IMMEDIATE`. Wallet creation,
  capture creation, and all movement rows commit together. Validation failures
  and database failures cannot leave a partially imported capture. Movement
  count and page queries share one read transaction, including when a new
  capture is imported between those queries.
- Validation and database diagnostics are fixed messages, never interpolated
  addresses, SQL, paths, provider errors, or input values. Filesystem failures
  creating the parent directory are ordinary OS errors.
- The database is not encrypted. Protect the database and its WAL/SHM files as
  local investigation data. There is intentionally no public edit/delete API
  for captures. Immutable means immutable through this API, not protection from
  someone who can edit the SQLite file.

## Wallets

```python
workspace = Workspace("investigation/workspace.sqlite3")
wallet = workspace.add_wallet(address, cluster="custom", label="Treasury")
workspace.list_wallets()
workspace.get_wallet(wallet["id"])
```

Wallet identity is **(address, cluster)**. Allowed clusters are `mainnet-beta`,
`devnet`, `testnet`, `custom`, and `synthetic`. Addresses use
`rpc.validate_address`: base58 decoding to exactly 32 bytes. The only non-public-key
exception is the packaged demo address
`SyntheticWallet111111111111111111111111111111`, and only for `synthetic`.

A wallet is `{id, address, cluster, label, created_at}`. Duplicate adds return the
existing wallet without overwriting its label. Lists are in ascending ID order.
Labels are strings of at most 256 characters with no ASCII control characters.
IDs must be positive SQLite-range integers; booleans and string coercion are
not accepted. Missing requested wallets/captures/jobs raise `ValidationError`.

## Importing and retrieving captures

```python
metadata = workspace.import_snapshot(snapshot, label="Evidence capture")
full = workspace.get_capture(metadata["id"])
captures = workspace.list_captures(wallet_id=None)
```

1. Run `ledger.analyze` before any database mutation.
2. Project an allowlisted normalized schema-v1 envelope and transaction balance
   evidence using the same `_analysis_transaction` projection as RPC capture.
3. Reanalyze that normalized evidence and atomically store both snapshot and
   ledger JSON, plus indexed movement records.

This is **not a raw RPC archive**. Unknown top-level/provider/transaction/meta
extensions, logs, and raw error payloads are discarded. A failed transaction's
`meta.err` becomes `{"failed": true}`; success remains `null`. Loaded addresses,
validated token balances/owners, signatures, slots, block times, and supported
transaction versions remain available for investigation. Current-token-account
capture coverage preserves its validated `token_accounts` and per-source
coverage fields. Unsupported nested coverage source fields are rejected by
ledger validation. Warning strings are retained evidence; callers must supply
application-controlled diagnostics, not raw transport exceptions or credentials.

The fingerprint is SHA-256 over UTF-8 JSON of the **normalized snapshot**, with
sorted object keys, compact separators, and nonfinite values forbidden.
Object-key ordering and discarded extensions do not change identity. Array
ordering and capture metadata do participate; this is capture deduplication,
not deduplication of every logically equivalent history window. The label does
not participate. Reimport returns the original capture, including its original
label/import time. Conflicting duplicate signatures within a snapshot are
rejected; later captures may contain changed evidence for the same signature.

Metadata contains `id`, `wallet_id`, `label`, `captured_at`, `imported_at`,
`fingerprint`, `transaction_count`, `row_count`, `partial`, and `synthetic`.
`get_capture` additionally returns `snapshot` and `ledger` dictionaries.
`import_snapshot` and `list_captures` return metadata without those JSON blobs.
Wallets created by import have an empty wallet label. Caller mutations of
returned dictionaries cannot modify stored evidence.

**Latest always means highest capture ID (import recency), not chronological
`captured_at`.** Lists are newest first; reimporting a deduplicated old capture
does not make it latest.

## Movements

```python
page = workspace.movements(
    wallet_id=None,
    capture_id=None,
    asset=None,
    direction=None,
    status=None,
    search="",
    limit=100,
    offset=0,
)
```

Returns `{rows, total, limit, offset}`. Each row preserves the ledger row fields
and adds `wallet_id` and `capture_id`. Without `capture_id`, only the latest
capture **per wallet** participates, avoiding double-counting overlapping saved
captures. An explicit capture selects that capture only. Supplying both IDs
requires the capture to belong to the wallet.

- `asset`: `SOL` for native rows, otherwise an exact mint string (not `SPL`).
- `direction`: `in`, `out`, or `zero`; `status`: `success` or `failed`.
- `search`: case-insensitive literal substring in signature or mint/native asset.
  `%`, `_`, and quotes are ordinary characters, not SQL wildcards or syntax.
  Search has the same length/control-character bounds as labels.
- Pagination is strict: integer `limit` in 1..500, integer `offset >= 0`, no
  booleans/coercion. Large offsets return an empty page while preserving total.
- Ordering is capture ID descending, numeric slot descending, signature, then
  original ledger row position. All user values are SQL parameters.

Amounts and slots are TEXT in SQLite, retaining integers beyond SQLite64.
Public amounts are integer strings and formatted decimal strings, never floats.
Public slots retain the ledger's integer representation.

## Analytics and interpretation

`analytics(wallet_id=None, capture_id=None)` uses the same latest-per-wallet or
explicit-capture scope as movements. It returns:

- `assets`: ledger-shaped per-asset totals (`asset`, `mint`, `decimals`,
  `inflow`, `outflow`, `net`, and corresponding `*_base_units` strings).
- `daily`: those totals plus UTC `date` and movement-row `count`.
- `transaction_count`, `row_count`, `failed_count`, `gap_count`, and
  `wallet_paid_fees_base_units`.
- `unknown_time_count`: movement rows with missing or unrepresentable timestamps.
  These remain in asset totals but are excluded from daily buckets.
- `synthetic` and `partial`: true when **any** selected capture has that flag.

Python integers perform all aggregation; there is no SQLite `SUM` or floating
conversion of amounts. Assets are sorted by asset/mint; daily groups by
UTC date then asset/mint. Different assets are never added together. The same
asset/mint with conflicting decimals causes `ValidationError`, including when
captures individually validate. Fee totals come from ledger transaction totals,
not one fee per token row. `gap_count` counts ledger gap records, not unavailable
signatures; unavailable evidence still makes coverage partial. Empty scopes
return empty lists, zero counts, fee `"0"`, and false flags.

**Across wallets, these are wallet-scoped balance movements, not unique transfer
volume.** The same signature can count for multiple observed wallets. An
internal transfer can produce both an outflow and an inflow. Likewise, combined
clusters or synthetic/live evidence must not be treated as one economic
portfolio. These are net balance changes, not payments, balances, transfer
classification, prices, portfolio PnL, or proof of complete wallet history.

## Capture comparison

`compare_captures(before_id, after_id)` requires the same wallet identity,
including cluster. It returns sorted `added_signatures`, `removed_signatures`,
and `changed_signatures`, plus IDs and sorted `assets`.

Signature comparisons use canonical **normalized transaction evidence**, not
only movement amounts. Known unavailable signatures participate; a previously
unavailable signature that resolves is changed rather than added. Metadata-only
changes to retained evidence are detectable even if net amounts stay equal.
Discarded provider extensions and raw error payload changes are not evidence
changes.

Each comparison asset has `asset`, `mint`, `decimals`, `before`, `after`,
`delta_base_units`, and `delta`. `before`/`after` are the two captures' exact net
base-unit strings; delta is after minus before, with absent assets treated as
zero. Conflicting decimals are refused. Results are deterministic, including
self-comparison. **This compares capture windows; it does not imply disjoint
windows, activity between capture times, or investment PnL.**

## Durable jobs

```python
job = workspace.create_job(wallet_id, limit=100, include_tokens=False)
workspace.update_job(job["id"], "running")
workspace.update_job(job["id"], "succeeded", capture_id=capture_id)
workspace.get_job(job["id"])
workspace.list_jobs()  # highest ID first
```

A job contains `id`, `wallet_id`, `status`, `limit`, `include_tokens`, `capture_id`,
`error`, `created_at`, and `updated_at`. Limit is a strict integer in 1..10000;
`include_tokens` is a strict boolean. No endpoint is accepted or stored.

Allowed transitions are only:

```text
queued  -> running | failed
running -> succeeded | partial | failed
```

Terminal states cannot be rewritten. `succeeded` and `partial` require a capture
associated with the job's wallet, and its effective `partial` flag must match.
`running`/`failed` cannot attach captures. `running`/`succeeded` cannot attach an
error. Error text must be an application-controlled, bounded single-line
message, never `str()` of a provider/transport exception. Explicit URL strings
containing `://` are rejected as defense in depth, not general secret detection.

`recover_jobs()` atomically marks every queued/running job failed, with the
fixed diagnostic `Capture interrupted by process restart. Submit a new job to
retry.` It returns the changed count and is idempotent. Call it **once at
exclusive capture-runner startup**, never while another runner is live. Opening
a Workspace alone does not interrupt jobs or trigger network activity.

## Verification evidence

Implementation was developed through incremental red/green cycles, including
an observed failing regression for concurrent import between count/page reads.
Real on-disk SQLite tests cover reopen persistence, migration and rollback,
24 parallel duplicate imports, invalid snapshots/signature conflicts,
parameterized filtering and labels, strict pagination/types, 71-digit amounts,
81-digit slots/timestamps, normalized provider-secret removal, packaged demo
import, latest-per-wallet aggregation, comparisons, job transitions, and restart
recovery.

Commands executed successfully after formatting:

```text
.venv/bin/python -m unittest discover -s tests -p test_workspace.py -q
  Ran 24 tests: OK
.venv/bin/python -m coverage run --data-file="$TMPDIR/solana-flow-workspace.coverage" \
  --source=solana_flow.workspace --branch -m unittest discover -s tests -p test_workspace.py -q
.venv/bin/python -m coverage report --data-file="$TMPDIR/solana-flow-workspace.coverage" -m
  workspace.py: 99% statement/branch combined coverage (278 statements)
.venv/bin/python -m ruff check src/solana_flow/workspace.py tests/test_workspace.py
  All checks passed!
.venv/bin/python -m unittest discover -s tests -q
  Ran 110 tests: OK
```

Full-suite count is a point-in-time integration result while other workers add
features. No database fixture, endpoint credentials, network publication, or
commit was created by this workspace change.
