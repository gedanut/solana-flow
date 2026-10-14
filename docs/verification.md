# Release verification

## Local release gate

Actual checks run on Python 3.14.7 against the release implementation:

| Check | Observed result |
| --- | --- |
| unittest suite | **45 passed, zero skips**, including real local HTTP rate-limit and redirect integration tests |
| Coverage | coverage.py line-and-branch report **99%**, threshold 90%; ledger/CLI/report/strict JSON modules at 100% |
| Ruff | Lint and formatting passed |
| Report controls | Ten Node assertions plus real Chromium search/asset/direction/status/combined-empty tests |
| Browser exports | CSV download byte-matched the generated file |
| Browser privacy | Zero HTTP requests from the offline report; zero runtime errors |
| Desktop and mobile | 1440px and 390px, zero axe violations, zero document overflow |
| Lighthouse | Performance 100, accessibility 100, best practices 100, SEO 91; localhost synthetic report |
| Packaging | Wheel and source distribution built; wheel built from sdist |
| Fresh wheel install | No-index/no-deps install, isolated module invocation and console command succeeded; demo and replay byte-matched |
| Live devnet | Installed release CLI fetched eight transactions and produced 16 ledger rows; zero unavailable records or analysis gaps |
| Live reconciliation | All eight SOL rows and wallet-paid fees independently compared with fresh public RPC responses; captured token amounts and owners matched original balance evidence |
| Review regressions | Duplicate RPC JSON keys/nonfinite numbers, malformed URL diagnostics, extension/log/error redaction, versioned keys and uncertainty preservation covered |

The live probe used a public devnet fee-payer address discovered from System Program activity, not an operator wallet. One observed transaction was [4b75DxQyCnMTihECTkogs5N6kGEa8hCQG7tTHUn7nNFLbhTZqiiwV7FeLneimTbi7i6kRmxCDCvWZPS2ywGmJ7Du](https://explorer.solana.com/tx/4b75DxQyCnMTihECTkogs5N6kGEa8hCQG7tTHUn7nNFLbhTZqiiwV7FeLneimTbi7i6kRmxCDCvWZPS2ywGmJ7Du?cluster=devnet). Devnet providers may later prune the record.

Coverage was capped at eight signatures and uses wallet-account-keys-only discovery. Successful capture does **not** mean complete wallet history. The public report remains a conspicuously **SYNTHETIC** offline example, never those live transactions.

Hosted Python 3.11–3.14 CI is configured; consult the [exact workflow run](https://github.com/gedanut/solana-flow/actions/workflows/ci.yml) for current remote results. Local results alone do not prove every supported interpreter passed hosted CI. Mainnet RPC availability was not established by the release gate.

## Reproduce

```sh
python -m pip install . ruff coverage build
SOLANA_FLOW_REQUIRE_LOCAL_HTTP=1 coverage run -m unittest discover -s tests -v
coverage report
ruff check .
ruff format --check .
node scripts/test_report_controls.cjs
python -m build
python -m venv .release-venv
.release-venv/bin/python -m pip install --no-index --no-deps dist/*.whl
.release-venv/bin/python -I -m solana_flow demo --output .release-demo
.release-venv/bin/solana-flow analyze .release-demo/snapshot.json --output .release-replay
cmp .release-demo/ledger.json .release-replay/ledger.json
```

Use equivalent Scripts paths on Windows. Build tools must already be available for offline builds. A Python 3.12+ stdlib executable-line fallback is available as `python scripts/check_coverage.py`; it is not a replacement for the branch-inclusive CI gate.

## Live probe

```sh
solana-flow fetch A5axoZYmALC4RztcJhxaNTQNHL3ejy2BYVQPewYAEmfJ \
  --rpc-url https://api.devnet.solana.com --cluster devnet \
  --limit 8 --output devnet-snapshot.json
solana-flow analyze devnet-snapshot.json --output devnet-report
```

This public devnet address can change activity or cease to be useful; the command is a probe, not a guaranteed fixture. Check exit status, coverage and warnings. Exit 2 preserves partial output. Never publish private wallet snapshots as verification material.

For each signature independently request the original RPC result. Compare wallet account index, pre/post lamports, fee payer, owned token mint/index/owner/base units/decimals, status and time. Provider responses remain untrusted and are not cryptographic proof.

## Browser inspection

Open `docs/demo/index.html` directly. Confirm the synthetic label, four asset summaries, 21 rows and one failed transaction. Filters affect the table only. Test combined filters and empty state. The ledger scrolls horizontally inside its own region on mobile. CSV is embedded and works from a standalone HTML; JSON is a sibling file, so share the report directory when that download matters.

The [README screenshot](images/report.png) is captured from the generated report, not an illustration. Assets and report code are bundled locally, with a restrictive hashed CSP and no analytics or external resources.

## CI provenance

CI has `contents: read`, does not persist checkout credentials and builds/tests each supported Python interpreter. Immutable action pins were independently verified via the unauthenticated GitHub tag-reference API:

- [checkout v4.2.2](https://github.com/actions/checkout/commit/11bd71901bbe5b1630ceea73d27597364c9af683)
- [setup-python v5.6.0](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065)
- [upload-artifact v4.6.2](https://github.com/actions/upload-artifact/commit/ea165f8d65b6e75b540449e92b4886f43607fa02)

`docs/demo/` is regenerated by the packaged tool. CI compares it against an isolated wheel-installed demo and uploads distributions plus generated report artifacts.
