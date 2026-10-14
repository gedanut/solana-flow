# Phase 2 evidence

RED: RPC tests failed to import solana_flow.rpc.
GREEN: initial capture implementation brought the combined suite to 13 passing tests.

Later regression RED: missing JSON-RPC version was accepted; truncated HTTP raised IncompleteRead; Retry-After NaN reached sleep(nan); capture-budget test had no corresponding limit constant. GREEN after envelope validation, safe HTTPException handling, finite backoff validation and a 64 MiB capture budget. Cross-transaction decimals remain checked while each captured result is analyzed once, avoiding quadratic replay.

Both real public-network captures used the public Vote program and saved partial snapshots with no transactions, exit 2. Direct devnet curl failed with code 6: Could not resolve host: api.devnet.solana.com. Local HTTP test cannot bind sockets in this environment and is explicitly skipped; CI makes it mandatory. Mocked rate-limit, retry, null, malformed, stall and redaction cases passed. No live success is claimed.
