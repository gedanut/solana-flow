"""Generate a synthetic, read-only explorer from real workspace/analyzer results."""

import argparse
import json
import re
import sys
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

# Running from a source checkout must not require an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from solana_flow.samples import seed_workspace  # noqa: E402
from solana_flow.workspace import Workspace  # noqa: E402


def build_demo_data() -> dict:
    """Build fresh local evidence; normalize publication clocks, not ledger values."""
    with TemporaryDirectory(prefix="solana-flow-explorer-") as directory:
        workspace = Workspace(Path(directory) / "demo.sqlite3")
        seed_workspace(workspace)
        wallets = workspace.list_wallets()
        captures = [workspace.get_capture(item["id"]) for item in workspace.list_captures()]
    # Database import/wallet clocks are operational metadata, not fixture evidence.
    # Walk these exact fields only; do not recursively rewrite transaction times.
    for wallet in wallets:
        wallet["created_at"] = min(
            capture["captured_at"] for capture in captures if capture["wallet_id"] == wallet["id"]
        )
    for capture in captures:
        capture["imported_at"] = capture["captured_at"]
        if "created_at" in capture:
            capture["created_at"] = capture["captured_at"]
    return {"wallets": wallets, "captures": captures, "jobs": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/explorer"))
    args = parser.parse_args(argv)
    assets = files("solana_flow").joinpath("assets")
    html = assets.joinpath("workbench.html").read_text(encoding="utf-8")
    match = re.search(r"<html\b[^>]*>", html, flags=re.IGNORECASE)
    if match is None:
        raise ValueError("Workbench template must contain an html element.")
    tag = re.sub(
        r"""\sdata-mode\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", "", match.group(), flags=re.IGNORECASE
    )
    html = html[: match.start()] + tag[:-1] + ' data-mode="static">' + html[match.end() :]
    output = {
        "index.html": html.encode("utf-8"),
        "workbench.css": assets.joinpath("workbench.css").read_bytes(),
        "workbench.js": assets.joinpath("workbench.js").read_bytes(),
        "demo-data.json": (
            json.dumps(
                build_demo_data(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
            )
            + "\n"
        ).encode("utf-8"),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in output.items():
        (args.output / name).write_bytes(content)


if __name__ == "__main__":
    main()
