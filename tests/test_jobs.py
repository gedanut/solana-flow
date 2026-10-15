"""Deterministic asynchronous lifecycle tests, built incrementally with TDD."""

import importlib.util
import threading
import unittest

W = "11111111111111111111111111111111"
ENDPOINT = "https://rpc.example/?api-key=NEVER-PERSIST"


class FakeWorkspace:
    """Thread-safe contract double while the SQLite workspace is built separately."""

    def __init__(self):
        self.lock = threading.RLock()
        self.wallet = {"id": 1, "address": W, "cluster": "devnet"}
        self.jobs = {}
        self.captures = []
        self.transitions = []
        self.recovery_calls = 0

    def get_wallet(self, wallet_id):
        if wallet_id != self.wallet["id"]:
            raise ValueError("Wallet not found.")
        return dict(self.wallet)

    def create_job(self, wallet_id, limit=100, include_tokens=False):
        with self.lock:
            job = {
                "id": len(self.jobs) + 1,
                "wallet_id": wallet_id,
                "limit": limit,
                "include_tokens": include_tokens,
                "status": "queued",
                "capture_id": None,
                "error": None,
            }
            self.jobs[job["id"]] = job
            self.transitions.append((job["id"], "queued"))
            return dict(job)

    def get_job(self, job_id):
        with self.lock:
            return dict(self.jobs[job_id])

    def list_jobs(self):
        with self.lock:
            return [dict(job) for job in self.jobs.values()]

    def update_job(self, job_id, status, capture_id=None, error=None):
        with self.lock:
            job = self.jobs[job_id]
            allowed = {
                "queued": ("running", "failed"),
                "running": ("succeeded", "partial", "failed"),
            }
            if status not in allowed.get(job["status"], ()):
                raise ValueError("Invalid transition.")
            job.update(status=status, capture_id=capture_id, error=error)
            self.transitions.append((job_id, status))
            return dict(job)

    def import_snapshot(self, snapshot, label=""):
        with self.lock:
            capture = {"id": len(self.captures) + 1, "partial": snapshot["partial"]}
            self.captures.append(capture)
            return dict(capture)

    def recover_jobs(self):
        self.recovery_calls += 1
        for job in self.list_jobs():
            if job["status"] in ("queued", "running"):
                self.update_job(job["id"], "failed", error="Capture interrupted; retry.")


class JobRunnerTests(unittest.TestCase):
    def runner(self, workspace, **kwargs):
        self.assertIsNotNone(
            importlib.util.find_spec("solana_flow.jobs"), "durable JobRunner module is missing"
        )
        from solana_flow.jobs import JobRunner

        runner = JobRunner(workspace, **kwargs)
        self.addCleanup(runner.close)
        return runner

    def test_shutdown_storage_failure_is_left_for_recovery_without_leaking(self):
        class UnavailableWorkspace(FakeWorkspace):
            def update_job(self, job_id, status, capture_id=None, error=None):
                if job_id == 2:
                    raise RuntimeError(ENDPOINT)
                return super().update_job(job_id, status, capture_id=capture_id, error=error)

        workspace = UnavailableWorkspace()
        entered, release = threading.Event(), threading.Event()

        def capture(*args, **kwargs):
            entered.set()
            release.wait(3)
            return {"partial": False}

        runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture)
        self.addCleanup(release.set)
        runner.submit(1)
        self.assertTrue(entered.wait(3))
        queued = runner.submit(1)
        try:
            try:
                runner.close(wait=False)
            except Exception:
                self.fail("Shutdown propagated a storage exception.")
            self.assertEqual(workspace.get_job(queued["id"])["status"], "queued")
        finally:
            release.set()
            runner.close()

    def test_real_workspace_runner_ownership_prevents_recovering_live_jobs(self):
        import tempfile
        from pathlib import Path

        from solana_flow.jobs import JobRunner
        from solana_flow.workspace import Workspace

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.sqlite3"
            workspace = Workspace(path)
            wallet = workspace.add_wallet(W, cluster="devnet")
            entered, release = threading.Event(), threading.Event()

            def capture(*args, **kwargs):
                entered.set()
                release.wait(3)
                raise RuntimeError(ENDPOINT)

            runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture)
            self.addCleanup(release.set)
            job = runner.submit(wallet["id"])
            self.assertTrue(entered.wait(3))
            try:
                for closing in (False, True):
                    if closing:
                        runner.close(wait=False)
                    with self.assertRaisesRegex(ValueError, "already"):
                        other = JobRunner(Workspace(path))
                        other.close()
                    self.assertEqual(workspace.get_job(job["id"])["status"], "running")
            finally:
                release.set()
                runner.close()
            other = JobRunner(Workspace(path))
            other.close()
            self.assertEqual(workspace.get_job(job["id"])["status"], "failed")

    def test_failure_persistence_errors_do_not_leak_or_kill_worker(self):
        import contextlib
        import io

        class UnavailableWorkspace(FakeWorkspace):
            def update_job(self, job_id, status, capture_id=None, error=None):
                if job_id == 1:
                    raise RuntimeError(ENDPOINT)
                return super().update_job(job_id, status, capture_id=capture_id, error=error)

        workspace = UnavailableWorkspace()
        runner = self.runner(
            workspace, rpc_url=ENDPOINT, capture_fn=lambda *a, **k: {"partial": False}
        )
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            runner.submit(1)
            second = runner.submit(1)
            runner.close()
        self.assertEqual(workspace.get_job(second["id"])["status"], "succeeded")
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(workspace.get_job(1)["status"], "queued")

    def test_running_transition_failure_is_sanitized_without_killing_worker(self):
        import contextlib
        import io

        class FailingTransitionWorkspace(FakeWorkspace):
            def update_job(self, job_id, status, **kwargs):
                if job_id == 1 and status == "running":
                    raise RuntimeError(ENDPOINT)
                return super().update_job(job_id, status, **kwargs)

        workspace = FailingTransitionWorkspace()
        runner = self.runner(
            workspace, rpc_url=ENDPOINT, capture_fn=lambda *a, **k: {"partial": False}
        )
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            first = runner.submit(1)
            second = runner.submit(1)
            runner.close()
        self.assertEqual(workspace.get_job(first["id"])["status"], "failed")
        self.assertEqual(workspace.get_job(second["id"])["status"], "succeeded")
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn("NEVER-PERSIST", str(workspace.list_jobs()))

    def test_invalid_pending_bounds_are_rejected_before_recovery(self):
        from solana_flow.jobs import JobRunner

        workspace = FakeWorkspace()
        for max_pending in (0, -1, True, 1.5, "2", None):
            with self.subTest(max_pending=max_pending), self.assertRaises(ValueError):
                runner = JobRunner(workspace, rpc_url=ENDPOINT, max_pending=max_pending)
                runner.close()
        self.assertEqual(workspace.recovery_calls, 0)

    def test_nonwaiting_close_cancels_queued_but_does_not_kill_active_capture(self):
        workspace = FakeWorkspace()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def capture(*args, **kwargs):
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(3))
            return {"partial": False}

        runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture)
        self.addCleanup(release.set)
        first = runner.submit(1)
        self.assertTrue(entered.wait(3))
        second = runner.submit(1)
        runner.close(wait=False)
        self.assertEqual(workspace.get_job(first["id"])["status"], "running")
        cancelled = workspace.get_job(second["id"])
        self.assertEqual(cancelled["status"], "failed")
        self.assertEqual(cancelled["error"], "Capture interrupted by shutdown; retry.")
        self.assertIsNone(cancelled["capture_id"])
        release.set()
        runner.close()
        self.assertEqual(workspace.get_job(first["id"])["status"], "succeeded")
        self.assertEqual(len(calls), 1)

    def test_close_rejects_submissions_without_creating_orphan_jobs(self):
        workspace = FakeWorkspace()
        runner = self.runner(workspace, rpc_url=ENDPOINT)
        self.assertTrue(runner.enabled)
        runner.close()
        with self.assertRaisesRegex(ValueError, "closed"):
            runner.submit(1)
        self.assertFalse(runner.enabled)
        self.assertEqual(workspace.list_jobs(), [])
        runner.close()

    def test_concurrent_submissions_obey_pending_bound_without_stranded_jobs(self):
        from concurrent.futures import ThreadPoolExecutor

        workspace = FakeWorkspace()
        entered, release = threading.Event(), threading.Event()
        callers = threading.Barrier(12)
        calls = []

        def capture(*args, **kwargs):
            calls.append(threading.get_ident())
            entered.set()
            self.assertTrue(release.wait(3))
            return {"partial": False}

        runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture, max_pending=2)
        self.addCleanup(release.set)
        first = runner.submit(1)
        self.assertTrue(entered.wait(3))

        def submit():
            callers.wait(3)
            try:
                return runner.submit(1)
            except ValueError as exc:
                self.assertIn("full", str(exc))
                return None

        try:
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: submit(), range(12)))
            accepted = [result for result in results if result is not None]
            self.assertEqual(len(accepted), 2)
            self.assertEqual(len(workspace.list_jobs()), 3)
            self.assertEqual(workspace.get_job(first["id"])["status"], "running")
            self.assertTrue(all(workspace.get_job(j["id"])["status"] == "queued" for j in accepted))
        finally:
            release.set()
            runner.close()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 1)
        self.assertTrue(all(j["status"] == "succeeded" for j in workspace.list_jobs()))

    def test_non_live_wallets_are_rejected_before_persisting(self):
        workspace = FakeWorkspace()
        runner = self.runner(
            workspace, rpc_url=ENDPOINT, capture_fn=lambda *a, **k: {"partial": False}
        )
        for address, cluster in (
            (W, "synthetic"),
            (W, "wrong"),
            (ENDPOINT, "custom"),
            (None, "devnet"),
        ):
            workspace.wallet.update(address=address, cluster=cluster)
            with self.subTest(cluster=cluster), self.assertRaises(ValueError):
                runner.submit(1)
        self.assertEqual(workspace.list_jobs(), [])

    def test_invalid_capture_options_do_not_persist_jobs(self):
        workspace = FakeWorkspace()
        runner = self.runner(
            workspace, rpc_url=ENDPOINT, capture_fn=lambda *a, **k: {"partial": False}
        )
        for kwargs in (
            {"limit": True},
            {"limit": 0},
            {"limit": 10001},
            {"limit": "3"},
            {"limit": 1.5},
            {"include_tokens": 1},
            {"include_tokens": "false"},
            {"include_tokens": None},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                runner.submit(1, **kwargs)
        self.assertEqual(workspace.list_jobs(), [])

    def test_disabled_runner_rejects_without_persisting_a_job(self):
        workspace = FakeWorkspace()
        runner = self.runner(workspace)
        with self.assertRaisesRegex(ValueError, "RPC"):
            runner.submit(1)
        self.assertFalse(runner.enabled)
        self.assertEqual(workspace.list_jobs(), [])

    def test_capture_exception_is_sanitized_and_worker_accepts_next_job(self):
        workspace = FakeWorkspace()
        calls = []

        def capture(*args, **kwargs):
            calls.append(args[1])
            if len(calls) == 1:
                raise RuntimeError(ENDPOINT)
            return {"partial": False}

        runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture)
        first = runner.submit(1)
        second = runner.submit(1)
        runner.close()
        failed = workspace.get_job(first["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "Capture failed; inspect RPC availability and retry.")
        self.assertIsNone(failed["capture_id"])
        self.assertEqual(workspace.get_job(second["id"])["status"], "succeeded")
        self.assertEqual(len(workspace.captures), 1)
        self.assertIs(calls[0], calls[1])
        self.assertNotIn("NEVER-PERSIST", str(workspace.list_jobs()))

    def test_partial_status_comes_from_imported_capture(self):
        workspace = FakeWorkspace()
        runner = self.runner(
            workspace, rpc_url=ENDPOINT, capture_fn=lambda *args, **kwargs: {"partial": True}
        )
        job = runner.submit(1)
        runner.close()
        stored = workspace.get_job(job["id"])
        self.assertEqual(stored["status"], "partial")
        self.assertEqual(stored["capture_id"], 1)
        self.assertIsNone(stored["error"])

    def test_submit_runs_off_caller_thread_with_durable_lifecycle(self):
        workspace = FakeWorkspace()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []

        def capture(wallet, client, *, limit, cluster, include_tokens):
            calls.append((wallet, client, limit, cluster, include_tokens, threading.get_ident()))
            entered.set()
            self.assertTrue(release.wait(3))
            return {"partial": False}

        runner = self.runner(workspace, rpc_url=ENDPOINT, capture_fn=capture)
        job = runner.submit(1, limit=7, include_tokens=True)
        self.assertEqual(job["status"], "queued")
        self.assertTrue(entered.wait(3))
        self.assertEqual(workspace.get_job(job["id"])["status"], "running")
        self.assertEqual(workspace.captures, [])
        self.assertEqual(calls[0][:1], (W,))
        self.assertEqual(calls[0][2:5], (7, "devnet", True))
        self.assertNotEqual(calls[0][-1], threading.get_ident())
        release.set()
        runner.close()
        self.assertEqual(workspace.get_job(job["id"])["status"], "succeeded")
        self.assertEqual(workspace.get_job(job["id"])["capture_id"], 1)
        self.assertEqual(workspace.transitions, [(1, "queued"), (1, "running"), (1, "succeeded")])
        self.assertEqual(workspace.recovery_calls, 1)
