"use strict";

// The viewer outside the ledger pages: one structure panel of viewer.js with a
// compact toolbar, for notebooks (stoms.viewer.view) and saved HTML files.
//
// Reads STOMS_EMBED (see stoms/viewer/document.py):
//   { frames, frame, settings, camera, title, bridge, height, api, measurements }
// frames are structure JSON as the ledger server sends it (id, symbols,
// positions, cell, pbc, arrays, properties); settings are viewerPrefs (the
// format of the viewer's settings files); camera is sharedView { R, scale, pan }.
//
// In an iframe, the page posts its height to the parent window. With
// `bridge` it also talks to the notebook widget (stoms/viewer/widget.js):
//   parent -> page: { stoms, type: "state", frame?, settings?, camera? }
//                   { stoms, type: "view", name }
//                   { stoms, type: "api", id, data | error }
//   page -> parent: { stoms, type: "ready" }
//                   { stoms, type: "api", id, path }
//                   { stoms, type: "size", height }
//                   { stoms, type: "snapshot", state: { frame, settings, camera }, svg, measurements }
// A snapshot follows every change once drawing settles: the SVG Python saves
// is the one drawn for exactly that state.
//
// What the ledger server computes on request (phonons: modes at any q, bands,
// DOS) the page asks for with api(path) as on the server; Python answers over
// the bridge. Replies are kept (`api`, by path), also in pop-out copies, which
// have no kernel to ask.
//
// Uses dom.js (el, formatNumber) and viewer.js (createPanel, viewerPrefs,
// sharedView, normalizePrefs, panelsToSvg, presetRotation, axisRotation, ...).

(() => {
  const data = STOMS_EMBED;
  // The page as loaded, before anything is drawn; the pop-out tab and saved
  // HTML files are copies of it with the current state.
  const pristine = `<!doctype html>\n${document.documentElement.outerHTML}`;
  const frames = data.frames;
  const framed = window.parent !== window;
  const bridge = Boolean(data.bridge) && framed;
  const post = (message) => { if (framed) window.parent.postMessage({ stoms: true, ...message }, "*"); };
  const clampFrame = (i) => Math.max(0, Math.min(frames.length - 1, Math.round(Number(i)) || 0));
  let index = clampFrame(data.frame);

  // viewer.js asks for data with api(path), answered here instead of by a server.
  const replies = new Map(Object.entries(data.api ?? {}));
  const waiting = new Map();
  let requests = 0;
  const API_TIMEOUT = 300_000;
  const copy = (value) => JSON.parse(JSON.stringify(value));
  globalThis.api = (path) => {
    if (replies.has(path)) return Promise.resolve(copy(replies.get(path)));
    if (!bridge) {
      return Promise.reject(new Error("This is computed in Python: open the viewer in its notebook, with the kernel running."));
    }
    const id = ++requests;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        waiting.delete(id);
        reject(new Error("No answer from Python: is the notebook's kernel running?"));
      }, API_TIMEOUT);
      waiting.set(id, { path, resolve, reject, timer });
      post({ type: "api", id, path });
    });
  };
  function replied(m) {
    const request = waiting.get(m.id);
    if (!request) return;
    waiting.delete(m.id);
    clearTimeout(request.timer);
    if (m.error !== undefined && m.error !== null) { request.reject(new Error(m.error)); return; }
    replies.set(request.path, m.data);
    request.resolve(copy(m.data));
  }
  document.body.classList.toggle("embed-standalone", !framed);
  if (data.title) document.title = data.title;

  // ------------------------------------------------------------ settings & camera

  // Bond cutoffs for every element pair in the frames, as on the structure page.
  const species = [...new Set(frames.flatMap((f) => f.symbols))].sort();
  const fillCutoffs = (prefs) => {
    for (const a of species) for (const b of species) prefs.cutoffs[pairKey(a, b)] ??= defaultCutoff(a, b);
    return prefs;
  };
  fillCutoffs(viewerPrefs);
  const replacePrefs = (next) => {
    for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
    Object.assign(viewerPrefs, next);
  };

  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  const isRotation = (R) => Array.isArray(R) && R.length === 3 && R.every((row) => Array.isArray(row) && row.length === 3 && row.every(finite));
  const isOrthonormal = (R) => R.every((row, i) => R.every((other, j) => Math.abs(dot(row, other) - (i === j ? 1 : 0)) < 1e-9));
  const cameraState = () => ({
    R: sharedView.R ? sharedView.R.map((row) => [...row]) : null,
    scale: sharedView.scale, pan: [...sharedView.pan],
  });
  // A camera without a usable rotation means the default: top view, fitted.
  function applyCamera(camera) {
    if (camera && isRotation(camera.R)) {
      sharedView.R = isOrthonormal(camera.R) ? camera.R.map((row) => [...row]) : orthonormalize(camera.R);
      sharedView.scale = finite(camera.scale) && camera.scale > 0 ? camera.scale : null;
      sharedView.pan = Array.isArray(camera.pan) && camera.pan.length === 2 && camera.pan.every(finite) ? [...camera.pan] : [0, 0];
    } else {
      Object.assign(sharedView, { R: null, scale: null, pan: [0, 0] });
    }
  }
  applyCamera(data.camera);

  const exportOptions = () => ({ transparent: viewerPrefs.svgTransparent, tripod: viewerPrefs.tripod.export });
  const fileStem = () => `${frames[index].formula}${frames.length > 1 ? `-frame${index}` : ""}`;

  // ------------------------------------------------------------ layout

  const root = document.getElementById("stoms-root");
  const host = el("div", { class: "viewer-panel embed-panel" });
  const panel = createPanel(host);
  // The structure, and a phonon plot below or beside it (as on the structure page).
  const figures = el("div", { class: "viewer-figures" }, host);
  const bar = el("div", { class: "embed-bar", role: "toolbar", "aria-label": "Viewer" });
  const vibrationBox = el("div", { class: "viewer-controls embed-vibrations", hidden: true });
  const measureBox = el("div", { class: "viewer-controls embed-measure", hidden: true });
  const settingsBox = el("div", { class: "embed-settings", hidden: true });
  const status = el("div", { class: "embed-status muted" });
  // What a click on an atom does while measuring (as on the structure page).
  const clickMode = el("div", { class: "click-mode", role: "status" });
  // Colour scale or categories of a property colouring.
  const legend = el("div", { class: "viewer-legend embed-legend" });
  root.append(clickMode, figures, legend, bar, measureBox, vibrationBox, settingsBox, status);
  // Every drawing of the scene (also a vibrating mode) is followed by a snapshot.
  const rebuildPanel = panel.rebuild;
  panel.rebuild = () => { rebuildPanel(); changed(); };

  // Settings controls register here how they show viewerPrefs (after imports
  // and changes from Python).
  const syncs = [];
  const sync = () => syncs.forEach((f) => f());
  // Controls that are rebuilt only when the settings change from outside
  // (Python, an imported file): rebuilding them after their own changes
  // would close an open colour picker.
  const externals = [];
  const syncExternal = () => externals.forEach((f) => f());

  function applySize() {
    const { width, height } = viewerPrefs.panelSize;
    panel.stage.style.height = height ? `${height}px` : framed ? `${data.height || 440}px` : "";
    panel.stage.style.width = width ? `${width}px` : "";
    host.classList.toggle("fixed-width", Boolean(width));
  }

  // Tooltip: element, index and height as on the structure page, then the
  // atom's values of up to four per-atom arrays (charges, forces, ...).
  const arrayText = (array, i) => {
    const v = array.values[i];
    if (array.kind === "vector") return v.includes(null) ? "–" : `${formatNumber(norm(v))} (|v|)`;
    return valueText(v);
  };
  function overlayFor(s) {
    const hs = heights(s);
    const shown = (s.arrays ?? []).slice(0, 4);
    return {
      colour: (i, symbol) => elementColor(symbol),
      describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[i].toFixed(2)} Å`, "height"],
        ...shown.map((a) => [arrayText(a, i), a.unit ? `${a.name} (${a.unit})` : a.name])],
    };
  }

  function propertyText(p) {
    const value = Array.isArray(p.value) ? `[${p.value.map((v) => (v === null ? "–" : formatNumber(v))).join(", ")}]`
      : typeof p.value === "number" ? String(Number(p.value.toPrecision(10))) : String(p.value);
    return `${p.name} = ${value}${p.unit ? ` ${p.unit}` : ""}`;
  }
  function renderStatus() {
    const s = frames[index];
    const scene = panel.scene;
    const energy = (s.properties ?? []).find((p) => p.source === "calculator" && p.name === "energy")
      ?? (s.properties ?? []).find((p) => p.name === "energy");
    status.textContent = [
      `${s.formula} · ${s.symbols.length} atoms`,
      `pbc ${s.pbc.map((p) => (p ? "T" : "F")).join("")}`,
      energy ? propertyText(energy) : null,
      scene && scene.totalAtoms > LARGE_SCENE ? "a large repeat: drawing may be slow" : null,
      colourNotes || null,
    ].filter(Boolean).join(" · ");
  }

  // ------------------------------------------------------------ force arrows

  // Per-atom vectors of the frames that can be drawn as arrows: calculator
  // forces first, then other 3-vector columns (extxyz REF_forces, ...). The
  // choice is viewerPrefs.forceChoice ({ source, name }), as a setting.
  const vectorChoices = (() => {
    const found = new Map();
    for (const f of frames) for (const a of f.arrays ?? []) {
      if (a.kind === "vector" && !found.has(`${a.source}:${a.name}`)) found.set(`${a.source}:${a.name}`, { source: a.source, name: a.name, unit: a.unit ?? null });
    }
    return [...found.values()].sort((a, b) => (b.source === "calculator") - (a.source === "calculator") || (b.name === "forces") - (a.name === "forces"));
  })();
  const chosenVector = () => {
    const c = viewerPrefs.forceChoice;
    return vectorChoices.find((v) => c && v.source === c.source && v.name === c.name) ?? vectorChoices[0] ?? null;
  };
  const vectorArray = (s, choice) => (choice ? (s.arrays ?? []).find((a) => a.kind === "vector" && a.source === choice.source && a.name === choice.name) : null);
  // What buildScene draws arrows from (and the tooltip shows), or null.
  function forcesFor(s) {
    if (!viewerPrefs.arrows.show) return null;
    const array = vectorArray(s, chosenVector());
    if (!array) return null;
    const vectors = array.values.map((v) => v.map((c) => c ?? 0));
    return { vectors, magnitudes: vectors.map(norm), included: forceIncluded(s), unit: array.unit ?? null, name: array.name };
  }
  // Auto length: the largest included vector of all frames becomes a 1.5 Å arrow.
  function autoArrowScale() {
    const choice = chosenVector();
    let max = 0;
    for (const f of frames) {
      const array = vectorArray(f, choice);
      if (!array) continue;
      const included = forceIncluded(f);
      array.values.forEach((v, i) => { if (included[i] && !v.includes(null)) max = Math.max(max, norm(v)); });
    }
    return max > 1e-9 ? Number((1.5 / max).toPrecision(2)) : null;
  }

  // ------------------------------------------------------------ measurements

  // Measurements from Python or a copied page ({ kind, atoms: [ref] }, see
  // measureState); anything else is dropped.
  const isRef = (r) => r && Number.isInteger(r.index) && r.index >= 0 && Number.isInteger(r.count) && typeof r.symbol === "string"
    && Array.isArray(r.image) && r.image.length === 3 && r.image.every(Number.isInteger);
  const validMeasurements = (items) => items
    .filter((item) => item && MEASURE_ATOMS[item.kind] && Array.isArray(item.atoms) && item.atoms.length === MEASURE_ATOMS[item.kind] && item.atoms.every(isRef))
    .map((item) => ({ kind: item.kind, atoms: item.atoms.map((r) => ({ index: r.index, image: [...r.image], symbol: r.symbol, count: r.count })) }));
  measureState.items = validMeasurements(Array.isArray(data.measurements) ? data.measurements : []);
  const measure = createMeasurePanel({ structures: () => [frames[index]], panels: () => [panel], stages: figures, clickMode, where: "📏" });
  measureBox.append(el("h3", {}, "Measure"), measure.controls);
  // Measurements with their values on the shown frame, for Python.
  const measurementsNow = () => measureState.items.map((item) => {
    const s = frames[index];
    const value = fitsStructure(s, item.atoms) ? measureValue(s, item) : null;
    return { kind: item.kind, atoms: item.atoms, value: value?.value ?? null, nearest: value?.nearest ?? null };
  });

  // ------------------------------------------------------------ colour by property

  // Properties of every frame (propertyOptions): per-atom arrays, calculator
  // results and values from the geometry. Ring sizes need the ledger
  // server's ring analysis and are left out.
  const colourOptions = (() => {
    const found = new Map();
    for (const f of frames) for (const o of propertyOptions(f)) {
      if (o.choice.source === "derived" && o.choice.name === "ring") continue;
      if (!found.has(o.key)) found.set(o.key, o);
    }
    return [...found.values()];
  })();
  const colouring = () => viewerPrefs.colour === "property";
  // One colour scale for all frames (as for a movie on the structure page).
  async function propertyRange() {
    const { choice, component } = viewerPrefs.property;
    const ranges = await Promise.all(frames.map(async (f) => extent(shownNumbers(f, await propertyValues(f, choice, component)))));
    return ranges.reduce(([lo, hi], [a, b]) => [Math.min(lo, a), Math.max(hi, b)], [Infinity, -Infinity]);
  }
  let colourToken = 0;
  let colourNotes = "";
  // The shown frame in property colours (async: values may be loading).
  async function colourByProperty(s) {
    const token = ++colourToken;
    const result = await propertyOverlays({ structures: [s], range: propertyRange, current: () => token === colourToken && frames[index] === s });
    if (!result) return;
    panel.overlay = result.overlays[0];
    legend.replaceChildren(...result.legend);
    colourNotes = result.notes.join(" ");
    panel.rebuild();
    renderStatus();
  }

  // ------------------------------------------------------------ drawing and state

  let snapshotTimer = 0;
  let lastSnapshot = "";
  function changed() {
    if (!bridge) return;
    clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(sendSnapshot, 200);
  }
  function sendSnapshot() {
    if (!panel.scene || !panel.stage.clientWidth || !sharedView.R) return;
    const state = { frame: index, settings: JSON.parse(JSON.stringify(viewerPrefs)), camera: cameraState() };
    const svg = panelsToSvg([panel], exportOptions());
    const measurements = measurementsNow();
    const key = `${JSON.stringify(state)}\n${JSON.stringify(measurements)}\n${svg}`;
    if (key === lastSnapshot) return;
    lastSnapshot = key;
    post({ type: "snapshot", state, svg, measurements });
  }

  function showFrame(i) {
    index = clampFrame(i);
    const s = frames[index];
    panel.structure = s;
    panel.forces = forcesFor(s);
    if (colouring()) {
      colourByProperty(s);
    } else {
      colourToken += 1;
      colourNotes = "";
      panel.overlay = overlayFor(s);
      legend.replaceChildren();
    }
    // Until property colours have loaded, the frame keeps its last colours.
    panel.overlay ??= overlayFor(s);
    panel.rebuild();
    measure.render();
    sync();
    renderStatus();
    changed();
  }
  // Everything again after the settings changed.
  let refreshFrame = 0;
  function refresh() {
    cancelAnimationFrame(refreshFrame);
    refreshFrame = requestAnimationFrame(() => { applySize(); showFrame(index); });
  }
  // viewer.js calls this whenever a setting changes (savePrefs).
  data.saved = refresh;

  sharedView.listeners.clear();
  sharedView.listeners.add(() => { panel.draw(); changed(); });
  // The first draw (once the panel has a size) fits the view.
  new ResizeObserver(() => changed()).observe(panel.stage);

  // Looks: "top", "side-a", "side-b" or an axis ("a", ..., "z"; "-c" from
  // the other side), as on the structure page.
  const hasCellAxis = (s, k) => norm(s.cell[k]) > 1e-8;
  function setView(name, animate = true) {
    const s = frames[index];
    const opposite = typeof name === "string" && name.startsWith("-");
    const axis = opposite ? name.slice(1) : name;
    let R;
    if (["top", "side-a", "side-b"].includes(axis)) R = presetRotation(s, axis);
    else if (["x", "y", "z"].includes(axis) || (["a", "b", "c"].includes(axis) && hasCellAxis(s, "abc".indexOf(axis)))) R = axisRotation(s, axis, opposite);
    else return;
    if (animate) animateView(R);
    else { sharedView.R = R; viewChanged(); }
  }
  function fit() {
    panel.fit();
    viewChanged();
  }

  // ------------------------------------------------------------ toolbar

  const button = (label, title, onclick, cls = "") => el("button", { type: "button", class: `small ${cls}`.trim(), title, "aria-label": title, onclick }, label);
  const group = (...children) => el("span", { class: "group" }, ...children);
  // A checkbox for viewerPrefs[key] (or viewerPrefs[key][sub]).
  function check(label, key, title, sub = null) {
    const read = () => (sub ? viewerPrefs[key][sub] : viewerPrefs[key]);
    const input = el("input", { type: "checkbox", onchange: () => {
      if (sub) viewerPrefs[key][sub] = input.checked; else viewerPrefs[key] = input.checked;
      savePrefs();
    } });
    syncs.push(() => { input.checked = read(); });
    return el("label", { class: "check", title }, input, label);
  }
  // A slider for viewerPrefs.appearance[key] (opacities and others).
  const percent = (value) => `${Math.round(value * 100)}%`;
  function appearanceSlider(label, key, { min = 0, max = 1, step = 0.05, format = percent } = {}) {
    const output = el("output", { class: "muted" });
    const show = () => { output.textContent = format(Number(viewerPrefs.appearance[key])); };
    const input = el("input", { type: "range", min, max, step, "aria-label": label,
      oninput: () => { viewerPrefs.appearance[key] = Number(input.value); show(); savePrefs(); } });
    syncs.push(() => { input.value = viewerPrefs.appearance[key]; show(); });
    return field(label, el("span", { class: "inline-fields" }, input, output));
  }

  // Frames: step, slider, number, play.
  let player = 0;
  const playButton = button("▶", "Play the frames", () => (player ? stop() : play()), "play");
  function play() {
    if (frames.length < 2) return;
    if (index === frames.length - 1) showFrame(0);
    playButton.textContent = "⏸";
    playButton.title = "Pause";
    const fps = Math.max(1, Math.min(60, Number(viewerPrefs.player.fps) || 10));
    player = setInterval(() => {
      if (index + 1 < frames.length) showFrame(index + 1);
      else if (viewerPrefs.player.loop) showFrame(0);
      else stop();
    }, 1000 / fps);
  }
  function stop() {
    clearInterval(player);
    player = 0;
    playButton.textContent = "▶";
    playButton.title = "Play the frames";
  }
  const step = (delta) => { stop(); showFrame(index + delta); };
  if (frames.length > 1) {
    const slider = el("input", { type: "range", class: "frame-slider", min: 0, max: frames.length - 1, step: 1, "aria-label": "Frame",
      oninput: () => { stop(); showFrame(Number(slider.value)); } });
    const number = el("input", { type: "number", class: "num-input frame-number", min: 0, max: frames.length - 1, step: 1, "aria-label": "Frame number",
      onchange: () => { stop(); showFrame(Number(number.value)); } });
    syncs.push(() => { slider.value = index; number.value = index; });
    bar.append(group(button("◀", "Previous frame (←)", () => step(-1)), slider, button("▶", "Next frame (→)", () => step(1)),
      number, el("span", { class: "muted" }, `/ ${frames.length - 1}`), playButton));
  }

  const anyPeriodic = frames.some((f) => f.pbc.some(Boolean));
  const atomSize = el("input", { type: "range", min: 0.3, max: MAX_ATOM_SCALE, step: 0.05, "aria-label": "Atom size",
    oninput: () => { viewerPrefs.appearance.atomScale = Number(atomSize.value); savePrefs(); } });
  syncs.push(() => { atomSize.value = viewerPrefs.appearance.atomScale; });
  const viewSelect = el("select", { "aria-label": "View along", title: "Look along a direction",
    onchange: () => { setView(viewSelect.value); viewSelect.value = ""; } },
  el("option", { value: "" }, "View…"),
  [["top", "Top"], ["side-a", "Side (a)"], ["side-b", "Side (b)"], ["a", "Along a"], ["b", "Along b"], ["c", "Along c"],
    ["x", "Along x"], ["y", "Along y"], ["z", "Along z"]].map(([value, label]) => el("option", { value }, label)));
  // Colour: element colours, or the property chosen under ⚙ › Colour atoms.
  const colourSelect = el("select", { "aria-label": "Colour atoms by", title: "Colour atoms by element or by a per-atom property (⚙ for which)",
    onchange: () => { viewerPrefs.colour = colourSelect.value; savePrefs(); } },
  el("option", { value: "element" }, "Elements"), el("option", { value: "property" }, "Property"));
  syncs.push(() => { colourSelect.value = colouring() ? "property" : "element"; });
  const measureButton = button("📏", "Measure distances, angles and dihedrals", () => {
    measureBox.hidden = !measureBox.hidden;
    measureButton.classList.toggle("active", !measureBox.hidden);
  });
  const settingsButton = button("⚙", "More settings", () => {
    settingsBox.hidden = !settingsBox.hidden;
    settingsButton.classList.toggle("active", !settingsBox.hidden);
  });
  bar.append(
    group(check("Cell", "cell", "Unit cell outline"), check("Bonds", "bonds", "Bonds (ball and stick)"),
      anyPeriodic ? check("Wrap", "wrap", "Draw every atom inside the cell") : null,
      vectorChoices.length ? check("Arrows", "arrows", "Force arrows (per-atom vectors; ⚙ for their style)", "show") : null),
    el("label", { class: "group", title: "Atom size (automatic radii)" }, "Size", atomSize),
    el("label", { class: "group" }, "Colour", colourSelect),
    group(viewSelect, button("Fit", "Fit the structure into the panel", fit)),
    el("span", { class: "spacer" }),
    group(button("Save SVG", "Save the view as an SVG (vector) image", saveSvg),
      button("⧉", "Open this view in a new browser tab", popOut), measureButton, settingsButton));

  function saveSvg() {
    if (!panel.scene) return;
    downloadText(`${fileStem()}.svg`, panelsToSvg([panel], exportOptions()), "image/svg+xml");
  }

  // ------------------------------------------------------------ settings box

  const field = (label, control, title) => el("label", { class: "field", title }, el("span", { class: "field-label" }, label), control);
  const fieldset = (legend, ...children) => el("fieldset", {}, el("legend", {}, legend), ...children);
  function choice(label, options, read, write) {
    const select = el("select", { "aria-label": label, onchange: () => { write(select.value); savePrefs(); } },
      options.map(([value, text]) => el("option", { value }, text)));
    syncs.push(() => { select.value = read(); });
    return field(label, select);
  }
  // Repeat along the periodic axes of the shown frame.
  const repeatInputs = [0, 1, 2].map((k) => {
    const input = el("input", { type: "number", class: "num-input", min: 1, max: MAX_REPEAT, step: 1, "aria-label": `Repeat ${"abc"[k]}`,
      onchange: () => { viewerPrefs.repeat[k] = clampRepeat(input.value); savePrefs(); } });
    syncs.push(() => { input.value = viewerPrefs.repeat[k]; input.disabled = !frames[index].pbc[k]; });
    return input;
  });
  // Panel size in pixels (also the size of saved images); blank: automatic.
  const sizeInput = (key) => {
    const input = el("input", { type: "number", class: "num-input", min: 160, max: 4000, step: 10, placeholder: "auto", "aria-label": `Panel ${key}`,
      onchange: () => {
        const value = optionalNumber(input.value);
        viewerPrefs.panelSize = { ...viewerPrefs.panelSize, [key]: value === null ? null : Math.max(160, Math.min(4000, Math.round(value))) };
        savePrefs();
      } });
    syncs.push(() => { input.value = viewerPrefs.panelSize[key] ?? ""; });
    return input;
  };
  const settingsInput = el("input", { type: "file", accept: ".json,application/json", hidden: true, "aria-label": "Settings file" });
  settingsInput.addEventListener("change", async () => {
    const file = settingsInput.files[0];
    settingsInput.value = "";
    if (!file) return;
    let parsed;
    try { parsed = JSON.parse(await file.text()); } catch { parsed = null; }
    if (!parsed || parsed.stoms_viewer_settings !== 1 || typeof parsed.settings !== "object") {
      window.alert(`${file.name} is not a STOMS viewer settings file.`);
      return;
    }
    replacePrefs(fillCutoffs(normalizePrefs(parsed.settings)));
    if (parsed.view) applyCamera(parsed.view);
    if (Array.isArray(parsed.measurements)) measureState.items = validMeasurements(parsed.measurements);
    syncExternal();
    refresh();
  });
  // Slice, element styles, bond cutoffs, polyhedron centres and planes: the
  // structure page's controls (see createSliceTable and the others). They
  // save the settings themselves, which redraws (data.saved).
  function structureSettings() {
    const redraw = () => {};
    const shownBoxes = createElementBoxes("hiddenElements", species, redraw, "Show");
    const sliceTable = createSliceTable("slice", redraw);
    externals.push(() => syncSliceControls("slice", "hiddenElements", sliceTable, shownBoxes, species));
    // Element colours also colour the swatches.
    const swatches = () => document.querySelectorAll(".swatch[data-element]").forEach((swatch) => {
      swatch.style.background = elementColor(swatch.dataset.element);
    });
    const styles = createElementStyles(species, { onColour: swatches, onRadius: redraw });
    const cutoffs = createCutoffControls(species, redraw);
    const centres = createCentreControls(species, redraw);
    const planes = createPlaneControls(() => frames[index].cell, redraw);
    externals.push(() => { styles.refresh(); swatches(); }, cutoffs.refresh, centres.refresh, planes.refresh);
    const anyMetal = species.some((s) => !NONMETALS.has(s));
    return [
      fieldset("Slice",
        field("Shown elements", shownBoxes),
        el("span", { class: "field-label" }, "Fractional coordinates"), sliceTable,
        el("div", { class: "button-row" }, button("Show all", "Show every element and the whole cell", () => {
          resetSliceControls("slice", "hiddenElements", sliceTable, shownBoxes, species);
        }))),
      fieldset("Elements",
        el("table", { class: "stats cutoffs radii" },
          el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "colour"), el("th", {}, "radius (Å)"), el("th", {}, ""))),
          styles.element),
        el("p", { class: "muted hint" }, "Blank radius: automatic (Size scales it)."),
        el("details", {}, el("summary", {}, "Bond cutoffs"), cutoffs.element,
          button("Reset cutoffs", "Default cutoffs (1.15 × covalent radii; none between metals)", cutoffs.reset)),
        anyMetal ? el("details", {}, el("summary", {}, "Polyhedron centres"), centres.element) : null),
      fieldset("Planes", planes.element, appearanceSlider("Plane opacity", "planeAlpha")),
    ];
  }
  // Colour atoms: the structure page's property and colour map controls.
  function colourSettings() {
    const properties = createPropertyControls(colourOptions, () => {});
    const palette = createPaletteControls(() => refresh());
    const mode = el("select", { "aria-label": "Colour mode", onchange: () => { viewerPrefs.colour = mode.value; savePrefs(); } },
      el("option", { value: "element" }, "Element colours"), el("option", { value: "property" }, "Atomic property"));
    syncs.push(() => {
      mode.value = colouring() ? "property" : "element";
      properties.element.hidden = !colouring();
      properties.refresh();
      palette.refresh();
    });
    return fieldset("Colour atoms", field("Colour by", mode), properties.element, palette.element);
  }
  // Arrows: which vectors, their length (Å per unit, or Auto), width, the
  // smallest drawn, and colour (blank: the text colour).
  function arrowSettings() {
    const number = (label, key, { min = 0, step = "any" } = {}) => {
      const input = el("input", { type: "number", min, step, class: "num-input", "aria-label": label,
        onchange: () => {
          const value = Number(input.value);
          if (key === "minMagnitude") viewerPrefs.arrows.minMagnitude = value > 0 ? value : 0;
          else if (value > 0) viewerPrefs.arrows[key] = value;
          savePrefs();
        } });
      syncs.push(() => { input.value = viewerPrefs.arrows[key]; });
      return input;
    };
    const vectorSelect = el("select", { "aria-label": "Arrow vectors", onchange: () => {
      const v = vectorChoices[Number(vectorSelect.value)];
      viewerPrefs.forceChoice = { source: v.source, name: v.name }; savePrefs();
    } }, vectorChoices.map((v, k) => el("option", { value: k }, `${v.name}${v.unit ? ` (${v.unit})` : ""}${v.source === "calculator" ? "" : ` · ${v.source}`}`)));
    syncs.push(() => { vectorSelect.value = String(Math.max(0, vectorChoices.indexOf(chosenVector()))); });
    const colour = el("input", { type: "color", "aria-label": "Arrow colour", oninput: () => { viewerPrefs.arrows.colour = colour.value; savePrefs(); } });
    syncs.push(() => { colour.value = viewerPrefs.arrows.colour ?? themeTextColour(); });
    return fieldset("Arrows",
      check("Show arrows", "arrows", "Arrows of the per-atom vectors", "show"),
      vectorChoices.length > 1 ? field("Vectors", vectorSelect) : null,
      field("Length (Å per unit)", el("span", { class: "inline-fields" }, number("Arrow length scale", "scale"),
        button("Auto", "Largest vector of all frames → 1.5 Å arrow", () => {
          const scale = autoArrowScale();
          if (scale) { viewerPrefs.arrows.scale = scale; savePrefs(); }
        }))),
      field("Width (Å)", number("Arrow width", "width", { min: 0.01, step: 0.01 })),
      field("Hide below", number("Smallest vector drawn", "minMagnitude")),
      field("Colour", el("span", { class: "inline-fields" }, colour,
        button("Theme", "The page's text colour", () => { viewerPrefs.arrows.colour = null; savePrefs(); }))));
  }
  // Cell outline: width, colour (null = the theme's) and line style.
  function cellSettings() {
    const themeCell = () => themeColours(panel.stage).cell;
    const colour = el("input", { type: "color", "aria-label": "Cell outline colour",
      oninput: () => { viewerPrefs.appearance.cellColour = colour.value; savePrefs(); } });
    syncs.push(() => { colour.value = viewerPrefs.appearance.cellColour ?? themeCell(); });
    return [
      appearanceSlider("Cell outline width", "cellWidth", { min: 0.5, max: MAX_CELL_WIDTH, step: 0.5, format: (value) => `${value} px` }),
      field("Cell outline colour", el("span", { class: "inline-fields" }, colour,
        button("Theme", "The theme's cell colour", () => { viewerPrefs.appearance.cellColour = null; savePrefs(); }))),
      choice("Cell outline style", Object.keys(CELL_DASHES).map((value) => [value, value]),
        () => viewerPrefs.appearance.cellDash, (value) => { viewerPrefs.appearance.cellDash = value; }),
    ];
  }
  const settingsFile = () => ({ stoms_viewer_settings: 1, settings: viewerPrefs, view: cameraState(), measurements: measureState.items });
  // Optional sections are null (no arrows without vectors).
  settingsBox.append(...[
    fieldset("Structure",
      anyPeriodic ? field("Repeat a × b × c", el("span", { class: "inline-fields" }, ...repeatInputs)) : null,
      ...cellSettings(),
      choice("Atom labels", [["off", "none"], ["index", "index"], ["element", "element"], ["element-index", "element + index"]],
        () => viewerPrefs.labels, (value) => { viewerPrefs.labels = value; }),
      check("Coordination polyhedra", "polyhedra", "Polyhedra around transition-metal atoms"),
      appearanceSlider("Polyhedra opacity", "polyAlpha"),
      appearanceSlider("Bond radius", "bondRadius", { min: 0.02, max: 0.4, step: 0.01, format: (value) => `${value.toFixed(2)} Å` }),
      check("Depth cueing", "appearance", "Fade atoms towards the back", "depthCue"),
      appearanceSlider("Depth fade at the back", "depthStrength", { min: 0.1, max: 0.9 })),
    colourSettings(),
    ...structureSettings(),
    vectorChoices.length ? arrowSettings() : null,
    fieldset("Axes and images",
      choice("Axes", [["abc", "cell a, b, c"], ["xyz", "x, y, z"], ["both", "both"], ["off", "none"]],
        () => viewerPrefs.tripod.axes, (value) => { viewerPrefs.tripod.axes = value; }),
      check("Axes in saved images", "tripod", "Draw the axes in saved SVG images", "export"),
      check("Transparent background", "svgTransparent", "Saved SVG images without a background, in light colours"),
      field("Panel width × height (px)", el("span", { class: "inline-fields" }, sizeInput("width"), sizeInput("height")),
        "Also the size of saved images; blank: automatic")),
    fieldset("Settings",
      el("div", { class: "button-row" },
        button("Export", "Save these settings and the view to a file", () => {
          downloadText("stoms-viewer-settings.json", `${JSON.stringify(settingsFile(), null, 2)}\n`, "application/json");
        }),
        button("Import", "Load settings from a file (also from the ledger viewer)", () => settingsInput.click()), settingsInput,
        button("Save HTML", "Save this viewer as a standalone HTML file", () => {
          downloadText(`${fileStem()}.html`, standaloneDocument(), "text/html");
        }),
        button("Reset view", "Top view, fitted", () => {
          Object.assign(sharedView, { R: presetRotation(frames[index], "top"), scale: null, pan: [0, 0] });
          viewChanged();
        })))].filter(Boolean));

  // ------------------------------------------------------------ pop-out

  const scriptJson = (value) => JSON.stringify(value).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  // This page as loaded, with the current frame, settings and view; not
  // linked to the notebook.
  function standaloneDocument() {
    const doc = new DOMParser().parseFromString(pristine, "text/html");
    const state = { ...data, frame: index, settings: viewerPrefs, camera: cameraState(), bridge: false, api: Object.fromEntries(replies),
      measurements: measureState.items };
    doc.getElementById("stoms-data").textContent = scriptJson(state);
    return `<!doctype html>\n${doc.documentElement.outerHTML}`;
  }
  function popOut() {
    // Not revoked: the tab may be reloaded.
    const url = URL.createObjectURL(new Blob([standaloneDocument()], { type: "text/html" }));
    if (!window.open(url, "_blank")) {
      status.textContent = "The browser did not open a new tab (pop-ups blocked?); ⚙ › Save HTML saves the viewer as a file instead.";
    }
  }

  // ------------------------------------------------------------ keys and messages

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && measure.cancel()) { event.preventDefault(); return; }
    if (event.target.closest?.("input, select, textarea") || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "ArrowLeft" && frames.length > 1) { step(-1); event.preventDefault(); }
    else if (event.key === "ArrowRight" && frames.length > 1) { step(1); event.preventDefault(); }
  });

  if (bridge) {
    window.addEventListener("message", (event) => {
      const m = event.data;
      if (event.source !== window.parent || !m || !m.stoms) return;
      if (m.type === "view") setView(m.name, false);
      else if (m.type === "api") replied(m);
      else if (m.type === "state") {
        if (m.settings && typeof m.settings === "object") {
          const next = fillCutoffs(normalizePrefs(m.settings));
          if (JSON.stringify(next) !== JSON.stringify(viewerPrefs)) { replacePrefs(next); syncExternal(); }
        }
        if (m.camera && typeof m.camera === "object" && JSON.stringify(m.camera) !== JSON.stringify(cameraState())) applyCamera(m.camera);
        if (m.frame !== undefined && m.frame !== null) { stop(); index = clampFrame(m.frame); }
        // Draw now, so the snapshot of this state follows at once.
        applySize();
        showFrame(index);
      }
    });
  }
  if (framed) {
    new ResizeObserver(() => post({ type: "size", height: Math.ceil(document.documentElement.getBoundingClientRect().height) }))
      .observe(document.body);
  }

  // ------------------------------------------------------------ vibrations

  // A structure with modes (stoms.viewer.view_phonons): the structure page's
  // vibration panel, and with phonons its band structure and DOS.
  async function showVibrations() {
    const s = frames[index];
    if (!s.has_modes) return;
    document.body.classList.toggle("has-phonons", Boolean(s.has_phonons));
    vibrationBox.hidden = false;
    vibrationBox.replaceChildren(el("h3", {}, "Vibrations"), el("p", { class: "muted" }, "Loading the modes…"));
    let modes;
    try {
      modes = await api(`structures/${encodeURIComponent(s.id)}/modes`);
    } catch (error) {
      modes = { error: error.message };
    }
    const vibration = createVibrationPanel({ structure: s, modes, figures, panel: () => panel, disposed: () => false, repeatChanged: sync });
    vibrationBox.replaceChildren(el("h3", {}, "Vibrations"), el("div", { class: "embed-vibration-controls" }, ...vibration.controls));
  }

  applySize();
  showFrame(index);
  showVibrations();
  if (bridge) post({ type: "ready" });
})();
