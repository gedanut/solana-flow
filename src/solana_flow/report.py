"""Deterministic CSV, JSON and self-contained HTML output."""

import base64
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from html import escape
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from .rpc import valid_signature

FIELDS = (
    "signature",
    "slot",
    "time",
    "status",
    "asset",
    "mint",
    "amount_base_units",
    "decimals",
    "decimal_amount",
    "direction",
    "wallet_paid_fee_base_units",
    "synthetic",
)
TEXT_FIELDS = {"signature", "status", "asset", "mint", "direction"}


def _cell(value):
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def csv_text(result: dict) -> str:
    """Spreadsheet-safe textual identifiers; exact numeric fields remain numeric strings."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in result["rows"]:
        writer.writerow(
            {key: _cell(row[key]) if key in TEXT_FIELDS else row[key] for key in FIELDS}
        )
    return output.getvalue()


def _e(value):
    return escape(str(value), quote=True)


def _when(value):
    if value is None:
        return "Unknown time"
    try:
        return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OverflowError, OSError, ValueError):
        return f"Unix seconds: {value}"


def _asset_key(asset):
    return "SOL" if asset["asset"] == "SOL" else "SPL:" + asset["mint"]


def _card(asset):
    native = asset["asset"] == "SOL"
    mint = asset["mint"]
    inflow, outflow = int(asset["inflow_base_units"]), int(asset["outflow_base_units"])
    scale = max(inflow, outflow, 1)
    a, b = inflow * 300 // scale, outflow * 300 // scale
    label = "Native SOL" if native else "SPL token"
    sign = "positive" if int(asset["net_base_units"]) >= 0 else "negative"
    chart_title = _e(
        f"{label}: inflow {asset['inflow']}; outflow {asset['outflow']}. "
        "Bar widths are relative within this asset only."
    )
    return f'''<article class="asset"><h3>{label}</h3>
<code>{_e(mint) if mint else "Native account lamports · 9 decimals"}</code>
<div class="net {sign}">{_e(asset["net"])}</div><div class="label">Net balance change</div>
<svg class="flow" viewBox="0 0 300 44" role="img" aria-label="{chart_title}">
<title>{chart_title}</title><rect class="bar-track" width="300" height="12" rx="4"/>
<rect class="in-bar" width="{a}" height="12" rx="4"/>
<rect class="bar-track" y="26" width="300" height="12" rx="4"/>
<rect class="out-bar" y="26" width="{b}" height="12" rx="4"/></svg>
<dl><div><dt>Inflow · net-positive rows</dt><dd>{_e(asset["inflow"])}</dd></div>
<div><dt>Outflow · net-negative rows</dt><dd>{_e(asset["outflow"])}</dd></div></dl></article>'''


def _table_row(row, result):
    signature = _e(row["signature"])
    if (
        not result["synthetic"]
        and result["cluster"] in ("mainnet-beta", "devnet", "testnet")
        and valid_signature(row["signature"])
    ):
        query = "" if result["cluster"] == "mainnet-beta" else "?cluster=" + result["cluster"]
        url = "https://explorer.solana.com/tx/" + quote(row["signature"], safe="") + query
        signature = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{signature}</a>'
    color = (
        "positive" if row["direction"] == "in" else "negative" if row["direction"] == "out" else ""
    )
    return f'''<tr data-asset="{_e(_asset_key(row))}" data-direction="{row["direction"]}"
 data-status="{row["status"]}"><td><code>{signature}</code></td><td>{row["slot"]}</td>
<td>{_e(_when(row["time"]))}</td><td><span class="status {row["status"]}">{row["status"]}</span></td>
<td>{row["asset"]}<code>{_e(row["mint"]) if row["mint"] else "Native SOL"}</code></td>
<td><span class="decimal {color}">{_e(row["decimal_amount"])}</span>
<span class="sub">{row["direction"]} · net movement</span></td>
<td><code>{_e(row["amount_base_units"])}</code></td><td>{row["decimals"]}</td></tr>'''


def html_text(result: dict) -> str:
    """Render an analyzed ledger; text fields are untrusted and escaped."""
    synthetic = result["synthetic"]
    label = "SYNTHETIC · offline demonstration" if synthetic else "Read-only · snapshot analysis"
    prefix = "SYNTHETIC — " if synthetic else ""
    cov = result["coverage"]
    coverage_title = (
        "Partial data — gaps affect totals"
        if cov["partial"]
        else "Limited discovery — scoped snapshot"
    )
    boundary = (
        "Capture cap reached; older references were not requested."
        if cov["cap_reached"]
        else "Provider returned an empty history page; this does not prove complete wallet history."
        if cov["reached_history"]
        else "History boundary was not established."
    )
    gaps = result["gaps"]
    issues = [
        *result["warnings"],
        *(f"{g['signature']} · {g['asset']}: {g['reason']}" for g in gaps),
        *(f"Unavailable transaction: {s}" for s in result["unavailable_signatures"]),
    ]
    issue_html = (
        "<details open><summary>Coverage details and missing data</summary><ul>"
        + "".join(f"<li>{_e(issue)}</li>" for issue in issues)
        + "</ul></details>"
        if issues
        else ""
    )
    cards = "".join(_card(asset) for asset in result["assets"])
    options = "".join(
        f'<option value="{_e(_asset_key(a))}">{_e(_asset_key(a))}</option>'
        for a in result["assets"]
    )
    rows = "".join(_table_row(row, result) for row in result["rows"])
    csv_data = base64.b64encode(csv_text(result).encode()).decode()
    stylesheet = files("solana_flow").joinpath("assets/report.css").read_text(encoding="utf-8")
    script = files("solana_flow").joinpath("assets/report.js").read_text(encoding="utf-8")
    css_hash = base64.b64encode(hashlib.sha256(stylesheet.encode()).digest()).decode()
    js_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = (
        f"default-src 'none'; style-src 'sha256-{css_hash}'; script-src 'sha256-{js_hash}'; "
        "img-src data:; base-uri 'none'; form-action 'none'; connect-src 'none'"
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}"><meta name="referrer" content="no-referrer">
<meta name="description" content="Read-only Solana net balance changes with exact amounts, per-asset totals, transaction evidence, and explicit coverage limits.">
<title>{prefix}Solana Flow · Net movement report</title><style>{stylesheet}</style></head>
<body><a class="skip" href="#ledger">Skip to ledger</a>
<header><div class="brand"><span class="mark" aria-hidden="true"></span>Solana Flow</div>
<div class="badge">{label}</div></header><main>
<section class="hero" aria-labelledby="title"><div>
<h1 id="title">Wallet movement report</h1><p class="lede">Inspect exact net changes by asset and transaction.
Coverage limits stay visible alongside the amounts.</p></div>
<div class="actions"><a class="button primary" download="ledger.csv" href="data:text/csv;base64,{csv_data}">Download CSV</a>
<a class="button" href="ledger.json" download>Ledger JSON</a></div></section>
<section class="coverage" aria-label="Coverage limitations"><strong>{prefix}{coverage_title}</strong>
<p>Discovery includes transactions referencing the supplied wallet in account keys only.
Passive receipts into owned token accounts may be absent. This is <b>not complete wallet history</b>.</p>
<p>{boundary} Limit: {cov["limit"]} signatures. Pages: {cov["pages"]}.
Unavailable: {len(result["unavailable_signatures"])}. Analysis gaps: {len(gaps)}.</p>
{("<p><b>SYNTHETIC: invented fixture transactions, not live activity. No explorer links.</b></p>" if synthetic else "")}
{issue_html}</section>
<div class="wallet">Wallet: <code>{_e(result["wallet"])}</code><br>
Cluster: {_e(result["cluster"])} · Captured: {_e(result["captured_at"])}</div>
<section class="stats" aria-label="Snapshot statistics">
<div class="stat"><div class="label">{prefix}Transactions captured</div><div class="number">{result["transaction_count"]}</div></div>
<div class="stat"><div class="label">Failed transactions</div><div class="number">{result["failed_count"]}</div>
<div class="muted">Unknown status: {result["unknown_status_count"]}</div></div>
<div class="stat"><div class="label">Wallet-paid fees · SOL</div><div class="number">{result["wallet_paid_fees_sol"]}</div>
<div class="muted">Already included in native net change</div></div>
<div class="stat"><div class="label">Distinct assets observed</div><div class="number">{len(result["assets"])}</div>
<div class="muted">Never combined or priced in USD</div></div></section>
<section aria-labelledby="asset-title"><div class="section-head"><h2 id="asset-title">{prefix}Asset movements</h2>
<p class="muted">All captured rows · each chart has its own scale</p></div>
<div class="assets">{cards or "<p>No attributable asset movements.</p>"}</div></section>
<section id="ledger" aria-labelledby="ledger-title"><div class="section-head"><h2 id="ledger-title">{prefix}The ledger</h2>
<p id="row-count" class="muted" aria-live="polite">{len(result["rows"])} ledger rows</p></div>
<p class="muted">Filters affect the table only. Summary totals above always cover all attributable rows.
Scroll horizontally to inspect all ledger columns.</p>
<div class="controls"><label>Search signature, mint or amount<input id="search" type="search" placeholder="Search this snapshot…"></label>
<label>Asset<select id="asset"><option value="">All assets</option>{options}</select></label>
<label>Direction<select id="direction"><option value="">All directions</option><option value="in">Inflow</option>
<option value="out">Outflow</option><option value="zero">Net zero</option></select></label>
<label>Status<select id="status"><option value="">All statuses</option><option value="success">Success</option>
<option value="failed">Failed</option></select></label></div>
<noscript><p>Enable JavaScript to filter. All rows and exports remain available without it.</p></noscript>
<div class="table-shell" role="region" aria-label="Scrollable transaction ledger" tabindex="0"><table>
<caption>{prefix}Net balance changes, not gross transfers or payment classifications. Unknown times remain unknown.</caption>
<thead><tr><th scope="col">Signature</th><th scope="col">Slot</th><th scope="col">Time</th><th scope="col">Status</th>
<th scope="col">Asset / mint</th><th scope="col">Decimal amount</th><th scope="col">Base units</th><th scope="col">Decimals</th></tr></thead>
<tbody>{rows}</tbody></table><p id="empty" class="empty" hidden>No rows match these filters.</p></div></section>
<section class="notes" aria-labelledby="method-title"><h2 id="method-title">Read the movement, respect the limits.</h2>
<p>SOL is the supplied wallet account’s post-balance minus pre-balance. SPL balances are summed across
accounts explicitly owned by the wallet on each side of each transaction. Ownership changes affect attribution;
missing owners create gaps. New and closed accounts use only the supplied side.</p>
<p>Inflow and outflow sum positive and negative <em>net transaction changes</em>. Internal movement can net to zero.
Fees, rent, swaps, burns and wrapped SOL can affect these numbers. None are labeled as payments, income or tax events.
Wrapped SOL stays a separate SPL mint. Token identifiers are untrusted; no symbol, logo or price is assumed.</p>
<p>Fees are counted only where the wallet is the fee payer. Incomplete metadata makes totals incomplete;
they are observed movements, not a current portfolio balance. CSV protects textual fields against spreadsheet formulas;
use JSON when exact identifier round trips matter.</p></section></main>
<footer><span>Solana Flow / by gedanut · {label}</span><span>Offline report · zero trackers · exact integer arithmetic</span></footer>
<script>{script}</script></body></html>'''


def write_report(result: dict, output: Path) -> None:
    """Write the three portable report artifacts, replacing existing named files."""
    output = Path(output)
    rendered = {
        "index.html": html_text(result),
        "ledger.csv": csv_text(result),
        "ledger.json": json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, content in rendered.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
