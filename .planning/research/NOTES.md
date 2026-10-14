# Protocol research

Primary sources: https://solana.com/docs/rpc/json-structures and https://solana.com/docs/rpc/http/gettransaction and https://solana.com/docs/rpc/http/getsignaturesforaddress

Token amounts use integer strings and decimals. Owner is optional: absent ownership is unknown. Parsed account keys already resolve lookup-table addresses; raw keys append writable then readonly loaded addresses. Discovery references only the supplied address, not all token accounts it owns. Endpoint history exhaustion cannot establish complete wallet history.
