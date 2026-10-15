# Methodology and snapshot contract

## Attribution, not interpretation

For wallet W, native movement is `postBalances[index(W)] - preBalances[index(W)]`, in lamports, with nine decimals. Native lamports held by token accounts are not consolidated into the wallet’s SOL row. Native change can include rent funding/refunds, fees, rewards or other effects; it is not a decoded transfer amount.

For mint M, token movement is `sum(post amounts where owner == W and mint == M) - sum(pre amounts where owner == W and mint == M)`. One row is emitted per observed owned mint per transaction, including zero changes. No ticker or price lookup occurs. Wrapped SOL remains its own SPL mint even when its decimals match native SOL.

Each side is attributed independently. If an account changes owner from W to another owner with unchanged balance, the ledger records a negative change in W’s attributed holdings; that is not evidence of a payment. When both records exist, a missing owner is never filled from the other side. Unknown ownership in any account for a mint suppresses that entire transaction/mint, rather than reporting a misleading partial net change.

When both token arrays are supplied, an absent record on one side is treated as a new/closed account with no token balance on that side. If an entire token array is missing/null, SPL attribution is unavailable and a gap is recorded. A missing/null `meta` creates an all-assets gap with unknown status. Malformed supplied fields are rejected, not replaced with zeros. Fee totals cover available metadata only.

Failed transactions are counted from `meta.err != null`; their recorded balances are still analyzed. Wallet-paid fees use the first resolved account key as fee payer and are counted once per unique transaction, including failed ones. Fees are informational, already reflected in native changes; no attempt is made to separate fee-only effects, rent, swaps, burns or income.

## Key resolution and precision

String `accountKeys` use raw indexing: append `loadedAddresses.writable`, then `loadedAddresses.readonly`. Object keys (`pubkey`) are parsed/resolved keys and are not appended again. The resolved key count must match both native balance arrays; duplicate keys and invalid indices are rejected. A raw versioned result lacking necessary loaded keys fails validation rather than shifting token indices.

Token amounts must be unsigned integer strings (1–100 digits); native balances/fees/slots are nonnegative integers, never booleans. Decimals must be 0–255 and consistent for each mint throughout the snapshot. Duplicate token account indices on a side, even identical duplicates, are rejected. Conflicting mints across sides of one account index are rejected. Amounts use integer arithmetic; formatting pads/splits digit strings. No binary float or Decimal arithmetic enters a ledger amount or total. SVG bar widths use integer ratios only for presentation.

Repeated identical signatures are deduplicated. A repeated signature with any differing transaction payload is rejected. Null block time stays JSON `null`, an empty CSV field and “Unknown time” in HTML. Ledger row order follows capture order, with native first and token mints sorted; output has no generation timestamp and is byte-deterministic for the same snapshot.

## Schema v1

The CLI reads UTF-8 JSON up to 128 MiB. Duplicate JSON keys and non-finite JSON numbers are rejected. The top-level snapshot contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `wallet` | Supplied address; live fetch validates a base58 32-byte key |
| `cluster` | `mainnet-beta`, `devnet`, `testnet`, `custom` or `synthetic`; explicit provenance label |
| `synthetic` | Boolean, true exactly when cluster is `synthetic` |
| `captured_at` | ISO-8601 timestamp including timezone |
| `coverage.limit` | Requested unique-signature cap, not an exhaustive-history claim |
| `coverage.pages` | Number of returned signature-page responses |
| `coverage.cap_reached` | Capture stopped at cap |
| `coverage.reached_history` | Provider returned an empty signature page |
| `coverage.partial` | Transport, availability or analysis gaps; false never means complete wallet history |
| `coverage.discovery` | `wallet-account-keys-only` or `wallet-and-current-token-accounts`; see discovery extension below |
| `transactions` | Allowlisted `getTransaction` analysis objects, not JSON-RPC envelopes or complete RPC archives |
| `unavailable_signatures` | Discovered signatures without usable transaction results |
| `warnings` | Safe diagnostic strings, never endpoint URLs or raw RPC error messages |

See the [packaged fixture](../src/solana_flow/data/demo.json) for a complete example. The analyzed ledger JSON adds `rows`, `assets`, `transaction_count`, `failed_count`, `unknown_status_count`, wallet-paid fees, `gaps` and effective coverage. Base units and decimal amounts are strings to preserve precision for downstream consumers. SOL rows have `mint: null`; SPL identifiers are never aliased to SOL. Each row carries its synthetic flag. Fetch retains slot/time/version, resolved or raw account keys, first signature, fee, native balances, token index/mint/owner/base units/decimals and loaded addresses. It drops instructions, logs, arbitrary provider metadata and raw error content. `meta.err` is normalized to null or a failed-status marker. Missing metadata and ownership stay unknown. Manually imported snapshots can contain extra fields; the analyzer ignores them but does not rewrite the input file.

## Capture and trust boundaries

Fetch requests `getSignaturesForAddress` with finalized commitment and a `before` cursor, then `getTransaction` with `encoding: jsonParsed`, `maxSupportedTransactionVersion: 0` and finalized commitment. Pages are at most 1,000 requested signatures. It deduplicates signatures, stops on a stalled/repeated cursor and never assumes that a short page means exhaustion. Null/pruned/invalid/unavailable transactions are recorded explicitly. Unsupported transaction versions become unavailable records, not guessed ledgers.

Each call defaults to a 20-second socket timeout, at most three retries after the first attempt, exponential backoff starting at 0.5 seconds (capped at eight seconds), and numeric Retry-After handling capped at eight seconds. Retryable HTTP statuses are 408/429/500/502/503/504; RPC codes 429/-32005/-32004/-32603 are retried. Other errors fail safely. Response bodies are capped at 16 MiB. Captured transaction JSON has a 64 MiB budget; reaching it stops discovery with a partial flag and warning. Fetch writes compact JSON so its output stays below the 128 MiB replay limit. Redirects are refused. A socket timeout is not a total capture deadline: many sequential requests can take time, and a trickling server can extend a read. Use an external process deadline for untrusted providers.

The endpoint and server error text never enter diagnostics or capture metadata. A malicious provider can still lie or put sensitive text in allowlisted identifiers. Dropping logs and extensions reduces accidental disclosure; it does not authenticate provider data or make arbitrary snapshots safe to publish. Do not publish private snapshots without reviewing them. Reports intentionally expose the analyzed address, signatures and amounts. HTML escapes untrusted strings; CSV prefixes potentially formula-leading textual identifiers with an apostrophe. This changes those CSV identifiers; JSON is the lossless export. Spreadsheet auto-conversion of large numbers is outside CSV’s control: import numeric columns as text when precision matters.

Provider responses are not cryptographic evidence. Captures are sequential rather than an atomic chain snapshot. Program parsing, historical token-account enumeration, forks beyond finalized provider claims, Token-2022 extension semantics (including withheld fees/confidential balances), fiat valuation and tax treatment are outside scope. Totals cover only attributable observed balances.

## v2 current-account discovery and persistence

Opt-in `--include-tokens` (or a token-enabled background job) enumerates current accounts from both classic SPL and Token-2022 programs with `getTokenAccountsByOwner`. It searches the wallet and bounded discovered addresses, deduplicates signature overlap globally, and retains per-source coverage. See [discovery](discovery.md) for traversal and bounds. This does not recover closed/transferred accounts or replace historical per-side owner metadata. Its scope warning makes the saved result partial even after clean page exhaustion.

The extension adds `coverage.token_accounts` and `coverage.sources` with address, pages, cap/history/partial flags. These fields are validated, not trusted as proof of exhaustive history. The legacy wallet-only contract remains supported. Offline reports describe the actual selected discovery mode.

Workspace imports normalize allowlisted evidence, reanalyze it and atomically persist immutable snapshots, derived ledgers and exact movement rows. Arbitrary input files are not rewritten; provider extensions are discarded from stored evidence. Latest means highest imported capture ID, not newest block time. Capture comparisons use normalized evidence, including unavailable observations. Different cluster assets are never combined by analytics. See [workspace](workspace.md) and [API](api.md).

## Primary protocol references

- [Solana JSON structures](https://solana.com/docs/rpc/json-structures)
- [getTransaction](https://solana.com/docs/rpc/http/gettransaction)
- [getSignaturesForAddress](https://solana.com/docs/rpc/http/getsignaturesforaddress)
