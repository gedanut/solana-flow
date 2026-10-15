# Roadmap

## Milestones
- v1.0 Snapshot Analyzer: phases 1–3 shipped, archived in milestones/v1.0.
- v2.0 Investigation Workbench: phases 4–7 active.

## Phases
- [ ] **Phase 4: Persistent workspace** - SQLite import, multi-wallet queries, exact analytics, capture comparisons.
- [ ] **Phase 5: Expanded discovery** - Bounded classic SPL/Token-2022 multi-source capture.
- [ ] **Phase 6: Operational workbench** - Durable jobs, secure loopback API, interactive application.
- [ ] **Phase 7: Public proof and release** - Static explorer, independent review, E2E, packaging, hosted CI, release.

### Phase 4: Persistent workspace
Goal: Investigate persistent captures without double counting overlapping windows.
Requirements: STORE-01, QUERY-01, DIFF-01
Success criteria: atomic rollback, idempotent imports, reopen persistence, exact large amounts, latest-per-wallet query, deterministic diffs.
Plans: 1

### Phase 5: Expanded discovery
Goal: Include passive receipts visible through currently owned token accounts.
Requirements: DISC-01
Success criteria: both programs enumerated, cap/dedupe, passive receipt attribution, explicit failures/truncation, v1 compatible.
Plans: 1

### Phase 6: Operational workbench
Goal: One-command real application completes import, inspect, compare and capture workflows.
Requirements: JOB-01, API-01, UI-01
Success criteria: actual HTTP tests, durable jobs/recovery, origin defenses, safe endpoints, responsive accessible browser workflows.
Plans: 1

### Phase 7: Public proof and release
Goal: Publish a coherent usable artifact and reproducible evidence.
Requirements: DEMO-01, RELEASE-02
Success criteria: functional static explorer, clean installed-wheel smoke, independent review, hosted matrix passes at published head, read-back of release and Pages.
Plans: 1
