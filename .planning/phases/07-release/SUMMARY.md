---
phase: 07-release
plan: 01
status: complete
requirements-completed: [DEMO-01, RELEASE-02]
---
# Public proof and release

Delivered deterministic two-wallet/four-capture synthetic explorer on GitHub Pages, using the same assets as the local operational application. Preserved the original portable report. Published v2.0.0, then a non-retargeted v2.0.1 patch after production browser verification found expanded comparison JSON overflow on desktop-to-mobile resize. A failing-first browser regression reproduced it; the existing wrapped evidence style fixes it.

v2.0.1 source dd8441eaa6100aaa06c95a805baf019a3a738a4f passed exact-head hosted Python3.11–3.14 matrix plus Chromium, Pages deployment and a tag-triggered reusable full verification gate before release publication. All three public assets were downloaded and verified; the downloaded wheel installed and passed real command/service/SQLite/resource smoke in a clean environment. Public application root/readonly/inspection/comparison/filter/mobile workflow passed, and all four served explorer files matched source bytes.

120 Python tests,96% branch coverage;18 Node logic plus4 supplemental browser tests;5 real local/static E2E flows. Independent backend crash/fix verification and bounded UI finish SHIP review completed. GSD was adapted manually with native smart-entry state checks, not every native command gate.

Release automation uses a short-lived GitHub repository token in a dependent publish-only contents-write job; verification stays read-only. No personal credentials, live user activity or writable public deployment. See VERIFICATION.md for exact run URLs and docs/verification.md for detailed limitations and reproduction.
