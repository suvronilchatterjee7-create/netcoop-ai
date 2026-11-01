---
name: NetCoop AI
description: A network diagnosis published like a research paper, with every claim cited to the agent message that proves it.
colors:
  page: "#ffffff"
  rail: "#f4f6fa"
  ink: "#16181d"
  ink-2: "#4a5160"
  ink-3: "#6a7180"
  rule: "#dfe3ea"
  rule-2: "#eef0f4"
  shell: "#1f3a7a"
  shell-2: "#2c4c96"
  shell-ink: "#c9d5f2"
  cite: "#c8361b"
  cite-wash: "#fcebe6"
  ok: "#0f6b4f"
  ok-wash: "#e4f3ec"
  hold: "#8a5300"
  hold-wash: "#fbf0dc"
  calm: "#1f3a7a"
  calm-wash: "#e8edf8"
  bad: "#a3123a"
  bad-wash: "#fbe7ec"
  agent-performance: "#0f766e"
  agent-infrastructure: "#9a5b0b"
  agent-wireless-service: "#6d3fc0"
  agent-connectivity: "#0b65a3"
  agent-courtroom: "#a3123a"
  agent-reporter: "#3b4252"
typography:
  headline:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  abstract:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.1875rem"
    fontWeight: 400
    lineHeight: 1.6
    fontFeature: "\"onum\", \"pnum\""
  prose:
    fontFamily: "Source Serif 4, Iowan Old Style, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "\"onum\", \"pnum\""
  body:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "\"tnum\""
  title:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.4
  label:
    fontFamily: "Public Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  mono:
    fontFamily: "ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  xs: "3px"
  sm: "4px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
components:
  button-primary:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.page}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.shell-2}"
  button-ghost:
    backgroundColor: "{colors.page}"
    textColor: "{colors.shell}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "38px"
  button-ghost-hover:
    backgroundColor: "{colors.calm-wash}"
  status-diagnosed:
    backgroundColor: "{colors.ok-wash}"
    textColor: "{colors.ok}"
    rounded: "{rounded.xs}"
    padding: "2px 8px"
  status-insufficient-evidence:
    backgroundColor: "{colors.hold-wash}"
    textColor: "{colors.hold}"
    rounded: "{rounded.xs}"
    padding: "2px 8px"
  status-no-fault:
    backgroundColor: "{colors.calm-wash}"
    textColor: "{colors.calm}"
    rounded: "{rounded.xs}"
    padding: "2px 8px"
  status-failed:
    backgroundColor: "{colors.bad-wash}"
    textColor: "{colors.bad}"
    rounded: "{rounded.xs}"
    padding: "2px 8px"
  citation:
    textColor: "{colors.cite}"
  input-field:
    backgroundColor: "{colors.page}"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "34px"
  top-bar:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.shell-ink}"
    height: "56px"
    padding: "0 24px"
  rail-item-selected:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: NetCoop AI

## Overview

**Creative North Star: "Journal of Record"**

The dashboard reads as a published research paper about one incident. A white journal page carries a serif headline naming the root cause, an abstract whose claims carry red superscript citations, then numbered evidence, actions, alternatives and the courtroom ruling. Beside it, Fig. 1 plots the agents as swimlanes over rounds, and every numbered point in the figure is the message a citation refers to. A journal-blue shell (top bar, tinted rail) frames the page the way a journal's masthead frames an article.

Density is that of a paper, not a console: one incident at a time, measured line lengths (66ch), section heads separated by hairline rules rather than boxes. Depth is flat. Structure comes from rules, column dividers and type contrast between the serif voice of the report and the sans voice of the instrument (labels, data, controls).

The signature is the citation link: a superscript in the prose, a point in the figure and an entry in the references list are one object. Hovering or focusing any of them lights the other two in citation red.

**Key Characteristics:**
- White page, ink text, journal-blue shell; no cards, no shadows.
- Serif (Source Serif 4) for what the report says; sans (Public Sans) for UI, data and figure labels; mono for identifiers.
- Citation red appears only on citation marks and whatever they currently point at.
- Fig. 1 is drawn at 1:1 as agent lanes by rounds; agents are figure series colours.
- Hairline rules and column dividers do the structural work.

## Colors

A restrained paper palette: ink on white inside a single deep-blue frame, one red reserved for citations, and muted figure-series hues for the agents.

### Primary
- **Journal Blue** (shell): the top bar background, primary buttons, links, ghost-button text and the focus ring. Its lighter step **Journal Blue Lift** (shell-2) is the primary hover and the focus outline colour. **Masthead Ink** (shell-ink) is the quiet text on the blue bar: brand suffix, inactive tabs, the locality note.

### Secondary
- **Citation Red** (cite): superscript citation numbers, reference numbers, the halo on the cited point, the lit edge in Fig. 1 and the lit lane label. **Citation Wash** (cite-wash) highlights the lit reference row and the text selection.

### Tertiary
- **Agent series** (agent-*): figure series in Fig. 1 and the legend. Performance teal, infrastructure ochre, wireless/service violet, connectivity blue, courtroom crimson (prosecutor, defense, judge share it), reporter slate. Translator and orchestrator use Muted Ink (ink-3); correlator uses Ink.
- **Outcome pairs**: each status has a text colour and a wash. Ledger Green (ok / ok-wash) for diagnosed and resolved rulings, Amber Hold (hold / hold-wash) for insufficient evidence and deferred rulings, Calm Blue (calm / calm-wash) for no fault detected, Fault Crimson (bad / bad-wash) for failed runs and the offline banner.

### Neutral
- **Page White** (page): the report and figure background; selected rail items lift to it.
- **Rail Tint** (rail): the left input rail and table-row hover.
- **Ink** (ink): body text, headlines, the Fig. 1 top rule, the heavy table rules, the root-cause device chip.
- **Secondary Ink** (ink-2): metadata lines, captions' bold lead, lane labels, the empty-state prose.
- **Muted Ink** (ink-3): section labels, source lines under evidence, captions, identifiers.
- **Rule** (rule): column dividers, section-head hairlines, rail borders.
- **Faint Rule** (rule-2): table row dividers, lane rules, code and device-chip fills.

### Named Rules
**The One Job Rule.** Citation red marks citations and the thing a citation points at. Nothing else is red-orange: not errors, not emphasis, not buttons.

**The Outcome Pair Rule.** Every status is a text colour on its own wash. Abstention (hold) and no-fault (calm) are styled as outcomes with the same weight as diagnosed, never as greyed-out or failed.

## Typography

**Display Font:** Source Serif 4 (with Iowan Old Style, Georgia)
**Body Font:** Public Sans (with Segoe UI, system-ui)
**Label/Mono Font:** ui-monospace (with Cascadia Mono, Consolas)

**Character:** A scholarly serif carries the report's argument; a civic, plain sans runs the instrument around it. The serif uses old-style proportional numerals so figures sit inside sentences; the sans uses tabular numerals so data lines up.

**Font files:** both families are self-hosted as latin-subset variable woff2 files in `netcoop/web/static/fonts/` (SIL OFL 1.1, licence texts beside them), declared with `@font-face` at the top of `app.css`, so the page renders in its own type with no network. Glyphs outside the latin subset, notably the → arrow, fall back to Georgia / Segoe UI.

### Hierarchy
- **Headline** (600, 1.875rem, 1.2, -0.01em): the root-cause statement and page titles; max 30ch, balanced wrap. Drops to 1.375rem under 760px.
- **Abstract** (400, 1.1875rem, 1.6, serif): the opening paragraph with citations; max 66ch. Drops to 1.0625rem under 760px.
- **Prose** (400, 1.0625rem, 1.55, serif): evidence and action list items, ledes, empty-state copy, the live "now" line; max 66ch.
- **Body** (400, 0.9375rem, 1.5, sans, tabular numerals): UI default.
- **Title** (600, 0.8125rem, sans): rail item names, metadata, status pills, table cells.
- **Label** (700, 0.75rem, 0.08em, uppercase, sans, Muted Ink): report section heads (Evidence, Actions) and rail group heads, each sitting on a hairline rule. These are section headings, not decorations above a headline.
- **Mono** (500, 0.75rem): run folder names, message ids, device chips, inline code.

### Named Rules
**The Two Voices Rule.** Serif is the report speaking; sans is the instrument. A claim the system makes is set in serif; a control, label, measurement or figure annotation is set in sans.

**The Numeral Rule.** Serif prose uses old-style proportional numerals; everything else is tabular.

## Layout

A three-column journal spread on desktop: input rail (284px), report (flexible, 32px top / 48px side padding), and Fig. 1 (minmax(400px, 34vw), sticky to the viewport and independently scrollable). Columns are divided by 1px Rule lines, not gutters or cards. Text measures are capped at 66ch for report prose and 72ch for the references list.

Below 1180px the figure moves under the report in the second column and the rail narrows to 260px. Below 760px everything stacks into one column: rail, report, figure; padding drops to 24px / 16px, the locality note in the bar hides, and the Diagnose button moves under the headline.

Spacing follows a 4px base scale (s1 to s7: 4, 8, 12, 16, 24, 32, 48). Section heads take 32px above and 12px below, with 12px between the rule and the label. Secondary pages (Past runs, Evaluation) use the same report padding with a 1180px max width.

## Elevation & Depth

Flat. There are no shadows anywhere. Depth is conveyed by tone (the blue bar, the tinted rail, the white page), by 1px hairline rules, and in tables by the journal convention of heavy 2px Ink rules top and bottom with a 1px Ink rule under the header row. The only layering is the sticky figure column.

### Named Rules
**The Hairline Rule.** Separate with a 1px rule or a change of ground, never with a shadow or a bordered card.

## Shapes

Nearly square. Controls and containers use a 4px radius (buttons, fields, rail items, error notes); small inline objects use 3px (status pills, device chips, reference rows, code). Circles appear only as data: Fig. 1 points (12px radius with a 2px white stroke and a 15px red halo when cited) and the 9px legend dots. Fig. 1 edges are thin cubic curves; round rules are dashed (2 3).

## Components

### Buttons
Solid, plain and confident, with a play icon.
- **Shape:** gently squared (4px), 38px tall, 16px side padding, 600 weight, 8px icon gap.
- **Primary:** Journal Blue fill with white text and a matching 1px border.
- **Hover / Focus:** fill lifts to Journal Blue Lift over 150ms on the house ease; 1px press on active; 2px Journal Blue Lift focus outline at 2px offset.
- **Ghost:** white fill, Journal Blue text and border; hover washes to Calm Wash. Used for "Diagnose again" once a report exists.
- **Disabled:** desaturated blue (#9aa6c0) with a progress cursor while a run is in flight.

### Chips
- **Status pill:** Title type on its outcome wash, 2px 8px padding, 3px radius (see Outcome Pair Rule).
- **Device chip:** mono on Faint Rule; the root-cause device inverts to white on Ink.

### Inputs / Fields
- **Style:** white, 1px #c7cdd8 border, 4px radius, 34px tall, small caption label above in Secondary Ink.
- **Focus:** the global 2px Journal Blue Lift outline.

### Navigation
- **Top bar:** 56px Journal Blue band with the wordmark (700, with a 500 Masthead Ink suffix), tabs and a right-aligned locality note.
- **Tabs:** Masthead Ink at rest, white on hover and when selected; the selected tab carries a 3px white underline flush with the bar's bottom edge. Focus uses a white inset outline.
- **Rail items:** full-width rows, name in Title type with a Muted Ink description line; hover tints, the selected item lifts to Page White with a Rule border and bolder name.

### Citation (signature)
A superscript at 0.62em, 700 weight sans, Citation Red, kept non-breaking with its word. Hover, focus or the cited state underlines it, lights its Fig. 1 point (halo), the point's incoming edge, its lane label and its reference row (Citation Wash), and shows the message under the figure. Clicking a figure point scrolls to the claims that cite it.

### Fig. 1 (signature)
A numbered figure in journal style: bold "Fig. 1" lead in the header, an Ink top rule and Rule bottom rule framing the plot, a Muted Ink caption below. One lane per agent with its name above the band, rounds left to right with dashed round rules, numbered points in agent series colours, edges joining each message to its cause. Drawn at 1:1; busy lanes wrap onto extra rows rather than shrinking. New points enter with a 380ms scale-and-fade pop.

### Tables
Journal tables: 2px Ink rules top and bottom, 1px Ink under the header, Faint Rule between rows, caption above and left-aligned. Clickable rows tint to Rail Tint on hover.

## Do's and Don'ts

### Do:
- **Do** put every claim the report makes in serif and give it a citation that resolves to a numbered Fig. 1 point and a reference row.
- **Do** keep citation red (#c8361b) to citation marks and the currently cited point, edge, lane label and reference row.
- **Do** style abstentions and no-fault results with their own outcome pair, at the same weight as diagnosed.
- **Do** structure with 1px rules, column dividers and changes of ground; heavy 2px Ink rules for table tops and bottoms.
- **Do** cap report prose at 66ch and use the 4px spacing scale.
- **Do** colour agents only by their series token, in the figure and its legend.
- **Do** use the single house ease (cubic-bezier(0.16, 1, 0.3, 1)) at 150-200ms for state changes, and honour reduced motion.

### Don't:
- **Don't** use cards, bordered panels or drop shadows; the system is flat.
- **Don't** use citation red for errors, warnings, buttons or emphasis; failures use Fault Crimson on its wash.
- **Don't** shrink Fig. 1 to fit; wrap busy lanes onto extra rows.
- **Don't** set controls, labels or figure annotations in the serif.
- **Don't** add labels above the headline; the run folder and incident id sit in the metadata under it.
