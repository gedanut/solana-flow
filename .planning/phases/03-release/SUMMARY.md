# Phase 3 evidence

Builder-stage observations below are historical. Parent release verification subsequently passed all 45 tests with no skips, actual coverage.py 99%, local HTTP and live devnet checks, browser and accessibility verification. See docs/verification.md for current evidence.

RED: report tests could not import solana_flow.report; implementation produced 15 passing combined tests. CLI tests then failed to import solana_flow.cli; implementation produced 18 passing tests.

Further RED: malformed subcommand arguments returned argparse's default code 2 instead of safe code 1 (subparser diagnostics could echo supplied text). GREEN: a safe parser subclass now applies to every subcommand, and the secret-redaction regression passes.

Final suite: 40 tests, 39 passing and one environment skip; stdlib trace executable-line coverage 687/692 (99.3%), above the 90% gate. Ruff lint/format passed; actual bundled JS passed ten filtering assertions. CSP hash and escaping tests pass. Wheel and sdist built; fresh no-index installed-wheel demo and replay worked.

Verification deviations: PyPI DNS blocked installing coverage.py/build, so offline uv plus cached setuptools built distributions and stdlib trace measured line coverage. Branch coverage and the Python 3.11–3.14 hosted matrix are configured, not claimed as run. Chromium launch failed with socket permission error; no browser pass is claimed. Action API/git-ref lookup was unavailable; immutable pins were checked against official release-linked commit pages instead. See docs/verification.md for reproducible commands and remaining checks.
