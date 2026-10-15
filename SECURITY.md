# Security

Solana Flow is read-only: no wallet connection, keys, signing or transaction submission. The RPC allowlist contains `getSignaturesForAddress`, `getTransaction`, and `getTokenAccountsByOwner`. Python 3.11+ standard library is the entire runtime dependency set. Keep Python security patches current.

## Local application boundary

The workbench binds exclusively to `127.0.0.1`. It is a single-user local process, not a multi-tenant or internet-facing web service. Do not expose it through a public tunnel or reverse proxy. Host and supplied Origin must match the actual loopback authority. Cross-site fetches are refused; mutations require a per-process session token. This is CSRF protection, not a general account/authentication system. Any local process able to contact loopback can access the workspace.

Requests use strict JSON with duplicate-key/nonfinite rejection and a 16 MiB body bound. The server serves only explicitly mapped packaged assets, never arbitrary workspace files. Responses have no-store, nosniff, no-referrer and restrictive CSP headers. No CORS is enabled. Untrusted UI values use text content rather than HTML insertion. CSV protects textual fields from formula injection; amounts stay exact strings in JSON. Review exports before sharing.

## Evidence and privacy

Endpoints live in RPCClient memory and are never written to job/capture records or logs. Prefer `SOLANA_FLOW_RPC_URL` over CLI arguments for private endpoints: shell history and process listings can reveal arguments. Transport errors are fixed safe diagnostics. Captures/imports retain allowlisted balance evidence only; instructions, logs, provider extensions and raw failure content are discarded. A failed status is normalized. This is not a full RPC archive and does not authenticate provider claims.

Warning strings, labels, addresses, signatures and balances are still user/provider-controlled investigation data. Allowlisting is not a promise that arbitrary imported text contains no secrets. The database is not encrypted. Protect its WAL/SHM files and backups as carefully as the main file. No delete/edit API is provided; a local filesystem owner can still modify SQLite directly. The runner's advisory lock coordinates cooperative processes; do not replace/unlink it while the owner runs.

## Availability and uncertainty

Response/file/capture bounds, bounded retries and strict structure checks reduce exposure but do not guarantee availability against every malicious document/provider. Socket timeout is not a total job deadline. Run untrusted workloads with external process memory/time limits. Token discovery covers current accounts only. Missing metadata and unknown ownership produce gaps, never guessed zero movement. A captured transaction is not independently authenticated chain evidence. No price, transfer-intent, tax or portfolio guarantee is made.

Report writers replace their documented output filenames. Choose a directory you control. The workspace creates a database and related files at the explicit path; keep that path outside shared/public folders.

## Reporting

Use GitHub private vulnerability reporting for `gedanut/solana-flow` if enabled. Otherwise open an issue requesting a private channel without exploit details, credentials or private activity. Supported release line: 2.x. The v1 analyzer remains in the current application; updates to the current line are preferred.
