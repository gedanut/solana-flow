# Bounded wallet + current token-account capture

```python
from solana_flow.discovery import capture
from solana_flow.rpc import RPCClient

snapshot = capture(
    wallet,
    RPCClient(rpc_url),  # Keep credential-bearing URLs private; never publish them.
    limit=100,
    cluster="custom",
    include_tokens=True,
    max_token_accounts=50,
)
```

`capture(wallet, client, *, limit=100, cluster="custom", include_tokens=False,
max_token_accounts=50)` returns the existing **schema v1 snapshot**, accepted by
`solana_flow.ledger.analyze`. It uses only Python's standard library. With
`include_tokens=False`, it delegates to `rpc.fetch` unchanged: no account
enumeration, no extra coverage fields, and the original wallet-only scope.
`include_tokens` must be an actual boolean.

## Discovery and bounds

Token-enabled capture first validates the wallet as a base58 public key decoding
to exactly 32 bytes, `limit` as an integer in **1..10000**, the existing live
cluster allowlist, and `max_token_accounts` as an integer in **1..1000**. Boolean
numbers are rejected. Invalid input performs no RPC calls. The account bound is
relevant only when token discovery is enabled.

It calls `getTokenAccountsByOwner` once for **each** program, even when the first
program response reaches the account bound:

- Original SPL Token: `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`
- Token-2022: `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`

Both requests specify a `programId` filter, `encoding="jsonParsed"`, and
`commitment="finalized"`. A response must contain a `value` array. Each inspected
record needs a valid `pubkey`, an `account.owner` matching the requested program,
and `data.parsed.type="account"` with an object `info`. If `info.owner` is present,
it must equal the queried wallet; an explicit null or mismatched owner is
rejected. A missing `info.owner` is tolerated because the owner-filtered RPC
response is discovery evidence, **not historical attribution evidence**. The
wallet itself is not accepted as a returned token-account address.

The RPC method has no pagination or server-side account-count limit. To bound
local processing, inspect only the first `max_token_accounts + 1` records per
program. Merge valid addresses, deduplicate, sort lexicographically, and retain
at most `max_token_accounts`. Thus the subset is deterministic for fixed provider
responses, but truncation is provider-order-dependent and never represented as
complete enumeration. Malformed records are skipped; valid records and the other
program remain usable. Failures, invalid data, and truncation emit static warnings
and prevent the overall `reached_history` flag.

## Fair history traversal

The ordered sources are the wallet followed by sorted retained token accounts.
Each active source receives one `getSignaturesForAddress` request per round, with
`limit=1` and finalized commitment, using its own `before` cursor. Single-record
pages deliberately trade request efficiency for strict fairness under a small
global budget: a busy wallet cannot consume the budget before another source's
turn. A budget smaller than the number of sources can still stop mid-round; order
is deterministic, not randomized or globally chronological.

The signature limit is **global and unique**, not per account. Overlap advances a
source's cursor without spending another unique slot or fetching its transaction
again. A signature repeated within the same source indicates a stalled/cycling
provider; that source stops, while other sources continue. Empty pages alone mark
provider history exhaustion. A short nonempty page does not prove exhaustion.
Oversized pages, malformed signatures, and transport failures stop only the
faulty source. Unavailable transactions consume the unique budget and are listed
once in `unavailable_signatures`.

With `S <= max_token_accounts + 1` retained sources and global limit `L`, there are
at most `S * (L + 1)` logical signature-page calls, at most `L` transaction calls,
and two account-enumeration calls. The existing RPC client additionally bounds
HTTP retries and each response to 16 MiB. The existing 64 MiB cumulative raw
transaction JSON budget also applies across **all** sources; hitting it stops all
sources and records the current signature as unavailable. This is an evidence
size budget, not an exact final-file byte limit.

## Coverage extension

For token-enabled snapshots, `coverage.discovery` is
`"wallet-and-current-token-accounts"`. Existing coverage fields remain, plus:

- `token_accounts`: unique retained public-key strings in lexicographic order.
- `sources`: wallet first, then those same token accounts. Each record has
  **exactly** these fields:

  | Field | Meaning |
  | --- | --- |
  | `address` | Strictly validated source public key. |
  | `pages` | Completed signature-page RPC responses, including empty, invalid, and stalled pages; failed calls without a response do not count. |
  | `cap_reached` | The global unique-signature budget stopped this still-active source before an empty page. Sources already stopped by failure/stall are not labeled capped. |
  | `reached_history` | This source returned a valid empty signature page. Never a claim of complete wallet history. |
  | `partial` | This source's traversal was interrupted by transport/data failure, pagination stall, or the global byte budget. Transaction availability and attribution gaps are snapshot/ledger-level concerns. |

Overall `pages` is the sum of source page counts; enumeration RPC calls are not
signature pages. Overall `cap_reached` means the global unique limit was reached,
including unavailable transactions. Overall `reached_history` requires **every**
retained source to return an empty page, with no discovery failure or truncation.
It can be true even when transactions are unavailable: it describes traversal,
not data completeness.

Token-enabled snapshots always contain this scope warning:

> Current token accounts only: closed or transferred accounts and prior ownership
> history may be missing; this is not complete wallet history.

The existing ledger treats any warning as partial coverage. To keep raw snapshots
and analyzed ledgers consistent without changing those semantics, token-enabled
snapshots therefore set overall `partial=True` even after clean exhaustion. Use
source flags and warnings to distinguish inherent scope limits from runtime
failures. Never interpret either `reached_history` or `partial` alone as a complete
accounting-history assertion.

The ledger validates both discovery scope values. For the extension it validates
public keys, unique account/source membership, exact source fields, integer page
counts, boolean flags, source/overall boundaries, and the page-count sum. Original
wallet-only snapshots retain their previous schema behavior.

## Ownership and redaction

Current account ownership only expands **where signatures are searched**. It
never fills missing historical token owners or changes per-side owners in
`preTokenBalances` / `postTokenBalances`. The existing ledger continues to omit
uncertain mint movements and emit unknown-owner gaps. Native balances and fees
retain their original semantics: a transaction discovered through a token account
can credit the wallet's tokens even if the wallet is absent from account keys,
without inventing a SOL row or charging the wallet the payer's fee.

Each transaction's returned signature must match its requested signature. Balance
evidence is validated by the ledger before applying the existing allowlisted
analysis projection; logs, instructions, RPC endpoints, account-enumeration
payloads, provider extensions, and detailed provider error text are not retained.
Cross-transaction mint-decimal conflicts produce unavailable signatures rather
than invalid snapshots. Exceptions and warnings never interpolate server text,
endpoint URLs, or rejected discovery addresses.

## Primary references

- [Solana `getTokenAccountsByOwner` RPC documentation](https://solana.com/docs/rpc/http/gettokenaccountsbyowner): owner filter, program filter, parsed request, and response structure.
- [Solana token account documentation](https://solana.com/docs/tokens#token-account): token authority versus account program ownership, and multiple accounts per owner/mint.
- [Official Token-2022 interface program IDs](https://github.com/solana-program/token-2022/blob/main/interface/src/lib.rs): declarations for Token-2022 and the original SPL Token program.

## Verification

```sh
SOLANA_FLOW_REQUIRE_LOCAL_HTTP=1 .venv/bin/python -m unittest discover -s tests -p test_discovery.py -v
```

The tests use deterministic RPC fixtures and a real loopback HTTP JSON-RPC server,
including rate-limit retry. No public RPC endpoint, production credential, signing,
or on-chain write is required.
