# Slide deck prompt: NetCoop AI in 6 slides

Paste everything below the line into Claude or another slide tool. Attach the ten screenshots
from `deliverables/5_working_prototype/screenshots/` too, because the prompt refers to them by
file name.

---

## Your job

You are a senior presentation designer. Build a **6-slide, 16:9 deck (1920 × 1080)** for
**NetCoop AI**, a hackathon project at the Agentic AI Hackathon, IIT Bhubaneswar.

The deck should read like **the opening pages of a well-made research journal**: calm, precise,
evidence-first. Every claim visibly points to its proof.

Use **only the facts in this prompt**. Keep every number and name exactly as written; do not
round or invent numbers. Where you need a value this prompt doesn't give, leave a visible
`[placeholder]` in brackets.

## 1. The visual world: "Journal of Record"

The deck mirrors the product's own dashboard, which lays out each diagnosis like a scientific
paper. Think of a printed journal article, not a pitch deck: white pages, black ink, one deep
journal blue, and a red reserved for proof.

### Canvas

- **Background:** clean white `#FFFFFF`.
- **Ruled baseline lines:** very faint horizontal lines in `#F1F2F5`, 1 px, every 36 px. Like
  ruled journal columns, never a grid.
- **Margins:** 112 px left and right, 72 px top, 120 px bottom.
- **Running head (top of every slide):**
  - `NetCoop AI · Agentic AI Hackathon, IIT Bhubaneswar` on the left, in 22 px small caps,
    slate `#6A7180`
  - `p. 2 / 6` on the right, in monospace
  - a 1 px hairline in `#16181D` underneath, across the full width
- **References strip (bottom of every slide):** a 1 px rule, then one line of numbered
  references in 22 px sans, slate. Each slide's red citation numbers are explained here (see
  the signature below).

### Colour

| role | hex | use |
|---|---|---|
| Page | `#FFFFFF` | background |
| Ink | `#16181D` | titles and body text |
| Ink, soft | `#4A5160` | secondary text, captions |
| Journal blue | `#1F3A7A` | the one solid colour field per slide: a band, a panel or a hub circle; light text on it |
| Citation red | `#C8361B` | **only** for citation numbers and the single "proof" mark on a slide; never decoration |
| Agent teal | `#0F766E` | the performance agent and "good" states (paired with the word) |
| Agent ochre | `#9A5B0B` | the infrastructure agent |
| Agent violet | `#6D3FC0` | the wireless / service agent |
| Agent blue | `#0B65A3` | the connectivity agent |
| Courtroom crimson | `#A3123A` | prosecutor, defense and judge |
| Outcome: diagnosed | text `#0F6B4F` on `#E4F3EC` | always paired with the word "Diagnosed" |
| Outcome: abstained | text `#8A5300` on `#FBF0DC` | always paired with "Not enough evidence" |
| Outcome: no fault | text `#1F3A7A` on `#E8EDF8` | always paired with "No fault detected" |

Rules:
- Colour never carries meaning alone; every status also shows its word.
- Text contrast is at least 4.5:1.
- Each slide gets **one** solid journal-blue field and **one** red proof mark at most.

### Type

- **Source Serif 4** for titles, claims and the pull-quote.
  - Titles: 600 weight, 60 px, line-height 1.12, tracking −0.5 px.
  - The cover title: 112 px.
- **Public Sans** for body, labels and tables.
  - Body: 26–28 px. Nothing below 22 px anywhere.
  - Numbers in tables use tabular figures.
- **JetBrains Mono** for section marks, commands, file names, message types and IDs: 22–26 px.
- **Section mark** above each title, in mono, slate: `§2 · How it works`.
- **Titles are claims, not topics.** "Agents reach a verdict by citing each other's evidence",
  not "Architecture".
- **The emphasis move:** in each title, exactly one phrase, the one carrying the point, is set
  in **Source Serif italic** with a 4 px citation-red underline offset 6 px below the baseline.
  Once per slide.

### The signature: claims cite their proof

The product's own report puts a small red superscript number after each claim, and the number
leads to the message that proves it. Do the same on every slide:
- Every number or claim in the body gets a red superscript citation, like 98.6%¹ or
  zero errors².
- The references strip at the bottom resolves each one in plain words, for example:
  `¹ docs/EVALUATION.md, 1,080 fresh test runs · ² netcoop translate, interop sample`.
- Keep citations small (0.6 em, bold sans, red). They should feel like a journal, not a
  warning.

### Figures and screenshots

- Every visual is a **numbered figure** with a caption underneath: `Fig. 3` in bold ink, then
  the caption in 22 px soft ink. Example: "**Fig. 3** The agents' message exchange for one run:
  one lane per agent; lines join each message to its cause."
- **Screenshots** sit in a quiet browser frame:
  - a 1 px `#DFE3EA` border, radius 10 px
  - a 36 px top bar in `#F4F6FA` with three small grey dots and the URL
    `127.0.0.1:8765` in mono
  - soft shadow `0 18px 48px rgba(22,24,29,.14)`
  - never stretched; crop to the region that matters
- **Annotations on screenshots:** numbered pins (28 px circles in ink with white mono numerals)
  with thin 2 px ink leader lines to short labels in the margin. At most three per screenshot.
  These are labels, not citations, so they are never red.
- **Diagrams:** hairline (2 px) line drawings in ink, with agent colours only where an agent is
  meant. Use rounded small-caps labels and numbered nodes. No 3D, gradients, stock photos,
  emoji or clip-art.
- **Tables:** booktabs style, as in a journal:
  - a 2 px ink rule above and below, and a 1 px rule under the header
  - no vertical lines
  - right-aligned numbers
  - the single most important number in bold, followed by its red citation

### Rhythm

- One idea per slide and one focal figure per slide, readable in 5 seconds.
- Alternate the layouts so no two adjacent slides look alike: split 55/45, full-width figure,
  table plus margin notes, and so on.
- About 65% of the area is used; the rest is quiet white.
- The running head, section mark, title position and references strip stay in exactly the same
  place on every slide.

## 2. The six slides

### Slide 1: Cover

- **Layout:** split. On the **left 56%**, white page:
  - the section mark `Agentic AI Hackathon · IIT Bhubaneswar`
  - the title "NetCoop **AI**", 112 px serif, with "AI" in journal blue
  - the claim beneath it, in 40 px serif: "Network faults diagnosed by cooperating agents, and
    *every claim cites its proof*." The italic phrase gets the red underline.
  - a one-line description in 26 px sans: "Specialist agents analyse a campus network's
    telemetry, exchange typed messages on a shared case board, and publish one explainable
    report, or honestly say there isn't enough evidence."
  - a quiet contents list in mono:
    `§1 Problem · §2 How it works · §3 Agents in action · §4 The report · §5 Robustness · §6 Results`
  - the team: a small mono label "Team" above the name **Havoc** in serif, next to an ink circle
    with the initial "H". No member names and no photos.
- **Right 44%:** a solid journal-blue panel holding a **line drawing**:
  - a small campus network as a topology: a core switch, two distribution switches, access
    switches, Wi-Fi access points, and DNS / DHCP servers, drawn as rounded hairline nodes in
    off-white
  - one link drawn in citation red (the fault)
  - four small agent circles orbiting the network in the agent colours, joined by dashed lines
    to a central "case board" rectangle
- **Running head:** `p. 1 / 6`. The references strip on this slide holds only the repository:
  `github.com/suvronilchatterjee7-create/netcoop-ai`.

### Slide 2: §1 Problem → §2 How it works

- **Title:** "Specialist agents reach one verdict *by citing each other's evidence*"
- **Focal figure (full width), Fig. 1, the pipeline as a left-to-right flow of hairline boxes:**
  1. **Raw telemetry** (any format: JSONL, legacy CSV)
  2. **Translator**: maps fields and units, scores data quality, never crashes on input
  3. **Case board**: an append-only shared log of typed, versioned messages; draw it larger, as
     a ledger
  4. **Four specialist agents** around the board, in their colours:
     - performance (latency, jitter, loss, utilisation)
     - infrastructure (devices, queues, interface errors)
     - wireless / service (Wi-Fi, DNS, DHCP)
     - connectivity (topology, blast radius)
  5. **Correlator**: calibrated scoring, claims a cause only above the bar
  6. **Courtroom**: prosecutor, defense and judge, called only on a near tie
  7. **Reporter** → **one report** (`report.json` + `report.md`) and a replayable
     `trace.jsonl`
- **Under the figure, a row of three short margin notes:**
  - **Problem:** evidence of a network fault is scattered across devices, links, Wi-Fi and
    services, in different formats.
  - **Approach:** agents never call each other; they only post typed messages (13 types, such
    as CLUE, HYPOTHESIS, REQUEST, RESPONSE, SUPPORT, CONTRADICT, VERDICT) on a shared board.
  - **Guarantee:** the same input and configuration give a byte-identical trace¹.
- **References:** `¹ netcoop replay verifies every trace (tests/test_orchestrator.py)`.

### Slide 3: §3 Agents in action

- **Title:** "One diagnosis, *every message on the record*"
- **Layout:** split 55/45.
- **Left:** screenshot `02_live_diagnosis_fig1.jpg`, cropped to the "Fig. 1" swimlane panel.
  Caption: "**Fig. 2** The agents' message exchange for a link-congestion run: one lane per
  agent, rounds left to right, lines from each message to its cause." Pins:
  - ① "performance proposes link congestion"
  - ② "requests and answers between agents"
  - ③ "the correlator's verdict"
- **Right:** a vertical numbered sequence (journal-style numbered paragraphs, no cards):
  1. The Translator reads raw telemetry into **406 observations**¹.
  2. Specialists compare each metric with calibrated baselines and post **457 clues**¹,
     including the "checked, normal" ones.
  3. Performance posts a **HYPOTHESIS** (link congestion), then **3 REQUESTs** for evidence it
     cannot see itself.
  4. Infrastructure and wireless **RESPOND**; three agents post **SUPPORT** stances.
     Connectivity confirms the symptoms sit inside the link's blast radius.
  5. The correlator issues the **VERDICT**: diagnosed, confidence 1.00.
- **Pull number at the bottom right:** "887 messages, 3 collaboration rounds"¹, in serif,
  48 px.
- **References:** `¹ netcoop run data/samples/link_congestion__s500__i1.0__n0.0__m0.0`.

### Slide 4: §4 The final report

- **Title:** "The report reads like a paper: *each claim links to its proof*"
- **Focal figure (left 60%):** screenshot `03_report_citation_hover.jpg`, cropped to the report
  header, the abstract and Fig. 1 on the right, showing the highlighted message. Caption:
  "**Fig. 3** Hovering a red citation lights up the message that proves it." Pins:
  - ① "root cause and calibrated confidence"
  - ② "a red citation"
  - ③ "the cited message, highlighted"
- **Right 40%: what the report contains**, as a compact list:
  - root cause at a specific link: "Link congestion on department-dist-01 →
    department-acc-02"¹
  - evidence with its baseline: "utilisation 97% against a normal 27.4%; jitter 8.21 ms
    against 0.197 ms; 104 egress queue drops against 0"¹
  - recommended actions, for human review only; nothing is executed automatically
  - affected devices, alternatives considered, data quality, limitations
- **Below, two small framed thumbnails side by side**, each with a one-line caption and an
  outcome chip with its word:
  - `06_abstention_not_enough_evidence.jpg`: the "Not enough evidence" chip (amber) and
    "A faint fault: NetCoop abstains instead of guessing."
  - `08_courtroom_deferred.jpg`: a "Courtroom: deferred" chip and "A fault type never seen in
    training: the judge defers rather than guess."
- **References:** `¹ report.md of the link-congestion sample (deliverables/4_sample_data_and_test_cases/example_reports)`.

### Slide 5: §5 Interoperability and robustness

- **Title:** "Messy, foreign data *bends but never breaks* the pipeline"
- **Layout:** table plus margin.
- **Left, Fig. 4:** screenshot `05_legacy_csv_translate.jpg`, cropped to the two output lines.
  Caption: "**Fig. 4** A legacy CSV export: 5 files, 466 series, 13,980 samples, 0 errors."
  Pin ①: "dialect detected: legacy_v1".
- **Right, Table 1**, booktabs style. Title: "Precision of claims as stacked format mutations
  increase."

  | mutations stacked | runs | precision of claims |
  |---|---|---|
  | 0 | 48 | 97.5% |
  | 1 | 48 | 97.1% |
  | 2 | 50 | 96.3% |
  | 3 | 46 | 95.7% |

  The last row is bold, with citation ¹.
- **Under it, three margin notes on error handling**, each with a short label word:
  - **Bad input** → typed ERROR messages and lower data-quality scores; the Translator never
    raises on input (22 kinds of corruption tested²).
  - **Agent failure or timeout** → that agent is isolated and its missing evidence is listed in
    the report.
  - **Fatal problem** → never a false "no fault".
- **References:** `¹ docs/EVALUATION.md, robustness · ² docs/INTEROP_RESULTS.md`.

### Slide 6: §6 Results and what we deliver

- **Title:** "On 1,080 fresh runs, *98.6% of claims are right*"
- **Top band (the one journal-blue field):** four big numbers in light serif, each with its word
  label beneath in sans:
  - **98.6%**¹ precision of claims (12 wrong of 846)
  - **77.2%**¹ accuracy
  - **100%**¹ root localisation
  - **0**² wrong claims on 120 runs of never-seen fault types
- **Below it, split 50/50:**
  - **Left: Table 2, "Full system on the fresh test suite"**, booktabs:

    | metric | value |
    |---|---|
    | abstention rate | 21.7% |
    | macro-F1 | 0.860 |
    | courtroom invoked | 227 runs |
    | wrong claims on ambiguous cases, without vs with courtroom | 32 → 0³ |

  - **Right: "Deliverables"**, a numbered list in mono and sans:
    1. Working prototype: the `netcoop` CLI and a local dashboard (`netcoop serve`)
    2. Source, setup, dependencies, and **246 tests** passing in CI⁴
    3. Architecture documentation: agents, protocol, orchestration, correlation, errors,
       workflow
    4. Nine labelled samples: normal operation plus eight fault scenarios
    5. A 4 min 25 s demo video
    6. Extensible: new agents and faults are data, external agents join over MCP, runs can
       pause and resume, and humans can review actions
- **Closing line at the bottom, in serif italic:** "NetCoop AI: every claim cites its proof."
  Next to it, the repository URL in mono: `github.com/suvronilchatterjee7-create/netcoop-ai`.
- **References:** `¹ docs/EVALUATION.md · ² ambiguity suite, seeds 100–109 · ³ docs/COURTROOM_RESULTS.md · ⁴ pytest, 246 passed`.

## 3. Before you deliver, check

- [ ] Every number matches this prompt exactly.
- [ ] Every claim with a number carries a red citation, and the references strip resolves it.
- [ ] Red appears only as citations or the one proof mark; there is one journal-blue field per
      slide.
- [ ] Every coloured status also shows its word.
- [ ] No text is under 22 px, and nothing overflows its box.
- [ ] Screenshots are cropped, never stretched, and framed consistently.
- [ ] The running head, page number and references strip are on all six slides.
- [ ] There are no stock photos, emoji or logos, and no team details beyond the team name, Havoc.

**Deliver:** 6 slides, 16:9, as PPTX and PDF.
