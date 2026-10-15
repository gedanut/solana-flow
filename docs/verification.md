# v2.0 release verification

These are observed checks, not a claim that passing tests prove complete Solana history or exhaustive security. The previous v1 gate is archived in `.planning/milestones/v1.0/VERIFICATION.md` and the v1 release history.

## Local evidence

| Check | Observed result |
| --- | --- |
| Python suite | **120 passed, zero skips** on Python 3.14.7, including real SQLite, HTTP/RPC, background-job and CLI regressions |
| Coverage | **96% branch-inclusive coverage.py**, 90% threshold; ledger/report/strict JSON/sample modules 100% |
| Lint | Ruff lint and formatting pass |
| Node logic | **18 tests passed**, plus the legacy report's ten control assertions |
| Supplemental Chromium harness | **22 passed**: the same 18 tests plus four DOM/network-body tests using explicitly mocked API routes |
| Actual application E2E | **5 passed**: real local API/SQLite workflows, browser exact-integer import/duplicate-key rejection, asynchronous local-RPC fixture job, static explorer and mobile accessibility |
| Desktop/mobile smoke | 1440×1000 and 390×844: zero axe violations, no document overflow, no console/page errors |
| Lighthouse local application | Performance **83**, accessibility **100**, best practices **100**, SEO **100**; experimental agentic-browsing category **66**; mobile-throttled initial-load performance is reduced by layout shifts (CLS approximately 0.345), not a claim of perfect performance |
| Determinism | Explorer generated into two directories, all files byte-identical; legacy installed-demo HTML still matches committed `docs/demo/index.html` |
| Packaging | Wheel and source distribution built; wheel built from sdist |
| Clean installed-wheel smoke | Python 3.12 isolated environment, no runtime dependency install: demo/replay, import/query/compare, actual `serve`, packaged HTML/JS/CSS, and seeded SQLite API passed |
| Live devnet | Installed v2 CLI used both token programs, discovered six current token accounts, captured three unique transactions with zero unavailable records |
| Independent live reconciliation | Fresh public RPC reads matched all three emitted ledger rows and captured token ownership/base-unit evidence; zero analysis gaps |

The live probe queried the public Vote program address, not an operator wallet. It reached the explicit three-signature cap. Token-enabled coverage was **partial by design** because current-account discovery cannot establish complete wallet history. No live activity is used in the public synthetic explorer. The verification capture stayed in ignored local QA state.

## Failure-first regressions

- The browser originally rounded a one-lamport change above the safe integer range to zero. The actual browser-to-server E2E test failed, then passed after sending original JSON text unchanged. Duplicate keys now reach strict server validation instead of being silently discarded by client parse/serialization.
- Browser response decoding preserves unsafe integer lexemes before evidence display. Supplemental Chromium tests include a slot of `9007199254740993` and native balances `18446744073709551615` / `18446744073709551614`.
- The static search adapter originally matched across concatenated field boundaries. A failing regression established the mismatch with SQL search; it now searches each identifier separately.
- Independent backend review found malformed `meta=null` transactions could bypass shape validation and cause an import traceback/disconnected HTTP response. Failing Workspace, subprocess CLI and actual HTTP regressions reproduced it. Validation now checks account-key structure before recording a missing-metadata gap; valid unknown metadata remains a visible gap.
- Parent review reproduced cross-cluster aggregation and non-ASCII mutation-token request failures. Regression tests now require cluster separation and controlled HTTP 403 responses.
- Job tests cover queue saturation under concurrent submission, exclusive workspace-runner ownership, nonwaiting shutdown, sanitized provider exceptions and storage-transition failures. No claim of exactly-once execution is made.

## Reproduce

```sh
python -m pip install -e . 'ruff>=0.11,<1' 'coverage>=7,<8' 'build>=1,<2'
SOLANA_FLOW_REQUIRE_LOCAL_HTTP=1 coverage run -m unittest discover -s tests -v
coverage report
ruff check .
ruff format --check .
npm ci
npm test
python scripts/generate_explorer.py --output .explorer-check
diff -qr docs/explorer .explorer-check
npx playwright install chromium
npm run test:e2e
WORKBENCH_BROWSER_TESTS=1 node scripts/test_workbench.cjs
python -m build
```

Set `E2E_PYTHON=/path/to/python` for a specific interpreter. E2E starts disposable loopback services on ports 8878/8879 and uses an explicitly local JSON-RPC fixture. It verifies the complete application path without treating a fixture as live network evidence. The separate live devnet probe is described above.

After installing the built wheel into a fresh environment without dependencies, run its interpreter with `-I scripts/smoke_installed.py`. The reported module path must be that environment's `site-packages`, not this checkout. Use equivalent executable paths for your OS.

## Architecture and operational limits

- Providers remain untrusted. Neither normalized captures nor comparison results are cryptographic proof or payment classifications.
- Current token accounts omit closed/transferred accounts and can omit prior ownership history. Source traversal is deterministic and bounded, not a globally newest merged history index.
- Jobs have bounded per-request transport retries/timeouts, not a total deadline or force-cancel of a running thread. Interrupted jobs require explicit resubmission.
- The service is loopback-only, single-user and unencrypted at rest. It is not suitable for public deployment. Linux was exercised locally and in the hosted Python 3.11–3.14 matrix; the Windows advisory-lock branch is not locally exercised.
- Static unknown-time daily buckets and local API unknown-time reporting are intentionally presented differently; amounts retain the same evidence semantics.
- Cold-start layout shift remains a performance improvement opportunity. No material accessibility/overflow/runtime finding remained in the tested desktop/mobile states.

## Publication and CI

The workflow has read-only contents permission, immutable action pins and no untrusted event values interpolated into commands. Matrix checks cover Python 3.11–3.14, branch coverage, Node logic, deterministic explorer generation, build, and clean installed-wheel smoke. A separate Chromium job runs the real application E2E suite. Exact public head status must be checked after pushing; local checks do not establish hosted CI success.

Implementation commit `06470ccb2acbe363a39de88c1ef4762ab8d27c99` passed all four Python checks and Chromium in [hosted run 38662960407](https://github.com/gedanut/solana-flow/actions/runs/38662960407). Independent backend fix review confirmed all six malformed message/account-key variants fail safely through Workspace, CLI and HTTP, while legitimate missing metadata remains a partial capture.

Finish review requested top-level operation entries and visible mobile inspector feedback. Both were reproduced as failing browser assertions, then fixed; the five-test E2E suite and all supplemental tests passed again. Updated desktop/mobile captures have zero axe/overflow/console findings. Exact-head CI for those finish fixes and final publication remain the next gate.

The README image is an actual seeded-application screenshot. Its provenance is in `images/workbench.png.json`; the public explorer is visibly synthetic and read-only.
