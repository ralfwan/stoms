"use strict";

// Structure viewer page (#/structures/<id>?from=<aggregation>&compare=<id>).
//
// One scene model (repeated cell, periodic bonds, coordination polyhedra,
// per-atom colours) feeds a dependency-free 2D canvas renderer; panels share
// one view state.
// Uses el, api, setMain, idCell, formatNumber and state from app.js.

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

const elementColor = (symbol) => (ELEMENTS[symbol] ?? ["#ff1493", 1.5])[0];
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

// Sequential single-hue ramps, light (low) to dark (high).
const RAMPS = {
  height: ["#dceafb", "#6c9fdf", "#123f7a"],
  error: ["#fde8d8", "#ee8a4c", "#8c2a06"],
};
function ramp(name, t) {
  const stops = RAMPS[name];
  const x = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  return mix(stops[i], stops[i + 1], x - i);
}

// ---------------------------------------------------------------- preferences & shared view

const DEFAULT_APPEARANCE = { polyAlpha: 0.45, polyEdges: true, planeAlpha: 0.2, radii: {} };

function defaultPrefs() {
  return { cell: true, bonds: false, polyhedra: false, colour: "element",
    repeat: [1, 1], cutoffs: {}, polyCenters: null, prefix: "run:",
    slice: [[null, null], [null, null], [null, null]], hiddenElements: [], planes: [],
    appearance: { ...DEFAULT_APPEARANCE, radii: {} } };
}

const viewerPrefs = (() => {
  const defaults = defaultPrefs();
  let prefs = defaults;
  try { prefs = { ...defaults, ...JSON.parse(localStorage.getItem("stoms.viewer") || "{}") }; } catch { /* storage unavailable */ }
  prefs.appearance = { ...DEFAULT_APPEARANCE, ...prefs.appearance };
  prefs.appearance.radii = { ...prefs.appearance.radii };
  return prefs;
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

function inSlice(f) {
  return viewerPrefs.slice.every(([lo, hi], k) => (lo === null || f[k] >= lo - 1e-9) && (hi === null || f[k] <= hi + 1e-9));
}

// Sphere radius (Angstrom): per-element override, else scaled covalent radius.
function autoRadius(symbol) {
  const ballAndStick = viewerPrefs.bonds || viewerPrefs.polyhedra;
  return Math.max(0.18, covalentRadius(symbol) * (ballAndStick ? 0.33 : 0.5));
}
const atomRadius = (symbol) => viewerPrefs.appearance.radii[symbol] ?? autoRadius(symbol);

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

// Everything a renderer draws, in Angstrom world coordinates.
function buildScene(structure, overlay) {
  const prefs = viewerPrefs;
  const [A, B] = structure.cell;
  const na = structure.pbc[0] ? prefs.repeat[0] : 1, nb = structure.pbc[1] ? prefs.repeat[1] : 1;
  const ballAndStick = prefs.bonds || prefs.polyhedra;
  const colours = structure.symbols.map((symbol, i) => overlay.colour(i, symbol));
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
  return { atoms, halfBonds, polyhedra, cellEdges, planes, centre, bondRadius: 0.11, structure, overlay,
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
  gradient.addColorStop(0, mix(colour, "#ffffff", 0.6));
  gradient.addColorStop(0.5, colour);
  gradient.addColorStop(1, mix(colour, "#000000", 0.45));
  ctx.fillStyle = gradient;
  ctx.beginPath(); ctx.arc(c, c, r, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = 1; ctx.stroke();
  if (spriteCache.size > 600) spriteCache.clear();
  spriteCache.set(key, sprite);
  return sprite;
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
      const project = projector(scene, width, height);
      const s = sharedView.scale;
      const cellColour = getComputedStyle(host).getPropertyValue("--tick").trim() || "#888";
      const items = [];
      for (const atom of scene.atoms) {
        const [x, y, z] = project(atom.position);
        items.push({ z, p: atom.position, draw: () => { const sprite = sphereSprite(atom.colour, atom.radius * s); ctx.drawImage(sprite, x - sprite.width / 2, y - sprite.height / 2); } });
      }
      for (const bond of scene.halfBonds) {
        const a = project(bond.from), b = project(bond.to);
        items.push({ z: Math.min(a[2], b[2]) - 0.05, p: mul(add(bond.from, bond.to), 0.5), draw: () => {
          ctx.strokeStyle = mix(bond.colour, "#000000", 0.2); ctx.lineWidth = Math.max(1, 2 * scene.bondRadius * s); ctx.lineCap = "butt";
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        } });
      }
      const R = sharedView.R;
      for (const poly of scene.polyhedra) for (const face of poly.faces) {
        const pts = face.points.map(project);
        const facing = dot(R[2], face.normal);
        items.push({ z: pts.reduce((m, p) => m + p[2], 0) / pts.length, p: mul(face.points.reduce(add, [0, 0, 0]), 1 / face.points.length), draw: () => {
          ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath();
          const look = scene.appearance;
          if (look.polyAlpha > 0) {
            ctx.globalAlpha = look.polyAlpha; ctx.fillStyle = mix(poly.colour, facing > 0 ? "#ffffff" : "#000000", Math.abs(facing) * 0.35); ctx.fill();
          }
          if (look.polyEdges) { ctx.globalAlpha = 0.7; ctx.strokeStyle = mix(poly.colour, "#000000", 0.5); ctx.lineWidth = 1; ctx.stroke(); }
          ctx.globalAlpha = 1;
        } });
      }
      items.sort((p, q) => p.z - q.z);
      ctx.strokeStyle = cellColour; ctx.lineWidth = 1;
      for (const [a, b] of scene.cellEdges) {
        const p = project(a), q = project(b);
        ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
      }
      // Planes are drawn whole; each item goes before or after a plane depending
      // on which side of it the item lies as seen from the viewer.
      const planes = scene.planes.map((pl) => {
        const pts = pl.polygon.points.map(project);
        return { ...pl, pts, depth: pts.reduce((m, q) => m + q[2], 0) / pts.length, facing: Math.sign(dot(pl.polygon.normal, R[2])) || 1 };
      }).sort((a, b) => a.depth - b.depth);
      const layers = planes.map(() => []).concat([[]]);
      for (const item of items) {
        const front = planes.reduce((n, pl) => n + (Math.sign(dot(pl.polygon.normal, sub(item.p, pl.polygon.centre))) === pl.facing ? 1 : 0), 0);
        layers[front].push(item);
      }
      layers.forEach((layer, k) => {
        for (const item of layer) item.draw();
        const pl = planes[k];
        if (!pl) return;
        ctx.beginPath(); pl.pts.forEach((q, i) => (i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]))); ctx.closePath();
        ctx.globalAlpha = scene.appearance.planeAlpha; ctx.fillStyle = pl.colour; ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = pl.colour; ctx.lineWidth = 2; ctx.stroke();
      });
    },
    dispose() { canvas.remove(); },
  };
}

// ---------------------------------------------------------------- viewer panel

// One panel: a structure, its overlay data, a renderer, and pointer interaction.
function createPanel(host) {
  const panel = { structure: null, overlay: null, scene: null, renderer: null };
  const stage = el("div", { class: "viewer-stage" });
  const tooltip = el("div", { class: "tooltip" });
  host.append(stage, tooltip);
  panel.renderer = createCanvasRenderer(stage);
  panel.rebuild = () => {
    if (!panel.structure || !panel.overlay) return;
    panel.scene = buildScene(panel.structure, panel.overlay);
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

  // Pointer: drag rotates, shift-drag pans, wheel zooms, hover inspects atoms.
  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    drag = { x: event.clientX, y: event.clientY, pan: event.shiftKey };
    stage.setPointerCapture(event.pointerId);
  });
  stage.addEventListener("pointermove", (event) => {
    if (drag) {
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      drag.x = event.clientX; drag.y = event.clientY;
      if (drag.pan) sharedView.pan = [sharedView.pan[0] + dx, sharedView.pan[1] + dy];
      else { rotateScreen("y", dx * 0.01); rotateScreen("x", dy * 0.01); }
      tooltip.style.display = "none";
      viewChanged();
      return;
    }
    hover(event);
  });
  stage.addEventListener("pointerup", () => { drag = null; });
  stage.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });
  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    sharedView.scale *= Math.exp(-event.deltaY * 0.0015);
    viewChanged();
  }, { passive: false });

  function hover(event) {
    if (!panel.scene) return;
    const box = stage.getBoundingClientRect();
    const mx = event.clientX - box.left, my = event.clientY - box.top;
    const project = projector(panel.scene, box.width, box.height);
    let best = null;
    for (const atom of panel.scene.atoms) {
      const [x, y, z] = project(atom.position);
      const r = atom.radius * sharedView.scale;
      if ((x - mx) ** 2 + (y - my) ** 2 <= r * r && (!best || z > best.z)) best = { atom, z };
    }
    if (!best) { tooltip.style.display = "none"; return; }
    const lines = panel.overlay.describe(best.atom.index);
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

// ---------------------------------------------------------------- page

let currentPage = null;

async function renderStructurePage(structureId, params) {
  currentPage?.dispose();
  currentPage = null;
  setMain(el("p", { class: "muted" }, "Loading…"));
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
  const page = { panels: [], structures: [structure], pair: defaultPair(structure), vector: "forces", disposed: false };
  currentPage = page;

  const hash = (id, extra = {}) => {
    const query = new URLSearchParams();
    if (fromId) query.set("from", fromId);
    const compare = "compare" in extra ? extra.compare : params.get("compare");
    if (compare) query.set("compare", compare);
    const text = query.toString();
    return `#/structures/${encodeURIComponent(id)}${text ? `?${text}` : ""}`;
  };

  // --- layout
  const stages = el("div", { class: "viewer-panels" });
  const legend = el("div", { class: "viewer-legend" });
  const status = el("p", { class: "muted viewer-status" });
  const controls = el("aside", { class: "viewer-controls" });
  const relatedSection = el("section");
  const evaluationsSection = el("section");

  setMain(
    fromAgg ? el("p", {}, el("a", { href: `#/aggregations/${encodeURIComponent(fromAgg.id)}` }, `← ${fromAgg.name}`)) : null,
    el("h1", {}, structure.formula, el("span", { class: "muted" }, ` · ${structure.positions.length} atoms`)),
    el("dl", { class: "facts" },
      el("dt", {}, "Structure"), el("dd", {}, idCell(structure.id)),
      el("dt", {}, "Source"), el("dd", {}, structure.source || "-"),
      el("dt", {}, "Tags"), el("dd", {}, structure.tags.length ? structure.tags.join(", ") : "-")),
    el("div", { class: "viewer-layout" }, el("div", {}, stages, legend, status), controls),
    relatedSection,
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

  const redrawAll = () => page.panels.forEach((p) => p.draw());
  sharedView.listeners.clear();
  sharedView.listeners.add(redrawAll);

  // --- overlays (shared colour scale across panels)
  async function updateOverlays() {
    const mode = viewerPrefs.colour;
    const overlays = [];
    if (mode === "height") {
      const hs = page.structures.map(heights);
      const lo = Math.min(...hs.flat()), hi = Math.max(...hs.flat());
      page.structures.forEach((s, k) => overlays.push({
        colour: (i) => ramp("height", (hs[k][i] - lo) / (hi - lo || 1)),
        describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[k][i].toFixed(2)} Å`, "height"]],
      }));
      legend.replaceChildren(rampLegend("height", `${lo.toFixed(1)} Å`, `${hi.toFixed(1)} Å`, "Height along surface normal"));
    } else if (mode === "error") {
      const [aId, bId] = page.pair;
      const a = page.structures[0].evaluations.find((e) => e.id === aId);
      const b = page.structures[0].evaluations.find((e) => e.id === bId);
      if (!a || !b) {
        legend.replaceChildren(el("span", { class: "muted" }, "Pick two evaluations with per-atom vectors."));
        page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      } else {
        // Match the chosen methods by spec hash in compared structures.
        const pairs = page.structures.map((s, k) => (k === 0 ? [a, b] : [
          s.evaluations.find((e) => e.spec_hash === a.spec_hash && e.vectors.some((v) => v.name === page.vector)),
          s.evaluations.find((e) => e.spec_hash === b.spec_hash && e.vectors.some((v) => v.name === page.vector)),
        ]));
        status.textContent = "Loading per-atom vectors…";
        const diffs = await Promise.all(pairs.map(async ([x, y]) => {
          if (!x || !y) return null;
          const [vx, vy] = await Promise.all([loadVector(x.id, page.vector), loadVector(y.id, page.vector)]);
          return { unit: vx.unit, values: vx.values.map((f, i) => norm(sub(f, vy.values[i]))) };
        }));
        if (page.disposed) return;
        status.textContent = diffs.some((d) => !d) ? "The compared structure has no evaluations with the same method specs; it is shown in element colours." : "";
        const max = Math.max(1e-9, ...diffs.filter(Boolean).flatMap((d) => d.values));
        const unitLabel = diffs.find(Boolean)?.unit ?? "";
        page.structures.forEach((s, k) => overlays.push(diffs[k] ? {
          colour: (i) => ramp("error", diffs[k].values[i] / max),
          describe: (i) => [[s.symbols[i], `atom ${i}`], [`${formatNumber(diffs[k].values[i])} ${unitLabel}`, `|Δ${page.vector}|`]],
        } : elementOverlay(s)));
        legend.replaceChildren(rampLegend("error", "0", `${formatNumber(max)} ${unitLabel}`, `|${page.vector}(${a.method}) − ${page.vector}(${b.method})| per atom`));
      }
    } else {
      page.structures.forEach((s) => overlays.push(elementOverlay(s)));
      legend.replaceChildren(el("div", { class: "legend" }, species.map((sym) =>
        el("span", {}, el("i", { class: "swatch", style: `background:${elementColor(sym)}` }), sym))));
    }
    page.panels.forEach((panel, k) => { panel.overlay = overlays[k]; panel.rebuild(); });
  }

  function elementOverlay(s) {
    const hs = heights(s);
    return {
      colour: (i, symbol) => elementColor(symbol),
      describe: (i) => [[s.symbols[i], `atom ${i}`], [`${hs[i].toFixed(2)} Å`, "height"]],
    };
  }

  function rampLegend(name, lo, hi, title) {
    const stops = RAMPS[name].join(", ");
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

  // Slice: keep atoms whose fractional coordinates lie in [min, max]; blank = no limit.
  const boundInput = (axis, side) => el("input", { type: "number", step: 0.05, class: "num-input",
    placeholder: side ? "max" : "min", value: viewerPrefs.slice[axis][side] ?? "",
    "aria-label": `${"abc"[axis]} ${side ? "maximum" : "minimum"}`,
    onchange: (event) => {
      const value = event.target.value.trim();
      viewerPrefs.slice[axis][side] = value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
      savePrefs(); rebuildAll();
    } });
  const sliceTable = el("table", { class: "stats cutoffs" },
    el("thead", {}, el("tr", {}, el("th", {}, "frac."), el("th", {}, "min"), el("th", {}, "max"))),
    el("tbody", {}, [0, 1, 2].map((axis) => el("tr", {}, el("td", {}, "abc"[axis]),
      el("td", {}, boundInput(axis, 0)), el("td", {}, boundInput(axis, 1))))));

  // Appearance: opacities and edges, collapsed by default.
  let appearanceFrame = 0;
  const scheduleRebuild = () => {
    cancelAnimationFrame(appearanceFrame);
    appearanceFrame = requestAnimationFrame(rebuildAll);
  };
  const slider = (key, label) => {
    const output = el("output", { class: "muted" });
    const input = el("input", { type: "range", min: 0, max: 1, step: 0.05, value: viewerPrefs.appearance[key], "aria-label": label });
    const show = () => { output.textContent = `${Math.round(Number(input.value) * 100)}%`; };
    input.addEventListener("input", () => {
      viewerPrefs.appearance[key] = Number(input.value); show(); savePrefs(); scheduleRebuild();
    });
    show();
    return el("label", { class: "slider-field" }, el("span", {}, label), input, output);
  };
  const appearanceBody = () => [
    slider("polyAlpha", "Polyhedra opacity"),
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.polyEdges, onchange: (event) => {
      viewerPrefs.appearance.polyEdges = event.target.checked; savePrefs(); rebuildAll();
    } }), "Polyhedron edges"),
    slider("planeAlpha", "Plane opacity"),
    el("div", { class: "muted radii-title" }, "Sphere radius (Å, blank = automatic)"),
    el("table", { class: "stats cutoffs radii" }, el("tbody", {}, species.map((sym) => el("tr", {},
      el("td", {}, el("i", { class: "swatch", style: `background:${elementColor(sym)}` }), ` ${sym}`),
      el("td", {}, el("input", { type: "number", step: 0.05, min: 0.05, class: "num-input radius-input", "data-symbol": sym,
        value: viewerPrefs.appearance.radii[sym] ?? "", placeholder: autoRadius(sym).toFixed(2), "aria-label": `${sym} radius`,
        onchange: (event) => {
          const value = Number(event.target.value);
          if (event.target.value.trim() === "" || !(value > 0)) { delete viewerPrefs.appearance.radii[sym]; event.target.value = ""; }
          else viewerPrefs.appearance.radii[sym] = value;
          savePrefs(); rebuildAll();
        } })))))),
    el("button", { type: "button", class: "small", onclick: () => {
      viewerPrefs.appearance = { ...DEFAULT_APPEARANCE, radii: {} }; savePrefs();
      appearanceControls.replaceChildren(appearanceControls.firstChild, ...appearanceBody());
      rebuildAll();
    } }, "Reset appearance"),
  ];
  const appearanceControls = el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Appearance"), ...appearanceBody());

  // Element visibility: unchecked elements are hidden (with their bonds).
  const elementBoxes = el("div", { class: "chips element-boxes" }, species.map((sym) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: !viewerPrefs.hiddenElements.includes(sym), "aria-label": `Show ${sym}`, onchange: (event) => {
      const hiddenSet = new Set(viewerPrefs.hiddenElements);
      if (event.target.checked) hiddenSet.delete(sym); else hiddenSet.add(sym);
      viewerPrefs.hiddenElements = [...hiddenSet]; savePrefs(); rebuildAll();
    } }),
    el("i", { class: "swatch", style: `background:${elementColor(sym)}` }), sym)));

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

  const vectorEvaluations = structure.evaluations.filter((e) => e.vectors.length);
  const pairSelect = (slot) => {
    const select = el("select", { "aria-label": slot ? "Evaluation B" : "Evaluation A" },
      vectorEvaluations.map((e) => el("option", { value: e.id, selected: page.pair[slot] === e.id }, evaluationLabel(e))));
    select.addEventListener("change", () => { page.pair[slot] = select.value; updateOverlays(); });
    return select;
  };
  const errorControls = el("div", { class: "error-controls", hidden: viewerPrefs.colour !== "error" },
    vectorEvaluations.length < 2
      ? el("p", { class: "muted" }, "Needs two evaluations with per-atom vectors (e.g. forces).")
      : [el("label", {}, el("span", { class: "muted" }, "Reference (A)"), pairSelect(0)),
        el("label", {}, el("span", { class: "muted" }, "Compared (B)"), pairSelect(1))]);
  const colourSelect = el("select", { "aria-label": "Colour atoms by" },
    [["element", "Element"], ["height", "Height"], ["error", "Per-atom force difference"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.colour === value }, label)));
  colourSelect.addEventListener("change", () => {
    viewerPrefs.colour = colourSelect.value; savePrefs();
    errorControls.hidden = viewerPrefs.colour !== "error";
    updateOverlays();
  });

  const compareSelect = el("select", { "aria-label": "Compare with" }, el("option", { value: "" }, "No comparison"));
  compareSelect.addEventListener("change", () => { location.hash = hash(structure.id, { compare: compareSelect.value || null }); });

  controls.append(
    el("h3", {}, "View"),
    el("div", { class: "button-row" },
      el("button", { type: "button", class: "small", onclick: preset("top") }, "Top"),
      el("button", { type: "button", class: "small", onclick: preset("side-a") }, "Along a"),
      el("button", { type: "button", class: "small", onclick: preset("side-b") }, "Along b"),
      el("button", { type: "button", class: "small", onclick: () => { page.panels[0].fit(); viewChanged(); } }, "Fit")),
    el("p", { class: "muted hint" }, "Drag to rotate, shift-drag to pan, scroll to zoom."),
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
        viewerPrefs.slice = [[null, null], [null, null], [null, null]];
        viewerPrefs.hiddenElements = []; savePrefs();
        sliceTable.querySelectorAll("input").forEach((input) => { input.value = ""; });
        elementBoxes.querySelectorAll("input").forEach((input) => { input.checked = true; });
        rebuildAll();
      } }, "Show all")),
    el("h3", {}, "Planes"),
    planeList,
    el("button", { type: "button", class: "small", onclick: () => {
      viewerPrefs.planes.push({ h: 0, k: 0, l: 1, t: 0.5, show: true }); savePrefs(); renderPlanes(); rebuildAll();
    } }, "Add plane"),
    el("h3", {}, "Colour"),
    colourSelect,
    errorControls,
    el("h3", {}, "Compare"),
    compareSelect,
    el("div", { class: "reset-all" }, el("button", { type: "button", class: "small", onclick: () => {
      if (!window.confirm("Reset all viewer settings to their defaults? This also removes your planes and custom cutoffs.")) return;
      for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
      Object.assign(viewerPrefs, defaultPrefs());
      savePrefs();
      Object.assign(sharedView, { R: null, scale: null, pan: [0, 0], panelCount: 0 });
      renderStructurePage(structureId, params);
    } }, "Reset all viewer settings")));

  // --- evaluations of this structure
  evaluationsSection.append(el("h2", {}, "Evaluations of this structure"),
    structure.evaluations.length ? el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {}, ["Method", "Family", "Spec", "Per-atom vectors", "Tags", "Created", "ID"].map((h) => el("th", {}, h)))),
      el("tbody", {}, structure.evaluations.map((e) => el("tr", {},
        el("td", {}, e.method), el("td", {}, e.family), el("td", {}, el("code", {}, e.spec_hash)),
        el("td", {}, e.vectors.map((v) => v.name).join(", ") || "-"), el("td", { class: "wrap" }, e.tags.join(", ") || "-"),
        el("td", {}, formatDate(e.created_at)), el("td", {}, idCell(e.id)))))))
      : el("p", { class: "muted" }, "No evaluations."));

  // --- related structures (shared tag prefix, e.g. one CMA-ES run)
  async function loadRelated() {
    const prefixInput = el("input", { type: "text", value: viewerPrefs.prefix, class: "prefix-input", spellcheck: "false", "aria-label": "Tag prefix" });
    prefixInput.addEventListener("change", () => { viewerPrefs.prefix = prefixInput.value; savePrefs(); loadRelated(); });
    relatedSection.replaceChildren(el("h2", {}, "Related structures"),
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Sharing a tag with prefix"), prefixInput));
    let related;
    try {
      related = await api(`structures/${encodeURIComponent(structure.id)}/related?prefix=${encodeURIComponent(viewerPrefs.prefix)}`);
    } catch (error) {
      relatedSection.append(el("p", { class: "error" }, error.message));
      return;
    }
    if (page.disposed) return;
    const list = related.structures;
    const label = (r) => [r.iteration ? `it ${r.iteration}` : null, ...r.distinct_tags.map((t) => t.split(":").pop())].filter(Boolean).join(" · ") || r.id;
    // Compare within one iteration (founder / winner / relaxed winner); the same
    // run index in another iteration is an unrelated structure.
    const iteration = iterationOf(structure.tags);
    compareSelect.replaceChildren(el("option", { value: "" }, "No comparison"),
      ...list.filter((r) => r.id !== structure.id && (!iteration || r.iteration === iteration)).map((r) => el("option", { value: r.id, selected: r.id === params.get("compare") }, `${related.tags.join(", ")}: ${label(r)}`)));
    if (!list.length) {
      relatedSection.append(el("p", { class: "muted" }, `No tag with prefix "${viewerPrefs.prefix}" on this structure.`));
      return;
    }
    const position = list.findIndex((r) => r.id === structure.id);
    const step = (delta) => { const next = list[position + delta]; if (next) location.hash = hash(next.id); };
    relatedSection.append(el("div", { class: "related-strip" },
      el("button", { type: "button", class: "small", disabled: position <= 0, onclick: () => step(-1) }, "← Previous"),
      el("div", { class: "chips" }, list.map((r) => el("a", {
        class: "chip", href: hash(r.id), "aria-pressed": String(r.id === structure.id), title: r.id,
      }, label(r)))),
      el("button", { type: "button", class: "small", disabled: position < 0 || position >= list.length - 1, onclick: () => step(1) }, "Next →")),
    el("p", { class: "muted hint" }, `${related.tags.join(", ")} · ${list.length} structures · ←/→ keys step through them`));
    page.onKey = (event) => {
      if (event.target.closest("input, select, textarea")) return;
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    };
  }
  page.onKey = null;
  const keyHandler = (event) => page.onKey?.(event);
  window.addEventListener("keydown", keyHandler);

  page.dispose = () => {
    page.disposed = true;
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
  await updateOverlays();
  rebuildAll();
  loadRelated();
}

function leaveStructurePage() {
  currentPage?.dispose();
  currentPage = null;
}
