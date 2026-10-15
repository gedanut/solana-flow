"""Smoke an installed distribution, not the source tree, with only stdlib.

Run with the isolated interpreter: python -I scripts/smoke_installed.py
"""

import json
import queue
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.request import urlopen

import solana_flow


def command(*args, expected=0):
    result = subprocess.run(
        [sys.executable, "-I", "-m", "solana_flow", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"Installed command {args[0]} failed: {result.returncode}; {result.stderr}"
        )
    return result.stdout


def main():
    assert solana_flow.__version__ == "2.0.0", solana_flow.__version__
    with tempfile.TemporaryDirectory(prefix="solana-flow-wheel-") as directory:
        root = Path(directory)
        command("demo", "--output", root / "demo")
        command("analyze", root / "demo/snapshot.json", "--output", root / "replay")
        assert (root / "demo/ledger.json").read_bytes() == (
            root / "replay/ledger.json"
        ).read_bytes()
        metadata = json.loads(
            command("import", root / "demo/snapshot.json", "--database", root / "cli.sqlite")
        )
        page = json.loads(command("query", "--database", root / "cli.sqlite", "--asset", "SOL"))
        assert page["total"] > 0
        diff = json.loads(
            command("compare", metadata["id"], metadata["id"], "--database", root / "cli.sqlite")
        )
        assert not diff["added_signatures"] and not diff["changed_signatures"]
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-m",
                "solana_flow",
                "serve",
                "--database",
                str(root / "server.sqlite"),
                "--demo",
                "--port",
                "0",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lines = queue.Queue()
        thread = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        thread.start()
        try:
            line = lines.get(timeout=15)
            match = re.search(r"http://127\.0\.0\.1:\d+/", line)
            assert match, "Installed server did not start."
            base = match.group()
            for path, marker in (
                ("", b"Investigation"),
                ("workbench.js", b"parseLosslessJSON"),
                ("workbench.css", b"--teal"),
            ):
                with urlopen(base + path, timeout=5) as response:
                    assert response.status == 200 and marker in response.read(), path
            with urlopen(base + "api/wallets", timeout=5) as response:
                assert len(json.load(response)["wallets"]) == 2
            with urlopen(base + "api/captures", timeout=5) as response:
                assert len(json.load(response)["captures"]) == 4
        finally:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            thread.join(5)
        print(
            json.dumps(
                {
                    "version": solana_flow.__version__,
                    "module": solana_flow.__file__,
                    "checks": [
                        "demo/replay",
                        "import/query/compare",
                        "serve",
                        "packaged HTML/JS/CSS",
                        "seeded SQLite API",
                    ],
                }
            )
        )


if __name__ == "__main__":
    main()
