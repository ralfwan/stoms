"use strict";

// Structure viewer page (#/structures/<id>?from=<aggregation>&compare=<id>&cycle=<tags|aggregation>&forces=<spec hash>).
//
// One scene model (repeated cell, periodic bonds, coordination polyhedra,
// per-atom colours) feeds a dependency-free 2D canvas renderer; panels share
// one view state.
// Uses el, api, setMain, idCell, formatNumber, formatDate, treeCard and state
// from app.js.

// ---------------------------------------------------------------- elements

// Element colours: Jmol, https://jmol.sourceforge.net/jscolors/#Atoms
// Covalent radii (Angstrom): B. Cordero et al., "Covalent radii revisited",
// Dalton Trans. (2008) 2832-2838, https://doi.org/10.1039/B801115J
const ELEMENTS = {
  H: ["#ffffff", 0.31], He: ["#d9ffff", 0.28], Li: ["#cc80ff", 1.28], Be: ["#c2ff00", 0.96],
  B: ["#ffb5b5", 0.84], C: ["#909090", 0.76], N: ["#3050f8", 0.71], O: ["#ff0d0d", 0.66],
  F: ["#90e050", 0.57], Ne: ["#b3e3f5", 0.58], Na: ["#ab5cf2", 1.66], Mg: ["#8aff00", 1.41],
  Al: ["#bfa6a6", 1.21], Si: ["#f0c8a0", 1.11], P: ["#ff8000", 1.07], S: ["#ffff30", 1.05],
  Cl: ["#1ff01f", 1.02], Ar: ["#80d1e3", 1.06], K: ["#8f40d4", 2.03], Ca: ["#3dff00", 1.76],
  Sc: ["#e6e6e6", 1.70], Ti: ["#bfc2c7", 1.60], V: ["#a6a6ab", 1.53], Cr: ["#8a99c7", 1.39],
  Mn: ["#9c7ac7", 1.39], Fe: ["#e06633", 1.32], Co: ["#f090a0", 1.26], Ni: ["#50d050", 1.24],
  Cu: ["#c88033", 1.32], Zn: ["#7d80b0", 1.22], Ga: ["#c28f8f", 1.22], Ge: ["#668f8f", 1.20],
  As: ["#bd80e3", 1.19], Se: ["#ffa100", 1.20], Br: ["#a62929", 1.20], Kr: ["#5cb8d1", 1.16],
  Rb: ["#702eb0", 2.20], Sr: ["#00ff00", 1.95], Y: ["#94ffff", 1.90], Zr: ["#94e0e0", 1.75],
  Nb: ["#73c2c9", 1.64], Mo: ["#54b5b5", 1.54], Ru: ["#248f8f", 1.46], Rh: ["#0a7d8c", 1.42],
  Pd: ["#006985", 1.39], Ag: ["#c0c0c0", 1.45], Cd: ["#ffd98f", 1.44], In: ["#a67573", 1.42],
  Sn: ["#668080", 1.39], Sb: ["#9e63b5", 1.39], Te: ["#d47a00", 1.38], I: ["#940094", 1.39],
  Xe: ["#429eb0", 1.40], Cs: ["#57178f", 2.44], Ba: ["#00c900", 2.15], La: ["#70d4ff", 2.07],
  Hf: ["#4dc2ff", 1.75], Ta: ["#4da6ff", 1.70], W: ["#2194d6", 1.62], Re: ["#267dab", 1.51],
  Os: ["#266696", 1.44], Ir: ["#175487", 1.41], Pt: ["#d0d0e0", 1.36], Au: ["#ffd123", 1.36],
  Hg: ["#b8b8d0", 1.32], Pb: ["#575961", 1.46], Bi: ["#9e4fb5", 1.48],
};
const NONMETALS = new Set(["H", "He", "B", "C", "N", "O", "F", "Ne", "Si", "P", "S", "Cl", "Ar",
  "Ge", "As", "Se", "Br", "Kr", "Sb", "Te", "I", "Xe"]);
const TRANSITION_METALS = new Set(["Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
  "Y", "Zr", "Nb", "Mo", "Ru", "Rh", "Pd", "Ag", "Cd", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg"]);

const defaultElementColor = (symbol) => (ELEMENTS[symbol] ?? ["#ff1493", 1.5])[0];
// The colour chosen under Appearance, else the default (spheres, bonds, polyhedra).
const elementColor = (symbol) => viewerPrefs.appearance.colours[symbol] ?? defaultElementColor(symbol);
// Swatches name their element, so they follow colour changes (data-element).
const elementSwatch = (symbol) => el("i", { class: "swatch", "data-element": symbol, style: `background:${elementColor(symbol)}` });
const covalentRadius = (symbol) => (ELEMENTS[symbol] ?? ["#ff1493", 1.5])[1];
// Tags shown in panel captions (e.g. role:founder / role:winner / role:relaxed_winner).
const CAPTION_TAG_PREFIX = "role:";
const iterationOf = (tags) => {
  const found = tags.filter((t) => t.startsWith("iteration:"));
  return found.length === 1 ? found[0].slice("iteration:".length) || null : null;
};
const panelCaption = (s) => [
  ...(s.file ? [`${s.file} · `] : []),
  ...s.tags.filter((t) => t.startsWith(CAPTION_TAG_PREFIX)).map((t) => `${t} · `),
  `${s.formula} (`, el("code", {}, s.id), ")",
];
const pairKey = (a, b) => (a < b ? `${a}-${b}` : `${b}-${a}`);

function defaultCutoff(a, b) {
  if (!NONMETALS.has(a) && !NONMETALS.has(b)) return 0; // no metal-metal bonds by default
  return Math.round((covalentRadius(a) + covalentRadius(b)) * 1.15 * 100) / 100;
}

// ---------------------------------------------------------------- vectors & colours

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const n = norm(a) || 1; return [a[0] / n, a[1] / n, a[2] / n]; };

function hexToRgb(hex) {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}
const rgbToHex = (rgb) => `#${rgb.map((c) => Math.round(Math.max(0, Math.min(255, c))).toString(16).padStart(2, "0")).join("")}`;
const mix = (a, b, t) => rgbToHex(hexToRgb(a).map((c, i) => c + (hexToRgb(b)[i] - c) * t));

// Palettes for the value colourings, low to high. Single-hue ramps run light
// to dark; viridis and cividis (perceptually uniform, readable with
// colour-vision deficiencies) run dark to light. Lightness is monotonic in all
// but the diverging one, which is light in the middle (for signed values such
// as charges or magnetic moments, best with a range symmetric around 0).
const PALETTES = {
  blue: { label: "Blue", stops: ["#dceafb", "#6c9fdf", "#123f7a"] },
  green: { label: "Green", stops: ["#e2f3ea", "#4fae84", "#0d5a3a"] },
  orange: { label: "Orange", stops: ["#fde8d8", "#ee8a4c", "#8c2a06"] },
  purple: { label: "Purple", stops: ["#ece6f8", "#8f74d2", "#36206e"] },
  grey: { label: "Grey", stops: ["#ededeb", "#8d8c88", "#2c2c2a"] },
  viridis: { label: "Viridis", stops: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"] },
  cividis: { label: "Cividis", stops: ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"] },
  plasma: { label: "Plasma", stops: ["#0d0887", "#6a00a8", "#b12a90", "#e16462", "#fca636", "#f0f921"] },
  inferno: { label: "Inferno", stops: ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"] },
  magma: { label: "Magma", stops: ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"] },
  turbo: { label: "Rainbow (turbo)", stops: ["#30123b", "#4686fb", "#1ae4b6", "#a2fc3c", "#fabb39", "#e4460a", "#7a0403"] },
  diverging: { label: "Blue–red (diverging)", stops: ["#2b59a8", "#8fb3e0", "#eeeeec", "#eb9a80", "#b2282c"] },
  // Its stops are viewerPrefs.customPalette (low, high).
  custom: { label: "Custom (two colours)", stops: null },
};
const DEFAULT_CUSTOM_PALETTE = ["#f2f0e9", "#8c1d40"];
// Palette per colour mode (height, force magnitude, force difference, atomic property).
const DEFAULT_PALETTES = { height: "blue", force: "green", error: "orange", property: "viridis" };
const stopsOf = (key) => (key === "custom" ? viewerPrefs.customPalette : PALETTES[key]?.stops);
const paletteStops = (mode) => stopsOf(viewerPrefs.palettes[mode]) ?? PALETTES[DEFAULT_PALETTES[mode]].stops;
// Colour at t in [0, 1] along a palette's stops.
function rampColour(stops, t) {
  const x = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  return mix(stops[i], stops[i + 1], x - i);
}
const ramp = (mode, t) => rampColour(paletteStops(mode), t);

// ---------------------------------------------------------------- preferences & shared view

// Depth cueing (off by default): items further back fade towards the
// background, up to depthStrength at the back.
const DEFAULT_APPEARANCE = { polyAlpha: 0.45, polyEdges: true, planeAlpha: 0.2, bondRadius: 0.08, depthCue: false, depthStrength: 0.6,
  radii: {}, colours: {} };
// Per-element radii and colours are objects of their own in every appearance.
const freshAppearance = () => ({ ...DEFAULT_APPEARANCE, radii: {}, colours: {} });
// Force arrows: length scale in Angstrom per force unit, shaft radius in
// Angstrom, colour (null = text colour of the theme), hidden below minMagnitude.
const DEFAULT_ARROWS = { show: false, scale: 1, width: 0.04, colour: null, minMagnitude: 0 };
const emptySlice = () => [[null, null], [null, null], [null, null]];
// Movie playback: frames per second and whether it starts over at the end.
const DEFAULT_PLAYER = { fps: 10, loop: true };
// Axis tripod in the bottom-left corner: "abc" (cell vectors), "xyz"
// (Cartesian), "both" or "off"; `export` also draws it in saved images.
const DEFAULT_TRIPOD = { axes: "abc", export: true };
// Colour by an atomic property: the chosen property (see propertyOptions), how
// to read its values ("auto", "continuous", "categories"), the component of a
// vector ("norm", "x", "y", "z"), and the colour range (null = automatic;
// `symmetric` centres an automatic range on 0).
const DEFAULT_PROPERTY = { choice: null, component: "norm", kind: "auto", min: null, max: null, symmetric: false };
// Rings (see loadRings). `method` is "planar" or "shortest-path" (rings up to
// `searchSize` atoms); `elements` holds per element { use, zmin, zmax }
// (missing: used, no height window); `cutoffs` per element pair (missing: the
// bond cutoff); `count` gives the ring size: "auto" (pairs when every bond
// joins two elements, else atoms), "pairs", "all", or an element; `scheme`
// colours sizes as "categories" (RING_COLOURS) or along a palette; `colours`
// per ring size replace the scheme's; `labelScale` sizes the ring labels.
const DEFAULT_RINGS = { show: false, method: "planar", searchSize: 12, elements: {}, cutoffs: {}, alternating: false, count: "auto", enclosed: true,
  minSize: null, maxSize: null, alpha: 0.5, outline: true, labels: false, labelScale: 1, scheme: "categories", colours: {} };
const freshRings = () => ({ ...DEFAULT_RINGS, elements: {}, cutoffs: {}, colours: {} });

// Settings saved before version 2 counted ring sizes in all ring atoms.
const PREFS_VERSION = 2;
// Vibrational modes: largest displacement (Angstrom), seconds per period
// whatever the frequency, arrows along the mode, bonds while vibrating
// ("fixed": the equilibrium bonds, "live": recomputed every frame) and the
// frequency unit ("THz" or "cm-1"). A recorded video holds recordPeriods
// periods, at videoSize ("shown": the panel as on screen, or a key of
// VIDEO_SIZES) and videoFps frames per second. The phonon plot sits below
// the structure, or beside it with plotSide; plotWidth and plotHeight (px,
// null = automatic) are its size.
// Video frame sizes in pixels.
const VIDEO_SIZES = { "720p": [1280, 720], "1080p": [1920, 1080] };
// Set once a structure with modes has opened on the Vibrations tab.
let vibrationTabShown = false;
const DEFAULT_VIBRATION = { amplitude: 0.3, periodSeconds: 1, showArrows: false, bonds: "fixed", unit: "THz",
  recordPeriods: 2, videoSize: "shown", videoFps: "60", plotSide: false, plotWidth: null, plotHeight: null };

function defaultPrefs() {
  return { version: PREFS_VERSION, cell: true, bonds: false, polyhedra: false, colour: "element",
    repeat: [1, 1, 1], cutoffs: {}, polyCenters: null, prefix: "run:",
    slice: emptySlice(), hiddenElements: [], planes: [],
    appearance: freshAppearance(),
    tripod: { ...DEFAULT_TRIPOD },
    // Text on every shown atom: "off", "index", "element", "element-index" or
    // "value" (the value the atom is coloured by).
    labels: "off",
    property: { ...DEFAULT_PROPERTY },
    rings: freshRings(),
    // Saved PNG images: pixels per screen pixel.
    pngScale: 3,
    // Force atom selection follows the slice unless forceFollowsSlice is off.
    arrows: { ...DEFAULT_ARROWS }, forceFollowsSlice: true, forceSlice: emptySlice(), forceHiddenElements: [],
    // Last chosen force method ({ spec, method, name }) and force-difference
    // pair ([{ spec, method }, { spec, method }]); see matchMethod.
    forceChoice: null, pairChoice: null,
    palettes: { ...DEFAULT_PALETTES },
    customPalette: [...DEFAULT_CUSTOM_PALETTE],
    // Settings tab shown in the viewer, and the file format for saving a structure.
    tab: "view", saveFormat: "extxyz",
    // Structure panel size in pixels; null = automatic.
    panelSize: { width: null, height: null },
    player: { ...DEFAULT_PLAYER },
    vibration: { ...DEFAULT_VIBRATION },
    // Save SVG without a background, in light-theme colours (for any page).
    svgTransparent: true };
}

const MAX_REPEAT = 12;
// Above this many atoms, a note says that drawing may be slow.
const LARGE_SCENE = 3000;
const clampRepeat = (value) => Math.max(1, Math.min(MAX_REPEAT, Math.round(Number(value)) || 1));

// Settings from storage or an imported file, completed with defaults. Unknown
// keys are dropped, and values of the wrong kind fall back to the default.
// Colours as the colour inputs give them. Settings may come from a file
// someone else made, and colours end up in SVG markup: anything else is
// dropped.
const isColour = (value) => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
const onlyColours = (map) => Object.fromEntries(Object.entries(map ?? {}).filter(([, value]) => isColour(value)));

function normalizePrefs(raw) {
  const prefs = defaultPrefs();
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return prefs;
  const kind = (value) => (value === null ? "null" : Array.isArray(value) ? "array" : typeof value);
  for (const key of Object.keys(prefs)) {
    if (!(key in raw)) continue;
    const value = raw[key], fallback = prefs[key];
    // Nullable settings (polyCenters, forceChoice, pairChoice) take any kind.
    if (fallback === null || kind(value) === kind(fallback)) prefs[key] = value;
  }
  for (const [key, defaults] of [["appearance", DEFAULT_APPEARANCE], ["arrows", DEFAULT_ARROWS],
    ["palettes", DEFAULT_PALETTES], ["panelSize", { width: null, height: null }], ["player", DEFAULT_PLAYER],
    ["tripod", DEFAULT_TRIPOD], ["property", DEFAULT_PROPERTY], ["rings", DEFAULT_RINGS], ["vibration", DEFAULT_VIBRATION]]) {
    prefs[key] = { ...defaults, ...prefs[key] };
  }
  const vibration = prefs.vibration;
  if (!(vibration.amplitude > 0)) vibration.amplitude = DEFAULT_VIBRATION.amplitude;
  if (!(vibration.periodSeconds > 0)) vibration.periodSeconds = DEFAULT_VIBRATION.periodSeconds;
  if (!["fixed", "live"].includes(vibration.bonds)) vibration.bonds = DEFAULT_VIBRATION.bonds;
  if (!["THz", "cm-1"].includes(vibration.unit)) vibration.unit = DEFAULT_VIBRATION.unit;
  if (!(Number.isInteger(vibration.recordPeriods) && vibration.recordPeriods >= 1)) vibration.recordPeriods = DEFAULT_VIBRATION.recordPeriods;
  if (vibration.videoSize !== "shown" && !Object.hasOwn(VIDEO_SIZES, vibration.videoSize)) vibration.videoSize = DEFAULT_VIBRATION.videoSize;
  if (!["30", "60"].includes(vibration.videoFps)) vibration.videoFps = DEFAULT_VIBRATION.videoFps;
  vibration.plotSide = vibration.plotSide === true;
  for (const key of ["plotWidth", "plotHeight"]) {
    if (!(Number.isFinite(vibration[key]) && vibration[key] >= 160 && vibration[key] <= 4000)) vibration[key] = null;
  }
  prefs.appearance.radii = { ...prefs.appearance.radii };
  prefs.appearance.colours = onlyColours(prefs.appearance.colours);
  for (const key of ["elements", "cutoffs", "colours"]) prefs.rings[key] = { ...prefs.rings[key] };
  prefs.rings.colours = onlyColours(prefs.rings.colours);
  if (!isColour(prefs.arrows.colour)) prefs.arrows.colour = null;
  if (!(Array.isArray(prefs.customPalette) && prefs.customPalette.length === 2 && prefs.customPalette.every(isColour))) {
    prefs.customPalette = [...DEFAULT_CUSTOM_PALETTE];
  }
  prefs.planes = prefs.planes.filter((plane) => plane && typeof plane === "object")
    .map((plane) => (isColour(plane.colour) ? plane : { ...plane, colour: undefined }));
  if (!(raw.version >= 2) && prefs.rings.count === "all") prefs.rings.count = "auto";
  prefs.version = PREFS_VERSION;
  // Older settings repeat along a and b only: c gets 1.
  prefs.repeat = [0, 1, 2].map((k) => clampRepeat(prefs.repeat[k]));
  return prefs;
}

const viewerPrefs = (() => {
  try { return normalizePrefs(JSON.parse(localStorage.getItem("stoms.viewer") || "{}")); } catch { return defaultPrefs(); }
})();
function savePrefs() {
  try { localStorage.setItem("stoms.viewer", JSON.stringify(viewerPrefs)); } catch { /* storage unavailable */ }
}

// Rotation rows map world vectors to screen axes (x right, y up, z towards the viewer).
// It survives navigation so stepping through structures keeps the orientation.
const sharedView = { R: null, scale: null, pan: [0, 0], panelCount: 0, listeners: new Set() };
function viewChanged() { for (const listener of sharedView.listeners) listener(); }

function orthonormalize(R) {
  const x = unit(R[0]);
  const y = unit(sub(R[1], mul(x, dot(R[1], x))));
  return [x, y, cross(x, y)];
}

// Eigenvectors of a symmetric 3x3 matrix (cyclic Jacobi), largest eigenvalue first.
function symmetricEigenvectors(S) {
  const A = S.map((row) => [...row]);
  const V = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let sweep = 0; sweep < 50; sweep++) {
    if (Math.abs(A[0][1]) + Math.abs(A[0][2]) + Math.abs(A[1][2]) < 1e-12) break;
    for (const [p, q] of [[0, 1], [0, 2], [1, 2]]) {
      if (Math.abs(A[p][q]) < 1e-15) continue;
      const theta = (A[q][q] - A[p][p]) / (2 * A[p][q]);
      const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.hypot(theta, 1));
      const c = 1 / Math.hypot(t, 1), s = t * c;
      for (let k = 0; k < 3; k++) {
        const [akp, akq] = [A[k][p], A[k][q]];
        A[k][p] = c * akp - s * akq; A[k][q] = s * akp + c * akq;
      }
      for (let k = 0; k < 3; k++) {
        const [apk, aqk] = [A[p][k], A[q][k]];
        A[p][k] = c * apk - s * aqk; A[q][k] = s * apk + c * aqk;
      }
      for (let k = 0; k < 3; k++) {
        const [vkp, vkq] = [V[k][p], V[k][q]];
        V[k][p] = c * vkp - s * vkq; V[k][q] = s * vkp + c * vkq;
      }
    }
  }
  return [0, 1, 2].sort((i, j) => A[j][j] - A[i][i]).map((i) => [V[0][i], V[1][i], V[2][i]]);
}

// View frame [a, b, n]: in-plane directions and the surface normal. Without a
// usable cell (plain molecules) the principal axes of the positions stand in,
// so the top view looks onto the molecule's flattest side.
function viewFrame(structure) {
  const [ca, cb] = structure.cell;
  const normal = cross(ca, cb);
  if (norm(normal) > 1e-8 * (dot(ca, ca) + dot(cb, cb))) {
    const n = unit(normal);
    return [unit(ca), unit(sub(cb, mul(n, dot(cb, n)))), n];
  }
  const positions = structure.positions;
  const centre = mul(positions.reduce(add, [0, 0, 0]), 1 / (positions.length || 1));
  const S = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of positions) {
    const d = sub(p, centre);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) S[i][j] += d[i] * d[j];
  }
  const [a, b] = symmetricEigenvectors(S);
  return [a, b, cross(a, b)];
}

function surfaceNormal(structure) { return viewFrame(structure)[2]; }

function presetRotation(structure, preset) {
  const [a, b, n] = viewFrame(structure);
  if (preset === "side-a") return orthonormalize([b, n, cross(b, n)]);
  if (preset === "side-b") return orthonormalize([mul(a, -1), n, cross(mul(a, -1), n)]);
  return orthonormalize([a, cross(n, a), n]); // top: look down the surface normal
}

// R turned about a screen axis (x right, y up, z towards the viewer).
function rotated(R, axis, angle) {
  const c = Math.cos(angle), s = Math.sin(angle);
  const M = axis === "x" ? [[1, 0, 0], [0, c, -s], [0, s, c]]
    : axis === "y" ? [[c, 0, s], [0, 1, 0], [-s, 0, c]] : [[c, -s, 0], [s, c, 0], [0, 0, 1]];
  return orthonormalize(M.map((row) => [0, 1, 2].map((k) => row[0] * R[0][k] + row[1] * R[1][k] + row[2] * R[2][k])));
}
function rotateScreen(axis, angle) { sharedView.R = rotated(sharedView.R, axis, angle); }

// Axes of the tripod: cell vectors a, b, c and Cartesian x, y, z.
const AXIS_COLOURS = { a: "#d6403a", b: "#2f9e44", c: "#2a6fd6", x: "#d6403a", y: "#2f9e44", z: "#2a6fd6" };
function axisDirection(cell, name) {
  const k = "abcxyz".indexOf(name);
  return k < 3 ? unit(cell[k]) : [0, 1, 2].map((j) => (j === k - 3 ? 1 : 0));
}

// The view looking along an axis: the axis points at the viewer (away with
// `opposite`). Up is the surface normal for a and b (z for x and y); along c
// the a axis points right as in the top view, along z the x axis.
function axisRotation(structure, name, opposite = false) {
  const cell = structure.cell;
  const n = surfaceNormal(structure);
  const up = { a: n, b: n, c: cross(n, unit(cell[0])), x: [0, 0, 1], y: [0, 0, 1], z: [0, 1, 0] }[name];
  const z = mul(axisDirection(cell, name), opposite ? -1 : 1);
  let y = sub(up, mul(z, dot(up, z)));
  if (norm(y) < 1e-6) y = sub([0, 1, 0], mul(z, z[1])); // up along the axis: any perpendicular
  if (norm(y) < 1e-6) y = sub([1, 0, 0], mul(z, z[0]));
  y = unit(y);
  return [cross(y, z), y, z];
}

// Rotations as unit quaternions, for smooth turns between two views.
function quaternion(R) {
  const [[m00, m01, m02], [m10, m11, m12], [m20, m21, m22]] = R;
  const trace = m00 + m11 + m22;
  let q;
  if (trace > 0) { const s = 2 * Math.sqrt(trace + 1); q = [s / 4, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s]; }
  else if (m00 > m11 && m00 > m22) { const s = 2 * Math.sqrt(1 + m00 - m11 - m22); q = [(m21 - m12) / s, s / 4, (m01 + m10) / s, (m02 + m20) / s]; }
  else if (m11 > m22) { const s = 2 * Math.sqrt(1 + m11 - m00 - m22); q = [(m02 - m20) / s, (m01 + m10) / s, s / 4, (m12 + m21) / s]; }
  else { const s = 2 * Math.sqrt(1 + m22 - m00 - m11); q = [(m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, s / 4]; }
  return q;
}
function quaternionMatrix([w, x, y, z]) {
  return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
    [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
    [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]];
}
function slerp(p, q, t) {
  let d = p.reduce((m, v, i) => m + v * q[i], 0);
  if (d < 0) { q = q.map((v) => -v); d = -d; }
  if (d > 0.9995) return p.map((v, i) => v + (q[i] - v) * t);
  const angle = Math.acos(d), s = Math.sin(angle);
  return p.map((v, i) => (Math.sin((1 - t) * angle) * v + Math.sin(t * angle) * q[i]) / s);
}

// Turn the shared view to R over a quarter second (at once with reduced motion).
let viewAnimation = 0;
function animateView(R, onDone) {
  cancelAnimationFrame(viewAnimation);
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const from = quaternion(sharedView.R), to = quaternion(R), start = performance.now(), duration = 250;
  const frame = (now) => {
    const t = reduced ? 1 : Math.min(1, (now - start) / duration);
    const eased = t < 0.5 ? 2 * t * t : 1 - (2 - 2 * t) ** 2 / 2;
    sharedView.R = t < 1 ? orthonormalize(quaternionMatrix(slerp(from, to, eased))) : R;
    viewChanged();
    if (t < 1) viewAnimation = requestAnimationFrame(frame);
    else onDone?.();
  };
  viewAnimation = requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- crystallography

// Reciprocal vectors without 2*pi: fractional f_k = p . recip[k].
function reciprocal(cell) {
  const [a, b, c] = cell;
  const volume = dot(a, cross(b, c)) || 1;
  return [mul(cross(b, c), 1 / volume), mul(cross(c, a), 1 / volume), mul(cross(a, b), 1 / volume)];
}

const fractional = (recip, p) => [dot(p, recip[0]), dot(p, recip[1]), dot(p, recip[2])];

function planeNormal(cell, plane) {
  const [ra, rb, rc] = reciprocal(cell);
  return add(add(mul(ra, plane.h), mul(rb, plane.k)), mul(rc, plane.l));
}

function dSpacing(cell, plane) {
  const g = norm(planeNormal(cell, plane));
  return g ? 1 / g : null;
}

// Polygon where h*x + k*y + l*z = t (fractional) cuts the box [0,na]x[0,nb]x[0,nc].
function planePolygon(cell, plane, box) {
  const g = (f) => plane.h * f[0] + plane.k * f[1] + plane.l * f[2];
  const corners = [];
  for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) corners.push([i * box[0], j * box[1], k * box[2]]);
  const found = [];
  const pushUnique = (f) => { if (!found.some((q) => Math.abs(q[0] - f[0]) + Math.abs(q[1] - f[1]) + Math.abs(q[2] - f[2]) < 1e-6)) found.push(f); };
  for (let m = 0; m < 8; m++) for (let n = m + 1; n < 8; n++) {
    const p = corners[m], q = corners[n];
    if ([0, 1, 2].filter((k) => p[k] !== q[k]).length !== 1) continue; // only box edges
    const gp = g(p) - plane.t, gq = g(q) - plane.t;
    if (Math.abs(gp) < 1e-9) pushUnique(p);
    if (Math.abs(gq) < 1e-9) pushUnique(q);
    if (gp * gq < 0) pushUnique(add(p, mul(sub(q, p), gp / (gp - gq))));
  }
  if (found.length < 3) return null;
  const points = found.map((f) => add(add(mul(cell[0], f[0]), mul(cell[1], f[1])), mul(cell[2], f[2])));
  const normal = unit(planeNormal(cell, plane));
  const centre = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  const u = unit(sub(points[0], centre)), v = cross(normal, u);
  const angle = (p) => Math.atan2(dot(sub(p, centre), v), dot(sub(p, centre), u));
  points.sort((p, q) => angle(p) - angle(q));
  return { points, normal, centre };
}

// Categorical slots (validated reference palette) for plane identity; a
// plane's chosen colour replaces its slot's.
const PLANE_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7", "#008300", "#e34948"];
const planeColour = (plane, k) => plane.colour ?? PLANE_COLOURS[k % PLANE_COLOURS.length];

function inSlice(f, slice = viewerPrefs.slice) {
  return slice.every(([lo, hi], k) => (lo === null || f[k] >= lo - 1e-9) && (hi === null || f[k] <= hi + 1e-9));
}

// Atoms that get force arrows and count towards force colour scales: the
// sliced (shown) atoms, or the force selection's own elements and bounds.
function forceIncluded(structure) {
  const follow = viewerPrefs.forceFollowsSlice;
  const recip = reciprocal(structure.cell);
  const hidden = new Set(follow ? viewerPrefs.hiddenElements : viewerPrefs.forceHiddenElements);
  const bounds = follow ? viewerPrefs.slice : viewerPrefs.forceSlice;
  return structure.positions.map((p, i) => !hidden.has(structure.symbols[i]) && inSlice(fractional(recip, p), bounds));
}

// Sphere radius (Angstrom): per-element override, else scaled covalent radius.
function autoRadius(symbol) {
  const ballAndStick = viewerPrefs.bonds || viewerPrefs.polyhedra;
  return Math.max(0.18, covalentRadius(symbol) * (ballAndStick ? 0.33 : 0.5));
}
const atomRadius = (symbol) => viewerPrefs.appearance.radii[symbol] ?? autoRadius(symbol);

// ---------------------------------------------------------------- measurements

// Measurements name atoms by index and periodic image, so they apply to every
// structure with the same atoms: compared panels, movie frames, stepping.
//   atom ref: { index, image: [i, j, k], symbol, count } (count: atoms in the structure)
//   item:     { kind: "distance" | "angle" | "dihedral", atoms: [ref, ...] }
const MEASURE_ATOMS = { distance: 2, angle: 3, dihedral: 4 };
const measureState = { mode: "off", pending: [], items: [] };
// Atom colours: groups of atoms ({ colour, atoms: [ref] }) drawn in their own
// colour over any colour mode, by atom number like measurements. `selected`
// holds the atoms clicked in mode "select" for the next group; `colour` is the
// last colour applied.
const paintState = { selected: [], groups: [], colour: "#d6336c" };

// Only structures with the same atom count and elements: otherwise an index
// can name a different atom.
const fitsStructure = (structure, refs) =>
  refs.every((r) => r.count === structure.symbols.length && structure.symbols[r.index] === r.symbol);

function refPosition(structure, ref) {
  const [A, B, C] = structure.cell;
  const shift = add(add(mul(A, ref.image[0]), mul(B, ref.image[1])), mul(C, ref.image[2]));
  return add(structure.positions[ref.index], shift);
}

// Value of a measurement on one structure: distance in Angstrom (and the
// nearest periodic image's, if shorter), angle at the middle atom, dihedral.
function measureValue(structure, item) {
  const p = item.atoms.map((r) => refPosition(structure, r));
  if (item.kind === "distance") {
    const value = norm(sub(p[1], p[0]));
    let nearest = value;
    const [A, B, C] = structure.cell;
    const ranges = structure.pbc.map((periodic) => (periodic ? [-1, 0, 1] : [0]));
    // Nearest image of the second atom's original position.
    const base = structure.positions[item.atoms[1].index];
    const first = p[0];
    const frac = fractional(reciprocal(structure.cell), sub(first, base)).map((f, k) => (structure.pbc[k] ? Math.round(f) : 0));
    for (const i of ranges[0]) for (const j of ranges[1]) for (const k of ranges[2]) {
      const shift = add(add(mul(A, frac[0] + i), mul(B, frac[1] + j)), mul(C, frac[2] + k));
      nearest = Math.min(nearest, norm(sub(add(base, shift), first)));
    }
    return { value, nearest: nearest < value - 1e-3 ? nearest : null, text: `${value.toFixed(3)} Å` };
  }
  if (item.kind === "angle") {
    const u = sub(p[0], p[1]), v = sub(p[2], p[1]);
    const value = (Math.acos(Math.max(-1, Math.min(1, dot(u, v) / (norm(u) * norm(v) || 1)))) * 180) / Math.PI;
    return { value, text: `${value.toFixed(1)}°` };
  }
  const b1 = sub(p[1], p[0]), b2 = sub(p[2], p[1]), b3 = sub(p[3], p[2]);
  const value = (Math.atan2(norm(b2) * dot(b1, cross(b2, b3)), dot(cross(b1, b2), cross(b2, b3))) * 180) / Math.PI;
  return { value, text: `${value.toFixed(1)}°` };
}

// ---------------------------------------------------------------- rings

// Rings come from the server: stoms.analysis.find_rings, which describes its
// two methods ("planar": faces of a layer's network in the a-b plane;
// "shortest-path": any network, also 3D) and how sizes are counted. The viewer
// chooses the network: per element whether it takes part and a window of
// heights along the surface normal (as shown when hovering an atom), the
// cutoff per element pair (the ring's own, else the bond cutoff), and options.
const RING_COLOURS = ["#e34948", "#eda100", "#1baf7a", "#2a78d6", "#7a5bd1", "#e87ba4", "#eb6834", "#008300", "#00a3c4", "#8a6d3b"];
// A size's colour: chosen, else by the scheme; palettes span `range`
// ([smallest, largest] size, see ringSizeRange).
function ringColour(size, range) {
  const { colours, scheme } = viewerPrefs.rings;
  if (colours[size]) return colours[size];
  const stops = scheme === "categories" ? null : stopsOf(scheme);
  if (stops && range) return rampColour(stops, (size - range[0]) / (range[1] - range[0] || 1));
  return RING_COLOURS[(((size - 3) % RING_COLOURS.length) + RING_COLOURS.length) % RING_COLOURS.length];
}
// Sizes a palette spans: the shown size limits, else the sizes found.
function ringSizeRange(data) {
  const sizes = data?.rings.map((ring) => ring.size) ?? [];
  const { minSize, maxSize } = viewerPrefs.rings;
  return [minSize ?? Math.min(...sizes), maxSize ?? Math.max(...sizes)];
}
const ringElement = (symbol) => ({ use: true, zmin: null, zmax: null, ...viewerPrefs.rings.elements[symbol] });
const ringCutoff = (a, b) => viewerPrefs.rings.cutoffs[pairKey(a, b)] ?? viewerPrefs.cutoffs[pairKey(a, b)] ?? defaultCutoff(a, b);

function insidePolygon([x, y], points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i], [xj, yj] = points[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// find_rings settings for structure s from the ring preferences.
function ringSettings(s) {
  const prefs = viewerPrefs.rings;
  const species = [...new Set(s.symbols)].sort();
  const used = species.filter((sym) => ringElement(sym).use);
  const heights = {};
  for (const sym of used) {
    const { zmin, zmax } = ringElement(sym);
    if (zmin !== null || zmax !== null) heights[sym] = [zmin, zmax];
  }
  const cutoffs = {};
  for (const a of species) for (const b of species) if (a <= b) cutoffs[`${a}-${b}`] = ringCutoff(a, b);
  return { method: prefs.method, elements: used, heights, cutoffs, alternating: prefs.alternating, count: prefs.count,
    enclosed: prefs.enclosed, max_size: prefs.searchSize };
}
// Rings of structure s with the current settings (cached: structures never
// change). Each ring gets its centre for drawing and labels.
const ringCache = new Map();
function loadRings(s) {
  const settings = JSON.stringify(ringSettings(s));
  const key = `${s.id}|${settings}`;
  if (!ringCache.has(key)) {
    if (ringCache.size > 300) ringCache.clear();
    const load = api(`structures/${encodeURIComponent(s.id)}/rings?settings=${encodeURIComponent(settings)}`).then((data) => {
      for (const ring of data.rings) ring.centre = mul(ring.points.reduce(add, [0, 0, 0]), 1 / ring.points.length);
      return data;
    });
    load.catch(() => ringCache.delete(key));
    ringCache.set(key, load);
  }
  return ringCache.get(key);
}
const ringShown = (ring) => {
  const { minSize, maxSize } = viewerPrefs.rings;
  return (minSize === null || ring.size >= minSize) && (maxSize === null || ring.size <= maxSize);
};

// ---------------------------------------------------------------- scene model

const neighbourCache = new Map();

// Directed neighbour pairs (i -> j + periodic offset) within the pair cutoffs.
function neighbours(structure, cutoffs) {
  const symbols = structure.symbols;
  const species = [...new Set(symbols)];
  const key = `${structure.id}|${species.map((a) => species.map((b) => cutoffs[pairKey(a, b)] ?? 0).join(",")).join(";")}`;
  if (neighbourCache.has(key)) return neighbourCache.get(key);
  const index = symbols.map((s) => species.indexOf(s));
  const cut2 = species.map((a) => species.map((b) => (cutoffs[pairKey(a, b)] ?? 0) ** 2));
  const [A, B, C] = structure.cell;
  const ranges = structure.pbc.map((periodic) => (periodic ? [-1, 0, 1] : [0]));
  const shifts = [];
  for (const i of ranges[0]) for (const j of ranges[1]) for (const k of ranges[2]) {
    shifts.push({ off: [i, j, k], vec: add(add(mul(A, i), mul(B, j)), mul(C, k)) });
  }
  const P = structure.positions;
  const bonds = [];
  for (let i = 0; i < P.length; i++) {
    const row = cut2[index[i]];
    for (let j = 0; j < P.length; j++) {
      const c2 = row[index[j]];
      if (!c2) continue;
      for (const shift of shifts) {
        if (i === j && !shift.off.some(Boolean)) continue;
        const dx = P[j][0] + shift.vec[0] - P[i][0], dy = P[j][1] + shift.vec[1] - P[i][1], dz = P[j][2] + shift.vec[2] - P[i][2];
        if (dx * dx + dy * dy + dz * dz < c2) bonds.push({ i, j, off: shift.off, to: add(P[j], shift.vec) });
      }
    }
  }
  if (neighbourCache.size > 20) neighbourCache.clear();
  neighbourCache.set(key, bonds);
  return bonds;
}

// Convex hull faces (as ordered polygons) of a handful of ligand points.
function hullFaces(points) {
  const eps = 1e-3;
  const centroid = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  const planes = new Map();
  for (let a = 0; a < points.length; a++) for (let b = a + 1; b < points.length; b++) for (let c = b + 1; c < points.length; c++) {
    let n = cross(sub(points[b], points[a]), sub(points[c], points[a]));
    if (norm(n) < eps) continue;
    n = unit(n);
    if (dot(n, sub(points[a], centroid)) < 0) n = mul(n, -1);
    const d = dot(n, points[a]);
    if (points.some((p) => dot(n, p) - d > 0.05)) continue;
    const key = n.map((v) => v.toFixed(2)).join(",");
    if (!planes.has(key)) planes.set(key, { n, d });
  }
  const faces = [];
  for (const { n, d } of planes.values()) {
    const onFace = points.filter((p) => Math.abs(dot(n, p) - d) < 0.05);
    if (onFace.length < 3) continue;
    const center = mul(onFace.reduce(add, [0, 0, 0]), 1 / onFace.length);
    const u = unit(sub(onFace[0], center)), v = cross(n, u);
    onFace.sort((p, q) => Math.atan2(dot(sub(p, center), v), dot(sub(p, center), u)) - Math.atan2(dot(sub(q, center), v), dot(sub(q, center), u)));
    faces.push({ points: onFace, normal: n });
  }
  return faces;
}

// Mode arrows are this many times the displacement long.
const MODE_ARROW_SCALE = 4;
const THZ_TO_CM = 33.35641;
// Video formats to record, in order of preference.
const VIDEO_TYPES = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"];

// A video frame for a panel of width × height CSS pixels at `dpr`: its size
// in pixels (even, as encoders want), and the layout size and pixel scale
// that keep the panel's view whole. A frame of another shape shows more of
// the scene along its longer side.
function videoFrame(size, width, height, dpr) {
  const even = (value) => 2 * Math.max(1, Math.round(value / 2));
  const [w, h] = Object.hasOwn(VIDEO_SIZES, size) ? VIDEO_SIZES[size] : [even(width * dpr), even(height * dpr)];
  const scale = Math.min(w / width, h / height);
  return { pixels: [w, h], layout: [w / scale, h / scale], scale };
}
// Frequencies closer to 0 than this (THz) count as 0, not imaginary: phonopy
// prints acoustic modes at Γ as -0.000001.
const ZERO_FREQUENCY = 1e-3;

// Displacement of a copy of atom i at fractional position r (its position in
// the cell plus the repeat index n) for one mode:
// Re[scale · d · exp(i(2π q·r − phase))], as phonopy defines its modes. The
// rows of motion.vectors are [Re x, Re y, Re z, Im x, Im y, Im z]. At q = 0
// the position does not matter (and need not exist: molecules have no cell).
function modeDisplacement(motion, i, r, phase = motion.phase) {
  const theta = (motion.q.some(Boolean) ? 2 * Math.PI * dot(motion.q, r) : 0) - phase;
  const c = Math.cos(theta), s = Math.sin(theta), d = motion.vectors[i], k = motion.scale;
  return [(d[0] * c - d[3] * s) * k, (d[1] * c - d[4] * s) * k, (d[2] * c - d[5] * s) * k];
}

// Everything a renderer draws, in Angstrom world coordinates. `forces` (or
// null) holds per-atom vectors, magnitudes and inclusion for the arrows.
// `motion` (or null) is a vibrational mode: { q, vectors, scale, phase,
// moving, arrows, bonds }; atoms are displaced while `moving`, and every
// copy of the cell moves with its own phase.
function buildScene(structure, overlay, forces, ringData = null, motion = null) {
  const prefs = viewerPrefs;
  const [A, B, C] = structure.cell;
  const [na, nb, nc] = prefs.repeat.map((n, k) => (structure.pbc[k] ? n : 1));
  const latticeShift = (n) => add(add(mul(A, n[0]), mul(B, n[1])), mul(C, n[2]));
  const recip = reciprocal(structure.cell);
  const moving = Boolean(motion?.moving);
  // Fractional positions of the atoms, for the phase of each copy.
  const frac = motion ? structure.positions.map((p) => fractional(recip, p)) : null;
  // Where atom i of the cell copy n (shifted by `shift`) is drawn.
  const place = moving
    ? (i, n, shift) => add(add(structure.positions[i], shift), modeDisplacement(motion, i, add(n, frac[i])))
    : (i, n, shift) => add(structure.positions[i], shift);
  const ballAndStick = prefs.bonds || prefs.polyhedra;
  const colours = structure.symbols.map((symbol, i) => overlay.colour(i, symbol));
  for (const group of paintState.groups) {
    if (fitsStructure(structure, group.atoms)) for (const r of group.atoms) colours[r.index] = group.colour;
  }
  const radii = structure.symbols.map(atomRadius);
  const images = [];
  for (let ia = 0; ia < na; ia++) for (let ib = 0; ib < nb; ib++) for (let ic = 0; ic < nc; ic++) {
    images.push({ n: [ia, ib, ic], shift: add(add(mul(A, ia), mul(B, ib)), mul(C, ic)) });
  }
  const hidden = new Set(prefs.hiddenElements);
  const visible = structure.positions.map((p, i) => !hidden.has(structure.symbols[i]) && inSlice(fractional(recip, p)));
  const atoms = [];
  // Atoms at rest while a mode plays: the depth range of depth cueing.
  const rest = moving ? [] : null;
  let centreSum = [0, 0, 0];
  // The centre ignores vibrations, so the view stays still.
  images.forEach(({ n, shift }) => structure.positions.forEach((p, i) => {
    centreSum = add(centreSum, add(p, shift));
    if (!visible[i]) return;
    atoms.push({ index: i, position: place(i, n, shift), radius: radii[i], colour: colours[i] });
    rest?.push(add(p, shift));
  }));
  const halfBonds = [], polyhedra = [];
  if (ballAndStick) {
    const bonds = neighbours(structure, prefs.cutoffs);
    // Bonds only between atoms that are shown: a partner in a cell copy
    // outside the repeat gets no half-bond (polyhedra keep all ligands).
    const shown = (m) => m[0] >= 0 && m[0] < na && m[1] >= 0 && m[1] < nb && m[2] >= 0 && m[2] < nc;
    if (prefs.bonds && !moving) {
      for (const { n, shift } of images) for (const bond of bonds) {
        if (!visible[bond.i] || !visible[bond.j] || !shown(add(n, bond.off))) continue;
        const from = add(structure.positions[bond.i], shift);
        halfBonds.push({ from, to: mul(add(from, add(bond.to, shift)), 0.5), colour: colours[bond.i] });
      }
    } else if (prefs.bonds) {
      // Fixed: the equilibrium bonds, between the displaced atoms. Live: no
      // atom moves further than motion.amplitude, so every bond of a frame
      // is among the pairs within cutoff + 2 amplitude at equilibrium; keep
      // those within the cutoff now.
      const live = motion.bonds === "live";
      const reach = Object.fromEntries(Object.entries(prefs.cutoffs).map(([key, c]) => [key, c > 0 ? c + 2 * motion.amplitude : 0]));
      const candidates = live ? neighbours(structure, reach) : bonds;
      for (const { n, shift } of images) for (const bond of candidates) {
        const m = add(n, bond.off);
        if (!visible[bond.i] || !visible[bond.j] || !shown(m)) continue;
        const from = place(bond.i, n, shift), to = place(bond.j, m, latticeShift(m));
        if (live) {
          const d = sub(to, from), c = prefs.cutoffs[pairKey(structure.symbols[bond.i], structure.symbols[bond.j])] ?? 0;
          if (dot(d, d) >= c * c) continue;
        }
        halfBonds.push({ from, to: mul(add(from, to), 0.5), colour: colours[bond.i] });
      }
    }
    if (prefs.polyhedra) {
      const centres = new Set(prefs.polyCenters ?? structure.symbols.filter((s) => TRANSITION_METALS.has(s)));
      const ligands = new Map();
      for (const bond of bonds) {
        if (!visible[bond.i] || !centres.has(structure.symbols[bond.i]) || !NONMETALS.has(structure.symbols[bond.j])) continue;
        if (!ligands.has(bond.i)) ligands.set(bond.i, []);
        ligands.get(bond.i).push(bond);
      }
      for (const [i, list] of ligands) {
        if (list.length < 4) continue;
        if (moving) {
          // The equilibrium ligands, displaced: each copy has its own shape.
          for (const { n } of images) {
            const points = list.map((bond) => { const m = add(n, bond.off); return place(bond.j, m, latticeShift(m)); });
            polyhedra.push({ colour: colours[i], faces: hullFaces(points) });
          }
          continue;
        }
        const faces = hullFaces(list.map((bond) => bond.to));
        for (const { shift } of images) {
          polyhedra.push({ colour: colours[i], faces: faces.map((f) => ({ normal: f.normal, points: f.points.map((p) => add(p, shift)) })) });
        }
      }
    }
  }
  const corners = [];
  for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) corners.push(add(add(mul(A, i), mul(B, j)), mul(C, k)));
  const cellEdges = prefs.cell ? [[0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3], [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7]].map(([a, b]) => [corners[a], corners[b]]) : [];
  // Centre on every atom so slicing does not move the view.
  const centre = mul(centreSum, 1 / Math.max(1, images.length * structure.positions.length));
  const planes = prefs.planes.map((plane, k) => ({ plane, k })).filter(({ plane }) => plane.show && (plane.h || plane.k || plane.l))
    .map(({ plane, k }) => ({ colour: planeColour(plane, k), polygon: planePolygon(structure.cell, plane, [na, nb, nc]) }))
    .filter((p) => p.polygon);
  // Rings in every shown cell copy, coloured by size.
  // (ringData: from loadRings, while rings are shown.)
  const rings = [], sizeRange = ringSizeRange(ringData);
  for (const ring of ringData?.rings ?? []) {
    if (!ringShown(ring)) continue;
    for (const { shift } of images) {
      rings.push({ ring, colour: ringColour(ring.size, sizeRange), points: ring.points.map((p) => add(p, shift)), centre: add(ring.centre, shift) });
    }
  }
  // Text on atoms: index, element, or the value the atom is coloured by.
  const labelText = {
    index: (i) => String(i), element: (i) => structure.symbols[i], "element-index": (i) => `${structure.symbols[i]}${i}`,
    value: (i) => overlay.value?.(i) ?? "",
  }[prefs.labels];
  const labels = labelText ? atoms.map((atom) => ({ position: atom.position, radius: atom.radius, text: labelText(atom.index) })).filter((l) => l.text) : [];
  // Arrows start on the sphere surface so the atom does not hide them.
  const arrows = [];
  if (prefs.arrows.show && forces) {
    for (const atom of atoms) {
      const i = atom.index, magnitude = forces.magnitudes[i];
      if (!forces.included[i] || !(magnitude > 0) || magnitude < prefs.arrows.minMagnitude) continue;
      const from = add(atom.position, mul(forces.vectors[i], atom.radius / magnitude));
      arrows.push({ from, to: add(from, mul(forces.vectors[i], prefs.arrows.scale)) });
    }
  }
  // Mode arrows: each atom's displacement at phase 0 (where the vibration
  // starts), drawn from the atom as shown.
  if (motion?.arrows) {
    for (const { n, shift } of images) structure.positions.forEach((p, i) => {
      if (!visible[i]) return;
      const vector = mul(modeDisplacement(motion, i, add(n, frac[i]), 0), MODE_ARROW_SCALE), length = norm(vector);
      if (!(length > 1e-6)) return;
      const from = add(place(i, n, shift), mul(vector, radii[i] / length));
      arrows.push({ from, to: add(from, vector) });
    });
  }
  // Measurements on top of the scene, and rings around atoms picked so far.
  const marks = measureState.items.filter((item) => fitsStructure(structure, item.atoms))
    .map((item) => ({ points: item.atoms.map((r) => refPosition(structure, r)), label: measureValue(structure, item).text }));
  const picked = fitsStructure(structure, measureState.pending)
    ? measureState.pending.map((r) => ({ position: refPosition(structure, r), radius: radii[r.index] })) : [];
  // Atoms selected for colouring: a ring on every shown copy.
  if (fitsStructure(structure, paintState.selected)) {
    const selected = new Set(paintState.selected.map((r) => r.index));
    for (const atom of atoms) if (selected.has(atom.index)) picked.push({ position: atom.position, radius: atom.radius });
  }
  return { atoms, halfBonds, polyhedra, cellEdges, planes, arrows, arrowStyle: { ...prefs.arrows }, marks, picked,
    rings, ringData, ringStyle: { ...prefs.rings }, labels, tripod: prefs.tripod.axes,
    centre, restPositions: rest, bondRadius: prefs.appearance.bondRadius, structure, overlay,
    appearance: { ...prefs.appearance, radii: { ...prefs.appearance.radii } },
    visibleAtoms: atoms.length, totalAtoms: images.length * structure.positions.length };
}

// ---------------------------------------------------------------- projection

function projector(scene, width, height) {
  const R = sharedView.R, s = sharedView.scale, c = scene.centre, [px, py] = sharedView.pan;
  return (p) => {
    const d = sub(p, c);
    return [dot(R[0], d) * s + width / 2 + px, height / 2 - dot(R[1], d) * s + py, dot(R[2], d)];
  };
}

// The scale that fits the atoms and the cell into the panel, and the pan that
// centres them (the scene's centre is the atoms' centroid, which can lie far
// from the middle of the cell outline).
function fitView(scene, width, height) {
  const R = sharedView.R;
  const points = [...scene.atoms.map((a) => a.position), ...scene.cellEdges.flat()];
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const p of points) {
    const d = sub(p, scene.centre);
    const x = dot(R[0], d), y = dot(R[1], d);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const scale = 0.9 * Math.min(width / Math.max(1, x1 - x0 + 3), height / Math.max(1, y1 - y0 + 3));
  return { scale, pan: [-(x0 + x1) / 2 * scale, (y0 + y1) / 2 * scale] };
}

// ---------------------------------------------------------------- display list

// Default arrow colour: the page's text colour, so arrows suit light and dark themes.
const themeTextColour = () => getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#1d2125";

// Everything a scene shows, as 2D primitives in painting order (back to front),
// for the canvas and for SVG export. Pixel coordinates; y points down.
//   sphere:  { kind, x, y, r, colour, fog?, fogColour? }
//   line:    { kind, a, b, colour, width }
//   polygon: { kind, points, fill, fillAlpha, stroke, strokeAlpha, strokeWidth }
//   arrow:   { kind, a, b, colour, width }
//   label:   { kind, x, y, text, colour, halo }
//   ring:    { kind, x, y, r, colour, width }
// Lines may carry a dash pattern; labels a font size (default 12). `theme`
// holds CSS colours (themeColours). With depth cueing, colours are mixed
// towards the background (theme.halo); spheres keep their cached sprite and
// get a background disc of opacity `fog`. With `tripod`, the axis tripod comes
// last (`hoverAxis` drawn highlighted).
function displayList(scene, width, height, theme, { tripod = true, hoverAxis = null } = {}) {
  const project = projector(scene, width, height);
  const s = sharedView.scale;
  const R = sharedView.R;
  const look = scene.appearance;
  const items = [];
  for (const atom of scene.atoms) {
    const [x, y, z] = project(atom.position);
    items.push({ z, p: atom.position, prims: [{ kind: "sphere", x, y, r: atom.radius * s, colour: atom.colour }] });
  }
  for (const bond of scene.halfBonds) {
    const a = project(bond.from), b = project(bond.to);
    items.push({ z: Math.min(a[2], b[2]) - 0.05, p: mul(add(bond.from, bond.to), 0.5),
      prims: [{ kind: "line", a, b, colour: mix(bond.colour, "#000000", 0.2), width: Math.max(1, 2 * scene.bondRadius * s) }] });
  }
  if (scene.arrows.length) {
    const colour = scene.arrowStyle.colour || theme.text;
    const arrowWidth = Math.max(1, 2 * scene.arrowStyle.width * s);
    for (const arrow of scene.arrows) {
      const a = project(arrow.from), b = project(arrow.to);
      items.push({ z: (a[2] + b[2]) / 2, p: mul(add(arrow.from, arrow.to), 0.5), prims: [{ kind: "arrow", a, b, colour, width: arrowWidth }] });
    }
  }
  for (const poly of scene.polyhedra) for (const face of poly.faces) {
    const points = face.points.map(project);
    const facing = dot(R[2], face.normal);
    items.push({ z: points.reduce((m, q) => m + q[2], 0) / points.length, p: mul(face.points.reduce(add, [0, 0, 0]), 1 / face.points.length),
      prims: [{ kind: "polygon", points,
        fill: look.polyAlpha > 0 ? mix(poly.colour, facing > 0 ? "#ffffff" : "#000000", Math.abs(facing) * 0.35) : null, fillAlpha: look.polyAlpha,
        stroke: look.polyEdges ? mix(poly.colour, "#000000", 0.5) : null, strokeAlpha: 0.7, strokeWidth: 1 }] });
  }
  // Rings sit just behind their own atoms, so the atoms stay on top.
  const ringStyle = scene.ringStyle;
  for (const ring of scene.rings) {
    const points = ring.points.map(project);
    items.push({ z: points.reduce((m, q) => m + q[2], 0) / points.length - 0.6, p: ring.centre,
      prims: [{ kind: "polygon", points, fill: ring.colour, fillAlpha: ringStyle.alpha,
        stroke: ringStyle.outline ? mix(ring.colour, "#000000", 0.35) : null, strokeAlpha: 0.9, strokeWidth: 1.5 }] });
  }
  const fogAt = depthFog(scene, look);
  if (fogAt) {
    for (const item of items) {
      const fog = fogAt(item.z);
      if (!(fog > 0)) continue;
      for (const prim of item.prims) {
        if (prim.kind === "sphere") Object.assign(prim, { fog, fogColour: theme.halo });
        else if (prim.kind === "polygon") {
          if (prim.fill) prim.fill = mix(prim.fill, theme.halo, fog);
          if (prim.stroke) prim.stroke = mix(prim.stroke, theme.halo, fog);
        } else prim.colour = mix(prim.colour, theme.halo, fog);
      }
    }
  }
  items.sort((p, q) => p.z - q.z);
  const list = scene.cellEdges.map(([a, b]) => {
    const pa = project(a), pb = project(b), fog = fogAt?.((pa[2] + pb[2]) / 2);
    return { kind: "line", a: pa, b: pb, colour: fog > 0 ? mix(theme.cell, theme.halo, fog) : theme.cell, width: 1 };
  });
  // Planes are drawn whole; each item goes before or after a plane depending
  // on which side of it the item lies as seen from the viewer.
  const planes = scene.planes.map((pl) => {
    const points = pl.polygon.points.map(project);
    return { ...pl, points, depth: points.reduce((m, q) => m + q[2], 0) / points.length, facing: Math.sign(dot(pl.polygon.normal, R[2])) || 1 };
  }).sort((a, b) => a.depth - b.depth);
  const layers = planes.map(() => []).concat([[]]);
  for (const item of items) {
    const front = planes.reduce((n, pl) => n + (Math.sign(dot(pl.polygon.normal, sub(item.p, pl.polygon.centre))) === pl.facing ? 1 : 0), 0);
    layers[front].push(item);
  }
  layers.forEach((layer, k) => {
    for (const item of layer) list.push(...item.prims);
    const pl = planes[k];
    if (pl) list.push({ kind: "polygon", points: pl.points, fill: pl.colour, fillAlpha: look.planeAlpha, stroke: pl.colour, strokeAlpha: 1, strokeWidth: 2 });
  });
  // Atom labels, ring sizes and measurements are always drawn on top, so they
  // stay visible.
  for (const label of scene.labels) {
    const [x, y] = project(label.position);
    list.push({ kind: "label", x, y: y + 5, text: label.text, colour: theme.text, halo: theme.halo, size: 10 });
  }
  // Ring labels: dark text in the ring's hue on a white outline, in every theme.
  if (ringStyle.labels) {
    const size = Math.round(12 * (ringStyle.labelScale ?? 1));
    for (const ring of scene.rings) {
      const [x, y] = project(ring.centre);
      list.push({ kind: "label", x, y: y + size / 2, text: ring.ring.label, colour: mix(ring.colour, "#000000", 0.55), halo: "#ffffff", size });
    }
  }
  // A measurement label that would overlap an earlier one moves up until it is free.
  const placed = [];
  const freeY = (x, y, text) => {
    const half = text.length * 3.6 + 3;
    while (placed.some((q) => Math.abs(q.x - x) < q.half + half && Math.abs(q.y - y) < 15)) y -= 15;
    placed.push({ x, y, half });
    return y;
  };
  for (const mark of scene.marks) {
    const points = mark.points.map(project);
    for (let k = 0; k + 1 < points.length; k++) {
      list.push({ kind: "line", a: points[k], b: points[k + 1], colour: theme.accent, width: 1.5, dash: [5, 4] });
    }
    // Label at the bond's middle (distance), the vertex (angle) or the middle bond (dihedral).
    const at = points.length === 3 ? points[1] : points.length === 2
      ? [(points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2]
      : [(points[1][0] + points[2][0]) / 2, (points[1][1] + points[2][1]) / 2];
    list.push({ kind: "label", x: at[0], y: freeY(at[0], at[1] - 6, mark.label), text: mark.label, colour: theme.text, halo: theme.halo });
  }
  for (const pick of scene.picked) {
    const [x, y] = project(pick.position);
    list.push({ kind: "ring", x, y, r: pick.radius * s + 3, colour: theme.accent, width: 2 });
  }
  if (tripod && scene.tripod !== "off") list.push(...tripodPrims(tripodLayout(scene, height), theme, hoverAxis));
  return list;
}

// ---------------------------------------------------------------- axis tripod

// The tripod's arrows in pixels, back to front: { name, colour, lattice,
// origin, tip, label, z } with z > 0 pointing at the viewer. With both kinds,
// the Cartesian arrows are shorter, so their labels stay apart.
const TRIPOD_LENGTH = 34;
function tripodLayout(scene, height) {
  const R = sharedView.R;
  const origin = [48, height - 48];
  const names = { abc: "abc", xyz: "xyz", both: "xyzabc" }[scene.tripod] ?? "";
  // Cell axes of zero length (a molecule without a cell) are left out.
  return [...names].map((name) => {
    const v = axisDirection(scene.structure.cell, name);
    if (!norm(v)) return null;
    const x = dot(R[0], v), y = dot(R[1], v);
    const lattice = "abc".includes(name), length = scene.tripod === "both" && !lattice ? 0.6 * TRIPOD_LENGTH : TRIPOD_LENGTH;
    return { name, colour: AXIS_COLOURS[name], lattice, origin, z: dot(R[2], v),
      tip: [origin[0] + x * length, origin[1] - y * length],
      label: [origin[0] + x * (length + 10), origin[1] - y * (length + 10)] };
  }).filter(Boolean).sort((p, q) => p.z - q.z);
}

// Cell axes as solid arrows, Cartesian ones thinner; axes pointing away from
// the viewer are paler.
function tripodPrims(layout, theme, hoverAxis) {
  const prims = [];
  for (const axis of layout) {
    const hovered = axis.name === hoverAxis;
    const colour = axis.z < -0.2 ? mix(axis.colour, theme.halo, 0.45) : axis.colour;
    const width = (axis.lattice ? 2.5 : 1.5) + (hovered ? 1.5 : 0);
    if (Math.hypot(axis.tip[0] - axis.origin[0], axis.tip[1] - axis.origin[1]) > 4) {
      prims.push({ kind: "arrow", a: [...axis.origin, 0], b: [...axis.tip, 0], colour, width });
    }
    prims.push({ kind: "label", x: axis.label[0], y: axis.label[1] + 6, text: axis.name, colour, halo: theme.halo, size: hovered ? 14 : 12 });
  }
  return prims;
}

// The axis under a pixel: its label or its shaft, front-most first.
function tripodHit(layout, x, y) {
  const near = (axis) => {
    if (Math.hypot(axis.label[0] - x, axis.label[1] - y) < 10) return true;
    const [ax, ay] = axis.origin, [bx, by] = axis.tip;
    const length2 = (bx - ax) ** 2 + (by - ay) ** 2;
    if (length2 < 16) return false;
    const t = Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / length2));
    return Math.hypot(ax + t * (bx - ax) - x, ay + t * (by - ay) - y) < 5;
  };
  return [...layout].reverse().find(near)?.name ?? null;
}

// Depth cueing: the fog (0 = none) at view depth z, from none at the front-most
// atom to look.depthStrength at the back-most; null when off. While a mode
// plays, the range comes from the atoms at rest, so the fog holds still.
function depthFog(scene, look) {
  if (!look.depthCue || !(look.depthStrength > 0)) return null;
  const R = sharedView.R;
  let front = -Infinity, back = Infinity;
  for (const p of scene.restPositions ?? scene.atoms.map((a) => a.position)) {
    const z = dot(R[2], sub(p, scene.centre));
    front = Math.max(front, z); back = Math.min(back, z);
  }
  const span = front - back;
  if (!(span > 1e-6)) return null;
  return (z) => look.depthStrength * Math.min(1, Math.max(0, (front - z) / span));
}

// Light-theme colours (app.css :root) for transparent SVGs, which may land on
// any page; labels get a white halo.
const LIGHT_THEME = { cell: "#6f6e69", accent: "#2759c4", text: "#1d2125", halo: "#ffffff" };

// Colours a panel takes from the page theme.
function themeColours(host) {
  const style = getComputedStyle(host);
  const value = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return { cell: value("--tick", "#888"), accent: value("--accent", "#2759c4"), text: value("--text", "#1d2125"), halo: value("--panel", "#ffffff") };
}

const labelFont = (size = 12) => `600 ${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
// Outline around label text, growing with larger labels.
const haloWidth = (size = 12) => Math.max(3, size / 6);

// Arrow geometry in pixels: shaft end and the head's three corners.
function arrowGeometry(a, b, width) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  if (length < 0.5) return null;
  const ux = dx / length, uy = dy / length;
  const head = Math.min(length, Math.max(3 * width, 6));
  const half = Math.max(1.5 * width, 3);
  const bx = b[0] - ux * head, by = b[1] - uy * head;
  return { shaft: length > head ? [a, [bx, by]] : null,
    head: [[b[0], b[1]], [bx - uy * half, by + ux * half], [bx + uy * half, by - ux * half]] };
}

// Shaded sphere: light top-left highlight, darker rim (canvas and SVG alike).
const sphereStops = (colour) => [[0, mix(colour, "#ffffff", 0.6)], [0.5, colour], [1, mix(colour, "#000000", 0.45)]];

// ---------------------------------------------------------------- canvas renderer

// Sprites are drawn in device pixels (`scale` per CSS pixel), so spheres stay
// sharp on high-density screens and in videos larger than the panel; the
// outline stays one CSS pixel wide.
const spriteCache = new Map();
const spriteRadius = (radius) => Math.max(1, Math.round(radius * 2) / 2);
function sphereSprite(colour, radius, scale = 1) {
  const r = spriteRadius(radius * scale);
  const key = `${colour}|${r}|${scale}`;
  let sprite = spriteCache.get(key);
  if (sprite) return sprite;
  const size = Math.ceil(2 * r + 2 * scale);
  sprite = document.createElement("canvas");
  sprite.width = sprite.height = size;
  const ctx = sprite.getContext("2d");
  const c = size / 2;
  const gradient = ctx.createRadialGradient(c - 0.35 * r, c - 0.35 * r, 0.1 * r, c, c, r);
  for (const [offset, stop] of sphereStops(colour)) gradient.addColorStop(offset, stop);
  ctx.fillStyle = gradient;
  ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = scale; ctx.stroke();
  if (spriteCache.size > 600) spriteCache.clear();
  spriteCache.set(key, sprite);
  return sprite;
}

// `pixelScale`: device pixels per CSS pixel of the canvas transform.
function paintCanvas(ctx, list, pixelScale = 1) {
  const path = (points) => { ctx.beginPath(); points.forEach((q, i) => (i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]))); };
  for (const prim of list) {
    if (prim.kind === "sphere") {
      const sprite = sphereSprite(prim.colour, prim.r, pixelScale), size = sprite.width / pixelScale;
      ctx.drawImage(sprite, prim.x - size / 2, prim.y - size / 2, size, size);
      if (prim.fog > 0) {
        // Covers the sprite's outline (half a CSS pixel outside its radius) too.
        ctx.globalAlpha = prim.fog; ctx.fillStyle = prim.fogColour;
        ctx.beginPath(); ctx.arc(prim.x, prim.y, spriteRadius(prim.r * pixelScale) / pixelScale + 0.5, 0, 2 * Math.PI); ctx.fill();
        ctx.globalAlpha = 1;
      }
    } else if (prim.kind === "line") {
      ctx.strokeStyle = prim.colour; ctx.lineWidth = prim.width; ctx.lineCap = "butt";
      if (prim.dash) ctx.setLineDash(prim.dash);
      path([prim.a, prim.b]); ctx.stroke();
      if (prim.dash) ctx.setLineDash([]);
    } else if (prim.kind === "label") {
      ctx.font = labelFont(prim.size); ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.lineWidth = haloWidth(prim.size); ctx.lineJoin = "round"; ctx.strokeStyle = prim.halo; ctx.strokeText(prim.text, prim.x, prim.y);
      ctx.fillStyle = prim.colour; ctx.fillText(prim.text, prim.x, prim.y);
    } else if (prim.kind === "ring") {
      ctx.strokeStyle = prim.colour; ctx.lineWidth = prim.width;
      ctx.beginPath(); ctx.arc(prim.x, prim.y, prim.r, 0, 2 * Math.PI); ctx.stroke();
    } else if (prim.kind === "arrow") {
      const geometry = arrowGeometry(prim.a, prim.b, prim.width);
      if (!geometry) continue;
      ctx.strokeStyle = ctx.fillStyle = prim.colour;
      if (geometry.shaft) { ctx.lineWidth = prim.width; ctx.lineCap = "butt"; path(geometry.shaft); ctx.stroke(); }
      path(geometry.head); ctx.closePath(); ctx.fill();
    } else if (prim.kind === "polygon") {
      path(prim.points); ctx.closePath();
      if (prim.fill && prim.fillAlpha > 0) { ctx.globalAlpha = prim.fillAlpha; ctx.fillStyle = prim.fill; ctx.fill(); }
      if (prim.stroke) { ctx.globalAlpha = prim.strokeAlpha; ctx.strokeStyle = prim.stroke; ctx.lineWidth = prim.strokeWidth; ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
  }
}

// A scene on `canvas`, laid out for width × height CSS pixels with
// `pixelScale` device pixels each. `opaque` paints the panel background first
// (videos have no transparency).
function paintScene(canvas, scene, width, height, pixelScale, theme, opaque = false, options = {}) {
  const ctx = canvas.getContext("2d");
  ctx.setTransform(pixelScale, 0, 0, pixelScale, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (opaque) { ctx.fillStyle = theme.halo; ctx.fillRect(0, 0, width, height); }
  paintCanvas(ctx, displayList(scene, width, height, theme, options), pixelScale);
}

// `onDraw(scene, theme)`, if set, runs after every draw (a video recording
// paints its own canvas).
function createCanvasRenderer(host) {
  const canvas = el("canvas", { class: "viewer-canvas" });
  host.append(canvas);
  return {
    canvas,
    onDraw: null,
    draw(scene, options) {
      const dpr = window.devicePixelRatio || 1;
      const width = host.clientWidth, height = host.clientHeight;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
        canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
      }
      const theme = themeColours(host);
      paintScene(canvas, scene, width, height, dpr, theme, false, options);
      this.onDraw?.(scene, theme);
    },
    dispose() { canvas.remove(); },
  };
}

// ---------------------------------------------------------------- SVG export

// The panels as one SVG document, side by side as on screen, each on its
// panel background. Spheres share one radial gradient per colour.
// With `transparent`, no background and light-theme colours; otherwise the
// panel's background and the page's theme, as on screen.
function panelsToSvg(panels, { transparent = false, tripod = true } = {}) {
  const round = (v) => Math.round(v * 100) / 100;
  const xy = (q) => `${round(q[0])},${round(q[1])}`;
  const gradients = new Map();
  const gradient = (colour) => {
    if (!gradients.has(colour)) gradients.set(colour, `sphere${gradients.size}`);
    return gradients.get(colour);
  };
  const groups = [];
  let offset = 0, totalHeight = 0;
  for (const panel of panels) {
    const host = panel.stage;
    const width = host.clientWidth, height = host.clientHeight;
    const theme = transparent ? LIGHT_THEME : themeColours(host);
    const shapes = transparent ? [] : [`<rect width="${width}" height="${height}" fill="${theme.halo}"/>`];
    for (const prim of displayList(panel.scene, width, height, theme, { tripod })) {
      if (prim.kind === "sphere") {
        shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(Math.max(0.5, prim.r))}" fill="url(#${gradient(prim.colour)})" stroke="#000" stroke-opacity="0.35"/>`);
        if (prim.fog > 0) shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(Math.max(0.5, prim.r) + 0.5)}" fill="${prim.fogColour}" fill-opacity="${round(prim.fog)}"/>`);
      } else if (prim.kind === "line") {
        const dash = prim.dash ? ` stroke-dasharray="${prim.dash.join(" ")}"` : "";
        shapes.push(`<line x1="${round(prim.a[0])}" y1="${round(prim.a[1])}" x2="${round(prim.b[0])}" y2="${round(prim.b[1])}" stroke="${prim.colour}" stroke-width="${round(prim.width)}"${dash}/>`);
      } else if (prim.kind === "label") {
        const text = prim.text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        shapes.push(`<text x="${round(prim.x)}" y="${round(prim.y)}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="${prim.size ?? 12}" font-weight="600" fill="${prim.colour}" stroke="${prim.halo}" stroke-width="${round(haloWidth(prim.size))}" stroke-linejoin="round" paint-order="stroke">${text}</text>`);
      } else if (prim.kind === "ring") {
        shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(prim.r)}" fill="none" stroke="${prim.colour}" stroke-width="${prim.width}"/>`);
      } else if (prim.kind === "arrow") {
        const geometry = arrowGeometry(prim.a, prim.b, prim.width);
        if (!geometry) continue;
        if (geometry.shaft) shapes.push(`<line x1="${round(geometry.shaft[0][0])}" y1="${round(geometry.shaft[0][1])}" x2="${round(geometry.shaft[1][0])}" y2="${round(geometry.shaft[1][1])}" stroke="${prim.colour}" stroke-width="${round(prim.width)}"/>`);
        shapes.push(`<polygon points="${geometry.head.map(xy).join(" ")}" fill="${prim.colour}"/>`);
      } else if (prim.kind === "polygon") {
        const fill = prim.fill && prim.fillAlpha > 0 ? `fill="${prim.fill}" fill-opacity="${round(prim.fillAlpha)}"` : `fill="none"`;
        const stroke = prim.stroke ? ` stroke="${prim.stroke}" stroke-opacity="${round(prim.strokeAlpha)}" stroke-width="${prim.strokeWidth}" stroke-linejoin="round"` : "";
        shapes.push(`<polygon points="${prim.points.map(xy).join(" ")}" ${fill}${stroke}/>`);
      }
    }
    groups.push(`<g transform="translate(${offset},0)">\n${shapes.join("\n")}\n</g>`);
    offset += width + (panels.length > 1 ? 12 : 0);
    totalHeight = Math.max(totalHeight, height);
  }
  const totalWidth = offset - (panels.length > 1 ? 12 : 0);
  // Focal point top-left of centre, as in the canvas sprites.
  const defs = [...gradients].map(([colour, id]) => `<radialGradient id="${id}" cx="0.5" cy="0.5" r="0.5" fx="0.325" fy="0.325" fr="0.05">${
    sphereStops(colour).map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join("")}</radialGradient>`);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="${totalHeight}" viewBox="0 0 ${totalWidth} ${totalHeight}">
<defs>${defs.join("\n")}</defs>
${groups.join("\n")}
</svg>
`;
}

// The panels as one PNG image, laid out as panelsToSvg, at `scale` pixels per
// screen pixel.
function panelsToPng(panels, { transparent = false, tripod = true, scale = 3 } = {}) {
  const gap = panels.length > 1 ? 12 : 0;
  const sizes = panels.map((panel) => [panel.stage.clientWidth, panel.stage.clientHeight]);
  const width = sizes.reduce((m, [w]) => m + w, 0) + gap * (panels.length - 1);
  const height = Math.max(...sizes.map(([, h]) => h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  let offset = 0;
  panels.forEach((panel, k) => {
    const [w, h] = sizes[k];
    const theme = transparent ? LIGHT_THEME : themeColours(panel.stage);
    ctx.setTransform(scale, 0, 0, scale, offset * scale, 0);
    if (!transparent) { ctx.fillStyle = theme.halo; ctx.fillRect(0, 0, w, h); }
    paintCanvas(ctx, displayList(panel.scene, w, h, theme, { tripod }), scale);
    offset += w + gap;
  });
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
// `text` may also be a Blob (a recorded video).
const downloadText = (filename, text, type) => downloadBlob(filename, new Blob([text], { type }));

// ---------------------------------------------------------------- phonon bands and DOS

// Where q lies on the band path: { k (segment), t (0..1 along it), d (path
// distance) } for each place, q shifted by a reciprocal lattice vector too.
function pathPositions(segments, q) {
  const found = [];
  segments.forEach((segment, k) => {
    const dir = sub(segment.end, segment.start), length2 = dot(dir, dir);
    const d0 = segment.distances[0], d1 = segment.distances.at(-1);
    for (const ga of [-1, 0, 1]) for (const gb of [-1, 0, 1]) for (const gc of [-1, 0, 1]) {
      const shifted = add(q, [ga, gb, gc]);
      const t = length2 ? dot(sub(shifted, segment.start), dir) / length2 : 0;
      if (t < -1e-6 || t > 1 + 1e-6) continue;
      if (norm(sub(add(segment.start, mul(dir, t)), shifted)) > 1e-4) continue;
      const d = d0 + Math.min(1, Math.max(0, t)) * (d1 - d0);
      if (!found.some((f) => Math.abs(f.d - d) < 1e-6)) found.push({ k, t, d });
    }
  });
  return found;
}

// Frequencies of every band at path distance d within segment k.
function bandsAt(segment, d) {
  const ds = segment.distances;
  let i = 0;
  while (i < ds.length - 2 && ds[i + 1] < d) i++;
  const t = ds[i + 1] > ds[i] ? Math.min(1, Math.max(0, (d - ds[i]) / (ds[i + 1] - ds[i]))) : 0;
  return segment.frequencies[i].map((f, b) => f + (segment.frequencies[i + 1][b] - f) * t);
}

// A round tick step for about `count` ticks over `span`.
function tickStep(span, count = 5) {
  const raw = span / count, power = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((step) => step >= raw);
}

const escapeXml = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

// The phonon band structure (with the DOS beside it) of a structure served
// from phonopy input. update({ q, frequency, factor, unit }) marks q and the
// mode's frequency (THz; shown times `factor` in `unit`). A click on the
// bands, on a labelled point or a move of the slider under the bands calls
// onPick(q, frequency in THz, direction of the segment), the direction
// mattering at Γ with NAC (LO-TO splitting). Labelled points and the slider
// keep the selected branch; a click on the bands takes the closest one.
function createPhononPlot(structure, onPick) {
  const figure = el("div", { class: "phonon-figure" });
  const note = el("span", { class: "muted" });
  // With Born charges, NAC can be switched off to compare (plot.nac); the
  // panel hears of it through plot.onNac and asks for its modes again.
  const nacBox = el("input", { type: "checkbox", checked: true });
  const nacSwitch = el("label", { class: "check", hidden: true, title: "Non-analytical term correction from Born charges: LO and TO modes split at Γ, by the direction Γ is approached from" },
    nacBox, "NAC");
  const plot = { bands: null, dos: null, state: null, geometry: null, svg: "" };
  const saveButton = el("button", { type: "button", class: "small", title: "Save the band structure and DOS as an SVG image", onclick: () => {
    if (plot.svg) downloadText(`${structure.formula}-phonons.svg`, `<?xml version="1.0" encoding="UTF-8"?>\n${plot.svg}\n`, "image/svg+xml");
  } }, "Save bands & DOS (SVG)");
  // Buttons of the page that shows the plot go here, before the save button.
  plot.actions = el("div", { class: "phonon-plot-actions" }, saveButton);
  // The slider runs along the path, under the bands (aligned in draw).
  const slider = el("input", { type: "range", class: "phonon-slider", min: 0, max: 1000, step: 1, value: 0,
    "aria-label": "Position along the band path", title: "Move q along the band path" });
  plot.element = el("section", { class: "phonon-plot", "aria-label": "Phonon band structure and DOS" },
    el("div", { class: "phonon-plot-head" }, el("strong", {}, "Phonon band structure and DOS"), nacSwitch, note, plot.actions), figure, slider);

  // Resize grip at the plot's bottom-right corner, as for the structure
  // panels: width and height (vibration.plotWidth, plotHeight; double-click:
  // automatic). The plot redraws as the figure changes size.
  const sizeLabel = el("div", { class: "resize-size" });
  const grip = el("div", { class: "resize-grip", title: "Drag to resize; double-click for the automatic size",
    role: "separator", "aria-label": "Resize band structure plot" });
  plot.element.append(grip, sizeLabel);
  const applySize = () => {
    const { plotWidth, plotHeight } = viewerPrefs.vibration;
    plot.element.style.maxWidth = plotWidth ? `${plotWidth}px` : "";
    if (plotHeight) figure.style.setProperty("--plot-height", `${plotHeight}px`);
    else figure.style.removeProperty("--plot-height");
  };
  applySize();
  let resize = null;
  grip.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    resize = { x: event.clientX, y: event.clientY, width: plot.element.offsetWidth, height: figure.clientHeight,
      available: plot.element.parentElement.clientWidth };
    sizeLabel.classList.add("shown");
  });
  grip.addEventListener("pointermove", (event) => {
    if (!resize) return;
    const width = Math.round(Math.max(320, Math.min(resize.available, resize.width + event.clientX - resize.x)));
    const height = Math.round(Math.max(160, Math.min(2400, resize.height + event.clientY - resize.y)));
    Object.assign(viewerPrefs.vibration, { plotWidth: width >= resize.available ? null : width, plotHeight: height });
    applySize();
    sizeLabel.textContent = `${figure.clientWidth} × ${figure.clientHeight} px`;
  });
  const endResize = () => {
    if (!resize) return;
    resize = null;
    sizeLabel.classList.remove("shown");
    savePrefs();
  };
  grip.addEventListener("pointerup", endResize);
  grip.addEventListener("pointercancel", endResize);
  grip.addEventListener("dblclick", () => {
    Object.assign(viewerPrefs.vibration, { plotWidth: null, plotHeight: null });
    applySize(); savePrefs();
  });
  figure.textContent = "Computing the band structure…";
  const base = `structures/${encodeURIComponent(structure.id)}/phonons`;
  plot.nac = true;
  let loads = 0;
  const load = () => {
    const token = ++loads, query = plot.nac ? "" : "?nac=0";
    Promise.all([api(`${base}/bands${query}`), api(`${base}/dos${query}`).catch((error) => ({ error: error.message }))]).then(([bands, dos]) => {
      if (token !== loads) return;
      plot.bands = bands;
      plot.dos = dos.error ? null : dos;
      nacSwitch.hidden = !bands.has_nac;
      note.textContent = dos.error ? `DOS: ${dos.error}` : "";
      draw();
    }).catch((error) => { if (token === loads) figure.textContent = `Band structure: ${error.message}`; });
  };
  load();
  nacBox.addEventListener("change", () => { plot.nac = nacBox.checked; load(); plot.onNac?.(); });
  plot.update = (state) => { plot.state = state; draw(); };

  function draw() {
    if (!plot.bands || !plot.state || !figure.isConnected) return;
    const { q, frequency, factor, unit } = plot.state;
    const segments = plot.bands.segments;
    const theme = themeColours(plot.element);
    const width = Math.max(320, figure.clientWidth), height = Math.max(160, figure.clientHeight || 300);
    const total = segments.at(-1).distances.at(-1) || 1;
    let lo = 0, hi = 0;
    for (const segment of segments) for (const row of segment.frequencies) for (const f of row) { lo = Math.min(lo, f); hi = Math.max(hi, f); }
    const pad = (hi - lo) * 0.05 || 1;
    lo = (lo < -ZERO_FREQUENCY ? lo - pad : 0) * factor; hi = (hi + pad) * factor;
    const dosWidth = plot.dos ? Math.min(160, Math.round(width * 0.2)) : 0;
    const left = 54, right = 8, top = 10, bottom = 26, gap = dosWidth ? 12 : 0;
    const bandWidth = width - left - right - gap - dosWidth, h = height - top - bottom, dosLeft = left + bandWidth + gap;
    const X = (d) => left + (d / total) * bandWidth, Y = (f) => top + ((hi - f * factor) / (hi - lo)) * h;
    const r = (v) => Math.round(v * 10) / 10;
    const shapes = [];
    const line = (x1, y1, x2, y2, stroke, extra = "") => shapes.push(`<line x1="${r(x1)}" y1="${r(y1)}" x2="${r(x2)}" y2="${r(y2)}" stroke="${stroke}"${extra}/>`);
    const text = (x, y, value, extra = "") => shapes.push(`<text x="${r(x)}" y="${r(y)}" fill="${theme.text}" font-size="11" font-family="system-ui, sans-serif"${extra}>${escapeXml(value)}</text>`);

    // Frequency ticks across both panels, and 0 when there are imaginary modes.
    const step = tickStep(hi - lo);
    for (let f = Math.ceil(lo / step) * step; f <= hi + 1e-9; f += step) {
      const y = top + ((hi - f) / (hi - lo)) * h;
      line(left, y, left + bandWidth, y, theme.cell, ` stroke-opacity="0.18"`);
      if (dosWidth) line(dosLeft, y, dosLeft + dosWidth, y, theme.cell, ` stroke-opacity="0.18"`);
      text(left - 6, y + 4, Number(f.toFixed(6)), ` text-anchor="end"`);
    }
    if (lo < 0) line(left, Y(0), left + bandWidth, Y(0), theme.cell, ` stroke-dasharray="3 3"`);

    // Labelled q-points, each clickable (data-tick="segment,t"): "X|U"
    // where the path jumps, the two names apart.
    const label = (x, name, k, t, anchor) => {
      if (name) text(x, height - 8, name, ` text-anchor="${anchor}" data-tick="${k},${t}"`);
    };
    segments.forEach((segment, k) => {
      const x = X(segment.distances[0]), previous = segments[k - 1];
      line(x, top, x, top + h, theme.cell, ` stroke-opacity="0.5"`);
      if (!previous || previous.connected) label(x, segment.labels[0], k, 0, "middle");
      else {
        label(x - 3, previous.labels[1], k - 1, 1, "end");
        text(x, height - 8, "|", ` text-anchor="middle"`);
        label(x + 3, segment.labels[0], k, 0, "start");
      }
    });
    line(X(total), top, X(total), top + h, theme.cell, ` stroke-opacity="0.5"`);
    label(X(total), segments.at(-1).labels[1], segments.length - 1, 1, "middle");

    // Branches, then the selected one on top. Connected segments form groups:
    // the selected branch is followed within the groups where q lies.
    const groups = [];
    let group = 0;
    for (const segment of segments) { groups.push(group); if (!segment.connected) group++; }
    const places = pathPositions(segments, q);
    const highlight = new Map(); // group -> band index
    for (const place of places) {
      const at = bandsAt(segments[place.k], place.d);
      const band = at.reduce((best, f, b) => (Math.abs(f - frequency) < Math.abs(at[best] - frequency) ? b : best), 0);
      highlight.set(groups[place.k], band);
    }
    plot.groups = groups; plot.highlight = highlight;
    if (places.length) plot.band = highlight.get(groups[places[0].k]);
    const branch = (segment, b) => segment.distances.map((d, i) => `${r(X(d))},${r(Y(segment.frequencies[i][b]))}`).join(" ");
    segments.forEach((segment) => {
      for (let b = 0; b < segment.frequencies[0].length; b++) {
        shapes.push(`<polyline points="${branch(segment, b)}" fill="none" stroke="${theme.text}" stroke-opacity="0.55" stroke-width="1.2" stroke-linejoin="round"/>`);
      }
    });
    segments.forEach((segment, k) => {
      if (!highlight.has(groups[k])) return;
      shapes.push(`<polyline points="${branch(segment, highlight.get(groups[k]))}" fill="none" stroke="${theme.accent}" stroke-width="2.5" stroke-linejoin="round"/>`);
    });
    for (const place of places) {
      line(X(place.d), top, X(place.d), top + h, theme.accent, ` stroke-dasharray="4 3"`);
      shapes.push(`<circle cx="${r(X(place.d))}" cy="${r(Y(frequency))}" r="4.5" fill="${theme.accent}" stroke="${theme.halo}" stroke-width="1.5"/>`);
    }
    const qLabel = `(${q.map((x) => String(Number(x.toFixed(4)))).join(", ")})`;
    note.textContent = places.length ? "" : `q = ${qLabel} is not on the path`;

    // DOS: total filled, elements as lines in their colours (several only).
    if (plot.dos) {
      const fs = plot.dos.frequencies, totalDos = plot.dos.total;
      const max = Math.max(1e-12, ...totalDos);
      const DX = (v) => dosLeft + (v / max) * dosWidth;
      const inside = fs.map((f, i) => [f, i]).filter(([f]) => f * factor >= lo && f * factor <= hi);
      if (inside.length) {
        const points = inside.map(([f, i]) => `${r(DX(totalDos[i]))},${r(Y(f))}`);
        shapes.push(`<polygon points="${r(dosLeft)},${r(Y(inside[0][0]))} ${points.join(" ")} ${r(dosLeft)},${r(Y(inside.at(-1)[0]))}" fill="${theme.text}" fill-opacity="0.15" stroke="${theme.text}" stroke-opacity="0.7"/>`);
        const elements = Object.entries(plot.dos.elements);
        if (elements.length > 1) {
          for (const [symbol, values] of elements) {
            shapes.push(`<polyline points="${inside.map(([f, i]) => `${r(DX(values[i]))},${r(Y(f))}`).join(" ")}" fill="none" stroke="${escapeXml(elementColor(symbol))}" stroke-width="1.5"/>`);
          }
          elements.forEach(([symbol], k) => {
            shapes.push(`<rect x="${r(dosLeft + dosWidth - 34)}" y="${r(top + 6 + k * 14)}" width="9" height="9" fill="${escapeXml(elementColor(symbol))}"/>`);
            text(dosLeft + dosWidth - 21, top + 14 + k * 14, symbol);
          });
        }
      }
      line(dosLeft, Y(frequency), dosLeft + dosWidth, Y(frequency), theme.accent, ` stroke-dasharray="4 3"`);
      // The mesh only where it fits (about 6.5 px a character).
      const dosLabel = `DOS ${plot.dos.mesh.join("×")}`;
      text(dosLeft + dosWidth / 2, height - 8, dosLabel.length * 6.5 < dosWidth ? dosLabel : "DOS", ` text-anchor="middle"`);
      shapes.push(`<rect x="${r(dosLeft)}" y="${top}" width="${r(dosWidth)}" height="${h}" fill="none" stroke="${theme.cell}"/>`);
    }
    shapes.push(`<rect x="${left}" y="${top}" width="${r(bandWidth)}" height="${h}" fill="none" stroke="${theme.cell}"/>`);
    text(14, top + h / 2, `Frequency (${unit})`, ` text-anchor="middle" transform="rotate(-90 14 ${r(top + h / 2)})"`);
    plot.geometry = { left, top, bandWidth, h, total, lo, hi, factor };
    slider.style.marginLeft = `${left}px`;
    slider.style.width = `${r(bandWidth)}px`;
    // Follow q, unless it is where the slider is already (X twice on a path).
    if (!plot.sliding && places.length) {
      if (!places.some((place) => Math.abs(place.d - plot.sliderD) < 1e-6 * total)) plot.sliderD = places[0].d;
      slider.value = String(Math.round((plot.sliderD / total) * 1000));
    }
    plot.svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">\n${shapes.join("\n")}\n</svg>`;
    figure.innerHTML = plot.svg;
  }

  // The point at path distance d: within a few pixels of a labelled point,
  // that point exactly (Γ is q = 0).
  const pointAt = (d) => {
    const g = plot.geometry, segments = plot.bands.segments;
    const k = Math.max(0, segments.findIndex((s) => d <= s.distances.at(-1) + 1e-9));
    const segment = segments[k], d0 = segment.distances[0], d1 = segment.distances.at(-1);
    const snap = (4 / g.bandWidth) * g.total;
    const t = d - d0 < snap ? 0 : d1 - d < snap ? 1 : Math.min(1, Math.max(0, (d - d0) / (d1 - d0)));
    return { k, t, segment, d: d0 + t * (d1 - d0) };
  };
  // One request at a time; while one runs, only the latest pick waits.
  let busy = false, queued = null;
  const send = async (pick) => {
    if (busy) { queued = pick; return; }
    busy = true;
    try { await onPick(...pick); } finally {
      busy = false;
      if (queued) { const next = queued; queued = null; send(next); }
    }
  };
  // q at a point, with the selected branch there (frequency null: the
  // closest mode to `frequency` given).
  const pick = ({ k, t, segment, d }, frequency = null) => {
    plot.sliderD = d;
    const q = add(segment.start, mul(sub(segment.end, segment.start), t)).map((v) => Math.round(v * 1e4) / 1e4);
    if (frequency === null) {
      const band = plot.highlight?.get(plot.groups[k]) ?? plot.band ?? 0;
      frequency = bandsAt(segment, d)[band];
    }
    send([q, frequency, sub(segment.end, segment.start)]);
  };

  figure.addEventListener("click", (event) => {
    const g = plot.geometry;
    if (!g) return;
    const tick = event.target.closest?.("[data-tick]");
    if (tick) {
      const [k, t] = tick.dataset.tick.split(",").map(Number), segment = plot.bands.segments[k];
      pick({ k, t, segment, d: t ? segment.distances.at(-1) : segment.distances[0] });
      return;
    }
    // A click on the bands: q at that point of the path, the closest mode there.
    const box = figure.getBoundingClientRect();
    const x = event.clientX - box.left, y = event.clientY - box.top;
    if (x < g.left || x > g.left + g.bandWidth || y < g.top || y > g.top + g.h) return;
    pick(pointAt(((x - g.left) / g.bandWidth) * g.total), (g.hi - ((y - g.top) / g.h) * (g.hi - g.lo)) / g.factor);
  });
  slider.addEventListener("input", () => {
    if (!plot.geometry) return;
    plot.sliding = true;
    pick(pointAt((Number(slider.value) / 1000) * plot.geometry.total));
  });
  slider.addEventListener("change", () => { plot.sliding = false; });
  new ResizeObserver(() => draw()).observe(figure);
  return plot;
}

// ---------------------------------------------------------------- viewer panel

// One panel: a structure, its overlay data, a renderer, and pointer interaction.
function createPanel(host) {
  const panel = { structure: null, overlay: null, forces: null, motion: null, scene: null, renderer: null };
  const stage = el("div", { class: "viewer-stage" });
  const tooltip = el("div", { class: "tooltip" });
  host.append(stage, tooltip);
  panel.stage = stage;
  panel.renderer = createCanvasRenderer(stage);
  panel.rebuild = () => {
    if (!panel.structure || !panel.overlay) return;
    panel.scene = buildScene(panel.structure, panel.overlay, panel.forces, viewerPrefs.rings.show ? panel.ringData : null, panel.motion);
    panel.draw();
  };
  panel.draw = () => {
    if (!panel.scene || !panel.renderer || !stage.clientWidth) return;
    if (!sharedView.R) sharedView.R = presetRotation(panel.structure, "top");
    if (!sharedView.scale) Object.assign(sharedView, fitView(panel.scene, stage.clientWidth, stage.clientHeight));
    panel.renderer.draw(panel.scene, { hoverAxis });
  };
  // Tripod axis under the pointer (highlighted; a click looks along it).
  let hoverAxis = null;
  const axisAt = (event) => {
    if (!panel.scene || panel.scene.tripod === "off") return null;
    const box = stage.getBoundingClientRect();
    return tripodHit(tripodLayout(panel.scene, box.height), event.clientX - box.left, event.clientY - box.top);
  };
  panel.fit = () => {
    if (!panel.scene) return;
    Object.assign(sharedView, fitView(panel.scene, stage.clientWidth, stage.clientHeight));
  };

  // Pointer: drag rotates; right-, middle- or shift-drag pans; wheel zooms;
  // hover inspects atoms.
  // A left click that barely moves picks the atom under the pointer
  // (panel.onPick, for measurements) instead of rotating.
  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    drag = { x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 1 || event.button === 2,
      click: event.button === 0 && !event.shiftKey, moved: 0 };
    stage.setPointerCapture(event.pointerId);
    if (event.button === 1) event.preventDefault(); // no autoscroll
  });
  stage.addEventListener("contextmenu", (event) => event.preventDefault());
  stage.addEventListener("pointermove", (event) => {
    if (drag) {
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      drag.x = event.clientX; drag.y = event.clientY;
      drag.moved += Math.abs(dx) + Math.abs(dy);
      if (drag.pan) sharedView.pan = [sharedView.pan[0] + dx, sharedView.pan[1] + dy];
      else { rotateScreen("y", dx * 0.01); rotateScreen("x", dy * 0.01); }
      tooltip.style.display = "none";
      viewChanged();
      return;
    }
    hover(event);
  });
  stage.addEventListener("pointerup", (event) => {
    const click = drag?.click && drag.moved < 4;
    drag = null;
    if (!click) return;
    const axis = axisAt(event);
    if (axis) { panel.onAxis?.(axis, panel); return; }
    if (!panel.onPick) return;
    const atom = atomAt(event);
    if (atom) {
      // The periodic image of the clicked copy, relative to the atom itself.
      const offset = sub(atom.position, panel.structure.positions[atom.index]);
      const image = fractional(reciprocal(panel.structure.cell), offset).map(Math.round);
      panel.onPick({ index: atom.index, image, symbol: panel.structure.symbols[atom.index], count: panel.structure.symbols.length });
    }
  });
  stage.addEventListener("pointerleave", () => {
    tooltip.style.display = "none";
    if (hoverAxis) { hoverAxis = null; stage.classList.remove("on-axis"); panel.draw(); }
  });
  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    sharedView.scale *= Math.exp(-event.deltaY * 0.0015);
    viewChanged();
  }, { passive: false });

  // The front-most atom under the pointer, or null.
  function atomAt(event) {
    if (!panel.scene) return null;
    const box = stage.getBoundingClientRect();
    const mx = event.clientX - box.left, my = event.clientY - box.top;
    const project = projector(panel.scene, box.width, box.height);
    let best = null;
    for (const atom of panel.scene.atoms) {
      const [x, y, z] = project(atom.position);
      const r = atom.radius * sharedView.scale;
      if ((x - mx) ** 2 + (y - my) ** 2 <= r * r && (!best || z > best.z)) best = { atom, z };
    }
    return best?.atom ?? null;
  }

  // The front-most shown ring under the pointer, or null.
  function ringAt(event) {
    if (!panel.scene?.rings.length) return null;
    const box = stage.getBoundingClientRect();
    const project = projector(panel.scene, box.width, box.height);
    const point = [event.clientX - box.left, event.clientY - box.top];
    let best = null;
    for (const ring of panel.scene.rings) {
      const points = ring.points.map(project);
      const z = points.reduce((m, q) => m + q[2], 0) / points.length;
      if ((!best || z > best.z) && insidePolygon(point, points)) best = { ring: ring.ring, z };
    }
    return best?.ring ?? null;
  }

  function hover(event) {
    const axis = axisAt(event);
    if (axis !== hoverAxis) { hoverAxis = axis; stage.classList.toggle("on-axis", Boolean(axis)); panel.draw(); }
    let lines;
    const atom = axis ? null : atomAt(event);
    if (axis) {
      lines = [[`View along ${axis}`, "click again for the opposite side"]];
    } else if (atom) {
      lines = panel.overlay.describe(atom.index);
      const forces = panel.forces, i = atom.index;
      if (forces) {
        lines.push(forces.included[i]
          ? [`${formatNumber(forces.magnitudes[i])}${forces.unit ? ` ${forces.unit}` : ""}`, `|${forces.name}|`]
          : ["not included", `in ${forces.name}`]);
      }
    } else {
      const ring = ringAt(event);
      if (!ring) { tooltip.style.display = "none"; return; }
      const counts = {};
      for (const i of ring.atoms) counts[panel.structure.symbols[i]] = (counts[panel.structure.symbols[i]] ?? 0) + 1;
      lines = [[ring.label, `ring (size in ${panel.scene.ringData.unit})`],
        [Object.entries(counts).map(([symbol, n]) => `${n} ${symbol}`).join(", "), "on the ring"]];
      if (ring.area !== null) lines.push([`${ring.area.toFixed(1)} Å²`, "area in the a–b plane"]);
      if (ring.inside.length) lines.push([ring.inside.map((i) => `${panel.structure.symbols[i]}${i}`).join(", "), "inside"]);
    }
    const box = stage.getBoundingClientRect();
    const mx = event.clientX - box.left, my = event.clientY - box.top;
    tooltip.replaceChildren(...lines.map(([value, label]) => el("div", {}, el("strong", {}, value), label ? el("span", { class: "muted" }, ` ${label}`) : null)));
    tooltip.style.display = "block";
    tooltip.style.left = `${Math.min(mx + 14, box.width - tooltip.offsetWidth)}px`;
    tooltip.style.top = `${Math.max(my - tooltip.offsetHeight - 8, 0)}px`;
  }

  new ResizeObserver(() => panel.draw()).observe(stage);
  panel.dispose = () => panel.renderer?.dispose();
  return panel;
}

// ---------------------------------------------------------------- overlays

// Movies load at most this many frames by default; larger ranges can stall.
// A range holds at most MOVIE_MAX_FRAMES, which the structure cache keeps.
const MOVIE_FRAMES = 1000;
const MOVIE_MAX_FRAMES = 10000;
// Chosen movie frame ranges per step list, kept while browsing.
const movieRanges = new Map();
// The last loaded movie ({ key, frames, scales }), so Play after a step
// resumes without loading or rescaling its frames again.
let lastMovie = null;

// Step lists, kept while browsing (the server is read-only): stepping then
// does not fetch a list of thousands of structures again.
const relatedCache = new Map();
function loadRelatedList(key, path) {
  if (!relatedCache.has(key)) {
    if (relatedCache.size > 20) relatedCache.clear();
    const load = api(path);
    load.catch(() => relatedCache.delete(key));
    relatedCache.set(key, load);
  }
  return relatedCache.get(key);
}

// Structures loaded as movie frames, kept for replaying (the server is read-only).
const structureCache = new Map();
function loadStructure(id) {
  if (!structureCache.has(id)) {
    // Drop the oldest entries, so a loading movie keeps its newest frames.
    for (const old of structureCache.keys()) {
      if (structureCache.size < MOVIE_MAX_FRAMES) break;
      structureCache.delete(old);
    }
    const load = api(`structures/${encodeURIComponent(id)}`);
    load.catch(() => structureCache.delete(id));
    structureCache.set(id, load);
  }
  return structureCache.get(id);
}

const vectorCache = new Map();
function loadVector(evaluationId, name) {
  const key = `${evaluationId}/${name}`;
  if (!vectorCache.has(key)) {
    const load = api(`evaluations/${encodeURIComponent(evaluationId)}/vectors/${encodeURIComponent(name)}`);
    load.catch(() => vectorCache.delete(key));
    vectorCache.set(key, load);
  }
  return vectorCache.get(key);
}

// Per-atom arrays, info and metadata of a structure (api .../extras), loaded
// only when shown: added to the structure object itself, which is returned.
const extrasCache = new Map();
function withExtras(s) {
  if (s.arrays) return Promise.resolve(s);
  if (!extrasCache.has(s.id)) {
    if (extrasCache.size > 2000) extrasCache.clear();
    const load = api(`structures/${encodeURIComponent(s.id)}/extras`);
    load.catch(() => extrasCache.delete(s.id));
    extrasCache.set(s.id, load);
  }
  return extrasCache.get(s.id).then(({ arrays, info, metadata }) => Object.assign(s, { arrays, info, metadata }));
}

const atomValueCache = new Map();
function loadAtomValues(evaluationId, name) {
  const key = `${evaluationId}/${name}`;
  if (!atomValueCache.has(key)) {
    if (atomValueCache.size > 2000) atomValueCache.clear();
    const load = api(`evaluations/${encodeURIComponent(evaluationId)}/atoms/${encodeURIComponent(name)}`);
    load.catch(() => atomValueCache.delete(key));
    atomValueCache.set(key, load);
  }
  return atomValueCache.get(key);
}

// ---------------------------------------------------------------- atomic properties

// Properties to colour atoms by, for structure s: values derived from the
// geometry, per-atom arrays stored with the structure (ASE arrays such as tags
// or initial_magmoms, and per-atom lists in its info or metadata), and per-atom
// properties of its evaluations. A choice ({ source, name, ... }) is found
// again on other structures by name, and evaluations by method (matchMethod).
//   option: { key, group, label, choice, kind: "number" | "vector" | "text", unit }
const DERIVED_PROPERTIES = [
  ["coordination", "Coordination number (bond cutoffs)"], ["ring", "Smallest ring size (ring settings)"],
  ["index", "Atom index"], ["x", "Cartesian x (Å)"], ["y", "Cartesian y (Å)"], ["z", "Cartesian z (Å)"],
  ["fa", "Fractional a"], ["fb", "Fractional b"], ["fc", "Fractional c"],
];
const VECTOR_COMPONENTS = [["norm", "magnitude"], ["x", "x"], ["y", "y"], ["z", "z"]];
const choiceKey = (choice) => (choice ? JSON.stringify([choice.source, choice.origin ?? null, choice.method ?? null, choice.name]) : "");

function propertyOptions(s) {
  const options = DERIVED_PROPERTIES.map(([name, label]) => ({ group: "From the geometry", label, kind: "number",
    choice: { source: "derived", name } }));
  for (const array of s.arrays ?? []) {
    options.push({ group: "Stored with the structure", label: array.source === "arrays" ? array.name : `${array.name} (${array.source})`,
      kind: array.kind, choice: { source: "array", origin: array.source, name: array.name } });
  }
  for (const e of s.evaluations) {
    for (const p of [...(e.atom_values ?? []), ...e.vectors]) {
      options.push({ group: `Evaluation ${evaluationLabel(e)}`, label: p.unit ? `${p.name} (${p.unit})` : p.name, unit: p.unit,
        kind: e.vectors.includes(p) ? "vector" : "number",
        choice: { source: "evaluation", name: p.name, spec: e.spec_hash, method: e.method, id: e.id } });
    }
  }
  for (const option of options) option.key = choiceKey(option.choice);
  return options;
}

// One value per atom of structure s for a choice (numbers, or text; null where
// missing), with a label and unit; null when s does not have the property.
async function propertyValues(s, choice, component = "norm") {
  if (!choice) return null;
  const pick = (vector) => (component === "norm" ? norm(vector) : vector["xyz".indexOf(component)]);
  const componentLabel = (name) => (component === "norm" ? `|${name}|` : `${name}_${component}`);
  if (choice.source === "derived") {
    const label = DERIVED_PROPERTIES.find(([name]) => name === choice.name)?.[1] ?? choice.name;
    const P = s.positions;
    if (choice.name === "coordination") {
      const counts = P.map(() => 0);
      for (const bond of neighbours(s, viewerPrefs.cutoffs)) counts[bond.i] += 1;
      return { values: counts, label };
    }
    if (choice.name === "ring") {
      const smallest = P.map(() => null);
      for (const ring of (await loadRings(s)).rings) for (const i of ring.atoms) smallest[i] = Math.min(smallest[i] ?? Infinity, ring.size);
      return { values: smallest, label };
    }
    if (choice.name === "index") return { values: P.map((p, i) => i), label };
    const k = ["x", "y", "z"].indexOf(choice.name);
    if (k >= 0) return { values: P.map((p) => p[k]), label, unit: "Å" };
    const recip = reciprocal(s.cell);
    const f = ["fa", "fb", "fc"].indexOf(choice.name);
    return { values: P.map((p) => fractional(recip, p)[f]), label };
  }
  if (choice.source === "array") {
    await withExtras(s);
    const array = (s.arrays ?? []).find((a) => a.name === choice.name && a.source === choice.origin)
      ?? (s.arrays ?? []).find((a) => a.name === choice.name);
    if (!array) return null;
    if (array.kind === "vector") return { values: array.values.map((v) => (v.includes(null) ? null : pick(v))), label: componentLabel(array.name) };
    return { values: array.values, label: array.name, text: array.kind === "text" };
  }
  const has = (e) => (e.atom_values ?? []).some((p) => p.name === choice.name) || e.vectors.some((v) => v.name === choice.name);
  const candidates = s.evaluations.filter(has);
  const e = candidates.find((x) => x.id === choice.id) ?? candidates.find((x) => x.spec_hash === choice.spec)
    ?? candidates.find((x) => x.method === choice.method);
  if (!e) return null;
  if (e.vectors.some((v) => v.name === choice.name)) {
    const data = await loadVector(e.id, choice.name);
    return { values: data.values.map(pick), label: `${componentLabel(choice.name)} (${e.method})`, unit: data.unit };
  }
  const data = await loadAtomValues(e.id, choice.name);
  return { values: data.values, label: `${choice.name} (${e.method})`, unit: data.unit };
}

// Category colours: integers keep their colour on every structure (value
// modulo the palette); other values get the next free colour, in the order seen.
const CATEGORY_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7", "#008300", "#e34948", "#00a3c4", "#8a6d3b"];
const categorySlots = new Map();
function categoryColour(value) {
  let slot;
  if (typeof value === "number" && Number.isInteger(value)) slot = value;
  else {
    const key = String(value);
    if (!categorySlots.has(key)) categorySlots.set(key, categorySlots.size);
    slot = categorySlots.get(key);
  }
  return CATEGORY_COLOURS[((slot % CATEGORY_COLOURS.length) + CATEGORY_COLOURS.length) % CATEGORY_COLOURS.length];
}
// Whether values are read as categories: text always; numbers with "auto"
// when all are whole and there are at most 12 different ones.
function asCategories(values, kind, text) {
  if (text) return true;
  if (kind !== "auto") return kind === "categories";
  const present = values.filter((v) => v !== null && Number.isFinite(v));
  return present.length > 0 && present.every(Number.isInteger) && new Set(present).size <= 12;
}
// A number typed into a field, or null when blank or not a number.
const optionalNumber = (value) => (value.trim() === "" || !Number.isFinite(Number(value)) ? null : Number(value));
const valueText = (v) => (v === null || v === undefined ? "–" : typeof v === "number" ? formatNumber(v) : String(v));

// Scalars keep 10 significant digits: energies differ in late digits.
function scalarText(property) {
  if (!property) return "-";
  const value = Number.isFinite(property.value) ? String(Number(property.value.toPrecision(10))) : String(property.value);
  return property.unit ? `${value} ${property.unit}` : value;
}

const evaluationCache = new Map();

function propertyRow(p) {
  const stats = p.stats ?? {};
  const cell = (value) => el("td", { class: "num" }, value === undefined ? "-" : formatNumber(value));
  return el("tr", {},
    el("td", {}, p.name), el("td", {}, p.unit ?? "-"),
    el("td", {}, p.shape ? (p.shape.length ? p.shape.join(" × ") : "scalar") : "non-numeric"),
    el("td", { class: "num" }, "value" in p ? scalarText(p) : "-"),
    cell(stats.min), cell(stats.max), cell(stats.mean), cell(p.max_norm));
}

// Expanded row of the structure's evaluation table: method, provenance, and
// an overview of every stored property.
function evaluationDetailRow(evaluationId, colspan) {
  const inner = el("div", { class: "detail-inner" }, el("p", { class: "muted" }, "Loading…"));
  const load = evaluationCache.get(evaluationId) ?? api(`evaluations/${encodeURIComponent(evaluationId)}`);
  evaluationCache.set(evaluationId, load);
  load.then((detail) => {
    inner.replaceChildren(
      el("dl", { class: "facts" },
        el("dt", {}, "Evaluation ID"), el("dd", {}, idCell(detail.id)),
        el("dt", {}, "Method"), el("dd", {}, detail.method),
        el("dt", {}, "Created"), el("dd", {}, formatDate(detail.created_at))),
      el("div", { class: "table-wrap" }, el("table", { class: "stats" },
        el("thead", {}, el("tr", {}, ["Property", "Unit", "Shape", "Value", "Min", "Max", "Mean", "Max |v|"].map((h) => el("th", {}, h)))),
        el("tbody", {}, detail.properties.map(propertyRow)))),
      el("div", { class: "detail-grid" },
        treeCard("Method specification", detail.method_spec),
        treeCard("Evaluation provenance", detail.provenance)));
  }).catch((error) => {
    evaluationCache.delete(evaluationId);
    inner.replaceChildren(el("p", { class: "error" }, error.message));
  });
  return el("tr", { class: "detail-row" }, el("td", { colspan }, inner));
}

function evaluationLabel(evaluation) {
  const stage = evaluation.tags.find((t) => t.startsWith("stage:"));
  return `${evaluation.method} · ${evaluation.spec_hash}${stage ? ` · ${stage.slice(6)}` : ""}`;
}

// Per-atom heights along the surface normal.
function heights(structure) {
  const n = surfaceNormal(structure);
  return structure.positions.map((p) => dot(p, n));
}

// Default force-difference pair: two evaluations with a shared vector property,
// preferring different method families (e.g. DFT reference vs. MLIP).
function defaultPair(structure) {
  const candidates = structure.evaluations.filter((e) => e.vectors.length);
  for (const a of candidates) for (const b of candidates) {
    if (a !== b && a.family !== b.family && a.vectors.some((v) => b.vectors.some((w) => w.name === v.name))) {
      return a.family.toLowerCase() === "dft" ? [a.id, b.id] : [b.id, a.id];
    }
  }
  return candidates.length > 1 ? [candidates[0].id, candidates[1].id] : [null, null];
}

// A chosen method, to find again on other structures.
const methodChoice = (evaluation) => ({ spec: evaluation.spec_hash, method: evaluation.method });

// The evaluation with a chosen method among those with per-atom vectors (or
// with the given vector): the same full method spec if present, else the same
// method (name/identifier), whose parameters such as k-points can differ
// from structure to structure.
function matchMethod(evaluations, choice, vector = null) {
  if (!choice) return undefined;
  const candidates = evaluations.filter((e) => (vector ? e.vectors.some((v) => v.name === vector) : e.vectors.length));
  return candidates.find((e) => e.spec_hash === choice.spec) ?? candidates.find((e) => e.method === choice.method);
}

// The last chosen force-difference pair, if this structure has both methods.
function rememberedPair(structure) {
  const ids = (viewerPrefs.pairChoice ?? []).map((choice) => matchMethod(structure.evaluations, choice)?.id);
  return ids.length === 2 && ids.every(Boolean) && ids[0] !== ids[1] ? ids : null;
}

// ---------------------------------------------------------------- page

let currentPage = null;
// Larger related lists get a position field instead of one chip per structure.
const MAX_RELATED_CHIPS = 60;

async function renderStructurePage(structureId, params) {
  // Stepping from one structure page to the next keeps the page's and the
  // settings box's scroll positions, so the structure stays put on screen. The
  // old page stays visible until the new one is ready: a short "Loading…" page
  // would make the browser jump to the top.
  let scroll = currentPage?.scrollState?.() ?? null;
  currentPage?.dispose();
  currentPage = null;
  if (!scroll) setMain(el("p", { class: "muted" }, "Loading…"));
  let structure;
  try {
    structure = await withExtras(await api(`structures/${encodeURIComponent(structureId)}`));
  } catch (error) {
    setMain(el("p", { class: "error" }, error.message));
    return;
  }
  document.title = `STOMS · ${structure.formula}`;
  // Vibrational modes, for structures served from phonopy v_sim files.
  let modes = null;
  if (structure.has_modes) {
    try {
      modes = await api(`structures/${encodeURIComponent(structure.id)}/modes`);
    } catch (error) {
      modes = { error: error.message };
    }
  }
  const fromId = params.get("from");
  const fromAgg = fromId ? state.aggregations.find((a) => a.id === fromId) : null;
  const species = [...new Set(structure.symbols)].sort();
  const page = { panels: [], structures: [structure], pair: rememberedPair(structure) ?? defaultPair(structure), vector: "forces",
    disposed: false, forceData: [], overlayToken: 0 };
  currentPage = page;

  // Evaluation and per-atom vector behind force arrows and force colours: the
  // method spec in the URL, else the method last chosen in this browser (see
  // matchMethod), else a default.
  const vectorEvaluations = structure.evaluations.filter((e) => e.vectors.length);
  const defaultVectorName = (e) => (e ? (e.vectors.some((v) => v.name === "forces") ? "forces" : e.vectors[0].name) : null);
  const urlSpec = params.get("forces");
  const remembered = viewerPrefs.forceChoice;
  const requestedForces = (urlSpec ? vectorEvaluations.find((e) => e.spec_hash === urlSpec) : undefined)
    ?? matchMethod(vectorEvaluations, remembered, remembered?.name) ?? matchMethod(vectorEvaluations, remembered);
  const initialForces = requestedForces ?? vectorEvaluations.find((e) => e.vectors.some((v) => v.name === "forces")) ?? vectorEvaluations[0] ?? null;
  const rememberedName = requestedForces && remembered?.method === requestedForces.method
    && requestedForces.vectors.some((v) => v.name === remembered.name) ? remembered.name : null;
  page.force = { evaluation: initialForces, name: rememberedName ?? defaultVectorName(initialForces), explicit: Boolean(requestedForces) };

  // What ←/→ step through: "tags" (structures sharing a tag prefix) or an
  // aggregation ID. Defaults to the aggregation the page was opened from.
  const defaultCycle = fromId ?? "tags";
  const cycle = params.get("cycle") ?? defaultCycle;
  const hash = (id, extra = {}) => {
    const query = new URLSearchParams();
    if (fromId) query.set("from", fromId);
    const compare = "compare" in extra ? extra.compare : params.get("compare");
    if (compare) query.set("compare", compare);
    const cycleValue = "cycle" in extra ? extra.cycle : cycle;
    if (cycleValue !== defaultCycle) query.set("cycle", cycleValue);
    // Which panel steps (and plays) when comparing: "right" keeps the left as reference.
    const side = "side" in extra ? extra.side : params.get("side");
    if (compare && side === "right") query.set("side", "right");
    if (page.force.explicit && page.force.evaluation) query.set("forces", page.force.evaluation.spec_hash);
    const text = query.toString();
    return `#/structures/${encodeURIComponent(id)}${text ? `?${text}` : ""}`;
  };

  // --- layout
  const stages = el("div", { class: "viewer-panels" });
  const legend = el("div", { class: "viewer-legend" });
  const ringLegend = el("div", { class: "ring-legend" });
  // Elements of the shown structures with their atom counts: click hides,
  // right-click edits colour and size (see renderElementBar).
  const elementBar = el("div", { class: "element-bar", role: "toolbar", "aria-label": "Elements" });
  // Comparison: with what, which panel steps, swap (see renderCompareBar).
  const compareBar = el("div", { class: "compare-bar" });
  const status = el("p", { class: "muted viewer-status" });
  const controls = el("aside", { class: "viewer-controls" });
  // Sits above the figure so stepping and the structure stay in view together.
  const relatedSection = el("section", { class: "related-bar", "aria-label": "Related structures" });
  const evaluationsSection = el("section");
  // Beside the structure, the settings box is as tall as the structure (not
  // the phonon plot) and scrolls on its own, so both end at the same line and
  // the structure stays in view; in one column the settings are part of the
  // page. The phonon plot joins the structure in `figures`: below it, or
  // beside it (vibration.plotSide).
  // What a click on an atom does (measure or select), whichever tab is open.
  const clickMode = el("div", { class: "click-mode", role: "status" });
  const viewerMain = el("div", { class: "viewer-main" }, clickMode, stages, el("div", { class: "viewer-footer" }, elementBar, legend, ringLegend), status);
  const figures = el("div", { class: "viewer-figures" }, viewerMain);
  const wide = window.matchMedia("(min-width: 1001px)");
  const fitSettings = () => {
    controls.style.maxHeight = wide.matches ? `${Math.max(320, viewerMain.offsetHeight)}px` : "";
  };
  const settingsFit = new ResizeObserver(fitSettings);
  settingsFit.observe(viewerMain);
  wide.addEventListener("change", fitSettings);

  // Select this structure in the aggregation it was opened from (shared with
  // the aggregation page's member checkboxes, for viewing and export).
  const pickField = el("span", { class: "muted" }, "…");
  if (fromAgg) {
    loadRelatedList(`aggregation:${fromAgg.id}`,
      `structures/${encodeURIComponent(structure.id)}/related?aggregation=${encodeURIComponent(fromAgg.id)}`).then((related) => {
      const member = related.structures.find((r) => r.id === structure.id);
      if (!member) { pickField.textContent = `not a member of ${fromAgg.name}`; return; }
      const note = el("span", { class: "muted" });
      const showCount = () => { note.textContent = ` (${picksOf(fromAgg.id).size} selected in ${fromAgg.name})`; };
      const box = el("input", { type: "checkbox", checked: picksOf(fromAgg.id).has(member.ordinal), onchange: () => {
        const picks = picksOf(fromAgg.id);
        if (box.checked) picks.add(member.ordinal); else picks.delete(member.ordinal);
        savePicks(fromAgg.id, picks);
        showCount();
      } });
      showCount();
      pickField.replaceChildren(el("label", { class: "check inline-check" }, box, "Selected"), note);
    }).catch(() => { pickField.textContent = "-"; });
  }

  const heading = el("h1", {}, structure.formula, el("span", { class: "muted" }, ` · ${structure.positions.length} atoms`));
  setMain(
    fromAgg ? el("p", {}, el("a", { href: `#/aggregations/${encodeURIComponent(fromAgg.id)}` }, `← ${fromAgg.name}`)) : null,
    heading,
    el("dl", { class: "facts compact" },
      el("div", {}, el("dt", {}, "Structure"), el("dd", {}, idCell(structure.id))),
      el("div", {}, el("dt", {}, "Source"), el("dd", {}, structure.source || "-")),
      el("div", {}, el("dt", {}, "Tags"), el("dd", {}, structure.tags.length ? structure.tags.join(", ") : "-")),
      // Pages served with serve --link-page whose manifest lists this structure.
      structure.linked_pages.length ? el("div", {}, el("dt", {}, "Linked pages"), el("dd", { class: "linked-pages" },
        structure.linked_pages.map((p) => el("a", { href: p.url, target: "_blank", rel: "noopener", title: p.description || null }, `${p.title} ↗`)))) : null,
      fromAgg ? el("div", {}, el("dt", {}, "Selection"), el("dd", {}, pickField)) : null),
    el("div", { class: "nav-card" }, relatedSection, compareBar),
    el("div", { class: "viewer-layout" }, figures, controls),
    evaluationsSection);

  // --- panels
  const addPanel = (s) => {
    const host = el("div", { class: "viewer-panel" });
    const panel = createPanel(host);
    panel.structure = s;
    panel.host = host;
    stages.append(host);
    page.panels.push(panel);
    return panel;
  };
  addPanel(structure);
  const compareId = params.get("compare");
  if (compareId && compareId !== structure.id) {
    try {
      const other = await withExtras(await api(`structures/${encodeURIComponent(compareId)}`));
      page.structures.push(other);
      addPanel(other);
    } catch (error) {
      status.textContent = `Compare structure: ${error.message}`;
    }
  }
  stages.classList.toggle("two", page.panels.length === 2);
  // The panel that steps through the list and plays movies (0 left, 1 right).
  page.side = page.panels.length > 1 && params.get("side") === "right" ? 1 : 0;
  page.originals = [...page.structures];
  // Captions name both structures (with their files) and mark the reference;
  // the other panel is the one that steps.
  const captionOf = (k) => {
    const panel = page.panels[k];
    if (page.panels.length < 2) return;
    panel.caption ??= panel.host.insertBefore(el("div", { class: "viewer-caption" }), panel.host.firstChild);
    panel.caption.replaceChildren(
      ...(k === page.side ? [] : [el("span", { class: "panel-role" }, "reference")]),
      ...panelCaption(page.structures[k]));
  };
  page.panels.forEach((_, k) => captionOf(k));

  page.scrollState = () => ({ page: window.scrollY, settings: controls.scrollTop, related: relatedSection.offsetHeight });
  // The step bar loads last; until then it keeps the previous page's height.
  if (scroll) relatedSection.style.minHeight = `${scroll.related}px`;
  // Stop restoring once the reader scrolls themselves (scroll positions alone
  // cannot tell: the browser also shifts them while the page is built).
  const readerScrolls = ["wheel", "touchmove", "keydown"];
  const stopRestoring = () => { scroll = null; };
  for (const type of readerScrolls) window.addEventListener(type, stopRestoring, { passive: true });
  const restoreScroll = () => {
    if (!scroll || page.disposed) return;
    fitSettings(); // final layout first, so nothing shifts after scrolling
    window.scrollTo(0, scroll.page);
    controls.scrollTop = scroll.settings;
  };

  // Resize grip at the panels' bottom-right corner: sets the width of the
  // panel area and the height of each structure panel (double-click: automatic).
  const sizeLabel = el("div", { class: "resize-size" });
  const grip = el("div", { class: "resize-grip", title: "Drag to resize; double-click for the automatic size",
    role: "separator", "aria-label": "Resize structure panel" });
  stages.append(grip, sizeLabel);
  const applyPanelSize = () => {
    const { width, height } = viewerPrefs.panelSize;
    if (height) stages.style.setProperty("--stage-height", `${height}px`);
    else stages.style.removeProperty("--stage-height");
    stages.style.maxWidth = width ? `${width}px` : "";
  };
  applyPanelSize();
  let resize = null;
  grip.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    resize = { x: event.clientX, y: event.clientY, width: stages.clientWidth, height: page.panels[0].stage.clientHeight,
      available: stages.parentElement.clientWidth };
    sizeLabel.classList.add("shown");
  });
  grip.addEventListener("pointermove", (event) => {
    if (!resize) return;
    const width = Math.round(Math.max(240, Math.min(resize.available, resize.width + event.clientX - resize.x)));
    const height = Math.round(Math.max(160, Math.min(2400, resize.height + event.clientY - resize.y)));
    viewerPrefs.panelSize = { width: width >= resize.available ? null : width, height };
    applyPanelSize();
    sizeLabel.textContent = `${page.panels[0].stage.clientWidth} × ${page.panels[0].stage.clientHeight} px`;
  });
  const endResize = () => {
    if (!resize) return;
    resize = null;
    sizeLabel.classList.remove("shown");
    savePrefs();
  };
  grip.addEventListener("pointerup", endResize);
  grip.addEventListener("pointercancel", endResize);
  grip.addEventListener("dblclick", () => {
    viewerPrefs.panelSize = { width: null, height: null };
    applyPanelSize(); savePrefs();
  });

  const redrawAll = () => page.panels.forEach((p) => p.draw());
  sharedView.listeners.clear();
  sharedView.listeners.add(redrawAll);

  // A chosen evaluation (or a { spec, method } choice), found on structure s
  // (another movie frame or a compared structure): the same evaluation, else
  // the same method.
  const evaluationOn = (s, chosen, vector) => (chosen
    ? s.evaluations.find((e) => e.id === chosen.id) ?? matchMethod(s.evaluations, { spec: chosen.spec ?? chosen.spec_hash, method: chosen.method }, vector)
    : undefined);

  // The forces to show: the evaluation chosen on this page; if this structure
  // has none (a movie frame without forces), the last choice in this browser,
  // else the first method with per-atom vectors among the movie's frames.
  function forceTarget() {
    if (page.force.evaluation) return { chosen: page.force.evaluation, name: page.force.name };
    const remembered = viewerPrefs.forceChoice;
    if (remembered) return { chosen: remembered, name: remembered.name ?? "forces" };
    for (const frame of page.movie?.frames ?? []) {
      const e = frame.evaluations.find((x) => x.vectors.length);
      if (e) return { chosen: methodChoice(e), name: e.vectors.some((v) => v.name === "forces") ? "forces" : e.vectors[0].name };
    }
    return { chosen: null, name: null };
  }

  // Force data of one structure for arrows, force colours and tooltips.
  async function forceDataFor(s) {
    const { chosen, name } = forceTarget();
    const e = evaluationOn(s, chosen, name);
    if (!e) return null;
    const data = await loadVector(e.id, name);
    return { name, unit: data.unit ?? "", method: e.method, vectors: data.values,
      magnitudes: data.values.map(norm), included: forceIncluded(s) };
  }
  async function loadForceData() {
    if (!forceTarget().chosen || !(viewerPrefs.arrows.show || viewerPrefs.colour === "force")) return page.structures.map(() => null);
    return Promise.all(page.structures.map(forceDataFor));
  }

  // The chosen force-difference pair: evaluations of this page's structure,
  // else (a movie frame without them) the last pair chosen in this browser.
  const chosenPair = () => {
    const pair = page.pair.map((id) => structure.evaluations.find((e) => e.id === id));
    return pair.every(Boolean) ? pair : viewerPrefs.pairChoice ?? [undefined, undefined];
  };
  // Per-atom |difference| of the pair's vectors on one structure, or null.
  async function diffFor(s) {
    const [a, b] = chosenPair();
    const x = evaluationOn(s, a, page.vector), y = evaluationOn(s, b, page.vector);
    if (!x || !y) return null;
    const [vx, vy] = await Promise.all([loadVector(x.id, page.vector), loadVector(y.id, page.vector)]);
    return { unit: vx.unit, values: vx.values.map((f, i) => norm(sub(f, vy.values[i]))), included: forceIncluded(s) };
  }

  // Colour scale limits. Normally over the shown structures; while a movie is
  // loaded, over all its frames (and a compared structure), fixed for the movie.
  // The structures shown beside a movie (the other panel), if any.
  const moviePeers = () => page.structures.filter((_, k) => k !== page.movie.side);
  const includedValues = (d) => (d ? d.values.filter((v, i) => d.included[i]) : []);
  async function scaleMax(kind, compute, shown) {
    if (!page.movie) return Math.max(1e-9, ...shown.flatMap(includedValues));
    // Keyed by methods, not evaluation IDs, so a kept movie (lastMovie) reuses
    // its scales on the next structure's page.
    const method = (e) => (e ? [e.spec ?? e.spec_hash, e.method] : null);
    const target = forceTarget();
    const key = JSON.stringify([kind, method(target.chosen), target.name, chosenPair().map(method), page.vector,
      viewerPrefs.forceFollowsSlice, viewerPrefs.slice, viewerPrefs.hiddenElements, viewerPrefs.forceSlice,
      viewerPrefs.forceHiddenElements, moviePeers().map((s) => s.id)]);
    if (!page.movie.scales.has(key)) {
      const all = [...page.movie.frames, ...moviePeers()];
      const load = Promise.all(all.map(compute)).then((data) => Math.max(1e-9, ...data.flatMap(includedValues)));
      load.catch(() => page.movie?.scales.delete(key));
      page.movie.scales.set(key, load);
    }
    return page.movie.scales.get(key);
  }
  const forceValues = async (s) => { const d = await forceDataFor(s); return d && { values: d.magnitudes, included: d.included }; };

  // Range of a property's numbers over the shown atoms (slice and elements);
  // while a movie is loaded, over all its frames (and a compared structure),
  // fixed for the movie like scaleMax.
  const shownAtoms = (s) => {
    const recip = reciprocal(s.cell), hidden = new Set(viewerPrefs.hiddenElements);
    return s.positions.map((p, i) => !hidden.has(s.symbols[i]) && inSlice(fractional(recip, p)));
  };
  const shownNumbers = (s, d) => {
    if (!d || d.text) return [];
    const shown = shownAtoms(s);
    return d.values.filter((v, i) => shown[i] && v !== null && Number.isFinite(v));
  };
  const extent = (values) => values.reduce(([lo, hi], v) => [Math.min(lo, v), Math.max(hi, v)], [Infinity, -Infinity]);
  async function propertyRange(data) {
    if (!page.movie) return extent(page.structures.flatMap((s, k) => shownNumbers(s, data[k])));
    const { choice, component } = viewerPrefs.property;
    const key = JSON.stringify(["property", choiceKey(choice), component, viewerPrefs.slice, viewerPrefs.hiddenElements,
      choice?.name === "coordination" ? viewerPrefs.cutoffs : null, choice?.name === "ring" ? viewerPrefs.rings : null,
      moviePeers().map((s) => s.id)]);
    if (!page.movie.scales.has(key)) {
      const all = [...page.movie.frames, ...moviePeers()];
      const load = Promise.all(all.map(async (s) => extent(shownNumbers(s, await propertyValues(s, choice, component)))))
        .then((ranges) => ranges.reduce(([lo, hi], [a, b]) => [Math.min(lo, a), Math.max(hi, b)], [Infinity, -Infinity]));
      load.catch(() => page.movie?.scales.delete(key));
      page.movie.scales.set(key, load);
    }
    return page.movie.scales.get(key);
  }

  // --- overlays (shared colour scale across panels)
  async function updateOverlays() {
    const token = ++page.overlayToken;
    const current = () => !page.disposed && token === page.overlayToken;
    const mode = viewerPrefs.colour;
    const overlays = [], notes = [];
    if (viewerPrefs.arrows.show || mode === "force" || mode === "error") status.textContent = "Loading per-atom vectors…";
    let forceData;
    try {
      forceData = await loadForceData();
    } catch (error) {
      forceData = page.structures.map(() => null);
      notes.push(`Forces: ${error.message}`);
    }
    if (!current()) return;
    const target = forceTarget();
    if (target.chosen && forceData.length > 1 && forceData[0] && !forceData[1]) {
      notes.push(`The compared structure has no evaluation of ${target.chosen.method}; it shows no forces.`);
    }
    if (mode === "height") {
      const hs = page.structures.map(heights);
      const range = page.movie ? [...page.movie.frames, ...moviePeers()].map(heights).flat() : hs.flat();
      const lo = Math.min(...range), hi = Math.max(...range);
      page.structures.forEach((s, k) => overlays.push({
        colour: (i) => ramp("height", (hs[k][i] - lo) / (hi - lo || 1)),
        describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[k][i].toFixed(2)} Å`, "height"]],
        value: (i) => hs[k][i].toFixed(2),
      }));
      legend.replaceChildren(rampLegend("height", `${lo.toFixed(1)} Å`, `${hi.toFixed(1)} Å`, "Height along surface normal"));
    } else if (mode === "error") {
      const [a, b] = chosenPair();
      if (!a || !b) {
        legend.replaceChildren(el("span", { class: "muted" }, "Pick two evaluations with per-atom vectors."));
        page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      } else {
        let diffs, max = 1e-9;
        try {
          diffs = await Promise.all(page.structures.map(diffFor));
          max = await scaleMax("error", diffFor, diffs);
        } catch (error) {
          diffs = diffs ?? page.structures.map(() => null);
          notes.push(error.message);
        }
        if (!current()) return;
        if (diffs.slice(1).some((d) => !d)) notes.push("The compared structure lacks one of the two methods; it is shown in element colours.");
        const unitLabel = diffs.find(Boolean)?.unit ?? "";
        page.structures.forEach((s, k) => overlays.push(diffs[k] ? {
          colour: (i) => (diffs[k].included[i] ? ramp("error", diffs[k].values[i] / max) : elementColor(s.symbols[i])),
          describe: (i) => [[s.symbols[i], `atom ${i}`], [`${formatNumber(diffs[k].values[i])} ${unitLabel}`, `|Δ${page.vector}|`]],
          value: (i) => formatNumber(diffs[k].values[i]),
        } : elementOverlay(s)));
        legend.replaceChildren(rampLegend("error", "0", `${formatNumber(max)} ${unitLabel}`,
          `|${page.vector}(${a.method}) − ${page.vector}(${b.method})| per atom${notIncludedNote(diffs)}`));
      }
    } else if (mode === "force") {
      const data = forceData.filter(Boolean);
      if (!data.length && page.movie && target.chosen) {
        // A frame without these forces: element colours, but the movie's scale stays.
        let max = 1e-9;
        try { max = await scaleMax("force", forceValues, []); } catch (error) { notes.push(error.message); }
        if (!current()) return;
        page.structures.forEach((s) => overlays.push(elementOverlay(s)));
        const unit = page.movie.frames.map((frame) => evaluationOn(frame, target.chosen, target.name))
          .find(Boolean)?.vectors.find((v) => v.name === target.name)?.unit;
        legend.replaceChildren(rampLegend("force", "0", `${formatNumber(max)}${unit ? ` ${unit}` : ""}`,
          `|${target.name}| per atom (${target.chosen.method}) · this frame has none`));
      } else if (!data.length) {
        legend.replaceChildren(el("span", { class: "muted" }, "Pick an evaluation with per-atom vectors under Forces."));
        page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      } else {
        let max = 1e-9;
        try {
          max = await scaleMax("force", forceValues, data.map((d) => ({ values: d.magnitudes, included: d.included })));
        } catch (error) {
          notes.push(error.message);
        }
        if (!current()) return;
        page.structures.forEach((s, k) => {
          const d = forceData[k];
          overlays.push(d ? {
            colour: (i) => (d.included[i] ? ramp("force", d.magnitudes[i] / max) : elementColor(s.symbols[i])),
            describe: (i) => [[s.symbols[i], `atom ${i}`]],
            value: (i) => (d.included[i] ? formatNumber(d.magnitudes[i]) : ""),
          } : elementOverlay(s));
        });
        legend.replaceChildren(rampLegend("force", "0", `${formatNumber(max)} ${data[0].unit}`,
          `|${data[0].name}| per atom (${data[0].method})${notIncludedNote(data)}`));
      }
    } else if (mode === "property") {
      const settings = viewerPrefs.property;
      let data = page.structures.map(() => null);
      try {
        data = await Promise.all(page.structures.map((s) => propertyValues(s, settings.choice, settings.component)));
      } catch (error) {
        notes.push(error.message);
      }
      if (!current()) return;
      const first = data.find(Boolean);
      if (!first) {
        legend.replaceChildren(el("span", { class: "muted" }, settings.choice
          ? `This structure has no ${settings.choice.name}; choose another property under Colour.` : "Choose a property under Colour."));
        page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      } else {
        const unit = first.unit ? ` ${first.unit}` : "";
        const missing = (v) => v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v));
        const describe = (s, d) => (i) => [[s.symbols[i], `atom ${i}`], [`${valueText(d.values[i])}${missing(d.values[i]) ? "" : unit}`, first.label]];
        let colourOf;
        if (asCategories(first.values, settings.kind, first.text)) {
          colourOf = (v) => categoryColour(v);
          // Legend: every value among the shown atoms, with its atom count.
          const counts = new Map();
          page.structures.forEach((s, k) => {
            const shown = shownAtoms(s);
            data[k]?.values.forEach((v, i) => { if (shown[i] && !missing(v)) counts.set(v, (counts.get(v) ?? 0) + 1); });
          });
          const values = [...counts.keys()].sort((a, b) => (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b))));
          legend.replaceChildren(el("div", { class: "muted" }, first.label),
            el("div", { class: "legend category-legend" }, values.slice(0, 40).map((v) => el("span", { title: `${counts.get(v)} atoms` },
              el("i", { class: "swatch", style: `background:${categoryColour(v)}` }), `${valueText(v)}${unit}`)),
            values.length > 40 ? el("span", {}, `… ${values.length - 40} more`) : null));
        } else {
          let [lo, hi] = [0, 1];
          try { [lo, hi] = await propertyRange(data); } catch (error) { notes.push(error.message); }
          if (!current()) return;
          if (!Number.isFinite(lo)) [lo, hi] = [0, 1];
          if (settings.symmetric) { const m = Math.max(Math.abs(lo), Math.abs(hi)); [lo, hi] = [-m, m]; }
          if (settings.min !== null) lo = settings.min;
          if (settings.max !== null) hi = settings.max;
          colourOf = (v) => ramp("property", (v - lo) / (hi - lo || 1));
          legend.replaceChildren(rampLegend("property", `${valueText(lo)}${unit}`, `${valueText(hi)}${unit}`,
            `${first.label} per atom${settings.min !== null || settings.max !== null ? " · values outside the range get its end colours" : ""}`));
        }
        if (data.slice(1).some((d) => !d)) notes.push(`The compared structure has no ${settings.choice.name}; it is shown in element colours.`);
        if (data.some((d) => d?.values.some(missing))) notes.push("Atoms without a value keep their element colours.");
        page.structures.forEach((s, k) => {
          const d = data[k];
          overlays.push(d ? {
            colour: (i, symbol) => (missing(d.values[i]) ? elementColor(symbol) : colourOf(d.values[i])),
            describe: describe(s, d),
            value: (i) => (missing(d.values[i]) ? "" : valueText(d.values[i])),
          } : elementOverlay(s));
        });
      }
    } else {
      // Element colours: the element bar is the legend.
      page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      legend.replaceChildren();
    }
    // Rings of every shown structure (fetched once per structure and settings).
    let ringData = page.structures.map(() => null);
    if (viewerPrefs.rings.show) {
      try {
        ringData = await Promise.all(page.structures.map(loadRings));
      } catch (error) {
        notes.push(`Rings: ${error.message}`);
      }
      if (!current()) return;
    }
    page.panels.forEach((panel, k) => { panel.ringData = ringData[k]; });
    status.textContent = notes.join(" ");
    page.forceData = forceData;
    page.panels.forEach((panel, k) => { panel.overlay = overlays[k]; panel.forces = forceData[k]; panel.rebuild(); });
    renderElementBar();
    renderInfo();
    updateForceSummary();
    renderMeasurements();
    renderRingSummary();
  }

  const notIncludedNote = (data) => (data.some((d) => d && d.included.some((x) => !x)) ? " · element colours: not included" : "");

  function elementOverlay(s) {
    const hs = heights(s);
    return {
      colour: (i, symbol) => elementColor(symbol),
      describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[i].toFixed(2)} Å`, "height"]],
    };
  }

  function rampLegend(name, lo, hi, title) {
    const stops = paletteStops(name).join(", ");
    return el("div", { class: "ramp-legend" },
      el("div", { class: "muted" }, title),
      el("div", { class: "ramp-bar", style: `background: linear-gradient(to right, ${stops})` }),
      el("div", { class: "ramp-labels" }, el("span", {}, lo), el("span", {}, hi)));
  }

  // --- controls
  const checkbox = (label, key, onChange) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: viewerPrefs[key], onchange: (event) => {
      viewerPrefs[key] = event.target.checked; savePrefs(); onChange?.();
    } }), label);
  const sliceCount = el("span", { class: "muted" });
  const rebuildAll = () => {
    page.panels.forEach((p) => p.rebuild());
    const scene = page.panels[0].scene;
    sliceCount.textContent = scene ? `${scene.visibleAtoms} of ${scene.totalAtoms} atoms shown${
      scene.totalAtoms > LARGE_SCENE ? " · a large repeat: drawing may be slow" : ""}` : "";
    document.querySelectorAll(".radius-input").forEach((input) => { input.placeholder = autoRadius(input.dataset.symbol).toFixed(2); });
    renderRingSummary();
    renderElementBar();
  };

  // Slice tables keep atoms whose fractional coordinates lie in [min, max];
  // blank = no limit. `key` names the bounds in viewerPrefs.
  const sliceTableFor = (key, onChange, labelPrefix = "") => {
    const boundInput = (axis, side) => el("input", { type: "number", step: 0.05, class: "num-input",
      placeholder: side ? "max" : "min", value: viewerPrefs[key][axis][side] ?? "",
      "aria-label": `${labelPrefix}${"abc"[axis]} ${side ? "maximum" : "minimum"}`,
      onchange: (event) => {
        const value = event.target.value.trim();
        viewerPrefs[key][axis][side] = value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
        savePrefs(); onChange();
      } });
    return el("table", { class: "stats cutoffs" },
      el("thead", {}, el("tr", {}, el("th", {}, "frac."), el("th", {}, "min"), el("th", {}, "max"))),
      el("tbody", {}, [0, 1, 2].map((axis) => el("tr", {}, el("td", {}, "abc"[axis]),
        el("td", {}, boundInput(axis, 0)), el("td", {}, boundInput(axis, 1))))));
  };
  // Element checkboxes: unchecked elements are listed in viewerPrefs[key].
  const elementBoxesFor = (key, onChange, labelPrefix) => el("div", { class: "chips element-boxes" }, species.map((sym) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: !viewerPrefs[key].includes(sym), "aria-label": `${labelPrefix} ${sym}`, onchange: (event) => {
      const hiddenSet = new Set(viewerPrefs[key]);
      if (event.target.checked) hiddenSet.delete(sym); else hiddenSet.add(sym);
      viewerPrefs[key] = [...hiddenSet]; savePrefs(); onChange();
    } }),
    elementSwatch(sym), sym)));
  // Show the stored bounds and elements in a slice table and its element boxes.
  const syncFilter = (sliceKey, elementKey, table, boxes) => {
    table.querySelectorAll("input").forEach((input, n) => { input.value = viewerPrefs[sliceKey][Math.floor(n / 2)][n % 2] ?? ""; });
    boxes.querySelectorAll("input").forEach((input, n) => { input.checked = !viewerPrefs[elementKey].includes(species[n]); });
  };
  const resetFilter = (sliceKey, elementKey, table, boxes) => {
    viewerPrefs[sliceKey] = emptySlice();
    viewerPrefs[elementKey] = []; savePrefs();
    syncFilter(sliceKey, elementKey, table, boxes);
  };
  // With "Same as slice", slicing also changes the force selection and its colour scales.
  const sliceChanged = () => { rebuildAll(); if (viewerPrefs.forceFollowsSlice) updateOverlays(); };
  const sliceTable = sliceTableFor("slice", sliceChanged);

  // Appearance: opacities and edges, collapsed by default.
  let appearanceFrame = 0;
  const scheduleRebuild = () => {
    cancelAnimationFrame(appearanceFrame);
    appearanceFrame = requestAnimationFrame(rebuildAll);
  };
  const percent = (value) => `${Math.round(value * 100)}%`;
  // `group` names the viewerPrefs object holding `key` (appearance or arrows).
  const slider = (key, label, { min = 0, max = 1, step = 0.05, format = percent, group = "appearance" } = {}) => {
    const output = el("output", { class: "muted" });
    const input = el("input", { type: "range", min, max, step, value: viewerPrefs[group][key], "aria-label": label });
    const show = () => { output.textContent = format(Number(input.value)); };
    input.addEventListener("input", () => {
      viewerPrefs[group][key] = Number(input.value); show(); savePrefs(); scheduleRebuild();
    });
    show();
    return el("label", { class: "slider-field" }, el("span", {}, label), input, output);
  };
  // Element colours changed: redraw, and refresh the legend and every swatch.
  let colourFrame = 0;
  function elementColoursChanged() {
    cancelAnimationFrame(colourFrame);
    colourFrame = requestAnimationFrame(() => {
      document.querySelectorAll(".swatch[data-element]").forEach((swatch) => {
        swatch.style.background = elementColor(swatch.dataset.element);
      });
      updateOverlays();
    });
  }
  // Per-element colour and sphere radius (also set from the element bar).
  // Inputs for the same element (style table, element editor) show one value.
  const setElementColour = (sym, colour) => {
    if (colour === null || colour === defaultElementColor(sym)) delete viewerPrefs.appearance.colours[sym];
    else viewerPrefs.appearance.colours[sym] = colour;
    document.querySelectorAll(`input[data-colour-of="${sym}"]`).forEach((input) => { input.value = elementColor(sym); });
    savePrefs(); elementColoursChanged();
  };
  const setElementRadius = (sym, radius) => {
    if (radius === null || !(radius > 0)) delete viewerPrefs.appearance.radii[sym];
    else viewerPrefs.appearance.radii[sym] = radius;
    document.querySelectorAll(`.radius-input[data-symbol="${sym}"]`).forEach((input) => { input.value = viewerPrefs.appearance.radii[sym] ?? ""; });
    savePrefs(); rebuildAll();
  };
  const colourInputFor = (sym) => el("input", { type: "color", value: elementColor(sym), "aria-label": `${sym} colour`, "data-colour-of": sym,
    oninput: (event) => setElementColour(sym, event.target.value) });
  const radiusInputFor = (sym) => el("input", { type: "number", step: 0.05, min: 0.05, class: "num-input radius-input", "data-symbol": sym,
    value: viewerPrefs.appearance.radii[sym] ?? "", placeholder: autoRadius(sym).toFixed(2), "aria-label": `${sym} radius`,
    onchange: (event) => {
      const value = optionalNumber(event.target.value);
      if (!(value > 0)) event.target.value = "";
      setElementRadius(sym, value);
    } });
  const elementStyles = el("tbody");
  function renderElementStyles() {
    elementStyles.replaceChildren(...species.map((sym) => el("tr", {},
      el("td", {}, elementSwatch(sym), ` ${sym}`),
      el("td", { class: "element-colour" }, colourInputFor(sym)),
      el("td", {}, radiusInputFor(sym)),
      el("td", {}, el("button", { type: "button", class: "small reset-colour", title: `Default colour and size for ${sym}`,
        "aria-label": `Default style for ${sym}`, onclick: () => {
          delete viewerPrefs.appearance.radii[sym]; setElementColour(sym, null); renderElementStyles(); rebuildAll();
        } }, "↺")))));
  }
  renderElementStyles();
  const styleSliders = () => [
    slider("bondRadius", "Bond radius", { min: 0.02, max: 0.4, step: 0.01, format: (value) => `${value.toFixed(2)} Å` }),
    slider("polyAlpha", "Polyhedra opacity"),
    slider("planeAlpha", "Plane opacity"),
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.polyEdges, onchange: (event) => {
      viewerPrefs.appearance.polyEdges = event.target.checked; savePrefs(); rebuildAll();
    } }), "Polyhedron edges"),
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.depthCue, onchange: (event) => {
      viewerPrefs.appearance.depthCue = event.target.checked; savePrefs(); rebuildAll();
    } }), "Depth cueing (fade towards the back)"),
    slider("depthStrength", "Depth fade at the back", { min: 0.1, max: 0.9 }),
  ];
  const sliderBox = el("div", { class: "field-stack" }, ...styleSliders());
  const resetAppearance = () => {
    viewerPrefs.appearance = freshAppearance(); savePrefs();
    sliderBox.replaceChildren(...styleSliders());
    renderElementStyles();
    rebuildAll();
    elementColoursChanged();
  };

  // Element visibility: unchecked elements are hidden (with their bonds).
  const elementBoxes = elementBoxesFor("hiddenElements", sliceChanged, "Show");

  // Miller planes: h*x + k*y + l*z = t in fractional coordinates (t = distance in units of d).
  const planeList = el("div", { class: "plane-list" });
  function renderPlanes() {
    planeList.replaceChildren(...viewerPrefs.planes.map((plane, index) => {
      const dLabel = el("span", { class: "muted plane-d" });
      const updateD = () => {
        const d = dSpacing(structure.cell, plane);
        dLabel.textContent = d ? `d = ${d.toFixed(3)} Å · ${(plane.t * d).toFixed(2)} Å from origin` : "invalid (0 0 0)";
      };
      const field = (key, label, step = 1) => el("input", { type: "number", step, value: plane[key], class: "num-input plane-index",
        "aria-label": label, onchange: (event) => {
          plane[key] = Number(event.target.value) || 0; savePrefs(); updateD(); rebuildAll();
        } });
      updateD();
      return el("div", { class: "plane-row" },
        el("div", { class: "inline-fields" },
          el("input", { type: "checkbox", checked: plane.show, "aria-label": "Show plane", onchange: (event) => {
            plane.show = event.target.checked; savePrefs(); rebuildAll();
          } }),
          el("input", { type: "color", class: "plane-colour", value: planeColour(plane, index), "aria-label": "Plane colour",
            title: "Plane colour", oninput: (event) => { plane.colour = event.target.value; savePrefs(); scheduleRebuild(); } }),
          "(", field("h", "h"), field("k", "k"), field("l", "l"), ")",
          el("button", { type: "button", class: "small", title: "Remove plane", "aria-label": "Remove plane", onclick: () => {
            viewerPrefs.planes.splice(index, 1); savePrefs(); renderPlanes(); rebuildAll();
          } }, "×")),
        el("div", { class: "inline-fields plane-position" }, el("span", { class: "muted" }, "t"), field("t", "Position t", 0.05), dLabel));
    }));
    if (!viewerPrefs.planes.length) planeList.append(el("p", { class: "muted hint" }, "h·x + k·y + l·z = t (fractional coordinates)."));
  }
  renderPlanes();
  // Measurements: pick atoms by clicking them; see measureState.
  const measureList = el("div", { class: "measure-list" });
  const measureHint = el("p", { class: "muted hint" });
  const atomName = (r) => `${r.symbol}${r.index}${r.image.some(Boolean) ? `′` : ""}`;
  function renderMeasurements() {
    const need = MEASURE_ATOMS[measureState.mode];
    stages.classList.toggle("measuring", Boolean(need) || measureState.mode === "select");
    measureSelect.value = need ? measureState.mode : "off";
    measureHint.textContent = !need ? "Choose what to measure, then click atoms in the structure."
      : `Click ${need - measureState.pending.length} more atom${need - measureState.pending.length === 1 ? "" : "s"}`
        + `${measureState.pending.length ? ` (after ${measureState.pending.map(atomName).join(", ")}); Esc cancels` : ""}.`;
    const selecting = measureState.mode === "select";
    clickMode.replaceChildren(...(need || selecting ? [
      el("span", {}, selecting ? "Clicking atoms selects them for a colour (Colour tab)."
        : `Clicking atoms measures ${measureState.mode === "distance" ? "a distance" : `an ${measureState.mode}`} (Measure tab): ${measureHint.textContent}`),
      el("button", { type: "button", class: "small", onclick: () => {
        measureState.mode = "off"; measureState.pending = []; measurementsChanged();
      } }, selecting ? "Stop selecting" : "Stop measuring")] : []));
    measureList.replaceChildren(...measureState.items.map((item, k) => {
      const values = page.structures.map((s) => (fitsStructure(s, item.atoms) ? measureValue(s, item) : null));
      const near = values[0]?.nearest;
      return el("div", { class: "measure-row" },
        el("span", { class: "measure-atoms", title: "′ marks a periodic image" }, item.atoms.map(atomName).join("–")),
        el("span", { class: "measure-value" }, values.map((v) => (v ? v.text : "–")).join(" | "),
          near ? el("span", { class: "muted" }, ` (nearest image ${near.toFixed(3)} Å)`) : null),
        el("button", { type: "button", class: "small", title: "Remove", "aria-label": "Remove measurement", onclick: () => {
          measureState.items.splice(k, 1); measurementsChanged();
        } }, "×"));
    }));
    if (measureState.items.length) {
      measureList.append(el("button", { type: "button", class: "small", onclick: () => {
        measureState.items = []; measureState.pending = []; measurementsChanged();
      } }, "Clear all"));
    }
  }
  const measurementsChanged = () => { page.panels.forEach((p) => p.rebuild()); renderMeasurements(); renderPaint(); };
  const measureSelect = el("select", { "aria-label": "Measure" },
    [["off", "Off"], ["distance", "Distance (2 atoms)"], ["angle", "Angle (3 atoms)"], ["dihedral", "Dihedral (4 atoms)"]].map(([value, label]) =>
      el("option", { value, selected: measureState.mode === value }, label)));
  measureSelect.addEventListener("change", () => {
    measureState.mode = measureSelect.value;
    measureState.pending = [];
    measurementsChanged();
  });
  const pickAtom = (ref) => {
    if (measureState.mode === "select") {
      // Toggle the atom (all its periodic copies) in the colouring selection.
      const at = paintState.selected.findIndex((r) => r.index === ref.index && r.count === ref.count);
      if (at >= 0) paintState.selected.splice(at, 1);
      else paintState.selected.push({ index: ref.index, symbol: ref.symbol, count: ref.count });
      measurementsChanged();
      return;
    }
    const need = MEASURE_ATOMS[measureState.mode];
    if (!need) return;
    measureState.pending.push(ref);
    if (measureState.pending.length === need) {
      measureState.items.push({ kind: measureState.mode, atoms: measureState.pending });
      measureState.pending = [];
    }
    measurementsChanged();
  };
  page.panels.forEach((panel) => { panel.onPick = pickAtom; });
  page.cancelMeasure = () => {
    if (measureState.pending.length) measureState.pending = [];
    else if (measureState.mode === "select" && paintState.selected.length) paintState.selected = [];
    else return false;
    measurementsChanged();
    return true;
  };
  const measureControls = el("div", { class: "measure-controls" }, measureSelect, measureHint, measureList);

  // Atom colours: select atoms by clicking (shares the click with Measure),
  // then give them a colour; see paintState.
  const atomLabel = (r) => `${r.symbol}${r.index}`;
  const selectBox = el("input", { type: "checkbox", onchange: (event) => {
    measureState.mode = event.target.checked ? "select" : "off";
    measureState.pending = [];
    measurementsChanged();
  } });
  const paintColour = el("input", { type: "color", value: paintState.colour, "aria-label": "Colour for the selected atoms" });
  const applyButton = el("button", { type: "button", class: "small", onclick: () => {
    if (!paintState.selected.length) return;
    paintState.colour = paintColour.value;
    paintState.groups.push({ colour: paintColour.value, atoms: paintState.selected });
    paintState.selected = [];
    measurementsChanged();
  } }, "Apply colour");
  const paintHint = el("p", { class: "muted hint" });
  const paintList = el("div", { class: "measure-list" });
  function renderPaint() {
    const selecting = measureState.mode === "select";
    selectBox.checked = selecting;
    const count = paintState.selected.length;
    paintHint.textContent = count ? `${count} atom${count === 1 ? "" : "s"} selected${selecting ? "; Esc clears" : ""}.`
      : selecting ? "Click atoms to select them." : "Turn on selecting, or select all shown atoms.";
    applyButton.disabled = !count;
    paintList.replaceChildren(...paintState.groups.map((group, k) => {
      const names = group.atoms.slice(0, 6).map(atomLabel).join(", ") + (group.atoms.length > 6 ? ` … (${group.atoms.length})` : "");
      // The colour stays editable after it is applied.
      return el("div", { class: "measure-row" },
        el("input", { type: "color", class: "group-colour", value: group.colour, "aria-label": `Colour of ${names}`, title: "Change this colour",
          oninput: (event) => { group.colour = event.target.value; paintState.colour = group.colour; scheduleRebuild(); } }),
        el("span", { class: "measure-atoms", title: group.atoms.map(atomLabel).join(", ") }, names),
        el("button", { type: "button", class: "small", title: "Remove", "aria-label": "Remove colour", onclick: () => {
          paintState.groups.splice(k, 1); measurementsChanged();
        } }, "×"));
    }));
    if (paintState.groups.length) {
      paintList.append(el("button", { type: "button", class: "small", onclick: () => {
        paintState.groups = []; measurementsChanged();
      } }, "Remove all colours"));
    }
  }
  const paintControls = el("div", { class: "measure-controls" },
    el("label", { class: "check" }, selectBox, "Select atoms by clicking"),
    el("div", { class: "button-row" },
      el("button", { type: "button", class: "small", title: "Select every atom the slice shows", onclick: () => {
        const shown = page.structures[0];
        const indices = [...new Set((page.panels[0].scene?.atoms ?? []).map((a) => a.index))].sort((a, b) => a - b);
        paintState.selected = indices.map((index) => ({ index, symbol: shown.symbols[index], count: shown.symbols.length }));
        measurementsChanged();
      } }, "All shown atoms"),
      el("button", { type: "button", class: "small", onclick: () => { paintState.selected = []; measurementsChanged(); } }, "Clear selection")),
    paintHint,
    el("div", { class: "inline-fields" }, paintColour, applyButton),
    paintList);
  renderMeasurements();
  renderPaint();

  const preset = (name) => () => {
    sharedView.R = presetRotation(structure, name);
    page.panels[0].fit();
    viewChanged();
  };
  // Look along an axis of the tripod (clicked, or its key). Already looking
  // along it, look from the opposite side; `opposite` forces a side.
  const alignAxis = (name, opposite = null, panel = page.panels[0]) => {
    const shown = panel.structure ?? structure;
    const direction = axisDirection(shown.cell, name);
    if (!norm(direction)) return; // no such cell axis
    const flip = opposite ?? dot(sharedView.R[2], direction) > 0.999;
    animateView(axisRotation(shown, name, flip));
  };
  page.panels.forEach((panel) => { panel.onAxis = (name) => alignAxis(name, null, panel); });
  const roll = (angle) => () => animateView(rotated(sharedView.R, "z", angle));
  const tripodSelect = el("select", { "aria-label": "Axes" },
    [["abc", "Cell axes a, b, c"], ["xyz", "Cartesian x, y, z"], ["both", "Both"], ["off", "Hidden"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.tripod.axes === value }, label)));
  tripodSelect.addEventListener("change", () => { viewerPrefs.tripod.axes = tripodSelect.value; savePrefs(); rebuildAll(); });
  const labelSelect = el("select", { "aria-label": "Atom labels" },
    [["off", "None"], ["index", "Index"], ["element", "Element"], ["element-index", "Element and index"], ["value", "Colour value"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.labels === value }, label)));
  labelSelect.addEventListener("change", () => { viewerPrefs.labels = labelSelect.value; savePrefs(); rebuildAll(); });
  const pngScaleInput = el("input", { type: "number", min: 1, max: 8, step: 1, value: viewerPrefs.pngScale, class: "num-input",
    "aria-label": "PNG resolution", title: "Pixels per screen pixel", onchange: (event) => {
      const value = Math.round(Number(event.target.value));
      viewerPrefs.pngScale = value >= 1 ? Math.min(8, value) : 3;
      event.target.value = viewerPrefs.pngScale; savePrefs();
    } });
  const repeatInput = (axis) => el("input", { type: "number", min: 1, max: MAX_REPEAT, value: viewerPrefs.repeat[axis], class: "num-input",
    disabled: !structure.pbc[axis],
    onchange: (event) => {
      viewerPrefs.repeat[axis] = clampRepeat(event.target.value);
      savePrefs(); rebuildAll(); page.panels[0].fit(); viewChanged();
    } });

  const pairs = [];
  for (const a of species) for (const b of species) if (a <= b) pairs.push([a, b]);
  for (const [a, b] of pairs) viewerPrefs.cutoffs[pairKey(a, b)] ??= defaultCutoff(a, b);
  const cutoffRows = pairs.map(([a, b]) => el("tr", {}, el("td", {}, `${a}–${b}`), el("td", {},
    el("input", { type: "number", step: 0.05, min: 0, value: viewerPrefs.cutoffs[pairKey(a, b)], class: "num-input",
      onchange: (event) => { viewerPrefs.cutoffs[pairKey(a, b)] = Math.max(0, Number(event.target.value) || 0); savePrefs(); rebuildAll(); } }),
    el("span", { class: "muted" }, " Å"))));

  const centres = viewerPrefs.polyCenters ?? species.filter((s) => TRANSITION_METALS.has(s));
  const centreBoxes = el("div", { class: "chips" }, species.filter((s) => !NONMETALS.has(s)).map((sym) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: centres.includes(sym), onchange: () => {
      viewerPrefs.polyCenters = [...centreBoxes.querySelectorAll("input")].filter((i) => i.checked).map((i) => i.parentElement.textContent);
      savePrefs(); rebuildAll();
    } }), sym)));

  // Rings (see loadRings): the method, which atoms form the network, its
  // bonds, how sizes are counted, which sizes are shown and how; a summary of
  // the found rings. Changes fetch the rings again (style changes only redraw).
  const rings = viewerPrefs.rings;
  let ringFrame = 0;
  const ringsChanged = () => {
    savePrefs();
    cancelAnimationFrame(ringFrame);
    ringFrame = requestAnimationFrame(() => updateOverlays());
  };
  const ringMethodSelect = el("select", { "aria-label": "Ring method" },
    [["planar", "Flat: surface, overlayer, 2D material"],
      ["shortest-path", "3D: bulk, zeolite, amorphous"]].map(([value, label]) =>
      el("option", { value, selected: rings.method === value }, label)));
  const searchSizeInput = el("input", { type: "number", min: 3, max: 24, step: 1, class: "num-input", value: rings.searchSize,
    "aria-label": "Largest ring searched", onchange: (event) => {
      const value = Math.round(Number(event.target.value));
      rings.searchSize = value >= 3 ? Math.min(24, value) : 12;
      event.target.value = rings.searchSize; ringsChanged();
    } });
  const searchSizeField = el("div", { class: "inline-fields" }, el("span", { class: "field-label" }, "Largest ring searched (atoms)"), searchSizeInput);
  const methodHint = el("p", { class: "muted hint" });
  const showMethod = () => {
    const planar = rings.method === "planar";
    searchSizeField.hidden = planar;
    enclosedBox.hidden = !planar;
    methodHint.textContent = planar
      ? "Looks down onto the a–b plane: every enclosed face of the network is a ring (polygons that wrap around the cell are open channels, not rings)."
      : "Any network: for every atom, each shortest path between two of its neighbours that avoids the atom closes a ring (Guttman's rings).";
  };
  ringMethodSelect.addEventListener("change", () => { rings.method = ringMethodSelect.value; showMethod(); ringsChanged(); });
  const ringElementRows = species.map((sym) => {
    const setting = (patch) => { rings.elements[sym] = { ...ringElement(sym), ...patch }; ringsChanged(); };
    const bound = (key, label) => el("input", { type: "number", step: 0.1, class: "num-input", placeholder: key === "zmin" ? "min" : "max",
      value: ringElement(sym)[key] ?? "", "aria-label": `${sym} ${label}`,
      onchange: (event) => setting({ [key]: optionalNumber(event.target.value) }) });
    return el("tr", {},
      el("td", {}, el("label", { class: "check" }, el("input", { type: "checkbox", checked: ringElement(sym).use, "aria-label": `Rings of ${sym}`,
        onchange: (event) => setting({ use: event.target.checked }) }), elementSwatch(sym), sym)),
      el("td", {}, bound("zmin", "minimum height")), el("td", {}, bound("zmax", "maximum height")));
  });
  const ringElementTable = el("table", { class: "stats cutoffs" },
    el("thead", {}, el("tr", {}, el("th", {}, "element"), el("th", {}, "height from"), el("th", {}, "to (Å)"))), el("tbody", {}, ringElementRows));
  const syncRingElements = () => ringElementTable.querySelectorAll("tbody tr").forEach((row, n) => {
    const setting = ringElement(species[n]);
    const [use, zmin, zmax] = row.querySelectorAll("input");
    use.checked = setting.use; zmin.value = setting.zmin ?? ""; zmax.value = setting.zmax ?? "";
  });
  const ringHint = el("p", { class: "muted hint" });
  // Height windows from the atoms selected under Colour (± 0.05 Å);
  // elements without selected atoms are left out.
  const fromSelection = el("button", { type: "button", class: "small", title: "Use only the elements and heights of the atoms selected in the Colour tab",
    onclick: () => {
      const shown = page.structures[0];
      if (!paintState.selected.length || !fitsStructure(shown, paintState.selected)) {
        ringHint.textContent = "First select some of the network's atoms in the Colour tab (Highlight selected atoms: click them, or slice and use All shown atoms).";
        return;
      }
      const normal = surfaceNormal(shown);
      for (const sym of species) {
        const hs = paintState.selected.filter((r) => r.symbol === sym).map((r) => dot(shown.positions[r.index], normal));
        rings.elements[sym] = hs.length
          ? { use: true, zmin: Math.floor((Math.min(...hs) - 0.05) * 100) / 100, zmax: Math.ceil((Math.max(...hs) + 0.05) * 100) / 100 }
          : { use: false, zmin: null, zmax: null };
      }
      syncRingElements(); ringsChanged();
    } }, "Use selected atoms");
  const ringCutoffRows = pairs.map(([a, b]) => el("tr", {}, el("td", {}, `${a}–${b}`), el("td", {},
    el("input", { type: "number", step: 0.05, min: 0, class: "num-input", value: rings.cutoffs[pairKey(a, b)] ?? "",
      placeholder: String(viewerPrefs.cutoffs[pairKey(a, b)]), "aria-label": `Ring cutoff ${a}–${b}`,
      onchange: (event) => {
        const value = optionalNumber(event.target.value);
        if (value === null || value < 0) { delete rings.cutoffs[pairKey(a, b)]; event.target.value = ""; }
        else rings.cutoffs[pairKey(a, b)] = value;
        ringsChanged();
      } }),
    el("span", { class: "muted" }, " Å"))));
  const ringCheck = (key, label, title) => el("label", { class: "check", title }, el("input", { type: "checkbox", checked: rings[key],
    onchange: (event) => { rings[key] = event.target.checked; ringsChanged(); } }), label);
  const ringCountSelect = el("select", { "aria-label": "Ring size counts" },
    [["auto", "Automatic"], ["pairs", "Atom pairs (half the ring atoms)"], ["all", "All ring atoms"],
      ...species.map((sym) => [sym, `${sym} atoms only`])].map(([value, label]) =>
      el("option", { value, selected: rings.count === value }, label)));
  const ringSchemeSelect = el("select", { "aria-label": "Ring colours" },
    el("option", { value: "categories", selected: rings.scheme === "categories" }, "One colour per size (the same in every structure; repeats after 10 sizes)"),
    el("optgroup", { label: "Colour map over the sizes" }, Object.entries(PALETTES).map(([value, palette]) =>
      el("option", { value, selected: rings.scheme === value }, palette.label))));
  const ringCustomColours = customPaletteInputs();
  ringCustomColours.hidden = rings.scheme !== "custom";
  ringSchemeSelect.addEventListener("change", () => {
    rings.scheme = ringSchemeSelect.value; ringCustomColours.hidden = rings.scheme !== "custom"; ringsChanged();
  });
  ringCountSelect.addEventListener("change", () => { rings.count = ringCountSelect.value; ringsChanged(); });
  const sizeInput = (key, label) => el("input", { type: "number", min: 0, step: 1, class: "num-input", value: rings[key] ?? "",
    placeholder: key === "minSize" ? "min" : "max", "aria-label": label,
    onchange: (event) => { rings[key] = optionalNumber(event.target.value); ringsChanged(); } });
  const ringSummary = el("div", { class: "ring-summary" });
  const enclosedBox = ringCheck("enclosed", "Count atoms inside a ring (labelled e.g. 6+1Cu)", "Network atoms that are pruned or unbonded count as inside the smallest ring around them");
  // The settings as steps, in the order one sets them up; the found rings first.
  const ringStep = (number, title, ...children) => el("div", { class: "ring-step" },
    el("div", { class: "ring-step-title" }, el("span", { class: "ring-step-number" }, String(number)), title), ...children);
  const ringBody = el("div", { class: "ring-controls", hidden: !rings.show },
    ringSummary,
    ringStep(1, "Kind of network",
      ringMethodSelect,
      methodHint,
      searchSizeField),
    ringStep(2, "Atoms that form it",
      el("p", { class: "muted hint" }, "Tick the elements of the network. Heights (along the surface normal a × b) keep one layer, for example the overlayer on a slab; leave them blank for all atoms of an element."),
      ringElementTable,
      el("div", { class: "button-row" }, fromSelection,
        el("button", { type: "button", class: "small", onclick: () => { rings.elements = {}; syncRingElements(); ringHint.textContent = ""; ringsChanged(); } }, "All atoms")),
      ringHint),
    ringStep(3, "Bonds",
      ringCheck("alternating", "Only bonds between different elements", "For networks that alternate between elements, such as metal–oxygen or Si–O; ignored with only one element"),
      el("details", {}, el("summary", { class: "muted" }, "Bond cutoffs for rings"),
        el("p", { class: "muted hint" }, "Blank: the bond cutoff of the Style tab (shown greyed). Turn on Bonds there to see the network."),
        el("table", { class: "stats cutoffs" }, el("tbody", {}, ringCutoffRows)))),
    ringStep(4, "Ring size",
      el("label", { class: "palette-field" }, el("span", { class: "muted" }, "Count"), ringCountSelect),
      el("p", { class: "muted hint" }, "A ring of 6 Cu and 6 O atoms is a 6-ring counting pairs or Cu atoms, a 12-ring counting all atoms. Automatic counts pairs when every bond joins two different elements, otherwise all atoms."),
      enclosedBox),
    el("details", { class: "ring-step" }, el("summary", { class: "ring-step-title" }, "Appearance"),
      el("div", { class: "ring-controls" },
        el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Show sizes"), sizeInput("minSize", "Smallest ring size shown"), "–",
          sizeInput("maxSize", "Largest ring size shown")),
        el("label", { class: "palette-field" }, el("span", { class: "muted" }, "Colours"), ringSchemeSelect),
        ringCustomColours,
        slider("alpha", "Ring opacity", { group: "rings" }),
        ringCheck("outline", "Ring outlines"),
        ringCheck("labels", "Ring size labels"),
        slider("labelScale", "Ring label size", { min: 0.5, max: 4, step: 0.1, format: (value) => `${value.toFixed(1)}×`, group: "rings" }))));
  showMethod();
  const ringShowBox = el("label", { class: "check" }, el("input", { type: "checkbox", checked: rings.show, onchange: (event) => {
    rings.show = event.target.checked; ringBody.hidden = !rings.show; ringsChanged();
    if (!rings.show) renderRingSummary();
  } }), "Show rings");

  // Found rings of the shown structure: counts and colours per size, the
  // signature (see RingResult.signature), and the legend under the structure.
  // Rebuilt only when the rings or sizes change, so colour pickers stay open.
  let ringSummaryKey = null;
  function renderRingSummary() {
    const data = rings.show ? page.panels[0].ringData : null;
    const key = data && JSON.stringify([page.structures[0].id, rings.minSize, rings.maxSize, rings.scheme, rings.scheme === "custom" ? viewerPrefs.customPalette : null, data.signature, data.network, data.bonds, data.warnings, Boolean(page.stepList)]);
    if (key === ringSummaryKey) { renderRingLegend(); return; }
    ringSummaryKey = key;
    if (!data) { ringSummary.replaceChildren(); ringLegend.replaceChildren(); return; }
    const bySize = new Map();
    for (const ring of data.rings) bySize.set(ring.size, (bySize.get(ring.size) ?? 0) + 1);
    const sizes = [...bySize.keys()].sort((a, b) => a - b);
    const range = ringSizeRange(data);
    const colourInput = (size) => el("input", { type: "color", value: ringColour(size, range), "aria-label": `Colour of ${size}-rings`,
      oninput: (event) => { rings.colours[size] = event.target.value; savePrefs(); scheduleRebuild(); renderRingLegend(); } });
    ringSummary.replaceChildren(
      el("p", { class: "muted hint" }, `${data.network} atoms in the network · ${data.bonds} bonds`
        + (data.method === "planar" ? ` · ${data.pruned} pruned${data.enclosed ? ` (${data.enclosed} enclosed)` : ""}`
          + ` · ${data.open_faces.length} open face${data.open_faces.length === 1 ? "" : "s"} (channels)` : "")),
      ...(data.warnings ?? []).map((warning) => el("p", { class: "hint error" }, warning)),
      sizes.length
        ? el("table", { class: "stats cutoffs ring-sizes" },
          el("thead", {}, el("tr", {}, el("th", {}, "size"), el("th", {}, "rings"), el("th", {}, "colour"))),
          el("tbody", {}, sizes.map((size) => el("tr", { class: ringShown({ size }) ? null : "muted" },
            el("td", {}, String(size)), el("td", { class: "num" }, String(bySize.get(size))),
            el("td", { class: "element-colour" }, colourInput(size),
              el("button", { type: "button", class: "small reset-colour", title: "Default colour", "aria-label": `Default colour of ${size}-rings`,
                onclick: (event) => {
                  delete rings.colours[size]; savePrefs();
                  event.currentTarget.previousSibling.value = ringColour(size, range);
                  scheduleRebuild();
                } }, "↺"))))))
        : el("p", { class: "muted hint" }, "No rings found: check the atoms, heights and cutoffs (turn on Bonds to see the network)."),
      data.signature ? el("p", { class: "hint ring-signature" }, el("span", { class: "muted" }, "Signature "), el("code", {}, data.signature),
        copyButton(data.signature)) : null,
      el("div", { class: "button-row" },
        el("button", { type: "button", class: "small", title: "The rings of this structure (atoms, polygons, sizes, areas) as JSON", onclick: () => {
          const s = page.structures[0];
          downloadText(`${s.formula}-${s.id}.rings.json`, `${JSON.stringify(ringsJson(s, page.panels[0].ringData), null, 1)}\n`, "application/json");
        } }, "Save rings (JSON)"),
        page.stepList ? el("button", { type: "button", class: "small", title: `Ring sizes of every structure stepped through (${page.stepList.list.length}) as CSV`,
          onclick: (event) => ringTable(event.currentTarget) }, "Ring counts of all steps (CSV)") : null));
    renderRingLegend();
  }
  function renderRingLegend() {
    const data = rings.show ? page.panels[0].ringData : null;
    if (!data) { ringLegend.replaceChildren(); return; }
    const bySize = new Map();
    for (const ring of data.rings) if (ringShown(ring)) bySize.set(ring.size, (bySize.get(ring.size) ?? 0) + 1);
    const range = ringSizeRange(data);
    ringLegend.replaceChildren(el("div", { class: "legend" }, el("span", {}, `Rings (size in ${data.unit}):`),
      bySize.size ? [...bySize.keys()].sort((a, b) => a - b).map((size) => el("span", {},
        el("i", { class: "swatch", style: `background:${ringColour(size, range)}` }), `${size} × ${bySize.get(size)}`)) : el("span", {}, "none shown")));
  }
  // The rings of one structure with their settings; `poly` holds the corners'
  // x, y (for plotting tools that draw the tiling in the xy plane).
  function ringsJson(s, data) {
    const { counts, rings: found, ...facts } = data;
    return { stoms_rings: 2, structure_id: s.id, formula: s.formula, cell: s.cell, pbc: s.pbc, settings: ringSettings(s), ...facts, counts,
      rings: found.map(({ centre, ...ring }) => ({ ...ring, centre: centre.map((v) => Number(v.toFixed(4))), poly: ring.points.map((p) => [p[0], p[1]]) })) };
  }
  // One CSV row per structure of the step list: ring counts per size.
  async function ringTable(button) {
    const { list, label } = page.stepList;
    const text = button.textContent;
    button.disabled = true;
    try {
      let done = 0;
      const results = await Promise.all(list.map((r) => loadStructure(r.id).then((s) => {
        done += 1;
        if (done % 10 === 0 || done === list.length) button.textContent = `Loading ${done} / ${list.length}…`;
        return loadRings(s);
      })));
      if (page.disposed) return;
      const sizes = [...new Set(results.flatMap((data) => data.rings.map((ring) => ring.size)))].sort((a, b) => a - b);
      const quote = (value) => (/[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value);
      const rows = [["position", "label", "structure_id", "rings", ...sizes.map((size) => `size_${size}`), "open_faces", "signature"].join(",")];
      results.forEach((data, k) => {
        const counts = sizes.map((size) => data.rings.filter((ring) => ring.size === size).length);
        rows.push([k + 1, quote(label(list[k])), list[k].id, data.rings.length, ...counts, data.open_faces.length, quote(data.signature)].join(","));
      });
      downloadText("ring-counts.csv", `${rows.join("\n")}\n`, "text/csv");
    } catch (error) {
      window.alert(`Ring counts failed: ${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = text;
    }
  }

  // Forces: which evaluation and vector, arrows, and the atoms included in both
  // (the others get no arrow and keep element colours in force colourings).
  const forceEvaluationSelect = el("select", { "aria-label": "Force evaluation" },
    vectorEvaluations.map((e) => el("option", { value: e.id, selected: e === page.force.evaluation }, evaluationLabel(e))));
  const forceVectorSelect = el("select", { "aria-label": "Per-atom vector" });
  const forceVectorField = el("label", {}, el("span", { class: "muted" }, "Property"), forceVectorSelect);
  const fillVectorSelect = () => {
    const vectors = page.force.evaluation?.vectors ?? [];
    forceVectorSelect.replaceChildren(...vectors.map((v) => el("option", { value: v.name, selected: v.name === page.force.name },
      v.unit ? `${v.name} (${v.unit})` : v.name)));
    forceVectorField.hidden = vectors.length < 2;
  };
  fillVectorSelect();
  const forcesChanged = () => {
    page.force.explicit = true;
    viewerPrefs.forceChoice = { ...methodChoice(page.force.evaluation), name: page.force.name }; savePrefs();
    history.replaceState(null, "", hash(structure.id));
    updateOverlays();
  };
  forceEvaluationSelect.addEventListener("change", () => {
    page.force.evaluation = vectorEvaluations.find((e) => e.id === forceEvaluationSelect.value);
    if (!page.force.evaluation.vectors.some((v) => v.name === page.force.name)) page.force.name = defaultVectorName(page.force.evaluation);
    fillVectorSelect(); forcesChanged();
  });
  forceVectorSelect.addEventListener("change", () => { page.force.name = forceVectorSelect.value; forcesChanged(); });

  const arrowStyleChanged = () => { savePrefs(); scheduleRebuild(); };
  const scaleInput = el("input", { type: "number", min: 0, step: "any", class: "num-input", "aria-label": "Arrow length scale",
    onchange: (event) => {
      const value = Number(event.target.value);
      if (value > 0) viewerPrefs.arrows.scale = value;
      event.target.value = viewerPrefs.arrows.scale; arrowStyleChanged();
    } });
  const scaleUnit = el("span");
  // Auto: the largest included force becomes a 1.5 Angstrom arrow (shared by
  // both panels, and by all frames of a loaded movie).
  const autoScaleButton = el("button", { type: "button", class: "small", title: "Largest included force → 1.5 Å arrow", onclick: async () => {
    const shown = page.forceData.filter(Boolean).map((d) => ({ values: d.magnitudes, included: d.included }));
    const max = await scaleMax("force", forceValues, shown);
    if (!(max > 1e-9)) return;
    viewerPrefs.arrows.scale = Number((1.5 / max).toPrecision(2));
    scaleInput.value = viewerPrefs.arrows.scale; arrowStyleChanged();
  } }, "Auto");
  const minMagnitudeInput = el("input", { type: "number", min: 0, step: "any", class: "num-input", "aria-label": "Minimum force for an arrow",
    onchange: (event) => {
      const value = Number(event.target.value);
      viewerPrefs.arrows.minMagnitude = value > 0 ? value : 0;
      event.target.value = viewerPrefs.arrows.minMagnitude; arrowStyleChanged();
    } });
  const colourInput = el("input", { type: "color", "aria-label": "Arrow colour",
    oninput: (event) => { viewerPrefs.arrows.colour = event.target.value; arrowStyleChanged(); } });
  const arrowStyleBody = () => {
    scaleInput.value = viewerPrefs.arrows.scale;
    minMagnitudeInput.value = viewerPrefs.arrows.minMagnitude;
    colourInput.value = viewerPrefs.arrows.colour ?? themeTextColour();
    return [
      el("div", { class: "arrow-length" }, el("span", { class: "muted" }, "Length, ", scaleUnit),
        el("div", { class: "inline-fields" }, scaleInput, autoScaleButton)),
      slider("width", "Arrow width", { min: 0.01, max: 0.2, step: 0.01, format: (value) => `${value.toFixed(2)} Å`, group: "arrows" }),
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Colour"), colourInput,
        el("button", { type: "button", class: "small", title: "Use the page's text colour", onclick: () => {
          viewerPrefs.arrows.colour = null; colourInput.value = themeTextColour(); arrowStyleChanged();
        } }, "Theme")),
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Hide below"), minMagnitudeInput, el("span", { class: "muted arrow-unit" })),
      el("button", { type: "button", class: "small", onclick: () => {
        viewerPrefs.arrows = { ...DEFAULT_ARROWS, show: viewerPrefs.arrows.show }; savePrefs();
        arrowStyleControls.replaceChildren(arrowStyleControls.firstChild, ...arrowStyleBody());
        updateForceSummary(); rebuildAll();
      } }, "Reset arrow style"),
    ];
  };
  const arrowStyleControls = el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Arrow style"), ...arrowStyleBody());

  const forceSliceTable = sliceTableFor("forceSlice", updateOverlays, "Forces ");
  const forceElementBoxes = elementBoxesFor("forceHiddenElements", updateOverlays, "Include forces of");
  const forceCount = el("span", { class: "muted" });
  // Own elements and bounds, shown only when the selection does not follow the slice.
  const ownSelection = el("div", { hidden: viewerPrefs.forceFollowsSlice },
    forceElementBoxes, forceSliceTable,
    el("button", { type: "button", class: "small", onclick: () => {
      resetFilter("forceSlice", "forceHiddenElements", forceSliceTable, forceElementBoxes);
      updateOverlays();
    } }, "Include all"));
  const followSliceBox = el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.forceFollowsSlice,
    onchange: (event) => {
      viewerPrefs.forceFollowsSlice = event.target.checked;
      // Unchecking starts the own selection from the current slice.
      if (!event.target.checked) {
        viewerPrefs.forceSlice = viewerPrefs.slice.map((bounds) => [...bounds]);
        viewerPrefs.forceHiddenElements = [...viewerPrefs.hiddenElements];
        syncFilter("forceSlice", "forceHiddenElements", forceSliceTable, forceElementBoxes);
      }
      savePrefs();
      ownSelection.hidden = event.target.checked;
      updateOverlays();
    } }), "Same as slice");
  const inclusionActive = () => !viewerPrefs.forceFollowsSlice
    && (viewerPrefs.forceHiddenElements.length > 0 || viewerPrefs.forceSlice.flat().some((v) => v !== null));
  const inclusionControls = el("details", { open: inclusionActive() }, el("summary", { class: "muted" }, "Include atoms"),
    el("p", { class: "muted hint" }, "Only included atoms get arrows and count towards force colour scales; the others keep their element colours."),
    followSliceBox, ownSelection, forceCount);

  // Units and counts depend on the loaded force data.
  function updateForceSummary() {
    const data = page.forceData[0];
    const unit = data?.unit || page.force.evaluation?.vectors.find((v) => v.name === page.force.name)?.unit || "";
    arrowStyleControls.querySelectorAll(".arrow-unit").forEach((node) => { node.textContent = unit; });
    scaleUnit.textContent = unit ? `Å per ${unit}` : "Å per unit";
    autoScaleButton.disabled = !page.forceData.some(Boolean);
    const included = forceIncluded(structure).filter(Boolean).length;
    forceCount.textContent = `${included} of ${structure.positions.length} atoms included`;
  }

  const forceControls = vectorEvaluations.length
    ? el("div", { class: "force-controls" },
      el("label", {}, el("span", { class: "muted" }, "Evaluation"), forceEvaluationSelect),
      forceVectorField,
      el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.arrows.show, onchange: (event) => {
        viewerPrefs.arrows.show = event.target.checked; savePrefs(); updateOverlays();
      } }), "Show arrows"),
      arrowStyleControls,
      inclusionControls)
    : el("p", { class: "muted" }, "No evaluations with per-atom vectors.");

  const pairSelect = (slot) => {
    const select = el("select", { "aria-label": slot ? "Evaluation B" : "Evaluation A" },
      vectorEvaluations.map((e) => el("option", { value: e.id, selected: page.pair[slot] === e.id }, evaluationLabel(e))));
    select.addEventListener("change", () => {
      page.pair[slot] = select.value;
      viewerPrefs.pairChoice = page.pair.map((id) => { const e = structure.evaluations.find((x) => x.id === id); return e ? methodChoice(e) : null; }); savePrefs();
      updateOverlays();
    });
    return select;
  };
  const errorControls = el("div", { class: "error-controls", hidden: viewerPrefs.colour !== "error" },
    vectorEvaluations.length < 2
      ? el("p", { class: "muted" }, "Needs two evaluations with per-atom vectors (e.g. forces).")
      : [el("label", {}, el("span", { class: "muted" }, "Reference (A)"), pairSelect(0)),
        el("label", {}, el("span", { class: "muted" }, "Compared (B)"), pairSelect(1))]);
  const colourSelect = el("select", { "aria-label": "Colour atoms by" },
    [["element", "Element"], ["height", "Height"], ["force", "Force magnitude"], ["error", "Per-atom force difference"],
      ["property", "Atomic property"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.colour === value }, label)));

  // Atomic property colouring: which property (see propertyOptions), the
  // component of a vector, categories or a range, and the range's limits.
  const property = viewerPrefs.property;
  const options = propertyOptions(structure);
  const propertySelect = el("select", { "aria-label": "Atomic property" });
  const componentSelect = el("select", { "aria-label": "Vector component" },
    VECTOR_COMPONENTS.map(([value, label]) => el("option", { value, selected: property.component === value }, label)));
  const componentField = el("label", {}, el("span", { class: "muted" }, "Component"), componentSelect);
  const fillPropertySelect = () => {
    const current = choiceKey(property.choice);
    const groups = [...new Set(options.map((o) => o.group))];
    propertySelect.replaceChildren(
      current && !options.some((o) => o.key === current)
        ? el("option", { value: current, selected: true }, `${property.choice.name} (not on this structure)`) : null,
      ...groups.map((group) => el("optgroup", { label: group }, options.filter((o) => o.group === group).map((o) =>
        el("option", { value: o.key, selected: o.key === current }, o.label)))));
    componentField.hidden = options.find((o) => o.key === current)?.kind !== "vector";
  };
  // Without a choice: the first property stored with the structure or its
  // evaluations, else the coordination number.
  if (!property.choice) property.choice = (options.find((o) => o.choice.source !== "derived") ?? options[0]).choice;
  fillPropertySelect();
  const propertyChanged = () => { savePrefs(); fillPropertySelect(); updateOverlays(); };
  propertySelect.addEventListener("change", () => {
    const option = options.find((o) => o.key === propertySelect.value);
    if (!option) return;
    property.choice = option.choice;
    property.min = property.max = null; rangeInputs.forEach((input) => { input.value = ""; });
    propertyChanged();
  });
  componentSelect.addEventListener("change", () => { property.component = componentSelect.value; propertyChanged(); });
  const kindSelect = el("select", { "aria-label": "Read values as" },
    [["auto", "Automatic"], ["continuous", "A range of values"], ["categories", "Categories"]].map(([value, label]) =>
      el("option", { value, selected: property.kind === value }, label)));
  kindSelect.addEventListener("change", () => { property.kind = kindSelect.value; propertyChanged(); });
  const rangeInputs = ["min", "max"].map((key) => el("input", { type: "number", step: "any", class: "num-input", placeholder: "auto",
    value: property[key] ?? "", "aria-label": `Colour range ${key === "min" ? "minimum" : "maximum"}`,
    onchange: (event) => { property[key] = optionalNumber(event.target.value); propertyChanged(); } }));
  const propertyControls = el("div", { class: "error-controls", hidden: viewerPrefs.colour !== "property" },
    el("label", {}, el("span", { class: "muted" }, "Property"), propertySelect),
    componentField,
    el("label", {}, el("span", { class: "muted" }, "Read values as"), kindSelect),
    el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Range"), rangeInputs[0], "–", rangeInputs[1]),
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: property.symmetric, onchange: (event) => {
      property.symmetric = event.target.checked; propertyChanged();
    } }), "Symmetric around 0"),
    el("p", { class: "muted hint" }, "Automatic: whole numbers with at most 12 values (such as tags) are categories. Blank range ends follow the shown atoms; the diverging palette suits signed values."));
  // Palette of the current value colouring; each mode remembers its own.
  const paletteSelect = el("select", { "aria-label": "Colour palette" });
  const paletteField = el("label", { class: "palette-field" }, el("span", { class: "muted" }, "Palette"), paletteSelect);
  // The two colours of the custom palette (shared by every colouring and the
  // rings); shown wherever the custom palette is chosen.
  function customPaletteInputs() {
    return el("div", { class: "inline-fields custom-palette" },
    el("span", { class: "field-label" }, "From"), ...[0, 1].flatMap((k) => [
      el("input", { type: "color", value: viewerPrefs.customPalette[k], "aria-label": k ? "Custom palette high colour" : "Custom palette low colour",
        oninput: (event) => {
          viewerPrefs.customPalette[k] = event.target.value; savePrefs();
          document.querySelectorAll(".custom-palette input[type=color]").forEach((input, n) => { input.value = viewerPrefs.customPalette[n % 2]; });
          customPaletteChanged();
        } }),
      k ? null : el("span", { class: "field-label" }, "to")]));
  }
  let customFrame = 0;
  const customPaletteChanged = () => {
    cancelAnimationFrame(customFrame);
    customFrame = requestAnimationFrame(() => updateOverlays());
  };
  const customPaletteField = customPaletteInputs();
  const colourMapSection = el("section", { class: "control-section" }, el("h4", {}, "Colour map"), paletteField, customPaletteField);
  const fillPaletteSelect = () => {
    const mode = viewerPrefs.colour;
    colourMapSection.hidden = !(mode in DEFAULT_PALETTES);
    const current = viewerPrefs.palettes[mode] ?? DEFAULT_PALETTES[mode];
    customPaletteField.hidden = current !== "custom";
    paletteSelect.replaceChildren(...Object.entries(PALETTES).map(([value, palette]) =>
      el("option", { value, selected: current === value }, palette.label)));
  };
  fillPaletteSelect();
  paletteSelect.addEventListener("change", () => {
    viewerPrefs.palettes[viewerPrefs.colour] = paletteSelect.value; savePrefs();
    customPaletteField.hidden = paletteSelect.value !== "custom";
    updateOverlays();
  });
  colourSelect.addEventListener("change", () => {
    viewerPrefs.colour = colourSelect.value; savePrefs();
    errorControls.hidden = viewerPrefs.colour !== "error";
    propertyControls.hidden = viewerPrefs.colour !== "property";
    fillPaletteSelect();
    updateOverlays();
  });

  // Settings files: { "stoms_viewer_settings": 1, "settings": { ... } }.
  const settingsInput = el("input", { type: "file", accept: ".json,application/json", hidden: true, "aria-label": "Settings file" });
  settingsInput.addEventListener("change", async () => {
    const file = settingsInput.files[0];
    settingsInput.value = "";
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); } catch { data = null; }
    if (!data || data.stoms_viewer_settings !== 1 || typeof data.settings !== "object") {
      window.alert(`${file.name} is not a STOMS viewer settings file.`);
      return;
    }
    for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
    Object.assign(viewerPrefs, normalizePrefs(data.settings));
    savePrefs();
    renderStructurePage(structureId, params);
  });

  const repeatInputs = [0, 1, 2].map(repeatInput);

  // --- vibrational modes: pick a q-point and a mode, then play it. The atoms
  // of the first panel move; at q ≠ 0 every cell copy of the repeat moves
  // with its own phase.
  const vibrationControls = modes ? vibrationPanel() : null;
  function vibrationPanel() {
    if (modes.error) return [el("p", { class: "error" }, modes.error)];
    const prefs = viewerPrefs.vibration;
    // The phase starts at π/2, where a mode at Γ passes through equilibrium.
    const vib = { q: 0, mode: 0, phase: Math.PI / 2, active: false, playing: false, frame: 0, last: 0 };
    const point = () => modes.qpoints[vib.q];
    const firstMode = () => Math.max(0, point().frequencies.findIndex((f) => Math.abs(f) >= ZERO_FREQUENCY));
    vib.mode = firstMode();
    const unitLabel = () => (prefs.unit === "cm-1" ? "cm⁻¹" : "THz");
    const frequencyText = (f) => {
      const value = Math.abs(f) < ZERO_FREQUENCY ? 0 : Math.abs(f) * (prefs.unit === "cm-1" ? THZ_TO_CM : 1);
      return `${value.toFixed(prefs.unit === "cm-1" ? 1 : 3)}${f <= -ZERO_FREQUENCY ? "i" : ""} ${unitLabel()}`;
    };
    const qText = (q) => `(${q.map((x) => String(Number(x.toFixed(4)))).join(", ")})`;

    const motion = () => {
      const vectors = point().displacements[vib.mode];
      // The atom that moves most moves by the amplitude.
      const largest = Math.max(1e-12, ...vectors.map((d) => Math.hypot(...d)));
      return { q: point().q, vectors, scale: prefs.amplitude / largest, amplitude: prefs.amplitude, phase: vib.phase,
        moving: vib.active, arrows: prefs.showArrows, bonds: prefs.bonds };
    };
    const show = () => {
      const panel = page.panels[0];
      panel.motion = vib.active || prefs.showArrows ? motion() : null;
      panel.rebuild();
    };

    const qSelect = el("select", { "aria-label": "q-point", onchange: () => {
      vib.q = Number(qSelect.value); vib.mode = firstMode(); fillModes(); showHint(); show(); updatePlot();
    } }, modes.qpoints.map((p, k) => el("option", { value: k }, `q = ${qText(p.q)}`)));
    const modeSelect = el("select", { class: "mode-list", "aria-label": "Mode", onchange: () => {
      vib.mode = Number(modeSelect.value); show(); updatePlot();
    } });

    // From phonopy, any q: three fields (reduced coordinates), computed by
    // the server. `frequency` (THz) picks the mode closest to it, else the
    // mode keeps its number. With NAC, q = 0 also takes the direction Γ is
    // approached from (`direction`, else the direction fields).
    const anyQ = Boolean(modes.any_q);
    const qNote = el("span", { class: "muted" });
    let qRequest = 0;
    const goToQ = async (q, frequency = null, direction = null) => {
      const token = ++qRequest;
      // The fields show the q asked for (a click on the bands sets them); a
      // reply never changes them, so typing on is never undone.
      qInputs.forEach((input, k) => { input.value = String(Number(q[k].toFixed(4))); });
      if (direction) directionInputs.forEach((input, k) => { input.value = String(Number(direction[k].toFixed(4))); });
      const towards = directionInputs.map((input) => Number(input.value) || 0);
      const query = `q=${q.join(",")}${towards.some(Boolean) ? `&direction=${towards.join(",")}` : ""}${plot?.nac === false ? "&nac=0" : ""}`;
      qNote.textContent = "…";
      let data;
      try {
        data = await api(`structures/${encodeURIComponent(structure.id)}/modes?${query}`);
      } catch (error) {
        if (token === qRequest) qNote.textContent = error.message;
        return;
      }
      if (token !== qRequest || page.disposed) return;
      qNote.textContent = "";
      modes.qpoints = data.qpoints; vib.q = 0;
      const frequencies = point().frequencies;
      if (frequency !== null) {
        vib.mode = frequencies.reduce((best, f, k) => (Math.abs(f - frequency) < Math.abs(frequencies[best] - frequency) ? k : best), 0);
      } else if (vib.mode >= frequencies.length) vib.mode = firstMode();
      fillModes(); showHint(); show(); updatePlot(); showDirection();
    };
    const fieldsQ = () => qInputs.map((input) => Number(input.value) || 0);
    const qInputs = [0, 1, 2].map((k) => el("input", { type: "number", step: 0.05, class: "num-input",
      value: String(Number(point().q[k].toFixed(4))), "aria-label": `q along ${"abc"[k]}*`,
      onchange: () => goToQ(fieldsQ()) }));
    const qRow = el("div", {},
      el("span", { class: "field-label" }, "q-point (reduced, along a*, b*, c*)"),
      el("div", { class: "inline-fields repeat-row" }, el("span", { class: "muted", title: "Reduced coordinates of the primitive reciprocal lattice" }, "q"),
        ...qInputs, qNote));
    const directionInputs = [0, 1, 2].map((k) => el("input", { type: "number", step: 0.5, class: "num-input",
      value: "", placeholder: "0", "aria-label": `Direction to Γ along ${"abc"[k]}*`,
      onchange: () => goToQ(fieldsQ()) }));
    const directionNote = el("p", { class: "muted hint" });
    const directionRow = el("div", {},
      el("div", { class: "inline-fields repeat-row" }, el("span", { class: "muted", title: "With NAC the modes at Γ depend on the direction q approaches Γ from (LO-TO splitting); reduced coordinates like q" }, "→Γ"),
        ...directionInputs),
      directionNote);
    // Shown at q = 0 with NAC only, where the direction changes the modes.
    function showDirection() {
      const p = point();
      directionRow.hidden = !(anyQ && p.nac && !p.q.some(Boolean));
      directionNote.textContent = p.direction
        ? "LO-TO split: Γ approached along this direction."
        : "No direction: NAC term left out at Γ (LO = TO). Give one, or click Γ on the bands.";
    }

    // Band structure and DOS under the structure, for phonopy input; the
    // selected q and mode are marked, and a click on the bands picks both.
    const plot = structure.has_phonons ? createPhononPlot(structure, (q, frequency, direction) => goToQ(q, frequency, direction)) : null;
    if (plot) {
      figures.append(plot.element);
      plot.onNac = () => goToQ(fieldsQ());
      // Below the structure (the default) or beside it, for wide screens.
      const sideButton = el("button", { type: "button", class: "small" });
      const showSide = () => {
        figures.classList.toggle("side", prefs.plotSide);
        sideButton.textContent = prefs.plotSide ? "Below the structure" : "Beside the structure";
        sideButton.title = prefs.plotSide ? "Show the plot below the structure" : "Show the plot beside the structure";
      };
      // The structure panel changes width: fit the structure into it again.
      sideButton.addEventListener("click", () => {
        prefs.plotSide = !prefs.plotSide; savePrefs(); showSide();
        page.panels[0].fit(); viewChanged();
      });
      showSide();
      plot.actions.prepend(sideButton);
    }
    function updatePlot() {
      plot?.update({ q: point().q, frequency: point().frequencies[vib.mode],
        factor: prefs.unit === "cm-1" ? THZ_TO_CM : 1, unit: unitLabel() });
    }
    const fillModes = () => {
      const frequencies = point().frequencies;
      modeSelect.size = Math.min(8, Math.max(2, frequencies.length));
      modeSelect.replaceChildren(...frequencies.map((f, k) => el("option", { value: k, selected: k === vib.mode }, `${k + 1} · ${frequencyText(f)}`)));
    };

    const playButton = el("button", { type: "button", class: "small" }, "▶ Play");
    // One period lasts periodSeconds whatever the frequency.
    const tick = (now) => {
      if (!vib.playing || page.disposed) return;
      vib.phase = (vib.phase + (2 * Math.PI * (now - vib.last)) / (1000 * prefs.periodSeconds)) % (2 * Math.PI);
      vib.last = now;
      show();
      vib.frame = requestAnimationFrame(tick);
    };
    const pause = () => {
      vib.playing = false;
      cancelAnimationFrame(vib.frame);
      playButton.textContent = "▶ Play";
    };
    const play = () => {
      vib.active = true; vib.playing = true; vib.last = performance.now();
      playButton.textContent = "❚❚ Pause";
      vib.frame = requestAnimationFrame(tick);
    };
    // Pausing or stopping also ends a recording, which keeps what it has.
    playButton.addEventListener("click", () => {
      if (!vib.playing) { play(); return; }
      pause(); finishRecording({ save: true });
    });
    const stopButton = el("button", { type: "button", class: "small", title: "Stop and return to the equilibrium structure", onclick: () => {
      pause(); finishRecording({ save: true }); vib.active = false; vib.phase = Math.PI / 2; show();
    } }, "Stop");

    // Video: the first panel's canvas as shown, for recordPeriods periods from
    // rest, so the video loops. WebM where the browser records it (Chrome,
    // Firefox), else MP4 (Safari).
    const recordButton = el("button", { type: "button", class: "small", title: "Record the vibration as a video" }, "● Record");
    let recording = null;
    const finishRecording = ({ save }) => {
      if (!recording) return;
      clearTimeout(recording.timer);
      recording.save = save;
      if (recording.recorder.state !== "inactive") recording.recorder.stop();
    };
    recordButton.addEventListener("click", () => {
      if (recording) { finishRecording({ save: true }); return; }
      const type = typeof MediaRecorder === "undefined" ? null : VIDEO_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
      const { renderer, stage } = page.panels[0];
      if (!type || !renderer.canvas.captureStream) { window.alert("This browser cannot record videos of the viewer."); return; }
      // Drawn on a canvas of its own at the video size, after every panel draw.
      const frame = videoFrame(prefs.videoSize, stage.clientWidth, stage.clientHeight, window.devicePixelRatio || 1);
      const canvas = document.createElement("canvas");
      [canvas.width, canvas.height] = frame.pixels;
      const fps = Number(prefs.videoFps);
      const stream = canvas.captureStream(fps);
      // About 8 Mbit/s for 1080p at 60 fps; plenty for drawn structures.
      const bitrate = Math.round(Math.max(2_000_000, frame.pixels[0] * frame.pixels[1] * fps * 0.07));
      const recorder = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: bitrate });
      const chunks = [];
      const q = point().q.map((x) => String(Number(x.toFixed(4)))).join("_");
      const name = `${structure.formula}-q${q}-mode${vib.mode + 1}.${type.startsWith("video/mp4") ? "mp4" : "webm"}`;
      recording = { recorder, save: true, timer: 0 };
      recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
      recorder.addEventListener("stop", () => {
        const { save } = recording;
        recording = null;
        renderer.onDraw = null;
        stream.getTracks().forEach((track) => track.stop());
        recordButton.textContent = "● Record";
        if (save && chunks.length && !page.disposed) downloadText(name, new Blob(chunks, { type }), type.split(";")[0]);
      });
      renderer.onDraw = (scene, theme) => paintScene(canvas, scene, ...frame.layout, frame.scale, theme, true, { tripod: viewerPrefs.tripod.export });
      vib.active = true; vib.phase = Math.PI / 2;
      show();
      if (vib.playing) vib.last = performance.now(); else play();
      recorder.start();
      recordButton.textContent = "■ Stop recording";
      recording.timer = setTimeout(() => finishRecording({ save: true }), prefs.recordPeriods * prefs.periodSeconds * 1000);
    });
    page.stopVibration = () => { pause(); finishRecording({ save: false }); };

    const numberField = (label, key, { min, max, step }) => el("label", { class: "inline-fields" }, el("span", { class: "muted" }, label),
      el("input", { type: "number", min, max, step, value: prefs[key], class: "num-input", onchange: (event) => {
        const value = Number(event.target.value);
        const clamped = Math.min(max, Math.max(min, step === 1 ? Math.round(value) : value));
        prefs[key] = value > 0 ? clamped : DEFAULT_VIBRATION[key];
        event.target.value = prefs[key]; savePrefs(); show();
      } }));
    const choice = (label, key, options, onChange) => el("label", {}, el("span", { class: "muted" }, label),
      el("select", { "aria-label": label, onchange: (event) => { prefs[key] = event.target.value; savePrefs(); onChange(); } },
        options.map(([value, text]) => el("option", { value, selected: prefs[key] === value }, text))));
    const arrowsBox = el("label", { class: "check" }, el("input", { type: "checkbox", checked: prefs.showArrows, onchange: (event) => {
      prefs.showArrows = event.target.checked; savePrefs(); show();
    } }), "Show as arrows");

    // At q ≠ 0 neighbouring cells move with different phases; the smallest
    // repeat that holds a whole number of wavelengths shows the pattern.
    const hint = el("div", { class: "hint muted" });
    const showHint = () => {
      const q = point().q;
      if (q.every((x) => Math.abs(x) < 1e-9)) { hint.replaceChildren("Γ point: every cell copy moves alike."); return; }
      const fit = q.map((x, k) => {
        if (!structure.pbc[k]) return 1;
        for (let n = 1; n <= MAX_REPEAT; n++) if (Math.abs(n * x - Math.round(n * x)) < 1e-3) return n;
        return null;
      });
      if (fit.includes(null)) {
        hint.replaceChildren(`Cell copies move with different phases at this q; no repeat up to ${MAX_REPEAT} fits it exactly.`);
        return;
      }
      hint.replaceChildren(`Cell copies move with different phases at this q; a repeat of ${fit.join(" × ")} shows a whole wavelength. `,
        el("button", { type: "button", class: "small", onclick: () => {
          viewerPrefs.repeat = fit.map(clampRepeat);
          repeatInputs.forEach((input, k) => { input.value = viewerPrefs.repeat[k]; });
          savePrefs(); rebuildAll(); page.panels[0].fit(); viewChanged();
        } }, "Apply"));
    };
    fillModes();
    showHint();
    updatePlot();
    showDirection();
    if (prefs.showArrows) show();

    return [
      anyQ ? qRow : modes.qpoints.length > 1 ? qSelect : el("p", { class: "muted hint" }, `q = ${qText(point().q)}`),
      directionRow,
      modeSelect,
      el("div", { class: "button-row" }, playButton, stopButton, recordButton),
      el("div", { class: "inline-fields" },
        numberField("Amplitude (Å)", "amplitude", { min: 0.01, max: 2, step: 0.05 }),
        numberField("Period (s)", "periodSeconds", { min: 0.2, max: 20, step: 0.1 })),
      choice("Bonds while vibrating", "bonds", [["fixed", "Fixed (equilibrium)"], ["live", "Recomputed every frame"]], show),
      choice("Frequency unit", "unit", [["THz", "THz"], ["cm-1", "cm⁻¹"]], () => { fillModes(); updatePlot(); }),
      arrowsBox,
      hint,
      el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Video"),
        numberField("Periods", "recordPeriods", { min: 1, max: 20, step: 1 }),
        choice("Size", "videoSize", [["shown", "As shown"], ["720p", "1280 × 720"], ["1080p", "1920 × 1080"]], () => {}),
        choice("Frame rate", "videoFps", [["30", "30 fps"], ["60", "60 fps"]], () => {}))];
  }

  const compareSelect = el("select", { class: "compare-select", "aria-label": "Compare with" }, el("option", { value: "" }, "No comparison"));
  compareSelect.addEventListener("change", () => { location.hash = hash(structure.id, { compare: compareSelect.value || null }); });

  // Compare bar: the compared structure (from the step list, or opened from
  // files, which are then stepped through on the right), which panel steps
  // through the list while the other stays as reference, swap and close.
  const compareFiles = el("input", { type: "file", multiple: true, hidden: true, "aria-label": "Structure files to compare with" });
  const openFileButton = el("button", { type: "button", class: "small", title: "Open structure files (extxyz, POSCAR, CIF, …) and compare with them",
    onclick: () => compareFiles.click() }, "Open file…");
  compareFiles.addEventListener("change", async () => {
    const files = [...compareFiles.files];
    compareFiles.value = "";
    if (!files.length) return;
    openFileButton.disabled = true; openFileButton.textContent = "Opening…";
    try {
      const [added] = await addStructureFiles(files);
      location.hash = hash(structure.id, { compare: added.structure_ids[0], cycle: added.id, side: "right" });
    } catch (error) {
      window.alert(error.message);
      openFileButton.disabled = false; openFileButton.textContent = "Open file…";
    }
  });
  function renderCompareBar() {
    const comparing = page.panels.length > 1;
    const segment = (side, label) => el("button", { type: "button", class: "segment", "aria-pressed": String((page.side === 1) === (side === "right")),
      onclick: () => { location.hash = hash(structure.id, { side: side === "right" ? "right" : null }); } }, label);
    compareBar.replaceChildren(...[
      el("div", { class: "inline-fields" }, el("span", { class: "field-label" }, "Compare with"), compareSelect, openFileButton, compareFiles),
      comparing ? el("div", { class: "inline-fields" }, el("span", { class: "field-label" }, "Steps move"),
        el("div", { class: "segmented", role: "group", "aria-label": "Panel that steps" }, segment("left", "Left"), segment("right", "Right")),
        el("button", { type: "button", class: "small", title: "Swap the two structures", onclick: () => {
          location.hash = hash(page.originals[1].id, { compare: structure.id });
        } }, "⇄ Swap"),
        el("button", { type: "button", class: "small", title: "Show one structure", onclick: () => {
          location.hash = hash(structure.id, { compare: null });
        } }, "Close comparison")) : null].filter(Boolean));
  }
  renderCompareBar();

  // Element bar under the structure: atom counts per element (left | right
  // when comparing). Click hides or shows an element; right-click edits it.
  function toggleElement(sym, only = false) {
    const hidden = new Set(viewerPrefs.hiddenElements);
    if (only) { hidden.clear(); for (const s of page.structures.flatMap((x) => x.symbols)) if (s !== sym) hidden.add(s); }
    else if (hidden.has(sym)) hidden.delete(sym); else hidden.add(sym);
    viewerPrefs.hiddenElements = [...hidden]; savePrefs();
    syncFilter("slice", "hiddenElements", sliceTable, elementBoxes);
    sliceChanged();
  }
  function renderElementBar() {
    const counts = page.structures.map((s) => {
      const c = {};
      for (const sym of s.symbols) c[sym] = (c[sym] ?? 0) + 1;
      return c;
    });
    const symbols = [...new Set(page.structures.flatMap((s) => s.symbols))].sort();
    const hidden = new Set(viewerPrefs.hiddenElements);
    elementBar.replaceChildren(...symbols.map((sym) => el("button", { type: "button", class: "element-chip",
      "aria-pressed": String(!hidden.has(sym)), title: `${hidden.has(sym) ? "Show" : "Hide"} ${sym}; right-click for colour and size`,
      onclick: () => toggleElement(sym),
      oncontextmenu: (event) => { event.preventDefault(); openElementEditor(sym, event.currentTarget); } },
    elementSwatch(sym), el("span", { class: "element-symbol" }, sym),
    el("span", { class: "element-count" }, counts.map((c) => c[sym] ?? 0).join(" | ")))));
  }
  let editor = null;
  const outsideEditor = (event) => { if (editor && !editor.contains(event.target)) closeElementEditor(); };
  function closeElementEditor() {
    if (!editor) return false;
    editor.remove(); editor = null;
    document.removeEventListener("pointerdown", outsideEditor, true);
    return true;
  }
  page.closeEditor = closeElementEditor;
  function openElementEditor(sym, anchor) {
    closeElementEditor();
    const hidden = viewerPrefs.hiddenElements.includes(sym);
    const count = page.structures[0].symbols.filter((x) => x === sym).length;
    editor = el("div", { class: "element-editor", role: "dialog", "aria-label": `Style of ${sym}` },
      el("div", { class: "editor-head" }, elementSwatch(sym), el("strong", {}, sym), el("span", { class: "muted" }, `${count} atoms`),
        el("button", { type: "button", class: "editor-close", "aria-label": "Close", onclick: closeElementEditor }, "×")),
      el("label", { class: "field" }, el("span", { class: "field-label" }, "Colour"), colourInputFor(sym)),
      el("label", { class: "field" }, el("span", { class: "field-label" }, "Radius (Å, blank = automatic)"), radiusInputFor(sym)),
      el("div", { class: "button-row" },
        el("button", { type: "button", class: "small", onclick: () => { toggleElement(sym); closeElementEditor(); } }, hidden ? "Show" : "Hide"),
        el("button", { type: "button", class: "small", onclick: () => { toggleElement(sym, true); closeElementEditor(); } }, `Only ${sym}`),
        el("button", { type: "button", class: "small", onclick: () => {
          delete viewerPrefs.appearance.radii[sym]; setElementColour(sym, null); renderElementStyles(); rebuildAll(); closeElementEditor();
        } }, "Default style")));
    viewerMain.append(editor);
    const box = viewerMain.getBoundingClientRect(), at = anchor.getBoundingClientRect();
    editor.style.left = `${Math.max(0, Math.min(at.left - box.left, box.width - editor.offsetWidth))}px`;
    editor.style.top = `${at.top - box.top - editor.offsetHeight - 6}px`;
    editor.querySelector("input")?.focus();
    document.addEventListener("pointerdown", outsideEditor, true);
  }

  // Info: composition, lattice parameters, cell and reciprocal matrices,
  // slab geometry, positions and stored info of the shown structures (side by
  // side when comparing; also for movie frames). Built while the tab is open.
  const infoPanel = el("div", { class: "info-panel" });
  const fixed = (value, digits) => (value === null || !Number.isFinite(value) ? "–" : value.toFixed(digits));
  const angleBetween = (u, v) => (Math.acos(Math.max(-1, Math.min(1, dot(u, v) / (norm(u) * norm(v) || 1)))) * 180) / Math.PI;
  // Structures without a cell (molecules) have no lattice to describe.
  const hasCell = (s) => s.cell.some((v) => norm(v) > 1e-8);
  // `lattice`: with the lattice rows (when any shown structure has a cell,
  // so that compared structures line up).
  function cellFacts(s, lattice = true) {
    const [A, B, C] = s.cell;
    const volume = Math.abs(dot(A, cross(B, C)));
    const normal = surfaceNormal(s);
    const hs = s.positions.map((p) => dot(p, normal));
    const [low, high] = extent(hs); // (no spread: any number of atoms)
    const thickness = hs.length ? high - low : 0;
    const counts = {};
    for (const sym of s.symbols) counts[sym] = (counts[sym] ?? 0) + 1;
    const head = [
      ["Formula", s.formula, ""],
      ["Atoms", String(s.symbols.length), ""],
      ["Composition", Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)).map(([sym, n]) => `${sym} ${n}`).join(", "), ""],
    ];
    if (!lattice) {
      return [...head,
        ["Mass", fixed(s.mass ?? null, 3), "u"],
        ["Thickness along the flattest direction", fixed(thickness, 3), "Å"]];
    }
    return [...head,
      ["a", fixed(norm(A), 4), "Å"], ["b", fixed(norm(B), 4), "Å"], ["c", fixed(norm(C), 4), "Å"],
      ["α (b, c)", fixed(angleBetween(B, C), 3), "°"], ["β (a, c)", fixed(angleBetween(A, C), 3), "°"], ["γ (a, b)", fixed(angleBetween(A, B), 3), "°"],
      ["Volume", fixed(volume, 3), "Å³"],
      ["Mass", fixed(s.mass ?? null, 3), "u"],
      // 1 u/Å³ = 1.66053907 g/cm³.
      ["Density", volume > 1e-9 && s.mass ? fixed((s.mass * 1.66053907) / volume, 4) : "–", "g/cm³"],
      ["Periodic", s.pbc.map((p, k) => `${"abc"[k]} ${p ? "yes" : "no"}`).join(", "), ""],
      ["Surface area |a × b|", fixed(norm(cross(A, B)), 3), "Å²"],
      ["Atom heights", hs.length ? `${fixed(low, 3)} – ${fixed(high, 3)}` : "–", "Å"],
      ["Slab thickness", fixed(thickness, 3), "Å"],
      ["Vacuum along the normal", fixed(Math.abs(dot(C, normal)) - thickness, 3), "Å"],
    ];
  }
  const matrixText = (rows, digits) => rows.map((row) => row.map((v) => v.toFixed(digits).padStart(digits + 6)).join(" ")).join("\n");
  function matrixTable(rows, names, digits) {
    return el("table", { class: "stats matrix" },
      el("thead", {}, el("tr", {}, el("th", {}, ""), ["x", "y", "z"].map((h) => el("th", {}, h)))),
      el("tbody", {}, rows.map((row, k) => el("tr", {}, el("th", {}, names[k]), row.map((v) => el("td", { class: "num" }, v.toFixed(digits)))))));
  }
  function positionsTable(s) {
    const recip = hasCell(s) ? reciprocal(s.cell) : null;
    const shown = s.positions.slice(0, 5000);
    const text = shown.map((p, i) => `${s.symbols[i]} ${p.map((v) => v.toFixed(5)).join(" ")}`).join("\n");
    return [
      el("div", { class: "button-row" }, el("span", { class: "muted hint" }, recip ? "Cartesian (Å) and fractional coordinates" : "Cartesian coordinates (Å)"), copyButton(text)),
      el("div", { class: "table-scroll" }, el("table", { class: "stats positions" },
        el("thead", {}, el("tr", {}, ["#", "", "x", "y", "z", ...(recip ? ["a", "b", "c"] : [])].map((h) => el("th", {}, h)))),
        el("tbody", {}, shown.map((p, i) => {
          const f = recip ? fractional(recip, p) : [];
          return el("tr", {}, el("td", {}, String(i)), el("td", {}, s.symbols[i]),
            p.map((v) => el("td", { class: "num" }, v.toFixed(3))), f.map((v) => el("td", { class: "num" }, v.toFixed(4))));
        })))),
      s.positions.length > shown.length ? el("p", { class: "muted hint" }, `First ${shown.length} of ${s.positions.length} atoms.`) : null,
    ];
  }
  let infoToken = 0;
  async function renderInfo() {
    if (viewerPrefs.tab !== "info") return;
    const token = ++infoToken;
    const shown = [...page.structures];
    // (Movie frames come without their stored info until it is shown here.)
    try { await Promise.all(shown.map(withExtras)); } catch { /* shown without stored info */ }
    if (token !== infoToken || page.disposed) return;
    const names = shown.length > 1 ? ["Left", "Right"] : [null];
    const lattice = shown.some(hasCell);
    const facts = shown.map((s) => cellFacts(s, lattice));
    const factTable = el("table", { class: "stats info-facts" },
      shown.length > 1 ? el("thead", {}, el("tr", {}, el("th", {}, ""), names.map((n) => el("th", { class: "num" }, n)))) : null,
      el("tbody", {}, facts[0].map(([label, , unit], row) => el("tr", {},
        el("th", {}, label, unit ? el("span", { class: "muted" }, ` (${unit})`) : null),
        facts.map((f) => el("td", { class: row > 2 ? "num" : null }, f[row][1]))))));
    const matrices = shown.filter(hasCell).map((s, k) => {
      const reciprocalRows = reciprocal(s.cell).map((row) => mul(row, 2 * Math.PI));
      return el("div", { class: "info-block" },
        names[k] ? el("h4", {}, `${names[k]}: ${s.formula}`) : null,
        el("div", { class: "button-row" }, el("span", { class: "field-label" }, "Cell vectors (rows, Å)"), copyButton(matrixText(s.cell, 6))),
        matrixTable(s.cell, ["a", "b", "c"], 4),
        el("div", { class: "button-row" }, el("span", { class: "field-label" }, "Reciprocal vectors (rows, 2π/Å)"), copyButton(matrixText(reciprocalRows, 6))),
        matrixTable(reciprocalRows, ["a*", "b*", "c*"], 4));
    });
    const extras = shown.map((s, k) => {
      const prefix = names[k] ? `${names[k]}: ` : "";
      const positions = el("details", {}, el("summary", {}, `${prefix}Atom positions`));
      positions.addEventListener("toggle", () => {
        if (positions.open && positions.children.length === 1) positions.append(...positionsTable(s).filter(Boolean));
      });
      return [positions,
        Object.keys(s.info ?? {}).length ? el("details", {}, el("summary", {}, `${prefix}Structure info (${Object.keys(s.info).length})`), jsonTree(s.info, "info")) : null,
        Object.keys(s.metadata ?? {}).length ? el("details", {}, el("summary", {}, `${prefix}Provenance metadata`), jsonTree(s.metadata, "metadata")) : null];
    });
    // Sections the reader opened stay open when the info is rebuilt.
    const open = new Set([...infoPanel.querySelectorAll("details[open] > summary")].map((summary) => summary.textContent));
    infoPanel.replaceChildren(
      el("section", { class: "control-section" }, el("h4", {}, lattice ? "Structure and lattice" : "Structure"), factTable),
      ...(matrices.length ? [el("section", { class: "control-section" }, el("h4", {}, "Cell"), ...matrices)] : []),
      el("section", { class: "control-section info-extras" }, ...extras.flat().filter(Boolean)));
    for (const details of infoPanel.querySelectorAll("details")) if (open.has(details.firstChild.textContent)) details.open = true;
  }

  // Clear all: back to the plain structure. Orientation, zoom and pan, cell
  // repeats, slicing and hidden elements, measurements, selected and coloured
  // atoms, atom labels and the colouring (to element colours) are reset;
  // rings, planes and force arrows are switched off but keep their settings,
  // as do element styles, cutoffs and palettes.
  function resetView() {
    // Measurements and atom colours cannot be restored: ask first.
    const losing = [measureState.items.length ? `${measureState.items.length} measurement${measureState.items.length === 1 ? "" : "s"}` : null,
      paintState.groups.length ? `${paintState.groups.length} atom colour${paintState.groups.length === 1 ? "" : "s"}` : null].filter(Boolean);
    if (losing.length && !window.confirm(`Clear all? This removes ${losing.join(" and ")}.`)) return;
    Object.assign(viewerPrefs, { repeat: [1, 1, 1], slice: emptySlice(), hiddenElements: [], labels: "off", colour: "element" });
    viewerPrefs.rings.show = false;
    viewerPrefs.arrows.show = false;
    for (const plane of viewerPrefs.planes) plane.show = false;
    savePrefs();
    Object.assign(measureState, { mode: "off", pending: [], items: [] });
    Object.assign(paintState, { selected: [], groups: [] });
    Object.assign(sharedView, { R: presetRotation(structure, "top"), scale: null, pan: [0, 0] });
    renderStructurePage(structureId, params);
  }
  const resetViewButton = el("button", { type: "button", class: "small reset-view",
    title: "Back to the plain structure (r): top view, fitted; no repeats, slicing, hidden elements, measurements, atom colours, labels, rings, planes or arrows. Styles, cutoffs and other settings are kept." },
  "⟲ Clear all");
  resetViewButton.addEventListener("click", resetView);
  // The structure panels as SVG, beside Clear all (the Save tab has PNG too).
  const saveViewButton = el("button", { type: "button", class: "small save-view", title: "Save the structure panels as an SVG image",
    onclick: () => saveImage("svg") }, "Save SVG");
  viewerMain.querySelector(".viewer-footer").append(el("div", { class: "footer-actions" }, saveViewButton, resetViewButton));

  // Save: the structure in a file format, the panels as an image, settings.
  const formatSelect = el("select", { "aria-label": "File format" },
    [["extxyz", "extxyz"], ["vasp", "VASP POSCAR"], ["cif", "CIF"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.saveFormat === value }, label)));
  formatSelect.addEventListener("change", () => { viewerPrefs.saveFormat = formatSelect.value; savePrefs(); });
  const saveStructure = async (event, s = structure) => {
    const button = event.currentTarget;
    const format = formatSelect.value;
    const query = new URLSearchParams();
    if (format !== "extxyz") query.set("format", format);
    else if (!state.file && s === structure && page.force.evaluation) query.set("evaluation", page.force.evaluation.id);
    const text = query.toString();
    button.disabled = true;
    try {
      await downloadExport(`api/structures/${encodeURIComponent(s.id)}/extxyz${text ? `?${text}` : ""}`);
    } catch (error) {
      window.alert(`Export failed: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  };
  const saveImage = async (kind) => {
    const shown = page.panels.filter((p) => p.scene);
    if (!shown.length) return;
    const options = { transparent: viewerPrefs.svgTransparent, tripod: viewerPrefs.tripod.export };
    const name = `${structure.formula}-${structure.id}`;
    if (kind === "svg") downloadText(`${name}.svg`, panelsToSvg(shown, options), "image/svg+xml");
    else {
      const blob = await panelsToPng(shown, { ...options, scale: viewerPrefs.pngScale });
      if (blob) downloadBlob(`${name}.png`, blob);
      else window.alert("This image is too large for the browser; lower the PNG resolution or the panel size.");
    }
  };

  // Settings in tabs; each tab holds titled sections. The open tab is remembered.
  const section = (title, ...children) => el("section", { class: "control-section" }, title ? el("h4", {}, title) : null, ...children);
  const field = (label, control) => el("label", { class: "field" }, el("span", { class: "field-label" }, label), control);
  const button = (label, onclick, title) => el("button", { type: "button", class: "small", onclick, title }, label);
  const tabs = {
    info: ["Info", [infoPanel]],
    view: ["View", [
      section("Orientation",
        el("div", { class: "button-grid" },
          button("Top", preset("top"), "Look down the surface normal (t)"),
          button("Side a", preset("side-a"), "Side view with b across the screen"),
          button("Side b", preset("side-b"), "Side view with a across the screen"),
          button("⟲ 90°", roll(Math.PI / 2), "Turn the view 90° anticlockwise in the screen plane"),
          button("⟳ 90°", roll(-Math.PI / 2), "Turn the view 90° clockwise in the screen plane"),
          button("Fit", () => { page.panels[0].fit(); viewChanged(); }, "Zoom to fit (f)"))),
      section("Cell",
        el("div", { class: "inline-fields repeat-row" }, el("span", { class: "field-label" }, "Repeat"), repeatInputs[0], "×", repeatInputs[1], "×", repeatInputs[2]),
        checkbox("Cell outline", "cell", rebuildAll)),
      section("Axes",
        field("Tripod", tripodSelect),
        el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.tripod.export, onchange: (event) => {
          viewerPrefs.tripod.export = event.target.checked; savePrefs();
        } }), "Show in saved images")),
      el("details", { class: "help" }, el("summary", {}, "Mouse and keys"),
        el("ul", {},
          el("li", {}, "Drag to rotate; right-drag or Shift-drag to pan; scroll to zoom."),
          el("li", {}, "Click an axis of the tripod, or press a b c x y z, to look along it; again (or with Shift) for the other side."),
          el("li", {}, "f fits, t shows the top view, r clears all (back to the plain structure); ←/→ step, space plays."),
          el("li", {}, "Below the structure: click an element to hide it, right-click to change its colour and size."),
          el("li", {}, "Drag the bottom-right corner to resize the panel."))),
    ]],
    style: ["Style", [
      section("Show",
        el("div", { class: "check-row" }, checkbox("Bonds", "bonds", rebuildAll), checkbox("Polyhedra", "polyhedra", rebuildAll)),
        field("Atom labels", labelSelect)),
      section("Elements",
        el("table", { class: "stats cutoffs radii" },
          el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "colour"), el("th", {}, "radius (Å)"), el("th", {}, ""))),
          elementStyles),
        el("p", { class: "muted hint" }, "Blank radius: automatic.")),
      section("Sizes and opacity", sliderBox),
      el("details", {}, el("summary", {}, "Bond cutoffs"), el("table", { class: "stats cutoffs" }, el("tbody", {}, cutoffRows)),
        button("Reset cutoffs", () => {
          for (const [a, b] of pairs) viewerPrefs.cutoffs[pairKey(a, b)] = defaultCutoff(a, b);
          savePrefs(); renderStructurePage(structureId, params);
        })),
      el("details", {}, el("summary", {}, "Polyhedron centres"), centreBoxes),
      section(null, button("Reset style", resetAppearance)),
    ]],
    colour: ["Colour", [
      section("Colour atoms by", colourSelect, propertyControls, errorControls),
      colourMapSection,
      section("Highlight selected atoms", paintControls),
    ]],
    slice: ["Slice", [
      section("Elements", elementBoxes),
      section("Fractional coordinates", sliceTable,
        el("div", { class: "inline-fields" }, sliceCount, button("Show all", () => {
          resetFilter("slice", "hiddenElements", sliceTable, elementBoxes);
          sliceChanged();
        }))),
    ]],
    measure: ["Measure", [section("Measure", measureControls)]],
    planes: ["Planes", [section("Miller planes", planeList, button("Add plane", () => {
      const colour = PLANE_COLOURS[viewerPrefs.planes.length % PLANE_COLOURS.length];
      viewerPrefs.planes.push({ h: 0, k: 0, l: 1, t: 0.5, show: true, colour }); savePrefs(); renderPlanes(); rebuildAll();
    }))]],
    rings: ["Rings", [section(null,
      el("p", { class: "hint" }, "Finds the rings (closed loops of bonds) of a network of atoms and colours them by size: "
        + "hexagons and 5–7 defects in graphene, the 4- and 8-rings of an oxide overlayer, the rings of silica or a zeolite."),
      ringShowBox, ringBody)]],
    forces: ["Forces", [section(null, forceControls)]],
    // Only for structures served with vibrational modes (v_sim or phonopy).
    ...(vibrationControls ? { vibrations: ["Vibrations", [section(null, ...vibrationControls)]] } : {}),
    save: ["Save", [
      section("Structure",
        field("Format", formatSelect),
        el("p", { class: "muted hint" }, "extxyz includes the evaluation chosen in the Forces tab; POSCAR and CIF hold the geometry only."),
        el("div", { class: "button-row" },
          button("Save structure", (event) => saveStructure(event), "Save the structure on the left"),
          page.structures.length > 1 ? button("Save compared", (event) => saveStructure(event, page.structures[1]), "Save the structure on the right") : null)),
      section("Image",
        el("div", { class: "button-row" }, button("Save SVG", () => saveImage("svg"), "The panels as shown, as a vector image"),
          button("Save PNG", () => saveImage("png"), "The panels as shown, as a bitmap image")),
        checkbox("Transparent background", "svgTransparent"),
        el("div", { class: "inline-fields" }, el("span", { class: "field-label" }, "PNG resolution ×"), pngScaleInput)),
      section("Viewer settings",
        el("div", { class: "button-row" },
          button("Export", () => {
            downloadText("stoms-viewer-settings.json", `${JSON.stringify({ stoms_viewer_settings: 1, settings: viewerPrefs }, null, 2)}\n`, "application/json");
          }, "Save all viewer settings to a file"),
          button("Import", () => settingsInput.click(), "Load viewer settings from a file"), settingsInput,
          button("Restore defaults", () => {
            if (!window.confirm("Reset all viewer settings to their defaults? This also removes your planes and custom cutoffs.")) return;
            for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
            Object.assign(viewerPrefs, defaultPrefs());
            savePrefs();
            Object.assign(sharedView, { R: null, scale: null, pan: [0, 0], panelCount: 0 });
            renderStructurePage(structureId, params);
          }, "Reset every viewer setting to its default"))),
    ]],
  };
  // The first structure with modes opens on its Vibrations tab.
  if (vibrationControls && !vibrationTabShown) { viewerPrefs.tab = "vibrations"; vibrationTabShown = true; }
  if (!(viewerPrefs.tab in tabs)) viewerPrefs.tab = "view";
  const tabButtons = {}, tabPanels = {};
  for (const [key, [label, children]] of Object.entries(tabs)) {
    tabButtons[key] = el("button", { type: "button", class: "tab", role: "tab", id: `tab-${key}`, "aria-controls": `tabpanel-${key}`,
      onclick: () => showTab(key) }, label);
    tabPanels[key] = el("div", { class: "tab-panel", role: "tabpanel", id: `tabpanel-${key}`, "aria-labelledby": `tab-${key}` }, ...children);
  }
  function showTab(key) {
    viewerPrefs.tab = key; savePrefs();
    for (const name of Object.keys(tabs)) {
      tabButtons[name].setAttribute("aria-selected", String(name === key));
      tabButtons[name].tabIndex = name === key ? 0 : -1;
      tabPanels[name].hidden = name !== key;
    }
    controls.scrollTop = 0;
    renderInfo();
  }
  const tabBar = el("div", { class: "tab-bar", role: "tablist", "aria-label": "Viewer settings" }, Object.values(tabButtons));
  // Rows of at most five tabs, filled evenly (11 tabs: 4, 4 and 3).
  const tabRows = Math.ceil(Object.keys(tabs).length / 5);
  tabBar.style.gridTemplateColumns = `repeat(${Math.ceil(Object.keys(tabs).length / tabRows)}, 1fr)`;
  // Arrow keys move between tabs.
  tabBar.addEventListener("keydown", (event) => {
    const keys = Object.keys(tabs), at = keys.indexOf(viewerPrefs.tab);
    const next = event.key === "ArrowRight" ? at + 1 : event.key === "ArrowLeft" ? at - 1 : null;
    if (next === null) return;
    event.preventDefault(); event.stopPropagation();
    const key = keys[(next + keys.length) % keys.length];
    showTab(key); tabButtons[key].focus();
  });
  controls.append(tabBar, ...Object.values(tabPanels));
  showTab(viewerPrefs.tab);

  // --- evaluations of this structure (click a row for its details)
  const evaluationHeadings = ["Method", "Family", "Spec", "Energy", "Other scalars", "Per-atom vectors", "Tags", "Created", "ID"];
  const openEvaluations = new Set();
  const evaluationBody = el("tbody");
  function drawEvaluations() {
    evaluationBody.replaceChildren();
    for (const e of structure.evaluations) {
      const open = openEvaluations.has(e.id);
      evaluationBody.append(el("tr", {
        class: open ? "member-row open" : "member-row", title: "Show method, provenance, and properties",
        onclick: () => {
          if (open) openEvaluations.delete(e.id);
          else openEvaluations.add(e.id);
          drawEvaluations();
        },
      },
      el("td", {}, e.method), el("td", {}, e.family), el("td", {}, el("code", {}, e.spec_hash)),
      el("td", { class: "num" }, scalarText(e.scalars.find((p) => p.name === "energy"))),
      el("td", { class: "wrap" }, e.scalars.filter((p) => p.name !== "energy").map((p) => `${p.name} = ${scalarText(p)}`).join(", ") || "-"),
      el("td", {}, e.vectors.map((v) => v.name).join(", ") || "-"), el("td", { class: "wrap" }, e.tags.join(", ") || "-"),
      el("td", {}, formatDate(e.created_at)), el("td", {}, idCell(e.id))));
      if (open) evaluationBody.append(evaluationDetailRow(e.id, evaluationHeadings.length));
    }
  }
  if (structure.evaluations.length) {
    const evaluationWrap = el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, evaluationHeadings.map((h) => el("th", {}, h)))), evaluationBody));
    evaluationsSection.append(el("h2", {}, "Evaluations of this structure"),
      el("p", { class: "muted" }, "Click a row for the method specification, provenance, and every stored property."),
      evaluationWrap);
    // Keep expanded details within the visible part of a wide table.
    new ResizeObserver(() => {
      evaluationWrap.style.setProperty("--wrap-width", `${evaluationWrap.clientWidth}px`);
    }).observe(evaluationWrap);
    drawEvaluations();
  } else {
    evaluationsSection.append(el("h2", {}, "Evaluations of this structure"), el("p", { class: "muted" }, "No evaluations."));
  }

  // --- related structures (shared tag prefix, e.g. one CMA-ES run, or one aggregation)
  async function loadRelated() {
    page.stopMovie?.();
    page.movie = null;
    // Back to the page's own structures after a movie.
    let restored = false;
    page.originals.forEach((original, k) => {
      if (page.structures[k] === original) return;
      page.structures[k] = original; page.panels[k].structure = original; restored = true;
    });
    if (restored) {
      heading.replaceChildren(structure.formula, el("span", { class: "muted" }, ` · ${structure.positions.length} atoms`));
      page.panels.forEach((_, k) => captionOf(k));
      updateOverlays();
    }
    const byAggregation = cycle !== "tags";
    // "selected": only the members selected on the opening aggregation's page.
    const bySelection = cycle === "selected" && fromAgg;
    const sourceSelect = el("select", { class: "related-source", "aria-label": "Step through" },
      el("option", { value: "tags", selected: !byAggregation }, "Structures sharing a tag prefix"),
      fromAgg ? el("option", { value: "selected", selected: bySelection }, `Selected members of ${fromAgg.name}`) : null,
      state.aggregations.length ? el("optgroup", { label: "Aggregation members" },
        state.aggregations.map((a) => el("option", { value: a.id, selected: a.id === cycle }, a.name))) : null);
    sourceSelect.addEventListener("change", () => { location.hash = hash(structure.id, { cycle: sourceSelect.value }); });
    const prefixInput = el("input", { type: "text", value: viewerPrefs.prefix, class: "prefix-input", spellcheck: "false", "aria-label": "Tag prefix" });
    prefixInput.addEventListener("change", () => { viewerPrefs.prefix = prefixInput.value; savePrefs(); loadRelated(); });
    const hint = el("span", { class: "muted related-hint" });
    relatedSection.replaceChildren(
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Step through"), sourceSelect,
        byAggregation ? null : [el("span", { class: "muted" }, "with prefix"), prefixInput], hint));
    let related;
    try {
      // An aggregation's list is the same from every member; a tag-prefix list
      // is the same for every structure with the same tags under that prefix.
      const aggregationId = bySelection ? fromAgg.id : cycle;
      const prefixTags = structure.tags.filter((t) => t.startsWith(viewerPrefs.prefix)).sort().join(",");
      related = await loadRelatedList(
        byAggregation ? `aggregation:${aggregationId}` : `prefix:${viewerPrefs.prefix}:${prefixTags}`,
        `structures/${encodeURIComponent(structure.id)}/related?${byAggregation
          ? `aggregation=${encodeURIComponent(aggregationId)}` : `prefix=${encodeURIComponent(viewerPrefs.prefix)}`}`);
    } catch (error) {
      relatedSection.style.minHeight = "";
      relatedSection.append(el("p", { class: "error" }, error.message));
      return;
    }
    if (page.disposed) return;
    // The bar is rebuilt below in one go, so the reserved height can go now.
    relatedSection.style.minHeight = "";
    const selection = bySelection ? picksOf(fromAgg.id) : null;
    // Stepping the right panel skips the left one's structure (the reference).
    const side = page.side, stepping = page.originals[side];
    const list = (selection ? related.structures.filter((r) => selection.has(r.ordinal)) : related.structures)
      .filter((r) => !side || r.id !== structure.id);
    const go = (id) => (side ? hash(structure.id, { compare: id }) : hash(id));
    const source = bySelection ? `${related.aggregation.name}, selected` : byAggregation ? related.aggregation.name : related.tags.join(", ");
    // Frames chosen from a file (serve --frames) carry their number in the
    // file as a frame: tag, which then labels them instead of the ordinal.
    const frameOf = (r) => r.distinct_tags.find((t) => t.startsWith("frame:"))?.slice(6);
    const label = (r) => [byAggregation && !frameOf(r) ? `#${r.ordinal}` : null, frameOf(r) ? `frame ${frameOf(r)}` : null,
      r.iteration ? `it ${r.iteration}` : null,
      ...r.distinct_tags.filter((t) => !t.startsWith("frame:")).map((t) => t.split(":").pop())].filter(Boolean).join(" · ") || r.id;
    // Within a tag prefix, compare within one iteration (founder / winner /
    // relaxed winner); the same run index in another iteration is an unrelated structure.
    const iteration = byAggregation ? null : iterationOf(structure.tags);
    compareSelect.replaceChildren(el("option", { value: "" }, "No comparison"),
      ...list.filter((r) => r.id !== structure.id && (!iteration || r.iteration === iteration)).map((r) => el("option", { value: r.id, selected: r.id === params.get("compare") }, `${source}: ${label(r)}`)));
    if (!list.length) {
      relatedSection.append(el("p", { class: "muted" }, bySelection
        ? `No members of ${fromAgg.name} are selected.`
        : `This structure has no tag starting with "${viewerPrefs.prefix}"; change the prefix, or step through an aggregation instead.`));
      return;
    }
    // For ring counts over every structure stepped through.
    page.stepList = { list, label };
    renderRingSummary();
    // Outside the list (e.g. not a member of the aggregation), ← / → enter it from the end / start.
    const position = list.findIndex((r) => r.id === stepping.id);
    const step = (delta) => {
      const from = page.movie ? page.movie.index : position;
      const next = list[from < 0 ? (delta > 0 ? 0 : list.length - 1) : from + delta];
      if (next) location.hash = go(next.id);
    };
    let picker;
    if (list.length <= MAX_RELATED_CHIPS) {
      picker = el("div", { class: "chips related-chips" }, list.map((r) => el("a", {
        class: "chip", href: go(r.id), "aria-pressed": String(r.id === stepping.id), title: r.id,
      }, label(r))));
    } else {
      const input = el("input", { type: "number", min: 1, max: list.length, step: 1, value: position >= 0 ? position + 1 : "",
        class: "num-input", "aria-label": "Position" });
      input.addEventListener("change", () => { const next = list[Number(input.value) - 1]; if (next) location.hash = go(next.id); });
      picker = el("span", { class: "inline-fields" }, input, el("span", { class: "muted" },
        `of ${list.length}${position >= 0 ? ` · ${label(list[position])}` : ""}`));
    }
    // The aggregation's name is already in the select.
    hint.textContent = [byAggregation && !bySelection ? null : source,
      `${list.length} structure${list.length === 1 ? "" : "s"}${side ? " in the right panel" : ""}`,
      position < 0 ? "this structure is not among them" : null,
      list.length > 1 ? "←/→ step, space plays" : null].filter(Boolean).join(" · ");
    // Nothing to step through or play.
    if (list.length === 1 && position === 0) return;
    relatedSection.append(el("div", { class: "related-strip" },
      el("button", { type: "button", class: "small", disabled: position === 0, onclick: () => step(-1) }, "← Previous"),
      picker,
      el("button", { type: "button", class: "small", disabled: position === list.length - 1, onclick: () => step(1) }, "Next →")));
    if (picker.classList.contains("related-chips")) {
      // Scroll the current chip into view; fade the edge that hides more chips.
      requestAnimationFrame(() => {
        const current = picker.querySelector("[aria-pressed=true]");
        if (current) picker.scrollLeft = current.offsetLeft - picker.offsetLeft - (picker.clientWidth - current.offsetWidth) / 2;
        const edges = () => {
          picker.classList.toggle("more-left", picker.scrollLeft > 1);
          picker.classList.toggle("more-right", picker.scrollLeft + picker.clientWidth < picker.scrollWidth - 1);
        };
        edges();
        picker.addEventListener("scroll", edges, { passive: true });
      });
    }

    // --- movie: play a range of the listed structures as frames inside this
    // page. The view and all settings stay; colour scales span the range's
    // frames (scaleMax). Ranges are kept per step list while browsing.
    const rangeKey = `${byAggregation ? cycle : related.tags.join(",")}|${list.length}|${side}`;
    let [first, last] = movieRanges.get(rangeKey) ?? [0, Math.min(MOVIE_FRAMES, list.length) - 1];
    const startAt = () => (position >= first && position <= last ? position : first);
    const playButton = el("button", { type: "button", class: "small play-button" }, "▶ Play");
    const frameSlider = el("input", { type: "range", min: first, max: last, step: 1, value: startAt(),
      class: "frame-slider", "aria-label": "Frame" });
    const frameLabel = el("span", { class: "muted frame-label" });
    // The position counts the list from 1, as the Frames range does; "#" is a member's ordinal.
    const showLabel = (i) => { frameLabel.textContent = `${label(list[i])} · ${i + 1} of ${list.length}`; };
    showLabel(Math.max(0, position));
    const fpsInput = el("input", { type: "number", min: 1, max: 60, step: 1, value: viewerPrefs.player.fps, class: "num-input",
      "aria-label": "Frames per second", onchange: (event) => {
        const value = Math.round(Number(event.target.value));
        viewerPrefs.player.fps = value >= 1 ? Math.min(60, value) : DEFAULT_PLAYER.fps;
        event.target.value = viewerPrefs.player.fps; savePrefs();
      } });
    const loopBox = el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.player.loop,
      onchange: (event) => { viewerPrefs.player.loop = event.target.checked; savePrefs(); } }), "Loop");
    // Frame range, numbered like the frame counter (1 = first listed structure).
    const rangeInput = (which) => el("input", { type: "number", min: 1, max: list.length, step: 1,
      value: (which ? last : first) + 1, class: "num-input", "aria-label": which ? "Last frame" : "First frame" });
    const firstInput = rangeInput(0), lastInput = rangeInput(1);
    const rangeNote = el("span", { class: "muted range-note" });
    const showRange = () => {
      firstInput.value = first + 1; lastInput.value = last + 1;
      frameSlider.min = first; frameSlider.max = last;
      rangeNote.textContent = last - first + 1 > MOVIE_FRAMES
        ? `${last - first + 1} frames: loading more than ${MOVIE_FRAMES} at once can stall; press Play again to continue loading.`
        : list.length > MOVIE_MAX_FRAMES ? `(at most ${MOVIE_MAX_FRAMES} frames at once)` : "";
    };
    const rangeChanged = () => {
      const lo = Math.round(Number(firstInput.value)), hi = Math.round(Number(lastInput.value));
      first = Math.max(0, Math.min(list.length - 1, (Number.isFinite(lo) ? lo : 1) - 1));
      last = Math.max(first, Math.min(list.length - 1, first + MOVIE_MAX_FRAMES - 1, (Number.isFinite(hi) ? hi : list.length) - 1));
      movieRanges.set(rangeKey, [first, last]);
      stop(false);
      page.movie = null;
      showRange();
      frameSlider.value = startAt();
    };
    firstInput.addEventListener("change", rangeChanged);
    lastInput.addEventListener("change", rangeChanged);
    relatedSection.append(el("div", { class: "player" }, playButton, frameSlider, frameLabel,
      el("span", { class: "inline-fields" }, fpsInput, el("span", { class: "muted" }, "fps")), loopBox),
    el("div", { class: "player-range inline-fields" }, el("span", { class: "muted" }, "Frames"), firstInput, "–", lastInput,
      el("span", { class: "muted" }, `of ${list.length}`), rangeNote));
    showRange();

    let playing = false, timer = 0;
    const frameAt = (i) => page.movie.frames[i - page.movie.first];
    // Loads the range's frames. Frames that arrived stay cached (loadStructure),
    // so after a stalled load, Play again continues with the missing ones.
    async function loadMovie() {
      if (page.movie) return true;
      const ids = list.slice(first, last + 1).map((r) => r.id);
      const movieKey = `${rangeKey}|${first}|${last}`;
      if (lastMovie?.key === movieKey) {
        page.movie = { frames: lastMovie.frames, first, last, index: startAt(), scales: lastMovie.scales, side };
        return true;
      }
      let done = 0;
      frameLabel.textContent = `Loading frames 0 / ${ids.length}…`;
      const results = await Promise.allSettled(ids.map((id) => loadStructure(id).then((frame) => {
        done += 1;
        if (done % 10 === 0 || done === ids.length) frameLabel.textContent = `Loading frames ${done} / ${ids.length}…`;
        return frame;
      })));
      if (page.disposed) return false;
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed) {
        frameLabel.textContent = `${failed} of ${ids.length} frames did not load; press Play again to continue.`;
        return false;
      }
      page.movie ??= { frames: results.map((r) => r.value), first, last, index: startAt(), scales: new Map(), side };
      lastMovie = { key: movieKey, frames: page.movie.frames, scales: page.movie.scales };
      return true;
    }
    async function showFrame(i) {
      const frame = frameAt(i);
      page.movie.index = i;
      page.structures[side] = frame;
      page.panels[side].structure = frame;
      frameSlider.value = i;
      showLabel(i);
      if (side) captionOf(side);
      else heading.replaceChildren(frame.formula, el("span", { class: "muted" }, ` · ${frame.positions.length} atoms · frame ${i + 1} of ${list.length}`));
      await updateOverlays();
    }
    // The next frame is scheduled after the current one is drawn, so slow
    // frames delay the movie instead of piling up.
    function tick() {
      if (!playing || page.disposed) return;
      let next = page.movie.index + 1;
      if (next > page.movie.last) {
        if (!viewerPrefs.player.loop) { stop(true); return; }
        next = page.movie.first;
      }
      const started = performance.now();
      showFrame(next).then(() => {
        if (playing) timer = setTimeout(tick, Math.max(0, 1000 / viewerPrefs.player.fps - (performance.now() - started)));
      });
    }
    async function play() {
      if (playing || !(await loadMovie()) || page.disposed) return;
      playing = true;
      playButton.textContent = "❚❚ Pause";
      if (!viewerPrefs.player.loop && page.movie.index >= page.movie.last) await showFrame(page.movie.first);
      timer = setTimeout(tick, 1000 / viewerPrefs.player.fps);
    }
    // Stopping on a frame opens that frame's own page (facts, evaluations).
    function stop(open) {
      playing = false;
      clearTimeout(timer);
      playButton.textContent = "▶ Play";
      const id = page.movie ? frameAt(page.movie.index).id : null;
      if (open && id && id !== stepping.id) location.hash = go(id);
    }
    page.stopMovie = () => stop(false);
    playButton.addEventListener("click", () => (playing ? stop(true) : play()));
    // Scrubbing shows frames in place; releasing the slider opens that frame.
    frameSlider.addEventListener("input", async () => {
      stop(false);
      if (await loadMovie()) showFrame(Number(frameSlider.value));
    });
    frameSlider.addEventListener("change", () => {
      stop(false);
      const id = list[Number(frameSlider.value)].id;
      if (id !== stepping.id) location.hash = go(id);
    });
    // Chips stay on one scrolling row; keep the current one in view.
    const active = picker.querySelector("[aria-pressed=true]");
    if (active) {
      const box = picker.getBoundingClientRect(), chip = active.getBoundingClientRect();
      picker.scrollLeft += chip.left - box.left - (box.width - chip.width) / 2;
    }
    restoreScroll();
    page.onKey = (event) => {
      if (event.target.closest("input, select, textarea")) return;
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
      if (event.key === " " && !event.target.closest("button, a")) {
        event.preventDefault();
        if (playing) stop(true); else play();
      }
    };
  }
  page.onKey = null;
  const keyHandler = (event) => {
    if (event.key === "Escape" && (page.closeEditor?.() || page.cancelMeasure?.())) return;
    // View keys: look along an axis (Shift: from the other side), fit, top view.
    if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest("input, select, textarea")) {
      const key = event.key.toLowerCase();
      if ("abcxyz".includes(key) && key.length === 1) { alignAxis(key, event.shiftKey ? true : null); return; }
      if (key === "f") { page.panels[0].fit(); viewChanged(); return; }
      if (key === "t") { animateView(presetRotation(structure, "top")); return; }
      if (key === "r") { resetView(); return; }
    }
    page.onKey?.(event);
  };
  window.addEventListener("keydown", keyHandler);

  page.dispose = () => {
    page.disposed = true;
    for (const type of readerScrolls) window.removeEventListener(type, stopRestoring);
    settingsFit.disconnect();
    wide.removeEventListener("change", fitSettings);
    page.stopMovie?.();
    page.stopVibration?.();
    window.removeEventListener("keydown", keyHandler);
    sharedView.listeners.clear();
    page.panels.forEach((p) => p.dispose());
  };

  // Panel width changes with the number of panels, so refit the shared zoom.
  if (sharedView.panelCount !== page.panels.length) {
    sharedView.panelCount = page.panels.length;
    sharedView.scale = null;
    sharedView.pan = [0, 0];
  }
  restoreScroll();
  await updateOverlays();
  rebuildAll();
  loadRelated();
}

function leaveStructurePage() {
  currentPage?.dispose();
  currentPage = null;
}
