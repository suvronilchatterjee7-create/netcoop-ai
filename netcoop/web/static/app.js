/* NetCoop dashboard. Plain JS over the JSON API in netcoop/web/server.py. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) n.append(k.nodeType ? k : String(k));
  return n;
};
const SVG = "http://www.w3.org/2000/svg";
const sv = (tag, attrs = {}) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

const AGENTS = ["translator", "performance", "infrastructure", "wireless_service", "connectivity",
  "correlator", "prosecutor", "defense", "judge", "reporter", "orchestrator"];
const CORE_LANES = ["translator", "performance", "infrastructure", "wireless_service", "connectivity", "correlator", "reporter"];
const AGENT_LABEL = { wireless_service: "wireless / service" };
const NAMES = {
  link_congestion: "Link congestion", interface_fault: "Interface fault", weak_wifi: "Weak Wi-Fi",
  weak_wifi_signal: "Weak Wi-Fi signal", dns_dhcp_failure: "DNS / DHCP failure",
  dns_service_failure: "DNS service failure", dhcp_service_failure: "DHCP service failure",
  hardware_failure: "Hardware failure", device_overload: "Device overload", normal: "Healthy network",
  interop_failure: "Legacy-dialect export",
};
const STATUS = {
  diagnosed: "Diagnosed", insufficient_evidence: "Not enough evidence",
  no_fault_detected: "No fault detected", running: "Diagnosing", failed: "Run failed",
};
const TYPE_WORD = {
  TOPOLOGY: "topology", HYPOTHESIS: "hypothesis", REQUEST: "request", RESPONSE: "response",
  SUPPORT: "support", CONTRADICT: "contradiction", VERDICT: "verdict", REPORT: "report",
  ERROR: "error", ACK: "acknowledgement", CLUE: "clue", OBSERVATION: "observation",
};

const num = (v) => (Math.abs(v) >= 100 ? Math.round(v).toString() : Number(v.toPrecision(3)).toString());
const pretty = (t) => NAMES[t] || (t ? t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "");
const ent = (id) => (id || "").replace("--", " → ");
const agentName = (a) => AGENT_LABEL[a] || a;
const agentColor = (a) => `var(--a-${AGENTS.includes(a) ? a : "orchestrator"})`;
const dialect = (d) => (!d ? "" : /legacy/i.test(d) ? "legacy CSV" : "native JSONL");

const state = {
  config: { replay_step_ms: 140 },
  inputs: [],
  selected: null,       // input object
  running: false,
  source: null,         // EventSource
  chain: [], queue: [], counts: {}, timer: null, doneIncident: null,
  detail: null,
  numbers: new Map(),   // msg_id -> citation number
  byNumber: new Map(),  // number -> event
};

/* ------------------------------------------------------------------ api */
async function api(path) {
  try {
    const r = await fetch(path);
    $("#offline").hidden = true;
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch (e) {
    if (e instanceof TypeError) $("#offline").hidden = false;
    throw e;
  }
}

/* ------------------------------------------------------------------ tabs */
function showTab(name) {
  for (const t of ["diagnose", "runs", "evaluation"]) {
    const tab = $(`#tab-${t}`), view = $(`#view-${t}`);
    const on = t === name;
    tab.setAttribute("aria-selected", on);
    tab.tabIndex = on ? 0 : -1;
    view.hidden = !on;
  }
  if (name === "runs") loadRuns();
  if (name === "evaluation") loadEvaluation();
}
$(".tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[role=tab]");
  if (b) showTab(b.id.slice(4));
});
$(".tabs").addEventListener("keydown", (e) => {
  if (!["ArrowRight", "ArrowLeft"].includes(e.key)) return;
  const tabs = [...document.querySelectorAll("[role=tab]")];
  const i = tabs.indexOf(document.activeElement);
  const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
  next.focus(); showTab(next.id.slice(4));
});

/* ------------------------------------------------------------------ rail */
// Run folder names break only after "__", never inside a number.
function folder(name) {
  const out = [];
  (name || "").split("__").forEach((part, i, all) => {
    out.push(part + (i < all.length - 1 ? "__" : ""));
    if (i < all.length - 1) out.push(document.createElement("wbr"));
  });
  return el("span", { class: "folder" }, ...out);
}

function inputButton(inp, compact) {
  const title = compact ? folder(inp.name) : pretty(inp.truth);
  const bits = [];
  if (inp.intensity != null && inp.truth !== "normal") bits.push(`intensity ${inp.intensity}`);
  if (inp.noise) bits.push(`noise ${inp.noise}`);
  if (inp.missing_rate) bits.push(`${Math.round(inp.missing_rate * 100)}% missing`);
  bits.push(dialect(inp.dialect));
  return el("li", {}, el("button", {
    type: "button", "aria-pressed": state.selected && state.selected.id === inp.id ? "true" : "false",
    "data-id": inp.id, onclick: () => select(inp),
  }, el("span", { class: "t" }, title), el("span", { class: "d", text: compact ? pretty(inp.truth) : bits.filter(Boolean).join(" · ") })));
}

function renderRail() {
  const samples = state.inputs.find((c) => c.collection.endsWith("samples"));
  const list = $("#samples");
  list.replaceChildren(...(samples ? samples.runs.map((r) => inputButton(r, false)) : [el("li", { class: "more-note", text: "No samples found in data/samples." })]));
  const others = state.inputs.filter((c) => c !== samples);
  const sel = $("#collection");
  if (!sel.options.length) {
    if (!others.length) sel.append(el("option", { value: "", text: "None generated yet" }));
    for (const c of others) sel.append(el("option", { value: c.collection, text: `${c.collection} (${c.total})` }));
  }
  renderMore();
}

function renderMore() {
  const coll = state.inputs.find((c) => c.collection === $("#collection").value);
  const box = $("#more");
  if (!coll) { box.replaceChildren(el("li", { class: "more-note", text: "Run netcoop generate or netcoop eval to add more run folders." })); return; }
  const q = $("#filter").value.trim().toLowerCase();
  const hits = coll.runs.filter((r) => !q || r.name.toLowerCase().includes(q)).slice(0, 12);
  const kids = hits.map((r) => inputButton(r, true));
  if (q && !hits.some((r) => r.name.toLowerCase() === q)) {
    kids.push(el("li", {}, el("button", { type: "button", onclick: () => select({ id: `${coll.collection}/${$("#filter").value.trim()}`, name: $("#filter").value.trim() }) },
      el("span", { class: "t", text: `Diagnose "${$("#filter").value.trim()}"` }),
      el("span", { class: "d", text: `searches all ${coll.total} folders in ${coll.collection}` }))));
  }
  if (!kids.length) kids.push(el("li", { class: "more-note", text: "No folder matches that name." }));
  box.replaceChildren(...kids);
}
$("#collection").addEventListener("change", renderMore);
$("#filter").addEventListener("input", renderMore);

function markSelected() {
  for (const b of document.querySelectorAll(".inputs button[data-id]")) {
    b.setAttribute("aria-pressed", state.selected && b.dataset.id === state.selected.id ? "true" : "false");
  }
}

function select(inp) {
  if (state.running) return;
  state.selected = inp;
  state.detail = null;
  markSelected();
  history.replaceState(null, "", location.pathname);
  renderReady();
  renderFigure([], {});
  setMsg(null);
}

/* ------------------------------------------------------------------ report: idle / ready / running */
function diagnoseButton(label = "Diagnose", ghost = false) {
  return el("button", { type: "button", class: ghost ? "btn ghost" : "btn", onclick: diagnose, disabled: state.running },
    icon("i-play"), label);
}
function icon(id) {
  const s = sv("svg", { class: "ic", "aria-hidden": "true" });
  const use = sv("use", { href: `#${id}` });
  s.append(use);
  return s;
}
function fixIcons() { /* icons are built in the SVG namespace by icon() */ }

function renderEmpty() {
  const r = $("#report");
  r.replaceChildren(el("div", { class: "empty" },
    el("h1", { class: "headline", text: "Pick a run, then watch the agents diagnose it" }),
    el("p", { text: "Each run folder holds a few hours of telemetry from a campus network. Specialist agents read it, post what they find to a shared case board, argue when explanations compete, and publish one report." }),
    el("ol", { class: "steps" },
      el("li", { text: "Choose a sample on the left. Each is labelled with the fault the generator injected." }),
      el("li", { text: "Press Diagnose. Fig. 1 fills in as the agents post messages." }),
      el("li", { text: "Read the report. Every red number cites the message that proves the claim; hover it to find that message in Fig. 1." }))));
}

function inputHeader(headline) {
  return el("div", { class: "r-top" }, headline,
    state.running ? null : diagnoseButton(state.detail ? "Diagnose again" : "Diagnose", !!state.detail));
}
// The run folder, shown in the line under the headline.
const inputName = () => (state.selected && state.selected.name ? el("span", { class: "r-input" }, folder(state.selected.name)) : null);

function renderReady() {
  const inp = state.selected;
  const r = $("#report");
  r.replaceChildren(
    inputHeader(el("h1", { class: "headline", text: inp.truth ? `${pretty(inp.truth)}, ready to diagnose` : "Ready to diagnose" })),
    el("p", { class: "meta" }, inputName(),
      inp.truth ? el("span", { class: "truth" }, "Generator label ", el("b", { text: pretty(inp.truth) }), " (the agents never see it)") : null,
      inp.dialect ? el("span", { text: dialect(inp.dialect) }) : null),
    el("p", { class: "prose", text: "Press Diagnose to run the full pipeline on this folder: the Translator reads the files, the specialists analyse them over several rounds, and the correlator decides. It takes a few seconds." }));
  fixIcons(r);
}

function renderRunning(latest) {
  if (!state.running) return; // a repaint queued during the run must not cover the finished report
  const r = $("#report");
  const c = state.counts;
  const total = Object.values(c).reduce((a, b) => a + b, 0);
  r.replaceChildren(
    inputHeader(el("h1", { class: "headline", text: "Diagnosing…" })),
    el("p", { class: "meta" }, el("span", { class: "status running", text: STATUS.running }),
      el("span", { text: `${total} messages so far` }),
      latest ? el("span", { text: `round ${latest.round}` }) : null, inputName()),
    el("div", { class: "live" },
      el("p", { class: "now", text: latest ? `${agentName(latest.sender)}: ${latest.summary}` : "The Translator is reading the input files…" })));
}

function renderFailed(message) {
  const r = $("#report");
  r.replaceChildren(
    inputHeader(el("h1", { class: "headline", text: "The run did not finish" })),
    el("p", { class: "meta" }, el("span", { class: "status failed", text: STATUS.failed }), inputName()),
    el("div", { class: "err" }, el("span", { text: `${message}. Nothing was diagnosed. Try again; if it fails again, run the same folder with netcoop run in a terminal to see the full error.` })));
  fixIcons(r);
}

/* ------------------------------------------------------------------ diagnose (live) */
function diagnose() {
  if (state.running || !state.selected) return;
  state.running = true; state.detail = null;
  state.chain = []; state.queue = []; state.counts = {}; state.doneIncident = null;
  state.numbers = new Map(); state.byNumber = new Map();
  for (const b of document.querySelectorAll(".inputs button")) b.disabled = true;
  renderRunning(null); renderFigure([], {}); renderCounts(); setMsg(null);

  const src = new EventSource(`/api/diagnose?input=${encodeURIComponent(state.selected.id)}`);
  state.source = src;
  let latest = null;
  src.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    state.counts[m.type] = (state.counts[m.type] || 0) + 1;
    if (["OBSERVATION", "CLUE", "CAPABILITY"].includes(m.type)) {
      if (m.type !== "OBSERVATION") latest = m;
      throttle(() => { renderCounts(); renderRunning(latest); });
    } else {
      state.queue.push(m);
      pump();
    }
  });
  src.addEventListener("done", (e) => { state.doneIncident = JSON.parse(e.data).incident; src.close(); pump(); });
  src.addEventListener("failed", (e) => { src.close(); finishFailed(JSON.parse(e.data).error); });
  src.onerror = () => { if (state.running && !state.doneIncident) { src.close(); finishFailed("Lost the connection to the server"); } };
}

let throttled = false;
function throttle(fn) {
  if (throttled) return;
  throttled = true;
  requestAnimationFrame(() => { throttled = false; fn(); });
}

function pump() {
  if (state.timer) return;
  const step = () => {
    const m = state.queue.shift();
    if (m) {
      state.chain.push(m);
      number(m);
      renderFigure(state.chain, { enter: m.msg_id });
      renderCounts();
      renderRunning(m);
      state.timer = setTimeout(step, state.config.replay_step_ms);
    } else {
      state.timer = null;
      if (state.doneIncident) openRun(state.doneIncident, { live: true });
    }
  };
  step();
}

function finishFailed(message) {
  state.running = false;
  clearTimeout(state.timer); state.timer = null;
  for (const b of document.querySelectorAll(".inputs button")) b.disabled = false;
  renderFailed(message);
}

/* ------------------------------------------------------------------ numbering */
function number(m) {
  if (state.numbers.has(m.msg_id)) return state.numbers.get(m.msg_id);
  const n = state.numbers.size + 1;
  state.numbers.set(m.msg_id, n);
  state.byNumber.set(n, m);
  return n;
}
function cite(msgId) {
  const n = state.numbers.get(msgId);
  if (!n) return null;
  return el("button", { type: "button", class: "cite", "data-n": n, "aria-label": `Citation ${n}: show the message`, text: String(n) });
}
function cites(ids) {
  const out = [];
  for (const id of ids) { const c = cite(id); if (c) out.push(c); }
  return out;
}

/* ------------------------------------------------------------------ open a finished run */
async function openRun(incident, { live = false } = {}) {
  let d;
  try { d = await api(`/api/runs/${encodeURIComponent(incident)}`); }
  catch (e) { finishFailed("Could not load the finished report"); return; }
  state.running = false;
  for (const b of document.querySelectorAll(".inputs button")) b.disabled = false;
  state.detail = d;
  state.numbers = new Map(); state.byNumber = new Map();
  for (const m of d.chain) number(m);
  const prov = (d.report.x_netcoop || {}).evidence_provenance || [];
  for (const p of prov) if (d.cited[p.clue_id]) number(d.cited[p.clue_id]);
  state.counts = {};
  for (const [type, by] of Object.entries(d.counts)) state.counts[type] = Object.values(by).reduce((a, b) => a + b, 0);
  for (const m of d.chain) state.counts[m.type] = (state.counts[m.type] || 0) + 1;
  if (!state.selected) {
    // The manifest lists input files; the run folder is the parent of the first one.
    const parts = ((d.manifest.inputs || [])[0] || "").split(/[\\/]/);
    const name = parts.length > 1 && /\.\w+$/.test(parts[parts.length - 1]) ? parts[parts.length - 2] : parts.pop();
    state.selected = { id: null, name };
    for (const c of state.inputs) for (const r of c.runs) if (r.name === name) state.selected = r;
    markSelected();
  }
  history.replaceState(null, "", `#run=${incident}`);
  renderFigure(d.chain, {});
  renderCounts();
  renderReport(d);
  setMsg(null);
  if (live) $("#report").focus({ preventScroll: true });
}

/* ------------------------------------------------------------------ report */
function renderReport(d) {
  const r = d.report, x = r.x_netcoop || {}, chain = d.chain;
  const verdict = chain.find((m) => m.type === "VERDICT" && m.sender === "judge") || chain.find((m) => m.type === "VERDICT");
  const hyps = chain.filter((m) => m.type === "HYPOTHESIS");
  const stances = chain.filter((m) => (m.type === "SUPPORT" || m.type === "CONTRADICT") && !["prosecutor", "defense"].includes(m.sender));
  const total = Object.values(d.manifest.message_counts || {}).reduce((a, b) => a + b, 0);

  let headline, abstract;
  const [causeAt] = splitCause(r.suspected_root_cause);
  const provs = x.evidence_provenance || [];
  if (r.status === "diagnosed") {
    headline = `${pretty(causeAt.type)} on ${ent(causeAt.entity)}`;
    const sup = stances.filter((m) => m.type === "SUPPORT"), con = stances.filter((m) => m.type === "CONTRADICT");
    // Lead with the measurements that prove the claim, each cited to its clue.
    const findings = provs.slice(0, 3).map((p) => [finding(r.supporting_evidence[p.evidence_index]), cite(p.clue_id)]);
    abstract = el("p", { class: "abstract" },
      findings.length ? ["The agents found ", ...findings.flatMap((f, i) => [i ? (i === findings.length - 1 ? " and " : ", ") : "", ...f]), ". "] : null,
      hyps.length ? ["Proposed by ", ...joinAgents(hyps), ". "] : null,
      sup.length ? ["Supported by ", ...joinAgents(sup), ". "] : null,
      con.length ? ["Contradicted by ", ...joinAgents(con), ". "] : null,
      verdict ? ["The verdict", cite(verdict.msg_id), ` gives a calibrated confidence of ${r.confidence.toFixed(2)}.`] : null);
  } else if (r.status === "insufficient_evidence") {
    headline = "Not enough evidence to name a cause";
    const best = (r.suspected_root_cause.split("; best explanation")[1] || "").replace(/^s?:\s*/, "");
    abstract = el("p", { class: "abstract" },
      "No candidate reached the confidence the system was calibrated to require before claiming a cause, so NetCoop abstains instead of guessing. ",
      best ? `The best explanations were ${readable(best)}. ` : null,
      verdict ? ["See the verdict", cite(verdict.msg_id), "."] : null);
  } else {
    headline = "No fault detected";
    abstract = el("p", { class: "abstract" }, "No significant deviation matches any fault the agents could assess on this data. ",
      verdict ? ["See the verdict", cite(verdict.msg_id), "."] : null);
  }

  const inp = state.selected || {};
  const kids = [
    inputHeader(el("h1", { class: "headline", text: headline })),
    el("p", { class: "meta" },
      el("span", { class: `status ${r.status}`, text: STATUS[r.status] || r.status }),
      el("span", { text: r.status === "insufficient_evidence" ? "No cause asserted" : `Confidence ${r.confidence.toFixed(2)} (${x.confidence_category || "-"})` }),
      r.affected_devices.length ? el("span", { text: `${r.affected_devices.length} affected` }) : null,
      el("span", { text: `${d.manifest.rounds} rounds · ${total} messages` }),
      inp.truth ? el("span", { class: "truth" }, "Generator label ", el("b", { text: pretty(inp.truth) })) : null,
      inputName(), el("span", { class: "truth", text: d.incident })),
    abstract,
  ];

  const prov = new Map((x.evidence_provenance || []).map((p) => [p.evidence_index, p]));
  if (r.supporting_evidence.length) {
    kids.push(el("h2", { text: r.status === "diagnosed" ? "Evidence" : "Evidence for the best explanations" }),
      el("ol", { class: "evidence" }, r.supporting_evidence.map((e, i) => {
        const p = prov.get(i);
        // The config key is shown on the source line, so drop the bracketed copy.
        const text = p ? e.interpretation.replace(/\s*\[[^\]]+\]\s*$/, "") : e.interpretation;
        return el("li", {}, text, p ? cite(p.clue_id) : null,
          p ? el("span", { class: "src", text: `${agentName(p.agent)} · compared with ${p.config_key} · ${p.observation_ids.length} observation${p.observation_ids.length === 1 ? "" : "s"}` }) : null);
      })));
  }
  if (r.recommended_actions.length) {
    kids.push(el("h2", { text: "Recommended actions" }),
      el("ol", { class: "actions" }, r.recommended_actions.map((a) => el("li", { text: a }))),
      el("p", { class: "cond", text: "For human review. NetCoop never executes a remediation; its effects are only simulated." }));
  }
  if (x.missing_evidence && x.missing_evidence.length) {
    kids.push(el("h2", { text: "What would settle it" }), el("ul", { class: "actions" }, x.missing_evidence.map((m) => el("li", { text: m }))));
  }
  if (r.affected_devices.length) {
    kids.push(el("h2", { text: "Affected devices" }),
      el("ul", { class: "devices" }, r.affected_devices.map((a, i) => el("li", { class: i === 0 && r.status === "diagnosed" ? "root" : null, text: ent(a), title: i === 0 ? "root cause location" : null }))));
  }
  if (x.courtroom && x.courtroom.invoked) kids.push(...courtroom(x.courtroom));
  if ((x.alternatives_scored || []).length) {
    kids.push(el("h2", { text: "Alternatives considered" }),
      el("table", { class: "alts" }, el("thead", {}, el("tr", {}, el("th", { text: "Cause" }), el("th", { class: "n", text: "Calibrated confidence" }))),
        el("tbody", {}, x.alternatives_scored.map((a) => el("tr", {}, el("td", { text: readable(a.cause) }), el("td", { class: "n", text: a.confidence.toFixed(2) }))))));
  }
  const dq = x.data_quality;
  kids.push(el("h2", { text: "Data quality and limitations" }),
    el("p", { class: "prose" }, dq ? `Input quality ${dq.overall.toFixed(2)} of 1.00` : "No quality summary", dq && Object.keys(dq.issues).length ? ` (issues: ${Object.entries(dq.issues).map(([k, v]) => `${k} ×${v}`).join(", ")}).` : ".",
      r.limitations.length ? null : " No limitations recorded."),
    r.limitations.length ? el("ul", { class: "actions" }, r.limitations.map((l) => el("li", { text: l }))) : null);
  if ((x.score_breakdown || []).length) {
    kids.push(el("details", { class: "score" }, el("summary", { text: "Score breakdown (itemised log-odds)" }),
      el("table", { class: "alts" }, el("thead", {}, el("tr", {}, el("th", { text: "Term" }), el("th", { text: "Status" }), el("th", { class: "n", text: "Contribution" }))),
        el("tbody", {}, x.score_breakdown.map((s) => el("tr", {}, el("td", { text: s.term }), el("td", { text: s.status }), el("td", { class: "n", text: (s.contribution >= 0 ? "+" : "") + s.contribution.toFixed(3) })))))));
  }
  kids.push(el("h2", { text: "References" }), references(), el("h2", { text: "Files" }),
    el("p", { class: "files" }, el("span", { text: `Report: ${d.files.report_md}` }), el("span", { text: `Trace: ${d.files.trace}` })));

  const box = $("#report");
  box.replaceChildren(...kids.flat().filter(Boolean));
  fixIcons(box);
}

// The first clause of an evidence interpretation, as a phrase for the abstract:
// "packet_loss on L: recent median 2.44 percent is above the normal-operation baseline of
// 0.02 percent by 50 robust …" -> "packet loss on L at 2.44 percent against a normal 0.02 percent".
function finding(e) {
  return e.interpretation
    .split(/;|, abnormal in/)[0]
    .replace(/\s*\[[^\]]+\]\s*$/, "")
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/: recent median /, " at ")
    .replace(/ is (above|below) the normal-operation baseline of /, " against a normal ")
    .replace(/ is (above|below) the cited threshold of /, " against a threshold of ")
    .replace(/ by [\d.]+ (robust standard deviations|x the threshold).*$/, "")
    .replace(/ (is|was) (rising|falling|in an abnormal state)/, " $2")
    .replace(/ stayed normal:.*$/, " normal")
    .replace(e.metric, e.metric.replace(/_/g, " "))
    .replace(/(\S+)--(\S+)/g, "$1 → $2")
    .trim();
}

function splitCause(text) {
  const m = /^([a-z_]+) at ([^:]+):\s*(.*)$/.exec(text || "");
  return m ? [{ type: m[1], entity: m[2] }, m[3]] : [{ type: "", entity: "" }, text || ""];
}
function joinAgents(msgs) {
  // One name per agent with all its citations; each name stays on one line with its punctuation.
  const by = new Map();
  for (const m of msgs) by.set(m.sender, [...(by.get(m.sender) || []), m.msg_id]);
  const names = [...by.keys()];
  return names.map((a, i) => {
    const sep = i === names.length - 1 ? "" : i === names.length - 2 ? " and" : ",";
    const marks = by.get(a).flatMap((id, j) => (j ? [el("sup", { class: "cite-sep", text: "," }), cite(id)] : [cite(id)]));
    return [el("span", { class: "nb" }, agentName(a), ...marks, sep), i === names.length - 1 ? "" : " "];
  }).flat();
}
// "interface_fault@a--b" anywhere in a ruling -> "Interface fault at a → b"
const readable = (s) => (s || "").replace(/\b([a-z]+(?:_[a-z]+)+)(@| at )/g, (_, t) => `${pretty(t)} at `).replace(/--/g, " → ");

function courtroom(c) {
  const [a, b] = c.contenders;
  const parts = c.summary.split(" | ");
  const transcript = cites(c.transcript_msg_ids);
  return [el("h2", { text: "Courtroom tie-break" }), el("div", { class: "court" },
    el("p", { class: "vs" }, readable(a), el("i", { text: "versus" }), readable(b)),
    el("ol", {}, parts.map((p) => el("li", { text: readable(p) }))),
    el("p", {}, el("span", { class: `outcome ${c.outcome}`, text: c.outcome === "resolved" ? "Resolved" : "Deferred" }),
      ` after ${c.rounds} round${c.rounds === 1 ? "" : "s"}. Transcript`, ...transcript, "."))];
}
function references() {
  return el("ol", { class: "refs" }, [...state.byNumber.entries()].map(([n, m]) =>
    el("li", { id: `ref-${n}`, "data-n": n }, el("span", { class: "no", text: n }),
      el("span", {}, el("span", { class: "ty", text: `${TYPE_WORD[m.type] || m.type} ` }), `from ${agentName(m.sender)}, round ${m.round}: ${m.summary} `,
        el("span", { class: "id", text: m.msg_id })))));
}

/* ------------------------------------------------------------------ Fig. 1 */
function renderFigure(chain, { enter } = {}) {
  const box = $("#fig");
  if (!chain.length) {
    box.replaceChildren(el("p", { class: "fig-empty", text: state.selected ? "Press Diagnose to watch the agents work." : "Pick a run on the left." }));
    $("#figlegend") && $("#figlegend").remove();
    return;
  }
  const senders = new Set(chain.map((m) => m.sender));
  const lanes = AGENTS.filter((a) => senders.has(a) || (state.running && CORE_LANES.includes(a)));
  for (const s of senders) if (!lanes.includes(s)) lanes.push(s);
  const maxRound = Math.max(...chain.map((m) => m.round), state.running ? 3 : 0);
  // Each round's column is as wide as its busiest lane needs; quiet rounds stay narrow.
  const slots = new Map(); // `${round}|${lane}` -> count
  const widest = new Array(maxRound + 1).fill(0);
  for (const m of chain) {
    const k = `${m.round}|${m.sender}`;
    slots.set(k, (slots.get(k) || 0) + 1);
    widest[m.round] = Math.max(widest[m.round], slots.get(k));
  }
  // Drawn at 1:1. Busy lanes wrap onto extra rows before the figure would overflow its column;
  // only a figure that still cannot fit is scaled down (CSS max-width).
  // Each lane is a band: its agent name on top, its points below. Names above the band (not in
  // a left column) leave the full width for rounds.
  const LEFT = 4, TOP = 22, NAME = 18, PITCH = 30, R = 12, ROW = 28;
  const avail = Math.max(300, box.clientWidth - 4);
  const colFor = (n, cap) => (n ? Math.min(n, cap) * PITCH + 14 : 26);
  const widthFor = (cap) => LEFT + 8 + widest.reduce((a, n) => a + colFor(n, cap), 0);
  let cap = Math.max(1, ...widest);
  while (cap > 1 && widthFor(cap) > avail) cap--;
  const rowsMax = Math.max(1, ...widest.map((n) => Math.ceil(n / cap)));
  const LANE = NAME + rowsMax * ROW + 8;
  const colW = widest.map((n) => colFor(n, cap));
  const colX = colW.map((_, i) => LEFT + colW.slice(0, i).reduce((a, b) => a + b, 0));
  const W = LEFT + colW.reduce((a, b) => a + b, 0) + 8, H = TOP + lanes.length * LANE + 4;
  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": "Fig. 1, agent message exchange" });

  for (let rnd = 0; rnd <= maxRound; rnd++) {
    const x0 = colX[rnd];
    if (rnd) svg.append(sv("line", { class: "round-rule", x1: x0, x2: x0, y1: TOP - 4, y2: H }));
    const t = sv("text", { class: "round-label", x: x0 + colW[rnd] / 2, y: 13, "text-anchor": "middle" });
    t.textContent = rnd ? `${rnd}` : "round 0"; svg.append(t);
  }
  lanes.forEach((a, i) => {
    const y0 = TOP + i * LANE;
    const g = sv("g", { "data-lane": a });
    g.append(sv("line", { class: "lane-rule", x1: 0, x2: W, y1: y0, y2: y0 }));
    const t = sv("text", { class: "lane-label", x: LEFT, y: y0 + 14 }); t.textContent = agentName(a); g.append(t);
    svg.append(g);
  });

  const pos = new Map(), seen = new Map();
  for (const m of chain) {
    const k = `${m.round}|${m.sender}`;
    const slot = seen.get(k) || 0; seen.set(k, slot + 1);
    const rows = Math.ceil(slots.get(k) / cap), row = Math.floor(slot / cap);
    const mid = TOP + lanes.indexOf(m.sender) * LANE + NAME + (LANE - NAME) / 2 - 2;
    const dy = (row - (rows - 1) / 2) * ROW;
    const inRow = Math.min(cap, slots.get(k) - row * cap); // centre each row in its column
    const x0 = colX[m.round] + (colW[m.round] - inRow * PITCH) / 2 + PITCH / 2;
    pos.set(m.msg_id, { x: x0 + (slot % cap) * PITCH, y: mid + dy });
  }
  const edges = sv("g");
  for (const m of chain) {
    const a = pos.get(m.causation_id), b = pos.get(m.msg_id);
    if (!a || !b) continue;
    const mx = (a.x + b.x) / 2;
    edges.append(sv("path", { class: "edge", "data-from": state.numbers.get(m.causation_id), "data-to": state.numbers.get(m.msg_id),
      d: `M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}` }));
  }
  svg.append(edges);
  for (const m of chain) {
    const p = pos.get(m.msg_id), n = state.numbers.get(m.msg_id);
    const g = sv("g", { class: `pt${m.msg_id === enter ? " enter" : ""}`, tabindex: 0, role: "button", "data-n": n,
      "aria-label": `${n}: ${TYPE_WORD[m.type] || m.type} from ${agentName(m.sender)}, round ${m.round}. ${m.summary}` });
    g.append(sv("circle", { class: "halo", cx: p.x, cy: p.y, r: R + 3 }));
    g.append(sv("circle", { cx: p.x, cy: p.y, r: R, fill: agentColor(m.sender) }));
    const t = sv("text", { x: p.x, y: p.y + 4, "text-anchor": "middle" }); t.textContent = n; g.append(t);
    svg.append(g);
  }
  box.replaceChildren(svg);
}

function renderCounts() {
  const c = state.counts;
  const items = [["OBSERVATION", "observations"], ["CLUE", "clues"], ["CAPABILITY", "capability cards"]];
  $("#counts").replaceChildren(...items.map(([k, label]) => el("span", {}, el("b", { text: (c[k] || 0).toLocaleString() }), ` ${label}`)),
    el("span", { class: "truth", text: "counted, not drawn" }));
}

/* ------------------------------------------------------------------ highlight: the signature */
function setMsg(n) {
  const box = $("#msg");
  const m = n && state.byNumber.get(n);
  if (!m) {
    box.replaceChildren(el("p", { class: "hint", text: state.byNumber.size ? "Hover or focus a numbered point or a red citation to read the message." : "" }));
    return;
  }
  const cause = state.numbers.get(m.causation_id);
  box.replaceChildren(
    el("div", { class: "h" }, el("span", { class: "no", text: n }), el("span", { class: "ty", text: TYPE_WORD[m.type] || m.type }),
      el("span", { class: "who", text: `${agentName(m.sender)} → ${m.recipient}, round ${m.round}` })),
    el("p", { text: m.summary }),
    el("div", { class: "id" }, m.msg_id, cause ? ` · caused by ${cause}` : ""));
}

function highlight(n) {
  for (const x of document.querySelectorAll(".lit")) x.classList.remove("lit");
  for (const x of document.querySelectorAll(".lane-hit")) x.classList.remove("lane-hit");
  if (!n) return;
  for (const x of document.querySelectorAll(`[data-n="${n}"]`)) x.classList.add("lit");
  for (const x of document.querySelectorAll(`.edge[data-from="${n}"], .edge[data-to="${n}"]`)) x.classList.add("lit");
  const m = state.byNumber.get(n);
  if (m && !document.querySelector(`.pt[data-n="${n}"]`)) {
    const lane = document.querySelector(`[data-lane="${m.sender}"]`);
    if (lane) lane.classList.add("lane-hit");
  }
  setMsg(n);
}

document.addEventListener("pointerover", (e) => {
  const t = e.target.closest(".cite, .pt");
  if (t) highlight(Number(t.dataset.n));
});
document.addEventListener("pointerout", (e) => {
  const t = e.target.closest(".cite, .pt");
  if (t && !t.contains(e.relatedTarget)) highlight(null);
});
document.addEventListener("focusin", (e) => {
  const t = e.target.closest(".cite, .pt");
  if (t) highlight(Number(t.dataset.n));
});
document.addEventListener("click", (e) => {
  const c = e.target.closest(".cite");
  if (c) {
    const ref = document.getElementById(`ref-${c.dataset.n}`);
    if (ref) ref.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const p = e.target.closest(".pt");
  if (p) jumpToCitation(p.dataset.n);
});
document.addEventListener("keydown", (e) => {
  const p = e.target.closest && e.target.closest(".pt");
  if (p && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); jumpToCitation(p.dataset.n); }
});
function jumpToCitation(n) {
  const target = document.querySelector(`#report .cite[data-n="${n}"]`) || document.getElementById(`ref-${n}`);
  if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
  highlight(Number(n));
}

/* ------------------------------------------------------------------ other views */
async function loadRuns() {
  const box = $("#runs");
  let runs;
  try { runs = await api("/api/runs"); } catch { box.replaceChildren(el("p", { class: "note", text: "Could not load past runs." })); return; }
  if (!runs.length) {
    box.replaceChildren(el("p", { class: "note", text: "No dashboard runs yet. Diagnose a sample and it will be listed here." }));
    return;
  }
  box.replaceChildren(el("table", { class: "table" },
    el("caption", {}, el("b", { text: "Table 1 " }), "Diagnoses run from this dashboard, newest first. Select a row to open its report."),
    el("thead", {}, el("tr", {}, ["Input", "Outcome", "Root cause", "Confidence", "Incident", "When"].map((h) => el("th", { text: h })))),
    el("tbody", {}, runs.map((r) => el("tr", { class: "click", tabindex: 0,
      onclick: () => openPast(r.incident), onkeydown: (e) => { if (e.key === "Enter") openPast(r.incident); } },
      el("td", { class: "mono", text: r.input || "-" }),
      el("td", {}, el("span", { class: `status ${r.status}`, text: STATUS[r.status] || r.status })),
      el("td", { text: r.status === "diagnosed" ? (() => { const [c] = splitCause(r.root_cause); return `${pretty(c.type)} on ${ent(c.entity)}`; })() : "-" }),
      el("td", { class: "v", text: r.status === "insufficient_evidence" ? "-" : r.confidence.toFixed(2) }),
      el("td", { class: "mono", text: r.incident }),
      el("td", { text: new Date(r.mtime * 1000).toLocaleString() }))))));
}
function openPast(incident) {
  state.selected = null;
  showTab("diagnose");
  markSelected();
  openRun(incident);
}

async function loadEvaluation() {
  const box = $("#evaluation");
  let rows;
  try { rows = await api("/api/evaluation"); } catch { box.replaceChildren(el("p", { class: "note", text: "Could not load the evaluation." })); return; }
  if (!rows.length) { box.replaceChildren(el("p", { class: "note", text: "docs/EVALUATION.md is missing. Run netcoop eval to create it." })); return; }
  box.replaceChildren(el("table", { class: "table" },
    el("caption", {}, el("b", { text: "Table 1 " }), "Full system on the fresh test suite. Precision of claims counts diagnoses and 'no fault' claims; abstentions are neither right nor wrong."),
    el("thead", {}, el("tr", {}, el("th", { text: "Metric" }), el("th", { text: "Value" }))),
    el("tbody", {}, rows.map(([k, v]) => el("tr", {}, el("td", { text: k }), el("td", { class: "v", text: v }))))),
    el("p", { class: "note", text: "Slices by noise, missing data and intensity, the ablations and the robustness curves are in docs/EVALUATION.md." }));
}

/* ------------------------------------------------------------------ boot */
(async function boot() {
  renderEmpty(); renderFigure([], {}); renderCounts(); setMsg(null);
  try { state.config = await api("/api/config"); } catch { /* defaults */ }
  try { state.inputs = await api("/api/inputs"); } catch { state.inputs = []; }
  renderRail();
  const fromHash = () => {
    const m = /#run=([\w.-]+)/.exec(location.hash);
    if (m && !state.running && (!state.detail || state.detail.incident !== m[1])) openPast(m[1]);
  };
  window.addEventListener("hashchange", fromHash);
  fromHash();
})();
