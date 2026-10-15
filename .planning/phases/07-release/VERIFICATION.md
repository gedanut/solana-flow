---
status: passed
phase: 07-release
requirements: [DEMO-01, RELEASE-02]
---
# Final acceptance

- Source tag: `v2.0.1` -> `dd8441eaa6100aaa06c95a805baf019a3a738a4f` (annotated tag read back and peeled to exact commit).
- Hosted main CI: https://github.com/gedanut/solana-flow/actions/runs/38665325714 success; Python3.11/3.12/3.13/3.14 and Chromium all passed.
- Hosted Pages: https://github.com/gedanut/solana-flow/actions/runs/38665326065 success.
- Full reusable gate plus publication: https://github.com/gedanut/solana-flow/actions/runs/38665403418 success.
- Public Release: https://github.com/gedanut/solana-flow/releases/tag/v2.0.1 read back as non-draft/non-prerelease with three uploaded assets.
- Public explorer: https://gedanut.github.io/solana-flow/explorer/ . All four source files match served bytes; root redirect, disabled writes, two synthetic wallets, inspect/compare/filter/mobile reveal pass actual production Chromium smoke.
- Downloaded all three actual Release assets; API size/digest and manifest checks passed. Native `sha256sum -c SHA256SUMS.txt` reports wheel/source archive OK.
- Installed downloaded wheel2.0.1 without dependencies in fresh Python3.12 environment. `python -I scripts/smoke_installed.py` passed demo/replay, import/query/compare, real server, packaged HTML/JS/CSS and seeded SQLite API from site-packages, not editable source.
- Local final source:120 Python tests,96% branch-inclusive coverage;22 supplemental Node/Chromium tests;5 actual E2E; Ruff lint/format; deterministic regeneration; official DESIGN.md lint all pass. Supplemental22 includes18 logic and4 mocked-route browser tests; it is separate from actual E2E5, not a claim of22 real-service flows.
- Independent backend malformed metadata fix verified across six variants and legitimate missing-meta control. Independent UI finish review SHIP, fresh5 E2E pass,390/1180/1181/1440 checks. Later comparison-overflow fix has its own failed-then-passed E2E regression and successful public smoke.

Local initial-load Lighthouse83 performance/100accessibility/100bestpractices/100SEO; CLS~0.345 and experimental agentic66 remain documented. Current-account discovery, partial capture, lack of total job deadline, local-only single-user server and unexercised local Windows lock branch remain explicit limits, not completeness claims.

Scope gate: evaluators can inspect and use persistence, exact queries, comparisons, discovery, durable workers, protected API and browser workflows, and try a visibly synthetic public explorer. This meets the requested expansion beyond a report facade. Documentation-only closure commits after the immutable release tag do not change its artifacts; final head CI is checked before announcing completion.
