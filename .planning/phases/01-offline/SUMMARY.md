# Phase 1 evidence

RED: the initial ledger test suite could not import solana_flow.ledger (ModuleNotFoundError).
GREEN: after implementation, all seven ledger tests passed. Later malformed-data, uncertainty, precision and fixture-contract tests expand coverage.

Ledger uses integers and decimal-string formatting. Unknown ownership omits the transaction/mint with a gap. Explicit arrays distinguish absent accounts from missing metadata. Native data remains usable when token metadata is missing. Fixtures cover 12 synthetic transactions and 21 rows.

A later fixture regression exposed nonzero native pre/post lamports on claimed new/closed accounts. The assertion expected zero and observed 2039280. Fixture generation was corrected to model account creation/closure, wrapped-SOL backing and native conservation minus fees. The three fixture contract tests then passed.
