# Release notes

## 2.0.1 · Mobile comparison patch

- Wrap the exact comparison JSON using the existing evidence code style. The production browser smoke exposed horizontal overflow after comparing at desktop size and then switching to mobile; a failing-first static-browser regression now covers that state.
- Publish flat checksum filenames so downloaded assets can be verified together with `sha256sum -c SHA256SUMS.txt`.

## 2.0.0 · Investigation Workbench

The project expands from a snapshot/report CLI into a persistent operational application while retaining the v1 analyzer and report commands.

- SQLite multi-wallet workspace with transactional imports, immutable normalized evidence, deduplication and schema guard.
- Search/filter/pagination, exact per-asset and daily aggregation, latest-import scope and mixed-cluster protection.
- Capture comparison across overlapping windows with added/removed/changed signatures and exact asset deltas.
- Classic SPL and Token-2022 current-account discovery for passive token-account references, with global caps/deduplication and source coverage.
- Durable bounded background jobs, exclusive runner ownership, safe failures and explicit restart recovery.
- Loopback HTTP API and real interactive browser workbench: register, import, capture, inspect, compare, export.
- Read-only deterministic synthetic public explorer using the same frontend, not a simulated hosted backend.
- Browser integer-preservation and strict import-path regression coverage, actual HTTP/RPC/SQLite integration, installed-wheel and browser CI.

No custody, signing, pricing, tax classification, complete-history claims or public multi-tenant deployment. Snapshot schema remains version 1; the discovery extension and workspace schema version 1 are documented separately. Existing `demo`, `fetch` without token opt-in, and `analyze` remain available.

## 1.0.0 · Snapshot Analyzer

Exact SOL/SPL movement analyzer, bounded wallet-reference RPC collector, deterministic synthetic fixture, self-contained HTML/CSV/JSON reports and Python 3.11–3.14 verification.
