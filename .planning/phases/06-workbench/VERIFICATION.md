---
status: passed
phase: 06-workbench
---
# Acceptance evidence

`E2E_PYTHON=.venv/bin/python npx playwright test`:5 passed. `WORKBENCH_BROWSER_TESTS=1 node scripts/test_workbench.cjs`:22 passed. Full unittest120 pass. Real API->worker->RPC->SQLite integration covers passive token receipt exact huge units/reopen. Worker tests cover concurrent queue bound, exclusive ownership, shutdown/recovery and safe state-transition failures. API tests cover strict JSON, unsafe host/origin/token, query/asset map and export boundaries. Actual desktop/mobile axe0, nooverflow/noerrors. See docs/verification.md for limits and reproducible commands.
