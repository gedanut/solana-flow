# Report design

## Surface

Command/Inspect: an offline balance-evidence document for reviewing an address. The first screen states the task, export actions and discovery limits. It is not a marketing landing page.

## Tokens

| Role | Value |
| --- | --- |
| Ground | `#0b1115` |
| Panels | `#121d23` |
| Border | `#2a3c44` |
| Main text | `#e9f2f1` |
| Secondary text | `#a4b8bb` |
| Positive movement / action | `#65decb` |
| Coverage warning / focus | `#d5ed8a` |
| Negative movement / failed status | `#f7bf91` |

System sans body is deliberately local for portable offline reports. Monospace is restricted to signatures, identifiers and base units. Numerals use tabular alignment. Heading scale is 30–44px, body 16px, ledger 13px. A 3px lime focus outline is visible on keyboard interaction.

## Layout and interaction

Export links align with the report title. Coverage warnings appear before summary totals. Asset charts never share scales across unlike assets. Summary values cover all attributable rows; table filters clearly state their narrower effect. Mobile uses single-column assets and two-column controls; the ledger scrolls inside a keyboard-focusable region. Meaning is carried by labels as well as color. No external fonts, images, scripts, trackers or loading animations.

## Evidence

Generated synthetic demo reviewed at 1440px and 390px: no document overflow, axe violations or runtime errors. Chromium verified search, filters, empty-state combinations and CSV download with no network requests. The README image is a browser capture of the actual generated demo. Synthetic provenance is repeated in header, coverage, ledger and footer.
