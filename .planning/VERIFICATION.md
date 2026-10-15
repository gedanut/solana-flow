# v2.0 acceptance verification

- STORE-01 / QUERY-01 / DIFF-01: real SQLite persistence, atomic validation/rollback, normalized dedupe, exact large amounts, latest-per-wallet scope, mixed-cluster guard and source-aware capture diffs pass tests.
- DISC-01: both token program enumeration, global bounds/dedupe, passive receipts, per-source coverage, explicit uncertainty pass tests. Installed CLI live devnet captured3 transactions across wallet/current-account references, discovered6 accounts, zero unavailable/gaps; fresh raw RPC independently reconciled3 ledger rows.
- JOB-01 / API-01 / UI-01: durable exclusive worker, safe errors/recovery, loopback API protections, actual browser workflows and supplemental numeric-boundary tests pass. Desktop/mobile axe0/nooverflow/noerrors. Local Lighthouse81 performance/100 accessibility/100 bestpractices/100 SEO, cold layoutshift remains known limit.
- DEMO-01: deterministic two-wallet/four-capture synthetic explorer generated from real analyzer/workspace; byte-identical regeneration and static browser workflow pass. No pretend hosted mutations.
- RELEASE-02:120 Python tests,96% branch coverage;18 Node logic plus4 supplemental browser tests;5 actual E2E pass; Ruff clean; wheel/sdist and isolated wheel commands/service/resources smoke passed. Independent follow-up review and exact-head hosted CI/Pages/tag publication remain final gates.

This is manually adapted GSD execution with persisted requirement traceability and native state discovery checks. Prior v1 evidence remains archived; it is not used to claim v2 verification.
