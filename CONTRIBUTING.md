# Contributing

Keep the runtime standard-library only and the project read-only. Changes to attribution or coverage need tests demonstrating the failure first, followed by a fix. Never classify a net movement as a payment, assume mint pricing or hide missing data.

```sh
uv sync --group dev
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run python -m build
```

When development packages are unavailable, `python scripts/check_coverage.py` runs the same suite with stdlib trace and enforces 90% executable-line coverage. It does not measure branches. CI additionally enforces 90% coverage with branches using coverage.py. Socket-restricted environments skip the local HTTP integration test with an explicit reason; mock transport cases still run. CI requires the local HTTP test to run.

```sh
node scripts/test_report_controls.cjs
PYTHONPATH=src python -m solana_flow demo --output docs/demo
python scripts/generate_fixture.py
```

Fixtures are deterministic and synthetic. After fixture edits, regenerate the report and verify that the data, labels and expected counts match. Do not commit captured private wallet data, endpoint URLs with secrets, generated coverage/build output or environment-specific paths. Do not add remote report assets. See [methodology](docs/methodology.md) and [verification](docs/verification.md).

A review should include the observed RED/GREEN result, relevant edge cases, export compatibility, coverage effects and any unverified behavior. Include public-safe examples only. Use the existing repository git identity when committing; never override it with an unrelated account.

## Release publication

Push an annotated `vX.Y.Z` tag only after the branch is verified and package version matches. The release workflow reuses the full Python/browser CI gate, then builds and publishes wheel/sdist/checksums with a short-lived repository token. Verification stays contents-read; only the dependent publishing job has contents-write. Ref values are passed through quoted environment variables and checked against the exact package version. A failed verification must not produce a Release. Verify the public tag target, workflow conclusion, Release assets and downloaded checksums before announcing success.

## Workbench and browser checks

Node/Playwright are development-only. Run `npm ci`, `npm test`, `python scripts/generate_explorer.py`, `npx playwright install chromium`, then `npm run test:e2e`. Set `E2E_PYTHON=/path/to/python` when the harness should start a specific interpreter. Keep ports 8878/8879 free. The E2E suite creates disposable SQLite state and an explicitly local RPC fixture. It exercises actual HTTP import/query/compare/export and job workflows, not live private activity. `WORKBENCH_BROWSER_TESTS=1 node scripts/test_workbench.cjs` additionally tests browser precision and UI state against mocked routes.

Generate the public explorer twice into separate directories and compare byte-for-byte. Never hand-edit totals. Protect database/WAL/lock files and user captures; `.gitignore` is not a secret scanner. Fresh distribution verification uses `python -I scripts/smoke_installed.py` with an isolated interpreter where the built wheel was installed without dependencies. It exercises packaged commands and starts the installed HTTP application, including HTML/JS/CSS resources.
