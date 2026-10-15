---
version: alpha
name: Solana Flow Workbench
description: Restrained slate navigation and a white evidence workspace with teal actions and amber uncertainty.
colors:
  primary: "#096c62"
  primary-hover: "#07564f"
  selected: "#e8f4f0"
  ink: "#182d36"
  muted: "#536773"
  border: "#d7e1e4"
  surface: "#f4f7f8"
  white: "#ffffff"
  rail: "#182a34"
  rail-text: "#f0f6f8"
  rail-muted: "#b8cbd2"
  rail-status: "#b4e0d5"
  wallet-text: "#e6eef0"
  wallet-hover: "#233e49"
  wallet-selected: "#294a53"
  amber: "#765110"
  amber-bg: "#fff7e6"
  danger: "#a12e29"
  outflow: "#8d3c29"
  inspector: "#f8fafb"
  placeholder: "#63767f"
  focus: "#ce970c"
typography:
  body:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  heading:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 26px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  heading-mobile:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  section:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-0.015em"
  label:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 12px
    fontWeight: 650
    lineHeight: 1.55
  button:
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.55
  amount:
    fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace'
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.55
  evidence:
    fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace'
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.65
rounded:
  field: 4px
  control: 5px
spacing:
  label-gap: 5px
  tight: 7px
  control-block: 8px
  field-inline: 10px
  compact: 12px
  control-inline: 13px
  form-gap: 16px
  mobile-inline: 18px
  pane-gap: 20px
  compact-main: 24px
  section-block: 26px
  rail-block: 30px
  section-gap: 36px
  wide-inline: 48px
components:
  body:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
  muted-text:
    textColor: "{colors.muted}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.white}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.white}"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    typography: "{typography.button}"
  button-secondary-hover:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    typography: "{typography.body}"
  input-placeholder:
    textColor: "{colors.placeholder}"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-text}"
  rail-muted:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-muted}"
  rail-status:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-status}"
  wallet-hover:
    backgroundColor: "{colors.wallet-hover}"
    textColor: "{colors.wallet-text}"
  wallet-selected:
    backgroundColor: "{colors.wallet-selected}"
    textColor: "{colors.wallet-text}"
  selected-row:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.ink}"
  notice:
    backgroundColor: "{colors.amber-bg}"
    textColor: "{colors.amber}"
    rounded: "{rounded.control}"
  error:
    textColor: "{colors.danger}"
  outflow:
    textColor: "{colors.outflow}"
  inspector:
    backgroundColor: "{colors.inspector}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  table-border:
    backgroundColor: "{colors.border}"
  focus-outline:
    backgroundColor: "{colors.focus}"
---

# Design System: Solana Flow Workbench

## Overview

**Creative North Star: "Evidence first"**

The implemented workbench expands the restrained report identity into an operational workspace: slate navigation, white working surfaces, teal actions and amber uncertainty. Compact system type and monospace identifiers keep evidence readable without external fonts or assets. This document refreshes the previous dark offline-report description; it records the workbench, not a claim that every report surface uses these values.

**Key Characteristics:**
- Local system fonts, tabular numerals and exact evidence text.
- Flat, bordered working regions rather than decorative dashboard cards.
- Explicit scope, uncertainty and status labels alongside color.

Source of truth: `src/solana_flow/assets/workbench.css`, `workbench.html` and `workbench.js`. Product constraints come from `PRODUCT.md`; the inherited direction is in `.planning/phases/06-workbench/CONTEXT.md`. `DESIGN.md` holds reusable primitives; `.impeccable/design.json` holds source-derived extensions; `tokens.json` is the official CLI DTCG export. The CSS remains authoritative if implementation and documentation diverge.

## Colors

Teal is the interaction and inflow accent, not proof of completeness or transaction success. Ink carries primary text; muted slate carries supporting context. White is the workspace ground; the surface token groups table headers, coverage JSON and empty results. The inspector has its own slightly lighter cool surface.

The rail pairs slate ground with light text, muted labels and a pale teal connection-status line. Wallet hover and selected backgrounds are distinct; selection is also exposed by `aria-current`.

Amber text and pale amber background identify scoped, synthetic or partial evidence notices. Failed and unknown transaction tags also use amber; operational request errors use danger red. Outflows use a separate brown-red, with a direction label and signed amount, not color alone. Border and focus tokens are non-text treatments, not background/text pairings.

## Typography

Body text is system sans (14px, line-height 1.55). The main heading is 26px, 700 weight, line-height 1.2 and negative tracking; the topbar heading becomes 24px at the mobile breakpoint. Section headings are 18px; generic subheadings are 15px, with inspector headings at 14px. Labels are 12px/650. The brand uses 22px/750, becoming 20px on mobile.

Ledger and asset tables use 12px text with 11px headers. Amounts are right-aligned, non-wrapping monospace with tabular numerals. Signature buttons use 11px monospace and a maximum visible width of 245px with ellipsis; full identifiers remain available in the inspector. Mints and timestamps use 10px text; mints wrap anywhere. Evidence JSON is 10px monospace with line-height 1.65, pre-wrapping and anywhere wrapping. Body numerals are tabular by default.

## Layout

| Range | Implemented behavior |
| --- | --- |
| Base, above 1180px | Shell columns: 254px rail and `minmax(0,1fr)` workspace. Rail padding 30px 20px. Main padding `30px clamp(20px,3vw,48px) 20px`, width 100%, maximum 1800px. Investigation columns: flexible ledger and 295px inspector, gap 20px. Ledger table minimum width 650px. |
| At least 1600px | Inspector column becomes 340px; ledger table minimum width becomes 740px. |
| At most 1180px | Rail becomes 220px with 25px 16px padding; main horizontal padding 24px. Inspector follows ledger in one column; its JSON maximum height falls from 520px to 320px. Filters become three equal columns, search spanning two. Export actions wrap within 160px and their label takes a full line. |
| At most 700px | Shell becomes block flow; rail moves above main with 18px 20px padding. Wallet panel is hidden until its toggle opens it; rail footer is hidden. Main padding is 24px 18px. Capture selector and export group stack; exports remain one row. Filters use two columns and search spans both. Comparison form and operation columns become single-column. Inspector padding becomes 16px. |

Filters use `minmax(180px,2fr) repeat(3,minmax(100px,1fr)) auto` with 10px gaps on the base layout. Capture selection is flexible with a 550px maximum; facts wrap with 12px 34px gaps, changing to 16px 25px on mobile. Comparison and operations have 36px separation and 26px top padding, changing to 28px and 23px on mobile. Tables scroll inside focusable, named regions; keep `min-width:0` on the surrounding grid children rather than widening the document.

Mobile sets generic button/input/select minimum height to 44px, including wallet controls. More-specific rules retain their exceptions: pagination buttons/selects remain 36px, signature buttons 28px, quiet rail controls 32px, job-list buttons 32px and Refresh jobs 34px. The checkbox remains 16×16px through its more-specific rule; summaries retain 32px minimum height. Filter controls explicitly receive 44px minimum height. Do not describe a universal 44×44 target. Signature buttons retain ellipsis rather than making the ledger reflow into cards.

## Elevation & Depth

No shadows, gradients or floating decorative layers are defined. Depth comes from solid surface tones, one-pixel borders and section dividers. The inspector aligns to the start of its grid cell; neither rail nor inspector is sticky. The skip link alone is fixed and raised with z-index 10 when focused.

Motion is enabled only under `prefers-reduced-motion: no-preference`: buttons, links, inputs and selects transition background and border color over 120ms ease-out; selected rows animate from pale green to the selected surface over 180ms ease-out. Reduced-motion users receive no authored transitions or selection animation.

## Shapes

Inputs and selects have 4px corners. Buttons, notices, table-scroll wrappers and inspector use 5px corners. Controls use one-pixel strokes: button border `#b8c9cf`, button hover border `#7c999e`, input border `#a8bcc4`, notice border `#dfc790`; table and inspector use the border token. These are practical frames, not pill shapes.

## Components

### Buttons and fields

Primary buttons are teal with white text; enabled hover deepens the fill. Secondary buttons are white/ink and hover to the surface tone. Default padding is 8px 13px, minimum height 40px; the minimum is documented here because the frontmatter schema has no min-height property. Disabled buttons use opacity 0.55 and a not-allowed cursor. Disabled fieldsets use opacity 0.65. Inputs/selects use 8px 10px padding, full width, teal caret and a muted placeholder. Labels remain visible above fields. All focus-visible elements receive a 3px amber outline with 3px offset; no replacement focus glow is implied.

### Navigation

Wallet buttons show label, full wrapping address and cluster. Hover changes background and border; current wallet changes both again and uses `aria-current="true"`. Quiet refresh controls have no filled background. At mobile size, the labeled Show wallets / Hide wallets button controls the collapsible panel and updates `aria-expanded`; the workspace itself stays in document flow.

### Ledger and inspector

Tables retain semantic headers, captions and right-aligned exact amounts. Selecting a signature marks its row, fills inspector fields and source JSON, and focuses the inspector heading. At widths of 1180px or below, native focus scrolls the stacked inspector into view; wider side-by-side layouts preserve scroll position. A missing source produces explicit unavailable evidence, not an invented transaction. Loading sets `aria-busy` on the ledger, displays a loading message and disables page controls; empty matches, no capture and fetch failure have distinct messages. Page size choices are 25, 50 and 100, with 50 selected initially. Changing capture, wallet or filters clears stale selection and inspector content.

### Notices, comparison and operations

Provenance appears before capture overview. Static mode explicitly says read-only demonstration and disables registration/import/live capture. Comparison needs two captures and displays added, removed and changed signatures without treating missing evidence as proof of reorganization. Import, registration and capture forms use native controls, visible labels, disabled states and text feedback. Header entry buttons open the existing import/capture details and focus the first usable input (or summary when disabled). Their flex group uses an 8px gap and wraps with the title on narrow screens; static mode disables both entry buttons. Background jobs expose textual state and an Open capture action when available; local polling pauses while the document is hidden.

### Exact values and uncertainty

These are implemented presentation semantics, not visual guarantees of data completeness. Decimal unit formatting uses integer strings and `BigInt`, preserves the configured fractional digits and returns `Unknown` for invalid integer text or decimals outside the supported range. Aggregation groups by asset, mint and decimals, never by an unlike-asset combined balance. JSON decoding preserves unsafe integer lexemes and large decimal/exponent lexemes as text; ordinary fractional/scientific JSON values remain numbers. This is not a claim that every JSON numeric token is represented as text.

The inspector labels base units, decimals, status, slot and wallet-paid fees explicitly. Capture overview totals cover the whole capture, not the filtered ledger; exports likewise cover the full selected capture. Net changes are not current balances. Synthetic, partial and scoped notices remain textual and visible; unknown time or unavailable source must not silently become certainty. Fees, rent and multiple instructions may contribute to a delta. The interface makes no USD pricing, payment-intent, tax, transfer-classification or complete-history claim.

## Do's and Don'ts

- **Do** keep system sans, monospace evidence and tabular amounts local and dependency-free.
- **Do** preserve named scroll regions, visible keyboard focus, labels and textual uncertainty.
- **Do** preserve full evidence in the inspector when a signature is visually shortened.
- **Don't** round exact base-unit strings through floating-point display formatting.
- **Don't** present filtered ledger counts as capture-wide totals or net deltas as balances.
- **Don't** use teal, amber or transaction status as proof of complete coverage.
- **Don't** infer a new design system for the older offline report from this workbench-only record.
