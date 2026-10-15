# v2 research and scope decision

Primary RPC references checked during the workbench build:
- https://solana.com/docs/rpc/http/gettokenaccountsbyowner describes current owner query, programId filtering, finalized jsonParsed response and nested parsed account owner.
- https://solana.com/docs/rpc/http/getsignaturesforaddress explicitly discovers accountKeys references newest first, not wallet economic history.

Implication: enumerate both token program account sets, query each address, deduplicate transactions and retain source boundaries. Present ownership at each balance side, not today's ownership applied retrospectively. Closed/transferred token accounts and history absent at the RPC provider remain outside discoverable scope. No claim of complete history follows from empty pages.

Product alternatives: (1) more report visuals would not solve the user's critique; (2) a hosted distributed indexer introduces infrastructure/cost before validation; (3) persistent local-first evidence workflow provides multi-wallet state, queries, comparisons, capture jobs and operational depth with a reproducible one-command start. Chosen (3), preserving zero runtime dependencies and exact arithmetic.

Publication observation: desktop preview could open but subsequent read/action said no Hermes window is showing this chat. Do not assume browser account access. Dedicated SSH push remains available; public API reads can verify CI/Pages. Never use a personal-account connector to work around gedanut separation.
