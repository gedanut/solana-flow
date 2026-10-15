---
phase: 06-workbench
plan: 01
status: complete
requirements-completed: [JOB-01, API-01, UI-01]
---
# Operational workbench

Implemented durable bounded worker and exclusive OS workspace ownership; strict same-origin loopback HTTP API; CLI import/query/compare/serve; shared production browser application with static adapter. Actual browser E2E passed all five flows: inspect/filter/compare/export; exact-integer/duplicate-key import; register/capture/open durable result through a real local RPC fixture; static read-only explorer; mobile axe/overflow. Node precision/state supplemental suite22 passes. Python120 tests pass,96% branch-inclusive coverage.

Independent backend review found malformed missing-meta input bypass. Workspace/CLI/HTTP regressions failed before ledger shape validation fix and passed after. A second independent fix review is part of phase7. Endpoint config remains server memory only; no public hosting installed.
