---
gsd_state_version: '1.0'
milestone: v2.0
milestone_name: Investigation Workbench
status: completed
current_phase: 7
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 4
  completed_plans: 4
  percent: 100
---
# Project State

## Current Position
Phase: 7 of 7 (Public proof and release)
Plan: 1 of 1
Status: Complete, v2.0.1 published and verified

## Delivered outcome
A real persistent local-first Solana investigation application, plus a functional read-only synthetic public explorer. Register wallets, import immutable captures, query/filter exact movements, inspect source evidence, compare captures, export and run bounded durable read-only RPC jobs. Python runtime remains standard-library only. No signing/custody, public writable service or completeness claim.

Manually adapted GSD execution with native state recognition and persisted requirement/phase evidence. Prior v1 milestone remains archived. User delegated product/design/implementation/publication under gedanut with no decision checkpoints.

## Acceptance evidence
120 Python tests,96% branch coverage;18 Node logic plus4 supplemental browser tests;5 real application E2E. Clean wheel/sdist and installed-service/assets/command smoke. Bounded live devnet3-reference capture with6 current token accounts and independent fresh-RPC reconciliation of3 ledger rows. Independent backend fix verification and bounded UI finish review passed, including an independent5-test E2E run. Official DESIGN.md lint0errors/0warnings,46 DTCG tokens and source-hashed design documentation.

Actual inspected desktop/mobile states: axe0/nooverflow/noerrors. Local initial-load Lighthouse83/100/100/100; cold CLS~0.345 remains documented, experimental agentic category66. A production-only expanded-comparison overflow was reproduced by a failing-first static E2E resize assertion and fixed in2.0.1. Public browser root redirect/read-only controls/inspection/comparison/filter/mobile reveal now pass with document width390 at viewport390.

## Publication
Release: https://github.com/gedanut/solana-flow/releases/tag/v2.0.1
Explorer: https://gedanut.github.io/solana-flow/explorer/
Source tag: dd8441eaa6100aaa06c95a805baf019a3a738a4f
CI: https://github.com/gedanut/solana-flow/actions/runs/38665325714
Pages: https://github.com/gedanut/solana-flow/actions/runs/38665326065
Release gate: https://github.com/gedanut/solana-flow/actions/runs/38665403418

All listed runs succeeded at that exact source head. Read back annotated tag, Release and assets; downloaded wheel/sdist/checksums, checked API digests/sizes and native sha256sum verification. Downloaded wheel2.0.1 installed without dependency resolution into a fresh Python3.12 environment; real demo/replay/import/query/compare/serve/packaged assets/SQLite smoke passed. All4 served explorer files matched repository bytes. Subsequent commits close documentation only; released code remains immutable at the tag. Check final documentation-head CI before announcing task completion.

## Operational boundaries
Dedicated SSH and GitHub's tag-triggered short-lived repository token handled publication, not an unrelated personal account. Ordinary verification contents-read; only the dependent release-publish job contents-write. No endpoint credentials or private captures committed. Synthetic public data stays labeled. Current-token-account discovery omits closed/transferred accounts. Jobs do not provide a total deadline or force-cancel. Windows advisory-lock branch was not locally exercised.

No follow-up implementation is required by this milestone. Runtime QA state remains ignored; task-owned port8876 server is stopped during final cleanup. E2E and installed smoke manage their own disposable servers.
