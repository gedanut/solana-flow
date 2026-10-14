# Solana Flow

A read-only Python library and CLI by gedanut converting Solana transaction snapshots into an exact net balance-change ledger and offline report.

Core value: attributable, auditable net changes with explicit uncertainty, never invented completeness or payment classifications.

User intent and architecture choices are auto-approved. Python >=3.11; zero runtime dependencies. All work stays in this repository; no publication or credential access. Deferred: token-account discovery, valuation, tax classification, instruction interpretation and all signing/trading operations.

Decisions: integer arithmetic; strict snapshot validation; per-side ownership; omit uncertain asset rows with explicit gaps; retain native rows when token ownership is uncertain; standalone offline report; stdlib transport. GSD artifacts adapted to three vertical slices and executed inline.
