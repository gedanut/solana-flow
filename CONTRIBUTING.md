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
