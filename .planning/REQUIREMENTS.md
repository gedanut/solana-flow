# v2.0 Requirements

- STORE-01: Atomic validated SQLite import, persistent multi-wallet identity, immutable idempotent captures, exact TEXT amounts and schema migration guard.
- QUERY-01: Safe paginated movement filtering, latest-capture-per-wallet defaults to avoid overlap double counts, exact asset and UTC daily analytics.
- DIFF-01: Same-wallet capture comparison: added/removed/changed signatures and exact net deltas, never PnL.
- DISC-01: Current classic SPL and Token-2022 account discovery, globally bounded deduplicated references, explicit source coverage and remaining limitations.
- JOB-01: Durable queued/running/succeeded/partial/failed jobs; one bounded worker; interruption recovery; endpoint URLs never persisted.
- API-01: Loopback-only stdlib HTTP API, strict bounded JSON, safe errors, same-origin mutation protection, no arbitrary files/CORS.
- UI-01: Real wallet/capture navigation, search/filter/pagination, evidence inspector, import/capture/compare/export; loading/empty/error/mobile/accessibility states.
- DEMO-01: Public static explorer runs same frontend with generated synthetic model, visibly read-only synthetic, no pretend live actions.
- RELEASE-02: Regression tests, independent review, built-wheel clean installation, browser E2E, exact-head hosted Python matrix, verified public release and Pages.

Traceability: phase4 STORE/QUERY/DIFF; phase5 DISC; phase6 JOB/API/UI; phase7 DEMO/RELEASE. All choices auto-approved by user's full delegation.
