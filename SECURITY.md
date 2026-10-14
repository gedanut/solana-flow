# Security

Solana Flow is read-only: no wallet connection, secrets, signing or transaction submission. Only two RPC methods are allowed: getSignaturesForAddress and getTransaction. Runtime code uses the Python standard library. Use supported Python versions with current security patches.

RPC responses, mints and signatures are untrusted. Reports escape textual content, avoid external resources and use a restrictive content-security policy. Textual CSV fields are protected against formula injection. JSON retains exact identifiers. An analysis capture is not independently authenticated chain evidence.

Use HTTPS for remote RPC. The CLI never persists the endpoint in capture metadata or prints it in errors, but command arguments may appear in process listings or shell history. Do not put private endpoints in shared command transcripts. Capture stores allowlisted balance-analysis fields only, dropping instructions, logs, arbitrary provider extensions and raw failure text. This is not a full RPC archive. Identifiers and balances still come from an untrusted provider; review snapshots before sharing. RPC and snapshot JSON reject duplicate keys and non-finite constants. Reports deliberately contain addresses and activity.

The analyzer applies input and response size bounds, rejects malformed structural data, records missing metadata as gaps, and keeps unknown ownership out of totals. These controls do not guarantee availability against every adversarial document or server. Run untrusted workloads with external memory/time limits. Report writers replace their documented filenames in the chosen directory; choose a directory you control.

If a vulnerability is found, use GitHub private vulnerability reporting for `gedanut/solana-flow` if enabled after publication. If unavailable, open an issue requesting a private reporting channel without including exploit details, credentials or private wallet data. No claim is made that a reporting channel is enabled before repository publication. Supported release line: 1.x.
