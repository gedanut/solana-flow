# Roadmap

1. Offline demo and analysis ledger: test exact arithmetic, ownership and malformed data before implementation; deliver packaged fixture and exports.
2. Live RPC capture and robust replay: test local transport/pagination/failure cases before implementation; deliver bounded capture with coverage flags.
3. Report polish, hardening and release verification: test escaping, CLI and packaging; deliver offline report, CI, docs and verified distribution.

Plan check: every requirement maps to a slice. Highest risks are owner uncertainty, missing data disguised as zero, ambiguous versioned indexing and endpoint-secret leakage. Tests target these before polish.
