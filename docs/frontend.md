# Investigation workbench frontend

The shared browser application is `src/solana_flow/assets/workbench.js`, with
`workbench.html` and `workbench.css` alongside it. It has no third-party runtime
dependencies and requires a modern browser with `fetch`, `BigInt`, and file APIs.
The same application supports the local SQLite workspace and the read-only
synthetic explorer. See [API](api.md), [workspace semantics](workspace.md), and
[methodology](methodology.md) for the backend and evidence contract.

## Modes and workflows

- **Local:** obtains a same-origin session from relative `api/session`. Reads use
  relative API paths; mutations include JSON content type and the session token.
  Register wallets, import snapshot JSON, inspect capture evidence, query and
  export movements, compare captures, and follow background capture jobs.
- **Static:** loads `demo-data.json`. An explicit static document mode skips the
  session probe; otherwise only a session **404** triggers static fallback.
  Service errors do not silently switch to demonstration data. Registration,
  import, and capture controls are disabled. Both `post` and `importSnapshot`
  reject without sending a write request.
- RPC capture availability comes from `session.capture_enabled`. A local service
  without an RPC endpoint still supports imports and reads. Endpoint credentials
  are configured on the server, not entered into the page.
- Jobs refresh every five seconds while the page is visible. A terminal
  **partial** job displays `partial`, not `unknown`, and its saved capture can be
  opened. A capture job is not a transaction submission or signing operation.

## Capture selection and query semantics

Capture menus are sorted by descending numeric **capture ID**, matching the
backend's latest-import rule. A snapshot's `captured_at` is its source capture
time, not import recency. By default the largest ID is selected even if its
source timestamp is older. The context identifies the latest or historical
import. Import/job navigation can explicitly select an older capture, and the
comparison controls initially select the preceding import and latest import.

Movement filters intersect before pagination. Search is a case-insensitive
literal substring in **either** signature or mint/native asset, never across
concatenated fields and never in amounts. Counts describe matching movement
rows. Overview totals remain scoped to the complete selected capture, not the
filtered page. Exact totals use `BigInt` base units, kept separate by mint and
decimals; no floating-point amounts or cross-asset total are computed.

Static analytics retain an `Unknown` daily bucket for undated rows; the local
API instead reports unknown-time information separately and excludes those
rows from dated daily buckets. Static daily counts remain per-asset movement
counts, not transaction counts. Static comparison includes source signatures
with no movement rows and unavailable signatures, and sorts added/removed/changed
signature lists deterministically. Changed evidence is not proof of a chain
reorganization, and per-asset deltas are not current balances.

## Preserving evidence at the browser boundary

### Import: send original JSON, not a reconstructed snapshot

The import handler reads file text and uses `JSON.parse` only to reject malformed
syntax. It **does not use that parsed value**. `adapter.importSnapshot(raw, label)`
sends:

```js
'{"snapshot":' + raw + ',"label":' + JSON.stringify(label) + '}'
```

Only the label is serialized. Snapshot whitespace, duplicate keys, integer
lexemes above JavaScript's safe range, and fractional/exponential syntax reach
the backend unchanged. This lets strict server decoding reject duplicate keys
and ledger validation reject invalid numeric types, rather than silently fixing
or rounding the submitted evidence. Client syntax checking is not schema or
strict-JSON validation; server validation remains authoritative. A successful
import reloads the saved capture from the workspace. The UI reserves envelope
space below the server's 16 MiB body limit; the server enforces the final size.

### Responses: protect native balances and slots before decoding

Every JSON response, including static demo captures, is read with `response.text()`
and `parseLosslessJSON`, **not `response.json()`**. The helper first validates the
original JSON syntax, then lexically recognizes string literals and numeric
tokens. Plain integral tokens outside `[-9007199254740991, 9007199254740991]` are
quoted before the final parse, using `BigInt` comparisons. Unsafe integers
therefore become exact decimal strings in the presentation model.

For magnitude safety, fractional/exponential tokens whose parsed magnitude is
at least `Number.MAX_SAFE_INTEGER`, or is nonfinite, are also retained as their
original token strings: `1e30` stays `"1e30"`, not a rounded integer. Ordinary
fractions/exponents remain JSON numbers (`1.25`, `1e-3`, `1e3`). This is integer
and large-magnitude preservation, **not arbitrary-precision decimal arithmetic**.
String contents, escapes, and existing amount strings are unchanged. Validation
before rewriting ensures malformed numeric object keys cannot become valid
quoted keys. The validation parse is temporary and is never reserialized or
used as evidence.

The inspector projects the selected source transaction's account keys, slot,
time, version, error/fee and pre/post native/token balances, including loaded
addresses. Missing source evidence is explicit. Provider logs are not displayed.
Its formatted JSON represents unsafe numbers as strings to preserve every digit;
it is a presentation view, not a byte-identical source archive. Local exports are
server downloads; static exports serialize the already precision-protected
ledger. CSV retains amount text and neutralizes formula-like identifier fields.

## Verification

Run from the repository root:

```sh
node --check src/solana_flow/assets/workbench.js
node --check scripts/test_workbench.cjs
node --test scripts/test_workbench.cjs
WORKBENCH_BROWSER_TESTS=1 node --test scripts/test_workbench.cjs
```

Verified results for this frontend change:

- Both syntax checks exit **0**.
- Default Node run: **18 tests, 18 pass, 0 fail**.
- Browser-enabled run: **22 tests, 22 pass, 0 fail** (the same 18 plus four
  Chromium browser tests).

Browser tests need Playwright and an installed Chromium. The harness resolves
Playwright from the pinned repository development dependency (`npm ci`);
browser dependencies are test-only. The separate real-server end-to-end suite
is run with `npm run test:e2e` and exercises actual HTTP/SQLite and a local RPC
fixture rather than mocked API routes.

Coverage includes the original search-boundary regression; intersecting filters
and pagination; exact amount formatting, aggregation and CSV; source-aware,
sorted comparison; static no-write behavior and session fallback; raw import
body equality including duplicate keys and unsafe integers; positive/negative
safe boundaries, escaped strings, decimal/exponent tokens and malformed JSON;
and exact capture slot/pre/post balance decoding in both adapters.

The four browser tests exercise:

1. Static evidence inspection with exact `9007199254740993` slot and
   `18446744073709551615` / `18446744073709551614` balances, search/reset,
   JSON download, disabled mutation controls, and no horizontal overflow at
   390 × 844.
2. File upload with malformed JSON producing no POST, duplicate-key preservation
   and displayed server rejection, exact unsafe integer request bodies, then
   successful capture reload.
3. `partial` job rendering and navigation to its capture.
4. Latest-import selection despite conflicting source timestamps, comparison
   defaults, and manual historical selection.

Browser API routes use explicit synthetic fixtures and mocked responses; these
checks verify the real DOM, fetch bodies and rendering, **not live RPC capture
or backend validation correctness**. Response mocks in Node tests are real
`Response` objects with text bodies, avoiding a `json()`-only shortcut that would
hide precision loss. No browser page errors were observed by the four tests.
