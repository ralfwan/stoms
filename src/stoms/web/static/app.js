"use strict";

// Single-page homepage for one STOMS ledger. Routes live in the URL hash:
//   #/                       overview (all aggregations)
//   #/aggregations/<id>      one aggregation and its members
//   #/structures/<id>        structure viewer (viewer.js)

// file: true when serving one extxyz file (exports copy its frames verbatim).
const state = { aggregations: [], current: null, memberCache: new Map(), file: false };

// Members selected (for viewing and export), per aggregation, kept for this
// browser tab so the structure viewer can use and add to them.
function picksOf(aggregationId) {
  try { return new Set(JSON.parse(sessionStorage.getItem(`stoms.picks.${aggregationId}`) || "[]")); } catch { return new Set(); }
}
function savePicks(aggregationId, picks) {
  try { sessionStorage.setItem(`stoms.picks.${aggregationId}`, JSON.stringify([...picks])); } catch { /* storage unavailable */ }
}

// Fetch an export and offer it as a download; returns the file name.
async function downloadExport(path, init) {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error((await response.json()).error || response.statusText);
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "export.extxyz";
  const url = URL.createObjectURL(await response.blob());
  el("a", { href: url, download: filename }).click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  return filename;
}

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function setMain(...children) {
  $("#main").replaceChildren(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
}

async function api(path) {
  const response = await fetch(`api/${path}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function formatDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function copyButton(text) {
  const button = el("button", {
    class: "copy", title: "Copy to clipboard", type: "button",
    onclick: (event) => {
      event.stopPropagation();
      navigator.clipboard?.writeText(text);
      button.textContent = "copied";
      setTimeout(() => { button.textContent = "copy"; }, 900);
    },
  }, "copy");
  return button;
}

function idCell(id) {
  return el("span", {}, el("code", {}, id), copyButton(id));
}

function propertiesLabel(properties) {
  return properties.length
    ? properties.map((p) => `${p.name} [${p.unit ?? "-"}]`).join(", ")
    : "-";
}

// ---------------------------------------------------------------- JSON tree

function jsonTree(value, label, depth = 0) {
  if (value !== null && typeof value === "object") {
    const entries = Array.isArray(value)
      ? value.map((item, index) => [`[${index}]`, item])
      : Object.entries(value);
    const summary = el("summary", {}, el("span", { class: "key" }, label),
      entries.length ? el("span", { class: "muted" }, Array.isArray(value) ? ` [${entries.length}]` : ` {${entries.length}}`)
        : el("span", { class: "muted" }, Array.isArray(value) ? " []" : " {}"));
    return el("details", { open: depth < 1 }, summary,
      entries.map(([key, item]) => jsonTree(item, key, depth + 1)));
  }
  let cls = "lit";
  if (typeof value === "string") cls = "str";
  else if (typeof value === "number") cls = "numv";
  return el("div", { class: "leaf" }, el("span", { class: "key" }, `${label}: `),
    el("code", { class: cls }, JSON.stringify(value)));
}

function treeCard(title, value) {
  const tree = el("div", { class: "tree" }, jsonTree(value, title));
  const setAll = (open) => tree.querySelectorAll("details").forEach((d) => { d.open = open; });
  return el("div", { class: "card" },
    el("div", { class: "tree-actions" },
      el("button", { type: "button", onclick: () => setAll(true) }, "expand all"),
      el("button", { type: "button", onclick: () => setAll(false) }, "collapse all"),
      el("button", { type: "button", onclick: () => navigator.clipboard?.writeText(JSON.stringify(value, null, 2)) }, "copy JSON")),
    tree);
}

// ---------------------------------------------------------------- sidebar

function renderSidebar() {
  const filter = $("#agg-filter").value.trim().toLowerCase();
  const list = $("#agg-list");
  list.replaceChildren();
  const currentId = state.current?.id;
  for (const agg of state.aggregations) {
    const haystack = `${agg.name} ${agg.id} ${agg.description ?? ""}`.toLowerCase();
    if (filter && !haystack.includes(filter)) continue;
    list.append(el("li", {},
      el("a", { href: `#/aggregations/${encodeURIComponent(agg.id)}`, class: agg.id === currentId ? "active" : null },
        el("span", { class: "name" }, agg.name),
        el("span", { class: "meta muted" }, `${agg.member_count} members · ${formatDate(agg.created_at)}`))));
  }
  if (!list.children.length) list.append(el("li", { class: "muted" }, "No aggregations."));
}

// ---------------------------------------------------------------- overview

function renderOverview() {
  state.current = null;
  renderSidebar();
  document.title = "STOMS ledger";
  const totalMembers = state.aggregations.reduce((sum, a) => sum + a.member_count, 0);
  const rows = state.aggregations.map((agg) => el("tr", {
    class: "member-row",
    onclick: () => { location.hash = `#/aggregations/${encodeURIComponent(agg.id)}`; },
  },
  el("td", {}, el("a", { href: `#/aggregations/${encodeURIComponent(agg.id)}` }, agg.name)),
  el("td", { class: "num" }, agg.member_count),
  el("td", {}, formatDate(agg.created_at)),
  el("td", {}, agg.description ?? el("span", { class: "muted" }, "-")),
  el("td", {}, idCell(agg.id))));
  setMain(
    guide(),
    el("h1", {}, "Aggregations"),
    el("p", { class: "muted" }, `${state.aggregations.length} aggregations · ${totalMembers} members in total`),
    state.aggregations.length
      ? el("div", { class: "table-wrap" }, el("table", {},
        el("thead", {}, el("tr", {}, ["Name", "Members", "Created", "Description", "ID"].map((h) => el("th", {}, h)))),
        el("tbody", {}, rows)))
      : el("p", {}, "No aggregations."));
}

// What the homepage can do; collapsible, and the choice is remembered per browser.
function guide() {
  let open = true;
  try { open = localStorage.getItem("stoms.guide") !== "closed"; } catch { /* storage unavailable */ }
  const section = (title, ...items) => el("div", { class: "guide-section" },
    el("h3", {}, title), el("ul", {}, items.map((item) => el("li", {}, item))));
  const details = el("details", { class: "card guide", open },
    el("summary", {}, "About this page"),
    el("p", {}, "A read-only view of this ledger. Every page reads the ledger when it loads, so reload to see newly ingested records. Nothing here changes the ledger."),
    el("div", { class: "guide-grid" },
      section("Aggregations",
        "Pick an aggregation in the sidebar or the table below.",
        "Metadata, source query snapshot, and an extxyz export with the same label options as the CLI (requires an evaluation for every member).",
        "Summary: evaluation coverage per iteration and histograms of numeric properties per method. Click a bar to filter the members.",
        "Members: filter by text or tag, narrow by iteration, sort by any column, and expand a member for its source, method, and provenance.",
        "Select members with the checkboxes (shift-click for a range) to view or export just those; the eye and download icons view or save one member."),
      section("Structure viewer",
        "Open it from an expanded member (\u201cOpen in structure viewer\u201d).",
        "Top view and views along a and b; drag to rotate, right-drag (or shift-drag) to pan, scroll to zoom; in-plane cell repeats; resizable panel; save as SVG.",
        "Optional bonds and coordination polyhedra with adjustable cutoffs and bond radius; slicing by fractional coordinates; Miller planes.",
        "Measure distances, angles, and dihedrals by clicking atoms; measurements follow the atoms in comparisons and movies.",
        "Choose element colours under Appearance, and colour selected atoms under Atom colours.",
        "Colour by element, height, force magnitude, or per-atom force difference between two evaluations of the structure, with a choice of palettes.",
        "Force arrows from a chosen evaluation, with adjustable length, width, and colour; choose the included atoms by element or fractional coordinates.",
        "Evaluations table: energy per evaluation; click a row for its method, provenance, and every stored property.",
        "Step through structures sharing a tag prefix (e.g. one run) or the members of an aggregation, or compare two side by side.",
        "Play them as a movie (space key): adjustable frames per second, optional loop, colour scales fixed over all frames."),
      section("Good to know",
        "Each page has its own URL, so browser back/forward and bookmarks work.",
        "The server runs on this machine only and stops with Ctrl+C in its terminal.",
        "Viewer settings (cutoffs, slices, planes, colours) are remembered in this browser, and can be exported to a file and imported again.")));
  details.addEventListener("toggle", () => {
    try { localStorage.setItem("stoms.guide", details.open ? "open" : "closed"); } catch { /* storage unavailable */ }
  });
  return details;
}

// ---------------------------------------------------------------- aggregation

const COLUMNS = [
  { key: "ordinal", label: "#", num: true },
  { key: "structure_id", label: "Structure" },
  { key: "formula", label: "Formula" },
  { key: "natoms", label: "Atoms", num: true },
  { key: "source", label: "Source" },
  { key: "iteration", label: "Iteration" },
  { key: "method", label: "Method" },
  { key: "properties", label: "Properties", wrap: true },
];

function cellValue(member, key) {
  if (key === "properties") return propertiesLabel(member.properties);
  return member[key] ?? "-";
}

async function renderAggregation(id) {
  setMain(el("p", { class: "muted" }, "Loading…"));
  let agg;
  try {
    agg = await api(`aggregations/${encodeURIComponent(id)}`);
  } catch (error) {
    setMain(el("p", { class: "error" }, error.message));
    return;
  }
  state.current = agg;
  renderSidebar();
  document.title = `STOMS · ${agg.name}`;

  const view = { filter: "", iteration: null, selection: null, sortKey: "ordinal", sortDir: 1, open: new Set() };
  // Selected members (checkbox column); shift-click selects a range.
  const picks = picksOf(agg.id);
  let lastPicked = null;
  const iterations = [...new Set(agg.members.map((m) => m.iteration).filter(Boolean))].sort();

  const facts = el("dl", { class: "facts" },
    el("dt", {}, "ID"), el("dd", {}, idCell(agg.id)),
    el("dt", {}, "Members"), el("dd", {}, agg.members.length),
    el("dt", {}, "Created"), el("dd", {}, formatDate(agg.created_at)),
    agg.external_key && [el("dt", {}, "External key"), el("dd", {}, el("code", {}, agg.external_key))],
    agg.source_stored_query_id && [el("dt", {}, "Source stored query"), el("dd", {}, idCell(agg.source_stored_query_id))]);

  const extra = [];
  if (agg.metadata && Object.keys(agg.metadata).length) extra.push(treeCard("Metadata", agg.metadata));
  if (agg.source_query_snapshot) extra.push(treeCard("Source query snapshot", agg.source_query_snapshot));

  const search = el("input", { type: "search", placeholder: "Filter members (formula, ID, source, method, tag…)" });
  const count = el("span", { class: "count" });
  const selectionChip = el("span");
  const membersHeading = el("h2", {}, "Members");
  const selectMembers = (label, ordinals) => {
    view.selection = { label, ordinals: new Set(ordinals) };
    draw();
    membersHeading.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const chips = iterations.length
    ? el("div", { class: "chips" }, el("span", { class: "muted" }, "Iteration:"),
      iterations.map((it) => el("button", {
        class: "chip", type: "button", "aria-pressed": "false",
        onclick: (event) => {
          view.iteration = view.iteration === it ? null : it;
          chips.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === event.currentTarget && view.iteration !== null)));
          draw();
        },
      }, it)))
    : null;
  const pickAll = el("input", { type: "checkbox", "aria-label": "Select all shown members", title: "Select all shown members" });
  const pickBar = el("div", { class: "pick-bar" });
  const exporter = exportPanel(agg, () => picks);
  // View: the selected members in the structure viewer (stepping through only
  // them), or all members if none are selected.
  const viewMembers = () => {
    const selected = agg.members.filter((m) => picks.has(m.ordinal));
    const first = (selected.length ? selected : agg.members)[0];
    if (first) location.hash = `${memberHref(agg.id, first)}${selected.length ? "&cycle=selected" : ""}`;
  };
  const setPicks = (ordinals, picked) => {
    for (const ordinal of ordinals) (picked ? picks.add(ordinal) : picks.delete(ordinal));
    savePicks(agg.id, picks);
    draw();
    exporter.refresh();
  };
  const header = el("tr", {}, el("th", { class: "pick" }, pickAll), COLUMNS.map((col) => el("th", {
    "data-sort": col.key,
    onclick: () => {
      view.sortDir = view.sortKey === col.key ? -view.sortDir : 1;
      view.sortKey = col.key;
      draw();
    },
  }, col.label)));
  const body = el("tbody");

  function matches(member) {
    if (view.iteration && member.iteration !== view.iteration) return false;
    if (view.selection && !view.selection.ordinals.has(member.ordinal)) return false;
    if (!view.filter) return true;
    const haystack = [member.structure_id, member.formula, member.source, member.method ?? "",
      member.evaluation_id ?? "", propertiesLabel(member.properties), ...member.tags].join(" ").toLowerCase();
    return view.filter.split(/\s+/).every((term) => haystack.includes(term));
  }

  function draw() {
    header.querySelectorAll("th").forEach((th) => {
      th.classList.toggle("asc", th.dataset.sort === view.sortKey && view.sortDir === 1);
      th.classList.toggle("desc", th.dataset.sort === view.sortKey && view.sortDir === -1);
    });
    const numeric = COLUMNS.find((c) => c.key === view.sortKey)?.num;
    const rows = agg.members.filter(matches).sort((a, b) => {
      const x = cellValue(a, view.sortKey), y = cellValue(b, view.sortKey);
      const order = numeric ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
      return order * view.sortDir || a.ordinal - b.ordinal;
    });
    const shownPicked = rows.filter((m) => picks.has(m.ordinal)).length;
    pickAll.checked = rows.length > 0 && shownPicked === rows.length;
    pickAll.indeterminate = shownPicked > 0 && shownPicked < rows.length;
    pickAll.onchange = () => setPicks(rows.map((m) => m.ordinal), pickAll.checked);
    pickBar.replaceChildren(el("button", { type: "button", class: "small",
      title: picks.size ? "Open the structure viewer with the selected members" : "Open the structure viewer with all members",
      onclick: viewMembers }, "View"));
    if (picks.size) {
      pickBar.append(el("span", {}, `${picks.size} selected`),
        el("button", { type: "button", class: "small", onclick: () => selectMembers("Selected", [...picks]) }, "Show only selected"),
        el("button", { type: "button", class: "small", onclick: () => exporter.open("picked") }, "Export…"),
        el("button", { type: "button", class: "small", onclick: () => { lastPicked = null; setPicks([...picks], false); } }, "Clear"));
    }
    count.textContent = `${rows.length} of ${agg.members.length} members`;
    selectionChip.replaceChildren();
    if (view.selection) {
      selectionChip.append(el("button", {
        class: "chip", type: "button", "aria-pressed": "true", title: "Clear this filter",
        onclick: () => { view.selection = null; draw(); },
      }, `${view.selection.label} ×`));
    }
    body.replaceChildren();
    rows.forEach((member, index) => {
      const pick = el("input", { type: "checkbox", checked: picks.has(member.ordinal), "aria-label": `Select member ${member.ordinal}` });
      pick.addEventListener("click", (event) => {
        event.stopPropagation();
        const range = event.shiftKey && lastPicked !== null ? rows.slice(Math.min(lastPicked, index), Math.max(lastPicked, index) + 1) : [member];
        lastPicked = index;
        setPicks(range.map((m) => m.ordinal), pick.checked);
      });
      const tr = el("tr", { class: "member-row" },
        el("td", { class: "pick", onclick: (event) => event.stopPropagation() },
          el("span", { class: "row-actions" }, pick,
            el("a", { class: "row-icon", href: memberHref(agg.id, member), title: "View this structure", "aria-label": `View member ${member.ordinal}` }, icon("eye")),
            el("button", { type: "button", class: "row-icon", title: "Download this structure as extxyz", "aria-label": `Download member ${member.ordinal}`,
              onclick: (event) => downloadMember(event.currentTarget, member) }, icon("download")))),
        COLUMNS.map((col) => el("td", { class: col.num ? "num" : col.wrap ? "wrap" : null },
          col.key === "structure_id" ? el("code", {}, member.structure_id) : cellValue(member, col.key))));
      body.append(tr);
      if (view.open.has(member.ordinal)) {
        tr.classList.add("open");
        body.append(detailRow(agg.id, member));
      }
      tr.addEventListener("click", () => {
        if (view.open.has(member.ordinal)) view.open.delete(member.ordinal);
        else view.open.add(member.ordinal);
        draw();
      });
    });
  }

  const tableWrap = el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, header), body));

  let timer;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { view.filter = search.value.trim().toLowerCase(); draw(); }, 120);
  });

  setMain(
    el("h1", {}, agg.name),
    agg.description ? el("p", {}, agg.description) : null,
    facts,
    extra.length ? el("div", { class: "detail-grid" }, extra) : null,
    exporter.element,
    summarySection(agg.id, selectMembers),
    membersHeading,
    el("div", { class: "toolbar" }, search, selectionChip, count),
    pickBar,
    chips,
    tableWrap);
  // Keep expanded member details within the visible part of a wide table.
  new ResizeObserver(() => {
    tableWrap.style.setProperty("--wrap-width", `${tableWrap.clientWidth}px`);
  }).observe(tableWrap);
  draw();
}

const memberHref = (aggregationId, member) =>
  `#/structures/${encodeURIComponent(member.structure_id)}?from=${encodeURIComponent(aggregationId)}`;

// One member as extxyz: verbatim from a served file, else with its evaluation.
async function downloadMember(button, member) {
  const evaluation = !state.file && member.evaluation_id ? `?evaluation=${encodeURIComponent(member.evaluation_id)}` : "";
  button.disabled = true;
  try {
    await downloadExport(`api/structures/${encodeURIComponent(member.structure_id)}/extxyz${evaluation}`);
  } catch (error) {
    window.alert(`Download failed: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

// Small line icons (16 px, current text colour).
const ICONS = {
  eye: ["M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8s-2.5 4.5-6.5 4.5S1.5 8 1.5 8z", "M8 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"],
  download: ["M8 2v8", "M4.5 6.5 8 10l3.5-3.5", "M2.5 11.5v2h11v-2"],
};
const icon = (name) => svg("svg", { viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": "true", fill: "none",
  stroke: "currentColor", "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round" },
...ICONS[name].map((d) => svg("path", { d })));

function detailRow(aggregationId, member) {
  const inner = el("div", { class: "detail-inner" }, el("p", { class: "muted" }, "Loading…"));
  const cell = el("td", { colspan: COLUMNS.length + 1 }, inner);
  const key = `${aggregationId}/${member.ordinal}`;
  const load = state.memberCache.get(key) ?? api(`aggregations/${encodeURIComponent(aggregationId)}/members/${member.ordinal}`);
  state.memberCache.set(key, load);
  load.then((detail) => {
    const ev = detail.evaluation;
    inner.replaceChildren(
      el("p", {}, el("a", { class: "button-link", href: `#/structures/${encodeURIComponent(detail.structure_id)}?from=${encodeURIComponent(aggregationId)}` }, "Open in structure viewer →")),
      el("dl", { class: "facts" },
        el("dt", {}, "Structure ID"), el("dd", {}, idCell(detail.structure_id)),
        el("dt", {}, "Source"), el("dd", {}, detail.source || "-"),
        el("dt", {}, "Evaluation ID"), el("dd", {}, ev ? idCell(ev.id) : "-"),
        el("dt", {}, "Method"), el("dd", {}, ev ? ev.method : "-")),
      el("div", { class: "detail-grid" },
        treeCard("Structure source specification", detail.source_spec),
        treeCard("Structure provenance", detail.structure_provenance),
        ev && treeCard("Method specification", ev.method_spec),
        ev && treeCard("Evaluation provenance", ev.provenance)));
  }).catch((error) => {
    state.memberCache.delete(key);
    inner.replaceChildren(el("p", { class: "error" }, error.message));
  });
  return el("tr", { class: "detail-row" }, cell);
}

// ---------------------------------------------------------------- charts

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child) node.append(child);
  return node;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) return value.toExponential(2);
  return String(Number(value.toPrecision(4)));
}

function niceTicks(min, max, count = 5) {
  if (!(max > min)) return [min];
  const raw = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw);
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

// A column whose top corners are rounded (4px data-end) and whose base is square.
function columnPath(x, y, width, height) {
  const r = Math.min(4, width / 2, height);
  return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`;
}

function chartFrame(card) {
  const tooltip = el("div", { class: "tooltip", role: "status" });
  const host = el("div", { class: "chart" });
  card.append(host);
  host.append(tooltip);
  const show = (event, lines) => {
    tooltip.replaceChildren(...lines.map(([value, label]) =>
      el("div", {}, el("strong", {}, value), label ? el("span", { class: "muted" }, ` ${label}`) : null)));
    tooltip.style.display = "block";
    const box = host.getBoundingClientRect();
    const target = event.target.getBoundingClientRect();
    const left = Math.min(Math.max(target.left - box.left + target.width / 2 - tooltip.offsetWidth / 2, 0), box.width - tooltip.offsetWidth);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(target.top - box.top - tooltip.offsetHeight - 6, 0)}px`;
  };
  const hide = () => { tooltip.style.display = "none"; };
  return { host, show, hide };
}

function drawWhenSized(host, render) {
  let width = 0;
  new ResizeObserver(() => {
    const next = Math.floor(host.clientWidth);
    if (next && next !== width) { width = next; render(width); }
  }).observe(host);
}

// Histogram: bins = [{lo, hi, count, ordinals?}]. Clicking a bin with ordinals selects those members.
function histogram(card, bins, { unit, onSelect }) {
  const { host, show, hide } = chartFrame(card);
  const height = 170, margin = { top: 10, right: 8, bottom: 30, left: 44 };
  drawWhenSized(host, (width) => {
    host.querySelector("svg")?.remove();
    const plotW = width - margin.left - margin.right, plotH = height - margin.top - margin.bottom;
    const lo = bins[0].lo, hi = bins[bins.length - 1].hi;
    const maxCount = Math.max(1, ...bins.map((b) => b.count));
    const yTicks = niceTicks(0, maxCount, 4).filter((t) => Number.isInteger(t));
    const yMax = Math.max(maxCount, yTicks[yTicks.length - 1]);
    const x = (v) => margin.left + ((v - lo) / (hi - lo || 1)) * plotW;
    const y = (v) => margin.top + plotH - (v / yMax) * plotH;
    const grid = yTicks.map((t) => svg("g", {},
      svg("line", { class: "grid", x1: margin.left, x2: width - margin.right, y1: y(t), y2: y(t) }),
      svg("text", { class: "tick", x: margin.left - 6, y: y(t), "text-anchor": "end", "dominant-baseline": "middle" }, document.createTextNode(t.toString()))));
    const xTicks = niceTicks(lo, hi, Math.max(2, Math.floor(plotW / 90))).map((t) => svg("text", {
      class: "tick", x: x(t), y: height - margin.bottom + 16, "text-anchor": "middle",
    }, document.createTextNode(formatNumber(t))));
    const bars = bins.map((bin) => {
      const x0 = x(bin.lo), x1 = x(bin.hi);
      const barW = Math.max(1, x1 - x0 - 2);
      const selectable = onSelect && bin.ordinals && bin.count > 0;
      const range = `${formatNumber(bin.lo)} – ${formatNumber(bin.hi)}${unit ? ` ${unit}` : ""}`;
      const lines = [[bin.count.toString(), bin.count === 1 ? "member" : "members"], [range]];
      if (selectable) lines.push(["", "click to filter members"]);
      return svg("g", { class: selectable ? "bin selectable" : "bin" },
        bin.count ? svg("path", { class: "bar", d: columnPath(x0 + 1, y(bin.count), barW, y(0) - y(bin.count)) }) : null,
        svg("rect", {
          class: "hit", x: x0, y: margin.top, width: Math.max(1, x1 - x0), height: plotH,
          tabindex: bin.count ? 0 : null,
          onpointerenter: (event) => show(event, lines), onpointerleave: hide,
          onfocus: (event) => show(event, lines), onblur: hide,
          onclick: selectable ? () => onSelect(range, bin.ordinals) : null,
          onkeydown: selectable ? (event) => { if (event.key === "Enter") onSelect(range, bin.ordinals); } : null,
        }));
    });
    host.prepend(svg("svg", { width, height, role: "img", "aria-label": "Histogram" },
      grid,
      svg("line", { class: "axis", x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0) }),
      xTicks, bars));
  });
}

function binValues(values, ordinals) {
  const finite = values.map((v, i) => [v, ordinals[i]]).filter(([v]) => Number.isFinite(v));
  let lo = Math.min(...finite.map(([v]) => v)), hi = Math.max(...finite.map(([v]) => v));
  if (lo === hi) { lo -= 0.5; hi += 0.5; }
  const count = Math.min(40, Math.max(5, Math.ceil(Math.sqrt(finite.length))));
  const width = (hi - lo) / count;
  const bins = Array.from({ length: count }, (_, i) => ({ lo: lo + i * width, hi: lo + (i + 1) * width, count: 0, ordinals: [] }));
  for (const [v, ordinal] of finite) {
    const bin = bins[Math.min(count - 1, Math.floor((v - lo) / width))];
    bin.count += 1;
    bin.ordinals.push(ordinal);
  }
  return bins;
}

function statsTable(stats, unit) {
  if (!stats.n) return el("p", { class: "muted" }, "No finite values.");
  const cells = [["n", stats.n.toString()], ["min", formatNumber(stats.min)], ["mean", formatNumber(stats.mean)],
    ["std", formatNumber(stats.std)], ["max", formatNumber(stats.max)]];
  return el("table", { class: "stats" },
    el("thead", {}, el("tr", {}, cells.map(([k]) => el("th", {}, k)))),
    el("tbody", {}, el("tr", {}, cells.map(([, v]) => el("td", { class: "num" }, v)))),
    unit ? el("caption", {}, `values in ${unit}`) : null);
}

function propertyCard(series, onSelect) {
  const unit = series.unit ?? "";
  const modes = [];
  if (series.values.length) {
    modes.push({ label: `Per structure: ${series.per_member}`, unit, values: series.values });
    if (series.kind === "scalar") {
      modes.push({ label: "Per structure, divided by atom count", unit: unit ? `${unit}/atom` : "per atom",
        values: series.values.map((v, i) => v / series.natoms[i]) });
    }
  }
  if (series.pooled) modes.push({ label: `All atoms: ${series.pooled.label}`, unit, pooled: series.pooled });
  const card = el("div", { class: "card chart-card" },
    el("h3", {}, series.property, unit ? el("span", { class: "muted" }, ` [${unit}]`) : null),
    el("div", { class: "muted subtitle" }, series.method));
  if (!modes.length) return card.append(el("p", { class: "muted" }, "No finite values.")), card;
  const body = el("div");
  const render = (mode) => {
    body.replaceChildren();
    if (mode.pooled) {
      const { edges, counts } = mode.pooled.histogram;
      histogram(body, counts.map((count, i) => ({ lo: edges[i], hi: edges[i + 1], count })), { unit: mode.unit });
      body.append(statsTable(mode.pooled.stats, mode.unit));
    } else {
      histogram(body, binValues(mode.values, series.ordinals), {
        unit: mode.unit,
        onSelect: (range, ordinals) => onSelect(`${series.property} ${range}`, ordinals),
      });
      const v = mode.values;
      const mean = v.reduce((a, b) => a + b, 0) / v.length;
      body.append(statsTable({ n: v.length, min: Math.min(...v), max: Math.max(...v), mean,
        std: Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length) }, mode.unit));
    }
  };
  if (modes.length > 1) {
    const select = el("select", { "aria-label": "Distribution" }, modes.map((m, i) => el("option", { value: i }, m.label)));
    select.addEventListener("change", () => render(modes[select.value]));
    card.append(select);
  } else {
    card.append(el("div", { class: "muted subtitle" }, modes[0].label));
  }
  card.append(body);
  render(modes[0]);
  return card;
}

function coverageCard(summary) {
  const rows = summary.iterations.map((r) => ({ ...r, label: r.iteration ?? "untagged" }));
  const card = el("div", { class: "card chart-card" },
    el("h3", {}, "Evaluation coverage by iteration"),
    el("div", { class: "legend" },
      el("span", {}, el("i", { class: "swatch s1" }), "evaluated"),
      el("span", {}, el("i", { class: "swatch s2" }), "missing evaluation")));
  const { host, show, hide } = chartFrame(card);
  const height = 170, margin = { top: 10, right: 8, bottom: 30, left: 44 };
  drawWhenSized(host, (width) => {
    host.querySelector("svg")?.remove();
    const plotW = width - margin.left - margin.right, plotH = height - margin.top - margin.bottom;
    const maxTotal = Math.max(1, ...rows.map((r) => r.evaluated + r.missing));
    const yTicks = niceTicks(0, maxTotal, 4).filter((t) => Number.isInteger(t));
    const yMax = Math.max(maxTotal, yTicks[yTicks.length - 1]);
    const y = (v) => margin.top + plotH - (v / yMax) * plotH;
    const slot = plotW / rows.length;
    const barW = Math.min(24, slot * 0.6);
    const labelEvery = Math.ceil(rows.length / Math.max(1, Math.floor(plotW / 48)));
    const columns = rows.map((row, i) => {
      const cx = margin.left + slot * (i + 0.5);
      const x0 = cx - barW / 2;
      const evalTop = y(row.evaluated), totalTop = y(row.evaluated + row.missing);
      const segments = [];
      if (row.evaluated) {
        segments.push(row.missing
          ? svg("rect", { class: "bar s1", x: x0, y: evalTop, width: barW, height: y(0) - evalTop })
          : svg("path", { class: "bar s1", d: columnPath(x0, evalTop, barW, y(0) - evalTop) }));
      }
      if (row.missing) {
        const top = totalTop, bottom = row.evaluated ? evalTop - 2 : y(0);
        if (bottom > top) segments.push(svg("path", { class: "bar s2", d: columnPath(x0, top, barW, bottom - top) }));
      }
      const lines = [[row.label], [row.evaluated.toString(), "evaluated"], [row.missing.toString(), "missing evaluation"]];
      return svg("g", { class: "bin" }, segments,
        i % labelEvery === 0 ? svg("text", { class: "tick", x: cx, y: height - margin.bottom + 16, "text-anchor": "middle" }, document.createTextNode(row.label)) : null,
        svg("rect", { class: "hit", x: cx - slot / 2, y: margin.top, width: slot, height: plotH, tabindex: 0,
          onpointerenter: (e) => show(e, lines), onpointerleave: hide, onfocus: (e) => show(e, lines), onblur: hide }));
    });
    host.prepend(svg("svg", { width, height, role: "img", "aria-label": "Evaluation coverage by iteration" },
      yTicks.map((t) => svg("g", {},
        svg("line", { class: "grid", x1: margin.left, x2: width - margin.right, y1: y(t), y2: y(t) }),
        svg("text", { class: "tick", x: margin.left - 6, y: y(t), "text-anchor": "end", "dominant-baseline": "middle" }, document.createTextNode(t.toString())))),
      svg("line", { class: "axis", x1: margin.left, x2: width - margin.right, y1: y(0), y2: y(0) }),
      columns));
  });
  card.append(el("details", { class: "table-view" }, el("summary", {}, "Table"),
    el("table", { class: "stats" },
      el("thead", {}, el("tr", {}, el("th", {}, "iteration"), el("th", {}, "evaluated"), el("th", {}, "missing"))),
      el("tbody", {}, rows.map((r) => el("tr", {}, el("td", {}, r.label),
        el("td", { class: "num" }, r.evaluated.toString()), el("td", { class: "num" }, r.missing.toString())))))));
  return card;
}

function statTile(label, value, note) {
  return el("div", { class: "tile" }, el("div", { class: "tile-label" }, label),
    el("div", { class: "tile-value" }, value), note ? el("div", { class: "muted tile-note" }, note) : null);
}

function summarySection(aggregationId, onSelect) {
  const section = el("section", {}, el("h2", {}, "Summary"), el("p", { class: "muted" }, "Computing property distributions…"));
  api(`aggregations/${encodeURIComponent(aggregationId)}/summary`).then((summary) => {
    const methods = new Set(summary.properties.map((p) => p.method));
    const charts = [];
    if (summary.iterations.length > 1 || summary.missing) charts.push(coverageCard(summary));
    for (const series of summary.properties) charts.push(propertyCard(series, onSelect));
    section.replaceChildren(el("h2", {}, "Summary"),
      el("div", { class: "tiles" },
        statTile("Members", summary.members.toString()),
        statTile("Evaluated", summary.evaluated.toString(),
          summary.members ? `${Math.round((100 * summary.evaluated) / summary.members)}%` : null),
        statTile("Missing evaluation", summary.missing.toString()),
        statTile("Methods", methods.size.toString())),
      charts.length ? el("div", { class: "chart-grid" }, charts) : el("p", { class: "muted" }, "No numeric properties."));
  }).catch((error) => {
    section.replaceChildren(el("h2", {}, "Summary"), el("p", { class: "error" }, error.message));
  });
  return section;
}

// ---------------------------------------------------------------- extxyz export

// Groupings offered for splitting or filtering an export.
const EXPORT_GROUPINGS = {
  none: { label: "Whole aggregation" },
  formula: { label: "Stoichiometry", key: (m) => m.formula },
  iteration: { label: "Iteration", key: (m) => (m.iteration ? `iteration-${m.iteration}` : "untagged") },
  tag: { label: "Tag prefix…" },
};

// Export panel of an aggregation page. Exports all members (strict: each needs
// an evaluation) or the selected ones (those without an evaluation are written as
// structures only). Frames of a served extxyz file are copied verbatim.
// Returns { element, refresh, open(scope) }.
function exportPanel(agg, getPicks) {
  const view = { scope: "all", grouping: "none", prefix: "role:", output: "split", excluded: new Set() };
  const scopeChoice = el("div", { class: "export-output export-scope" });
  const field = (name, value) => el("label", {}, el("span", { class: "muted" }, name),
    el("input", { type: "text", name, value, spellcheck: "false" }));
  const status = el("span", { class: "muted" });
  const button = el("button", { class: "primary", type: "submit" }, "Download extxyz");
  const prefixInput = el("input", { type: "text", value: view.prefix, class: "prefix-input", spellcheck: "false", "aria-label": "Tag prefix" });
  const groupingSelect = el("select", { "aria-label": "Group by" },
    Object.entries(EXPORT_GROUPINGS).map(([value, g]) => el("option", { value }, g.label)));
  const groupBox = el("div", { class: "export-groups" });
  const outputChoice = el("div", { class: "export-output" },
    ["split", "single"].map((value) => el("label", { class: "check" },
      el("input", { type: "radio", name: "export-output", value, checked: view.output === value,
        onchange: () => { view.output = value; refresh(); } }),
      value === "split" ? "One file per group (zip)" : "Single file with the selected groups")));

  function keyOf(member) {
    if (view.grouping === "tag") {
      const tags = member.tags.filter((t) => t.startsWith(view.prefix)).map((t) => t.slice(view.prefix.length));
      return tags.length ? tags.join("+") : "(no tag)";
    }
    return EXPORT_GROUPINGS[view.grouping].key(member);
  }

  const scopeMembers = () => (view.scope === "picked" ? agg.members.filter((m) => getPicks().has(m.ordinal)) : agg.members);

  function groups() {
    const base = agg.name || agg.id;
    if (view.grouping === "none") return [{ key: view.scope === "picked" ? `${base.replace(/\.extxyz$/, "")}_selected` : base, members: scopeMembers() }];
    const map = new Map();
    for (const member of scopeMembers()) {
      const key = keyOf(member);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(member);
    }
    return [...map.entries()].map(([key, members]) => ({ key, members }))
      .sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
  }

  function refresh() {
    const pickedCount = getPicks().size;
    if (view.scope === "picked" && !pickedCount) view.scope = "all";
    scopeChoice.replaceChildren(...[["all", `All members (${agg.members.length})`], ["picked", `Selected members (${pickedCount})`]].map(([value, text]) =>
      el("label", { class: "check" }, el("input", { type: "radio", name: "export-scope", value, checked: view.scope === value,
        disabled: value === "picked" && !pickedCount, onchange: () => { view.scope = value; view.excluded.clear(); refresh(); } }), text)));
    const all = groups();
    const grouped = view.grouping !== "none";
    prefixInput.hidden = view.grouping !== "tag";
    outputChoice.hidden = !grouped;
    groupBox.replaceChildren();
    if (grouped) {
      const setAll = (include) => { for (const g of all) (include ? view.excluded.delete(g.key) : view.excluded.add(g.key)); refresh(); };
      groupBox.append(
        el("div", { class: "export-groups-head" }, el("span", { class: "muted" }, `${all.length} groups`),
          el("button", { type: "button", class: "small", onclick: () => setAll(true) }, "All"),
          el("button", { type: "button", class: "small", onclick: () => setAll(false) }, "None")),
        el("div", { class: "export-group-list" }, all.map((g) => {
          const missing = g.members.filter((m) => !m.evaluation_id).length;
          return el("label", { class: "check" },
            el("input", { type: "checkbox", checked: !view.excluded.has(g.key), onchange: (event) => {
              if (event.target.checked) view.excluded.delete(g.key); else view.excluded.add(g.key);
              refresh();
            } }),
            el("span", {}, el("code", {}, g.key), el("span", { class: "muted" },
              ` ${g.members.length} member${g.members.length === 1 ? "" : "s"}${missing ? `, ${missing} without evaluation` : ""}`)));
        })));
    }
    const selected = all.filter((g) => !grouped || !view.excluded.has(g.key));
    const members = selected.flatMap((g) => g.members);
    const missing = state.file ? 0 : members.filter((m) => !m.evaluation_id).length;
    const strict = view.scope === "all";
    const files = grouped && view.output === "split" ? selected.length : 1;
    button.disabled = !members.length || (strict && missing > 0);
    button.textContent = files > 1 ? `Download zip (${files} files, ${members.length} frames)` : `Download extxyz (${members.length} frames)`;
    status.className = "muted";
    status.textContent = !members.length ? "No members selected."
      : strict && missing ? `Exporting all members needs an evaluation for each; ${missing} ${missing === 1 ? "has" : "have"} none. Select members to export them as structures only.`
        : missing ? `${missing} without an evaluation ${missing === 1 ? "is" : "are"} written as ${missing === 1 ? "a structure" : "structures"} only.` : "";
    return { selected, members, files };
  }

  groupingSelect.addEventListener("change", () => { view.grouping = groupingSelect.value; view.excluded.clear(); refresh(); });
  prefixInput.addEventListener("change", () => { view.prefix = prefixInput.value; view.excluded.clear(); refresh(); });

  const form = el("form", { class: "export-form" },
    scopeChoice,
    state.file
      ? el("p", { class: "muted export-verbatim" }, "Frames are copied verbatim from the file, in file order.")
      : [field("energy_label", "REF_energy"), field("forces_label", "REF_forces"), field("node_energy_label", "REF_node_energy"),
        el("label", { class: "check" }, el("input", { type: "checkbox", name: "include_node_energy", value: "1" }), "Include per-atom energies")],
    el("div", { class: "export-split" },
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Group by"), groupingSelect, prefixInput),
      groupBox, outputChoice),
    el("div", { class: "export-actions" }, button, status));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const { selected, members, files } = refresh();
    if (button.disabled) return;
    const base = (agg.name || agg.id).replace(/\.extxyz$/, "");
    const fileList = files > 1
      ? selected.map((g) => ({ name: `${base}_${g.key}`, ordinals: g.members.map((m) => m.ordinal) }))
      : [{ name: view.grouping !== "none" ? base : selected[0].key.replace(/\.extxyz$/, ""), ordinals: members.map((m) => m.ordinal) }];
    const data = new FormData(form);
    const payload = {
      ...(state.file ? {} : {
        energy_label: data.get("energy_label"), forces_label: data.get("forces_label"),
        node_energy_label: data.get("node_energy_label"), include_node_energy: data.get("include_node_energy") === "1",
      }),
      include_unevaluated: view.scope === "picked", archive_name: base, files: fileList,
    };
    button.disabled = true;
    status.className = "muted";
    status.textContent = "Exporting…";
    try {
      const filename = await downloadExport(`api/aggregations/${encodeURIComponent(agg.id)}/extxyz`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      refresh();
      status.textContent = `Downloaded ${filename} (${members.length} frames).`;
    } catch (error) {
      status.className = "error";
      status.textContent = error.message;
      button.disabled = false;
    }
  });
  refresh();
  const element = el("details", { class: "card export" }, el("summary", {}, "Export to extxyz"), form);
  return {
    element,
    refresh,
    open(scope) {
      view.scope = scope;
      view.excluded.clear();
      refresh();
      element.open = true;
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  };
}

// ---------------------------------------------------------------- routing

function route() {
  const structure = location.hash.match(/^#\/structures\/([^?]+)(?:\?(.*))?$/);
  if (structure) {
    state.current = null;
    renderSidebar();
    renderStructurePage(decodeURIComponent(structure[1]), new URLSearchParams(structure[2] ?? ""));
    return;
  }
  leaveStructurePage();
  const match = location.hash.match(/^#\/aggregations\/(.+)$/);
  if (match) renderAggregation(decodeURIComponent(match[1]));
  else renderOverview();
}

// Sidebar visibility, remembered per browser.
function setupSidebarToggle() {
  const button = $("#sidebar-toggle");
  const apply = (hidden) => {
    document.body.classList.toggle("sidebar-hidden", hidden);
    button.setAttribute("aria-expanded", String(!hidden));
    button.title = hidden ? "Show sidebar" : "Hide sidebar";
  };
  let hidden = false;
  try { hidden = localStorage.getItem("stoms.sidebar") === "hidden"; } catch { /* storage unavailable */ }
  apply(hidden);
  button.addEventListener("click", () => {
    hidden = !hidden;
    apply(hidden);
    try { localStorage.setItem("stoms.sidebar", hidden ? "hidden" : "shown"); } catch { /* storage unavailable */ }
  });
}

async function start() {
  setupSidebarToggle();
  $("#agg-filter").addEventListener("input", renderSidebar);
  try {
    const [overview, aggregations] = await Promise.all([api("ledger"), api("aggregations")]);
    $("#ledger-label").textContent = overview.ledger;
    state.file = Boolean(overview.file);
    state.aggregations = aggregations;
  } catch (error) {
    setMain(el("p", { class: "error" }, `Could not reach the STOMS server: ${error.message}`));
    return;
  }
  window.addEventListener("hashchange", route);
  route();
}

start();
