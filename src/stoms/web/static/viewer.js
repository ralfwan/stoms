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

// Sequential palettes for the value colourings, low to high. Single-hue ramps
// run light to dark; viridis and cividis (perceptually uniform, readable with
// colour-vision deficiencies) run dark to light. Lightness is monotonic in all.
const PALETTES = {
  blue: { label: "Blue", stops: ["#dceafb", "#6c9fdf", "#123f7a"] },
  green: { label: "Green", stops: ["#e2f3ea", "#4fae84", "#0d5a3a"] },
  orange: { label: "Orange", stops: ["#fde8d8", "#ee8a4c", "#8c2a06"] },
  purple: { label: "Purple", stops: ["#ece6f8", "#8f74d2", "#36206e"] },
  grey: { label: "Grey", stops: ["#ededeb", "#8d8c88", "#2c2c2a"] },
  viridis: { label: "Viridis", stops: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"] },
  cividis: { label: "Cividis", stops: ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"] },
};
// Palette per colour mode (height, force magnitude, force difference).
const DEFAULT_PALETTES = { height: "blue", force: "green", error: "orange" };
const paletteStops = (mode) => (PALETTES[viewerPrefs.palettes[mode]] ?? PALETTES[DEFAULT_PALETTES[mode]]).stops;
function ramp(mode, t) {
  const stops = paletteStops(mode);
  const x = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  return mix(stops[i], stops[i + 1], x - i);
}

// ---------------------------------------------------------------- preferences & shared view

const DEFAULT_APPEARANCE = { polyAlpha: 0.45, polyEdges: true, planeAlpha: 0.2, bondRadius: 0.08, radii: {}, colours: {} };
// Per-element radii and colours are objects of their own in every appearance.
const freshAppearance = () => ({ ...DEFAULT_APPEARANCE, radii: {}, colours: {} });
// Force arrows: length scale in Angstrom per force unit, shaft radius in
// Angstrom, colour (null = text colour of the theme), hidden below minMagnitude.
const DEFAULT_ARROWS = { show: false, scale: 1, width: 0.04, colour: null, minMagnitude: 0 };
const emptySlice = () => [[null, null], [null, null], [null, null]];
// Movie playback: frames per second and whether it starts over at the end.
const DEFAULT_PLAYER = { fps: 10, loop: true };

function defaultPrefs() {
  return { cell: true, bonds: false, polyhedra: false, colour: "element",
    repeat: [1, 1], cutoffs: {}, polyCenters: null, prefix: "run:",
    slice: emptySlice(), hiddenElements: [], planes: [],
    appearance: freshAppearance(),
    // Force atom selection follows the slice unless forceFollowsSlice is off.
    arrows: { ...DEFAULT_ARROWS }, forceFollowsSlice: true, forceSlice: emptySlice(), forceHiddenElements: [],
    // Last chosen force method ({ spec, method, name }) and force-difference
    // pair ([{ spec, method }, { spec, method }]); see matchMethod.
    forceChoice: null, pairChoice: null,
    palettes: { ...DEFAULT_PALETTES },
    // Structure panel size in pixels; null = automatic.
    panelSize: { width: null, height: null },
    player: { ...DEFAULT_PLAYER },
    // Save SVG without a background, in light-theme colours (for any page).
    svgTransparent: true };
}

// Settings from storage or an imported file, completed with defaults. Unknown
// keys are dropped, and values of the wrong kind fall back to the default.
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
    ["palettes", DEFAULT_PALETTES], ["panelSize", { width: null, height: null }], ["player", DEFAULT_PLAYER]]) {
    prefs[key] = { ...defaults, ...prefs[key] };
  }
  prefs.appearance.radii = { ...prefs.appearance.radii };
  prefs.appearance.colours = { ...prefs.appearance.colours };
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

function surfaceNormal(cell) { return unit(cross(cell[0], cell[1])); }

function presetRotation(cell, preset) {
  const n = surfaceNormal(cell);
  const a = unit(cell[0]);
  const b = unit(sub(cell[1], mul(n, dot(cell[1], n))));
  if (preset === "side-a") return orthonormalize([b, n, cross(b, n)]);
  if (preset === "side-b") return orthonormalize([mul(a, -1), n, cross(mul(a, -1), n)]);
  return orthonormalize([a, cross(n, a), n]); // top: look down the surface normal
}

function rotateScreen(axis, angle) {
  const c = Math.cos(angle), s = Math.sin(angle);
  const M = axis === "x" ? [[1, 0, 0], [0, c, -s], [0, s, c]] : [[c, 0, s], [0, 1, 0], [-s, 0, c]];
  const R = sharedView.R;
  sharedView.R = orthonormalize(M.map((row) => [0, 1, 2].map((k) => row[0] * R[0][k] + row[1] * R[1][k] + row[2] * R[2][k])));
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

// Polygon where h*x + k*y + l*z = t (fractional) cuts the box [0,na]x[0,nb]x[0,1].
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

// Categorical slots (validated reference palette) for plane identity.
const PLANE_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7", "#008300", "#e34948"];

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

// Everything a renderer draws, in Angstrom world coordinates. `forces` (or
// null) holds per-atom vectors, magnitudes and inclusion for the arrows.
function buildScene(structure, overlay, forces) {
  const prefs = viewerPrefs;
  const [A, B] = structure.cell;
  const na = structure.pbc[0] ? prefs.repeat[0] : 1, nb = structure.pbc[1] ? prefs.repeat[1] : 1;
  const ballAndStick = prefs.bonds || prefs.polyhedra;
  const colours = structure.symbols.map((symbol, i) => overlay.colour(i, symbol));
  for (const group of paintState.groups) {
    if (fitsStructure(structure, group.atoms)) for (const r of group.atoms) colours[r.index] = group.colour;
  }
  const radii = structure.symbols.map(atomRadius);
  const images = [];
  for (let ia = 0; ia < na; ia++) for (let ib = 0; ib < nb; ib++) images.push(add(mul(A, ia), mul(B, ib)));
  const recip = reciprocal(structure.cell);
  const hidden = new Set(prefs.hiddenElements);
  const visible = structure.positions.map((p, i) => !hidden.has(structure.symbols[i]) && inSlice(fractional(recip, p)));
  const atoms = [];
  let centreSum = [0, 0, 0];
  images.forEach((shift) => structure.positions.forEach((p, i) => {
    centreSum = add(centreSum, add(p, shift));
    if (visible[i]) atoms.push({ index: i, position: add(p, shift), radius: radii[i], colour: colours[i] });
  }));
  const halfBonds = [], polyhedra = [];
  if (ballAndStick) {
    const bonds = neighbours(structure, prefs.cutoffs);
    if (prefs.bonds) {
      for (const shift of images) for (const bond of bonds) {
        if (!visible[bond.i] || !visible[bond.j]) continue;
        const from = add(structure.positions[bond.i], shift);
        halfBonds.push({ from, to: mul(add(from, add(bond.to, shift)), 0.5), colour: colours[bond.i] });
      }
    }
    if (prefs.polyhedra) {
      const centres = new Set(prefs.polyCenters ?? structure.symbols.filter((s) => TRANSITION_METALS.has(s)));
      const ligands = new Map();
      for (const bond of bonds) {
        if (!visible[bond.i] || !centres.has(structure.symbols[bond.i]) || !NONMETALS.has(structure.symbols[bond.j])) continue;
        if (!ligands.has(bond.i)) ligands.set(bond.i, []);
        ligands.get(bond.i).push(bond.to);
      }
      for (const [i, points] of ligands) {
        if (points.length < 4) continue;
        const faces = hullFaces(points);
        for (const shift of images) {
          polyhedra.push({ colour: colours[i], faces: faces.map((f) => ({ normal: f.normal, points: f.points.map((p) => add(p, shift)) })) });
        }
      }
    }
  }
  const [, , C] = structure.cell;
  const corners = [];
  for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) corners.push(add(add(mul(A, i), mul(B, j)), mul(C, k)));
  const cellEdges = prefs.cell ? [[0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3], [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7]].map(([a, b]) => [corners[a], corners[b]]) : [];
  // Centre on every atom so slicing does not move the view.
  const centre = mul(centreSum, 1 / Math.max(1, images.length * structure.positions.length));
  const planes = prefs.planes.map((plane, k) => ({ plane, k })).filter(({ plane }) => plane.show && (plane.h || plane.k || plane.l))
    .map(({ plane, k }) => ({ colour: PLANE_COLOURS[k % PLANE_COLOURS.length], polygon: planePolygon(structure.cell, plane, [na, nb, 1]) }))
    .filter((p) => p.polygon);
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
    centre, bondRadius: prefs.appearance.bondRadius, structure, overlay,
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

function fitScale(scene, width, height) {
  const R = sharedView.R;
  const points = [...scene.atoms.map((a) => a.position), ...scene.cellEdges.flat()];
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const p of points) {
    const d = sub(p, scene.centre);
    const x = dot(R[0], d), y = dot(R[1], d);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  return 0.9 * Math.min(width / Math.max(1, x1 - x0 + 3), height / Math.max(1, y1 - y0 + 3));
}

// ---------------------------------------------------------------- display list

// Default arrow colour: the page's text colour, so arrows suit light and dark themes.
const themeTextColour = () => getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#1d2125";

// Everything a scene shows, as 2D primitives in painting order (back to front),
// for the canvas and for SVG export. Pixel coordinates; y points down.
//   sphere:  { kind, x, y, r, colour }
//   line:    { kind, a, b, colour, width }
//   polygon: { kind, points, fill, fillAlpha, stroke, strokeAlpha, strokeWidth }
//   arrow:   { kind, a, b, colour, width }
//   label:   { kind, x, y, text, colour, halo }
//   ring:    { kind, x, y, r, colour, width }
// Lines may carry a dash pattern. `theme` holds CSS colours (themeColours).
function displayList(scene, width, height, theme) {
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
  items.sort((p, q) => p.z - q.z);
  const list = scene.cellEdges.map(([a, b]) => ({ kind: "line", a: project(a), b: project(b), colour: theme.cell, width: 1 }));
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
  // Measurements are always drawn on top, so they stay visible. A label that
  // would overlap an earlier one moves up until it is free.
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
  return list;
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

const LABEL_FONT = "600 12px system-ui, -apple-system, \"Segoe UI\", sans-serif";

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

const spriteCache = new Map();
function sphereSprite(colour, radius) {
  const r = Math.max(1, Math.round(radius * 2) / 2);
  const key = `${colour}|${r}`;
  let sprite = spriteCache.get(key);
  if (sprite) return sprite;
  const size = Math.ceil(2 * r + 2);
  sprite = document.createElement("canvas");
  sprite.width = sprite.height = size;
  const ctx = sprite.getContext("2d");
  const c = size / 2;
  const gradient = ctx.createRadialGradient(c - 0.35 * r, c - 0.35 * r, 0.1 * r, c, c, r);
  for (const [offset, stop] of sphereStops(colour)) gradient.addColorStop(offset, stop);
  ctx.fillStyle = gradient;
  ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = 1; ctx.stroke();
  if (spriteCache.size > 600) spriteCache.clear();
  spriteCache.set(key, sprite);
  return sprite;
}

function paintCanvas(ctx, list) {
  const path = (points) => { ctx.beginPath(); points.forEach((q, i) => (i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]))); };
  for (const prim of list) {
    if (prim.kind === "sphere") {
      const sprite = sphereSprite(prim.colour, prim.r);
      ctx.drawImage(sprite, prim.x - sprite.width / 2, prim.y - sprite.height / 2);
    } else if (prim.kind === "line") {
      ctx.strokeStyle = prim.colour; ctx.lineWidth = prim.width; ctx.lineCap = "butt";
      if (prim.dash) ctx.setLineDash(prim.dash);
      path([prim.a, prim.b]); ctx.stroke();
      if (prim.dash) ctx.setLineDash([]);
    } else if (prim.kind === "label") {
      ctx.font = LABEL_FONT; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.lineWidth = 3; ctx.lineJoin = "round"; ctx.strokeStyle = prim.halo; ctx.strokeText(prim.text, prim.x, prim.y);
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

function createCanvasRenderer(host) {
  const canvas = el("canvas", { class: "viewer-canvas" });
  host.append(canvas);
  return {
    draw(scene) {
      const dpr = window.devicePixelRatio || 1;
      const width = host.clientWidth, height = host.clientHeight;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
        canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
      }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      paintCanvas(ctx, displayList(scene, width, height, themeColours(host)));
    },
    dispose() { canvas.remove(); },
  };
}

// ---------------------------------------------------------------- SVG export

// The panels as one SVG document, side by side as on screen, each on its
// panel background. Spheres share one radial gradient per colour.
// With `transparent`, no background and light-theme colours; otherwise the
// panel's background and the page's theme, as on screen.
function panelsToSvg(panels, { transparent = false } = {}) {
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
    for (const prim of displayList(panel.scene, width, height, theme)) {
      if (prim.kind === "sphere") {
        shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(Math.max(0.5, prim.r))}" fill="url(#${gradient(prim.colour)})" stroke="#000" stroke-opacity="0.35"/>`);
      } else if (prim.kind === "line") {
        const dash = prim.dash ? ` stroke-dasharray="${prim.dash.join(" ")}"` : "";
        shapes.push(`<line x1="${round(prim.a[0])}" y1="${round(prim.a[1])}" x2="${round(prim.b[0])}" y2="${round(prim.b[1])}" stroke="${prim.colour}" stroke-width="${round(prim.width)}"${dash}/>`);
      } else if (prim.kind === "label") {
        const text = prim.text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        shapes.push(`<text x="${round(prim.x)}" y="${round(prim.y)}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="12" font-weight="600" fill="${prim.colour}" stroke="${prim.halo}" stroke-width="3" stroke-linejoin="round" paint-order="stroke">${text}</text>`);
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

function downloadText(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el("a", { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- viewer panel

// One panel: a structure, its overlay data, a renderer, and pointer interaction.
function createPanel(host) {
  const panel = { structure: null, overlay: null, forces: null, scene: null, renderer: null };
  const stage = el("div", { class: "viewer-stage" });
  const tooltip = el("div", { class: "tooltip" });
  host.append(stage, tooltip);
  panel.stage = stage;
  panel.renderer = createCanvasRenderer(stage);
  panel.rebuild = () => {
    if (!panel.structure || !panel.overlay) return;
    panel.scene = buildScene(panel.structure, panel.overlay, panel.forces);
    panel.draw();
  };
  panel.draw = () => {
    if (!panel.scene || !panel.renderer || !stage.clientWidth) return;
    if (!sharedView.R) sharedView.R = presetRotation(panel.structure.cell, "top");
    if (!sharedView.scale) sharedView.scale = fitScale(panel.scene, stage.clientWidth, stage.clientHeight);
    panel.renderer.draw(panel.scene);
  };
  panel.fit = () => {
    if (!panel.scene) return;
    sharedView.pan = [0, 0];
    sharedView.scale = fitScale(panel.scene, stage.clientWidth, stage.clientHeight);
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
    if (!click || !panel.onPick) return;
    const atom = atomAt(event);
    if (atom) {
      // The periodic image of the clicked copy, relative to the atom itself.
      const offset = sub(atom.position, panel.structure.positions[atom.index]);
      const image = fractional(reciprocal(panel.structure.cell), offset).map(Math.round);
      panel.onPick({ index: atom.index, image, symbol: panel.structure.symbols[atom.index], count: panel.structure.symbols.length });
    }
  });
  stage.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });
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

  function hover(event) {
    const atom = atomAt(event);
    if (!atom) { tooltip.style.display = "none"; return; }
    const box = stage.getBoundingClientRect();
    const mx = event.clientX - box.left, my = event.clientY - box.top;
    const lines = panel.overlay.describe(atom.index);
    const forces = panel.forces, i = atom.index;
    if (forces) {
      lines.push(forces.included[i]
        ? [`${formatNumber(forces.magnitudes[i])}${forces.unit ? ` ${forces.unit}` : ""}`, `|${forces.name}|`]
        : ["not included", `in ${forces.name}`]);
    }
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
  const n = surfaceNormal(structure.cell);
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
    structure = await api(`structures/${encodeURIComponent(structureId)}`);
  } catch (error) {
    setMain(el("p", { class: "error" }, error.message));
    return;
  }
  document.title = `STOMS · ${structure.formula}`;
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
    if (page.force.explicit && page.force.evaluation) query.set("forces", page.force.evaluation.spec_hash);
    const text = query.toString();
    return `#/structures/${encodeURIComponent(id)}${text ? `?${text}` : ""}`;
  };

  // --- layout
  const stages = el("div", { class: "viewer-panels" });
  const legend = el("div", { class: "viewer-legend" });
  const status = el("p", { class: "muted viewer-status" });
  const controls = el("aside", { class: "viewer-controls" });
  // Sits above the figure so stepping and the structure stay in view together.
  const relatedSection = el("section", { class: "related-bar", "aria-label": "Related structures" });
  const evaluationsSection = el("section");
  // Beside the structure, the settings box is as tall as the structure column
  // and scrolls on its own, so both end at the same line and the structure
  // stays in view; in one column the settings are part of the page.
  const viewerMain = el("div", {}, stages, legend, status);
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
    el("dl", { class: "facts" },
      el("dt", {}, "Structure"), el("dd", {}, idCell(structure.id)),
      el("dt", {}, "Source"), el("dd", {}, structure.source || "-"),
      el("dt", {}, "Tags"), el("dd", {}, structure.tags.length ? structure.tags.join(", ") : "-"),
      fromAgg ? [el("dt", {}, "Selection"), el("dd", {}, pickField)] : null),
    relatedSection,
    el("div", { class: "viewer-layout" }, viewerMain, controls),
    evaluationsSection);

  // --- panels
  const addPanel = (s, caption) => {
    const host = el("div", { class: "viewer-panel" });
    const panel = createPanel(host);
    panel.structure = s;
    if (caption) host.prepend(el("div", { class: "viewer-caption" }, caption));
    stages.append(host);
    page.panels.push(panel);
    return panel;
  };
  addPanel(structure, null);
  const compareId = params.get("compare");
  if (compareId && compareId !== structure.id) {
    try {
      const other = await api(`structures/${encodeURIComponent(compareId)}`);
      page.structures.push(other);
      stages.firstChild.prepend(el("div", { class: "viewer-caption" }, panelCaption(structure)));
      addPanel(other, panelCaption(other));
    } catch (error) {
      status.textContent = `Compare structure: ${error.message}`;
    }
  }
  stages.classList.toggle("two", page.panels.length === 2);

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
  const includedValues = (d) => (d ? d.values.filter((v, i) => d.included[i]) : []);
  async function scaleMax(kind, compute, shown) {
    if (!page.movie) return Math.max(1e-9, ...shown.flatMap(includedValues));
    // Keyed by methods, not evaluation IDs, so a kept movie (lastMovie) reuses
    // its scales on the next structure's page.
    const method = (e) => (e ? [e.spec ?? e.spec_hash, e.method] : null);
    const target = forceTarget();
    const key = JSON.stringify([kind, method(target.chosen), target.name, chosenPair().map(method), page.vector,
      viewerPrefs.forceFollowsSlice, viewerPrefs.slice, viewerPrefs.hiddenElements, viewerPrefs.forceSlice,
      viewerPrefs.forceHiddenElements, page.structures.slice(1).map((s) => s.id)]);
    if (!page.movie.scales.has(key)) {
      const all = [...page.movie.frames, ...page.structures.slice(1)];
      const load = Promise.all(all.map(compute)).then((data) => Math.max(1e-9, ...data.flatMap(includedValues)));
      load.catch(() => page.movie?.scales.delete(key));
      page.movie.scales.set(key, load);
    }
    return page.movie.scales.get(key);
  }
  const forceValues = async (s) => { const d = await forceDataFor(s); return d && { values: d.magnitudes, included: d.included }; };

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
      const range = page.movie ? [...page.movie.frames, ...page.structures.slice(1)].map(heights).flat() : hs.flat();
      const lo = Math.min(...range), hi = Math.max(...range);
      page.structures.forEach((s, k) => overlays.push({
        colour: (i) => ramp("height", (hs[k][i] - lo) / (hi - lo || 1)),
        describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[k][i].toFixed(2)} Å`, "height"]],
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
          } : elementOverlay(s));
        });
        legend.replaceChildren(rampLegend("force", "0", `${formatNumber(max)} ${data[0].unit}`,
          `|${data[0].name}| per atom (${data[0].method})${notIncludedNote(data)}`));
      }
    } else {
      page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      legend.replaceChildren(el("div", { class: "legend" }, species.map((sym) =>
        el("span", {}, elementSwatch(sym), sym))));
    }
    status.textContent = notes.join(" ");
    page.forceData = forceData;
    page.panels.forEach((panel, k) => { panel.overlay = overlays[k]; panel.forces = forceData[k]; panel.rebuild(); });
    updateForceSummary();
    renderMeasurements();
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
    sliceCount.textContent = scene ? `${scene.visibleAtoms} of ${scene.totalAtoms} atoms shown` : "";
    controls.querySelectorAll(".radius-input").forEach((input) => { input.placeholder = autoRadius(input.dataset.symbol).toFixed(2); });
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
  const appearanceBody = () => [
    slider("polyAlpha", "Polyhedra opacity"),
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.polyEdges, onchange: (event) => {
      viewerPrefs.appearance.polyEdges = event.target.checked; savePrefs(); rebuildAll();
    } }), "Polyhedron edges"),
    slider("planeAlpha", "Plane opacity"),
    slider("bondRadius", "Bond radius", { min: 0.02, max: 0.4, step: 0.01, format: (value) => `${value.toFixed(2)} Å` }),
    el("div", { class: "muted radii-title" }, "Colour and sphere radius (Å, blank = automatic)"),
    el("table", { class: "stats cutoffs radii" }, el("tbody", {}, species.map((sym) => el("tr", {},
      el("td", {}, elementSwatch(sym), ` ${sym}`),
      el("td", { class: "element-colour" }, el("input", { type: "color", value: elementColor(sym), "aria-label": `${sym} colour`,
        oninput: (event) => {
          if (event.target.value === defaultElementColor(sym)) delete viewerPrefs.appearance.colours[sym];
          else viewerPrefs.appearance.colours[sym] = event.target.value;
          savePrefs(); elementColoursChanged();
        } }),
        el("button", { type: "button", class: "small reset-colour", title: `Default colour for ${sym}`, "aria-label": `Default colour for ${sym}`,
          onclick: (event) => {
            delete viewerPrefs.appearance.colours[sym]; savePrefs();
            event.currentTarget.previousSibling.value = defaultElementColor(sym);
            elementColoursChanged();
          } }, "↺")),
      el("td", {}, el("input", { type: "number", step: 0.05, min: 0.05, class: "num-input radius-input", "data-symbol": sym,
        value: viewerPrefs.appearance.radii[sym] ?? "", placeholder: autoRadius(sym).toFixed(2), "aria-label": `${sym} radius`,
        onchange: (event) => {
          const value = Number(event.target.value);
          if (event.target.value.trim() === "" || !(value > 0)) { delete viewerPrefs.appearance.radii[sym]; event.target.value = ""; }
          else viewerPrefs.appearance.radii[sym] = value;
          savePrefs(); rebuildAll();
        } })))))),
    el("button", { type: "button", class: "small", onclick: () => {
      viewerPrefs.appearance = freshAppearance(); savePrefs();
      appearanceControls.replaceChildren(appearanceControls.firstChild, ...appearanceBody());
      rebuildAll();
      elementColoursChanged();
    } }, "Reset appearance"),
  ];
  const appearanceControls = el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Appearance"), ...appearanceBody());

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
          el("i", { class: "swatch", style: `background:${PLANE_COLOURS[index % PLANE_COLOURS.length]}` }),
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
      return el("div", { class: "measure-row" },
        el("i", { class: "swatch", style: `background:${group.colour}` }),
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
    sharedView.R = presetRotation(structure.cell, name);
    page.panels[0].fit();
    viewChanged();
  };
  const repeatInput = (axis) => el("input", { type: "number", min: 1, max: 6, value: viewerPrefs.repeat[axis], class: "num-input",
    disabled: !structure.pbc[axis],
    onchange: (event) => {
      viewerPrefs.repeat[axis] = Math.max(1, Math.min(6, Number(event.target.value) || 1));
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
    [["element", "Element"], ["height", "Height"], ["force", "Force magnitude"], ["error", "Per-atom force difference"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.colour === value }, label)));
  // Palette of the current value colouring; each mode remembers its own.
  const paletteSelect = el("select", { "aria-label": "Colour palette" });
  const paletteField = el("label", { class: "palette-field" }, el("span", { class: "muted" }, "Palette"), paletteSelect);
  const fillPaletteSelect = () => {
    const mode = viewerPrefs.colour;
    paletteField.hidden = !(mode in DEFAULT_PALETTES);
    paletteSelect.replaceChildren(...Object.entries(PALETTES).map(([value, palette]) =>
      el("option", { value, selected: (viewerPrefs.palettes[mode] ?? DEFAULT_PALETTES[mode]) === value }, palette.label)));
  };
  fillPaletteSelect();
  paletteSelect.addEventListener("change", () => {
    viewerPrefs.palettes[viewerPrefs.colour] = paletteSelect.value; savePrefs();
    updateOverlays();
  });
  colourSelect.addEventListener("change", () => {
    viewerPrefs.colour = colourSelect.value; savePrefs();
    errorControls.hidden = viewerPrefs.colour !== "error";
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

  const compareSelect = el("select", { "aria-label": "Compare with" }, el("option", { value: "" }, "No comparison"));
  compareSelect.addEventListener("change", () => { location.hash = hash(structure.id, { compare: compareSelect.value || null }); });

  controls.append(
    el("h3", {}, "View"),
    el("div", { class: "button-row" },
      el("button", { type: "button", class: "small", onclick: preset("top") }, "Top"),
      el("button", { type: "button", class: "small", onclick: preset("side-a") }, "Along a"),
      el("button", { type: "button", class: "small", onclick: preset("side-b") }, "Along b"),
      el("button", { type: "button", class: "small", onclick: () => { page.panels[0].fit(); viewChanged(); } }, "Fit"),
      el("button", { type: "button", class: "small",
        title: state.file ? "Save this frame, copied verbatim from the file" : "Save this structure as extxyz, with the evaluation chosen under Forces",
        onclick: async (event) => {
          const button = event.currentTarget;
          const evaluation = state.file ? null : page.force.evaluation?.id;
          button.disabled = true;
          try {
            await downloadExport(`api/structures/${encodeURIComponent(structure.id)}/extxyz${evaluation ? `?evaluation=${encodeURIComponent(evaluation)}` : ""}`);
          } catch (error) {
            window.alert(`Export failed: ${error.message}`);
          } finally {
            button.disabled = false;
          }
        } }, "Save extxyz"),
      el("button", { type: "button", class: "small", title: "Save the structure panel as shown, as an SVG image", onclick: () => {
        const shown = page.panels.filter((p) => p.scene);
        if (shown.length) {
          downloadText(`${structure.formula}-${structure.id}.svg`,
            panelsToSvg(shown, { transparent: viewerPrefs.svgTransparent }), "image/svg+xml");
        }
      } }, "Save SVG")),
    checkbox("Transparent SVG background", "svgTransparent"),
    el("p", { class: "muted hint" }, "Drag to rotate, right-drag (or shift-drag) to pan, scroll to zoom; drag the bottom-right corner to resize."),
    el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Repeat"), repeatInput(0), "×", repeatInput(1)),
    el("h3", {}, "Display"),
    checkbox("Cell", "cell", rebuildAll),
    checkbox("Bonds", "bonds", rebuildAll),
    checkbox("Polyhedra", "polyhedra", rebuildAll),
    el("details", {}, el("summary", { class: "muted" }, "Polyhedron centres"), centreBoxes),
    appearanceControls,
    el("details", {}, el("summary", { class: "muted" }, "Bond cutoffs"), el("table", { class: "stats cutoffs" }, el("tbody", {}, cutoffRows)),
      el("button", { type: "button", class: "small", onclick: () => {
        for (const [a, b] of pairs) viewerPrefs.cutoffs[pairKey(a, b)] = defaultCutoff(a, b);
        savePrefs(); renderStructurePage(structureId, params);
      } }, "Reset cutoffs")),
    el("h3", {}, "Slice"),
    elementBoxes,
    sliceTable,
    el("div", { class: "inline-fields" }, sliceCount,
      el("button", { type: "button", class: "small", onclick: () => {
        resetFilter("slice", "hiddenElements", sliceTable, elementBoxes);
        sliceChanged();
      } }, "Show all")),
    el("h3", {}, "Measure"),
    measureControls,
    el("h3", {}, "Atom colours"),
    paintControls,
    el("h3", {}, "Planes"),
    planeList,
    el("button", { type: "button", class: "small", onclick: () => {
      viewerPrefs.planes.push({ h: 0, k: 0, l: 1, t: 0.5, show: true }); savePrefs(); renderPlanes(); rebuildAll();
    } }, "Add plane"),
    el("h3", {}, "Forces"),
    forceControls,
    el("h3", {}, "Colour"),
    colourSelect,
    paletteField,
    errorControls,
    el("h3", {}, "Compare"),
    compareSelect,
    el("div", { class: "settings-file" },
      el("button", { type: "button", class: "small", title: "Save all viewer settings to a file", onclick: () => {
        downloadText("stoms-viewer-settings.json", `${JSON.stringify({ stoms_viewer_settings: 1, settings: viewerPrefs }, null, 2)}\n`, "application/json");
      } }, "Export settings"),
      el("button", { type: "button", class: "small", title: "Load viewer settings from a file", onclick: () => settingsInput.click() }, "Import settings"),
      settingsInput),
    el("div", { class: "reset-all" }, el("button", { type: "button", class: "small", onclick: () => {
      if (!window.confirm("Reset all viewer settings to their defaults? This also removes your planes and custom cutoffs.")) return;
      for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
      Object.assign(viewerPrefs, defaultPrefs());
      savePrefs();
      Object.assign(sharedView, { R: null, scale: null, pan: [0, 0], panelCount: 0 });
      renderStructurePage(structureId, params);
    } }, "Reset all viewer settings")));

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
    if (page.structures[0] !== structure) {
      page.structures[0] = structure;
      page.panels[0].structure = structure;
      heading.replaceChildren(structure.formula, el("span", { class: "muted" }, ` · ${structure.positions.length} atoms`));
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
    const list = selection ? related.structures.filter((r) => selection.has(r.ordinal)) : related.structures;
    const source = bySelection ? `${related.aggregation.name}, selected` : byAggregation ? related.aggregation.name : related.tags.join(", ");
    const label = (r) => [byAggregation ? `#${r.ordinal}` : null, r.iteration ? `it ${r.iteration}` : null,
      ...r.distinct_tags.map((t) => t.split(":").pop())].filter(Boolean).join(" · ") || r.id;
    // Within a tag prefix, compare within one iteration (founder / winner /
    // relaxed winner); the same run index in another iteration is an unrelated structure.
    const iteration = byAggregation ? null : iterationOf(structure.tags);
    compareSelect.replaceChildren(el("option", { value: "" }, "No comparison"),
      ...list.filter((r) => r.id !== structure.id && (!iteration || r.iteration === iteration)).map((r) => el("option", { value: r.id, selected: r.id === params.get("compare") }, `${source}: ${label(r)}`)));
    if (!list.length) {
      relatedSection.append(el("p", { class: "muted" }, bySelection
        ? `No members of ${fromAgg.name} are selected.` : `No tag with prefix "${viewerPrefs.prefix}" on this structure.`));
      return;
    }
    // Outside the list (e.g. not a member of the aggregation), ← / → enter it from the end / start.
    const position = list.findIndex((r) => r.id === structure.id);
    const step = (delta) => {
      const from = page.movie ? page.movie.index : position;
      const next = list[from < 0 ? (delta > 0 ? 0 : list.length - 1) : from + delta];
      if (next) location.hash = hash(next.id);
    };
    let picker;
    if (list.length <= MAX_RELATED_CHIPS) {
      picker = el("div", { class: "chips related-chips" }, list.map((r) => el("a", {
        class: "chip", href: hash(r.id), "aria-pressed": String(r.id === structure.id), title: r.id,
      }, label(r))));
    } else {
      const input = el("input", { type: "number", min: 1, max: list.length, step: 1, value: position >= 0 ? position + 1 : "",
        class: "num-input", "aria-label": "Position" });
      input.addEventListener("change", () => { const next = list[Number(input.value) - 1]; if (next) location.hash = hash(next.id); });
      picker = el("span", { class: "inline-fields" }, input, el("span", { class: "muted" },
        `of ${list.length}${position >= 0 ? ` · ${label(list[position])}` : ""}`));
    }
    relatedSection.append(el("div", { class: "related-strip" },
      el("button", { type: "button", class: "small", disabled: position === 0, onclick: () => step(-1) }, "← Previous"),
      picker,
      el("button", { type: "button", class: "small", disabled: position === list.length - 1, onclick: () => step(1) }, "Next →")));
    hint.textContent = `${source} · ${list.length} structures · ${position < 0
      ? "this structure is not among them; " : ""}←/→ keys step through them, space plays them`;

    // --- movie: play a range of the listed structures as frames inside this
    // page. The view and all settings stay; colour scales span the range's
    // frames (scaleMax). Ranges are kept per step list while browsing.
    const rangeKey = `${byAggregation ? cycle : related.tags.join(",")}|${list.length}`;
    let [first, last] = movieRanges.get(rangeKey) ?? [0, Math.min(MOVIE_FRAMES, list.length) - 1];
    const startAt = () => (position >= first && position <= last ? position : first);
    const playButton = el("button", { type: "button", class: "small play-button" }, "▶ Play");
    const frameSlider = el("input", { type: "range", min: first, max: last, step: 1, value: startAt(),
      class: "frame-slider", "aria-label": "Frame" });
    const frameLabel = el("span", { class: "muted frame-label" });
    const showLabel = (i) => { frameLabel.textContent = `${i + 1} / ${list.length} · ${label(list[i])}`; };
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
        page.movie = { frames: lastMovie.frames, first, last, index: startAt(), scales: lastMovie.scales };
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
      page.movie ??= { frames: results.map((r) => r.value), first, last, index: startAt(), scales: new Map() };
      lastMovie = { key: movieKey, frames: page.movie.frames, scales: page.movie.scales };
      return true;
    }
    async function showFrame(i) {
      const frame = frameAt(i);
      page.movie.index = i;
      page.structures[0] = frame;
      page.panels[0].structure = frame;
      frameSlider.value = i;
      showLabel(i);
      heading.replaceChildren(frame.formula, el("span", { class: "muted" }, ` · ${frame.positions.length} atoms · frame ${i + 1} of ${list.length}`));
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
      if (open && id && id !== structure.id) location.hash = hash(id);
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
      if (id !== structure.id) location.hash = hash(id);
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
    if (event.key === "Escape" && page.cancelMeasure?.()) return;
    page.onKey?.(event);
  };
  window.addEventListener("keydown", keyHandler);

  page.dispose = () => {
    page.disposed = true;
    for (const type of readerScrolls) window.removeEventListener(type, stopRestoring);
    settingsFit.disconnect();
    wide.removeEventListener("change", fitSettings);
    page.stopMovie?.();
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
