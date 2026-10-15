"""Disposable browser-test workspace and explicit local RPC contract fixture.

Not a live Solana provider and never used for the public demonstration.
"""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from solana_flow.jobs import JobRunner
from solana_flow.samples import seed_workspace
from solana_flow.server import create_server
from solana_flow.workspace import Workspace


class FixtureRPC(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        method = request["method"]
        result = (
            {"context": {"slot": 1}, "value": []} if method == "getTokenAccountsByOwner" else []
        )
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    with tempfile.TemporaryDirectory(prefix="solana-flow-browser-") as directory:
        workspace = Workspace(Path(directory) / "workspace.sqlite")
        seed_workspace(workspace)
        rpc = ThreadingHTTPServer(("127.0.0.1", 0), FixtureRPC)
        thread = threading.Thread(target=rpc.serve_forever, daemon=True)
        thread.start()
        runner = JobRunner(workspace, f"http://127.0.0.1:{rpc.server_port}/")
        http = create_server(workspace, port=8878, runner=runner)
        try:
            http.serve_forever()
        finally:
            http.server_close()
            runner.close()
            rpc.shutdown()
            rpc.server_close()
            thread.join(5)


if __name__ == "__main__":
    main()
