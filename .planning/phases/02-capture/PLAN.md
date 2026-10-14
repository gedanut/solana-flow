# Phase 2 — capture and robust replay

Implement only getSignaturesForAddress and getTransaction. Test pagination, dedup, caps, null results, transport failures and redaction before transport code. Bound calls, body sizes and aggregate capture size; use explicit finalized commitment and version 0. Treat provider boundary and wallet-history completeness separately. Local HTTP integration must not depend on public network availability.
