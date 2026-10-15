"""Deterministic, unmistakably synthetic workbench evidence; never contacts RPC."""

import json
from copy import deepcopy
from importlib.resources import files
from typing import Any

WALLETS = (
    ("11111111111111111111111111111111", "Synthetic treasury"),
    ("Vote111111111111111111111111111111111111111", "Synthetic operations"),
)


def _replace_wallet(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {key: _replace_wallet(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_wallet(item, old, new) for item in value]
    return new if value == old else value


def sample_snapshots() -> list[tuple[str, dict]]:
    """Return fresh (capture label, snapshot) pairs: two captures for two wallets.

    Wallet addresses are valid public-key encodings used only as synthetic labels,
    not claims about the real system/vote programs or their chain activity.
    """
    fixture = json.loads(files("solana_flow").joinpath("data/demo.json").read_text())
    samples = []
    for wallet_index, (address, label) in enumerate(WALLETS):
        source = _replace_wallet(deepcopy(fixture), fixture["wallet"], address)
        for index, transaction in enumerate(source["transactions"]):
            transaction["transaction"]["signatures"][0] = (
                f"SYNTHETIC-W{wallet_index + 1}-" + transaction["transaction"]["signatures"][0]
            )
            if transaction["blockTime"] is not None:
                transaction["blockTime"] += (index // 4 + wallet_index) * 86400
        for window, transactions in (
            ("baseline", source["transactions"][:8]),
            ("follow-up", source["transactions"][2:]),
        ):
            snapshot = deepcopy(source)
            snapshot["transactions"] = deepcopy(transactions)
            snapshot["captured_at"] = (
                "2026-01-04T13:00:00Z" if window == "baseline" else "2026-01-05T13:00:00Z"
            )
            if window == "follow-up":
                # Same synthetic signature, corrected balance evidence in a NEW capture.
                snapshot["transactions"][1]["meta"]["postTokenBalances"][0]["uiTokenAmount"][
                    "amount"
                ] = "85250000"
                snapshot["transactions"][6]["meta"] = None
                snapshot["transactions"][7]["meta"]["postTokenBalances"][0].pop("owner")
                snapshot["coverage"].update(limit=16, partial=True)
                snapshot["unavailable_signatures"] = [
                    f"SYNTHETIC-W{wallet_index + 1}-unavailable-not-a-chain-signature"
                ]
                snapshot["warnings"] = [
                    "Synthetic overlapping windows, not an incremental balance history.",
                    "Synthetic correction: transaction 004 token evidence differs from baseline.",
                    "Missing metadata and owner demonstrate uncertainty, not zero movement.",
                ]
            samples.append((f"{label} · {window}", snapshot))
    return samples


def seed_workspace(workspace) -> list[dict]:
    """Import all sample captures idempotently; return capture metadata in seed order.

    Imports use the workspace's normal validation, normalization and analyzer;
    there is no separate synthetic ledger or hardcoded presentation metric.
    """
    for address, label in WALLETS:
        workspace.add_wallet(address, cluster="synthetic", label=label)
    return [
        workspace.import_snapshot(snapshot, label=label) for label, snapshot in sample_snapshots()
    ]
