# Capture jobs and restart recovery

`JobRunner(workspace, rpc_url=None, capture_fn=None, max_pending=16)` owns one background thread and a bounded in-memory pending queue. A submitted job is persisted before it is acknowledged. The queue holds at most 16 pending jobs plus one running capture by default. Limits count unique discovered signatures, not guaranteed successful transactions.

Lifecycle: `queued -> running -> succeeded | partial | failed`. Terminal state is immutable. Only successful/partial jobs link a validated capture belonging to the same wallet. Token-enabled captures always carry the current-account scope warning and therefore finish `partial`, even if all discovered source pages were exhausted successfully. A provider boundary is never complete wallet history.

The endpoint lives only in an RPCClient in process memory. It is not stored in SQLite, jobs, capture evidence, request logs or exception diagnostics. Use `SOLANA_FLOW_RPC_URL` rather than putting a private endpoint in shell arguments. Input labels and allowlisted identifiers are still sensitive user evidence, not sanitized public content.

## Exclusive ownership

Before recovering prior jobs, the runner acquires a nonblocking OS advisory lock beside the resolved database path (`.jobs.lock`). Unix uses `flock`; Windows uses a one-byte `msvcrt` lock. A second owner is refused before it can recover the live runner's jobs. The lock remains held until the worker thread exits, including during a nonwaiting close while capture remains active. Do not delete or replace the lock file while an owner runs; this is single-user process coordination, not protection against a malicious local administrator or a network filesystem with broken advisory locks.

## Recovery and shutdown

On startup, existing queued/running records are marked failed with an interrupted-capture diagnostic. There is no silent automatic resubmission or exactly-once remote-job claim. An operator explicitly starts another capture. A capture is a new immutable observation window, not an incremental append to earlier history.

`close(wait=True)` rejects new work, drains accepted work, then joins the worker. `close(wait=False)` fails queued work and lets the active capture complete while this process lives. The CLI uses nonwaiting close on interruption; process exit can terminate its daemon thread. The next startup recovers nonterminal records. RPC calls have bounded timeouts/retries, but there is no total job deadline or force-cancel of a running Python thread. Use a process deadline for untrusted providers.

Provider exceptions and persistence failures do not reach `threading.excepthook`. A storage outage can leave a queued/running record for startup recovery; it does not cause a guessed terminal success. If a capture import succeeds but final job-state persistence fails, its capture can exist without a completed job association. Inspect capture history and retry explicitly.

## Evidence

`tests/test_jobs.py` exercises asynchronous transitions, queue saturation under concurrent submissions, sanitized failures, shutdown, persistent runner ownership, and storage-transition failures. `tests/test_integration.py` runs the actual local HTTP API, worker, JSON-RPC transport and SQLite together, captures a passive token receipt, checks an exact integer above IEEE-754 precision, and reopens the saved job/capture. Browser tests additionally register a wallet and submit/open a job against an explicitly local RPC fixture. These fixtures are not described as live Solana transactions.
