"""Durable capture jobs executed by one session-local background worker."""

import os
import threading
from collections import deque
from pathlib import Path

from .ledger import ValidationError, require
from .rpc import RPCClient, validate_address


class JobRunner:
    """Persist lifecycle transitions; capture outside the submission lock."""

    def __init__(self, workspace, rpc_url=None, *, capture_fn=None, max_pending=16):
        require(type(max_pending) is int and max_pending > 0, "Invalid pending queue bound.")
        self.workspace = workspace
        self._client = RPCClient(rpc_url) if rpc_url is not None else None
        self._capture_fn = capture_fn
        self._max_pending = max_pending
        self._pending = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._owner_file = None
        self._acquire_owner()
        self._thread = threading.Thread(target=self._work, name="solana-flow-capture", daemon=True)
        try:
            workspace.recover_jobs()
            self._thread.start()
        except Exception:
            self._release_owner()
            raise

    def _acquire_owner(self):
        path = getattr(self.workspace, "path", None)
        if path is None:
            return  # Contract doubles have no shared persistent store.
        lock_path = str(Path(path).resolve()) + ".jobs.lock"
        owner_file = None
        try:
            owner_file = open(lock_path, "a+b")
            if os.name == "nt":
                import msvcrt

                if owner_file.seek(0, os.SEEK_END) == 0:
                    owner_file.write(b"0")
                    owner_file.flush()
                owner_file.seek(0)
                msvcrt.locking(owner_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(owner_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if owner_file is not None:
                owner_file.close()
            raise ValidationError(
                "Workspace capture runner already active or lock unavailable."
            ) from None
        self._owner_file = owner_file

    def _release_owner(self):
        if self._owner_file is not None:
            self._owner_file.close()
            self._owner_file = None

    @property
    def enabled(self):
        return self._client is not None and not self._closed

    def submit(self, wallet_id, limit=100, include_tokens=False):
        with self._condition:
            require(not self._closed, "Capture runner is closed.")
            require(self._client is not None, "RPC endpoint is not configured.")
            require(type(limit) is int and 1 <= limit <= 10000, "Invalid capture limit.")
            require(type(include_tokens) is bool, "Invalid token discovery flag.")
            wallet = self.workspace.get_wallet(wallet_id)
            require(
                wallet["cluster"] in ("mainnet-beta", "devnet", "testnet", "custom"),
                "Only live wallets can be captured.",
            )
            validate_address(wallet["address"])
            require(len(self._pending) < self._max_pending, "Capture queue is full; retry later.")
            job = self.workspace.create_job(wallet_id, limit=limit, include_tokens=include_tokens)
            self._pending.append((job, wallet))
            self._condition.notify()
            return job

    def _work(self):
        try:
            self._drain()
        finally:
            self._release_owner()

    def _drain(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._closed)
                if not self._pending:
                    return
                job, wallet = self._pending.popleft()
            try:
                self.workspace.update_job(job["id"], "running")
                capture = self._capture_fn
                if capture is None:
                    from .discovery import capture
                snapshot = capture(
                    wallet["address"],
                    self._client,
                    limit=job["limit"],
                    cluster=wallet["cluster"],
                    include_tokens=job["include_tokens"],
                )
                result = self.workspace.import_snapshot(snapshot)
                status = "partial" if result["partial"] else "succeeded"
                self.workspace.update_job(job["id"], status, capture_id=result["id"])
            except Exception:
                self._fail_job(job["id"], "Capture failed; inspect RPC availability and retry.")

    def _fail_job(self, job_id, error):
        try:
            self.workspace.update_job(job_id, "failed", error=error)
        except Exception:
            # A storage outage leaves durable queued/running state for startup recovery.
            # Never let a provider-controlled exception reach threading.excepthook.
            pass

    def close(self, wait=True):
        with self._condition:
            self._closed = True
            if not wait:
                while self._pending:
                    job, _ = self._pending.popleft()
                    self._fail_job(job["id"], "Capture interrupted by shutdown; retry.")
            self._condition.notify_all()
        if wait:
            self._thread.join()
