# Local workbench API

Source of truth: [server.py](../src/solana_flow/server.py), [Workspace](../src/solana_flow/workspace.py), [JobRunner](../src/solana_flow/jobs.py), and [strict JSON decoding](../src/solana_flow/jsonio.py). This is a same-origin, single-user loopback interface, not a hosted API. The static explorer reads `demo-data.json` through a browser adapter; it does not expose these mutation endpoints.

## Start and session protection

```sh
solana-flow serve --database investigation.sqlite3 --demo
# Optional live capture configuration; prefer the environment for endpoint secrets:
# SOLANA_FLOW_RPC_URL=<your endpoint> solana-flow serve --database investigation.sqlite3
```

`--database` is required; port defaults to `8765` (`--port 0` chooses an available port). `--demo` idempotently seeds synthetic captures. `--rpc-url` overrides `SOLANA_FLOW_RPC_URL`; without either, import/query/export still work but network capture submission is unavailable. The bind address is always `127.0.0.1`, with no public-host override. Open the printed `http://127.0.0.1:PORT/` URL.

1. `GET /api/session` returns `{token, mode: "local", version, capture_enabled}`.
2. Every POST requires `X-Solana-Flow-Token: <token>` and `Content-Type: application/json`.
3. Host must be `127.0.0.1:PORT` or `localhost:PORT`. When Origin is present, it must exactly match `http://<Host>`. Cross-site fetches are refused. Tokens change on process restart; reload the workbench rather than persisting a token.

Bodies must be JSON **objects**, between 1 byte and **16 MiB**, with exactly one valid Content-Length and no Transfer-Encoding. Duplicate object keys, non-finite numbers, invalid JSON and unknown POST fields are rejected. POST query parameters are not supported. Do not include RPC URLs, credentials or signing material in API payloads.

Query keys must be documented, occur once, and total at most 16. IDs and numeric pagination parameters use unsigned ASCII decimal strings of at most ten digits; IDs/limit must be positive, offset may be zero. The workspace validates referenced records and wallet/capture compatibility. Labels/search are at most 256 characters, with no ASCII control characters.

## Read endpoints

| Method/path | Accepted query | Success payload |
| --- | --- | --- |
| `GET /api/session` | None | Session fields above. |
| `GET /api/wallets` | None | `{wallets: [wallet, ...]}` ordered by ascending ID. |
| `GET /api/captures` | Optional `wallet_id` | `{captures: [metadata, ...]}` ordered by descending ID. |
| `GET /api/captures/{id}` | None | Capture metadata plus `snapshot` and `ledger`. |
| `GET /api/movements` | `wallet_id`, `capture_id`, `asset`, `direction`, `status`, `search`, `limit`, `offset` | `{rows, total, limit, offset}`. |
| `GET /api/analytics` | `wallet_id`, `capture_id` | Scoped analytics object below. |
| `GET /api/compare` | Required `before`, `after` capture IDs | Same-wallet comparison below. |
| `GET /api/jobs` | None | `{jobs: [job, ...]}` ordered by descending ID. |
| `GET /api/jobs/{id}` | None | One durable job record. |
| `GET /api/export` | Required `capture_id`; `format=json` (default) or `csv` | Download of analyzed ledger, not raw snapshot: `ledger.json` or `ledger.csv`. |

All successful reads return 200. JSON uses `application/json; charset=utf-8`; CSV uses `text/csv; charset=utf-8`. Export includes an attachment filename.

### Scoping and movement filters

Without `capture_id`, movements/analytics use the latest **imported** capture (largest ID) per selected wallet. Without either scope, all wallets' latest captures are selected. Historical captures are not concatenated. If both IDs are supplied, the capture must belong to that wallet. Empty wallets produce empty scoped results, not fabricated balances.

- `asset`: literal `SOL` for native SOL or exact SPL mint identifier; not a symbol lookup.
- `direction`: `in`, `out`, `zero`.
- `status`: `success`, `failed`. Unknown metadata creates gaps, not guessed successful rows.
- `search`: case-insensitive **literal substring** of signature or mint/asset. SQL wildcard characters are not patterns.
- `limit`: 1–500, default 100. `offset`: nonnegative, default 0.

Movement rows have analyzer fields `signature`, `slot`, `time` (Unix seconds or null), `status`, `asset`, `mint` (null for SOL), `amount_base_units`, `decimals`, `decimal_amount`, `direction`, `wallet_paid_fee_base_units`, `synthetic`, plus `wallet_id` and `capture_id`. Amount/fee base units and decimal amounts are strings; consumers must not convert exact values to binary floating-point. Token rows use an empty wallet-paid-fee field rather than duplicating native fees. Ordering is capture ID descending, slot descending, then signature and row index. `total` is the count after filters, before pagination.

### Analytics

Payload fields: `assets`, `daily`, `transaction_count`, `row_count`, `failed_count`, `gap_count`, `wallet_paid_fees_base_units`, `unknown_time_count`, `synthetic`, `partial`.

Each asset entry has `asset`, `mint`, `decimals`, `inflow`, `outflow`, `net` (decimal strings), and matching `*_base_units` strings. Each daily entry adds `date` (UTC `YYYY-MM-DD`) and `count` (movement rows for that date/asset). Daily data excludes rows with unknown block time; overall assets retain them. Native SOL, wrapped SOL and other mints remain distinct. No USD total or cross-asset aggregate is returned. Conflicting decimals for an asset across the selected scope are rejected rather than summed incorrectly. A scope containing multiple cluster labels is also rejected; select a wallet or capture before aggregating different networks. The [architecture](architecture.md) explains uncertainty and overlapping observations.

### Comparison

`GET /api/compare?before=1&after=2` requires both captures to belong to the same wallet record. It returns:

- `before_id`, `after_id`, `wallet_id`;
- sorted `added_signatures`, `removed_signatures`, `changed_signatures` (available and unavailable observations participate);
- `assets`: `asset`, `mint`, `decimals`, `before`, `after` (net **base-unit strings**), `delta_base_units`, `delta` (decimal string).

Changed signatures reflect normalized evidence differences, not just differing emitted ledger rows. An unavailable observation becoming available counts as changed. Deltas are `after.net - before.net` over the respective observation windows; they are not an incremental cashflow period or proof of current balance. The server does not require chronological IDs or times; `before` and `after` explicitly choose subtraction direction.

## Write endpoints

All fields below are explicitly allowlisted; unknown fields are invalid.

### `POST /api/wallets` → 201

```json
{"address":"11111111111111111111111111111111","cluster":"synthetic","label":"Synthetic example"}
```

Required: `address` (valid base58 32-byte public key). Optional: `cluster` (default `custom`), `label` (default empty string). Clusters: `mainnet-beta`, `devnet`, `testnet`, `custom`, `synthetic`. The legacy packaged synthetic wallet identifier is accepted only in synthetic scope. Returns `{id, address, cluster, label, created_at}`. An existing address/cluster returns the original record, including original label, with the same 201 status; registration does not prove that the address is an ordinary wallet or verify endpoint identity.

### `POST /api/import` → 201

Body: `{"snapshot": <schema-v1 snapshot object>, "label": "optional capture label"}`. `snapshot` is required; label defaults to empty. See [snapshot methodology](methodology.md) and the [packaged example](../src/solana_flow/data/demo.json); discovery may be `wallet-account-keys-only` or `wallet-and-current-token-accounts`.

Returns capture metadata:

`id`, `wallet_id`, `label`, `captured_at`, `imported_at`, `fingerprint`, `transaction_count`, `row_count`, `partial`, `synthetic`.

A duplicate normalized fingerprint returns the existing metadata, still with status 201. Invalid evidence produces no partial import. The resulting capture is immutable; later corrected evidence is another capture. Retrieve `/api/captures/{id}` for the normalized snapshot and analyzer ledger. Ledger extras include `rows`, `assets`, effective `coverage`, `warnings`, `unavailable_signatures`, `gaps`, transaction/failed/unknown-status counts and wallet-paid fees. Unknown evidence is not filled with zero.

### `POST /api/jobs` → 202

```json
{"wallet_id":1,"limit":100,"include_tokens":false}
```

Required: `wallet_id`. Optional: integer `limit` 1–10000 (default 100), boolean `include_tokens` (default false). Returns a queued durable job record; poll the job endpoint for completion. Capture requires a session-configured endpoint and a supported live (non-synthetic) wallet scope. Without capture configuration the server returns 409. Submission is asynchronous, not a completed-capture response.

Job fields are `id`, `wallet_id`, `status`, `limit`, `include_tokens`, `capture_id`, `error`, `created_at`, `updated_at`. Lifecycle: queued → running → succeeded/partial/failed. Terminal jobs are immutable. Only succeeded/partial jobs associate a same-wallet capture; errors are safe diagnostic strings or null. Interrupted queued/running jobs become failed when a new worker starts, and require explicit resubmission. Token-enabled jobs inspect **current** Token/Token-2022 accounts, not historical ownership; this mode always carries a completeness warning.

## Errors and operational boundaries

JSON error payloads have the shape `{"error": "safe message"}`:

| Status | Meaning |
| --- | --- |
| 400 | Invalid JSON/fields/query/filter, missing or incompatible record, invalid evidence, or unavailable job capacity. Unknown record IDs are not distinguished with 404. |
| 403 | Invalid loopback Host/Origin/cross-site request or missing/incorrect session mutation token. |
| 404 | Unknown route. |
| 409 | Capture submission without configured RPC support. |
| 415 | POST content type is not `application/json`. |
| 503 | Storage/I/O unavailable when surfaced as a server storage failure. Workspace validation wrappers can instead surface a storage failure as 400. |

Responses include `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and restrictive Content-Security-Policy. Raw exception details, endpoint URLs and provider errors are not API diagnostics. This does not authenticate imported/provider-controlled identifiers or remove sensitive user labels. The token is CSRF protection for a local process, not a general user-account authorization system. Do not expose this server publicly.
