# Video generation prompt: NetCoop AI demo (screen recording, about 4 min 40 s)

Copy everything below the line into the video generation tool. Each scene lists:
- the time window
- what the screen shows and what the cursor does
- the narration, which is spoken by Kokoro and burned in as subtitles word for word

Every number, label and screen element in this prompt comes from the real project, so keep
them exactly as written.

---

## PROMPT

Create a **4 minute 40 second screen-recording video** that demonstrates **NetCoop AI**. NetCoop AI is
an interoperable multi-agent system that diagnoses network faults, built for the Agentic AI
Hackathon at IIT Bhubaneswar.

The whole video is one continuous **desktop screen recording**:
- no camera, no presenter, no talking head, no stock footage
- no 3D or cinematic camera moves

It should feel like a developer recording their own screen while a calm narrator explains what is
happening live.

### Global format

- **Resolution and frame rate:** 1920 × 1080, 16:9, 30 fps.
- **The capture:** a Windows 11 desktop recorded at native resolution.
  - Only two windows ever appear: a dark **terminal** (black background, light grey monospace
    text, green prompt) and a **Chrome browser** window.
  - Windows switch with a quick, plain cut, the way a screen recorder captures Alt+Tab.
- **Cursor:** a standard white arrow cursor, always visible.
  - It moves smoothly and deliberately, like a human: slight easing, no teleporting.
  - Each click shows a soft circular click ripple (a light blue ring about 40 px wide that fades
    over 300 ms).
  - Typing in the terminal appears character by character at a realistic speed of about 12
    characters per second, with a blinking block caret.
- **Zoom:** gentle screen-recorder zooms only, a smooth 1.0× → 1.6× punch-in on the area being
  explained, held, then eased back out. These are the only camera moves allowed.
- **No other overlays** besides the subtitles and a small title card at the start and end.
- **Audio:**
  - narration only, voiced with **Kokoro TTS**: voice `af_heart` (warm, clear American English),
    speed 1.0, natural pauses at sentence ends
  - optional very quiet lo-fi background bed at −28 dB, ducked under speech
  - soft keyboard clicks while typing and a light mouse click sound on clicks, both quiet
- **Subtitles:**
  - burned in, bottom centre, white sans-serif (Inter or similar) at 40 px on a 70% black
    rounded box
  - at most two lines and about 42 characters per line
  - each phrase synced to the Kokoro speech and shown exactly as narrated
  - the subtitle box must never cover what the cursor is pointing at; move it to the top
    centre while the bottom of the screen is the focus

### What the NetCoop dashboard looks like (keep this consistent in every browser shot)

The browser shows `http://127.0.0.1:8765/`, a clean light page in a research-paper style.

**Top bar.** A deep navy blue bar (#1f3a7a) across the top holds:
- the white wordmark "NetCoop AI" on the left
- three tabs: **Diagnose**, **Past runs**, **Evaluation**; the active tab has a white underline
- small pale text on the right: "Local server · results stay on this machine"

**Left rail.** A very light grey-blue column, about 280 px wide.
- Heading "SAMPLE RUNS" in small caps, then a list of samples, each with a bold title and a
  small grey line under it. In order:
  1. Device overload
  2. DNS / DHCP failure
  3. Hardware failure
  4. Interface fault
  5. DNS / DHCP failure, marked "legacy CSV"
  6. Link congestion, "intensity 0.25"
  7. Link congestion, "intensity 1"
  8. Healthy network
  9. Weak Wi-Fi
- The selected item has a white background and a thin grey outline.
- Below the list: "MORE RUN FOLDERS", a "Collection" dropdown and a "Filter by name" search box.

**Centre column: the report.** White page, set like a journal article.
- The title is the root cause in a large serif typeface (Source Serif).
- Under it, a small line holds:
  - a coloured status pill: green "Diagnosed", amber "Not enough evidence", or blue
    "No fault detected"
  - the confidence, device count, rounds and message count
- Then an abstract paragraph in serif text. **Small red superscript citation numbers** follow
  each claim.
- Then sections with small uppercase grey headings and thin grey rules:
  - EVIDENCE (a numbered list, each item ending in a red citation number)
  - RECOMMENDED ACTIONS
  - AFFECTED DEVICES (small grey chips; the first, the root, is black)
  - COURTROOM TIE-BREAK (when present)
  - ALTERNATIVES CONSIDERED
  - DATA QUALITY AND LIMITATIONS
  - REFERENCES (a numbered list of the cited messages)
- A navy "▶ Diagnose" button sits at the top right of the report column. After a run it reads
  "Diagnose again" with a white background.

**Right column: "Fig. 1 How the agents reached the verdict".** A swimlane figure.
- **Layout.** Each agent has a horizontal band labelled above it:
  - translator, performance, infrastructure, wireless / service, connectivity, correlator,
    prosecutor, judge, reporter
  - rounds 0, 1, 2, 3, 4 run left to right across the top, with dashed vertical lines between
    rounds
- **Points.** Messages are small numbered circles (white numbers), coloured by agent:
  - translator grey
  - performance teal
  - infrastructure ochre-brown
  - wireless violet
  - connectivity blue
  - correlator near-black
  - courtroom agents crimson
- **Lines.** Thin grey curves join each message to the message that caused it.
- **Below the figure:**
  - a caption line
  - a counts strip: "406 observations · 457 clues · 11 capability cards · counted, not drawn"
  - a message panel that shows the hovered message's details

### Scene-by-scene timeline

**Scene 1 — Title and the problem (0:00–0:18)**
- **Screen:** a 3-second title card in the same navy colour: "NetCoop AI" in large white text,
  and beneath it "Interoperable multi-agent network fault diagnosis · IIT Bhubaneswar Agentic AI
  Hackathon". Then cut to the GitHub repository page
  `github.com/suvronilchatterjee7-create/netcoop-ai`. The README is visible, with its results
  table: 98.6% precision of claims, 77.2% accuracy, 21.7% honest abstentions, macro-F1 0.860,
  100% root localisation. The cursor scrolls slowly to the mermaid architecture diagram.
- **Narration:** "When a campus network slows down, the evidence is scattered across devices,
  links, Wi-Fi and services, in different formats. NetCoop AI lets specialist agents work
  together on that evidence and publish one explainable diagnosis. Let me show you, live."

**Scene 2 — Setup and launch (0:18–0:38)**
- **Screen:** the terminal. Type `pip install -e ".[dev]"`; show a few fast-scrolling install
  lines ending with "Successfully installed netcoop". Then type `netcoop serve`. The terminal
  prints "NetCoop dashboard on http://127.0.0.1:8765/ (Ctrl+C to stop)" and Chrome opens to the
  dashboard in its empty state:
  - the headline "Pick a run, then watch the agents diagnose it"
  - three numbered steps
  - Fig. 1 reading "Pick a run on the left."
- **Narration:** "It installs with one command and needs no cloud service. 'netcoop serve' starts
  a local dashboard that only listens on this machine. On the left are nine labelled sample
  runs, including a healthy network and several different faults."

**Scene 3 — Live diagnosis and inter-agent communication (0:38–1:30)**
- **Screen, before the run.** The cursor clicks "Link congestion, intensity 1" in the rail. The
  centre shows:
  - "Link congestion, ready to diagnose"
  - "Generator label Link congestion (the agents never see it)"
  - "native JSONL"
- **Screen, during the run.** The cursor clicks the navy "▶ Diagnose" button.
  - The centre switches to "Diagnosing…" with a grey "Diagnosing" pill. A live line updates as
    messages arrive, for example "infrastructure: egress_queue_drops on department-dist-01:
    abnormal…".
  - Zoom 1.5× on Fig. 1 as it **fills in point by point**, about one point every 0.15 s:
    - grey point 1 on the translator lane
    - teal point 2 (the HYPOTHESIS) and teal points 3, 4, 5 (REQUESTs) on performance in round 1
    - ochre points 7, 8, 9 (infrastructure), violet points 10, 11 (wireless) and blue point 6
      (connectivity) in round 2
    - grey curves drawing from point 2 to each answer
    - a black point 12 on correlator (the VERDICT) and point 13 on reporter (the REPORT) in
      round 4
  - The counts strip ticks up to "406 observations · 457 clues · 11 capability cards".
- **Narration:** "I'll pick a link-congestion run and press Diagnose. First the Translator turns
  raw telemetry into four hundred and six canonical observations. Each specialist compares its
  metrics with calibrated baselines and posts clues to a shared case board, four hundred and
  fifty-seven of them, including the 'checked, normal' ones. Here, the performance agent proposes
  link congestion. It can't see queue drops or Wi-Fi itself, so it sends requests. The
  infrastructure and wireless agents answer, and every agent posts a stance. Connectivity
  confirms the symptoms sit inside that link's blast radius. Each line in Fig. 1 joins a message
  to the one that caused it. Finally the correlator issues its verdict."

**Scene 4 — The final diagnostic report (1:30–2:10)**
- **Screen, the report.** Zoom eases out. The report appears:
  - title, in serif: "Link congestion on department-dist-01 → department-acc-02"
  - a green "Diagnosed" pill, then "Confidence 1.00 (high) · 6 affected · 3 rounds · 887
    messages"
  - the abstract: "The agents found utilization on department-dist-01 → department-acc-02 at
    97 percent against a normal 27.4 percent¹⁴, jitter … at 8.21 ms against a normal 0.197 ms¹⁵
    and egress queue drops on department-dist-01 at 104 count against a normal 0 count¹⁶.
    Proposed by performance². Supported by connectivity⁶, infrastructure⁷ and wireless /
    service¹⁰. The verdict¹² gives a calibrated confidence of 1.00."
- **Screen, the signature interaction.**
  - The cursor hovers over the red citation "²". In Fig. 1 point 2 gets a red ring, its lines
    turn red, and the message panel shows "2 hypothesis · performance → board, round 1 ·
    link_congestion at department-dist-01--department-acc-02 (proposer confidence 1.00)".
  - The cursor scrolls down through EVIDENCE (three numbered items with red citations, each
    with a small grey source line such as "performance · compared with
    baselines.utilization.link · 1 observation"), RECOMMENDED ACTIONS ("Identify the top
    traffic sources … rate-limit or reschedule bulk transfers", "Apply or review QoS …"), and
    AFFECTED DEVICES chips.
  - The note "For human review. NetCoop never executes a remediation" is visible.
- **Narration:** "This is the unified report. The root cause, a calibrated confidence, the
  affected devices and recommended actions. It reads like a research paper: every claim carries
  a red citation. Hover one, and Fig. 1 lights up the exact message that proves it. Every
  evidence line names the baseline it was compared with and the configuration key behind it, so
  nothing is a magic number. Remediation is only ever suggested for human review."

**Scene 5 — Interoperability: a legacy CSV export (2:10–2:35)**
- **Screen:** the cursor clicks "DNS / DHCP failure · legacy CSV" in the rail, then Diagnose.
  Fig. 1 refills quickly. Cut briefly to the terminal and type
  `netcoop translate data/samples/interop_failure__s500__i0.5__n0.1__m0.0`. It prints five
  files, each detected as `legacy_v1`, then the stats line "files: 5 … series: 466, samples:
  13980, errors: 0". Cut back to the browser: "DNS service failure at dns", green "Diagnosed",
  confidence 1.00.
- **Narration:** "Real networks export in different formats. This run comes from a legacy tool:
  CSV files, different field names, units and timestamps. A declarative mapping recovers every
  series with zero errors, and the same agents find a DNS failure. We tested the Translator
  against twenty-two kinds of schema corruption, and it never crashes."

**Scene 6 — Honest abstention (2:35–2:55)**
- **Screen:** the cursor clicks "Link congestion · intensity 0.25", then Diagnose. The report
  shows:
  - the title "Not enough evidence to name a cause" and an amber "Not enough evidence" pill
  - "No cause asserted"
  - the abstract "No candidate reached the confidence the system was calibrated to require
    before claiming a cause, so NetCoop abstains instead of guessing."
  - a "WHAT WOULD SETTLE IT" section reading "more complete or less noisy telemetry for the
    affected period"
- **Narration:** "Here the fault is real but faint. No explanation reaches the calibrated bar,
  so NetCoop says so, and tells the operator what data would settle it. That's why ninety-eight
  point six percent of its claims are correct."

**Scene 7 — Conflict resolution: the courtroom (2:55–3:30)**
- **Screen, the resolved case.** The cursor clicks "Interface fault", then Diagnose. In Fig. 1,
  crimson points appear on the prosecutor and judge lanes. Scroll to "COURTROOM TIE-BREAK":
  - "Interface fault at hostel-acc-01 → hostel-acc-01-ap-01 *versus* Hardware failure at
    hostel-acc-01-ap-01"
  - numbered rulings: "prosecutor for interface_fault … +2.00 (confirmed +2.00)", "defense for
    hardware_failure … +0.00 (no discriminating evidence)"
  - a green "Resolved after 1 round"
- **Screen, the deferred case.** Then click "Hardware failure", then Diagnose. The same section
  shows an amber "Deferred". The ruling reads "evidence favours hardware_failure … but the
  calibrated model gives it 0.00 < 0.98 (never trained on it): deferred".
- **Narration:** "When two explanations compete, a courtroom opens. A prosecutor and a defense
  argue only from evidence that tells the two apart, and a judge rules. Here the interface fault
  is confirmed. In this second case the true cause is a hardware failure, a fault type the model
  never saw in training. The evidence leans toward it, but the calibrated model can't vouch for
  it, so the judge defers instead of guessing. Across a hundred and twenty such runs: zero wrong
  claims."

**Scene 8 — Traceability in the terminal (3:30–3:55)**
- **Screen:** the terminal. Type
  `netcoop run data/samples/link_congestion__s500__i1.0__n0.0__m0.0 -v`. Lines scroll fast, one
  per board message, in the form "r1 #739 HYPOTHESIS performance -> board hypothesis-…". It ends
  with "status: diagnosed root cause: link_congestion at department-dist-01--department-acc-02 …
  confidence: 1.00". Then type `netcoop replay runs/inc-9ce9df1bb813`; it prints "replayed 887
  messages … (trace verified)".
- **Narration:** "Everything you saw is also a command-line tool. Every message is written to a
  trace file. Replay rebuilds the board from that trace and verifies it byte for byte: the same
  input and configuration always give the same result."

**Scene 9 — Evaluation (3:55–4:20)**
- **Screen:** back in the browser, click the **Evaluation** tab. Show "Table 1", a clean journal
  table with black top and bottom rules:
  - root-cause accuracy 77.2%
  - precision of claims 98.6% (12 wrong of 846)
  - abstention rate 21.7%
  - macro-F1 0.860
  - root localisation 100.0%
  - courtroom invoked 227 runs

  Zoom on the precision row. Then click **Past runs**, which shows a table of the runs
  diagnosed in this video with their outcomes.
- **Narration:** "We evaluated on one thousand and eighty fresh runs never used for development.
  Seventy-seven percent accuracy, ninety-eight point six percent precision of claims, and every
  correct diagnosis located at the right device. Precision stays above ninety-five percent even
  with three stacked schema mutations."

**Scene 10 — Extensibility, quality and close (4:20–4:40)**
- **Screen:**
  - In the terminal, type `pytest -q`; dots stream and it ends with "246 passed".
  - Cut to the repository's GitHub Actions page, showing a green check on the "ci" workflow.
  - End on a 3-second navy title card: "NetCoop AI — every claim cites its proof." and the
    GitHub URL.
- **Narration:** "Agents and faults are defined as data. New ones plug in without code changes,
  and outside agents can join over MCP. Two hundred and forty-six tests and continuous
  integration keep it honest. NetCoop AI: every claim cites its proof. Thank you."

### Style rules to keep throughout

- It must always look like a real screen recording of real software, with crisp UI text and no
  morphing or warping. The visible text must be legible, and every number on screen must match
  the narration.
- Pacing is calm and confident. Hold each important screen state for at least 1.5 seconds
  before the cursor moves on.
- Use the zoom-ins only on what the narration is talking about, then return to full screen.
- Nothing appears that the product does not have: no fake charts, popups, logos or extra
  windows.
- Total length 4:30–4:50, with narration, subtitles and on-screen actions in sync.

---

## Production note (not part of the prompt)

Video generation models usually cannot render several minutes of legible, accurate UI text.
A judge watching closely may notice invented details.

The most reliable result is to **screen-record the real dashboard** following the timeline
above. Then generate the narration with Kokoro TTS, taking the narration lines verbatim; they
add up to about 550 words, about 3¾ minutes of speech at Kokoro's normal speed. With pauses
and on-screen holds, that fills the 4½-minute timeline. Add the
same lines as subtitles in any video editor. Everything shown in the timeline exists and works
today:
- `netcoop serve` for the dashboard
- `netcoop translate`, `netcoop run -v` and `netcoop replay` in the terminal
