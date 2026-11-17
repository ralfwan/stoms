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

// Van der Waals radii (Angstrom): S. Alvarez, "A cartography of the van der
// Waals territories", Dalton Trans. 42 (2013) 8617-8636,
// https://doi.org/10.1039/C3DT50599E (as in ase.data.vdw_alvarez).
const VDW_RADII = {
  H: 1.20, He: 1.43, Li: 2.12, Be: 1.98, B: 1.91, C: 1.77, N: 1.66, O: 1.50, F: 1.46, Ne: 1.58,
  Na: 2.50, Mg: 2.51, Al: 2.25, Si: 2.19, P: 1.90, S: 1.89, Cl: 1.82, Ar: 1.83, K: 2.73, Ca: 2.62,
  Sc: 2.58, Ti: 2.46, V: 2.42, Cr: 2.45, Mn: 2.45, Fe: 2.44, Co: 2.40, Ni: 2.40, Cu: 2.38, Zn: 2.39,
  Ga: 2.32, Ge: 2.29, As: 1.88, Se: 1.82, Br: 1.86, Kr: 2.25, Rb: 3.21, Sr: 2.84, Y: 2.75, Zr: 2.52,
  Nb: 2.56, Mo: 2.45, Ru: 2.46, Rh: 2.44, Pd: 2.15, Ag: 2.53, Cd: 2.49, In: 2.43, Sn: 2.42, Sb: 2.47,
  Te: 1.99, I: 2.04, Xe: 2.06, Cs: 3.48, Ba: 3.03, La: 2.98, Hf: 2.63, Ta: 2.53, W: 2.57, Re: 2.49,
  Os: 2.48, Ir: 2.41, Pt: 2.29, Au: 2.32, Hg: 2.45, Pb: 2.60, Bi: 2.54,
};
// Ionic radii (Angstrom): R. D. Shannon, "Revised effective ionic radii and
// systematic studies of interatomic distances in halides and chalcogenides",
// Acta Cryst. A32 (1976) 751-767, https://doi.org/10.1107/S0567739476001551.
// Effective ionic radii (IR, on the scale of r(O2-) = 1.40 Å), one ion per
// element: [radius, ion]. Charge: the element's usual state in oxides,
// halides and chalcogenides (anions for O, N, S, Se, Te and the halogens,
// otherwise the commonest cation, not always the highest: e.g. Mn2+, Co2+,
// Pb2+; high spin for Mn2+, Fe3+, Co2+).
// Coordination: 6 (octahedral), the one Shannon tabulates for nearly every
// ion and the commonest in oxides; N3- only exists at CN 4. H and the noble
// gases have no usable ionic radius and keep their covalent one.
const IONIC_RADII = {
  Li: [0.76, "Li+"], Be: [0.45, "Be2+"], B: [0.27, "B3+"], C: [0.16, "C4+"], N: [1.46, "N3- (CN 4)"],
  O: [1.40, "O2-"], F: [1.33, "F-"], Na: [1.02, "Na+"], Mg: [0.72, "Mg2+"], Al: [0.535, "Al3+"],
  Si: [0.40, "Si4+"], P: [0.38, "P5+"], S: [1.84, "S2-"], Cl: [1.81, "Cl-"], K: [1.38, "K+"],
  Ca: [1.00, "Ca2+"], Sc: [0.745, "Sc3+"], Ti: [0.605, "Ti4+"], V: [0.54, "V5+"], Cr: [0.615, "Cr3+"],
  Mn: [0.83, "Mn2+"], Fe: [0.645, "Fe3+"], Co: [0.745, "Co2+"], Ni: [0.69, "Ni2+"], Cu: [0.73, "Cu2+"],
  Zn: [0.74, "Zn2+"], Ga: [0.62, "Ga3+"], Ge: [0.53, "Ge4+"], As: [0.46, "As5+"], Se: [1.98, "Se2-"],
  Br: [1.96, "Br-"], Rb: [1.52, "Rb+"], Sr: [1.18, "Sr2+"], Y: [0.90, "Y3+"], Zr: [0.72, "Zr4+"],
  Nb: [0.64, "Nb5+"], Mo: [0.59, "Mo6+"], Ru: [0.62, "Ru4+"], Rh: [0.665, "Rh3+"], Pd: [0.86, "Pd2+"],
  Ag: [1.15, "Ag+"], Cd: [0.95, "Cd2+"], In: [0.80, "In3+"], Sn: [0.69, "Sn4+"], Sb: [0.60, "Sb5+"],
  Te: [2.21, "Te2-"], I: [2.20, "I-"], Cs: [1.67, "Cs+"], Ba: [1.35, "Ba2+"], La: [1.032, "La3+"],
  Hf: [0.71, "Hf4+"], Ta: [0.64, "Ta5+"], W: [0.60, "W6+"], Re: [0.63, "Re4+"], Os: [0.63, "Os4+"],
  Ir: [0.625, "Ir4+"], Pt: [0.625, "Pt4+"], Au: [0.85, "Au3+"], Hg: [1.02, "Hg2+"], Pb: [1.19, "Pb2+"],
  Bi: [1.03, "Bi3+"],
};
// Radius types: the table behind the automatic atom radii.
const RADIUS_TYPES = ["covalent", "vdw", "ionic"];
// The radius of a radius type; elements missing from the table keep their
// covalent radius.
function typedRadius(symbol, type) {
  if (type === "vdw" && VDW_RADII[symbol]) return VDW_RADII[symbol];
  if (type === "ionic" && IONIC_RADII[symbol]) return IONIC_RADII[symbol][0];
  return covalentRadius(symbol);
}
// Where an element's automatic radius comes from (radius input tooltips).
function radiusSource(symbol, type) {
  if (type === "vdw" && VDW_RADII[symbol]) return "van der Waals radius (Alvarez 2013)";
  if (type === "ionic" && IONIC_RADII[symbol]) return `ionic radius of ${IONIC_RADII[symbol][1]}, CN 6 unless noted (Shannon 1976)`;
  return `covalent radius (Cordero 2008)${type === "covalent" ? "" : `: no ${type === "vdw" ? "van der Waals" : "ionic"} radius`}`;
}
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
// background, up to depthStrength at the back. atomScale multiplies the
// automatic sphere radii in ball-and-stick (not those set per element, which
// are in Angstrom; see autoRadius).
// The cell outline: line width in pixels, colour (null = the theme's) and
// line style (CELL_DASHES).
const DEFAULT_APPEARANCE = { polyAlpha: 0.45, polyEdges: true, planeAlpha: 0.2, bondRadius: 0.08, depthCue: false, depthStrength: 0.6,
  atomScale: 1, cellWidth: 1, cellColour: null, cellDash: "solid", radii: {}, colours: {} };
// Dash patterns of the cell outline, in units of its width.
const CELL_DASHES = { solid: null, dashed: [5, 3], dotted: [1, 2] };
const MAX_CELL_WIDTH = 6;
const MAX_ATOM_SCALE = 3;
// Per-element radii and colours are objects of their own in every appearance.
const freshAppearance = () => ({ ...DEFAULT_APPEARANCE, radii: {}, colours: {} });
// Force arrows: length scale in Angstrom per force unit, shaft radius in
// Angstrom, colour (null = text colour of the theme), hidden below minMagnitude.
// `source`: "vectors" (per-atom vectors of an evaluation or the frames) or
// "displacement" (from a reference structure, see displacementOf).
const DEFAULT_ARROWS = { show: false, scale: 1, width: 0.04, colour: null, minMagnitude: 0, source: "vectors" };
const ARROW_SOURCES = ["vectors", "displacement"];
// Displacements (arrows and colours) compare each structure with a reference:
// "compared" (the other panel of the structure page), "first" (the first
// structure of the step list, or frame 0 of a notebook viewer), "previous"
// (the one before it), or "frame" (`frame`: a 0-based position in the step
// list or the frames).
const DISPLACEMENT_REFERENCES = ["compared", "first", "previous", "frame"];
const DEFAULT_DISPLACEMENT = { reference: "first", frame: 0 };
const emptySlice = () => [[null, null], [null, null], [null, null]];
// Movie playback: frames per second and whether it starts over at the end.
const DEFAULT_PLAYER = { fps: 10, loop: true };
// Axis tripod in the bottom-left corner: "abc" (cell vectors), "xyz"
// (Cartesian), "both" or "off"; `export` also draws it in saved images;
// `size` scales it (arrows, and with them a mode's q and v_g; see tripodLayout);
// `axesSize` and `waveSize` scale the axis arrows and q, v_g on top of it.
const DEFAULT_TRIPOD = { axes: "abc", export: true, size: 1, axesSize: 1, waveSize: 1 };
const TRIPOD_SIZES = { min: 0.5, max: 3 };
const TRIPOD_PART_SIZES = { min: 0.5, max: 2 };
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
// null = automatic) are its size. With waveVector the axis tripod (Cartesian
// axes only, see setTripodAxes) also shows the mode's wave vector q and its
// group velocity v_g: colours qColour and vgColour, line styles qDash and
// vgDash (keys of CELL_DASHES), their names at the tips (waveLabels) and a
// legend under the checkbox (waveLegend).
// Video frame sizes in pixels.
const VIDEO_SIZES = { "720p": [1280, 720], "1080p": [1920, 1080] };
// Set once a structure with modes has opened on the Vibrations tab.
let vibrationTabShown = false;
const DEFAULT_VIBRATION = { amplitude: 0.3, periodSeconds: 1, showArrows: false, bonds: "fixed", unit: "THz",
  recordPeriods: 2, videoSize: "shown", videoFps: "60", plotSide: false, plotWidth: null, plotHeight: null,
  waveVector: false, qColour: "#e67700", vgColour: "#9c36b5", qDash: "solid", vgDash: "dashed", waveLabels: true, waveLegend: true };

// Symmetry (spglib, computed by the ledger server or in Python): the
// distance tolerance in Å (spglib's symprec), within the range the server
// accepts.
const DEFAULT_SYMMETRY = { tolerance: 0.01 };
const MIN_SYMMETRY_TOLERANCE = 1e-5;
const MAX_SYMMETRY_TOLERANCE = 1;

// Hydrogen bonds D–H···A (see hydrogenBonds): drawn when `show`, for
// acceptors (and donors) of the `acceptors` elements, H···A from `min` to
// `max` Å and a D–H···A angle of at least `angle` degrees; dashed lines in
// `colour`. With `perAcceptor`, an acceptor element with an entry in
// `ranges` ({ O: [min, max] }) uses that H···A range instead (see
// hbondRange); `min` and `max` keep their meaning, so a stoms without
// per-acceptor ranges reads such settings with the single range.
const DEFAULT_HBONDS = { show: false, acceptors: ["O", "N", "F"], min: 1.5, max: 2.5, angle: 120, colour: "#2f7fd0",
  perAcceptor: false, ranges: {} };
const freshHbonds = () => ({ ...DEFAULT_HBONDS, acceptors: [...DEFAULT_HBONDS.acceptors], ranges: {} });
// The H···A range [min, max] of acceptor element `symbol` in effect under
// the hbonds settings `hb`.
const hbondRange = (hb, symbol) => (hb.perAcceptor && Object.hasOwn(hb.ranges, symbol) ? hb.ranges[symbol] : [hb.min, hb.max]);
// Atoms bonded to shown ones but outside the repeat or the slice: "hide",
// "partners" (drawn, with their bonds; one step) or "ligands" (only the
// ligands of shown polyhedra).
const BONDED_OUTSIDE = ["hide", "partners", "ligands"];

// Drawing styles (viewerPrefs.style):
//   "ball-and-stick": spheres at a third of the radius type with bonds or
//     polyhedra, at half without (the look before styles existed);
//   "space-filling": spheres at the full radius, no bonds or polyhedra;
//   "stick": bonds as cylinders, atoms as spheres of the bond radius;
//   "wireframe": bonds as thin lines, atoms without bonds as small dots.
// Stick and wireframe always draw bonds (the Bonds setting is kept for the
// other styles). Per-element radii (appearance.radii) win in every style but
// space-filling: such atoms are spheres of that radius, also in stick and
// wireframe. Space-filling always draws the radius type's table radii.
const STYLES = ["ball-and-stick", "space-filling", "stick", "wireframe"];
// Width in pixels of wireframe lines (on screen one device pixel: see
// paintCanvas) and smallest radius of its dots.
const WIRE_WIDTH = 1;
const DOT_RADIUS = 2;
function defaultPrefs() {
  return { version: PREFS_VERSION, cell: true, bonds: false, polyhedra: false, colour: "element",
    // Draw the centre atoms of drawn polyhedra (see buildScene).
    polyhedraCentres: true,
    // Drawing style (STYLES) and the radius type of automatic radii (RADIUS_TYPES).
    style: "ball-and-stick", radiusType: "covalent",
    // Draw every atom inside the cell (see positionsOf).
    wrap: false,
    repeat: [1, 1, 1], cutoffs: {}, polyCenters: null, prefix: "run:",
    // Transformation matrix of the shown cell instead of the repeat (see
    // checkRepeatMatrix; null: the repeat), and whether the stored cell's
    // outline is drawn beside the new one.
    repeatMatrix: null, storedCellOutline: false,
    // Draw the stored cell's outline at every copy of the repeat (see
    // copyOutlines).
    repeatCellOutline: false,
    // Only the stored cell and its atoms, nothing from periodic images (see
    // SINGLE_CELL_LOCK): overrides the settings above without changing them.
    singleCell: false,
    // Shortest bond per element pair (Å; missing: 0), beside the cutoffs
    // (the longest), and the bond search options above.
    bondMinimums: {}, hbonds: freshHbonds(), bondedOutside: "hide",
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
    displacement: { ...DEFAULT_DISPLACEMENT },
    symmetry: { ...DEFAULT_SYMMETRY },
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

// Repeat by a transformation matrix (viewerPrefs.repeatMatrix; null: the
// diagonal repeat a × b × c). Its rows are the shown cell's vectors in units
// of the stored a, b and c, such as [[2, 1, 0], [-1, 1, 0], [0, 0, 1]] for
// (√3×√3)R30° of a hexagonal a-b lattice. Whole numbers of at most
// MAX_REPEAT in size, the determinant (the number of cell copies) from 1 to
// MAX_REPEAT³ as for the largest repeat. Display only: the Info tab, saved
// structures and downloads keep the stored cell. Slice bounds and Miller
// planes keep referring to the stored cell (see shownCell).
const MAX_REPEAT_COPIES = MAX_REPEAT ** 3;
const det3 = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
  - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
// Why `matrix` is no transformation matrix, or null when it is one.
function repeatMatrixProblem(matrix) {
  if (!(Array.isArray(matrix) && matrix.length === 3 && matrix.every((row) => Array.isArray(row) && row.length === 3))) {
    return "The matrix has 3 rows of 3 numbers.";
  }
  if (!matrix.flat().every(Number.isInteger)) return "The matrix entries are whole numbers.";
  if (!matrix.flat().every((v) => Math.abs(v) <= MAX_REPEAT)) return `The matrix entries are from −${MAX_REPEAT} to ${MAX_REPEAT}.`;
  const d = det3(matrix);
  if (d < 1) return d === 0 ? "The rows are not independent (determinant 0)." : `The determinant is ${d}: the new cell is left-handed. Swap two rows.`;
  if (d > MAX_REPEAT_COPIES) return `The determinant is ${d}: at most ${MAX_REPEAT_COPIES} cell copies.`;
  return null;
}
const checkRepeatMatrix = (matrix) => (repeatMatrixProblem(matrix) ? null : matrix.map((row) => row.map((v) => v + 0)));
const identityMatrix = () => [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
const diagonalMatrix = (counts) => [0, 1, 2].map((i) => [0, 1, 2].map((j) => (i === j ? counts[i] : 0)));
// Presets for surface cells (a and b in the surface): [label, matrix, title].
// (√3×√3)R30° depends on the angle between a and b (60° or 120°).
function repeatPresets(structure) {
  const [a, b] = structure.cell;
  const gamma = norm(a) && norm(b) ? (Math.acos(Math.max(-1, Math.min(1, dot(a, b) / (norm(a) * norm(b))))) * 180) / Math.PI : 120;
  const sixty = Math.abs(gamma - 60) < 5;
  return [
    ["(√3×√3)R30°", sixty ? [[1, 1, 0], [-1, 2, 0], [0, 0, 1]] : [[2, 1, 0], [-1, 1, 0], [0, 0, 1]],
      `For a hexagonal a-b lattice (here γ = ${gamma.toFixed(1)}°; the rows suit γ = ${sixty ? 60 : 120}°)`],
    ["c(2×2), primitive", [[1, 1, 0], [-1, 1, 0], [0, 0, 1]], "The primitive cell of c(2×2): (√2×√2)R45° on a square lattice"],
    ["p(2×1)", [[2, 0, 0], [0, 1, 0], [0, 0, 1]], "Twice a, once b"],
    ["c(4×2), primitive", [[2, -1, 0], [2, 1, 0], [0, 0, 1]], "The primitive cell of c(4×2) (half the 4a × 2b rectangle)"],
  ];
}

// Atom refs (measurements, planes through atoms; see measureState) and planes
// through atoms (see atomPlaneFit): at least MIN_PLANE_ATOMS atoms; a patch
// reaches PATCH_MARGIN Å beyond them. Defined before normalizePrefs, which
// runs as the script loads.
const MIN_PLANE_ATOMS = 3;
const PATCH_MARGIN = 1;
const isAtomRef = (r) => Boolean(r) && Number.isInteger(r.index) && r.index >= 0 && Number.isInteger(r.count)
  && typeof r.symbol === "string" && Array.isArray(r.image) && r.image.length === 3 && r.image.every(Number.isInteger);
const copyRef = (r) => ({ index: r.index, image: [...r.image], symbol: r.symbol, count: r.count });
const isAtomPlane = (plane) => Array.isArray(plane?.atoms);
// A plane's `scale` (both kinds; absent = 1) extends its drawn polygon in all
// in-plane directions about its centre (see scalePolygon).
const MIN_PLANE_SCALE = 1, MAX_PLANE_SCALE = 10;
const isPlaneScale = (s) => Number.isFinite(s) && s >= MIN_PLANE_SCALE && s <= MAX_PLANE_SCALE;

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
    ["tripod", DEFAULT_TRIPOD], ["property", DEFAULT_PROPERTY], ["rings", DEFAULT_RINGS], ["vibration", DEFAULT_VIBRATION],
    ["displacement", DEFAULT_DISPLACEMENT], ["symmetry", DEFAULT_SYMMETRY], ["hbonds", DEFAULT_HBONDS]]) {
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
  for (const key of ["waveVector", "waveLabels", "waveLegend"]) {
    if (typeof vibration[key] !== "boolean") vibration[key] = DEFAULT_VIBRATION[key];
  }
  for (const key of ["qColour", "vgColour"]) if (!isColour(vibration[key])) vibration[key] = DEFAULT_VIBRATION[key];
  for (const key of ["qDash", "vgDash"]) if (!Object.hasOwn(CELL_DASHES, vibration[key])) vibration[key] = DEFAULT_VIBRATION[key];
  // The wave vector is drawn on the Cartesian axes alone (see setTripodAxes).
  if (prefs.tripod.axes !== "xyz") vibration.waveVector = false;
  const tripodSize = prefs.tripod.size;
  if (!(Number.isFinite(tripodSize) && tripodSize >= TRIPOD_SIZES.min && tripodSize <= TRIPOD_SIZES.max)) prefs.tripod.size = DEFAULT_TRIPOD.size;
  for (const key of ["axesSize", "waveSize"]) {
    const part = prefs.tripod[key];
    if (!(Number.isFinite(part) && part >= TRIPOD_PART_SIZES.min && part <= TRIPOD_PART_SIZES.max)) prefs.tripod[key] = DEFAULT_TRIPOD[key];
  }
  for (const key of ["plotWidth", "plotHeight"]) {
    if (!(Number.isFinite(vibration[key]) && vibration[key] >= 160 && vibration[key] <= 4000)) vibration[key] = null;
  }
  const atomScale = prefs.appearance.atomScale;
  if (!(Number.isFinite(atomScale) && atomScale > 0 && atomScale <= MAX_ATOM_SCALE)) prefs.appearance.atomScale = DEFAULT_APPEARANCE.atomScale;
  const cellWidth = prefs.appearance.cellWidth;
  if (!(Number.isFinite(cellWidth) && cellWidth > 0 && cellWidth <= MAX_CELL_WIDTH)) prefs.appearance.cellWidth = DEFAULT_APPEARANCE.cellWidth;
  if (!isColour(prefs.appearance.cellColour)) prefs.appearance.cellColour = null;
  if (!Object.hasOwn(CELL_DASHES, prefs.appearance.cellDash)) prefs.appearance.cellDash = DEFAULT_APPEARANCE.cellDash;
  prefs.appearance.radii = { ...prefs.appearance.radii };
  prefs.appearance.colours = onlyColours(prefs.appearance.colours);
  for (const key of ["elements", "cutoffs", "colours"]) prefs.rings[key] = { ...prefs.rings[key] };
  prefs.rings.colours = onlyColours(prefs.rings.colours);
  if (!isColour(prefs.arrows.colour)) prefs.arrows.colour = null;
  if (!ARROW_SOURCES.includes(prefs.arrows.source)) prefs.arrows.source = DEFAULT_ARROWS.source;
  if (!DISPLACEMENT_REFERENCES.includes(prefs.displacement.reference)) prefs.displacement.reference = DEFAULT_DISPLACEMENT.reference;
  if (!(Number.isInteger(prefs.displacement.frame) && prefs.displacement.frame >= 0)) prefs.displacement.frame = DEFAULT_DISPLACEMENT.frame;
  // Bond lengths: numbers ≥ 0 (others dropped).
  const lengths = (map) => Object.fromEntries(Object.entries(map ?? {}).filter(([, v]) => Number.isFinite(v) && v >= 0));
  prefs.cutoffs = lengths(prefs.cutoffs);
  prefs.bondMinimums = lengths(prefs.bondMinimums);
  const hbonds = prefs.hbonds;
  hbonds.show = hbonds.show === true;
  hbonds.acceptors = Array.isArray(hbonds.acceptors) ? [...new Set(hbonds.acceptors.filter((x) => typeof x === "string"))] : [...DEFAULT_HBONDS.acceptors];
  for (const key of ["min", "max"]) if (!(Number.isFinite(hbonds[key]) && hbonds[key] >= 0)) hbonds[key] = DEFAULT_HBONDS[key];
  if (hbonds.min > hbonds.max) [hbonds.min, hbonds.max] = [DEFAULT_HBONDS.min, DEFAULT_HBONDS.max];
  if (!(Number.isFinite(hbonds.angle) && hbonds.angle >= 0 && hbonds.angle <= 180)) hbonds.angle = DEFAULT_HBONDS.angle;
  if (!isColour(hbonds.colour)) hbonds.colour = DEFAULT_HBONDS.colour;
  hbonds.perAcceptor = hbonds.perAcceptor === true;
  // Per-acceptor ranges: [min, max] with 0 ≤ min ≤ max (others dropped).
  const isRange = (r) => Array.isArray(r) && r.length === 2 && r.every((v) => Number.isFinite(v) && v >= 0) && r[0] <= r[1];
  hbonds.ranges = Object.fromEntries(Object.entries(kind(hbonds.ranges) === "object" ? hbonds.ranges : {})
    .filter(([, r]) => isRange(r)).map(([symbol, r]) => [symbol, [...r]]));
  if (!BONDED_OUTSIDE.includes(prefs.bondedOutside)) prefs.bondedOutside = "hide";
  if (!STYLES.includes(prefs.style)) prefs.style = STYLES[0];
  if (!RADIUS_TYPES.includes(prefs.radiusType)) prefs.radiusType = RADIUS_TYPES[0];
  const tolerance = prefs.symmetry.tolerance;
  if (!(Number.isFinite(tolerance) && tolerance >= MIN_SYMMETRY_TOLERANCE && tolerance <= MAX_SYMMETRY_TOLERANCE)) {
    prefs.symmetry.tolerance = DEFAULT_SYMMETRY.tolerance;
  }
  if (!(Array.isArray(prefs.customPalette) && prefs.customPalette.length === 2 && prefs.customPalette.every(isColour))) {
    prefs.customPalette = [...DEFAULT_CUSTOM_PALETTE];
  }
  // Planes through atoms (with `atoms`) need 3 valid atom refs; Miller planes
  // are kept as they come. A `scale` outside 1 to 10 is dropped (1).
  prefs.planes = prefs.planes.filter((plane) => plane && typeof plane === "object")
    .filter((plane) => !("atoms" in plane) || (Array.isArray(plane.atoms) && plane.atoms.length >= MIN_PLANE_ATOMS && plane.atoms.every(isAtomRef)))
    .map((plane) => (isColour(plane.colour) ? plane : { ...plane, colour: undefined }))
    .map((plane) => {
      if (!("scale" in plane) || isPlaneScale(plane.scale)) return plane;
      const { scale, ...rest } = plane;
      return rest;
    })
    .map((plane) => (isAtomPlane(plane) ? { atoms: plane.atoms.map(copyRef), show: plane.show !== false, patch: plane.patch === true, colour: plane.colour,
      ...("scale" in plane ? { scale: plane.scale } : {}) }
      : plane));
  if (!(raw.version >= 2) && prefs.rings.count === "all") prefs.rings.count = "auto";
  prefs.version = PREFS_VERSION;
  // Older settings repeat along a and b only: c gets 1.
  prefs.repeat = [0, 1, 2].map((k) => clampRepeat(prefs.repeat[k]));
  prefs.repeatMatrix = prefs.repeatMatrix === null ? null : checkRepeatMatrix(prefs.repeatMatrix);
  prefs.storedCellOutline = prefs.storedCellOutline === true;
  prefs.repeatCellOutline = prefs.repeatCellOutline === true;
  prefs.singleCell = prefs.singleCell === true;
  return prefs;
}

// "Single cell only" (viewerPrefs.singleCell): the stored cell and each of
// its atoms once inside it, nothing from periodic images. While it is on, the
// repeat is 1 × 1 × 1 and a transformation matrix is ignored (shownCell),
// atoms are wrapped into the cell (positionsOf), bonded atoms outside are
// hidden, polyhedra and rings reaching into a neighbouring copy are left out,
// and planes are clipped to the cell (buildScene). The settings it overrides
// are kept, so switching it off brings the previous view back; their controls
// are disabled with this tooltip.
const SINGLE_CELL_LOCK = "Single cell only is on";
const singleCellLock = (prefs = viewerPrefs) => (prefs.singleCell ? SINGLE_CELL_LOCK : null);
const SINGLE_CELL_TITLE = "Show only the stored cell, each atom once inside it (wrapped), with nothing from periodic images: "
  + "no repeat or transformation matrix, no bonded atoms outside, only polyhedra and rings complete inside the cell, planes clipped to it. "
  + "The overridden settings are kept for when it is off.";
// While it is on, those controls show the effective state (repeat 1 × 1 × 1,
// Wrap ticked, bonded atoms outside "hide", no transformation matrix, no
// outline of every copy), set without change events, so the stored settings
// stay as they are and show again once it is off.
// Disable a control's input (inside `label`) with `lock` as its tooltip, or
// enable it with its own tooltip again (kept in data-title).
function lockControl(label, lock) {
  label.dataset.title ??= label.title;
  for (const input of label.querySelectorAll("input, select")) input.disabled = Boolean(lock);
  label.title = lock ?? label.dataset.title;
  label.classList.toggle("muted", Boolean(lock));
}

// Tooltip of "Outline every copy" (viewerPrefs.repeatCellOutline), both viewers.
const EVERY_COPY_TITLE = "Draw the cell outline at every repeated copy; with a transformation matrix, "
  + "the stored-cell grid inside the shown cell, dotted";

// ---------------------------------------------------------------- control registry (GUI profiles)

// Every control of both viewers (the structure page and the notebook
// viewer), by a stable ID "area.control"; the elements carry it as
// data-control (see tagControl). Per control:
//   level: "simple" or "advanced" (the profiles);
//   label, keywords: for finding it by name;
//   data(ctx) (optional): a data rule. It REPLACES the level: when present,
//     it alone decides whether the control counts as simple (simple exactly
//     when it returns true for the shown data, see controlContext), and the
//     level is then documentation only;
//   neverHide (optional): true for a control no profile may hide (the ⚙
//     button of the notebook, where the profile switch lives); see
//     controlNeverHidden;
//   notebookOnly (optional): true for a control only the notebook viewer has
//     (the structure page's search leaves it out; see CONTROL_NEEDS for the
//     ones the structure page has only with some data);
//   countsWith (optional): the ID of the control this one is part of for the
//     count of advanced settings in use and its list (activeAdvancedControls):
//     it is counted only as that control, once (the matrix entries with the
//     transformation matrix). Hiding, its "adv." mark, inUse and search keep
//     its own ID;
//   inUse(prefs, ctx) (optional): whether its stored setting differs from
//     the default, so a profile that hides it shows it anyway. It reads the
//     stored setting, also where a lock overrides it (such as single cell
//     only). Absent for actions, outputs and remembered UI state (the
//     evaluation and pair chosen, the open tab, the file format, the tag
//     prefix, panel sizes, the property chosen automatically).
// Released IDs are never removed: a renamed control keeps its old ID in
// CONTROL_ALIASES (old → new), so saved profiles keep working.
const CONTROL_ALIASES = {};
const CONTROLS = (() => {
  const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
  const changedFrom = (value, fallback) => value !== fallback;
  const anyBound = (slice) => slice.flat().some((v) => v !== null);
  const hasEntries = (map) => Object.keys(map ?? {}).length > 0;
  // Bond cutoffs are filled with the default per pair when the controls are
  // made: in use when a pair differs from its default, or has a minimum.
  function cutoffsChanged(prefs) {
    const differs = Object.entries(prefs.cutoffs).some(([key, value]) => {
      const [a, b] = key.split("-");
      return Math.abs(value - defaultCutoff(a, b)) > 1e-9;
    });
    return differs || Object.values(prefs.bondMinimums).some((v) => v > 0);
  }
  // Displacements are shown (as arrows, or as the colouring).
  const displacementsUsed = (prefs) => (prefs.arrows.show && prefs.arrows.source === "displacement")
    || (prefs.colour === "property" && prefs.property.choice?.source === "derived" && prefs.property.choice?.name === "displacement");
  // The palette of the value colouring in use (none for element colours).
  const paletteInUse = (prefs) => (prefs.colour in DEFAULT_PALETTES ? prefs.palettes[prefs.colour] ?? DEFAULT_PALETTES[prefs.colour] : null);
  const customPaletteEdited = (prefs) => prefs.customPalette.some((c, k) => c.toLowerCase() !== DEFAULT_CUSTOM_PALETTE[k]);
  // The settings of the property colouring count only in property mode (the
  // block that shows them exists only then).
  const propertyMode = (prefs) => prefs.colour === "property";
  // Data rules shared by several controls.
  const periodicData = (ctx) => ctx.periodic;
  const modesData = (ctx) => ctx.hasModes;
  const phononData = (ctx) => ctx.hasPhonons;
  const stepData = (ctx) => ctx.stepCount > 1;
  const framesData = (ctx) => ctx.frames > 1;
  const arrowData = (ctx) => ctx.hasVectors || ctx.canDisplace;
  const S = "simple", A = "advanced";
  return {
    // Info tab
    "info.copy-cell": { level: S, label: "Copy cell and reciprocal vectors", keywords: ["lattice", "matrix", "copy", "reciprocal"] },
    "info.atom-positions": { level: S, label: "Atom positions", keywords: ["coordinates", "positions", "fractional", "copy"] },
    "info.structure-info": { level: S, label: "Structure info", keywords: ["info", "metadata", "keys"] },
    "info.provenance": { level: S, label: "Provenance metadata", keywords: ["provenance", "metadata"] },
    "info.inequivalent-sites": { level: S, label: "Inequivalent sites", keywords: ["Wyckoff", "sites", "symmetry", "equivalent"] },
    "symmetry.tolerance": { level: A, label: "Symmetry tolerance", keywords: ["symprec", "spglib", "space group", "tolerance"],
      inUse: (p) => changedFrom(p.symmetry.tolerance, DEFAULT_SYMMETRY.tolerance) },
    // View tab
    "view.preset": { level: S, label: "Top and side views", keywords: ["top view", "side view", "orientation", "normal"] },
    "view.along": { level: S, notebookOnly: true, label: "View along an axis", keywords: ["along", "axis", "a", "b", "c", "x", "y", "z", "orientation"] },
    "view.roll": { level: S, label: "Turn 90°", keywords: ["rotate", "turn", "roll", "in-plane"] },
    "view.fit": { level: S, label: "Fit", keywords: ["zoom", "fit", "centre"] },
    "cell.single-cell": { level: S, label: "Single cell only", keywords: ["unit cell", "wrap", "no images", "primitive"], data: periodicData,
      inUse: (p) => p.singleCell },
    "cell.repeat": { level: S, label: "Repeat", keywords: ["supercell", "repeat", "images", "tile"], data: periodicData,
      inUse: (p) => p.repeat.some((n) => n !== 1) },
    "cell.matrix": { level: A, label: "Transformation matrix", keywords: ["supercell", "reconstruction", "√3", "matrix", "transformation"],
      inUse: (p) => p.repeatMatrix !== null },
    "cell.matrix-entries": { level: A, label: "Transformation matrix entries", keywords: ["matrix", "rows", "supercell"],
      countsWith: "cell.matrix", inUse: (p) => p.repeatMatrix !== null },
    "cell.matrix-preset": { level: A, label: "Matrix preset", keywords: ["preset", "surface", "reconstruction"] },
    "cell.stored-outline": { level: A, label: "Stored cell outline too", keywords: ["stored cell", "dotted", "outline"],
      inUse: (p) => p.storedCellOutline && p.repeatMatrix !== null },
    "cell.outline": { level: S, label: "Cell outline", keywords: ["unit cell", "box", "outline"], inUse: (p) => !p.cell },
    "cell.outline-every-copy": { level: A, label: "Outline every copy", keywords: ["grid", "copies", "outline", "supercell"],
      inUse: (p) => p.repeatCellOutline },
    "cell.outline-width": { level: A, label: "Cell outline width", keywords: ["line width", "cell", "thickness"],
      inUse: (p) => changedFrom(p.appearance.cellWidth, DEFAULT_APPEARANCE.cellWidth) },
    "cell.outline-colour": { level: A, label: "Cell outline colour", keywords: ["cell colour", "line colour"],
      inUse: (p) => p.appearance.cellColour !== null },
    "cell.outline-style": { level: A, label: "Cell outline style", keywords: ["dashed", "dotted", "line style"],
      inUse: (p) => changedFrom(p.appearance.cellDash, DEFAULT_APPEARANCE.cellDash) },
    "cell.wrap": { level: S, label: "Wrap atoms into cell", keywords: ["wrap", "inside cell", "periodic"], data: periodicData, inUse: (p) => p.wrap },
    "axes.tripod": { level: S, label: "Axes (tripod)", keywords: ["axes", "tripod", "abc", "xyz", "compass"],
      inUse: (p) => changedFrom(p.tripod.axes, DEFAULT_TRIPOD.axes) },
    "axes.size": { level: S, label: "Tripod size", keywords: ["axes size", "tripod size", "bigger axes", "wave vector", "group velocity"],
      inUse: (p) => changedFrom(p.tripod.size, DEFAULT_TRIPOD.size) },
    "axes.axes-size": { level: A, label: "Axis arrow size", keywords: ["axes size", "tripod size", "xyz", "abc", "arrows"],
      inUse: (p) => changedFrom(p.tripod.axesSize, DEFAULT_TRIPOD.axesSize) },
    "axes.wave-size": { level: A, label: "Wave vector arrow size", keywords: ["q size", "group velocity size", "wave vector", "tripod", "phonon", "vibration"],
      data: (ctx) => ctx.hasModes && ctx.periodic, inUse: (p) => changedFrom(p.tripod.waveSize, DEFAULT_TRIPOD.waveSize) },
    "axes.in-images": { level: A, label: "Axes in saved images", keywords: ["export", "image", "axes"],
      inUse: (p) => changedFrom(p.tripod.export, DEFAULT_TRIPOD.export) },
    "settings.export-import": { level: A, label: "Export and import settings", keywords: ["settings file", "json", "save settings", "load"] },
    "settings.restore-defaults": { level: S, label: "Restore defaults", keywords: ["reset", "defaults"] },
    "help.mouse-keys": { level: S, label: "Mouse and keys", keywords: ["help", "keyboard", "shortcuts", "mouse"] },
    // Style tab
    "style.model": { level: S, label: "Model", keywords: ["style", "ball and stick", "spacefill", "CPK", "wireframe", "licorice"],
      inUse: (p) => changedFrom(p.style, STYLES[0]) },
    "style.radius-type": { level: S, label: "Radius type", keywords: ["vdW", "ionic", "Shannon", "radii"],
      inUse: (p) => changedFrom(p.radiusType, RADIUS_TYPES[0]) },
    "bonds.show": { level: S, label: "Bonds", keywords: ["bonds", "sticks"], inUse: (p) => p.bonds },
    "polyhedra.show": { level: S, label: "Polyhedra", keywords: ["polyhedra", "coordination", "octahedra", "tetrahedra"], inUse: (p) => p.polyhedra },
    "polyhedra.centre-atoms": { level: S, label: "Show centre atoms", keywords: ["centre atoms", "polyhedra", "hide metal"],
      inUse: (p) => !p.polyhedraCentres },
    "labels.mode": { level: S, label: "Atom labels", keywords: ["labels", "index", "numbers", "names"], inUse: (p) => p.labels !== "off" },
    "elements.colour": { level: S, label: "Element colours", keywords: ["colour", "element colour", "CPK colours"],
      inUse: (p) => hasEntries(p.appearance.colours) },
    "elements.radius": { level: S, label: "Element radii", keywords: ["radius", "size", "sphere size"], inUse: (p) => hasEntries(p.appearance.radii) },
    "elements.reset": { level: S, label: "Default element style", keywords: ["reset", "default colour"] },
    "appearance.atom-scale": { level: S, label: "Atom size", keywords: ["atom size", "scale", "sphere"],
      inUse: (p) => changedFrom(p.appearance.atomScale, DEFAULT_APPEARANCE.atomScale) },
    "appearance.bond-radius": { level: S, label: "Bond radius", keywords: ["bond thickness", "stick radius"],
      inUse: (p) => changedFrom(p.appearance.bondRadius, DEFAULT_APPEARANCE.bondRadius) },
    "appearance.polyhedra-opacity": { level: S, label: "Polyhedra opacity", keywords: ["transparency", "polyhedra", "alpha"],
      inUse: (p) => changedFrom(p.appearance.polyAlpha, DEFAULT_APPEARANCE.polyAlpha) },
    "appearance.plane-opacity": { level: S, label: "Plane opacity", keywords: ["transparency", "planes", "alpha"],
      inUse: (p) => changedFrom(p.appearance.planeAlpha, DEFAULT_APPEARANCE.planeAlpha) },
    "appearance.polyhedron-edges": { level: S, label: "Polyhedron edges", keywords: ["edges", "polyhedra outline"],
      inUse: (p) => changedFrom(p.appearance.polyEdges, DEFAULT_APPEARANCE.polyEdges) },
    "appearance.depth-cue": { level: S, label: "Depth cueing", keywords: ["fog", "depth", "fade"], inUse: (p) => p.appearance.depthCue },
    "appearance.depth-strength": { level: S, label: "Depth fade at the back", keywords: ["fog strength", "depth"],
      inUse: (p) => changedFrom(p.appearance.depthStrength, DEFAULT_APPEARANCE.depthStrength) },
    "bonds.cutoffs": { level: A, label: "Bond cutoffs", keywords: ["cutoff", "bond length", "neighbours", "coordination", "minimum"],
      inUse: cutoffsChanged },
    "bonds.reset-cutoffs": { level: A, label: "Reset cutoffs", keywords: ["reset", "default cutoffs"] },
    "hbonds.show": { level: A, label: "Hydrogen bonds", keywords: ["hydrogen bonds", "H-bond", "water"], data: (ctx) => ctx.hasHydrogenBondPartners,
      inUse: (p) => p.hbonds.show },
    "hbonds.acceptors": { level: A, label: "Hydrogen bond acceptors and colour", keywords: ["acceptor", "donor", "colour"],
      inUse: (p) => !sameSet(p.hbonds.acceptors, DEFAULT_HBONDS.acceptors) || p.hbonds.colour.toLowerCase() !== DEFAULT_HBONDS.colour },
    "hbonds.distance": { level: A, label: "H···A distance", keywords: ["distance", "range"],
      inUse: (p) => p.hbonds.min !== DEFAULT_HBONDS.min || p.hbonds.max !== DEFAULT_HBONDS.max },
    "hbonds.per-acceptor": { level: A, label: "Per acceptor H···A ranges", keywords: ["per element", "range"],
      inUse: (p) => p.hbonds.perAcceptor || hasEntries(p.hbonds.ranges) },
    "hbonds.angle": { level: A, label: "D–H···A angle", keywords: ["angle", "linearity"], inUse: (p) => p.hbonds.angle !== DEFAULT_HBONDS.angle },
    "bonds.outside": { level: S, label: "Bonded atoms outside", keywords: ["outside", "ligands", "partners", "complete polyhedra", "boundary"],
      inUse: (p) => p.bondedOutside !== "hide" },
    "polyhedra.centres": { level: S, label: "Polyhedron centres", keywords: ["centre", "metal", "polyhedra elements"], data: (ctx) => ctx.hasMetal,
      // null: the transition metals of the structure.
      inUse: (p, ctx) => p.polyCenters !== null
        && !(ctx?.species && sameSet(p.polyCenters, ctx.species.filter((s) => TRANSITION_METALS.has(s)))) },
    "style.reset-appearance": { level: S, label: "Reset appearance", keywords: ["reset", "defaults", "appearance"] },
    // Colour tab
    "colour.mode": { level: S, label: "Colour atoms by", keywords: ["colour by", "height", "force", "property", "charge"],
      inUse: (p) => p.colour !== "element" },
    "colour.property": { level: S, label: "Atomic property", keywords: ["property", "charges", "tags", "coordination", "magnetic moment"] },
    "colour.component": { level: A, label: "Vector component", keywords: ["vector", "component"],
      inUse: (p) => propertyMode(p) && changedFrom(p.property.component, DEFAULT_PROPERTY.component) },
    "colour.read-as": { level: A, label: "Read values as", keywords: ["categories", "continuous"],
      inUse: (p) => propertyMode(p) && changedFrom(p.property.kind, DEFAULT_PROPERTY.kind) },
    "colour.range": { level: A, label: "Colour range", keywords: ["range", "limits", "scale"],
      inUse: (p) => propertyMode(p) && (p.property.min !== null || p.property.max !== null) },
    "colour.symmetric": { level: A, label: "Symmetric around 0", keywords: ["diverging", "signed", "zero"],
      inUse: (p) => propertyMode(p) && p.property.symmetric },
    "colour.error-pair": { level: A, label: "Force difference: reference and compared", keywords: ["force error", "difference", "MLIP vs DFT"] },
    "colour.palette": { level: S, label: "Palette", keywords: ["palette", "colour map", "viridis", "colormap"],
      inUse: (p) => paletteInUse(p) !== null && paletteInUse(p) !== DEFAULT_PALETTES[p.colour] },
    "colour.custom-palette": { level: A, label: "Custom palette colours", keywords: ["custom colours", "gradient"],
      inUse: (p) => paletteInUse(p) === "custom" && customPaletteEdited(p) },
    "highlight.select": { level: S, label: "Select atoms by clicking", keywords: ["select", "pick", "highlight"] },
    "highlight.select-all": { level: S, label: "Select all shown atoms", keywords: ["select all", "slice"] },
    "highlight.clear-selection": { level: S, label: "Clear selection", keywords: ["clear", "deselect"] },
    "highlight.apply": { level: S, label: "Apply colour to selected atoms", keywords: ["highlight", "paint", "colour atoms", "adsorbate"] },
    "highlight.groups": { level: S, label: "Applied colours", keywords: ["highlight", "groups"], inUse: (p, ctx) => (ctx?.highlightGroups ?? 0) > 0 },
    "highlight.remove-all": { level: S, label: "Remove all colours", keywords: ["remove", "clear colours"] },
    // Slice tab
    "slice.elements": { level: S, label: "Shown elements", keywords: ["hide element", "show element", "filter"],
      inUse: (p) => p.hiddenElements.length > 0 },
    "slice.bounds": { level: S, label: "Fractional coordinates (slice)", keywords: ["slice", "cut", "layers", "fractional", "clip"],
      inUse: (p) => anyBound(p.slice) },
    "slice.show-all": { level: S, label: "Show all", keywords: ["reset slice", "show all"] },
    // Measure tab (notebook: the 📏 box)
    "measure.mode": { level: S, label: "Measure", keywords: ["distance", "angle", "dihedral", "measure", "bond length", "position", "coordinates"] },
    "measure.plane-choice": { level: A, label: "Planes to measure", keywords: ["plane angle", "plane distance"] },
    "measure.list": { level: S, label: "Measurements", keywords: ["remove", "clear measurements"], inUse: (p, ctx) => (ctx?.measurements ?? 0) > 0 },
    "measure.polyhedra-list": { level: S, label: "Measured polyhedra", keywords: ["polyhedron", "volume", "distortion", "bond lengths"],
      inUse: (p, ctx) => (ctx?.polyhedra ?? 0) > 0 },
    "measure.polyhedra-csv": { level: A, label: "Copy polyhedra as CSV", keywords: ["csv", "export", "clipboard"] },
    "measure.polyhedra-clear": { level: S, label: "Clear polyhedra", keywords: ["clear"] },
    "measure.stop": { level: S, label: "Stop measuring", keywords: ["stop", "cancel", "Esc"] },
    // Planes tab (notebook: ⚙ › Planes)
    "planes.add-miller": { level: S, label: "Add plane", keywords: ["Miller", "hkl", "lattice plane", "add"] },
    "planes.pick-atoms": { level: S, label: "Plane through atoms", keywords: ["plane through atoms", "best fit"] },
    "planes.make": { level: S, label: "Make plane", keywords: ["make plane", "fit"] },
    "planes.show": { level: S, label: "Show plane", keywords: ["visible", "toggle"], inUse: (p) => p.planes.length > 0 },
    "planes.colour": { level: S, label: "Plane colour", keywords: ["colour"], inUse: (p) => p.planes.length > 0 },
    "planes.miller-indices": { level: S, label: "Miller indices", keywords: ["Miller", "hkl"], inUse: (p) => p.planes.some((plane) => !isAtomPlane(plane)) },
    "planes.position": { level: S, label: "Plane position", keywords: ["position", "offset", "d spacing"],
      inUse: (p) => p.planes.some((plane) => !isAtomPlane(plane)) },
    "planes.extend": { level: S, label: "Extend plane", keywords: ["extend", "size", "scale"], inUse: (p) => p.planes.some((plane) => "scale" in plane) },
    "planes.patch": { level: S, label: "Patch around the atoms", keywords: ["patch", "local"], inUse: (p) => p.planes.some((plane) => plane.patch === true) },
    "planes.remove": { level: S, label: "Remove plane", keywords: ["remove", "delete"] },
    "planes.fit-text": { level: S, label: "Plane fit", keywords: ["RMS", "fit"] },
    // Rings tab (structure page only)
    "rings.show": { level: A, label: "Show rings", keywords: ["rings", "graphene", "zeolite", "defects"], inUse: (p) => p.rings.show },
    "rings.summary-actions": { level: A, label: "Ring signature and downloads", keywords: ["export", "json", "csv", "signature"] },
    "rings.size-colour": { level: A, label: "Ring colour per size", keywords: ["ring colour"], inUse: (p) => hasEntries(p.rings.colours) },
    "rings.method": { level: A, label: "Kind of network", keywords: ["planar", "shortest path", "Guttman"],
      inUse: (p) => changedFrom(p.rings.method, DEFAULT_RINGS.method) },
    "rings.search-size": { level: A, label: "Largest ring searched", keywords: ["ring size limit"],
      inUse: (p) => changedFrom(p.rings.searchSize, DEFAULT_RINGS.searchSize) },
    "rings.elements": { level: A, label: "Atoms that form the network", keywords: ["network atoms", "layer", "heights"],
      inUse: (p) => hasEntries(p.rings.elements) },
    "rings.from-selection": { level: A, label: "Rings of the selected atoms", keywords: ["selection", "layer"] },
    "rings.all-atoms": { level: A, label: "Rings of all atoms", keywords: ["reset", "all"] },
    "rings.alternating": { level: A, label: "Only bonds between different elements", keywords: ["alternating", "M–O"], inUse: (p) => p.rings.alternating },
    "rings.cutoffs": { level: A, label: "Bond cutoffs for rings", keywords: ["ring cutoff"], inUse: (p) => hasEntries(p.rings.cutoffs) },
    "rings.count": { level: A, label: "Ring size count", keywords: ["ring size", "counting"], inUse: (p) => changedFrom(p.rings.count, DEFAULT_RINGS.count) },
    "rings.enclosed": { level: A, label: "Count atoms inside a ring", keywords: ["enclosed", "6+1"], inUse: (p) => !p.rings.enclosed },
    "rings.size-range": { level: A, label: "Ring sizes shown", keywords: ["filter sizes"],
      inUse: (p) => p.rings.minSize !== null || p.rings.maxSize !== null },
    "rings.scheme": { level: A, label: "Ring colours", keywords: ["ring colours", "palette"], inUse: (p) => changedFrom(p.rings.scheme, DEFAULT_RINGS.scheme) },
    "rings.custom-palette": { level: A, label: "Custom ring colours", keywords: ["custom"],
      inUse: (p) => p.rings.scheme === "custom" && customPaletteEdited(p) },
    "rings.opacity": { level: A, label: "Ring opacity", keywords: ["transparency"], inUse: (p) => changedFrom(p.rings.alpha, DEFAULT_RINGS.alpha) },
    "rings.outline": { level: A, label: "Ring outlines", keywords: ["outline"], inUse: (p) => !p.rings.outline },
    "rings.labels": { level: A, label: "Ring size labels", keywords: ["labels"], inUse: (p) => p.rings.labels },
    "rings.label-size": { level: A, label: "Ring label size", keywords: ["label size"],
      inUse: (p) => changedFrom(p.rings.labelScale, DEFAULT_RINGS.labelScale) },
    // Forces tab (notebook: ⚙ › Arrows)
    // Simple when there is only something to displace: the source defaults
    // to the vectors with no fallback here, so without this the simple
    // profile could show arrows of nothing (the notebook falls back itself).
    "arrows.source": { level: A, label: "Arrows of", keywords: ["displacement", "forces", "source"],
      data: (ctx) => ctx.canDisplace && !ctx.hasVectors,
      inUse: (p) => changedFrom(p.arrows.source, DEFAULT_ARROWS.source) },
    "arrows.evaluation": { level: S, label: "Arrow evaluation", keywords: ["method", "evaluation", "DFT", "MLIP"], data: (ctx) => ctx.hasVectors },
    "arrows.vector": { level: A, label: "Arrow vector", keywords: ["vector", "forces"] },
    // Notebook: one select for the vector columns and displacements.
    "arrows.vectors": { level: A, notebookOnly: true, label: "Arrow vectors", keywords: ["vector", "forces", "displacement", "columns"],
      inUse: (p) => changedFrom(p.arrows.source, DEFAULT_ARROWS.source) },
    "arrows.displacement-reference": { level: A, label: "Displacement reference", keywords: ["reference", "displacement", "relaxation"],
      inUse: (p) => displacementsUsed(p)
        && (p.displacement.reference !== DEFAULT_DISPLACEMENT.reference || p.displacement.frame !== DEFAULT_DISPLACEMENT.frame) },
    "arrows.show": { level: S, label: "Show arrows", keywords: ["arrows", "forces", "vectors"], data: arrowData, inUse: (p) => p.arrows.show },
    "arrows.length": { level: S, label: "Arrow length", keywords: ["length", "scale", "auto"], data: arrowData,
      inUse: (p) => changedFrom(p.arrows.scale, DEFAULT_ARROWS.scale) },
    "arrows.width": { level: S, label: "Arrow width", keywords: ["thickness", "width"], data: arrowData,
      inUse: (p) => changedFrom(p.arrows.width, DEFAULT_ARROWS.width) },
    "arrows.colour": { level: S, label: "Arrow colour", keywords: ["arrow colour"], data: arrowData, inUse: (p) => p.arrows.colour !== null },
    "arrows.min-magnitude": { level: A, label: "Hide arrows below", keywords: ["threshold", "small forces"],
      inUse: (p) => changedFrom(p.arrows.minMagnitude, DEFAULT_ARROWS.minMagnitude) },
    "arrows.reset-style": { level: S, label: "Reset arrow style", keywords: ["reset"], data: arrowData },
    "forces.follow-slice": { level: A, label: "Include atoms: same as slice", keywords: ["include", "selection", "slice"],
      inUse: (p) => !p.forceFollowsSlice },
    "forces.include-elements": { level: A, label: "Include forces of elements", keywords: ["exclude", "elements"],
      inUse: (p) => p.forceHiddenElements.length > 0 },
    "forces.include-bounds": { level: A, label: "Include forces within bounds", keywords: ["fixed atoms", "bottom layers"],
      inUse: (p) => anyBound(p.forceSlice) },
    "forces.include-all": { level: A, label: "Include all", keywords: ["reset"] },
    // Vibrations tab (notebook: the Vibrations box); only with modes.
    "vibration.q-point": { level: S, label: "q-point", keywords: ["q-point", "wave vector", "Brillouin zone", "phonon", "vibration"], data: modesData },
    "vibration.direction": { level: A, label: "Direction to Γ", keywords: ["LO-TO", "NAC", "direction", "phonon", "vibration"] },
    "vibration.mode": { level: S, label: "Mode", keywords: ["mode", "frequency", "phonon", "vibration"], data: modesData },
    "vibration.play": { level: S, label: "Play vibration", keywords: ["animate", "play", "vibrate", "phonon", "vibration"], data: modesData },
    "vibration.record": { level: S, label: "Record video", keywords: ["video", "movie", "record", "webm", "mp4", "phonon", "vibration"], data: modesData },
    "vibration.amplitude": { level: S, label: "Amplitude", keywords: ["amplitude", "displacement size", "phonon", "vibration"], data: modesData,
      inUse: (p) => changedFrom(p.vibration.amplitude, DEFAULT_VIBRATION.amplitude) },
    "vibration.period": { level: A, label: "Period", keywords: ["speed", "period", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.periodSeconds, DEFAULT_VIBRATION.periodSeconds) },
    "vibration.bonds": { level: A, label: "Bonds while vibrating", keywords: ["bonds", "live", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.bonds, DEFAULT_VIBRATION.bonds) },
    "vibration.unit": { level: S, label: "Frequency unit", keywords: ["wavenumber", "cm-1", "THz", "phonon", "vibration"], data: modesData,
      inUse: (p) => changedFrom(p.vibration.unit, DEFAULT_VIBRATION.unit) },
    "vibration.arrows": { level: S, label: "Show modes as arrows", keywords: ["eigenvector", "arrows", "phonon", "vibration"], data: modesData,
      inUse: (p) => p.vibration.showArrows },
    "vibration.apply-repeat": { level: S, label: "Apply the repeat for this q", keywords: ["supercell", "wavelength", "phonon", "vibration"], data: modesData },
    "vibration.wave-vector": { level: S, label: "Show wave vector on the axes",
      keywords: ["wave vector", "q arrow", "group velocity", "Brillouin zone", "tripod", "phonon", "vibration"],
      data: (ctx) => ctx.hasModes && ctx.periodic, inUse: (p) => p.vibration.waveVector },
    "vibration.wave-colours": { level: A, label: "Wave vector arrow colours", keywords: ["q colour", "group velocity colour", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.qColour, DEFAULT_VIBRATION.qColour) || changedFrom(p.vibration.vgColour, DEFAULT_VIBRATION.vgColour) },
    "vibration.wave-styles": { level: A, label: "Wave vector arrow styles", keywords: ["dashed", "dotted", "line style", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.qDash, DEFAULT_VIBRATION.qDash) || changedFrom(p.vibration.vgDash, DEFAULT_VIBRATION.vgDash) },
    "vibration.wave-labels": { level: A, label: "Wave vector arrow names", keywords: ["labels", "q", "v_g", "phonon", "vibration"],
      inUse: (p) => !p.vibration.waveLabels },
    "vibration.wave-legend": { level: A, label: "Wave vector legend", keywords: ["legend", "explanation", "phonon", "vibration"],
      inUse: (p) => !p.vibration.waveLegend },
    "vibration.video-periods": { level: A, label: "Video periods", keywords: ["video length", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.recordPeriods, DEFAULT_VIBRATION.recordPeriods) },
    "vibration.video-size": { level: A, label: "Video size", keywords: ["resolution", "HD", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.videoSize, DEFAULT_VIBRATION.videoSize) },
    "vibration.video-fps": { level: A, label: "Video frame rate", keywords: ["fps", "phonon", "vibration"],
      inUse: (p) => changedFrom(p.vibration.videoFps, DEFAULT_VIBRATION.videoFps) },
    // Save tab
    "save.format": { level: S, label: "Structure file format", keywords: ["export", "POSCAR", "CIF", "extxyz", "download"] },
    "save.structure": { level: S, label: "Save structure", keywords: ["download", "export", "file"] },
    "save.svg": { level: S, label: "Save SVG", keywords: ["image", "vector", "figure", "export"] },
    "save.png": { level: S, label: "Save PNG", keywords: ["bitmap", "png", "figure"] },
    "save.transparent": { level: A, label: "Transparent background", keywords: ["background", "transparent"], inUse: (p) => !p.svgTransparent },
    "save.png-scale": { level: A, label: "PNG resolution", keywords: ["dpi", "resolution", "scale"], inUse: (p) => changedFrom(p.pngScale, 3) },
    // Structure page, around the viewer
    "page.selected": { level: S, label: "Selected", keywords: ["select", "pick", "aggregation"], data: (ctx) => ctx.fromAggregation },
    "step.source": { level: A, label: "Step through", keywords: ["step", "aggregation", "related", "trajectory"] },
    "step.prefix": { level: A, label: "Tag prefix", keywords: ["tag prefix", "run"] },
    "step.previous-next": { level: S, label: "Previous and next structure", keywords: ["previous", "next", "step"], data: stepData },
    "step.picker": { level: S, label: "Structure in the step list", keywords: ["jump", "position", "frame"], data: stepData },
    "movie.play": { level: S, label: "Play movie", keywords: ["movie", "play", "trajectory", "animate"], data: stepData },
    "movie.frame-slider": { level: S, label: "Movie frame", keywords: ["scrub", "frame"], data: stepData },
    "movie.fps": { level: S, label: "Frames per second", keywords: ["speed", "frames per second"],
      inUse: (p) => changedFrom(p.player.fps, DEFAULT_PLAYER.fps) },
    "movie.loop": { level: S, label: "Loop", keywords: ["loop", "repeat"], inUse: (p) => !p.player.loop },
    "movie.range": { level: S, label: "Movie frames", keywords: ["range", "frames"] },
    "compare.with": { level: S, label: "Compare with", keywords: ["compare", "side by side", "difference", "two structures"], data: stepData },
    "compare.open-file": { level: A, label: "Open file to compare", keywords: ["open", "upload", "POSCAR", "compare file"] },
    "compare.steps-side": { level: A, label: "Steps move left or right", keywords: ["reference", "panel"] },
    "compare.swap": { level: A, label: "Swap", keywords: ["swap"] },
    "compare.close": { level: S, label: "Close comparison", keywords: ["close", "single"], data: (ctx) => ctx.comparing },
    "elements.bar": { level: S, label: "Element bar", keywords: ["element", "hide", "legend", "count"], inUse: (p) => p.hiddenElements.length > 0 },
    "elements.editor": { level: S, label: "Element editor", keywords: ["colour", "radius", "only element"] },
    "footer.save-svg": { level: S, label: "Save SVG", keywords: ["image", "export", "figure"] },
    "footer.clear-all": { level: S, label: "Clear all", keywords: ["reset", "clear", "plain structure"] },
    "panel.resize": { level: S, label: "Resize the panel", keywords: ["size", "resize", "width", "height"] },
    "tabs.bar": { level: S, label: "Settings tabs", keywords: ["tabs"] },
    "phonon.nac": { level: A, label: "NAC", keywords: ["NAC", "Born charges", "LO-TO", "phonon"] },
    "phonon.save-svg": { level: S, label: "Save bands and DOS", keywords: ["band structure", "DOS", "figure", "phonon"], data: phononData },
    "phonon.side": { level: A, label: "Plot beside the structure", keywords: ["layout", "side by side", "phonon"], inUse: (p) => p.vibration.plotSide },
    "phonon.path-slider": { level: S, label: "Position along the band path", keywords: ["q path", "slider", "phonon"], data: phononData },
    "phonon.resize": { level: S, label: "Resize the band plot", keywords: ["size", "phonon"], data: phononData },
    // Notebook viewer only
    "frames.step": { level: S, notebookOnly: true, label: "Previous and next frame", keywords: ["frame", "previous", "next", "trajectory"], data: framesData },
    "frames.slider": { level: S, notebookOnly: true, label: "Frame slider", keywords: ["frame", "scrub"], data: framesData },
    "frames.number": { level: S, notebookOnly: true, label: "Frame number", keywords: ["frame number", "jump"], data: framesData },
    "frames.play": { level: S, notebookOnly: true, label: "Play frames", keywords: ["play", "movie", "animate"], data: framesData },
    "embed.pop-out": { level: S, notebookOnly: true, label: "Open in a new tab (⧉)", keywords: ["new tab", "pop out", "browser"] },
    "embed.measure-toggle": { level: S, notebookOnly: true, label: "Measure box (📏)", keywords: ["measure", "distance", "angle"] },
    "embed.settings-toggle": { level: S, notebookOnly: true, label: "Settings panel (⚙)", keywords: ["settings", "options", "profile"], neverHide: true },
    "embed.panel-size": { level: A, notebookOnly: true, label: "Panel width and height", keywords: ["size", "width", "height", "image size"] },
    "embed.save-html": { level: S, notebookOnly: true, label: "Save HTML", keywords: ["standalone", "html", "share"] },
    "embed.reset-view": { level: S, notebookOnly: true, label: "Reset view", keywords: ["reset", "top view", "camera"] },
  };
})();

// The control `id` names (an alias resolved).
const controlId = (id) => CONTROL_ALIASES[id] ?? id;
// Mark `node` (an element, or null) as the control `id` of CONTROLS.
function tagControl(node, id) {
  if (!Object.hasOwn(CONTROLS, id)) console.error(`Unknown viewer control ${id}`);
  if (node) node.dataset.control = id;
  return node;
}
// The data the control rules ask about (see CONTROLS), for `structures`
// (the shown ones) and what the host knows besides: frames (notebook),
// stepCount (structure page: the step list), comparing, fromAggregation,
// hasVectors (per-atom vectors to draw), canDisplace (a reference for
// displacements), and the page state counted as in use: measurements,
// polyhedra and highlightGroups (numbers).
function controlContext(structures, extra = {}) {
  const shown = structures.filter(Boolean);
  const species = [...new Set(shown.flatMap((s) => s.symbols ?? []))].sort();
  return {
    species,
    periodic: shown.some((s) => (s.pbc ?? []).some(Boolean)),
    // A cell to show (the Info tab's "Structure and lattice").
    hasCell: shown.some((s) => (s.cell ?? []).some((v) => Math.hypot(...v) > 1e-8)),
    hasMetal: species.some((s) => !NONMETALS.has(s)),
    hasHydrogenBondPartners: species.includes("H") && species.some((s) => DEFAULT_HBONDS.acceptors.includes(s)),
    hasModes: shown.some((s) => Boolean(s.has_modes)),
    hasPhonons: shown.some((s) => Boolean(s.has_phonons)),
    hasSymmetry: shown.some(symmetryAvailable),
    frames: 1, stepCount: 0, comparing: false, fromAggregation: false, hasVectors: false, canDisplace: false,
    measurements: 0, polyhedra: 0, highlightGroups: 0,
    ...extra,
  };
}
// Whether control `id` is simple under the data in `ctx`, and whether its
// setting is in use (see CONTROLS).
function controlIsSimple(id, ctx) {
  const control = CONTROLS[controlId(id)];
  return control.data ? Boolean(control.data(ctx)) : control.level === "simple";
}
const controlInUse = (id, prefs, ctx) => Boolean(CONTROLS[controlId(id)].inUse?.(prefs, ctx));
// The control `id` counts as among the advanced settings in use (countsWith).
const controlCountedAs = (id) => controlId(CONTROLS[controlId(id)]?.countsWith ?? id);
// Whether no profile may hide control `id` (see CONTROLS).
const controlNeverHidden = (id) => Boolean(CONTROLS[controlId(id)].neverHide);

// ---------------------------------------------------------------- profiles (GUI profiles)

// A profile chooses which controls are shown; it never changes a setting or
// the picture, and is no setting itself (not in viewerPrefs or settings
// files). The structure page keeps it in this browser (PROFILE_KEY), the
// notebook viewer in its state and saved HTML (STOMS_EMBED.profile).
const PROFILES = { simple: "Simple", advanced: "Advanced" };
const DEFAULT_PROFILE = "simple";
const PROFILE_KEY = "stoms.viewer.profile";
const validProfile = (profile) => (Object.hasOwn(PROFILES, profile) ? profile : DEFAULT_PROFILE);
function storedProfile() {
  try { return validProfile(localStorage.getItem(PROFILE_KEY)); } catch { return DEFAULT_PROFILE; }
}
function storeProfile(profile) {
  try { localStorage.setItem(PROFILE_KEY, profile); } catch { /* storage unavailable */ }
}
// Profile files (format version PROFILE_FORMAT), also how the built-in
// profiles are written:
//   { "stomsProfile": 1, "name": "my profile",
//     "controls": { "cell.matrix": true, "cell.repeat": false } }
// "controls" maps control IDs (CONTROLS) to true (shown) or false (hidden).
// A control not listed follows its built-in level and data rule, as in
// simple (so controls added after a file was saved fall back to their level);
// an ID this version does not know is ignored (a file from a newer STOMS
// loads here); an old ID (CONTROL_ALIASES) counts as its new one, unless the
// file names the new one too. No profile hides a control marked neverHide
// (false is ignored), and a setting in use is shown under every profile.
// checkProfileFile reads one; stoms.viewer.profiles does the same in Python
// (the same cases run through both: tests/data/profile_files.json).
const PROFILE_FORMAT = 1;
function deepFreeze(o) {
  for (const v of Object.values(o)) if (v !== null && typeof v === "object") deepFreeze(v);
  return Object.freeze(o);
}
// Simple lists nothing (every control by its level); advanced shows all.
const BUILTIN_PROFILES = deepFreeze({
  simple: { stomsProfile: PROFILE_FORMAT, name: "simple", controls: {} },
  advanced: { stomsProfile: PROFILE_FORMAT, name: "advanced",
    controls: Object.fromEntries(Object.keys(CONTROLS).map((id) => [id, true])) },
});
// What a profile file is checked against: the control IDs, the old IDs
// (old → new) and the IDs no profile hides. stoms/viewer/controls.json holds
// the same for Python (a test keeps it equal).
const profileRegistry = () => ({
  ids: Object.keys(CONTROLS),
  aliases: { ...CONTROL_ALIASES },
  neverHide: Object.keys(CONTROLS).filter(controlNeverHidden),
});
// The profile in the file `doc` (parsed JSON), as { profile, warnings }:
// profile { stomsProfile, name, controls } with only known current IDs (old
// ones renamed; unknown ones and false for a control no profile hides
// dropped), warnings what was ignored, in the file's order. Throws an Error
// whose message says what is wrong (wrong type, missing field, other format
// version). `registry` as profileRegistry() (tests use their own).
function checkProfileFile(doc, registry = profileRegistry()) {
  const kind = (v) => (v === null ? "null" : Array.isArray(v) ? "a list" : typeof v === "object" ? "an object"
    : typeof v === "boolean" ? "a boolean" : typeof v === "number" ? "a number" : typeof v === "string" ? "a string" : typeof v);
  const fail = (message) => { throw new Error(`Invalid STOMS profile: ${message}`); };
  const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  if (!isObject(doc)) fail(`expected a JSON object, got ${kind(doc)}.`);
  if (!Object.hasOwn(doc, "stomsProfile")) fail('"stomsProfile" (the format version) is missing.');
  if (typeof doc.stomsProfile !== "number") fail(`"stomsProfile" must be the number ${PROFILE_FORMAT}, got ${kind(doc.stomsProfile)}.`);
  if (doc.stomsProfile !== PROFILE_FORMAT) fail(`this STOMS reads format version ${PROFILE_FORMAT} only ("stomsProfile": ${PROFILE_FORMAT}).`);
  if (!Object.hasOwn(doc, "name")) fail('"name" is missing.');
  if (typeof doc.name !== "string") fail(`"name" must be a string, got ${kind(doc.name)}.`);
  if (!doc.name) fail('"name" is empty.');
  if (!Object.hasOwn(doc, "controls")) fail('"controls" is missing.');
  if (!isObject(doc.controls)) fail(`"controls" must be an object of control IDs, got ${kind(doc.controls)}.`);
  const entries = Object.entries(doc.controls);
  for (const [id, value] of entries) {
    if (typeof value !== "boolean") fail(`control "${id}" must be true or false, got ${kind(value)}.`);
  }
  const ids = new Set(registry.ids), neverHide = new Set(registry.neverHide);
  const current = (id) => (Object.hasOwn(registry.aliases, id) ? registry.aliases[id] : id);
  const controls = {}, warnings = [];
  for (const [id, value] of entries) {
    const to = current(id);
    if (!ids.has(to)) { warnings.push(`Unknown control "${id}" ignored (from a newer STOMS, or a typo).`); continue; }
    // The new ID wins over its old one.
    if (to !== id && Object.hasOwn(doc.controls, to)) continue;
    if (!value && neverHide.has(to)) { warnings.push(`Control "${id}" cannot be hidden by a profile; false ignored.`); continue; }
    controls[to] = value;
  }
  return { profile: { stomsProfile: PROFILE_FORMAT, name: doc.name, controls }, warnings };
}
// The profile object of `profile`: a built-in's name (anything else is the
// default), or a profile object as checkProfileFile returns it.
const profileDefinition = (profile) => (profile !== null && typeof profile === "object" ? profile : BUILTIN_PROFILES[validProfile(profile)]);
// Whether `profile` (a name or a profile object) hides control `id` while
// its setting is not in use: what the profile lists for it, else its level
// and data rule (as simple). Never a control no profile hides, nor an
// unknown one.
function profileHides(id, profile, ctx) {
  const key = controlId(id);
  if (!Object.hasOwn(CONTROLS, key) || controlNeverHidden(key)) return false;
  const listed = profileDefinition(profile).controls;
  return !(Object.hasOwn(listed, key) ? listed[key] : controlIsSimple(key, ctx));
}
// Whether control `id` is shown under `profile` (a name or a profile
// object): advanced shows everything; simple shows the simple controls (level
// or data rule), the ones no profile hides, and those whose setting is in
// use, so that nothing that changes the picture is ever hidden; another
// profile shows what it lists as true and hides what it lists as false,
// the rest as simple, a setting in use always. Unknown IDs are shown.
function controlShown(id, profile, ctx, prefs) {
  return !profileHides(id, profile, ctx) || controlInUse(id, prefs, ctx);
}
// Whether control `id` is an advanced one under the data in `ctx`: a profile
// that shows only simple controls hides it unless it is in use (no data
// rule makes it simple, and it is not one no profile hides).
const controlAdvanced = (id, ctx) => profileHides(id, BUILTIN_PROFILES.simple, ctx);
// The small grey tag after the label of an advanced control that simple shows
// anyway, and its tooltip (also its text for screen readers), by the reason
// it is shown.
const PROFILE_MARK = "adv.";
const PROFILE_MARK_TITLES = {
  use: "Advanced setting, shown because it is in use",
  search: "Advanced setting, shown because you searched for it",
  // In the search results: a control the profile hides now.
  hidden: "Advanced setting, hidden by the Simple profile",
};
function profileMark(reason = "use") {
  const title = PROFILE_MARK_TITLES[reason] ?? PROFILE_MARK_TITLES.use;
  return el("span", { class: "profile-mark", title },
    el("span", { "aria-hidden": "true" }, PROFILE_MARK), el("span", { class: "visually-hidden" }, ` (${title})`));
}
// Whether the host hides `node` (a `hidden` element around it, under `root`)
// where a jump cannot open it: tab panels (role "tabpanel") and boxes marked
// data-profile-place (the notebook's ⚙) can be opened.
function hiddenByHost(node, root) {
  for (let n = node; n && n !== root; n = n.parentElement) {
    if (n.hidden && n.getAttribute("role") !== "tabpanel" && !n.hasAttribute("data-profile-place")) return true;
  }
  return false;
}
// The advanced settings in use under `root`, once per control ID even when
// it is tagged twice: [{ id, node }] in the order of the page, `node` its
// first element the host shows (see hiddenByHost). A control with countsWith
// counts as that control (its own element stands in for it only where the
// host shows none of that control's). Only controls that are
// there count (the notebook has no ring controls, so ring settings from a
// settings file do not); locked settings count (inUse reads the stored
// value). The same in both profiles; simple shows them with PROFILE_MARK.
function activeAdvancedControls(root, ctx, prefs = viewerPrefs) {
  const found = new Map();
  for (const node of root.querySelectorAll("[data-control]")) {
    const id = controlId(node.dataset.control);
    if (!controlAdvanced(id, ctx) || !controlInUse(id, prefs, ctx) || hiddenByHost(node, root)) continue;
    const counted = controlCountedAs(id), own = counted === id;
    // An element of the control itself replaces one that stood in for it.
    if (found.has(counted) && (found.get(counted).own || !own)) continue;
    found.set(counted, { node, own });
  }
  return [...found].map(([id, { node }]) => ({ id, node }));
}
// Where `node` sits under `root`, for a list of controls: its tab (or the
// box marked data-profile-place: the notebook's ⚙, 📏 and Vibrations; the
// structure page's Steps, Compare, Element bar and Footer outside the tabs;
// the innermost wins) and the sections around it (<details>
// summary, fieldset legend, section heading), outermost first.
function controlPlace(node, root) {
  const text = (n) => {
    const copy = n.cloneNode(true);
    for (const m of copy.querySelectorAll(".profile-mark")) m.remove();
    return copy.textContent.replace(/\s+/g, " ").trim();
  };
  const parts = [];
  for (let n = node.parentElement; n && n !== root; n = n.parentElement) {
    let heading = null;
    if (n.tagName === "DETAILS") heading = n.querySelector(":scope > summary");
    else if (n.tagName === "FIELDSET") heading = n.querySelector(":scope > legend");
    else if (n.tagName === "SECTION") heading = n.querySelector(":scope > h4, :scope > h3");
    if (heading && text(heading)) parts.unshift(text(heading));
    if (n.getAttribute("role") === "tabpanel") {
      const tab = root.querySelector(`[role="tab"][aria-controls="${CSS.escape(n.id)}"]`);
      if (tab) parts.unshift(text(tab));
      break;
    }
    if (n.dataset.profilePlace) { parts.unshift(n.dataset.profilePlace); break; }
  }
  return parts;
}
// Where the mark of a tagged `node` goes: at the end of its label (a
// <details> summary, a field label, legend or heading, the text before the
// input of a field, the text of a check box), or after the control itself
// (an input, select or button). A table: in the summary of the <details> it
// opens, else before it.
function placeProfileMark(node, mark) {
  const summaryOf = (details) => details?.querySelector(":scope > summary");
  if (node.tagName === "DETAILS" && summaryOf(node)) { summaryOf(node).append(mark); return; }
  if (node.tagName === "TABLE") {
    const details = node.closest("details");
    if (summaryOf(details) && details.querySelector("[data-control]") === node) summaryOf(details).append(mark);
    else node.before(mark);
    return;
  }
  if (["INPUT", "SELECT", "BUTTON", "TEXTAREA"].includes(node.tagName)) { node.after(mark); return; }
  const first = node.firstElementChild;
  const label = node.querySelector(":scope > .field-label, :scope > legend, :scope > h4, :scope > summary")
    ?? (first && first === node.firstChild && ["SPAN", "STRONG"].includes(first.tagName) && !first.querySelector("input, select, button") ? first : null);
  (label ?? node).append(mark);
}
// Show the controls of `profile` (a built-in's name or a profile object, see
// checkProfileFile) under `root` and hide the rest (attribute
// data-profile-hidden, display: none, so they also leave the tab order).
// Tags sit on the controls themselves, so their containers (a section,
// <details>, fieldset, row of checkboxes or buttons, a field) are hidden
// when every control in them is; a tab (role "tab", with aria-controls) when
// its panel shows none. The open tab and its panel always stay. Results
// marked data-profile-content (a ring summary, the space group) count as
// shown, so what holds them stays; tables, their rows and cells are never
// hidden for being empty (their columns would shift). `keep` (a Map of IDs
// to the reason: "use" for controls shown because they were in use, "tab"
// for the open tab kept whole, "jump" for one chosen from the count's list,
// "search" for one chosen from the search results) holds controls that stay
// shown, also once set back to their default, until the caller clears it (on
// leaving the tab or changing the profile). An advanced control shown in
// simple because it is (or was) in use, or chosen from the list or the
// search, carries PROFILE_MARK after its label (its tooltip says which:
// PROFILE_MARK_TITLES; in use wins over searched); not in advanced, not
// on simple controls or those a data rule makes simple (in general: only on
// controls the profile hides, profileHides). Purely visual: never writes a
// setting.
function applyProfile(root, profile, ctx, { prefs = viewerPrefs, keep = null } = {}) {
  const HIDDEN = "data-profile-hidden";
  const mark = (node, hide) => { if (node.hasAttribute(HIDDEN) !== hide) node.toggleAttribute(HIDDEN, hide); };
  const tagged = [...root.querySelectorAll("[data-control]")];
  const own = new Map(), marked = new Map();
  for (const node of tagged) {
    const id = node.dataset.control;
    let shown = controlShown(id, profile, ctx, prefs);
    const revealed = profileHides(id, profile, ctx);
    const inUse = revealed && controlInUse(id, prefs, ctx);
    if (keep) {
      if (inUse && !["jump", "search"].includes(keep.get(controlId(id)))) keep.set(controlId(id), "use");
      shown ||= keep.has(controlId(id));
    }
    own.set(node, shown);
    const reason = inUse ? "use" : keep?.get(controlId(id));
    if (revealed && shown && ["use", "jump", "search"].includes(reason)) marked.set(node, reason === "search" ? "search" : "use");
  }
  // Shown: itself and every tagged element around it.
  const visible = (node) => {
    for (let n = node; n && n !== root; n = n.parentElement) if (own.get(n) === false) return false;
    return true;
  };
  const panelOf = (tab) => root.querySelector(`#${CSS.escape(tab.getAttribute("aria-controls"))}`);
  const panels = new Set([...root.querySelectorAll('[role="tab"][aria-controls]')].map(panelOf).filter(Boolean));
  // The open tab never empties under the user: when the profile would hide
  // all of it, it stays whole (kept) until it is left.
  for (const tab of root.querySelectorAll('[role="tab"][aria-selected="true"][aria-controls]')) {
    const inside = tagged.filter((node) => panelOf(tab)?.contains(node));
    if (inside.length && !inside.some(visible)) {
      for (const node of inside) {
        own.set(node, true);
        if (!keep?.has(controlId(node.dataset.control))) keep?.set(controlId(node.dataset.control), "tab");
      }
    }
  }
  const holders = new Set(), showing = new Set();
  const up = (node, shown) => {
    for (let n = node.parentElement; n && n !== root; n = n.parentElement) {
      holders.add(n);
      if (shown) showing.add(n);
    }
  };
  for (const node of tagged) up(node, visible(node));
  // Results shown (not empty, not hidden by their host or a hidden control).
  for (const node of root.querySelectorAll("[data-profile-content]")) {
    if (node.textContent.trim() && !node.closest("[hidden]") && visible(node)) up(node, true);
  }
  for (const node of tagged) mark(node, !own.get(node));
  // Containers: untagged elements holding tagged ones, none of them shown.
  const TABLE_PARTS = new Set(["TABLE", "THEAD", "TBODY", "TFOOT", "TR", "TD", "TH"]);
  for (const node of root.querySelectorAll(`[${HIDDEN}]:not([data-control])`)) {
    if (!holders.has(node) || showing.has(node)) mark(node, false);
  }
  for (const node of holders) {
    if (own.has(node) || panels.has(node)) continue;
    mark(node, !showing.has(node) && !TABLE_PARTS.has(node.tagName) && !node.closest("[data-profile-content]"));
  }
  // Tabs: hidden when their panel shows nothing, except the open one.
  for (const tab of root.querySelectorAll('[role="tab"][aria-controls]')) {
    const panel = root.querySelector(`#${CSS.escape(tab.getAttribute("aria-controls"))}`);
    if (!panel) continue;
    const empty = holders.has(panel) && !showing.has(panel);
    const open = tab.getAttribute("aria-selected") === "true";
    mark(tab, empty && !open);
    mark(panel, empty && !open);
  }
  // Marks: one per control, after the first of its elements in a row (Export
  // and Import share one; a label and its input too), none inside another
  // element of the same control. Added and removed only when that changes.
  const wanted = new Set(), seen = new Map();
  for (const [node, reason] of marked) {
    if (!visible(node) || node.tagName === "OPTION") continue;
    const id = controlId(node.dataset.control);
    const parents = seen.get(id) ?? new Set();
    seen.set(id, parents);
    if (parents.has(node.parentElement) || node.parentElement?.closest(`[data-control="${CSS.escape(node.dataset.control)}"]`)) continue;
    parents.add(node.parentElement);
    let tag = profileMarks.get(node);
    if (!tag?.isConnected || tag.dataset.profileMark !== reason) {
      tag?.remove();
      tag = profileMark(reason);
      tag.dataset.profileMark = reason;
      profileMarks.set(node, tag);
      placeProfileMark(node, tag);
    }
    wanted.add(tag);
  }
  for (const tag of root.querySelectorAll("[data-profile-mark]")) if (!wanted.has(tag)) tag.remove();
}
// The mark (PROFILE_MARK) of each tagged element that has one.
const profileMarks = new WeakMap();
// Functions called after every savePrefs (settings changed).
const savePrefsListeners = new Set();
// A profile on `root`, applied again (once per frame) whenever the elements
// under it change, an input in it is used, the settings change, or the
// profile is switched. `context()` gives the control rules' data (see
// controlContext), `onApply(view)` runs after each pass. The kept controls
// (see applyProfile) are cleared on another tab and another profile.
// view.active lists the advanced settings in use (activeAdvancedControls),
// for the count beside the switch (createProfileCount); view.jump(id, reason)
// goes to one of them, or to any control the host shows (the search,
// createControlSearch): its tab, `open(node)` of the host for a box it keeps
// closed (the notebook's ⚙), closed <details> around it; it is shown there
// (kept, for `reason`: "jump" or "search", see applyProfile) until the tab is
// left, scrolled to, focused and highlighted. Returns false when the host
// shows no element of it. Never writes a setting.
function createProfileView(root, { profile = DEFAULT_PROFILE, context, onApply = null, open = null } = {}) {
  const view = { root, profile: validProfile(profile), keep: new Map(), tab: undefined, listeners: new Set(),
    active: [], applied: new Set() };
  let frame = 0;
  view.apply = () => {
    cancelAnimationFrame(frame);
    frame = 0;
    const tab = root.querySelector('[role="tab"][aria-selected="true"]')?.id ?? null;
    if (tab !== view.tab) { view.keep.clear(); view.tab = tab; }
    const ctx = context();
    applyProfile(root, view.profile, ctx, { keep: view.keep });
    view.active = activeAdvancedControls(root, ctx);
    onApply?.(view);
    view.applied.forEach((f) => f(view));
  };
  view.jump = (id, reason = "jump") => {
    const node = view.active.find((a) => a.id === controlId(id))?.node
      ?? [...root.querySelectorAll(`[data-control="${CSS.escape(id)}"]`)].find((n) => !hiddenByHost(n, root));
    if (!node) return false;
    const panel = node.closest('[role="tabpanel"]');
    if (panel?.hidden) root.querySelector(`[role="tab"][aria-controls="${CSS.escape(panel.id)}"]`)?.click();
    open?.(node);
    // On a new tab the kept controls go first (see apply).
    view.apply();
    for (let n = node; n && n !== root; n = n.parentElement) {
      if (n.dataset.control && Object.hasOwn(CONTROLS, controlId(n.dataset.control))) view.keep.set(controlId(n.dataset.control), reason);
      if (n.tagName === "DETAILS") n.open = true;
    }
    view.apply();
    // To the middle of its scroll box (the structure page's settings), else
    // just into view (the notebook, where the page itself scrolls).
    let box = node.parentElement;
    while (box && box !== document.body && !(/(auto|scroll)/.test(getComputedStyle(box).overflowY) && box.scrollHeight > box.clientHeight)) {
      box = box.parentElement;
    }
    if (box && box !== document.body) {
      const top = node.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
      box.scrollTop = top - (box.clientHeight - node.getBoundingClientRect().height) / 2;
    } else {
      node.scrollIntoView({ block: "nearest" });
    }
    const focusable = "input:not([disabled]), select:not([disabled]), button:not([disabled]), textarea:not([disabled]), summary, a[href]";
    (node.matches(focusable) ? node : node.querySelector(focusable))?.focus({ preventScroll: true });
    // A short highlight, as for a search result.
    node.classList.remove("profile-jumped");
    void node.offsetWidth;
    node.classList.add("profile-jumped");
    setTimeout(() => node.classList.remove("profile-jumped"), 1600);
    return true;
  };
  view.schedule = () => { if (!frame) frame = requestAnimationFrame(view.apply); };
  view.set = (profile) => {
    const next = validProfile(profile);
    if (next === view.profile) return;
    view.profile = next;
    view.keep.clear();
    view.apply();
    view.listeners.forEach((f) => f(next));
  };
  const observer = new MutationObserver(view.schedule);
  observer.observe(root, { childList: true, subtree: true });
  for (const type of ["input", "change", "click"]) root.addEventListener(type, view.schedule);
  savePrefsListeners.add(view.schedule);
  view.dispose = () => {
    observer.disconnect();
    savePrefsListeners.delete(view.schedule);
    cancelAnimationFrame(frame);
  };
  view.apply();
  return view;
}
// The switch "Simple | Advanced" of a profile view: two radio buttons.
let profileSwitches = 0;
function createProfileSwitch(view) {
  const name = `stoms-profile-${++profileSwitches}`;
  const inputs = Object.entries(PROFILES).map(([value, label]) => {
    const input = el("input", { type: "radio", name, value, checked: value === view.profile, onchange: () => view.set(value) });
    return [input, el("label", { class: "profile-option" }, input, el("span", {}, label))];
  });
  view.listeners.add((profile) => { for (const [input] of inputs) input.checked = input.value === profile; });
  return el("div", { class: "profile-switch", role: "radiogroup", "aria-label": "Controls shown",
    title: "Simple shows the controls most pictures need (and every setting in use); Advanced shows all. Only what is shown changes, never a setting." },
  inputs.map(([, label]) => label));
}
// The count beside the switch, "3 advanced settings active" (in simple, while
// there are any; see activeAdvancedControls): a button that opens the list of
// them (tab › section, label, PROFILE_MARK); choosing one jumps there
// (view.jump). Returns [button, list]: the list goes below the switch's row.
function createProfileCount(view) {
  const listId = `stoms-profile-list-${profileSwitches}`;
  const button = el("button", { type: "button", class: "profile-count", "aria-expanded": "false", "aria-controls": listId, hidden: true,
    title: "Advanced settings that differ from their defaults, shown in Simple with “adv.”: choose one to go to it" });
  const list = el("ul", { class: "profile-count-list", id: listId, "aria-label": "Advanced settings active", hidden: true });
  let shownKey = null;
  const setOpen = (open) => {
    list.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  };
  function render() {
    const active = view.profile === "advanced" ? [] : view.active;
    const text = `${active.length} advanced setting${active.length === 1 ? "" : "s"} active`;
    if (button.textContent !== text) button.textContent = text;
    if (button.hidden !== !active.length) button.hidden = !active.length;
    if (!active.length && !list.hidden) setOpen(false);
    // Rebuilt only when it changes (the profile view watches these elements).
    const items = active.map(({ id, node }) => [id, controlPlace(node, view.root).join(" › "), CONTROLS[id].label]);
    const key = JSON.stringify(items);
    if (key === shownKey) return;
    shownKey = key;
    list.replaceChildren(...items.map(([id, place, label]) => el("li", {},
      el("button", { type: "button", "data-profile-target": id, onclick: () => { setOpen(false); view.jump(id); } },
        place ? el("span", { class: "profile-count-place" }, `${place} › `) : null,
        el("span", {}, label), " ", profileMark()))));
  }
  button.addEventListener("click", () => setOpen(list.hidden));
  list.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { setOpen(false); button.focus(); event.stopPropagation(); }
  });
  // A click elsewhere closes it (the listener goes with the page).
  const outside = (event) => {
    if (!button.isConnected) { document.removeEventListener("pointerdown", outside, true); return; }
    if (!list.hidden && !list.contains(event.target) && !button.contains(event.target)) setOpen(false);
  };
  document.addEventListener("pointerdown", outside, true);
  view.applied.add(render);
  render();
  return [button, list];
}

// ---------------------------------------------------------------- feature search (structure page)

// Why a control of the structure page may not be there, for the search
// results (greyed, with the note). Per reason: the note; where the control
// sits once it is there (place: tab, section, or a box outside the tabs
// marked data-profile-place, or a function of the data giving them; only
// used while it is absent, see controlNeedPlace; a test compares it with the
// real place); has(ctx) (optional): whether the shown data has
// it (see controlContext); after (optional): a reason that must hold first,
// whose note wins while it does not (no modes: no NAC direction either);
// requires (optional): for a reason that is another setting, the control of
// that setting: choosing the greyed result goes there (never changing it);
// controls: the IDs it applies to. Reasons without `requires` (data the
// structure lacks) cannot be chosen. A control missing for another reason
// gets a generic note (CONTROL_SEARCH_NOTES).
const CONTROL_NEEDS = {
  periodic: { note: "needs a periodic cell", place: ["View", "Cell"], has: (ctx) => ctx.periodic,
    controls: ["cell.single-cell", "cell.matrix"] },
  matrix: { note: "only with Transformation matrix on", requires: "cell.matrix", controls: ["cell.matrix-entries", "cell.matrix-preset", "cell.stored-outline"] },
  cell: { note: "needs a cell", place: ["Info", "Cell"], controls: ["info.copy-cell"] },
  storedInfo: { note: "only with stored info", place: ["Info"], controls: ["info.structure-info"] },
  provenance: { note: "only with provenance metadata", place: ["Info"], controls: ["info.provenance"] },
  positions: { note: "not available for this structure", place: ["Info"], controls: ["info.atom-positions"] },
  symmetry: { note: "needs symmetry (spglib)", place: (ctx) => ["Info", ctx.hasCell ? "Structure and lattice" : "Structure"], has: (ctx) => ctx.hasSymmetry,
    controls: ["info.inequivalent-sites", "symmetry.tolerance"] },
  property: { note: "only when colouring by Atomic property", requires: "colour.mode", controls: ["colour.property", "colour.read-as", "colour.range", "colour.symmetric"] },
  vectorProperty: { note: "only for a vector property", requires: "colour.property", controls: ["colour.component"] },
  forceDifference: { note: "only when colouring by force difference", requires: "colour.mode", controls: ["colour.error-pair"] },
  valueColour: { note: "only when colouring by a value", requires: "colour.mode", controls: ["colour.palette"] },
  customPalette: { note: "only with the custom palette", requires: "colour.palette", controls: ["colour.custom-palette"] },
  highlightGroups: { note: "only once colours are applied", place: ["Colour", "Highlight selected atoms"],
    controls: ["highlight.groups", "highlight.remove-all"] },
  measurements: { note: "only with measurements", place: ["Measure", "Measure"], controls: ["measure.list"] },
  measuredPolyhedra: { note: "only with a measured polyhedron", place: ["Measure", "Measure"],
    controls: ["measure.polyhedra-list", "measure.polyhedra-csv", "measure.polyhedra-clear"] },
  measuring: { note: "only while measuring", controls: ["measure.stop"] },
  planes: { note: "only with a plane", place: ["Planes", "Planes"],
    controls: ["planes.show", "planes.colour", "planes.extend", "planes.remove"] },
  millerPlanes: { note: "only with a Miller plane", place: ["Planes", "Planes"], controls: ["planes.miller-indices", "planes.position"] },
  atomPlanes: { note: "only with a plane through atoms", place: ["Planes", "Planes"], controls: ["planes.patch", "planes.fit-text"] },
  picking: { note: "only while picking atoms for a plane", controls: ["planes.make"] },
  rings: { note: "only with Show rings on", requires: "rings.show", controls: ["rings.method", "rings.search-size", "rings.elements", "rings.from-selection",
    "rings.all-atoms", "rings.alternating", "rings.cutoffs", "rings.count", "rings.enclosed", "rings.size-range", "rings.scheme",
    "rings.custom-palette", "rings.opacity", "rings.outline", "rings.labels", "rings.label-size"] },
  ringsFound: { note: "only when rings are found", place: ["Rings"], controls: ["rings.size-colour", "rings.summary-actions"] },
  vectors: { note: "only with several per-atom vectors", controls: ["arrows.vector"] },
  displacements: { note: "only for arrows of displacements", requires: "arrows.source", controls: ["arrows.displacement-reference"] },
  forceSelection: { note: "only with Same as slice off", requires: "forces.follow-slice", controls: ["forces.include-elements", "forces.include-bounds", "forces.include-all"] },
  modes: { note: "needs vibrational modes", place: ["Vibrations"], has: (ctx) => ctx.hasModes,
    controls: ["vibration.q-point", "vibration.mode", "vibration.play", "vibration.record", "vibration.amplitude", "vibration.period",
      "vibration.bonds", "vibration.unit", "vibration.arrows"] },
  video: { note: "needs vibrational modes", place: ["Vibrations", "Video"], has: (ctx) => ctx.hasModes,
    controls: ["vibration.video-periods", "vibration.video-size", "vibration.video-fps"] },
  nacDirection: { note: "only at Γ with NAC data", place: ["Vibrations"], after: "modes", controls: ["vibration.direction"] },
  waveVector: { note: "needs vibrational modes of a periodic structure", place: ["Vibrations"], has: (ctx) => ctx.hasModes && ctx.periodic,
    controls: ["vibration.wave-vector"] },
  waveStyle: { note: "needs vibrational modes of a periodic structure", place: ["Vibrations", "Wave vector arrows"],
    has: (ctx) => ctx.hasModes && ctx.periodic,
    controls: ["vibration.wave-colours", "vibration.wave-styles", "vibration.wave-labels", "vibration.wave-legend"] },
  waveSize: { note: "needs vibrational modes of a periodic structure", place: ["Axes"], has: (ctx) => ctx.hasModes && ctx.periodic,
    controls: ["axes.wave-size"] },
  repeatForQ: { note: "only at a q-point other than Γ", place: ["Vibrations"], after: "modes", controls: ["vibration.apply-repeat"] },
  phonons: { note: "needs phonon data (phonopy)", has: (ctx) => ctx.hasPhonons,
    controls: ["phonon.save-svg", "phonon.side", "phonon.path-slider", "phonon.resize"] },
  nac: { note: "needs NAC data", after: "phonons", controls: ["phonon.nac"] },
  steps: { note: "needs a step list", place: ["Steps"], has: (ctx) => ctx.stepCount > 1,
    controls: ["step.previous-next", "step.picker", "movie.play", "movie.frame-slider", "movie.fps", "movie.loop", "movie.range"] },
  tagPrefix: { note: "only when stepping by tag prefix", place: ["Steps"], requires: "step.source", controls: ["step.prefix"] },
  comparing: { note: "only while comparing", place: ["Compare"], has: (ctx) => ctx.comparing, controls: ["compare.close", "compare.steps-side", "compare.swap"] },
  aggregation: { note: "only when opened from an aggregation", has: (ctx) => ctx.fromAggregation, controls: ["page.selected"] },
  editor: { note: "opens with a right-click on an element below the structure", controls: ["elements.editor"] },
};
const CONTROL_NEED_OF = Object.fromEntries(Object.entries(CONTROL_NEEDS).flatMap(([key, need]) => need.controls.map((id) => [id, key])));
// The generic notes: a control there but hidden by the page, and one not there.
const CONTROL_SEARCH_NOTES = { hidden: "shown only with other settings", absent: "not available for this structure" };
// Where a control missing for reason `need` would sit (CONTROL_NEEDS place).
const controlNeedPlace = (need, ctx) => (typeof need?.place === "function" ? need.place(ctx) : need?.place ?? []);
// The reason control `id` may be missing (CONTROL_NEEDS) under the data in
// `ctx`, or null.
function controlNeed(id, ctx) {
  const need = CONTROL_NEEDS[CONTROL_NEED_OF[controlId(id)]] ?? null;
  const first = need?.after ? CONTROL_NEEDS[need.after] : null;
  return first && first.has?.(ctx) === false ? first : need;
}
// The search entries matching `query` (case-insensitive; each word a part of
// the label, a keyword, or the name of the tab or section, entry.place),
// best first: the whole query at the start of the label, in the label, as a
// keyword, in a keyword, in the place, the words spread out; then entries
// that can be chosen (available) before the rest, then in their order. An
// entry: { label, keywords, place: [...], available }. Pure (tested in Node).
function searchControls(query, entries) {
  const terms = String(query).toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const whole = terms.join(" ");
  const lower = (list) => (list ?? []).map((s) => String(s).toLowerCase());
  return entries.map((entry, index) => {
    const label = String(entry.label).toLowerCase(), keywords = lower(entry.keywords), place = lower(entry.place);
    const fields = [label, ...keywords, ...place];
    if (!terms.every((term) => fields.some((field) => field.includes(term)))) return null;
    const rank = label.startsWith(whole) ? 0 : label.includes(whole) ? 1
      : keywords.includes(whole) ? 2 : keywords.some((k) => k.includes(whole)) ? 3
        : place.some((p) => p.includes(whole)) ? 4 : 5;
    return { entry, rank, index };
  }).filter(Boolean)
    .sort((a, b) => a.rank - b.rank || Number(a.entry.available === false) - Number(b.entry.available === false) || a.index - b.index)
    .map((found) => found.entry);
}
// What the search can offer on the page of `view` (structure page: every
// control but the notebook's own), in the registry's order: { id, label,
// keywords, place, available, hidden (the profile hides it now: "adv."),
// note (why it is not available), jumpTo (for one that needs another
// setting, CONTROL_NEEDS requires: the control of that setting, when the host
// shows it), show (a host function that builds it first) }. A control is
// available where the host shows an element of it; one the host builds only
// when asked (`build(id)` returns a function that does, giving a promise; the
// Info tab) is available unless the data lacks it. Results that are not
// available never carry "adv.".
function controlSearchEntries(view, ctx, build = null) {
  const root = view.root, simple = view.profile !== "advanced";
  const found = new Map();
  for (const node of root.querySelectorAll("[data-control]")) {
    const id = controlId(node.dataset.control);
    if (!Object.hasOwn(CONTROLS, id)) continue;
    const at = found.get(id) ?? { node: null, any: node };
    if (!at.node && !hiddenByHost(node, root)) at.node = node;
    found.set(id, at);
  }
  return Object.entries(CONTROLS).filter(([, control]) => !control.notebookOnly).map(([id, control]) => {
    const at = found.get(id), need = controlNeed(id, ctx);
    const entry = { id, label: control.label, keywords: control.keywords };
    if (at?.node) {
      return { ...entry, available: true, place: controlPlace(at.node, root), hidden: simple && Boolean(at.node.closest("[data-profile-hidden]")) };
    }
    const show = !at && need?.has?.(ctx) !== false ? build?.(id) : null;
    if (show) return { ...entry, available: true, show, place: controlNeedPlace(need, ctx), hidden: profileHides(id, view.profile, ctx) };
    const jumpTo = need?.requires && found.get(need.requires)?.node ? need.requires : null;
    return { ...entry, available: false, jumpTo, place: at ? controlPlace(at.any, root) : controlNeedPlace(need, ctx),
      note: need?.note ?? CONTROL_SEARCH_NOTES[at ? "hidden" : "absent"], hidden: false };
  });
}
// The search field of a profile view (structure page) and its list of
// results: label, tab › section, PROFILE_MARK for controls the profile hides,
// and greyed, with a note, those not there. Choosing one goes there
// (view.jump, reason "search": shown until the tab is left); choosing a
// greyed one that needs another setting goes to that setting's control
// instead (jumpTo; the setting stays as it is); the other greyed ones cannot
// be chosen. Keys in the field: ↓/↑ move among the results that can be
// chosen, Enter chooses (when none is selected: the first available one, else
// the first that goes to another setting), Esc clears and closes (and leaves
// the field when it is already empty). `context()` gives the data (see
// controlContext), `build(id)` the controls the host builds only when asked
// (see controlSearchEntries). Returns { field, list, focus }.
let controlSearches = 0;
function createControlSearch(view, { context, build = null } = {}) {
  const listId = `stoms-control-search-${++controlSearches}`;
  const field = el("input", { type: "search", class: "control-search", id: `${listId}-field`, role: "combobox", autocomplete: "off",
    spellcheck: "false", "aria-autocomplete": "list", "aria-expanded": "false", "aria-controls": listId,
    "aria-label": "Find a control", placeholder: "Find a control  /",
    title: "Find a control by name or keyword, also one the profile hides (press / to come here)" });
  const list = el("ul", { class: "control-search-list", id: listId, role: "listbox", "aria-label": "Controls found", hidden: true });
  let results = [], selected = null, shownKey = null;
  const choosable = (r) => Boolean(r.available || r.jumpTo);
  const setOpen = (open) => {
    if (list.hidden === !open) return;
    list.hidden = !open;
    field.setAttribute("aria-expanded", String(open));
  };
  const optionId = (id) => `${listId}-${id.replace(/[^\w-]/g, "_")}`;
  function select(id) {
    selected = id;
    for (const item of list.querySelectorAll("[role=option]")) item.setAttribute("aria-selected", String(item.dataset.searchResult === id));
    if (id) {
      field.setAttribute("aria-activedescendant", optionId(id));
      list.querySelector(`#${CSS.escape(optionId(id))}`)?.scrollIntoView({ block: "nearest" });
    } else {
      field.removeAttribute("aria-activedescendant");
    }
  }
  function update() {
    if (!field.value.trim()) { results = []; shownKey = null; list.replaceChildren(); select(null); setOpen(false); return; }
    results = searchControls(field.value, controlSearchEntries(view, context(), build));
    // Rebuilt only when it changes (the profile view watches these elements).
    const key = JSON.stringify(results.map((r) => [r.id, r.available, r.jumpTo ?? null, r.place, r.hidden, r.note ?? null]));
    if (key !== shownKey) {
      shownKey = key;
      list.replaceChildren(...(results.length ? results.map((r) => {
        const via = r.jumpTo ? CONTROLS[r.jumpTo].label : null;
        const note = via ? `${r.note}: choose to go to ${via}` : r.note;
        return el("li", {
          role: "option", id: optionId(r.id),
          class: `control-search-result${r.available ? "" : " unavailable"}${r.jumpTo ? " via" : ""}`,
          "data-search-result": r.id, "data-search-via": r.jumpTo, "aria-selected": "false",
          "aria-disabled": choosable(r) ? null : "true", title: note ?? null,
          onclick: choosable(r) ? () => choose(r) : null,
        }, el("span", { class: "control-search-label" }, r.label), r.hidden ? profileMark("hidden") : null,
        r.place.length ? el("span", { class: "control-search-place" }, r.place.join(" › ")) : null,
        note ? el("span", { class: "control-search-note" }, note) : null);
      }) : [el("li", { class: "control-search-none" }, "No control found")]));
      if (!results.some((r) => r.id === selected && choosable(r))) selected = null;
      select(selected);
    }
    setOpen(true);
  }
  async function choose(result) {
    if (!result || !choosable(result)) return;
    setOpen(false);
    // Needs another setting: to that setting's control (never changing it).
    if (!result.available) {
      if (!view.jump(result.jumpTo, "search")) { field.focus(); update(); }
      return;
    }
    await result.show?.();
    // Gone in the meantime (or the host built none): the results say why.
    if (!view.jump(result.id, "search")) { field.focus(); update(); }
  }
  function move(step) {
    const options = results.filter(choosable);
    if (!options.length) return;
    const at = options.findIndex((r) => r.id === selected);
    const next = at < 0 ? (step > 0 ? 0 : options.length - 1) : (at + step + options.length) % options.length;
    select(options[next].id);
  }
  field.addEventListener("input", (event) => {
    // Typing changes no control: no profile pass for it.
    event.stopPropagation();
    selected = null;
    update();
  });
  field.addEventListener("focus", () => { if (field.value.trim()) update(); });
  field.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.hidden) update();
      move(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (list.hidden) update();
      choose(results.find((r) => r.id === selected && choosable(r)) ?? results.find((r) => r.available) ?? results.find(choosable));
    } else if (event.key === "Escape") {
      // Not the page's Escape (closing the element editor, stopping a measurement).
      event.preventDefault();
      event.stopPropagation();
      if (field.value || !list.hidden) { field.value = ""; update(); } else field.blur();
    }
  });
  // A click elsewhere closes it (the listener goes with the page).
  const outside = (event) => {
    if (!field.isConnected) { document.removeEventListener("pointerdown", outside, true); return; }
    if (!list.hidden && !list.contains(event.target) && event.target !== field) setOpen(false);
  };
  document.addEventListener("pointerdown", outside, true);
  view.applied.add(() => { if (!list.hidden) update(); });
  return { field, list, focus: () => { field.focus(); field.select(); } };
}

// The embedded viewer (embed.js) defines STOMS_EMBED before this script: its
// settings come from the page (Python) and never from this browser's storage,
// so a notebook shows the same figure for everyone; `saved` hears of changes.
const embedded = typeof STOMS_EMBED === "object" && STOMS_EMBED !== null;
const viewerPrefs = (() => {
  if (embedded) return normalizePrefs(STOMS_EMBED.settings);
  try { return normalizePrefs(JSON.parse(localStorage.getItem("stoms.viewer") || "{}")); } catch { return defaultPrefs(); }
})();
function savePrefs() {
  savePrefsListeners.forEach((f) => f());
  if (embedded) { STOMS_EMBED.saved?.(); return; }
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

// ---------------------------------------------------------------- first Brillouin zone

// The first Brillouin zone is the Wigner–Seitz cell of the reciprocal lattice
// (vectors n·recip, without 2π as everywhere here): the points k with
// k·G <= |G|²/2 for every lattice vector G. Only the Voronoi-relevant G bound
// it, and each is a shortest vector of its class n mod 2 (Voronoi): those
// shortest vectors (all of them on a tie, which bound it too), from n within
// ±ZONE_SEARCH. Returns [{ n, G }].
const ZONE_SEARCH = 4;
function zoneVectors(recip) {
  const best = new Map();
  for (let i = -ZONE_SEARCH; i <= ZONE_SEARCH; i++) {
    for (let j = -ZONE_SEARCH; j <= ZONE_SEARCH; j++) {
      for (let k = -ZONE_SEARCH; k <= ZONE_SEARCH; k++) {
        if (!i && !j && !k) continue;
        const n = [i, j, k];
        const G = add(add(mul(recip[0], i), mul(recip[1], j)), mul(recip[2], k));
        const length = dot(G, G), key = n.map((x) => ((x % 2) + 2) % 2).join("");
        const entry = best.get(key);
        if (!entry || length < entry.length * (1 - 1e-9)) best.set(key, { length, vectors: [{ n, G }] });
        else if (length <= entry.length * (1 + 1e-9)) entry.vectors.push({ n, G });
      }
    }
  }
  return [...best.values()].flatMap((entry) => entry.vectors);
}

// The point of the first Brillouin zone equivalent to `q` (reduced, along
// a*, b*, c*): { reduced, cartesian } (1/Å without 2π, in the cell's axes).
// On the zone boundary several points are equivalent (q = ½ b₁ and −½ b₁):
// q itself when it is one of them, else the one with the largest reduced
// coordinates (a* first, then b*, then c*).
function firstZonePoint(cell, q) {
  const recip = reciprocal(cell), vectors = zoneVectors(recip);
  const cartesian = (f) => add(add(mul(recip[0], f[0]), mul(recip[1], f[1])), mul(recip[2], f[2]));
  // How far k lies beyond the plane halfway to G, relative to |G|².
  const beyond = (k, G) => (dot(k, G) - dot(G, G) / 2) / dot(G, G);
  const TOLERANCE = 1e-8;
  // Each step to a shorter equivalent point; the lattice is discrete.
  let f = q.map((x) => x - Math.round(x));
  for (let step = 0; step < 1000; step++) {
    const k = cartesian(f);
    let worst = null, most = TOLERANCE;
    for (const v of vectors) {
      const e = beyond(k, v.G);
      if (e > most) { most = e; worst = v; }
    }
    if (!worst) break;
    f = f.map((x, i) => x - worst.n[i]);
  }
  // Every equivalent point on the boundary: steps across the faces it lies on.
  const key = (g) => g.map((x) => x.toFixed(6)).join(",");
  const ties = [f], seen = new Set([key(f)]);
  for (let i = 0; i < ties.length && ties.length < 64; i++) {
    const k = cartesian(ties[i]);
    for (const v of vectors) {
      if (Math.abs(beyond(k, v.G)) > TOLERANCE) continue;
      const g = ties[i].map((x, j) => x - v.n[j]);
      if (!seen.has(key(g))) { seen.add(key(g)); ties.push(g); }
    }
  }
  const same = (a, b) => a.every((x, j) => Math.abs(x - b[j]) < 1e-6);
  const larger = (a, b) => {
    for (let j = 0; j < 3; j++) if (Math.abs(a[j] - b[j]) > 1e-9) return a[j] > b[j];
    return false;
  };
  const reduced = ties.find((g) => same(g, q)) ?? ties.reduce((best, g) => (larger(g, best) ? g : best));
  return { reduced: reduced.map((x) => (Math.abs(x) < 1e-12 ? 0 : x)), cartesian: cartesian(reduced) };
}

// The largest distance from Γ to a point of the first Brillouin zone (a
// corner): 1/Å without 2π. Corners are where three bounding planes meet.
function zoneExtent(cell) {
  const vectors = zoneVectors(reciprocal(cell)).map((v) => v.G);
  const inside = (k) => vectors.every((G) => dot(k, G) <= (dot(G, G) / 2) * (1 + 1e-7));
  let extent = 0;
  for (let a = 0; a < vectors.length; a++) {
    for (let b = a + 1; b < vectors.length; b++) {
      for (let c = b + 1; c < vectors.length; c++) {
        const rows = [vectors[a], vectors[b], vectors[c]];
        const det = dot(rows[0], cross(rows[1], rows[2]));
        if (Math.abs(det) < 1e-9 * norm(rows[0]) * norm(rows[1]) * norm(rows[2])) continue;
        // k with rows[i]·k = |rows[i]|²/2: the reciprocal of `rows` solves it.
        const inverse = reciprocal(rows);
        const k = add(add(mul(inverse[0], dot(rows[0], rows[0]) / 2), mul(inverse[1], dot(rows[1], rows[1]) / 2)),
          mul(inverse[2], dot(rows[2], rows[2]) / 2));
        if (norm(k) > extent && inside(k)) extent = norm(k);
      }
    }
  }
  return extent;
}

// Positions the viewer works with: the stored ones, or with "Wrap atoms into
// cell" each atom moved by a lattice vector so its fractional coordinates lie
// in [0, 1) along the periodic axes (as ASE's Atoms.wrap). Everything shown
// follows them: drawing, bonds, slicing, heights, measurements, picking. The
// Info tab and saved files keep the stored positions.
const wrappedPositions = new WeakMap();
function positionsOf(structure) {
  // Single cell only wraps as well (see SINGLE_CELL_LOCK).
  if (!viewerPrefs.wrap && !viewerPrefs.singleCell) return structure.positions;
  const periodic = [0, 1, 2].map((k) => Boolean(structure.pbc?.[k]) && norm(structure.cell[k]) > 1e-8);
  if (!periodic.some(Boolean)) return structure.positions;
  if (!wrappedPositions.has(structure)) {
    const [A, B, C] = structure.cell, recip = reciprocal(structure.cell);
    wrappedPositions.set(structure, structure.positions.map((p) => {
      const n = fractional(recip, p).map((f, k) => (periodic[k] ? Math.floor(f + 1e-7) : 0));
      return n.some(Boolean) ? sub(p, add(add(mul(A, n[0]), mul(B, n[1])), mul(C, n[2]))) : p;
    }));
  }
  return wrappedPositions.get(structure);
}

function planeNormal(cell, plane) {
  const [ra, rb, rc] = reciprocal(cell);
  return add(add(mul(ra, plane.h), mul(rb, plane.k)), mul(rc, plane.l));
}

function dSpacing(cell, plane) {
  const g = norm(planeNormal(cell, plane));
  return g ? 1 / g : null;
}

// Polygon where h*x + k*y + l*z = t (fractional, of the stored cell) cuts the
// box [0,na]x[0,nb]x[0,nc], or with a 3×3 `box` the parallelepiped spanned by
// its rows (fractional; the cell of a transformation matrix). The plane is a
// Miller plane { h, k, l, t } or a Cartesian one { point, normal } (Å; the
// plane through atoms, see atomPlaneFit).
function planePolygon(cell, plane, box) {
  const cartesian = Array.isArray(plane.normal);
  const n = cartesian ? unit(plane.normal) : null;
  // h, k, l of a Cartesian plane: its unit normal along a, b and c (Å).
  const [h, k, l] = cartesian ? [0, 1, 2].map((j) => dot(n, cell[j])) : [plane.h, plane.k, plane.l];
  const level = cartesian ? dot(n, plane.point) : plane.t;
  const g = (f) => h * f[0] + k * f[1] + l * f[2];
  const rows = Array.isArray(box[0]) ? box : diagonalMatrix(box);
  const corners = [];
  for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) {
    corners.push([0, 1, 2].map((x) => i * rows[0][x] + j * rows[1][x] + k * rows[2][x]));
  }
  const found = [];
  const pushUnique = (f) => { if (!found.some((q) => Math.abs(q[0] - f[0]) + Math.abs(q[1] - f[1]) + Math.abs(q[2] - f[2]) < 1e-6)) found.push(f); };
  for (let m = 0; m < 8; m++) for (let n = m + 1; n < 8; n++) {
    const p = corners[m], q = corners[n];
    if (![1, 2, 4].includes(m ^ n)) continue; // only box edges
    const gp = g(p) - level, gq = g(q) - level;
    if (Math.abs(gp) < 1e-9) pushUnique(p);
    if (Math.abs(gq) < 1e-9) pushUnique(q);
    if (gp * gq < 0) pushUnique(add(p, mul(sub(q, p), gp / (gp - gq))));
  }
  if (found.length < 3) return null;
  const points = found.map((f) => add(add(mul(cell[0], f[0]), mul(cell[1], f[1])), mul(cell[2], f[2])));
  const normal = cartesian ? n : unit(planeNormal(cell, plane));
  const centre = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  const u = unit(sub(points[0], centre)), v = cross(normal, u);
  const angle = (p) => Math.atan2(dot(sub(p, centre), v), dot(sub(p, centre), u));
  points.sort((p, q) => angle(p) - angle(q));
  return { points, normal, centre };
}

// ---------------------------------------------------------------- planes through atoms

// A plane through atoms (an entry of viewerPrefs.planes with `atoms`):
//   { atoms: [ref, ...] (3 or more, see measureState), show, colour, patch, scale? }
// Like measurements it names atoms by index and periodic image, so it follows
// frames and compared structures with the same atoms. Three atoms give the
// plane through them, more the least-squares plane. It is drawn where it cuts
// the shown region (the repeat or the transformation matrix's cell, as Miller
// planes), or with `patch` (and always without a cell, or when it misses the
// shown region) as a patch around the atoms, PATCH_MARGIN Å wider.
// (MIN_PLANE_ATOMS, PATCH_MARGIN, isAtomRef: see normalizePrefs.)

// The plane through the atoms `refs` of `structure` (all fitting it): the
// least-squares plane through their centroid `point`, its unit `normal`, the
// RMS and largest distance of the atoms from it (Å) and their positions; null
// when the atoms lie on a line. The normal points to the side the surface
// normal points to (up for a slab; see viewFrame), or, for a plane along it,
// by the right-hand rule of the first three atoms.
function atomPlaneFit(structure, refs) {
  const positions = refs.map((r) => refPosition(structure, r));
  if (positions.length < MIN_PLANE_ATOMS) return null;
  const point = mul(positions.reduce(add, [0, 0, 0]), 1 / positions.length);
  const S = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (const p of positions) {
    const d = sub(p, point);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) S[i][j] += d[i] * d[j];
  }
  const [, second, smallest] = symmetricEigenvectors(S);
  // On a line: no spread across the line either.
  const spread = (axis) => positions.reduce((total, p) => total + dot(sub(p, point), axis) ** 2, 0) / positions.length;
  if (!(spread(second) > 1e-8)) return null;
  let normal = unit(smallest);
  const up = surfaceNormal(structure), side = dot(normal, up);
  const turn = Math.abs(side) > 1e-6 ? side
    : dot(normal, cross(sub(positions[1], positions[0]), sub(positions[2], positions[0])));
  if (turn < 0) normal = mul(normal, -1);
  const distances = positions.map((p) => dot(sub(p, point), normal));
  const rms = Math.sqrt(distances.reduce((total, d) => total + d * d, 0) / distances.length);
  return { point, normal, rms, max: Math.max(...distances.map(Math.abs)), positions };
}

// Patch around `positions` in the plane { point, normal }: their convex hull
// in the plane, each corner PATCH_MARGIN further from the centre.
function planePatch(positions, { point, normal }) {
  const u = unit(Math.abs(normal[0]) < 0.9 ? cross(normal, [1, 0, 0]) : cross(normal, [0, 1, 0])), v = cross(normal, u);
  const flat = positions.map((p) => { const d = sub(p, point); return [dot(d, u), dot(d, v)]; })
    .sort((p, q) => p[0] - q[0] || p[1] - q[1]);
  // Monotone chain.
  const turn = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list) => {
    const chain = [];
    for (const p of list) {
      while (chain.length >= 2 && turn(chain[chain.length - 2], chain[chain.length - 1], p) <= 1e-12) chain.pop();
      chain.push(p);
    }
    chain.pop();
    return chain;
  };
  const hull = [...half(flat), ...half([...flat].reverse())];
  if (hull.length < 3) return null;
  const middle = mul(hull.reduce((m, p) => [m[0] + p[0], m[1] + p[1]], [0, 0]), 1 / hull.length);
  const points = hull.map((p) => {
    const d = [p[0] - middle[0], p[1] - middle[1]], length = Math.hypot(...d) || 1;
    const q = [p[0] + (d[0] / length) * PATCH_MARGIN, p[1] + (d[1] / length) * PATCH_MARGIN];
    return add(point, add(mul(u, q[0]), mul(v, q[1])));
  });
  const centre = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  return { points, normal, centre };
}

// The polygon of a plane through atoms on `structure` (see above), or null
// when its atoms do not fit the structure or lie on a line. `box` as for
// planePolygon. `patch` in the result says whether it is a patch.
function atomPlanePolygon(structure, plane, box) {
  if (!fitsStructure(structure, plane.atoms)) return null;
  const fit = atomPlaneFit(structure, plane.atoms);
  if (!fit) return null;
  const [A, B, C] = structure.cell, hasVolume = Math.abs(dot(A, cross(B, C))) > 1e-9;
  const cut = plane.patch || !hasVolume ? null : planePolygon(structure.cell, fit, box);
  if (cut) return { ...cut, patch: false };
  const patch = planePatch(fit.positions, fit);
  return patch && { ...patch, patch: true };
}

// `polygon` ({ points, normal, centre, ... }) extended by `scale` in all
// in-plane directions: each corner p moves to centre + scale·(p − centre).
// Scale 1 (or none) returns the polygon itself.
function scalePolygon(polygon, scale) {
  if (!polygon || scale === undefined || scale === 1) return polygon;
  const { centre } = polygon;
  return { ...polygon, points: polygon.points.map((p) => add(centre, mul(sub(p, centre), scale))) };
}

// Fractional coordinates of `cell` within [0, 1] (tolerance 1e-6) along its
// periodic axes `periodic`: whether a point (Å) lies inside the stored cell.
const IN_CELL_TOLERANCE = 1e-6;
const insideCell = (recip, periodic) => (p) => fractional(recip, p)
  .every((f, k) => !periodic[k] || (f >= -IN_CELL_TOLERANCE && f <= 1 + IN_CELL_TOLERANCE));

// `polygon` ({ points, normal, centre, ... }, a convex plane polygon) clipped
// to the stored cell, fractional coordinates 0 to 1 along a, b and c, for
// "Single cell only"; null when nothing of it is left. A cell without volume
// leaves the polygon as it is (planes need a cell to be cut anyway).
function clipToCell(polygon, cell) {
  if (!polygon) return polygon;
  const [A, B, C] = cell;
  if (!(Math.abs(dot(A, cross(B, C))) > 1e-9)) return polygon;
  const recip = reciprocal(cell);
  let corners = polygon.points.map((p) => ({ p, f: fractional(recip, p) }));
  // Sutherland–Hodgman against the six faces f_k = 0 and f_k = 1.
  for (let k = 0; k < 3; k++) {
    for (const [side, bound] of [[1, 0], [-1, 1]]) {
      const inside = (q) => side * (q.f[k] - bound) >= -1e-9;
      const kept = [];
      corners.forEach((q, i) => {
        const r = corners[(i + 1) % corners.length];
        if (inside(q)) kept.push(q);
        if (inside(q) !== inside(r)) {
          const t = (bound - q.f[k]) / (r.f[k] - q.f[k]);
          kept.push({ p: add(q.p, mul(sub(r.p, q.p), t)), f: q.f.map((v, j) => (j === k ? bound : v + t * (r.f[j] - v))) });
        }
      });
      corners = kept;
      if (corners.length < 3) return null;
    }
  }
  const points = corners.map((q) => q.p);
  return { ...polygon, points, centre: mul(points.reduce(add, [0, 0, 0]), 1 / points.length) };
}

// A plane as a measurement keeps it: a Miller plane { h, k, l, t } or a
// plane through atoms { atoms: [ref] } (without show, colour or patch).
const planeDefinition = (plane) => (isAtomPlane(plane) ? { atoms: plane.atoms.map(copyRef) }
  : { h: plane.h, k: plane.k, l: plane.l, t: plane.t });
const refName = (r) => `${r.symbol}${r.index}${r.image.some(Boolean) ? "′" : ""}`;
function planeName(plane) {
  if (!isAtomPlane(plane)) return `(${plane.h} ${plane.k} ${plane.l})`;
  const names = plane.atoms.slice(0, 4).map(refName).join(" ");
  return `plane ${names}${plane.atoms.length > 4 ? ` … (${plane.atoms.length} atoms)` : ""}`;
}
// A plane on `structure` as { point, normal (unit), rms? }, or null (atoms
// that do not fit, on a line; a Miller plane without a cell).
function planeGeometry(structure, plane) {
  if (isAtomPlane(plane)) return fitsStructure(structure, plane.atoms) ? atomPlaneFit(structure, plane.atoms) : null;
  const d = dSpacing(structure.cell, plane);
  if (!d || !(plane.h || plane.k || plane.l)) return null;
  const normal = unit(planeNormal(structure.cell, plane));
  return { point: mul(normal, plane.t * d), normal };
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
  return positionsOf(structure).map((p, i) => !hidden.has(structure.symbols[i]) && inSlice(fractional(recip, p), bounds));
}

const drawsBonds = (prefs = viewerPrefs) => (prefs.style === "stick" || prefs.style === "wireframe" ? true
  : prefs.style === "space-filling" ? false : prefs.bonds);
const drawsPolyhedra = (prefs = viewerPrefs) => prefs.style !== "space-filling" && prefs.polyhedra;

// Automatic sphere radius (Angstrom) for the style and radius type. Space-
// filling draws the radius type's table radius exactly; atomScale scales it
// only in ball-and-stick (stick and wireframe atoms take the bond radius).
function autoRadius(symbol) {
  const prefs = viewerPrefs;
  if (prefs.style === "stick" || prefs.style === "wireframe") return prefs.appearance.bondRadius;
  const radius = typedRadius(symbol, prefs.radiusType);
  if (prefs.style === "space-filling") return radius;
  const ballAndStick = prefs.bonds || prefs.polyhedra;
  return Math.max(0.18, radius * (ballAndStick ? 0.33 : 0.5)) * prefs.appearance.atomScale;
}
// The radius an atom is drawn, picked and measured with: a radius set per
// element (appearance.radii) wins in every style but space-filling, which
// always shows the table's radii. Stored settings are untouched, so another
// style brings the per-element radii back.
const atomRadius = (symbol) => (viewerPrefs.style === "space-filling" ? autoRadius(symbol)
  : viewerPrefs.appearance.radii[symbol] ?? autoRadius(symbol));
// Names of the styles and radius types in the controls.
const STYLE_LABELS = { "ball-and-stick": "Ball and stick", "space-filling": "Space-filling", stick: "Stick", wireframe: "Wireframe" };
const RADIUS_TYPE_LABELS = { covalent: "Covalent", vdw: "Van der Waals", ionic: "Ionic (Shannon)" };
// Why a setting does nothing in the current style (null: it applies); the
// controls are disabled with this as their tooltip.
function styleLocks(prefs = viewerPrefs) {
  const thin = prefs.style === "stick" || prefs.style === "wireframe";
  const filling = prefs.style === "space-filling";
  return {
    bonds: filling ? "Space-filling draws no bonds" : thin ? "Stick and wireframe always draw bonds" : null,
    polyhedra: filling ? "Space-filling draws no polyhedra" : null,
    // Showing or hiding polyhedron centres needs drawn polyhedra.
    polyhedraCentres: filling ? "Space-filling draws no polyhedra" : !prefs.polyhedra ? "Polyhedra are off" : null,
    radiusType: thin ? "Stick and wireframe atoms take the bond radius" : null,
    // The atom size factor applies only to ball-and-stick; per-element radii
    // to every style but space-filling (see autoRadius, atomRadius).
    atomScale: filling ? "Space-filling uses the true radii" : thin ? "Stick and wireframe atoms take the bond radius" : null,
    elementRadii: filling ? "Space-filling uses the true radii" : null,
  };
}

// ---------------------------------------------------------------- measurements

// Measurements name atoms by index and periodic image, so they apply to every
// structure with the same atoms: compared panels, movie frames, stepping.
//   atom ref: { index, image: [i, j, k], symbol, count } (count: atoms in the structure)
//   item:     { kind: "position" | "distance" | "angle" | "dihedral", atoms: [ref, ...] }
//             { kind: "plane-angle", atoms: [], planes: [plane, plane] }
//             { kind: "plane-distance", atoms: [ref], planes: [plane] }
//             (plane: see planeDefinition; kept as it was when measured)
//   polyhedra: atom refs of polyhedron centres (mode "polyhedron", see polyhedronOf)
// Mode "plane" collects atoms (pending) for a plane through atoms (Planes tab).
const MEASURE_ATOMS = { position: 1, distance: 2, angle: 3, dihedral: 4, "plane-distance": 1 };
const MEASURE_PLANES = { "plane-angle": 2, "plane-distance": 1 };
const measureState = { mode: "off", pending: [], items: [], polyhedra: [] };
// Every atom a measurement depends on (its atoms and its planes' atoms).
const measureRefs = (item) => [...item.atoms, ...(item.planes ?? []).flatMap((p) => p.atoms ?? [])];
// Measurements from Python, a settings file or a copied page, as kept in
// measureState.items; anything else is dropped.
function validMeasurements(items) {
  const validPlane = (p) => (isAtomPlane(p) ? p.atoms.length >= MIN_PLANE_ATOMS && p.atoms.every(isAtomRef)
    : Boolean(p) && [p.h, p.k, p.l].every(Number.isInteger) && Boolean(p.h || p.k || p.l) && Number.isFinite(p.t ?? 0));
  return (Array.isArray(items) ? items : [])
    .filter((item) => item && typeof item.kind === "string" && (Object.hasOwn(MEASURE_ATOMS, item.kind) || Object.hasOwn(MEASURE_PLANES, item.kind)))
    .filter((item) => Array.isArray(item.atoms) && item.atoms.length === (MEASURE_ATOMS[item.kind] ?? 0) && item.atoms.every(isAtomRef)
      && (!MEASURE_PLANES[item.kind] || (Array.isArray(item.planes) && item.planes.length === MEASURE_PLANES[item.kind] && item.planes.every(validPlane))))
    .map((item) => {
      const copy = { kind: item.kind, atoms: item.atoms.map(copyRef) };
      if (MEASURE_PLANES[item.kind]) copy.planes = item.planes.map((p) => planeDefinition(isAtomPlane(p) ? p : { ...p, t: p.t ?? 0 }));
      return copy;
    });
}
// Atom colours: groups of atoms ({ colour, atoms: [ref] }) drawn in their own
// colour over any colour mode, by atom number like measurements. `selected`
// holds the atoms clicked in mode "select" for the next group; `colour` is the
// last colour applied.
const paintState = { selected: [], groups: [], colour: "#d6336c" };

// Only structures with the same atom count and elements: otherwise an index
// can name a different atom.
const fitsStructure = (structure, refs) =>
  refs.every((r) => r.count === structure.symbols.length && structure.symbols[r.index] === r.symbol);

// A Cartesian position as shown in the tooltip and by a position measurement.
const positionText = (p) => `(${p.map((x) => (Math.abs(x) < 5e-4 ? 0 : x).toFixed(3)).join(", ")}) Å`;

function refPosition(structure, ref) {
  const [A, B, C] = structure.cell;
  const shift = add(add(mul(A, ref.image[0]), mul(B, ref.image[1])), mul(C, ref.image[2]));
  return add(positionsOf(structure)[ref.index], shift);
}

// Value of a measurement on one structure: an atom's Cartesian position
// (x, y, z in Angstrom, of the clicked copy; value is the vector), distance in Angstrom (and the
// nearest periodic image's, if shorter), angle at the middle atom, dihedral;
// the angle between two planes (0 to 90°), an atom's signed distance from a
// plane along its normal (with `points`: the atom and its foot on the plane).
// Null when a plane cannot be placed on this structure.
function measureValue(structure, item) {
  if (MEASURE_PLANES[item.kind]) {
    const planes = item.planes.map((plane) => planeGeometry(structure, plane));
    if (planes.some((g) => !g)) return null;
    if (item.kind === "plane-angle") {
      const cos = Math.min(1, Math.abs(dot(planes[0].normal, planes[1].normal)));
      const value = (Math.acos(cos) * 180) / Math.PI;
      return { value, text: `${value.toFixed(1)}°` };
    }
    const p = refPosition(structure, item.atoms[0]), { point, normal } = planes[0];
    const value = dot(sub(p, point), normal);
    // (No "-0.000" for an atom in the plane.)
    return { value, text: `${(Math.abs(value) < 5e-4 ? 0 : value).toFixed(3)} Å`, points: [p, sub(p, mul(normal, value))] };
  }
  const p = item.atoms.map((r) => refPosition(structure, r));
  if (item.kind === "position") {
    return { value: p[0], text: positionText(p[0]), points: p };
  }
  if (item.kind === "distance") {
    const value = norm(sub(p[1], p[0]));
    let nearest = value;
    const [A, B, C] = structure.cell;
    const ranges = structure.pbc.map((periodic) => (periodic ? [-1, 0, 1] : [0]));
    // Nearest image of the second atom's original position.
    const base = positionsOf(structure)[item.atoms[1].index];
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

// ---------------------------------------------------------------- displacements

// Displacement of every atom of s from the same atom of the reference `ref`
// (same number of atoms, elements in the same order), in Angstrom: along the
// periodic axes the shortest over periodic images (minimum image), so an atom
// that crossed a cell face gets a short arrow. When the cells differ (a cell
// relaxation), the reference's fractional coordinates along the periodic axes
// are taken in the cell of s, so a homogeneous strain moves no atom
// (cellsDiffer says so). Stored positions: wrapping moves no atom.
//   result: { vectors, magnitudes, rmsd, max, maxIndex, cellsDiffer } or { error }
function displacementOf(s, ref) {
  const n = s.symbols.length;
  if (ref.symbols.length !== n) return { error: `the reference has ${ref.symbols.length} atoms, this structure ${n}` };
  if (ref.symbols.some((symbol, i) => symbol !== s.symbols[i])) return { error: "the reference has its elements in another order" };
  const volume = (cell) => Math.abs(dot(cell[0], cross(cell[1], cell[2])));
  const periodic = [0, 1, 2].map((k) => Boolean(s.pbc?.[k]));
  const usable = periodic.some(Boolean) && volume(s.cell) > 1e-9 && volume(ref.cell) > 1e-9;
  const cellsDiffer = usable && s.cell.some((row, k) => periodic[k] && row.some((v, j) => Math.abs(v - ref.cell[k][j]) > 1e-6));
  const recip = usable ? reciprocal(s.cell) : null, refRecip = cellsDiffer ? reciprocal(ref.cell) : null;
  const vectors = s.positions.map((p, i) => {
    let q = ref.positions[i];
    if (!usable) return sub(p, q);
    if (cellsDiffer) {
      const g = fractional(refRecip, q);
      for (let k = 0; k < 3; k++) if (periodic[k]) q = add(q, mul(sub(s.cell[k], ref.cell[k]), g[k]));
    }
    let d = sub(p, q);
    const f = fractional(recip, d);
    for (let k = 0; k < 3; k++) if (periodic[k] && Math.round(f[k])) d = sub(d, mul(s.cell[k], Math.round(f[k])));
    return d;
  });
  const magnitudes = vectors.map(norm);
  let maxIndex = -1;
  magnitudes.forEach((m, i) => { if (maxIndex < 0 || m > magnitudes[maxIndex]) maxIndex = i; });
  const rmsd = n ? Math.sqrt(magnitudes.reduce((total, m) => total + m * m, 0) / n) : 0;
  return { vectors, magnitudes, rmsd, max: maxIndex >= 0 ? magnitudes[maxIndex] : 0, maxIndex, cellsDiffer };
}

const displacementReferenceText = (settings = viewerPrefs.displacement) => ({
  compared: "the compared structure", first: "the first frame", previous: "the previous frame", frame: `frame ${settings.frame + 1}`,
})[settings.reference];

// The reference structure of s, from the page that shows s (the structure
// page or embed.js set this): { reference } (s itself when s is the
// reference: zero displacements) or { reference: null, reason }.
let displacementReference = async () => ({ reference: null, reason: "No reference structure." });

// Displacements of s from its reference (displacementOf), or { reason } when
// there are none.
async function displacementFor(s) {
  const { reference, reason } = await displacementReference(s);
  if (!reference) return { reason: reason ?? null };
  const d = displacementOf(s, reference);
  return d.error ? { reason: `No displacements: ${d.error}.` } : d;
}

// Controls for the reference (both viewers). `compared` offers the compared
// structure; `count()` is the number of frames or step-list entries (null
// while unknown), the largest frame number.
function createDisplacementControls({ compared, count, onChange }) {
  const labels = { compared: "The compared structure", first: "The first frame", previous: "The previous frame", frame: "Frame number" };
  const select = el("select", { "aria-label": "Displacement reference" },
    DISPLACEMENT_REFERENCES.filter((r) => compared || r !== "compared").map((r) => el("option", { value: r }, labels[r])));
  const frameInput = el("input", { type: "number", min: 1, step: 1, class: "num-input", "aria-label": "Reference frame number" });
  const sync = () => {
    const settings = viewerPrefs.displacement;
    select.value = settings.reference;
    frameInput.value = settings.frame + 1;
    frameInput.hidden = settings.reference !== "frame";
    const n = count();
    if (n) frameInput.max = n; else frameInput.removeAttribute("max");
  };
  select.addEventListener("change", () => { viewerPrefs.displacement.reference = select.value; sync(); savePrefs(); onChange(); });
  frameInput.addEventListener("change", () => {
    let value = Math.round(Number(frameInput.value));
    if (!Number.isFinite(value) || value < 1) value = 1;
    const n = count();
    if (n) value = Math.min(value, n);
    viewerPrefs.displacement.frame = value - 1; sync(); savePrefs(); onChange();
  });
  sync();
  return { element: el("div", { class: "inline-fields", "data-control": "arrows.displacement-reference" }, el("span", { class: "muted" }, "Reference"), select, frameInput), sync };
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
    enclosed: prefs.enclosed, max_size: prefs.searchSize,
    // Height windows refer to the positions shown: the server wraps as well.
    ...(positionsOf(s) !== s.positions ? { wrap: true } : {}) };
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
// ---------------------------------------------------------------- symmetry

// Space group, Wyckoff letters and equivalent atoms (stoms.analysis.symmetry)
// of structure s at viewerPrefs.symmetry.tolerance. The ledger server
// computes them on request (structure.symmetry_available says whether it
// can: spglib is an optional extra); the notebook embeds them in the frames
// (s.symmetry; absent without spglib) and asks Python for other tolerances.
// A result: { available, applicable, reason, international, number,
// crystal_system, tolerance, wyckoffs, site_symmetries, equivalent_atoms }.
const SYMMETRY_INSTALL = 'Symmetry needs the optional extra stoms[symmetry]: pip install "stoms[symmetry]" (or uvx --from "stoms[symmetry]" stoms …)';
const symmetryAvailable = (s) => Boolean(s) && (s.symmetry_available === true || (s.symmetry != null && s.symmetry.available !== false));
// The structure page loads symmetry for tooltips by itself up to this many
// atoms (larger cells: when the Info tab or equivalent-site colours need it).
const SYMMETRY_AUTO_ATOMS = 1000;
const symmetryCache = new Map();
const symmetryResolved = new Map();
const symmetryKey = (s) => `${s.id}|${viewerPrefs.symmetry.tolerance}`;
function loadSymmetry(s) {
  if (!symmetryAvailable(s)) return Promise.resolve(null);
  const tolerance = viewerPrefs.symmetry.tolerance;
  const embedded = s.symmetry;
  if (embedded && !embedded.deferred && embedded.tolerance === tolerance) return Promise.resolve(embedded);
  const key = symmetryKey(s);
  if (!symmetryCache.has(key)) {
    if (symmetryCache.size > 2000) { symmetryCache.clear(); symmetryResolved.clear(); }
    const load = api(`structures/${encodeURIComponent(s.id)}/symmetry?tolerance=${tolerance}`).then((data) => {
      symmetryResolved.set(key, data);
      return data;
    });
    load.catch(() => symmetryCache.delete(key));
    symmetryCache.set(key, load);
  }
  return symmetryCache.get(key);
}
// The symmetry of s if known now (embedded or loaded), else null.
function symmetryNow(s) {
  if (!symmetryAvailable(s)) return null;
  const embedded = s.symmetry;
  if (embedded && !embedded.deferred && embedded.tolerance === viewerPrefs.symmetry.tolerance) return embedded;
  return symmetryResolved.get(symmetryKey(s)) ?? null;
}
// Whether a result has per-atom data for s (Wyckoff letters, sites).
const symmetrySites = (sym, s) => Boolean(sym?.equivalent_atoms?.length) && sym.equivalent_atoms.length === s.symbols.length;
// Space group as "Fd-3m (227)", or what stands in its place.
function spaceGroupText(sym) {
  if (!sym) return "–";
  if (sym.error) return "–";
  if (sym.available === false) return "–";
  if (sym.applicable === false) return "not applicable";
  if (sym.number == null) return "none found";
  return `${sym.international} (${sym.number})`;
}
// One label per atom naming its symmetry-equivalent site: the element, a
// number per element (in the order of the atoms) and the Wyckoff letter,
// such as "O2 (f)".
function siteLabels(sym, s) {
  const names = new Map();
  const counts = {};
  return sym.equivalent_atoms.map((first) => {
    if (!names.has(first)) {
      const symbol = s.symbols[first];
      counts[symbol] = (counts[symbol] ?? 0) + 1;
      names.set(first, `${symbol}${counts[symbol]} (${sym.wyckoffs[first]})`);
    }
    return names.get(first);
  });
}
// The inequivalent sites of s: { label, symbol, wyckoff, site, atoms }.
function symmetrySiteList(sym, s) {
  const labels = siteLabels(sym, s);
  const sites = new Map();
  sym.equivalent_atoms.forEach((first, i) => {
    if (!sites.has(first)) {
      sites.set(first, { label: labels[i], symbol: s.symbols[first], wyckoff: sym.wyckoffs[first], site: sym.site_symmetries[first], atoms: [] });
    }
    sites.get(first).atoms.push(i);
  });
  return [...sites.values()];
}

const ringShown = (ring) => {
  const { minSize, maxSize } = viewerPrefs.rings;
  return (minSize === null || ring.size >= minSize) && (maxSize === null || ring.size <= maxSize);
};

// ---------------------------------------------------------------- scene model

const neighbourCache = new Map();

// The lattice the bond search runs over: the periodic axes (pbc and a
// non-zero cell vector), and reciprocal vectors of the cell with each
// non-periodic axis replaced by a unit vector perpendicular to the periodic
// ones (so slabs with c = 0 and wires have them too). |recip[k]| is
// 1 / the cell's width perpendicular to the other two axes. Null without
// periodic axes or when the periodic vectors are not independent.
// stoms.analysis.polyhedra._search_lattice is the same.
function searchLattice(structure) {
  const cell = structure.cell;
  const periodic = [0, 1, 2].map((k) => Boolean(structure.pbc?.[k]) && norm(cell[k]) > 1e-8);
  const count = periodic.filter(Boolean).length;
  if (!count) return null;
  const basis = cell.map((v, k) => (periodic[k] ? v : null));
  if (count === 2) {
    const k = periodic.indexOf(false);
    basis[k] = unit(cross(basis[(k + 1) % 3], basis[(k + 2) % 3]));
  } else if (count === 1) {
    const k = periodic.indexOf(true), u = unit(cell[k]);
    const helper = Math.abs(u[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
    const v = unit(cross(u, helper));
    basis[(k + 1) % 3] = v;
    basis[(k + 2) % 3] = cross(u, v);
  }
  const volume = Math.abs(dot(basis[0], cross(basis[1], basis[2])));
  if (!(volume > 1e-8 * norm(basis[0]) * norm(basis[1]) * norm(basis[2]))) return null;
  const recip = reciprocal(basis);
  return { periodic, recip, inverseWidth: recip.map(norm) };
}

// Directed neighbour pairs (i -> j + periodic offset) within the pair cutoffs
// (maximum lengths) and at least the pair minimums. Every periodic image within
// the cutoff is searched, also further than one cell away when a cutoff
// exceeds the cell's perpendicular width: for each pair only the images
// n with |f_j − f_i + n|·width < cutoff along each axis.
function neighbours(structure, cutoffs, minimums = {}) {
  const symbols = structure.symbols;
  const species = [...new Set(symbols)];
  const P = positionsOf(structure);
  const lattice = searchLattice(structure);
  const table = (map) => species.map((a) => species.map((b) => Number(map[pairKey(a, b)]) || 0));
  const cut = table(cutoffs), low = table(minimums);
  const longest = Math.max(0, ...cut.flat());
  // Images searched along each axis at most (beyond the nearest one).
  const reach = lattice ? lattice.inverseWidth.map((g, k) => (lattice.periodic[k] ? Math.ceil(longest * g) : 0)) : [0, 0, 0];
  // The key holds everything the result depends on: the cell (with the
  // cutoffs it sets the image range searched), the range itself, wrapping.
  const key = [structure.id, P === structure.positions ? "" : "wrapped", structure.cell.flat().join(","), structure.pbc.join(","),
    cut.map((r) => r.join(",")).join(";"), low.map((r) => r.join(",")).join(";"), reach.join(",")].join("|");
  if (neighbourCache.has(key)) return neighbourCache.get(key);
  const index = symbols.map((s) => species.indexOf(s));
  const [A, B, C] = structure.cell;
  const bonds = [];
  const found = (i, j, n0, n1, n2, c2, m2) => {
    const vx = A[0] * n0 + B[0] * n1 + C[0] * n2, vy = A[1] * n0 + B[1] * n1 + C[1] * n2, vz = A[2] * n0 + B[2] * n1 + C[2] * n2;
    const dx = P[j][0] + vx - P[i][0], dy = P[j][1] + vy - P[i][1], dz = P[j][2] + vz - P[i][2];
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 < c2 && d2 >= m2) bonds.push({ i, j, off: [n0, n1, n2], to: [P[j][0] + vx, P[j][1] + vy, P[j][2] + vz] });
  };
  if (!lattice) {
    // No usable lattice: the ±1 images of the periodic axes.
    const ranges = structure.pbc.map((periodic) => (periodic ? [-1, 0, 1] : [0]));
    for (let i = 0; i < P.length; i++) for (let j = 0; j < P.length; j++) {
      const c = cut[index[i]][index[j]];
      if (!c) continue;
      for (const n0 of ranges[0]) for (const n1 of ranges[1]) for (const n2 of ranges[2]) {
        if (i !== j || n0 || n1 || n2) found(i, j, n0, n1, n2, c * c, low[index[i]][index[j]] ** 2);
      }
    }
  } else {
    const { periodic, recip, inverseWidth } = lattice;
    const n = P.length, ns = species.length;
    // Fractional coordinates (0 along non-periodic axes), and per element pair
    // the cutoff in fractional units along each axis (0 when not periodic).
    const F = new Float64Array(3 * n);
    P.forEach((p, i) => { for (let k = 0; k < 3; k++) F[3 * i + k] = periodic[k] ? dot(p, recip[k]) : 0; });
    const R = new Float64Array(3 * ns * ns), C2 = new Float64Array(ns * ns), M2 = new Float64Array(ns * ns);
    for (let a = 0; a < ns; a++) for (let b = 0; b < ns; b++) {
      const c = cut[a][b], ab = a * ns + b;
      C2[ab] = c * c; M2[ab] = low[a][b] ** 2;
      // |f + n| · width < c, with a little slack for rounding.
      for (let k = 0; k < 3; k++) R[3 * ab + k] = periodic[k] ? c * inverseWidth[k] + 1e-9 : 0;
    }
    for (let i = 0; i < n; i++) {
      const fi0 = F[3 * i], fi1 = F[3 * i + 1], fi2 = F[3 * i + 2], row = index[i] * ns;
      for (let j = 0; j < n; j++) {
        const ab = row + index[j];
        const c2 = C2[ab];
        if (!c2) continue;
        // Images n along each axis with |f_j − f_i + n| < r (none: next pair).
        const f0 = F[3 * j] - fi0, r0 = R[3 * ab];
        const lo0 = Math.ceil(-f0 - r0), hi0 = Math.floor(-f0 + r0);
        if (lo0 > hi0) continue;
        const f1 = F[3 * j + 1] - fi1, r1 = R[3 * ab + 1];
        const lo1 = Math.ceil(-f1 - r1), hi1 = Math.floor(-f1 + r1);
        if (lo1 > hi1) continue;
        const f2 = F[3 * j + 2] - fi2, r2 = R[3 * ab + 2];
        const lo2 = Math.ceil(-f2 - r2), hi2 = Math.floor(-f2 + r2);
        if (lo2 > hi2) continue;
        const m2 = M2[ab];
        for (let n0 = lo0; n0 <= hi0; n0++) for (let n1 = lo1; n1 <= hi1; n1++) for (let n2 = lo2; n2 <= hi2; n2++) {
          if (i !== j || n0 || n1 || n2) found(i, j, n0, n1, n2, c2, m2);
        }
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

// ---------------------------------------------------------------- polyhedron details

// Volume (Å³) enclosed by hullFaces(points); null for fewer than 4 points or
// a flat set.
function hullVolume(points) {
  if (points.length < 4) return null;
  const centroid = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  let volume = 0;
  for (const { points: face, normal } of hullFaces(points)) {
    const c = mul(face.reduce(add, [0, 0, 0]), 1 / face.length);
    let area = 0;
    for (let k = 0; k < face.length; k++) area += dot(normal, cross(sub(face[k], c), sub(face[(k + 1) % face.length], c))) / 2;
    volume += (Math.abs(area) * Math.abs(dot(normal, sub(c, centroid)))) / 3;
  }
  return volume > 1e-6 ? volume : null;
}

// Bond cutoffs for every element pair of structure s: the settings', else the
// default (as the Bonds controls fill them in).
function bondCutoffs(s) {
  const species = [...new Set(s.symbols)], cutoffs = {};
  for (const a of species) for (const b of species) cutoffs[pairKey(a, b)] = viewerPrefs.cutoffs[pairKey(a, b)] ?? defaultCutoff(a, b);
  return cutoffs;
}

// Hydrogen bonds D–H···A of structure s with the settings' hbonds: for each H
// atom, the acceptor atoms A (elements hbonds.acceptors) from hbonds.min to
// hbonds.max Å away (with hbonds.perAcceptor, the acceptor element's own
// range where hbonds.ranges has one: hbondRange) that are not bonded to it, where the D–H···A angle at H
// is at least hbonds.angle; the donor D is the nearest atom bonded to the H
// (bond cutoffs and minimums) of an acceptor element. H atoms without such a
// donor get none. Each is { h, a, off (A's cell offset from the H), to (A's
// position), donor: { j, off } }.
function hydrogenBonds(s) {
  const hb = viewerPrefs.hbonds;
  if (!s.symbols.includes("H") || !hb.acceptors.length) return [];
  const acceptors = new Set(hb.acceptors);
  const reach = {}, shortest = {};
  for (const symbol of new Set(s.symbols)) {
    const [low, high] = hbondRange(hb, symbol);
    if (acceptors.has(symbol) && high > 0) { reach[pairKey("H", symbol)] = high; shortest[pairKey("H", symbol)] = low; }
  }
  if (!Object.keys(reach).length) return [];
  const P = positionsOf(s);
  const bonded = new Map();
  for (const bond of neighbours(s, bondCutoffs(s), viewerPrefs.bondMinimums)) {
    if (s.symbols[bond.i] !== "H") continue;
    if (!bonded.has(bond.i)) bonded.set(bond.i, []);
    bonded.get(bond.i).push(bond);
  }
  const imageKey = (j, off) => `${j}|${off}`;
  const cosMax = Math.cos((hb.angle * Math.PI) / 180);
  const found = [];
  for (const pair of neighbours(s, reach, shortest)) {
    if (s.symbols[pair.i] !== "H") continue;
    const partners = bonded.get(pair.i) ?? [];
    if (partners.some((b) => imageKey(b.j, b.off) === imageKey(pair.j, pair.off))) continue;
    const donors = partners.filter((b) => acceptors.has(s.symbols[b.j]))
      .sort((x, y) => norm(sub(x.to, P[pair.i])) - norm(sub(y.to, P[pair.i])));
    if (!donors.length) continue;
    const donor = donors[0];
    const u = sub(donor.to, P[pair.i]), v = sub(pair.to, P[pair.i]);
    if (dot(u, v) / (norm(u) * norm(v) || 1) > cosMax + 1e-12) continue;
    found.push({ h: pair.i, a: pair.j, off: pair.off, to: pair.to, donor: { j: donor.j, off: donor.off } });
  }
  return found;
}

// The coordination polyhedron of atom `index` of structure s: the ligands are
// its bonded non-metals within `cutoffs` (the rule of drawn polyhedra, see
// buildScene; here any atom can be the centre). As stoms.analysis.polyhedron:
//   { index, symbol, cn, ligands: [{ index, symbol, image, length }] (by length),
//     lengths (sorted), mean, volume (hull, Å³; null below 4 ligands),
//     distortion (Baur 1974), quadraticElongation and angleVariance
//     (Robinson et al. 1971; 4 and 6 ligands, against the regular
//     tetrahedron and octahedron of the same volume), econ (Hoppe 1979, as
//     VESTA: weights from the shortest bond) }
function polyhedronOf(s, index, cutoffs = bondCutoffs(s), minimums = viewerPrefs.bondMinimums) {
  const P = positionsOf(s), centre = P[index];
  const ligands = neighbours(s, cutoffs, minimums).filter((b) => b.i === index && NONMETALS.has(s.symbols[b.j]))
    .map((b) => ({ index: b.j, symbol: s.symbols[b.j], image: b.off, to: b.to, length: norm(sub(b.to, centre)) }))
    // Shortest first; lengths within 1e-9 Å count as equal (by atom, image).
    .sort((a, b) => (Math.abs(a.length - b.length) > 1e-9 ? a.length - b.length
      : a.index - b.index || a.image[0] - b.image[0] || a.image[1] - b.image[1] || a.image[2] - b.image[2]));
  const n = ligands.length, lengths = ligands.map((l) => l.length);
  const mean = n ? lengths.reduce((t, l) => t + l, 0) / n : null;
  const result = { index, symbol: s.symbols[index], cn: n, ligands: ligands.map(({ to, ...l }) => l), lengths, mean,
    volume: null, distortion: null, quadraticElongation: null, angleVariance: null, econ: null };
  if (!n) return result;
  result.distortion = lengths.reduce((t, l) => t + Math.abs(l - mean), 0) / (n * mean);
  const shortest = lengths[0];
  const weights = lengths.map((l) => Math.exp(1 - (l / shortest) ** 6));
  const weighted = lengths.reduce((t, l, k) => t + l * weights[k], 0) / weights.reduce((t, w) => t + w, 0);
  result.econ = lengths.reduce((t, l) => t + Math.exp(1 - (l / weighted) ** 6), 0);
  result.volume = hullVolume(ligands.map((l) => l.to));
  if ((n === 4 || n === 6) && result.volume) {
    // Centre-to-vertex distance of the regular polyhedron of this volume:
    // V = 8 l0³ / (9√3) (tetrahedron), 4 l0³ / 3 (octahedron).
    const l0 = n === 4 ? Math.cbrt((9 * Math.sqrt(3) * result.volume) / 8) : Math.cbrt((3 * result.volume) / 4);
    result.quadraticElongation = lengths.reduce((t, l) => t + (l / l0) ** 2, 0) / n;
    // Ligand–centre–ligand angles: all 6 of a tetrahedron; the 12 cis ones of
    // an octahedron (the 3 largest of the 15 are the trans angles).
    const angles = [];
    for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) {
      const u = sub(ligands[a].to, centre), v = sub(ligands[b].to, centre);
      angles.push((Math.acos(Math.max(-1, Math.min(1, dot(u, v) / (norm(u) * norm(v))))) * 180) / Math.PI);
    }
    angles.sort((x, y) => x - y);
    const used = n === 4 ? angles : angles.slice(0, 12);
    const ideal = n === 4 ? (Math.acos(-1 / 3) * 180) / Math.PI : 90;
    result.angleVariance = used.reduce((t, a) => t + (a - ideal) ** 2, 0) / (used.length - 1);
  }
  return result;
}

// Columns of the polyhedron table (and its CSV): key, heading, text of a value.
const POLYHEDRON_FIELDS = [
  ["cn", "Coordination number", (p) => String(p.cn)],
  ["ligands", "Ligands", (p) => p.ligands.map((l) => `${l.symbol}${l.index}`).join(" ")],
  ["lengths", "Bond lengths (Å)", (p) => p.lengths.map((l) => l.toFixed(4)).join(" ")],
  ["mean", "Mean bond length (Å)", (p) => (p.mean === null ? "" : p.mean.toFixed(4))],
  ["volume", "Volume (Å³)", (p) => (p.volume === null ? "" : p.volume.toFixed(4))],
  ["distortion", "Distortion index", (p) => (p.distortion === null ? "" : p.distortion.toFixed(5))],
  ["quadraticElongation", "Quadratic elongation", (p) => (p.quadraticElongation === null ? "" : p.quadraticElongation.toFixed(5))],
  ["angleVariance", "Bond-angle variance (deg²)", (p) => (p.angleVariance === null ? "" : p.angleVariance.toFixed(4))],
  ["econ", "Effective coordination number", (p) => (p.econ === null ? "" : p.econ.toFixed(4))],
];

// CSV of polyhedron entries: rows { structure (a name), polyhedron }.
function polyhedraCsv(rows) {
  const quote = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const header = ["structure", "centre", ...POLYHEDRON_FIELDS.map(([key]) => key)];
  return `${[header, ...rows.map(({ structure, polyhedron: p }) =>
    [structure, `${p.symbol}${p.index}`, ...POLYHEDRON_FIELDS.map(([, , text]) => text(p))])].map((r) => r.map(quote).join(",")).join("\n")}\n`;
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

// The cell shown (the repeat or the transformation matrix) for structure s
// with positions P:
//   matrix: rows of the shown cell in units of the stored cell (the repeat:
//     diagonal); along non-periodic axes it is the identity (other entries
//     there are dropped, with a `note`);
//   transformed: whether a transformation matrix is in use;
//   copies: the number of cell copies (the determinant);
//   images: cell copies n (integer, in the stored lattice) in which some atom
//     is shown, ordered as the repeat orders them: { n, shift (Å), K };
//   has(i, image): whether atom i is shown in that cell copy;
//   inCell(i, m): the same for any image m;
//   pointImages(p): the cell copies a point p of the stored cell is shown in.
// An atom is shown in cell copy n when its position in the stored cell
// (fractional coordinates reduced to [0, 1) along periodic axes) plus n lies
// in the shown cell: each atom once per new cell, none twice at its faces. It
// is drawn at its stored (or wrapped) position plus n, so atoms outside the
// stored cell stay outside as with the repeat, and "Wrap atoms into cell"
// puts them all inside the new cell. With the repeat (and with a diagonal
// matrix) every atom is in every copy.
// The test runs in integers: with the adjugate adj (M·adj = D·I, D = det M),
// the new fractional coordinates are (u + n)·adj / D, so n is shown when
// K = n·adj lies in [t, t + D) for t = ceil(−u·adj).
function shownCell(s, P = positionsOf(s), prefs = viewerPrefs) {
  const [A, B, C] = s.cell;
  const periodic = [0, 1, 2].map((k) => Boolean(s.pbc[k]));
  let note = null;
  // Single cell only: the stored cell once (see SINGLE_CELL_LOCK).
  let matrix = prefs.singleCell ? null : prefs.repeatMatrix;
  if (prefs.singleCell && prefs.repeatMatrix) note = "single cell only is on";
  if (matrix) {
    const kept = matrix.map((row, i) => row.map((v, j) => (periodic[i] && periodic[j] ? v : i === j ? 1 : 0)));
    if (kept.some((row, i) => row.some((v, j) => i !== j && v !== matrix[i][j]))) note = "matrix entries along non-periodic axes are left out";
    matrix = kept;
    if (det3(matrix) < 1) { matrix = null; note = "the transformation matrix needs non-periodic axes: shown without it"; }
  }
  if (!matrix) {
    // The repeat a × b × c: every atom in every copy.
    const [na, nb, nc] = prefs.singleCell ? [1, 1, 1] : prefs.repeat.map((n, k) => (periodic[k] ? n : 1));
    const images = [];
    for (let ia = 0; ia < na; ia++) for (let ib = 0; ib < nb; ib++) for (let ic = 0; ic < nc; ic++) {
      images.push({ n: [ia, ib, ic], shift: add(add(mul(A, ia), mul(B, ib)), mul(C, ic)) });
    }
    const inBox = (m) => m[0] >= 0 && m[0] < na && m[1] >= 0 && m[1] < nb && m[2] >= 0 && m[2] < nc;
    return { matrix: diagonalMatrix([na, nb, nc]), transformed: false, copies: na * nb * nc, images, note,
      has: () => true, inCell: (i, m) => inBox(m), pointImages: () => images };
  }
  const M = matrix, D = det3(M);
  // Adjugate (transposed cofactors).
  const adj = [0, 1, 2].map((i) => [0, 1, 2].map((j) => {
    const r = [0, 1, 2].filter((x) => x !== j), c = [0, 1, 2].filter((x) => x !== i);
    return ((i + j) % 2 ? -1 : 1) * (M[r[0]][c[0]] * M[r[1]][c[1]] - M[r[0]][c[1]] * M[r[1]][c[0]]);
  }));
  const times = (n) => [0, 1, 2].map((k) => n[0] * adj[0][k] + n[1] * adj[1][k] + n[2] * adj[2][k]);
  const recip = reciprocal(s.cell);
  // t of a position: its fractional coordinates reduced to [0, 1) (kept
  // below 1 so rounding cannot move it to the next cell).
  const tOf = (p) => {
    const f = fractional(recip, p);
    const u = [0, 1, 2].map((k) => {
      if (!periodic[k] || !Number.isFinite(f[k])) return 0;
      return Math.min(f[k] - Math.floor(f[k]), 1 - 1e-9);
    });
    return times(u).map((x) => Math.ceil(-x));
  };
  const T = new Int32Array(3 * P.length);
  const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity];
  P.forEach((p, i) => {
    const t = tOf(p);
    for (let k = 0; k < 3; k++) { T[3 * i + k] = t[k]; low[k] = Math.min(low[k], t[k]); high[k] = Math.max(high[k], t[k]); }
  });
  const within = (K, t) => K[0] >= t[0] && K[0] < t[0] + D && K[1] >= t[1] && K[1] < t[1] + D && K[2] >= t[2] && K[2] < t[2] + D;
  // Candidates: u + n inside the shown cell means n within its corners' box
  // (less up to 1).
  const lo = [0, 1, 2].map((k) => Math.min(0, M[0][k]) + Math.min(0, M[1][k]) + Math.min(0, M[2][k]) - 1);
  const hi = [0, 1, 2].map((k) => Math.max(0, M[0][k]) + Math.max(0, M[1][k]) + Math.max(0, M[2][k]));
  const images = [];
  for (let ia = lo[0]; ia <= hi[0]; ia++) for (let ib = lo[1]; ib <= hi[1]; ib++) for (let ic = lo[2]; ic <= hi[2]; ic++) {
    const n = [ia, ib, ic], K = times(n);
    if (!(K.every((v, k) => v >= low[k] && v < high[k] + D))) continue;
    images.push({ n, shift: add(add(mul(A, ia), mul(B, ib)), mul(C, ic)), K });
  }
  const has = (i, image) => {
    const K = image.K, j = 3 * i;
    return K[0] >= T[j] && K[0] < T[j] + D && K[1] >= T[j + 1] && K[1] < T[j + 1] + D && K[2] >= T[j + 2] && K[2] < T[j + 2] + D;
  };
  return { matrix: M, transformed: true, copies: D, images, note,
    has, inCell: (i, m) => has(i, { K: times(m) }),
    pointImages: (p) => { const t = tOf(p); return images.filter((image) => within(image.K, t)); } };
}

// Unit edges [p, q] of the stored cell's outline at each of the cell copies
// `origins` (whole numbers, in units of a, b, c; q = p + a step along one
// axis). An edge shared by neighbouring copies is listed once, so dashed
// outlines stay clean. `axes[k]` false: the cell vector k is zero (as c of
// ASE's graphene), so the outline is flat along it.
function copyOutlines(origins, axes = [true, true, true]) {
  const steps = [[1, 0, 0], [0, 1, 0], [0, 0, 1]].filter((s, k) => axes[k]);
  const none = [0, 0, 0];
  const plus = (p, q) => p.map((v, k) => v + q[k]);
  const seen = new Set(), edges = [];
  for (const origin of origins) {
    for (const step of steps) {
      const others = steps.filter((s) => s !== step);
      for (const i of others[0] ? [0, 1] : [0]) for (const j of others[1] ? [0, 1] : [0]) {
        const p = plus(plus(origin, i ? others[0] : none), j ? others[1] : none), q = plus(p, step);
        const key = `${p}|${q}`;
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push([p, q]);
      }
    }
  }
  return edges;
}

// The stored cells' grid inside the cell of a transformation matrix (rows: the
// shown a, b, c in units of the stored ones): the outlines of every stored
// cell that meets the shown cell (copyOutlines), each edge clipped to the
// shown cell, as edges in units of a, b, c. Pieces lying on an edge of the
// shown cell are left out (that outline is drawn already); pieces in its faces
// stay. A diagonal matrix gives the copies' outlines less those edges.
function storedGrid(matrix, axes = [true, true, true]) {
  const M = matrix, D = det3(M);
  // Fractional coordinates in the shown cell: x · M⁻¹ = x · adj / D.
  const adj = [0, 1, 2].map((i) => [0, 1, 2].map((j) => {
    const r = [0, 1, 2].filter((x) => x !== j), c = [0, 1, 2].filter((x) => x !== i);
    return ((i + j) % 2 ? -1 : 1) * (M[r[0]][c[0]] * M[r[1]][c[1]] - M[r[0]][c[1]] * M[r[1]][c[0]]);
  }));
  const shown = (x) => [0, 1, 2].map((k) => (x[0] * adj[0][k] + x[1] * adj[1][k] + x[2] * adj[2][k]) / D);
  // Stored cells n meeting the shown cell lie within its corners' box (less 1).
  const lo = [0, 1, 2].map((k) => (axes[k] ? Math.min(0, M[0][k]) + Math.min(0, M[1][k]) + Math.min(0, M[2][k]) - 1 : 0));
  const hi = [0, 1, 2].map((k) => (axes[k] ? Math.max(0, M[0][k]) + Math.max(0, M[1][k]) + Math.max(0, M[2][k]) : 0));
  const origins = [];
  for (let i = lo[0]; i <= hi[0]; i++) for (let j = lo[1]; j <= hi[1]; j++) for (let k = lo[2]; k <= hi[2]; k++) origins.push([i, j, k]);
  const eps = 1e-9, at = (p, q, t) => p.map((v, k) => (t === 0 ? v : t === 1 ? q[k] : v + t * (q[k] - v)));
  const edges = [];
  for (const [p, q] of copyOutlines(origins, axes)) {
    // Clip p + t (q − p) to [0, 1]³ in the shown cell (Liang–Barsky).
    const f = shown(p), g = shown(q);
    let t0 = 0, t1 = 1;
    for (let k = 0; k < 3 && t0 <= t1; k++) {
      const d = g[k] - f[k];
      if (Math.abs(d) < eps) { if (f[k] < -eps || f[k] > 1 + eps) t1 = -1; continue; }
      let a = (0 - f[k]) / d, b = (1 - f[k]) / d;
      if (a > b) [a, b] = [b, a];
      t0 = Math.max(t0, a); t1 = Math.min(t1, b);
    }
    if (t1 - t0 < 1e-6) continue;
    if (t0 < eps) t0 = 0;
    if (t1 > 1 - eps) t1 = 1;
    // On an edge of the shown cell: two coordinates at 0 or 1 at both ends.
    const u = f.map((v, k) => v + t0 * (g[k] - v)), w = f.map((v, k) => v + t1 * (g[k] - v));
    const onBorder = [0, 1, 2].filter((k) => Math.abs(u[k] - w[k]) < eps && (Math.abs(u[k]) < eps || Math.abs(u[k] - 1) < eps));
    if (onBorder.length >= 2) continue;
    edges.push([at(p, q, t0), at(p, q, t1)]);
  }
  return edges;
}

// Everything a renderer draws, in Angstrom world coordinates. `forces` (or
// null) holds per-atom vectors, magnitudes and inclusion for the arrows.
// `motion` (or null) is a vibrational mode: { q, vectors, scale, phase,
// moving, arrows, bonds }; atoms are displaced while `moving`, and every
// copy of the cell moves with its own phase.
function buildScene(structure, overlay, forces, ringData = null, motion = null) {
  const prefs = viewerPrefs;
  const P = positionsOf(structure);
  const [A, B, C] = structure.cell;
  // The cell copies shown (the repeat or the transformation matrix).
  const shownLattice = shownCell(structure, P, prefs);
  const { images, has } = shownLattice;
  const latticeShift = (n) => add(add(mul(A, n[0]), mul(B, n[1])), mul(C, n[2]));
  const recip = reciprocal(structure.cell);
  const moving = Boolean(motion?.moving);
  // Fractional positions of the atoms, for the phase of each copy.
  const frac = motion ? P.map((p) => fractional(recip, p)) : null;
  // Where atom i of the cell copy n (shifted by `shift`) is drawn.
  const place = moving
    ? (i, n, shift) => add(add(P[i], shift), modeDisplacement(motion, i, add(n, frac[i])))
    : (i, n, shift) => add(P[i], shift);
  // The style decides whether bonds and polyhedra are drawn (drawsBonds).
  const showBonds = drawsBonds(prefs), showPolyhedra = drawsPolyhedra(prefs);
  const colours = structure.symbols.map((symbol, i) => overlay.colour(i, symbol));
  for (const group of paintState.groups) {
    if (fitsStructure(structure, group.atoms)) for (const r of group.atoms) colours[r.index] = group.colour;
  }
  const radii = structure.symbols.map(atomRadius);
  const hidden = new Set(prefs.hiddenElements);
  const visible = P.map((p, i) => !hidden.has(structure.symbols[i]) && inSlice(fractional(recip, p)));
  const atoms = [];
  // Atoms at rest while a mode plays: the depth range of depth cueing.
  const rest = moving ? [] : null;
  let centreSum = [0, 0, 0];
  // The centre ignores vibrations, so the view stays still.
  images.forEach((image) => P.forEach((p, i) => {
    if (!has(i, image)) return;
    const { n, shift } = image;
    centreSum = add(centreSum, add(p, shift));
    if (!visible[i]) return;
    atoms.push({ index: i, image: n, position: place(i, n, shift), radius: radii[i], colour: colours[i] });
    rest?.push(add(p, shift));
  }));
  const shownAtoms = atoms.length;
  // Cell copies that are drawn, and the atoms drawn in cell copy m: the shown
  // ones, and the extra atoms bonded to them (bondedOutside; keys "j|m";
  // none with single cell only).
  const shown = shownLattice.inCell;
  const bondedOutside = prefs.singleCell ? "hide" : prefs.bondedOutside;
  const extraKeys = new Set();
  const drawn = (j, m) => (visible[j] && shown(j, m)) || extraKeys.has(`${j}|${m}`);
  const halfBonds = [], polyhedra = [], hbonds = [];
  // Wireframe: the atoms with a half-bond (atomKey); the others are dots.
  const bonded = prefs.style === "wireframe" ? new Set() : null;
  const atomKey = (i, n) => i + P.length * (((n[0] + 64) * 128 + n[1] + 64) * 128 + n[2] + 64);
  if (showBonds || showPolyhedra) {
    const bonds = neighbours(structure, prefs.cutoffs, prefs.bondMinimums);
    const centres = new Set(prefs.polyCenters ?? structure.symbols.filter((s) => TRANSITION_METALS.has(s)));
    // Polyhedra: the bonded non-metals of shown centres, at least 4.
    const ligands = new Map();
    if (showPolyhedra) {
      for (const bond of bonds) {
        if (!visible[bond.i] || !centres.has(structure.symbols[bond.i]) || !NONMETALS.has(structure.symbols[bond.j])) continue;
        if (!ligands.has(bond.i)) ligands.set(bond.i, []);
        ligands.get(bond.i).push(bond);
      }
      for (const [i, list] of ligands) if (list.length < 4) ligands.delete(i);
      // Single cell only: only polyhedra complete inside the cell, without a
      // ligand from a neighbouring copy (atoms are wrapped, so the centre is
      // inside); the others are left out (their centres are drawn as atoms).
      if (prefs.singleCell) for (const [i, list] of ligands) if (list.some((bond) => bond.off.some(Boolean))) ligands.delete(i);
    }
    // Atoms outside the repeat or the slice (not of hidden elements) bonded
    // to a shown atom ("partners") or ligands of a shown polyhedron
    // ("ligands"), one step: hoverable and labelled, not counted as shown.
    const extras = [];
    const addExtra = (j, m) => {
      const key = `${j}|${m}`;
      if (hidden.has(structure.symbols[j]) || (visible[j] && shown(j, m)) || extraKeys.has(key)) return;
      extraKeys.add(key);
      extras.push({ j, m });
    };
    if (bondedOutside === "partners") {
      for (const image of images) for (const bond of bonds) if (visible[bond.i] && has(bond.i, image)) addExtra(bond.j, add(image.n, bond.off));
    } else if (bondedOutside === "ligands") {
      for (const [i, list] of ligands) for (const image of images) if (has(i, image)) for (const bond of list) addExtra(bond.j, add(image.n, bond.off));
    }
    for (const { j, m } of extras) {
      atoms.push({ index: j, image: m, position: place(j, m, latticeShift(m)), radius: radii[j], colour: colours[j], extra: true });
      rest?.push(add(P[j], latticeShift(m)));
    }
    // Without polyhedraCentres, the centres of drawn polyhedra (shown atoms
    // with ligands) are not drawn: no sphere, label or half-bonds. They stay
    // in `atoms` (flag hiddenCentre), so they are counted as shown and can
    // still be picked inside their polyhedron.
    const hiddenCentre = showPolyhedra && !prefs.polyhedraCentres && ligands.size
      ? (j, m) => ligands.has(j) && visible[j] && shown(j, m) : null;
    if (hiddenCentre) for (const atom of atoms) if (!atom.extra && ligands.has(atom.index)) atom.hiddenCentre = true;
    // Bonds only between drawn atoms: without extra atoms, a partner in a
    // cell copy outside the repeat gets no half-bond (polyhedra keep all
    // ligands).
    const bondEnds = (bond, n, m) => drawn(bond.j, m) && !hiddenCentre?.(bond.i, n) && !hiddenCentre?.(bond.j, m);
    const byAtom = (list) => {
      const map = new Map();
      if (extras.length) for (const bond of list) { if (!map.has(bond.i)) map.set(bond.i, []); map.get(bond.i).push(bond); }
      return map;
    };
    if (showBonds && !moving) {
      const halfBond = (bond, n, shift) => {
        if (!bondEnds(bond, n, add(n, bond.off))) return;
        const from = add(P[bond.i], shift);
        halfBonds.push({ from, to: mul(add(from, add(bond.to, shift)), 0.5), colour: colours[bond.i] });
        bonded?.add(atomKey(bond.i, n));
      };
      for (const image of images) for (const bond of bonds) if (visible[bond.i] && has(bond.i, image)) halfBond(bond, image.n, image.shift);
      const from = byAtom(bonds);
      for (const { j, m } of extras) for (const bond of from.get(j) ?? []) halfBond(bond, m, latticeShift(m));
    } else if (showBonds) {
      // Fixed: the equilibrium bonds, between the displaced atoms. Live: no
      // atom moves further than motion.amplitude, so every bond of a frame
      // is among the pairs within cutoff + 2 amplitude at equilibrium; keep
      // those within the cutoff (and not below the minimum) now.
      const live = motion.bonds === "live";
      const reach = Object.fromEntries(Object.entries(prefs.cutoffs).map(([key, c]) => [key, c > 0 ? c + 2 * motion.amplitude : 0]));
      const candidates = live ? neighbours(structure, reach) : bonds;
      const halfBond = (bond, n, shift) => {
        const m = add(n, bond.off);
        if (!bondEnds(bond, n, m)) return;
        const from = place(bond.i, n, shift), to = place(bond.j, m, latticeShift(m));
        if (live) {
          const d = sub(to, from), d2 = dot(d, d), key = pairKey(structure.symbols[bond.i], structure.symbols[bond.j]);
          const c = prefs.cutoffs[key] ?? 0, low = prefs.bondMinimums[key] ?? 0;
          if (d2 >= c * c || d2 < low * low) return;
        }
        halfBonds.push({ from, to: mul(add(from, to), 0.5), colour: colours[bond.i] });
        bonded?.add(atomKey(bond.i, n));
      };
      for (const image of images) for (const bond of candidates) if (visible[bond.i] && has(bond.i, image)) halfBond(bond, image.n, image.shift);
      const from = byAtom(candidates);
      for (const { j, m } of extras) for (const bond of from.get(j) ?? []) halfBond(bond, m, latticeShift(m));
    }
    if (showPolyhedra) {
      for (const [i, list] of ligands) {
        if (moving) {
          // The equilibrium ligands, displaced: each copy has its own shape.
          for (const { n } of images.filter((image) => has(i, image))) {
            const points = list.map((bond) => { const m = add(n, bond.off); return place(bond.j, m, latticeShift(m)); });
            polyhedra.push({ colour: colours[i], faces: hullFaces(points) });
          }
          continue;
        }
        const faces = hullFaces(list.map((bond) => bond.to));
        for (const { shift } of images.filter((image) => has(i, image))) {
          polyhedra.push({ colour: colours[i], faces: faces.map((f) => ({ normal: f.normal, points: f.points.map((p) => add(p, shift)) })) });
        }
      }
    }
  }
  if (bonded) for (const atom of atoms) atom.bonded = bonded.has(atomKey(atom.index, atom.image));
  // Hydrogen bonds between drawn atoms, from each drawn H.
  if (prefs.hbonds.show) {
    const byH = new Map();
    for (const hb of hydrogenBonds(structure)) {
      if (!byH.has(hb.h)) byH.set(hb.h, []);
      byH.get(hb.h).push(hb);
    }
    if (byH.size) {
      for (const atom of atoms) for (const hb of byH.get(atom.index) ?? []) {
        const m = add(atom.image, hb.off);
        if (drawn(hb.a, m)) hbonds.push({ from: atom.position, to: place(hb.a, m, latticeShift(m)) });
      }
    }
  }
  // The cell outline: the stored cell, or with a transformation matrix the
  // new cell (and the stored one when storedCellOutline).
  const outline = ([U, V, W]) => {
    const corners = [];
    for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) corners.push(add(add(mul(U, i), mul(V, j)), mul(W, k)));
    return [[0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3], [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7]].map(([a, b]) => [corners[a], corners[b]]);
  };
  const shownVectors = shownLattice.matrix.map((row) => add(add(mul(A, row[0]), mul(B, row[1])), mul(C, row[2])));
  const everyCopy = prefs.cell && prefs.repeatCellOutline && shownLattice.copies > 1;
  let cellEdges = !prefs.cell ? [] : outline(shownLattice.transformed ? shownVectors : [A, B, C]);
  let storedEdges = prefs.cell && shownLattice.transformed && prefs.storedCellOutline && shownLattice.copies > 1 ? outline([A, B, C]) : [];
  // repeatCellOutline: the stored cell at every copy of the repeat (in the
  // outline's style), or with a matrix the stored cells' grid inside the new
  // cell (dotted, as the stored cell; it includes storedCellOutline's part).
  if (everyCopy) {
    const axes = [A, B, C].map((v) => norm(v) > 1e-8);
    const edges = (shownLattice.transformed ? storedGrid(shownLattice.matrix, axes) : copyOutlines(images.map(({ n }) => n), axes))
      .map(([p, q]) => [latticeShift(p), latticeShift(q)]);
    if (shownLattice.transformed) storedEdges = edges; else cellEdges = edges;
  }
  // Centre on every atom so slicing does not move the view.
  const centre = mul(centreSum, 1 / Math.max(1, shownLattice.copies * P.length));
  // Miller planes (of the stored cell) and planes through atoms cut the shown
  // region; planes through atoms may be patches around their atoms instead.
  // With single cell only every plane (also an extended one or a patch) is
  // clipped to the stored cell.
  const clip = prefs.singleCell ? (polygon) => clipToCell(polygon, structure.cell) : (polygon) => polygon;
  const planes = prefs.planes.map((plane, k) => ({ plane, k })).filter(({ plane }) => plane.show && (isAtomPlane(plane) || plane.h || plane.k || plane.l))
    .map(({ plane, k }) => ({ colour: planeColour(plane, k), polygon: clip(scalePolygon(isAtomPlane(plane)
      ? atomPlanePolygon(structure, plane, shownLattice.matrix) : planePolygon(structure.cell, plane, shownLattice.matrix), plane.scale)) }))
    .filter((p) => p.polygon);
  // Rings in every shown cell copy, coloured by size; with single cell only
  // the rings inside the cell (none reaching into a neighbouring copy).
  // (ringData: from loadRings, while rings are shown.)
  const rings = [], sizeRange = ringSizeRange(ringData);
  const ringInside = prefs.singleCell ? insideCell(recip, structure.pbc.map(Boolean)) : null;
  for (const ring of ringData?.rings ?? []) {
    if (!ringShown(ring)) continue;
    if (ringInside && !ring.points.every(ringInside)) continue;
    for (const { shift } of shownLattice.pointImages(ring.centre)) {
      rings.push({ ring, colour: ringColour(ring.size, sizeRange), points: ring.points.map((p) => add(p, shift)), centre: add(ring.centre, shift) });
    }
  }
  // Text on atoms: index, element, or the value the atom is coloured by.
  const labelText = {
    index: (i) => String(i), element: (i) => structure.symbols[i], "element-index": (i) => `${structure.symbols[i]}${i}`,
    value: (i) => overlay.value?.(i) ?? "",
  }[prefs.labels];
  const labels = labelText ? atoms.filter((atom) => !atom.hiddenCentre).map((atom) => ({ position: atom.position, radius: atom.radius, text: labelText(atom.index) })).filter((l) => l.text) : [];
  // Arrows start on the sphere surface so the atom does not hide them; on a
  // hidden polyhedron centre (polyhedraCentres off) at the atom itself.
  const arrows = [];
  const hiddenKeys = new Set(atoms.filter((a) => a.hiddenCentre).map((a) => atomKey(a.index, a.image)));
  if (prefs.arrows.show && forces) {
    for (const atom of atoms) {
      if (atom.extra) continue;
      const i = atom.index, magnitude = forces.magnitudes[i];
      if (!forces.included[i] || !(magnitude > 0) || magnitude < prefs.arrows.minMagnitude) continue;
      const from = atom.hiddenCentre ? atom.position : add(atom.position, mul(forces.vectors[i], atom.radius / magnitude));
      arrows.push({ from, to: add(from, mul(forces.vectors[i], prefs.arrows.scale)) });
    }
  }
  // Mode arrows: each atom's displacement at phase 0 (where the vibration
  // starts), drawn from the atom as shown.
  if (motion?.arrows) {
    for (const image of images) P.forEach((p, i) => {
      if (!visible[i] || !has(i, image)) return;
      const { n, shift } = image;
      const vector = mul(modeDisplacement(motion, i, add(n, frac[i]), 0), MODE_ARROW_SCALE), length = norm(vector);
      if (!(length > 1e-6)) return;
      const from = hiddenKeys.has(atomKey(i, n)) ? place(i, n, shift) : add(place(i, n, shift), mul(vector, radii[i] / length));
      arrows.push({ from, to: add(from, vector) });
    });
  }
  // Measurements on top of the scene, and rings around atoms picked so far.
  // (A plane angle has no mark; a distance to a plane runs to the plane.)
  const marks = measureState.items.filter((item) => item.kind !== "plane-angle" && fitsStructure(structure, measureRefs(item)))
    .map((item) => {
      const value = measureValue(structure, item);
      return value && { points: value.points ?? item.atoms.map((r) => refPosition(structure, r)), label: value.text,
        radius: item.kind === "position" ? radii[item.atoms[0].index] : 0 };
    }).filter(Boolean);
  const picked = fitsStructure(structure, measureState.pending)
    ? measureState.pending.map((r) => ({ position: refPosition(structure, r), radius: radii[r.index] })) : [];
  // Atoms selected for colouring: a ring on every shown copy.
  if (fitsStructure(structure, paintState.selected)) {
    const selected = new Set(paintState.selected.map((r) => r.index));
    for (const atom of atoms) if (selected.has(atom.index)) picked.push({ position: atom.position, radius: atom.radius });
  }
  return { atoms, halfBonds, hbonds, hbondColour: prefs.hbonds.colour, polyhedra, cellEdges, storedEdges, planes, arrows, arrowStyle: { ...prefs.arrows }, marks, picked,
    rings, ringData, ringStyle: { ...prefs.rings }, labels, tripod: prefs.tripod.axes, tripodSize: prefs.tripod.size,
    tripodAxesSize: prefs.tripod.axesSize, tripodWaveSize: prefs.tripod.waveSize,
    centre, restPositions: rest, bondRadius: prefs.appearance.bondRadius, style: prefs.style, structure, overlay,
    appearance: { ...prefs.appearance, radii: { ...prefs.appearance.radii } },
    visibleAtoms: shownAtoms, extraAtoms: atoms.length - shownAtoms, totalAtoms: shownLattice.copies * P.length,
    transform: shownLattice.transformed ? { matrix: shownLattice.matrix, copies: shownLattice.copies } : null, cellNote: shownLattice.note };
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
  const points = [...scene.atoms.map((a) => a.position), ...scene.cellEdges.flat(), ...(scene.storedEdges ?? []).flat()];
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
//   dot:     { kind, x, y, r, colour } (a flat disc: wireframe atoms without bonds)
//   lines:   { kind, segments: [[ax, ay, bx, by], ...], colour, width } (wireframe bonds)
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
  // Wireframe: bonded atoms are their bonds' ends, others a dot; atoms with
  // a radius of their own stay spheres in every style.
  const wireframe = scene.style === "wireframe";
  const symbols = scene.structure.symbols;
  for (const atom of scene.atoms) {
    // Hidden polyhedron centres (polyhedraCentres off) are only pickable.
    if (atom.hiddenCentre) continue;
    const [x, y, z] = project(atom.position);
    if (wireframe && look.radii[symbols[atom.index]] == null) {
      if (!atom.bonded) items.push({ z, p: atom.position, prims: [{ kind: "dot", x, y, r: Math.max(DOT_RADIUS, atom.radius * s), colour: atom.colour }] });
      continue;
    }
    items.push({ z, p: atom.position, prims: [{ kind: "sphere", x, y, r: atom.radius * s, colour: atom.colour }] });
  }
  // Bond colours are the atoms' colours, a little darker; computed once per colour.
  const bondColours = new Map();
  const bondColour = (colour) => {
    let c = bondColours.get(colour);
    if (c === undefined) bondColours.set(colour, c = mix(colour, "#000000", 0.2));
    return c;
  };
  // Wireframe bonds are not sorted by depth: they are drawn as one batch of
  // lines per colour, beneath the atoms (and polyhedra) of their side of the
  // planes. Thin lines barely hide each other, and this draws large scenes
  // fast.
  const wires = [];
  const bondWidth = Math.max(1, 2 * scene.bondRadius * s);
  for (const bond of scene.halfBonds) {
    const a = project(bond.from), b = project(bond.to);
    if (wireframe) { wires.push({ a, b, bond }); continue; }
    items.push({ z: Math.min(a[2], b[2]) - 0.05, p: mul(add(bond.from, bond.to), 0.5),
      prims: [{ kind: "line", a, b, colour: bondColour(bond.colour), width: bondWidth }] });
  }
  // Hydrogen bonds: dashed lines between the atoms' centres.
  if (scene.hbonds.length) {
    const width = Math.max(1, scene.bondRadius * s), dash = [Math.max(4, 3 * width), Math.max(3, 2 * width)];
    for (const line of scene.hbonds) {
      const a = project(line.from), b = project(line.to);
      items.push({ z: (a[2] + b[2]) / 2 - 0.05, p: mul(add(line.from, line.to), 0.5),
        prims: [{ kind: "line", a, b, colour: scene.hbondColour, width, dash }] });
    }
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
  const cellColour = look.cellColour ?? theme.cell, cellWidth = look.cellWidth;
  const cellDash = CELL_DASHES[look.cellDash]?.map((x) => x * cellWidth);
  const list = scene.cellEdges.map(([a, b]) => {
    const pa = project(a), pb = project(b), fog = fogAt?.((pa[2] + pb[2]) / 2);
    return { kind: "line", a: pa, b: pb, colour: fog > 0 ? mix(cellColour, theme.halo, fog) : cellColour, width: cellWidth, dash: cellDash };
  });
  // The stored cell beside a transformed one: thinner and dotted.
  const storedWidth = Math.max(0.5, cellWidth / 2), storedDash = CELL_DASHES.dotted.map((x) => x * storedWidth);
  for (const [a, b] of scene.storedEdges ?? []) {
    const pa = project(a), pb = project(b), fog = fogAt?.((pa[2] + pb[2]) / 2);
    list.push({ kind: "line", a: pa, b: pb, colour: fog > 0 ? mix(cellColour, theme.halo, fog) : cellColour, width: storedWidth, dash: storedDash });
  }
  // Planes are drawn whole; each item goes before or after a plane depending
  // on which side of it the item lies as seen from the viewer.
  const planes = scene.planes.map((pl) => {
    const points = pl.polygon.points.map(project);
    return { ...pl, points, depth: points.reduce((m, q) => m + q[2], 0) / points.length, facing: Math.sign(dot(pl.polygon.normal, R[2])) || 1 };
  }).sort((a, b) => a.depth - b.depth);
  const layers = planes.map(() => []).concat([[]]);
  const sideOf = (p) => planes.reduce((n, pl) => n + (Math.sign(dot(pl.polygon.normal, sub(p, pl.polygon.centre))) === pl.facing ? 1 : 0), 0);
  for (const item of items) layers[sideOf(item.p)].push(item);
  // Wireframe batches per layer and colour (with depth cueing, per colour
  // and fog in steps of 2.5%).
  const wireLayers = layers.map(() => new Map());
  const fogged = new Map();
  for (const { a, b, bond } of wires) {
    let colour = bondColour(bond.colour);
    if (fogAt) {
      const fog = Math.round(fogAt((a[2] + b[2]) / 2) * 40) / 40;
      if (fog > 0) {
        const key = `${colour}|${fog}`;
        if (!fogged.has(key)) fogged.set(key, mix(colour, theme.halo, fog));
        colour = fogged.get(key);
      }
    }
    const batches = wireLayers[planes.length ? sideOf(mul(add(bond.from, bond.to), 0.5)) : 0];
    if (!batches.has(colour)) batches.set(colour, []);
    batches.get(colour).push([a[0], a[1], b[0], b[1]]);
  }
  layers.forEach((layer, k) => {
    for (const [colour, segments] of wireLayers[k]) list.push({ kind: "lines", segments, colour, width: WIRE_WIDTH });
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
    // Label above the atom (position), at the bond's middle (distance), the
    // vertex (angle) or the middle bond (dihedral).
    const at = points.length === 1 ? [points[0][0], points[0][1] - mark.radius * s] : points.length === 3 ? points[1] : points.length === 2
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
// origin, tip, label, z, scale } with z > 0 pointing at the viewer. With both
// kinds, the Cartesian arrows are shorter, so their labels stay apart.
// scene.tripodSize scales the arrows, scene.tripodAxesSize and
// scene.tripodWaveSize the axes and q, v_g on top of it; line widths, heads and
// labels grow with the square root (`scale`, never below 1), so a small tripod
// stays legible. The origin moves inwards for the larger of the two.
const TRIPOD_LENGTH = 34;
function tripodLayout(scene, height) {
  const R = sharedView.R;
  const size = scene.tripodSize ?? 1;
  const axesSize = size * (scene.tripodAxesSize ?? 1), waveSize = size * (scene.tripodWaveSize ?? 1);
  const scaleOf = (s) => Math.max(1, Math.sqrt(s));
  const scale = scaleOf(axesSize), waveScale = scaleOf(waveSize);
  const length = TRIPOD_LENGTH * axesSize, gap = 10 * scale;
  const waveLength = TRIPOD_LENGTH * waveSize, waveGap = 10 * waveScale;
  const margin = Math.max(length + 14 * scale, scene.wave ? waveLength + 14 * waveScale : 0);
  const origin = [margin, height - margin];
  const names = { abc: "abc", xyz: "xyz", both: "xyzabc" }[scene.tripod] ?? "";
  // Cell axes of zero length (a molecule without a cell) are left out.
  return [...names].map((name) => {
    const v = axisDirection(scene.structure.cell, name);
    if (!norm(v)) return null;
    const x = dot(R[0], v), y = dot(R[1], v);
    const lattice = "abc".includes(name), shown = scene.tripod === "both" && !lattice ? 0.6 * length : length;
    return { name, colour: AXIS_COLOURS[name], lattice, origin, z: dot(R[2], v), scale,
      tip: [origin[0] + x * shown, origin[1] - y * shown],
      label: [origin[0] + x * (shown + gap), origin[1] - y * (shown + gap)] };
  }).filter(Boolean).concat(waveLayout(scene.wave, origin, waveLength, waveGap, waveScale)).sort((p, q) => p.z - q.z);
}

// The wave vector q and the group velocity v_g of a mode (scene.wave, set by
// the vibration panel: Cartesian vectors, q scaled so the farthest point of
// the first Brillouin zone is one axis length (at the axes' own size), v_g of
// unit length; either may
// be null) as tripod arrows of `length` pixels per unit, names `gap` beyond
// the tips. `wave` marks them: they are not axes to look along.
function waveLayout(wave, origin, length = TRIPOD_LENGTH, gap = 10, scale = 1) {
  if (!wave) return [];
  const R = sharedView.R;
  return [["q", wave.q, wave.qColour, wave.qDash], ["v_g", wave.vg, wave.vgColour, wave.vgDash]].map(([name, v, colour, dash]) => {
    if (!v || !(norm(v) > 0)) return null;
    const x = dot(R[0], v), y = dot(R[1], v), along = gap / norm(v);
    return { name, colour, dash, wave: true, scale, label: wave.labels ? [origin[0] + x * (length + along), origin[1] - y * (length + along)] : null,
      origin, z: dot(R[2], v) / norm(v), tip: [origin[0] + x * length, origin[1] - y * length] };
  }).filter(Boolean);
}

// Sets the tripod's axes ("abc", "xyz", "both", "off"). A mode's wave vector
// is drawn on the Cartesian axes alone, so any other choice switches it off.
function setTripodAxes(value) {
  viewerPrefs.tripod.axes = value;
  if (value !== "xyz") viewerPrefs.vibration.waveVector = false;
}

// Cell axes as solid arrows, Cartesian ones thinner; axes pointing away from
// the viewer are paler. q and v_g are not axes and look different: a wider
// shaft with a dark outline and a larger head, and a bold italic label because
// they are vectors. A name with "_" (v_g) gets the rest as a subscript, which
// stays upright at the normal weight.
function tripodPrims(layout, theme, hoverAxis) {
  const prims = [];
  for (const axis of layout) {
    const scale = axis.scale ?? 1;
    const hovered = !axis.wave && axis.name === hoverAxis;
    const colour = axis.z < -0.2 ? mix(axis.colour, theme.halo, 0.45) : axis.colour;
    const width = ((axis.wave ? 3.5 : axis.lattice ? 2.5 : 1.5) + (hovered ? 1.5 : 0)) * scale;
    if (Math.hypot(axis.tip[0] - axis.origin[0], axis.tip[1] - axis.origin[1]) > 4) {
      prims.push({ kind: "arrow", a: [...axis.origin, 0], b: [...axis.tip, 0], colour, width,
        ...(axis.wave ? { dash: CELL_DASHES[axis.dash]?.map((x) => x * scale) ?? null, outline: mix(axis.colour, "#000000", 0.55), head: 1.3 } : { dash: null }) });
    }
    if (axis.label) {
      const [text, sub = null] = axis.name.split("_");
      prims.push({ kind: "label", x: axis.label[0], y: axis.label[1] + 6 * scale, text, sub, colour, halo: theme.halo, size: (hovered ? 14 : 12) * scale,
        ...(axis.wave ? { weight: 800, italic: true, embolden: emboldenWidth(12 * scale) } : {}) });
    }
  }
  return prims;
}

// The axis under a pixel: its label or its shaft, front-most first.
function tripodHit(layout, x, y) {
  const near = (axis) => {
    if (axis.wave) return false;
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

// prim.weight overrides the label weight (bold for vectors), prim.italic
// slants it (not a subscript). A font may have
// no weight above bold, so prim.embolden also strokes the text (not a
// subscript) in its own colour, this wide.
const emboldenWidth = (size = 12) => size / 12;
const LABEL_WEIGHT = 600;
const labelFont = (size = 12, weight = LABEL_WEIGHT, italic = false) => `${italic ? "italic " : ""}${weight} ${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
// Outline around label text, growing with larger labels.
const haloWidth = (size = 12) => Math.max(3, size / 6);
// A label's subscript (prim.sub): its size, and how far its baseline drops.
const subscriptSize = (size = 12) => 0.72 * size;
const subscriptDrop = (size = 12) => 0.3 * size;
// An outlined arrow's outline: this much wider than the shaft, and the
// stroke around its head.
const ARROW_OUTLINE = 2;

// Arrow geometry in pixels: shaft end and the head's three corners; `headScale`
// enlarges the head.
function arrowGeometry(a, b, width, headScale = 1) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const length = Math.hypot(dx, dy);
  if (length < 0.5) return null;
  const ux = dx / length, uy = dy / length;
  const head = Math.min(length, headScale * Math.max(3 * width, 6));
  const half = headScale * Math.max(1.5 * width, 3);
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

// `pixelScale`: device pixels per CSS pixel of the canvas transform. With
// `hairlines` (on screen), wireframe lines are one device pixel wide, which
// the browser draws much faster than wider lines (saved images keep their
// width).
const LINES_PER_STROKE = 250;
function paintCanvas(ctx, list, pixelScale = 1, { hairlines = false } = {}) {
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
    } else if (prim.kind === "dot") {
      ctx.fillStyle = prim.colour;
      ctx.beginPath(); ctx.arc(prim.x, prim.y, prim.r, 0, 2 * Math.PI); ctx.fill();
    } else if (prim.kind === "lines") {
      // A few hundred segments per path: faster than one path each or one for all.
      ctx.strokeStyle = prim.colour; ctx.lineWidth = hairlines ? 1 / pixelScale : prim.width; ctx.lineCap = "butt";
      const segments = prim.segments;
      for (let start = 0; start < segments.length; start += LINES_PER_STROKE) {
        ctx.beginPath();
        for (let k = start, end = Math.min(segments.length, start + LINES_PER_STROKE); k < end; k++) {
          const q = segments[k];
          ctx.moveTo(q[0], q[1]); ctx.lineTo(q[2], q[3]);
        }
        ctx.stroke();
      }
    } else if (prim.kind === "line") {
      ctx.strokeStyle = prim.colour; ctx.lineWidth = prim.width; ctx.lineCap = "butt";
      if (prim.dash) ctx.setLineDash(prim.dash);
      path([prim.a, prim.b]); ctx.stroke();
      if (prim.dash) ctx.setLineDash([]);
    } else if (prim.kind === "label" && prim.sub) {
      // Text and subscript side by side, centred together; halos first, so
      // the subscript's halo does not cover the text.
      const size = prim.size ?? 12, small = subscriptSize(size);
      const weight = prim.weight ?? LABEL_WEIGHT;
      ctx.font = labelFont(size, weight, prim.italic); const width = ctx.measureText(prim.text).width;
      ctx.font = labelFont(small); const subWidth = ctx.measureText(prim.sub).width;
      const left = prim.x - (width + subWidth) / 2;
      const pieces = [[prim.text, size, weight, left, prim.y, prim.italic], [prim.sub, small, LABEL_WEIGHT, left + width, prim.y + subscriptDrop(size), false]];
      ctx.textAlign = "left"; ctx.textBaseline = "bottom"; ctx.lineJoin = "round";
      ctx.lineWidth = haloWidth(size); ctx.strokeStyle = prim.halo;
      for (const [text, px, w, x, y, it] of pieces) { ctx.font = labelFont(px, w, it); ctx.strokeText(text, x, y); }
      if (prim.embolden) {
        const [text, px, w, x, y, it] = pieces[0];
        ctx.font = labelFont(px, w, it); ctx.lineWidth = prim.embolden; ctx.strokeStyle = prim.colour; ctx.strokeText(text, x, y);
      }
      ctx.fillStyle = prim.colour;
      for (const [text, px, w, x, y, it] of pieces) { ctx.font = labelFont(px, w, it); ctx.fillText(text, x, y); }
    } else if (prim.kind === "label") {
      ctx.font = labelFont(prim.size, prim.weight, prim.italic); ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.lineWidth = haloWidth(prim.size); ctx.lineJoin = "round"; ctx.strokeStyle = prim.halo; ctx.strokeText(prim.text, prim.x, prim.y);
      if (prim.embolden) { ctx.lineWidth = prim.embolden; ctx.strokeStyle = prim.colour; ctx.strokeText(prim.text, prim.x, prim.y); }
      ctx.fillStyle = prim.colour; ctx.fillText(prim.text, prim.x, prim.y);
    } else if (prim.kind === "ring") {
      ctx.strokeStyle = prim.colour; ctx.lineWidth = prim.width;
      ctx.beginPath(); ctx.arc(prim.x, prim.y, prim.r, 0, 2 * Math.PI); ctx.stroke();
    } else if (prim.kind === "arrow") {
      const geometry = arrowGeometry(prim.a, prim.b, prim.width, prim.head);
      if (!geometry) continue;
      const shaft = (colour, width) => {
        if (!geometry.shaft) return;
        ctx.strokeStyle = colour; ctx.lineWidth = width; ctx.lineCap = "butt";
        if (prim.dash) ctx.setLineDash(prim.dash);
        path(geometry.shaft); ctx.stroke();
        if (prim.dash) ctx.setLineDash([]);
      };
      if (prim.outline) {
        shaft(prim.outline, prim.width + ARROW_OUTLINE);
        ctx.lineWidth = ARROW_OUTLINE; ctx.lineJoin = "round";
        path(geometry.head); ctx.closePath(); ctx.stroke();
      }
      shaft(prim.colour, prim.width);
      ctx.fillStyle = prim.colour;
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
  paintCanvas(ctx, displayList(scene, width, height, theme, options), pixelScale, { hairlines: options.hairlines });
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
      paintScene(canvas, scene, width, height, dpr, theme, false, { ...options, hairlines: true });
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
      } else if (prim.kind === "dot") {
        shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(prim.r)}" fill="${prim.colour}"/>`);
      } else if (prim.kind === "lines") {
        shapes.push(`<g stroke="${prim.colour}" stroke-width="${round(prim.width)}">`,
          ...prim.segments.map(([ax, ay, bx, by]) => `<line x1="${round(ax)}" y1="${round(ay)}" x2="${round(bx)}" y2="${round(by)}"/>`), "</g>");
      } else if (prim.kind === "line") {
        const dash = prim.dash ? ` stroke-dasharray="${prim.dash.map(round).join(" ")}"` : "";
        shapes.push(`<line x1="${round(prim.a[0])}" y1="${round(prim.a[1])}" x2="${round(prim.b[0])}" y2="${round(prim.b[1])}" stroke="${prim.colour}" stroke-width="${round(prim.width)}"${dash}/>`);
      } else if (prim.kind === "label") {
        const escape = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        const size = prim.size ?? 12;
        const weight = prim.weight ?? LABEL_WEIGHT;
        const subWeight = (weight === LABEL_WEIGHT ? "" : ` font-weight="${LABEL_WEIGHT}"`) + (prim.italic ? ' font-style="normal"' : "");
        const style = prim.italic ? ' font-style="italic"' : "";
        const subOf = (extra = "") => (prim.sub ? `<tspan dy="${round(subscriptDrop(size))}" font-size="${round(subscriptSize(size))}"${subWeight}${extra}>${escape(prim.sub)}</tspan>` : "");
        const text = (stroke, width, sub) => `<text x="${round(prim.x)}" y="${round(prim.y)}" text-anchor="middle" font-family="system-ui, sans-serif" font-size="${round(size)}" font-weight="${weight}"${style} fill="${prim.colour}" stroke="${stroke}" stroke-width="${round(width)}" stroke-linejoin="round" paint-order="stroke">${escape(prim.text)}${sub}</text>`;
        shapes.push(text(prim.halo, haloWidth(size), subOf()));
        // Emboldened: the text again, stroked in its colour; the subscript is not.
        if (prim.embolden) shapes.push(text(prim.colour, prim.embolden, subOf(' stroke-width="0"')));
      } else if (prim.kind === "ring") {
        shapes.push(`<circle cx="${round(prim.x)}" cy="${round(prim.y)}" r="${round(prim.r)}" fill="none" stroke="${prim.colour}" stroke-width="${prim.width}"/>`);
      } else if (prim.kind === "arrow") {
        const geometry = arrowGeometry(prim.a, prim.b, prim.width, prim.head);
        if (!geometry) continue;
        const dash = prim.dash ? ` stroke-dasharray="${prim.dash.map(round).join(" ")}"` : "";
        const shaft = (colour, width) => (geometry.shaft ? [`<line x1="${round(geometry.shaft[0][0])}" y1="${round(geometry.shaft[0][1])}" x2="${round(geometry.shaft[1][0])}" y2="${round(geometry.shaft[1][1])}" stroke="${colour}" stroke-width="${round(width)}"${dash}/>`] : []);
        const head = geometry.head.map(xy).join(" ");
        if (prim.outline) {
          shapes.push(...shaft(prim.outline, prim.width + ARROW_OUTLINE),
            `<polygon points="${head}" fill="none" stroke="${prim.outline}" stroke-width="${ARROW_OUTLINE}" stroke-linejoin="round"/>`);
        }
        shapes.push(...shaft(prim.colour, prim.width), `<polygon points="${head}" fill="${prim.colour}"/>`);
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
  const nacSwitch = el("label", { class: "check", hidden: true, "data-control": "phonon.nac", title: "Non-analytical term correction from Born charges: LO and TO modes split at Γ, by the direction Γ is approached from" },
    nacBox, "NAC");
  const plot = { bands: null, dos: null, state: null, geometry: null, svg: "" };
  const saveButton = el("button", { type: "button", class: "small", title: "Save the band structure and DOS as an SVG image", "data-control": "phonon.save-svg", onclick: () => {
    if (plot.svg) downloadText(`${structure.formula}-phonons.svg`, `<?xml version="1.0" encoding="UTF-8"?>\n${plot.svg}\n`, "image/svg+xml");
  } }, "Save bands & DOS (SVG)");
  // Buttons of the page that shows the plot go here, before the save button.
  plot.actions = el("div", { class: "phonon-plot-actions" }, saveButton);
  // The slider runs along the path, under the bands (aligned in draw).
  const slider = el("input", { type: "range", class: "phonon-slider", min: 0, max: 1000, step: 1, value: 0, "data-control": "phonon.path-slider",
    "aria-label": "Position along the band path", title: "Move q along the band path" });
  plot.element = el("section", { class: "phonon-plot", "aria-label": "Phonon band structure and DOS" },
    el("div", { class: "phonon-plot-head" }, el("strong", {}, "Phonon band structure and DOS"), nacSwitch, note, plot.actions), figure, slider);

  // Resize grip at the plot's bottom-right corner, as for the structure
  // panels: width and height (vibration.plotWidth, plotHeight; double-click:
  // automatic). The plot redraws as the figure changes size.
  const sizeLabel = el("div", { class: "resize-size" });
  const grip = el("div", { class: "resize-grip", title: "Drag to resize; double-click for the automatic size",
    role: "separator", "aria-label": "Resize band structure plot", "data-control": "phonon.resize" });
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
    // The wave vector and group velocity on the tripod (see waveLayout).
    panel.scene.wave = panel.wave ?? null;
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
      const offset = sub(atom.position, positionsOf(panel.structure)[atom.index]);
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
      // At least a few pixels: stick and wireframe atoms are small.
      const r = Math.max(4, atom.radius * sharedView.scale);
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
      lines.push([positionText(atom.position), "x, y, z"]);
      if (atom.extra) lines.push(["outside the repeat or slice", "bonded to a shown atom"]);
      if (atom.hiddenCentre) lines.push(["not drawn", "centre of a shown polyhedron"]);
      const forces = panel.forces, i = atom.index;
      // Wyckoff letter and site symmetry, once the symmetry is known.
      const sym = symmetryNow(panel.structure);
      if (symmetrySites(sym, panel.structure)) {
        lines.push([sym.wyckoffs[i], "Wyckoff letter"], [sym.site_symmetries[i], "site symmetry"]);
      }
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
  ["displacement", "Displacement from the reference (Å)"],
  ["equivalent", "Equivalent site (symmetry)"],
];
const VECTOR_COMPONENTS = [["norm", "magnitude"], ["x", "x"], ["y", "y"], ["z", "z"]];
const choiceKey = (choice) => (choice ? JSON.stringify([choice.source, choice.origin ?? null, choice.method ?? null, choice.name]) : "");

function propertyOptions(s) {
  // Equivalent sites need symmetry (spglib): not offered without it.
  const options = DERIVED_PROPERTIES.filter(([name]) => name !== "equivalent" || symmetryAvailable(s)).map(([name, label]) => ({
    group: "From the geometry", label,
    kind: name === "displacement" ? "vector" : name === "equivalent" ? "text" : "number", choice: { source: "derived", name } }));
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
    if (choice.name === "displacement") {
      const d = await displacementFor(s);
      return d.vectors ? { values: d.vectors.map(pick), label: `${componentLabel("Δr")} from ${displacementReferenceText()}`, unit: "Å" } : null;
    }
    const P = positionsOf(s);
    if (choice.name === "coordination") {
      const counts = P.map(() => 0);
      for (const bond of neighbours(s, viewerPrefs.cutoffs, viewerPrefs.bondMinimums)) counts[bond.i] += 1;
      return { values: counts, label };
    }
    if (choice.name === "ring") {
      const smallest = P.map(() => null);
      for (const ring of (await loadRings(s)).rings) for (const i of ring.atoms) smallest[i] = Math.min(smallest[i] ?? Infinity, ring.size);
      return { values: smallest, label };
    }
    if (choice.name === "equivalent") {
      const sym = await loadSymmetry(s);
      if (!symmetrySites(sym, s)) return null;
      return { values: siteLabels(sym, s), label: `${label}, ${sym.international} (${sym.number})`, text: true };
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
    // Arrays from the notebook (stoms.viewer) may carry a unit (calculator results).
    if (array.kind === "vector") return { values: array.values.map((v) => (v.includes(null) ? null : pick(v))), label: componentLabel(array.name), unit: array.unit };
    return { values: array.values, label: array.name, text: array.kind === "text", unit: array.unit };
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
  return positionsOf(structure).map((p) => dot(p, n));
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

// ---------------------------------------------------------------- structure controls

// Controls of settings shared by the structure page and the notebook viewer
// (embed.js). Each saves the settings it changes and then calls onChange.

// Slice tables keep atoms whose fractional coordinates lie in [min, max];
// blank = no limit. `key` names the bounds in viewerPrefs.
function createSliceTable(key, onChange, labelPrefix = "") {
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
}
// Element checkboxes: unchecked elements (of `species`) are listed in viewerPrefs[key].
function createElementBoxes(key, species, onChange, labelPrefix) {
  return el("div", { class: "chips element-boxes" }, species.map((sym) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: !viewerPrefs[key].includes(sym), "aria-label": `${labelPrefix} ${sym}`, onchange: (event) => {
      const hiddenSet = new Set(viewerPrefs[key]);
      if (event.target.checked) hiddenSet.delete(sym); else hiddenSet.add(sym);
      viewerPrefs[key] = [...hiddenSet]; savePrefs(); onChange();
    } }),
    elementSwatch(sym), sym)));
}
// Show the stored bounds and elements in a slice table and its element boxes.
function syncSliceControls(sliceKey, elementKey, table, boxes, species) {
  table.querySelectorAll("input").forEach((input, n) => { input.value = viewerPrefs[sliceKey][Math.floor(n / 2)][n % 2] ?? ""; });
  boxes.querySelectorAll("input").forEach((input, n) => { input.checked = !viewerPrefs[elementKey].includes(species[n]); });
}
function resetSliceControls(sliceKey, elementKey, table, boxes, species) {
  viewerPrefs[sliceKey] = emptySlice();
  viewerPrefs[elementKey] = []; savePrefs();
  syncSliceControls(sliceKey, elementKey, table, boxes, species);
}

// Per-element colour and sphere radius of `species`, as a table body; its
// inputs are also used elsewhere (the structure page's element editor).
// Inputs for the same element show one value. onColour() follows a colour,
// onRadius() a radius. Returns { element, refresh, colourInputFor,
// radiusInputFor, setElementColour, setElementRadius }.
// Per-element radius inputs: the automatic radius as placeholder, and where it comes from.
const radiusInputTitle = (sym) => `Blank: automatic (${autoRadius(sym).toFixed(2)} Å, ${
  viewerPrefs.style === "stick" || viewerPrefs.style === "wireframe" ? "the bond radius" : radiusSource(sym, viewerPrefs.radiusType)})`;
// Placeholder and tooltip of a radius input; in space-filling, which ignores
// per-element radii, it is disabled with the reason as its tooltip (styleLocks).
function syncRadiusInput(input) {
  const lock = styleLocks().elementRadii;
  input.placeholder = autoRadius(input.dataset.symbol).toFixed(2);
  input.title = lock ?? radiusInputTitle(input.dataset.symbol);
  input.disabled = Boolean(lock);
  return input;
}
function refreshRadiusInputs() {
  document.querySelectorAll(".radius-input").forEach(syncRadiusInput);
}

function createElementStyles(species, { onColour, onRadius }) {
  const setElementColour = (sym, colour) => {
    if (colour === null || colour === defaultElementColor(sym)) delete viewerPrefs.appearance.colours[sym];
    else viewerPrefs.appearance.colours[sym] = colour;
    document.querySelectorAll(`input[data-colour-of="${sym}"]`).forEach((input) => { input.value = elementColor(sym); });
    savePrefs(); onColour();
  };
  const setElementRadius = (sym, radius) => {
    if (radius === null || !(radius > 0)) delete viewerPrefs.appearance.radii[sym];
    else viewerPrefs.appearance.radii[sym] = radius;
    document.querySelectorAll(`.radius-input[data-symbol="${sym}"]`).forEach((input) => { input.value = viewerPrefs.appearance.radii[sym] ?? ""; });
    savePrefs(); onRadius();
  };
  const colourInputFor = (sym) => el("input", { type: "color", value: elementColor(sym), "aria-label": `${sym} colour`, "data-colour-of": sym,
    oninput: (event) => setElementColour(sym, event.target.value) });
  const radiusInputFor = (sym) => syncRadiusInput(el("input", { type: "number", step: 0.05, min: 0.05, class: "num-input radius-input", "data-symbol": sym,
    value: viewerPrefs.appearance.radii[sym] ?? "", "aria-label": `${sym} radius`,
    onchange: (event) => {
      const value = optionalNumber(event.target.value);
      if (!(value > 0)) event.target.value = "";
      setElementRadius(sym, value);
    } }));
  const element = el("tbody");
  function refresh() {
    element.replaceChildren(...species.map((sym) => el("tr", {},
      el("td", {}, elementSwatch(sym), ` ${sym}`),
      el("td", { class: "element-colour" }, tagControl(colourInputFor(sym), "elements.colour")),
      el("td", {}, tagControl(radiusInputFor(sym), "elements.radius")),
      el("td", {}, el("button", { type: "button", class: "small reset-colour", title: `Default colour and size for ${sym}`, "data-control": "elements.reset",
        "aria-label": `Default style for ${sym}`, onclick: () => {
          delete viewerPrefs.appearance.radii[sym]; setElementColour(sym, null); refresh(); onRadius();
        } }, "↺")))));
  }
  refresh();
  return { element, refresh, colourInputFor, radiusInputFor, setElementColour, setElementRadius };
}

// Planes (viewerPrefs.planes). Miller planes: h*x + k*y + l*z = t in
// fractional coordinates (t = distance in units of d), with an "Add plane"
// button. The position is entered as t or as the distance from the origin in
// Å (t·d); the two fields follow each other, and t is what is stored, and the
// spacing d is listed. Each plane has an "Extend ×" field (its scale, see
// scalePolygon). Planes through atoms (see atomPlaneFit): "Plane
// through atoms" turns on the click mode "plane" of the measure panel
// (`measure()`, see createMeasurePanel), and "Add plane" makes a plane of the
// atoms clicked ("Make plane"); each such plane lists its fit (RMS deviation) on every one
// of structures(), or why it is not shown there.
// cell() is the shown structure's cell (for d). onChange() follows a change
// that needs a rebuild, onStyle() a colour. Returns { element, refresh,
// update } (update: the fit texts and the click mode, after measurements or
// the shown structure changed).
function createPlaneControls(cell, onChange, onStyle = onChange, { structures = () => [], measure = () => null } = {}) {
  const planeList = el("div", { class: "plane-list" });
  let rendered = [];
  const fitTexts = [];
  const remover = (index, label) => el("button", { type: "button", class: "small", title: "Remove plane", "aria-label": label, "data-control": "planes.remove", onclick: () => {
    viewerPrefs.planes.splice(index, 1); savePrefs(); refresh(); onChange();
  } }, "×");
  const shared = (plane, index) => [
    el("input", { type: "checkbox", checked: plane.show, "aria-label": "Show plane", "data-control": "planes.show", onchange: (event) => {
      plane.show = event.target.checked; savePrefs(); onChange();
    } }),
    el("input", { type: "color", class: "plane-colour", value: planeColour(plane, index), "aria-label": "Plane colour",
      title: "Plane colour", "data-control": "planes.colour", oninput: (event) => { plane.colour = event.target.value; savePrefs(); onStyle(); } })];
  // "Extend ×": the plane's scale (1 to 10; 1 is stored as no scale). With
  // single cell only, planes are clipped to the cell: a plane across the cell
  // fills its cut already, so the factor is locked (kept) for all but
  // patches, which it still extends up to the cell's faces.
  const extenders = [];
  const extendLock = (plane) => (viewerPrefs.singleCell && !(isAtomPlane(plane) && plane.patch)
    ? `${SINGLE_CELL_LOCK}: the plane is clipped to the cell` : null);
  const syncExtenders = () => { for (const [plane, label] of extenders) lockControl(label, extendLock(plane)); };
  const extender = (plane) => {
    const label = extenderField(plane);
    extenders.push([plane, label]);
    lockControl(label, extendLock(plane));
    return label;
  };
  const extenderField = (plane) => el("label", { class: "check plane-extend-field", "data-control": "planes.extend", title: "Extend the drawn plane in all in-plane directions about its centre (1 to 10 times)" },
    "Extend ×", el("input", { type: "number", class: "num-input plane-extend", min: MIN_PLANE_SCALE, max: MAX_PLANE_SCALE, step: 0.5,
      value: plane.scale ?? 1, "aria-label": "Extend factor", onchange: (event) => {
        const value = Number(event.target.value);
        if (!(event.target.value !== "" && isPlaneScale(value))) { event.target.value = plane.scale ?? 1; return; }
        if (value === 1) delete plane.scale; else plane.scale = value;
        savePrefs(); onChange();
      } }));
  function millerRow(plane, index) {
    const dLabel = el("span", { class: "muted plane-d" });
    const distance = el("input", { type: "number", step: 0.1, class: "num-input plane-distance",
      "aria-label": "Distance from origin (Å)", title: "Distance from the origin along the plane normal, in Å (t·d)",
      onchange: (event) => {
        // The field shows t·d rounded; a change event that only repeats
        // what it shows (the browser sends one on blur) must not move t.
        if (event.target.value === shownDistance) return;
        const d = dSpacing(cell(), plane), value = Number(event.target.value);
        if (!d || !Number.isFinite(value)) { updateD(); return; }
        plane.t = Number((value / d).toPrecision(10));
        tField.value = plane.t; savePrefs(); updateD(); onChange();
      } });
    const updateD = () => {
      const d = dSpacing(cell(), plane);
      dLabel.textContent = d ? `Å (d = ${d.toFixed(3)} Å)` : "invalid (0 0 0)";
      distance.disabled = !d;
      distance.value = d ? Number((plane.t * d).toFixed(3)) : "";
      shownDistance = distance.value;
    };
    let shownDistance = "";
    const field = (key, label, step = 1) => el("input", { type: "number", step, value: plane[key], class: "num-input plane-index",
      "aria-label": label, onchange: (event) => {
        plane[key] = Number(event.target.value) || 0; savePrefs(); updateD(); onChange();
      } });
    const tField = field("t", "Position t", 0.05);
    updateD();
    return el("div", { class: "plane-row" },
      el("div", { class: "inline-fields" }, ...shared(plane, index),
        "(", ...["h", "k", "l"].map((key) => tagControl(field(key, key), "planes.miller-indices")), ")", remover(index, "Remove plane")),
      el("div", { class: "inline-fields plane-position", "data-control": "planes.position" }, el("span", { class: "muted" }, "t"), tField, el("span", { class: "muted" }, "="), distance, dLabel),
      el("div", { class: "inline-fields" }, extender(plane)));
  }
  function atomRow(plane, index) {
    const fit = el("p", { class: "muted hint plane-fit", "data-control": "planes.fit-text" });
    fitTexts.push([plane, fit]);
    return el("div", { class: "plane-row atom-plane" },
      el("div", { class: "inline-fields" }, ...shared(plane, index),
        el("span", { class: "plane-atoms", title: `Through ${plane.atoms.map(refName).join(", ")} (′ marks a periodic image)` }, planeName(plane)),
        remover(index, `Remove ${planeName(plane)}`)),
      el("div", { class: "inline-fields" },
        el("label", { class: "check", title: "Draw a patch around the atoms instead of the plane across the shown cell", "data-control": "planes.patch" },
          el("input", { type: "checkbox", class: "plane-patch", checked: plane.patch, onchange: (event) => {
            plane.patch = event.target.checked; savePrefs(); syncExtenders(); onChange();
          } }), "Patch around the atoms"),
        extender(plane)),
      fit);
  }
  // The fit of each plane through atoms on each shown structure.
  const fitText = (plane, s) => {
    if (!s || !fitsStructure(s, plane.atoms)) return "Not shown: the atoms of this structure differ (count or elements).";
    const fit = atomPlaneFit(s, plane.atoms);
    if (!fit) return "Not shown: the atoms lie on a line.";
    return plane.atoms.length === MIN_PLANE_ATOMS ? "Through 3 atoms."
      : `${plane.atoms.length} atoms: RMS deviation ${fit.rms.toFixed(3)} Å, largest ${fit.max.toFixed(3)} Å.`;
  };
  function refresh() {
    rendered = [...viewerPrefs.planes];
    fitTexts.length = 0;
    extenders.length = 0;
    planeList.replaceChildren(...viewerPrefs.planes.map((plane, index) => (isAtomPlane(plane) ? atomRow(plane, index) : millerRow(plane, index))));
    if (!viewerPrefs.planes.length) planeList.append(el("p", { class: "muted hint" }, "h·x + k·y + l·z = t (fractional coordinates)."));
    update();
  }
  const pickButton = el("button", { type: "button", class: "small plane-pick", "data-control": "planes.pick-atoms", title: "Click 3 or more atoms in the structure, then Make plane", onclick: () => {
    measureState.mode = measureState.mode === "plane" ? "off" : "plane";
    measureState.pending = [];
    measure()?.changed();
  } }, "Plane through atoms");
  const finishButton = el("button", { type: "button", class: "small plane-finish", "data-control": "planes.make", title: "Add the plane through the clicked atoms",
    onclick: () => measure()?.finishPlane() }, "Make plane");
  const pickHint = el("span", { class: "muted plane-pick-hint" });
  function update() {
    if (rendered.length !== viewerPrefs.planes.length || rendered.some((p, k) => p !== viewerPrefs.planes[k])) { refresh(); return; }
    const shown = structures().filter(Boolean);
    for (const [plane, element] of fitTexts) {
      const texts = shown.map((s) => fitText(plane, s));
      element.textContent = shown.length > 1 ? texts.map((t, k) => `${shown[k].id ?? k + 1}: ${t}`).join(" ") : texts[0] ?? "";
    }
    const picking = measureState.mode === "plane", count = picking ? measureState.pending.length : 0;
    pickButton.textContent = picking ? "Stop picking" : "Plane through atoms";
    pickButton.classList.toggle("active", picking);
    finishButton.hidden = !picking;
    finishButton.disabled = count < MIN_PLANE_ATOMS;
    finishButton.textContent = `Make plane (${count} atom${count === 1 ? "" : "s"})`;
    pickHint.textContent = picking ? `Click ${count < MIN_PLANE_ATOMS ? `${MIN_PLANE_ATOMS - count} more atom${MIN_PLANE_ATOMS - count === 1 ? "" : "s"}` : "more atoms for a best fit, or Make plane"}.` : "";
  }
  const add = el("button", { type: "button", class: "small", "data-control": "planes.add-miller", onclick: () => {
    const colour = PLANE_COLOURS[viewerPrefs.planes.length % PLANE_COLOURS.length];
    viewerPrefs.planes.push({ h: 0, k: 0, l: 1, t: 0.5, show: true, colour }); savePrefs(); refresh(); onChange();
  } }, "Add plane");
  refresh();
  return { element: el("div", { class: "plane-controls" }, planeList,
    el("div", { class: "inline-fields" }, add, pickButton, finishButton, pickHint)), refresh, update, syncLocks: syncExtenders };
}

// Bond lengths per element pair of `species`: the shortest
// (viewerPrefs.bondMinimums, missing: 0) and the longest (the cutoff; missing
// ones get the default first). Returns { element (a table), pairs, refresh,
// reset }.
function createCutoffControls(species, onChange) {
  const pairs = [];
  for (const a of species) for (const b of species) if (a <= b) pairs.push([a, b]);
  for (const [a, b] of pairs) viewerPrefs.cutoffs[pairKey(a, b)] ??= defaultCutoff(a, b);
  const length = (value) => Math.max(0, Number(value) || 0);
  const minInputs = pairs.map(([a, b]) => el("input", { type: "number", step: 0.05, min: 0, value: viewerPrefs.bondMinimums[pairKey(a, b)] ?? 0,
    class: "num-input", "aria-label": `Shortest bond ${a}–${b}`, title: "Shorter bonds are not drawn",
    onchange: (event) => {
      const value = length(event.target.value);
      if (value) viewerPrefs.bondMinimums[pairKey(a, b)] = value; else delete viewerPrefs.bondMinimums[pairKey(a, b)];
      savePrefs(); onChange();
    } }));
  const inputs = pairs.map(([a, b]) => el("input", { type: "number", step: 0.05, min: 0, value: viewerPrefs.cutoffs[pairKey(a, b)], class: "num-input",
    "aria-label": `Bond cutoff ${a}–${b}`,
    onchange: (event) => { viewerPrefs.cutoffs[pairKey(a, b)] = length(event.target.value); savePrefs(); onChange(); } }));
  const element = el("table", { class: "stats cutoffs", "data-control": "bonds.cutoffs" },
    el("thead", {}, el("tr", {}, el("th", {}, "Pair"), el("th", {}, "Min (Å)"), el("th", {}, "Max (Å)"))),
    el("tbody", {}, pairs.map(([a, b], k) => el("tr", {}, el("td", {}, `${a}–${b}`), el("td", {}, minInputs[k]), el("td", {}, inputs[k])))));
  const refresh = () => pairs.forEach(([a, b], k) => {
    viewerPrefs.cutoffs[pairKey(a, b)] ??= defaultCutoff(a, b);
    inputs[k].value = viewerPrefs.cutoffs[pairKey(a, b)];
    minInputs[k].value = viewerPrefs.bondMinimums[pairKey(a, b)] ?? 0;
  });
  const reset = () => {
    for (const [a, b] of pairs) { viewerPrefs.cutoffs[pairKey(a, b)] = defaultCutoff(a, b); delete viewerPrefs.bondMinimums[pairKey(a, b)]; }
    savePrefs(); refresh(); onChange();
  };
  return { element, pairs, refresh, reset };
}

// Hydrogen bonds (viewerPrefs.hbonds) and "Bonded atoms outside"
// (viewerPrefs.bondedOutside), for the Bonds settings of both viewers.
// Returns { hbonds, outside (elements), refresh }.
function createBondSearchControls(onChange) {
  const hb = () => viewerPrefs.hbonds;
  const changed = () => { savePrefs(); onChange(); };
  const number = (label, key, step, min, max, title) => el("input", { type: "number", step, min, max, class: "num-input", "aria-label": label, title,
    value: hb()[key], onchange: (event) => {
      const value = Number(event.target.value);
      if (Number.isFinite(value) && value >= min && value <= max) hb()[key] = value;
      if (hb().min > hb().max) [hb().min, hb().max] = [hb().max, hb().min];
      refresh(); changed();
    } });
  const show = el("input", { type: "checkbox", "aria-label": "Hydrogen bonds", onchange: (event) => { hb().show = event.target.checked; changed(); } });
  const acceptors = el("input", { type: "text", class: "num-input", style: "width:6rem", "aria-label": "Hydrogen bond acceptors",
    title: "Elements of acceptors A and donors D, separated by spaces or commas",
    onchange: (event) => {
      hb().acceptors = [...new Set(event.target.value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean)
        .map((x) => x[0].toUpperCase() + x.slice(1).toLowerCase()))];
      refresh(); changed();
    } });
  const min = number("Shortest H···A", "min", 0.05, 0, 10, "Shortest H···A distance (Å)");
  const max = number("Longest H···A", "max", 0.05, 0, 10, "Longest H···A distance (Å)");
  const angle = number("Smallest D–H···A angle", "angle", 5, 0, 180, "Smallest D–H···A angle at the H (degrees; 180 is straight)");
  const colour = el("input", { type: "color", "aria-label": "Hydrogen bond colour", value: hb().colour,
    oninput: (event) => { hb().colour = event.target.value; changed(); } });
  // Per-acceptor H···A ranges: one row per acceptor element, kept while the
  // element is listed (so focus survives a refresh). A row without a stored
  // range shows the single one; editing either field stores both, and the
  // row's ↺ (shown only then) removes it again.
  const perAcceptor = el("input", { type: "checkbox", "aria-label": "Per acceptor H···A ranges",
    onchange: (event) => { hb().perAcceptor = event.target.checked; refresh(); changed(); } });
  const rangeList = el("div", { class: "hbond-ranges" });
  const rangeRows = new Map();
  function rangeRow(symbol) {
    const store = () => {
      const values = [Number(low.value), Number(high.value)];
      if (values.every((v) => Number.isFinite(v) && v >= 0 && v <= 10)) hb().ranges[symbol] = values[0] <= values[1] ? values : [values[1], values[0]];
      refresh(); changed();
    };
    const field = (label, title) => el("input", { type: "number", step: 0.05, min: 0, max: 10, class: "num-input", "aria-label": label, title, onchange: store });
    const low = field(`Shortest H···${symbol}`, `Shortest H···${symbol} distance (Å)`);
    const high = field(`Longest H···${symbol}`, `Longest H···${symbol} distance (Å)`);
    const reset = el("button", { type: "button", class: "small reset-colour", title: "Use the single H···A range",
      "aria-label": `Single H···A range for ${symbol}`, onclick: () => { delete hb().ranges[symbol]; refresh(); changed(); } }, "↺");
    const row = el("div", { class: "inline-fields" }, el("span", { class: "field-label hbond-label" }, `H···${symbol}`), low, "–", high, el("span", { class: "field-label" }, "Å"), reset);
    return { row, low, high, reset };
  }
  function refreshRanges() {
    rangeList.hidden = !hb().perAcceptor;
    for (const [symbol, entry] of rangeRows) if (!hb().acceptors.includes(symbol)) { entry.row.remove(); rangeRows.delete(symbol); }
    for (const symbol of hb().acceptors) if (!rangeRows.has(symbol)) rangeRows.set(symbol, rangeRow(symbol));
    // Rows in the order of the acceptors, moved only when that changes: a
    // row moved between mousedown and mouseup (a blur's refresh) loses the
    // click on its ↺.
    const rows = hb().acceptors.map((symbol) => rangeRows.get(symbol).row);
    if (rows.length !== rangeList.children.length || rows.some((row, k) => rangeList.children[k] !== row)) rangeList.replaceChildren(...rows);
    for (const symbol of hb().acceptors) {
      const entry = rangeRows.get(symbol);
      const own = Object.hasOwn(hb().ranges, symbol);
      const range = own ? hb().ranges[symbol] : [hb().min, hb().max];
      entry.low.value = range[0]; entry.high.value = range[1];
      entry.reset.hidden = !own;
    }
  }
  const hbonds = el("div", { class: "hbond-controls" },
    el("label", { class: "check", "data-control": "hbonds.show" }, show, "Hydrogen bonds (D–H···A, dashed)"),
    el("div", { class: "inline-fields", "data-control": "hbonds.acceptors" }, el("span", { class: "field-label" }, "Acceptors"), acceptors, colour),
    el("div", { class: "inline-fields", "data-control": "hbonds.distance" }, el("span", { class: "field-label hbond-label" }, "H···A"), min, "–", max, el("span", { class: "field-label" }, "Å")),
    el("label", { class: "check", title: "A H···A range of its own for each acceptor element (rows start from the range above)", "data-control": "hbonds.per-acceptor" }, perAcceptor, "Per acceptor"),
    tagControl(rangeList, "hbonds.per-acceptor"),
    el("div", { class: "inline-fields", "data-control": "hbonds.angle" }, el("span", { class: "field-label" }, "Angle D–H···A ≥"), angle, el("span", { class: "field-label" }, "°")),
    el("p", { class: "muted hint" }, "D is the atom bonded to the H, of an acceptor element."));
  const outsideSelect = el("select", { "aria-label": "Bonded atoms outside", onchange: (event) => { viewerPrefs.bondedOutside = event.target.value; changed(); } },
    [["hide", "hide"], ["partners", "show partners"], ["ligands", "show polyhedron ligands"]].map(([value, text]) => el("option", { value }, text)));
  const outside = el("label", { class: "inline-fields", "data-control": "bonds.outside", title: "Atoms outside the repeat or the slice that are bonded to shown atoms: drawn (one step, with their bonds) or not. They are not counted as shown atoms." },
    el("span", { class: "field-label" }, "Bonded atoms outside"), outsideSelect);
  // Single cell only hides them (see SINGLE_CELL_LOCK): shown as "hide",
  // the choice kept.
  const syncOutside = () => {
    outsideSelect.value = viewerPrefs.singleCell ? "hide" : viewerPrefs.bondedOutside;
    lockControl(outside, singleCellLock());
  };
  function refresh() {
    show.checked = hb().show;
    acceptors.value = hb().acceptors.join(" ");
    min.value = hb().min; max.value = hb().max; angle.value = hb().angle; colour.value = hb().colour;
    perAcceptor.checked = hb().perAcceptor;
    refreshRanges();
    syncOutside();
  }
  refresh();
  return { hbonds, outside, refresh, syncOutside };
}

// Text of a transformation matrix: "[[2, 1, 0], [-1, 1, 0], [0, 0, 1]]".
const matrixRowsText = (matrix) => `[${matrix.map((row) => `[${row.join(", ")}]`).join(", ")}]`;
// One line on the shown cell when a transformation matrix is in use (for the
// Info tab and the notebook's status line); null without one.
function transformNote(s) {
  if (!viewerPrefs.repeatMatrix) return null;
  const shown = shownCell(s, []);
  if (!shown.transformed) return `Transformation matrix not applied: ${shown.note}.`;
  return `Shown: the cell transformed by ${matrixRowsText(shown.matrix)} (${shown.copies} cell cop${shown.copies === 1 ? "y" : "ies"}${
    shown.note ? `; ${shown.note}` : ""}). Display only: these numbers and saved files are for the stored cell.`;
}

// Controls of the transformation matrix (both viewers): a check box that
// switches it on (starting from the repeat), 3 × 3 whole-number fields
// (rows: the new a, b, c in units of the stored ones), presets for surface
// cells, the stored cell's outline, and a line with the number of copies or
// what is wrong with the entries (the last valid matrix stays shown).
// `structure()` is the shown structure; `onChange()` follows each change of
// the settings. Returns { element, sync }.
const STORED_TITLE = "Also draw the stored cell, dotted";
function createRepeatMatrixControls({ structure, onChange }) {
  const toggle = el("input", { type: "checkbox", "aria-label": "Transformation matrix" });
  const fields = [0, 1, 2].map((i) => [0, 1, 2].map((j) => el("input", { type: "number", step: 1, min: -MAX_REPEAT, max: MAX_REPEAT,
    class: "num-input matrix-input", "aria-label": `Matrix row ${i + 1} column ${j + 1}` })));
  const preset = el("select", { "aria-label": "Matrix preset" });
  const stored = el("input", { type: "checkbox", "aria-label": "Stored cell outline" });
  const status = el("p", { class: "muted hint repeat-matrix-status" });
  const grid = el("div", { class: "matrix-grid", "data-control": "cell.matrix-entries", title: "Rows: the shown cell's a, b and c in units of the stored a, b and c" },
    ...fields.map((row, i) => el("div", { class: "inline-fields matrix-row" }, el("span", { class: "field-label" }, `${"abc"[i]}′ =`), ...row)));
  const toggleLabel = el("label", { class: "check", "data-control": "cell.matrix", title: "Show a cell given by an integer matrix (such as a surface reconstruction) instead of the repeat" },
    toggle, "Transformation matrix");
  const body = el("div", { class: "repeat-matrix-body" }, grid,
    el("div", { class: "inline-fields", "data-control": "cell.matrix-preset" }, el("span", { class: "field-label" }, "Preset"), preset),
    el("label", { class: "check", title: STORED_TITLE, "data-control": "cell.stored-outline" }, stored, "Stored cell outline too"), status);
  const changed = () => { savePrefs(); onChange(); sync(); };
  function apply() {
    const matrix = fields.map((row) => row.map((f) => (f.value.trim() === "" ? NaN : Number(f.value))));
    const problem = repeatMatrixProblem(matrix);
    for (const f of fields.flat()) f.classList.toggle("invalid", Boolean(problem));
    if (problem) { status.textContent = `${problem} The last valid matrix stays shown.`; status.classList.add("error"); return; }
    viewerPrefs.repeatMatrix = checkRepeatMatrix(matrix);
    changed();
  }
  for (const f of fields.flat()) f.addEventListener("change", apply);
  toggle.addEventListener("change", () => {
    viewerPrefs.repeatMatrix = toggle.checked ? diagonalMatrix(viewerPrefs.repeat) : null;
    changed();
  });
  preset.addEventListener("change", () => {
    const chosen = repeatPresets(structure())[Number(preset.value)];
    preset.value = "";
    if (!chosen) return;
    viewerPrefs.repeatMatrix = chosen[1].map((row) => [...row]);
    changed();
  });
  stored.addEventListener("change", () => { viewerPrefs.storedCellOutline = stored.checked; changed(); });
  function sync() {
    // Single cell only applies no matrix: shown as without one (the stored
    // matrix is kept, see SINGLE_CELL_LOCK).
    const matrix = viewerPrefs.singleCell ? null : viewerPrefs.repeatMatrix;
    toggle.checked = Boolean(matrix);
    body.hidden = !matrix;
    // Outline every copy draws the stored cells already: the box is locked
    // (shown ticked) and the setting kept for when it is off again.
    const included = viewerPrefs.repeatCellOutline;
    stored.checked = included || viewerPrefs.storedCellOutline;
    // Single cell only ignores the matrix (see SINGLE_CELL_LOCK): every
    // control here is locked, the matrix kept.
    const single = singleCellLock();
    stored.disabled = included || Boolean(single);
    stored.parentElement.title = single ?? (included ? "Included in “Outline every copy”" : STORED_TITLE);
    stored.parentElement.classList.toggle("muted", included || Boolean(single));
    lockControl(toggleLabel, single);
    for (const f of fields.flat()) f.disabled = Boolean(single);
    preset.disabled = Boolean(single);
    grid.title = single ?? "Rows: the shown cell's a, b and c in units of the stored a, b and c";
    preset.replaceChildren(el("option", { value: "" }, "Choose…"),
      ...repeatPresets(structure()).map(([label, , title], k) => el("option", { value: k, title }, label)));
    for (const f of fields.flat()) f.classList.remove("invalid");
    status.classList.remove("error");
    if (!matrix) { status.textContent = ""; return; }
    fields.forEach((row, i) => row.forEach((f, j) => { f.value = matrix[i][j]; }));
    const shown = shownCell(structure(), []);
    status.textContent = shown.transformed
      ? `${shown.copies} cell cop${shown.copies === 1 ? "y" : "ies"}${shown.note ? ` (${shown.note})` : ""}. Display only: the Info tab and saved files keep the stored cell.`
      : `Not applied: ${shown.note}.`;
  }
  sync();
  const element = el("div", { class: "repeat-matrix" }, toggleLabel, body);
  return { element, sync };
}

// Coordination polyhedron centres (viewerPrefs.polyCenters; null: the
// transition metals) among the metals of `species`. Returns { element, refresh }.
function createCentreControls(species, onChange) {
  const metals = species.filter((s) => !NONMETALS.has(s));
  const centres = () => viewerPrefs.polyCenters ?? species.filter((s) => TRANSITION_METALS.has(s));
  const boxes = metals.map((sym) => el("input", { type: "checkbox", checked: centres().includes(sym), "aria-label": `Polyhedra around ${sym}`, onchange: () => {
    viewerPrefs.polyCenters = metals.filter((s, k) => boxes[k].checked);
    savePrefs(); onChange();
  } }));
  const element = el("div", { class: "chips", "data-control": "polyhedra.centres" }, metals.map((sym, k) => el("label", { class: "check" }, boxes[k], sym)));
  const refresh = () => boxes.forEach((box, k) => { box.checked = centres().includes(metals[k]); });
  return { element, refresh };
}

// ---------------------------------------------------------------- colour by property

// Atoms that are shown (slice and hidden elements), and the numbers among a
// property's values (`d`, from propertyValues) of the shown atoms.
const shownAtoms = (s) => {
  const recip = reciprocal(s.cell), hidden = new Set(viewerPrefs.hiddenElements);
  return positionsOf(s).map((p, i) => !hidden.has(s.symbols[i]) && inSlice(fractional(recip, p)));
};
const shownNumbers = (s, d) => {
  if (!d || d.text) return [];
  const shown = shownAtoms(s);
  return d.values.filter((v, i) => shown[i] && v !== null && Number.isFinite(v));
};
const extent = (values) => values.reduce(([lo, hi], v) => [Math.min(lo, v), Math.max(hi, v)], [Infinity, -Infinity]);

// Element colours, with the height in the tooltip.
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

// Colour by viewerPrefs.property: one overlay per structure (one colour
// scale for all), the legend's nodes and notes. `range(data)` gives the
// automatic [lo, hi] of continuous values (data: per structure, from
// propertyValues); `current()` is false once the result is no longer wanted,
// and the result is then null.
async function propertyOverlays({ structures, range, current = () => true }) {
  const settings = viewerPrefs.property;
  const notes = [];
  let data = structures.map(() => null);
  try {
    data = await Promise.all(structures.map((s) => propertyValues(s, settings.choice, settings.component)));
  } catch (error) {
    notes.push(error.message);
  }
  if (!current()) return null;
  const first = data.find(Boolean);
  if (!first) {
    return { notes, overlays: structures.map(elementOverlay), legend: [el("span", { class: "muted" }, settings.choice
      ? `This structure has no ${settings.choice.name}; choose another property under Colour.` : "Choose a property under Colour.")] };
  }
  const unit = first.unit ? ` ${first.unit}` : "";
  const missing = (v) => v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v));
  const describe = (s, d) => (i) => [[s.symbols[i], `atom ${i}`], [`${valueText(d.values[i])}${missing(d.values[i]) ? "" : unit}`, first.label]];
  let colourOf, legend;
  if (asCategories(first.values, settings.kind, first.text)) {
    colourOf = (v) => categoryColour(v);
    // Legend: every value among the shown atoms, with its atom count.
    const counts = new Map();
    structures.forEach((s, k) => {
      const shown = shownAtoms(s);
      data[k]?.values.forEach((v, i) => { if (shown[i] && !missing(v)) counts.set(v, (counts.get(v) ?? 0) + 1); });
    });
    const values = [...counts.keys()].sort((a, b) => (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true })));
    legend = [el("div", { class: "muted" }, first.label),
      el("div", { class: "legend category-legend" }, values.slice(0, 40).map((v) => el("span", { title: `${counts.get(v)} atoms` },
        el("i", { class: "swatch", style: `background:${categoryColour(v)}` }), `${valueText(v)}${unit}`)),
      values.length > 40 ? el("span", {}, `… ${values.length - 40} more`) : null)];
  } else {
    let [lo, hi] = [0, 1];
    try { [lo, hi] = await range(data); } catch (error) { notes.push(error.message); }
    if (!current()) return null;
    if (!Number.isFinite(lo)) [lo, hi] = [0, 1];
    if (settings.symmetric) { const m = Math.max(Math.abs(lo), Math.abs(hi)); [lo, hi] = [-m, m]; }
    if (settings.min !== null) lo = settings.min;
    if (settings.max !== null) hi = settings.max;
    colourOf = (v) => ramp("property", (v - lo) / (hi - lo || 1));
    legend = [rampLegend("property", `${valueText(lo)}${unit}`, `${valueText(hi)}${unit}`,
      `${first.label} per atom${settings.min !== null || settings.max !== null ? " · values outside the range get its end colours" : ""}`)];
  }
  if (data.slice(1).some((d) => !d)) notes.push(`The compared structure has no ${settings.choice.name}; it is shown in element colours.`);
  if (data.some((d) => d?.values.some(missing))) notes.push("Atoms without a value keep their element colours.");
  const overlays = structures.map((s, k) => {
    const d = data[k];
    return d ? {
      colour: (i, symbol) => (missing(d.values[i]) ? elementColor(symbol) : colourOf(d.values[i])),
      describe: describe(s, d),
      value: (i) => (missing(d.values[i]) ? "" : valueText(d.values[i])),
    } : elementOverlay(s);
  });
  return { overlays, legend, notes };
}

// Controls of viewerPrefs.property: which property (one of `options`, see
// propertyOptions), the component of a vector, categories or a range, and
// the range's limits. onChange() follows every change (settings saved);
// refresh() shows the settings again (after an import or a change from
// Python). Returns { element, refresh }.
function createPropertyControls(options, onChange) {
  const property = () => viewerPrefs.property;
  const propertySelect = el("select", { "aria-label": "Atomic property" });
  const componentSelect = el("select", { "aria-label": "Vector component" },
    VECTOR_COMPONENTS.map(([value, label]) => el("option", { value }, label)));
  const componentField = el("label", { "data-control": "colour.component" }, el("span", { class: "muted" }, "Component"), componentSelect);
  const fillPropertySelect = () => {
    const current = choiceKey(property().choice);
    const groups = [...new Set(options.map((o) => o.group))];
    propertySelect.replaceChildren(
      current && !options.some((o) => o.key === current)
        ? el("option", { value: current, selected: true }, `${property().choice.name} (not on this structure)`) : null,
      ...groups.map((group) => el("optgroup", { label: group }, options.filter((o) => o.group === group).map((o) =>
        el("option", { value: o.key, selected: o.key === current }, o.label)))));
    componentField.hidden = options.find((o) => o.key === current)?.kind !== "vector";
  };
  const kindSelect = el("select", { "aria-label": "Read values as" },
    [["auto", "Automatic"], ["continuous", "A range of values"], ["categories", "Categories"]].map(([value, label]) =>
      el("option", { value }, label)));
  const changed = () => { savePrefs(); fillPropertySelect(); onChange(); };
  const rangeInputs = ["min", "max"].map((key) => el("input", { type: "number", step: "any", class: "num-input", placeholder: "auto",
    "aria-label": `Colour range ${key === "min" ? "minimum" : "maximum"}`,
    onchange: (event) => { property()[key] = optionalNumber(event.target.value); changed(); } }));
  const symmetricBox = el("input", { type: "checkbox", onchange: (event) => {
    property().symmetric = event.target.checked; changed();
  } });
  // Without a choice: the first property stored with the structure or its
  // evaluations, else the coordination number.
  const refresh = () => {
    if (!property().choice && options.length) property().choice = (options.find((o) => o.choice.source !== "derived") ?? options[0]).choice;
    fillPropertySelect();
    componentSelect.value = property().component;
    kindSelect.value = property().kind;
    rangeInputs.forEach((input, k) => { input.value = property()[k ? "max" : "min"] ?? ""; });
    symmetricBox.checked = property().symmetric;
  };
  propertySelect.addEventListener("change", () => {
    const option = options.find((o) => o.key === propertySelect.value);
    if (!option) return;
    property().choice = option.choice;
    property().min = property().max = null; rangeInputs.forEach((input) => { input.value = ""; });
    changed();
  });
  componentSelect.addEventListener("change", () => { property().component = componentSelect.value; changed(); });
  kindSelect.addEventListener("change", () => { property().kind = kindSelect.value; changed(); });
  refresh();
  const element = el("div", { class: "error-controls" },
    el("label", { "data-control": "colour.property" }, el("span", { class: "muted" }, "Property"), propertySelect),
    componentField,
    el("label", { "data-control": "colour.read-as" }, el("span", { class: "muted" }, "Read values as"), kindSelect),
    el("div", { class: "inline-fields", "data-control": "colour.range" }, el("span", { class: "muted" }, "Range"), rangeInputs[0], "–", rangeInputs[1]),
    el("label", { class: "check", "data-control": "colour.symmetric" }, symmetricBox, "Symmetric around 0"),
    el("p", { class: "muted hint" }, "Automatic: whole numbers with at most 12 values (such as tags) are categories. Blank range ends follow the shown atoms; the diverging palette suits signed values."));
  return { element, refresh };
}

// The two colours of the custom palette (shared by every colouring and the
// rings); shown wherever the custom palette is chosen. onChange() follows a
// change.
function customPaletteInputs(onChange) {
  return el("div", { class: "inline-fields custom-palette" },
    el("span", { class: "field-label" }, "From"), ...[0, 1].flatMap((k) => [
      el("input", { type: "color", value: viewerPrefs.customPalette[k], "aria-label": k ? "Custom palette high colour" : "Custom palette low colour",
        oninput: (event) => {
          viewerPrefs.customPalette[k] = event.target.value; savePrefs();
          document.querySelectorAll(".custom-palette input[type=color]").forEach((input, n) => { input.value = viewerPrefs.customPalette[n % 2]; });
          onChange();
        } }),
      k ? null : el("span", { class: "field-label" }, "to")]));
}

// Palette of the current value colouring (viewerPrefs.colour); each mode
// remembers its own. Hidden for modes without one (element colours).
// onChange() follows a choice, onCustom() a custom colour. Returns
// { element, refresh }.
function createPaletteControls(onChange, onCustom = onChange) {
  const paletteSelect = el("select", { "aria-label": "Colour palette" });
  const paletteField = el("label", { class: "palette-field", "data-control": "colour.palette" }, el("span", { class: "muted" }, "Palette"), paletteSelect);
  const customPaletteField = tagControl(customPaletteInputs(onCustom), "colour.custom-palette");
  const element = el("section", { class: "control-section" }, el("h4", {}, "Colour map"), paletteField, customPaletteField);
  const refresh = () => {
    const mode = viewerPrefs.colour;
    element.hidden = !(mode in DEFAULT_PALETTES);
    const current = viewerPrefs.palettes[mode] ?? DEFAULT_PALETTES[mode];
    customPaletteField.hidden = current !== "custom";
    paletteSelect.replaceChildren(...Object.entries(PALETTES).map(([value, palette]) =>
      el("option", { value, selected: current === value }, palette.label)));
    customPaletteField.querySelectorAll("input[type=color]").forEach((input, n) => { input.value = viewerPrefs.customPalette[n]; });
  };
  refresh();
  paletteSelect.addEventListener("change", () => {
    viewerPrefs.palettes[viewerPrefs.colour] = paletteSelect.value; savePrefs();
    customPaletteField.hidden = paletteSelect.value !== "custom";
    onChange();
  });
  return { element, refresh };
}

// Measurements: pick atoms by clicking them in panels() (see measureState);
// values are listed for each of structures(). `stages` gets the class
// "measuring" while clicks measure, `clickMode` says what a click does, and
// onChange() follows every change (the page redraws its atom colours); `where`
// names the measure controls in hints. Also
// handles the click mode "select" of the page's atom colours, and the mode
// "polyhedron": a click adds the atom's coordination polyhedron
// (measureState.polyhedra, see polyhedronOf) to the list "Polyhedra".
// Returns { controls, render, changed, cancel, pick }.
function createMeasurePanel({ structures, panels, stages, clickMode, onChange, where = "Measure tab" }) {
const measureList = el("div", { class: "measure-list", "data-control": "measure.list" });
const polyList = el("div", { class: "polyhedron-list" });
const measureHint = el("p", { class: "muted hint" });
// Plane choices of the plane measurements (indices into viewerPrefs.planes).
const planeChoice = el("div", { class: "inline-fields plane-choice", "data-control": "measure.plane-choice" });
const chosenPlanes = [0, 1];
const listeners = new Set();
const atomName = refName;
const measureName = (item) => (item.kind === "plane-angle" ? `∠ ${item.planes.map(planeName).join(" / ")}`
  : item.kind === "plane-distance" ? `${item.atoms.map(atomName).join("")} → ${planeName(item.planes[0])}`
  : item.atoms.map(atomName).join("–"));
const usablePlanes = () => viewerPrefs.planes.map((plane, k) => ({ plane, k }))
  .filter(({ plane }) => isAtomPlane(plane) || plane.h || plane.k || plane.l);
const planeSelect = (slot) => {
  const choices = usablePlanes();
  if (!choices.some(({ k }) => k === chosenPlanes[slot])) chosenPlanes[slot] = choices[Math.min(slot, choices.length - 1)]?.k ?? 0;
  return el("select", { class: "plane-select", "aria-label": slot ? "Second plane" : "Plane", onchange: (event) => {
    chosenPlanes[slot] = Number(event.target.value); renderMeasurements();
  } }, choices.map(({ plane, k }) => el("option", { value: k, selected: k === chosenPlanes[slot] }, `${k + 1}: ${planeName(plane)}`)));
};
function renderPlaneChoice() {
  const mode = measureState.mode;
  if (!MEASURE_PLANES[mode]) { planeChoice.replaceChildren(); return; }
  if (!usablePlanes().length) {
    planeChoice.replaceChildren(el("span", { class: "muted" }, "Add a plane first (Miller or through atoms; Planes)."));
    return;
  }
  if (mode === "plane-distance") { planeChoice.replaceChildren(el("span", { class: "muted" }, "Plane"), planeSelect(0)); return; }
  planeChoice.replaceChildren(planeSelect(0), el("span", { class: "muted" }, "and"), planeSelect(1),
    el("button", { type: "button", class: "small plane-angle-add", onclick: () => {
      const [a, b] = chosenPlanes.map((k) => viewerPrefs.planes[k]);
      if (!a || !b) return;
      measureState.items.push({ kind: "plane-angle", atoms: [], planes: [planeDefinition(a), planeDefinition(b)] });
      measurementsChanged();
    } }, "Measure angle"));
}
function renderMeasurements() {
  const mode = measureState.mode;
  const need = MEASURE_ATOMS[mode];
  const polyMode = mode === "polyhedron", planeMode = mode === "plane";
  // A distance to a plane needs a plane to click towards.
  const clicking = Boolean(need) && (mode !== "plane-distance" || usablePlanes().length > 0);
  stages.classList.toggle("measuring", clicking || polyMode || planeMode || mode === "select");
  measureSelect.value = need || polyMode || MEASURE_PLANES[mode] ? mode : "off";
  const picked = measureState.pending.length;
  measureHint.textContent = polyMode ? "Click a centre atom: its bonded non-metals (bond cutoffs) are the ligands."
    : mode === "plane-angle" ? "Choose two planes (the angle between them, 0 to 90°)."
    : mode === "plane-distance" ? "Choose a plane, then click atoms: their signed distance along the plane normal."
    : !need ? "Choose what to measure, then click atoms in the structure."
    : `Click ${need - picked} more atom${need - picked === 1 ? "" : "s"}`
      + `${picked ? ` (after ${measureState.pending.map(atomName).join(", ")}); Esc cancels` : ""}.`;
  renderPlaneChoice();
  const selecting = mode === "select";
  const planeHint = `Clicking atoms picks them for a plane (Planes): ${picked} picked${picked ? ` (${measureState.pending.map(atomName).join(", ")})` : ""}`
    + `${picked < MIN_PLANE_ATOMS ? `, ${MIN_PLANE_ATOMS} needed` : ""}; clicking an atom again drops it.`;
  clickMode.replaceChildren(...(clicking || selecting || polyMode || planeMode ? [
    el("span", {}, selecting ? "Clicking atoms selects them for a colour (Colour tab)."
      : polyMode ? `Clicking an atom adds its coordination polyhedron (${where}).`
      : planeMode ? planeHint
      : `Clicking atoms measures ${mode === "position" ? "a position" : mode === "distance" ? "a distance" : mode === "plane-distance" ? "the distance to a plane" : `an ${mode}`} (${where}): ${measureHint.textContent}`),
    planeMode ? el("button", { type: "button", class: "small", disabled: picked < MIN_PLANE_ATOMS, onclick: finishPlane, "data-control": "planes.make" }, "Make plane") : null,
    el("button", { type: "button", class: "small", "data-control": "measure.stop", onclick: () => {
      measureState.mode = "off"; measureState.pending = []; measurementsChanged();
    } }, selecting ? "Stop selecting" : planeMode ? "Stop picking" : "Stop measuring")] : []));
  // A measurement shows "–" on a structure it does not fit (other atoms, or
  // a plane that cannot be placed there).
  const rows = measureState.items.map((item, k) => {
    const values = structures().map((s) => (s && fitsStructure(s, measureRefs(item)) ? measureValue(s, item) : null));
    const near = values[0]?.nearest;
    return el("div", { class: "measure-row", "data-kind": item.kind },
      el("span", { class: "measure-atoms", title: "′ marks a periodic image" }, measureName(item)),
      el("span", { class: "measure-value" }, values.map((v) => (v ? v.text : "–")).join(" | "),
        near ? el("span", { class: "muted" }, ` (nearest image ${near.toFixed(3)} Å)`) : null),
      el("button", { type: "button", class: "small", title: "Remove", "aria-label": "Remove measurement", onclick: () => {
        measureState.items.splice(k, 1); measurementsChanged();
      } }, "×"));
  });
  measureList.replaceChildren(...rows);
  if (measureState.items.length) {
    measureList.append(el("button", { type: "button", class: "small", onclick: () => {
      measureState.items = []; measureState.pending = []; measurementsChanged();
    } }, "Clear all"));
  }
  renderPolyhedra();
  for (const listener of listeners) listener();
}
// The plane through the atoms picked in mode "plane" (Planes).
function finishPlane() {
  const refs = measureState.pending;
  if (refs.length < MIN_PLANE_ATOMS) return;
  const shown = structures().find((s) => s && fitsStructure(s, refs));
  if (shown && !atomPlaneFit(shown, refs)) {
    clickMode.querySelector("span")?.append(" These atoms lie on a line: pick another.");
    return;
  }
  const colour = PLANE_COLOURS[viewerPrefs.planes.length % PLANE_COLOURS.length];
  viewerPrefs.planes.push({ atoms: refs.map(copyRef), show: true, patch: false, colour });
  measureState.pending = [];
  measureState.mode = "off";
  savePrefs();
  measurementsChanged();
}
// Polyhedra: one table per centre, a column per structure it applies to.
// Entries that apply to none of the structures are left out, with a note.
function renderPolyhedra() {
  const shown = structures();
  const rows = [], tables = [];
  let hiddenCount = 0;
  measureState.polyhedra.forEach((ref, k) => {
    const results = shown.map((s) => (s && fitsStructure(s, [ref]) ? polyhedronOf(s, ref.index) : null));
    if (!results.some(Boolean)) { hiddenCount += 1; return; }
    results.forEach((p, n) => { if (p) rows.push({ structure: shown[n].id, polyhedron: p }); });
    const head = el("tr", {}, el("th", {}, `${ref.symbol}${ref.index}`), ...(shown.length > 1 ? shown.map((s) => el("th", {}, s.id)) : []));
    tables.push(el("div", { class: "polyhedron-entry", "data-control": "measure.polyhedra-list" },
      el("table", { class: "stats polyhedron" }, el("thead", {}, head), el("tbody", {}, POLYHEDRON_FIELDS.map(([key, label, text]) =>
        el("tr", { "data-field": key }, el("th", {}, label), ...results.map((p) => el("td", {}, p ? text(p) || "–" : "–")))))),
      el("button", { type: "button", class: "small", title: "Remove", "aria-label": `Remove polyhedron ${ref.symbol}${ref.index}`, onclick: () => {
        measureState.polyhedra.splice(k, 1); measurementsChanged();
      } }, "×")));
  });
  const children = [];
  if (tables.length || hiddenCount) children.push(el("h4", {}, "Polyhedra"));
  children.push(...tables);
  if (hiddenCount) {
    children.push(el("p", { class: "muted hint polyhedra-hidden" },
      `${hiddenCount} polyhedr${hiddenCount === 1 ? "on is" : "a are"} not shown: the atoms of this structure differ (count or elements).`));
  }
  if (measureState.polyhedra.length) {
    children.push(el("div", { class: "inline-fields" },
      tables.length ? el("button", { type: "button", class: "small", title: "Copy the polyhedra as CSV to the clipboard", "data-control": "measure.polyhedra-csv", onclick: (event) => {
        const csv = polyhedraCsv(rows);
        const button = event.currentTarget;
        Promise.resolve(navigator.clipboard?.writeText(csv)).then(() => { button.textContent = "Copied"; },
          () => downloadText("polyhedra.csv", csv, "text/csv"));
      } }, "Copy as CSV") : null,
      el("button", { type: "button", class: "small", "data-control": "measure.polyhedra-clear", onclick: () => { measureState.polyhedra = []; measurementsChanged(); } }, "Clear polyhedra")));
  }
  polyList.replaceChildren(...children);
}
const measurementsChanged = () => { panels().forEach((p) => p.rebuild()); renderMeasurements(); onChange?.(); };
const measureSelect = el("select", { "aria-label": "Measure", "data-control": "measure.mode" },
  [["off", "Off"], ["position", "Position x, y, z (1 atom)"], ["distance", "Distance (2 atoms)"], ["angle", "Angle (3 atoms)"], ["dihedral", "Dihedral (4 atoms)"],
    ["plane-angle", "Plane angle (2 planes)"], ["plane-distance", "Distance to a plane (1 atom)"],
    ["polyhedron", "Polyhedron (click a centre)"]].map(([value, label]) =>
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
  if (measureState.mode === "polyhedron") {
    if (!measureState.polyhedra.some((r) => r.index === ref.index && r.count === ref.count && r.symbol === ref.symbol)) {
      measureState.polyhedra.push({ index: ref.index, image: [0, 0, 0], symbol: ref.symbol, count: ref.count });
    }
    measurementsChanged();
    return;
  }
  if (measureState.mode === "plane") {
    // Atoms of a plane: a second click drops the atom.
    const at = measureState.pending.findIndex((r) => r.index === ref.index && r.count === ref.count && r.image.every((n, k) => n === ref.image[k]));
    if (at >= 0) measureState.pending.splice(at, 1);
    else measureState.pending.push(ref);
    measurementsChanged();
    return;
  }
  const need = MEASURE_ATOMS[measureState.mode];
  if (!need) return;
  if (measureState.mode === "plane-distance") {
    if (!usablePlanes().some(({ k }) => k === chosenPlanes[0])) return;
    const plane = viewerPrefs.planes[chosenPlanes[0]];
    measureState.items.push({ kind: "plane-distance", atoms: [ref], planes: [planeDefinition(plane)] });
    measurementsChanged();
    return;
  }
  measureState.pending.push(ref);
  if (measureState.pending.length === need) {
    measureState.items.push({ kind: measureState.mode, atoms: measureState.pending });
    measureState.pending = [];
  }
  measurementsChanged();
};
panels().forEach((panel) => { panel.onPick = pickAtom; });
const cancel = () => {
  if (measureState.pending.length) measureState.pending = [];
  else if (measureState.mode === "select" && paintState.selected.length) paintState.selected = [];
  else return false;
  measurementsChanged();
  return true;
};
const measureControls = el("div", { class: "measure-controls" }, measureSelect, measureHint, planeChoice, measureList, polyList);
// listen(f): f runs after every render (the Planes tab follows the click mode "plane").
return { controls: measureControls, render: renderMeasurements, changed: measurementsChanged, cancel, pick: pickAtom, finishPlane,
  listen: (listener) => listeners.add(listener) };
}

// Vibrational modes of one structure: pick a q-point and a mode, then play
// it. The atoms of panel() move; at q ≠ 0 every cell copy of the repeat moves
// with its own phase. `modes` is the structure's modes (api .../modes); with
// structure.has_phonons the band structure and DOS go into `figures`.
// `disposed()` tells when the page has gone, `repeatChanged()` follows a
// repeat applied from the hint, `axesChanged()` (optional) the tripod set to
// the Cartesian axes for the wave vector. Returns { controls, stop } (stop:
// null when the modes could not be loaded).
function createVibrationPanel({ structure, modes, figures, panel, disposed, repeatChanged, axesChanged = null }) {
  if (modes.error) return { controls: [el("p", { class: "error" }, modes.error)], stop: null };
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
  // The group velocity's name, g as a subscript (that does not open up the line).
  const vgName = () => el("span", {}, "v", el("sub", { style: "line-height:0" }, "g"));

  const motion = () => {
    const vectors = point().displacements[vib.mode];
    // The atom that moves most moves by the amplitude.
    const largest = Math.max(1e-12, ...vectors.map((d) => Math.hypot(...d)));
    return { q: point().q, vectors, scale: prefs.amplitude / largest, amplitude: prefs.amplitude, phase: vib.phase,
      moving: vib.active, arrows: prefs.showArrows, bonds: prefs.bonds };
  };
  const show = () => {
    const target = panel();
    target.motion = vib.active || prefs.showArrows ? motion() : null;
    target.wave = prefs.waveVector && zoneScale ? waveScene() : null;
    target.rebuild();
  };

  // The wave vector q, reduced to the first Brillouin zone, and the group
  // velocity v_g of the mode (phonopy only) as arrows of the axis tripod,
  // which then shows the Cartesian axes alone (setTripodAxes). q is to
  // scale: one axis length is the farthest point of the zone. v_g is a
  // direction only; it is left out where it has none (at Γ, or below
  // VG_ZERO of the fastest mode at this q). Needs a 3D cell.
  const cell = structure.cell ?? [];
  const zoneScale = (structure.pbc ?? []).some(Boolean) && cell.length === 3
    && Math.abs(dot(cell[0], cross(cell[1], cell[2]))) > 1e-8 ? zoneExtent(cell) : 0;
  const VG_ZERO = 1e-3;
  let waveMemo = null;
  const waveState = () => {
    const p = point();
    if (waveMemo?.point === p && waveMemo.mode === vib.mode) return waveMemo.state;
    const { reduced, cartesian } = firstZonePoint(cell, p.q);
    const atGamma = norm(cartesian) <= 1e-9 * zoneScale;
    const velocities = p.group_velocities ?? null;
    let vg = null, note = null;
    if (atGamma) note = "q = Γ: no wave vector, and the group velocity has no direction; nothing is drawn.";
    else if (!velocities) note = "No group velocities for these modes (they come with phonopy force constants): only q is drawn.";
    else {
      const fastest = Math.max(0, ...velocities.map(norm)), v = velocities[vib.mode];
      if (fastest > 0 && norm(v) >= VG_ZERO * fastest) vg = unit(v);
      else note = [vgName(), " ≈ 0 for this mode: it has no direction to draw."];
    }
    const state = { reduced, q: atGamma ? null : mul(cartesian, 1 / zoneScale), vg, note };
    waveMemo = { point: p, mode: vib.mode, state };
    return state;
  };
  const waveScene = () => {
    const { q, vg } = waveState();
    return { q, vg, qColour: prefs.qColour, vgColour: prefs.vgColour, qDash: prefs.qDash, vgDash: prefs.vgDash, labels: prefs.waveLabels };
  };
  // The checkbox puts the tripod on the Cartesian axes; another choice of
  // axes unticks it (setTripodAxes, followed here after every saved setting).
  const waveInput = el("input", { type: "checkbox", checked: prefs.waveVector, onchange: () => {
    prefs.waveVector = waveInput.checked;
    if (prefs.waveVector) viewerPrefs.tripod.axes = "xyz";
    savePrefs(); axesChanged?.(); showWave(); show();
  } });
  const waveBox = el("label", { class: "check", "data-control": "vibration.wave-vector",
    title: "Draw the wave vector q (in the first Brillouin zone) and the mode's group velocity on the Cartesian axes" },
  waveInput, "Show wave vector on the axes");
  const waveInfo = el("div", { class: "hint muted" });
  const swatch = (colour, dash) => el("span", { "aria-hidden": "true",
    style: `display:inline-block;width:22px;margin-right:.35rem;vertical-align:middle;border-top:3px ${dash} ${colour}` });
  // The legend: q in reduced coordinates.
  function showWave() {
    waveInput.checked = prefs.waveVector;
    if (!prefs.waveVector || !zoneScale) { waveInfo.replaceChildren(); waveInfo.hidden = true; return; }
    const { reduced, q, note } = waveState();
    const rows = [];
    if (prefs.waveLegend) {
      if (q) {
        rows.push(el("div", {}, swatch(prefs.qColour, prefs.qDash), `q = ${qText(reduced)} (reduced)`));
      }
      if (point().group_velocities) {
        rows.push(el("div", {}, swatch(prefs.vgColour, prefs.vgDash), vgName(), ": group velocity of this mode; direction only, length arbitrary."));
      }
    }
    if (note) rows.push(el("div", {}, ...[note].flat()));
    waveInfo.replaceChildren(...rows);
    waveInfo.hidden = !rows.length;
  }
  // Settings changed elsewhere (the tripod's axes, an imported file).
  const followSettings = () => {
    if (disposed()) { savePrefsListeners.delete(followSettings); return; }
    if (waveInput.checked !== prefs.waveVector) { showWave(); show(); }
  };
  savePrefsListeners.add(followSettings);
  const waveStyle = () => { savePrefs(); showWave(); show(); };
  // `label`: the name as shown; `spoken`: the same for aria-label.
  const waveColour = (label, spoken, key) => el("label", { class: "inline-fields" }, el("span", { class: "muted" }, label),
    el("input", { type: "color", value: prefs[key], "aria-label": `${spoken} colour`, oninput: (event) => { prefs[key] = event.target.value; waveStyle(); } }));
  const waveDash = (label, spoken, key) => el("label", { class: "inline-fields" }, el("span", { class: "muted" }, label),
    el("select", { "aria-label": `${spoken} line style`, onchange: (event) => { prefs[key] = event.target.value; waveStyle(); } },
      Object.keys(CELL_DASHES).map((value) => el("option", { value, selected: prefs[key] === value }, value))));
  const waveCheck = (label, key) => el("label", { class: "check" },
    el("input", { type: "checkbox", checked: prefs[key], onchange: (event) => { prefs[key] = event.target.checked; waveStyle(); } }), label);
  const waveControls = zoneScale ? [waveBox, waveInfo,
    el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Wave vector arrows"),
      el("div", { class: "inline-fields", "data-control": "vibration.wave-colours" }, waveColour("q", "q", "qColour"), waveColour(vgName(), "v_g", "vgColour")),
      el("div", { class: "inline-fields", "data-control": "vibration.wave-styles" }, waveDash("q", "q", "qDash"), waveDash(vgName(), "v_g", "vgDash")),
      tagControl(waveCheck("Names at the tips", "waveLabels"), "vibration.wave-labels"),
      tagControl(waveCheck("Legend", "waveLegend"), "vibration.wave-legend"))] : [];

  const qSelect = el("select", { "aria-label": "q-point", "data-control": "vibration.q-point", onchange: () => {
    vib.q = Number(qSelect.value); vib.mode = firstMode(); fillModes(); showHint(); showWave(); show(); updatePlot();
  } }, modes.qpoints.map((p, k) => el("option", { value: k }, `q = ${qText(p.q)}`)));
  const modeSelect = el("select", { class: "mode-list", "aria-label": "Mode", "data-control": "vibration.mode", onchange: () => {
    vib.mode = Number(modeSelect.value); showWave(); show(); updatePlot();
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
    if (token !== qRequest || disposed()) return;
    qNote.textContent = "";
    modes.qpoints = data.qpoints; vib.q = 0;
    const frequencies = point().frequencies;
    if (frequency !== null) {
      vib.mode = frequencies.reduce((best, f, k) => (Math.abs(f - frequency) < Math.abs(frequencies[best] - frequency) ? k : best), 0);
    } else if (vib.mode >= frequencies.length) vib.mode = firstMode();
    fillModes(); showHint(); showWave(); show(); updatePlot(); showDirection();
  };
  const fieldsQ = () => qInputs.map((input) => Number(input.value) || 0);
  const qInputs = [0, 1, 2].map((k) => el("input", { type: "number", step: 0.05, class: "num-input",
    value: String(Number(point().q[k].toFixed(4))), "aria-label": `q along ${"abc"[k]}*`,
    onchange: () => goToQ(fieldsQ()) }));
  const qRow = el("div", { "data-control": "vibration.q-point" },
    el("span", { class: "field-label" }, "q-point (reduced, along a*, b*, c*)"),
    el("div", { class: "inline-fields repeat-row" }, el("span", { class: "muted", title: "Reduced coordinates of the primitive reciprocal lattice" }, "q"),
      ...qInputs, qNote));
  const directionInputs = [0, 1, 2].map((k) => el("input", { type: "number", step: 0.5, class: "num-input",
    value: "", placeholder: "0", "aria-label": `Direction to Γ along ${"abc"[k]}*`,
    onchange: () => goToQ(fieldsQ()) }));
  const directionNote = el("p", { class: "muted hint" });
  const directionRow = el("div", { "data-control": "vibration.direction" },
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
    const sideButton = el("button", { type: "button", class: "small", "data-control": "phonon.side" });
    const showSide = () => {
      figures.classList.toggle("side", prefs.plotSide);
      sideButton.textContent = prefs.plotSide ? "Below the structure" : "Beside the structure";
      sideButton.title = prefs.plotSide ? "Show the plot below the structure" : "Show the plot beside the structure";
    };
    // The structure panel changes width: fit the structure into it again.
    sideButton.addEventListener("click", () => {
      prefs.plotSide = !prefs.plotSide; savePrefs(); showSide();
      panel().fit(); viewChanged();
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

  const playButton = el("button", { type: "button", class: "small", "data-control": "vibration.play" }, "▶ Play");
  // One period lasts periodSeconds whatever the frequency.
  const tick = (now) => {
    if (!vib.playing || disposed()) return;
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
  const stopButton = el("button", { type: "button", class: "small", title: "Stop and return to the equilibrium structure", "data-control": "vibration.play", onclick: () => {
    pause(); finishRecording({ save: true }); vib.active = false; vib.phase = Math.PI / 2; show();
  } }, "Stop");

  // Video: the first panel's canvas as shown, for recordPeriods periods from
  // rest, so the video loops. WebM where the browser records it (Chrome,
  // Firefox), else MP4 (Safari).
  const recordButton = el("button", { type: "button", class: "small", title: "Record the vibration as a video", "data-control": "vibration.record" }, "● Record");
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
    const { renderer, stage } = panel();
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
      if (save && chunks.length && !disposed()) downloadText(name, new Blob(chunks, { type }), type.split(";")[0]);
    });
    renderer.onDraw = (scene, theme) => paintScene(canvas, scene, ...frame.layout, frame.scale, theme, true, { tripod: viewerPrefs.tripod.export });
    vib.active = true; vib.phase = Math.PI / 2;
    show();
    if (vib.playing) vib.last = performance.now(); else play();
    recorder.start();
    recordButton.textContent = "■ Stop recording";
    recording.timer = setTimeout(() => finishRecording({ save: true }), prefs.recordPeriods * prefs.periodSeconds * 1000);
  });
  const stop = () => { pause(); finishRecording({ save: false }); };

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
  const arrowsBox = el("label", { class: "check", "data-control": "vibration.arrows" }, el("input", { type: "checkbox", checked: prefs.showArrows, onchange: (event) => {
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
    applyButton = el("button", { type: "button", class: "small repeat-apply", "data-control": "vibration.apply-repeat", onclick: () => {
      viewerPrefs.repeat = fit.map(clampRepeat);
      viewerPrefs.repeatMatrix = null;
      savePrefs(); repeatChanged(); panel().fit(); viewChanged();
    } }, "Apply");
    syncApply();
    hint.replaceChildren(`Cell copies move with different phases at this q; a repeat of ${fit.join(" × ")} shows a whole wavelength. `, applyButton);
  };
  // Single cell only shows no repeat: Apply is locked meanwhile (see
  // SINGLE_CELL_LOCK); the hosts call syncApply when it is switched.
  let applyButton = null;
  function syncApply() {
    if (!applyButton) return;
    applyButton.disabled = viewerPrefs.singleCell;
    applyButton.title = singleCellLock() ?? "Set the repeat to this";
  }
  fillModes();
  showHint();
  updatePlot();
  showDirection();
  showWave();
  if (prefs.showArrows || (prefs.waveVector && zoneScale)) show();

  return { stop, syncApply, controls: [
    anyQ ? qRow : modes.qpoints.length > 1 ? qSelect : el("p", { class: "muted hint" }, `q = ${qText(point().q)}`),
    directionRow,
    modeSelect,
    el("div", { class: "button-row" }, playButton, stopButton, recordButton),
    el("div", { class: "inline-fields" },
      tagControl(numberField("Amplitude (Å)", "amplitude", { min: 0.01, max: 2, step: 0.05 }), "vibration.amplitude"),
      tagControl(numberField("Period (s)", "periodSeconds", { min: 0.2, max: 20, step: 0.1 }), "vibration.period")),
    tagControl(choice("Bonds while vibrating", "bonds", [["fixed", "Fixed (equilibrium)"], ["live", "Recomputed every frame"]], show), "vibration.bonds"),
    tagControl(choice("Frequency unit", "unit", [["THz", "THz"], ["cm-1", "cm⁻¹"]], () => { fillModes(); updatePlot(); }), "vibration.unit"),
    arrowsBox,
    ...waveControls,
    hint,
    el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Video"),
      tagControl(numberField("Periods", "recordPeriods", { min: 1, max: 20, step: 1 }), "vibration.video-periods"),
      tagControl(choice("Size", "videoSize", [["shown", "As shown"], ["720p", "1280 × 720"], ["1080p", "1920 × 1080"]], () => {}), "vibration.video-size"),
      tagControl(choice("Frame rate", "videoFps", [["30", "30 fps"], ["60", "60 fps"]], () => {}), "vibration.video-fps"))] };
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
  // What the control rules ask about this page (see controlContext).
  page.controlContext = () => {
    const stepCount = page.stepList?.list.length ?? 0, comparing = page.panels.length > 1;
    return controlContext(page.structures, { stepCount, comparing, fromAggregation: Boolean(fromAgg),
      hasVectors: page.structures.some((s) => s.evaluations.some((e) => e.vectors.length)),
      canDisplace: comparing || stepCount > 1,
      measurements: measureState.items.length, polyhedra: measureState.polyhedra.length, highlightGroups: paintState.groups.length });
  };

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
  const elementBar = el("div", { class: "element-bar", role: "toolbar", "aria-label": "Elements", "data-control": "elements.bar" });
  // Comparison: with what, which panel steps, swap (see renderCompareBar).
  const compareBar = el("div", { class: "compare-bar", "data-profile-place": "Compare" });
  const status = el("p", { class: "muted viewer-status" });
  const controls = el("aside", { class: "viewer-controls" });
  // Sits above the figure so stepping and the structure stay in view together.
  const relatedSection = el("section", { class: "related-bar", "aria-label": "Related structures", "data-profile-place": "Steps" });
  const evaluationsSection = el("section");
  // Beside the structure, the settings box is as tall as the structure (not
  // the phonon plot) and scrolls on its own, so both end at the same line and
  // the structure stays in view; in one column the settings are part of the
  // page. The phonon plot joins the structure in `figures`: below it, or
  // beside it (vibration.plotSide).
  // What a click on an atom does (measure or select), whichever tab is open.
  const clickMode = el("div", { class: "click-mode", role: "status" });
  const viewerMain = el("div", { class: "viewer-main" }, clickMode, stages, el("div", { class: "viewer-footer", "data-profile-place": "Element bar" }, elementBar, legend, ringLegend), status);
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
      pickField.replaceChildren(el("label", { class: "check inline-check", "data-control": "page.selected" }, box, "Selected"), note);
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
    role: "separator", "aria-label": "Resize structure panel", "data-control": "panel.resize" });
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

  // Displacement references on this page (see displacementReference): the
  // structure in the other panel, or a structure of the step list (loaded on
  // demand; the reference itself gets zero displacements).
  displacementReference = async (s) => {
    const { reference, frame } = viewerPrefs.displacement;
    if (reference === "compared") {
      if (page.structures.length < 2) return { reference: null, reason: "Open a comparison to take the compared structure as the reference." };
      return { reference: page.structures[1 - page.side] === s ? s : page.structures[1 - page.side] };
    }
    const list = page.stepList?.list;
    if (!list) return { reference: null, reason: "Displacements from a frame need the step list below the structure." };
    let k;
    if (reference === "first") k = 0;
    else if (reference === "frame") k = Math.min(frame, list.length - 1);
    else {
      const at = list.findIndex((r) => r.id === s.id);
      if (at < 0) return { reference: null, reason: "This structure is not in the step list, so it has no previous frame." };
      if (at === 0) return { reference: null, reason: "The first frame has no previous frame." };
      k = at - 1;
    }
    return { reference: list[k].id === s.id ? s : await loadStructure(list[k].id) };
  };
  const displacementInUse = () => (viewerPrefs.arrows.show && viewerPrefs.arrows.source === "displacement")
    || (viewerPrefs.colour === "property" && viewerPrefs.property.choice?.source === "derived" && viewerPrefs.property.choice?.name === "displacement");
  // Arrow data (as forceDataFor) of the displacements of s.
  const displacementArrows = (s, d) => ({ name: "Δr", unit: "Å", method: `from ${displacementReferenceText()}`,
    vectors: d.vectors, magnitudes: d.magnitudes, included: forceIncluded(s) });
  const displacementValues = async (s) => {
    const d = await displacementFor(s);
    return d.vectors ? { values: d.magnitudes, included: forceIncluded(s) } : null;
  };

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
    const arrows = viewerPrefs.arrows.show && viewerPrefs.arrows.source === "vectors";
    if (!forceTarget().chosen || !(arrows || viewerPrefs.colour === "force")) return page.structures.map(() => null);
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
      viewerPrefs.forceHiddenElements, viewerPrefs.wrap || viewerPrefs.singleCell, viewerPrefs.displacement, moviePeers().map((s) => s.id)]);
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
  async function propertyRange(data) {
    if (!page.movie) return extent(page.structures.flatMap((s, k) => shownNumbers(s, data[k])));
    const { choice, component } = viewerPrefs.property;
    const key = JSON.stringify(["property", choiceKey(choice), component, viewerPrefs.slice, viewerPrefs.hiddenElements,
      choice?.name === "coordination" ? [viewerPrefs.cutoffs, viewerPrefs.bondMinimums] : null, choice?.name === "ring" ? viewerPrefs.rings : null,
      choice?.name === "displacement" ? viewerPrefs.displacement : null,
      choice?.name === "equivalent" ? viewerPrefs.symmetry : null,
      viewerPrefs.wrap || viewerPrefs.singleCell, moviePeers().map((s) => s.id)]);
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
    // Displacements (arrows, Info tab); notes for the panel that steps.
    let arrowData = forceData;
    page.displacements = page.structures.map(() => null);
    if (displacementInUse()) {
      const results = await Promise.all(page.structures.map((s) => displacementFor(s).catch((error) => ({ reason: error.message }))));
      if (!current()) return;
      page.displacements = results.map((d) => (d.vectors ? d : null));
      const own = results[page.side];
      if (own.reason) notes.push(own.reason);
      if (own.cellsDiffer) notes.push("The cells differ: displacements take the reference's fractional coordinates in this cell.");
      if (viewerPrefs.arrows.source === "displacement") {
        arrowData = page.structures.map((s, k) => (page.displacements[k] ? displacementArrows(s, page.displacements[k]) : null));
      }
    }
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
      const result = await propertyOverlays({ structures: page.structures, range: propertyRange, current });
      if (!result) return;
      overlays.push(...result.overlays);
      notes.push(...result.notes);
      legend.replaceChildren(...result.legend);
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
    page.arrowData = arrowData;
    page.panels.forEach((panel, k) => { panel.overlay = overlays[k]; panel.forces = arrowData[k]; panel.rebuild(); });
    renderElementBar();
    renderInfo();
    updateForceSummary();
    renderMeasurements();
    renderRingSummary();
    // Wyckoff letters for the tooltips, loaded in the background.
    for (const s of page.structures) if (s.symbols.length <= SYMMETRY_AUTO_ATOMS) loadSymmetry(s).catch(() => {});
  }

  const notIncludedNote = (data) => (data.some((d) => d && d.included.some((x) => !x)) ? " · element colours: not included" : "");


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
      scene.extraAtoms ? ` (and ${scene.extraAtoms} bonded outside)` : ""}${
      scene.totalAtoms > LARGE_SCENE ? ` · a large repeat: drawing may be slow${
        viewerPrefs.style === "wireframe" ? "" : " (Style › Model › Wireframe draws fastest)"}` : ""}` : "";
    refreshRadiusInputs();
    renderRingSummary();
    // Polyhedra follow the cutoffs and the wrapping.
    if (measureState.polyhedra.length) renderMeasurements();
    renderElementBar();
  };

  // Slice tables and element boxes (see createSliceTable).
  const sliceTableFor = createSliceTable;
  const elementBoxesFor = (key, onChange, labelPrefix) => createElementBoxes(key, species, onChange, labelPrefix);
  const syncFilter = (sliceKey, elementKey, table, boxes) => syncSliceControls(sliceKey, elementKey, table, boxes, species);
  const resetFilter = (sliceKey, elementKey, table, boxes) => resetSliceControls(sliceKey, elementKey, table, boxes, species);
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
  const slider = (key, label, { min = 0, max = 1, step = 0.05, format = percent, group = "appearance", control } = {}) => {
    const output = el("output", { class: "muted" });
    const input = el("input", { type: "range", min, max, step, value: viewerPrefs[group][key], "aria-label": label });
    const show = () => { output.textContent = format(Number(input.value)); };
    input.addEventListener("input", () => {
      viewerPrefs[group][key] = Number(input.value); show(); savePrefs(); scheduleRebuild();
    });
    show();
    return el("label", { class: "slider-field", "data-setting": key, "data-control": control }, el("span", {}, label), input, output);
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
  // Per-element colour and sphere radius (also set from the element bar; see
  // createElementStyles).
  const elementStylePanel = createElementStyles(species, { onColour: () => elementColoursChanged(), onRadius: () => rebuildAll() });
  const { colourInputFor, radiusInputFor, setElementColour } = elementStylePanel;
  const elementStyles = elementStylePanel.element;
  const renderElementStyles = elementStylePanel.refresh;
  const styleSliders = () => [
    slider("atomScale", "Atom size (automatic radii)", { min: 0.3, max: MAX_ATOM_SCALE, step: 0.05, format: (value) => `${value.toFixed(2)}×`,
      control: "appearance.atom-scale" }),
    slider("bondRadius", "Bond radius", { min: 0.02, max: 0.4, step: 0.01, format: (value) => `${value.toFixed(2)} Å`, control: "appearance.bond-radius" }),
    slider("polyAlpha", "Polyhedra opacity", { control: "appearance.polyhedra-opacity" }),
    slider("planeAlpha", "Plane opacity", { control: "appearance.plane-opacity" }),
    el("label", { class: "check", "data-control": "appearance.polyhedron-edges" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.polyEdges, onchange: (event) => {
      viewerPrefs.appearance.polyEdges = event.target.checked; savePrefs(); rebuildAll();
    } }), "Polyhedron edges"),
    el("label", { class: "check", "data-control": "appearance.depth-cue" }, el("input", { type: "checkbox", checked: viewerPrefs.appearance.depthCue, onchange: (event) => {
      viewerPrefs.appearance.depthCue = event.target.checked; savePrefs(); rebuildAll();
    } }), "Depth cueing (fade towards the back)"),
    slider("depthStrength", "Depth fade at the back", { min: 0.1, max: 0.9, control: "appearance.depth-strength" }),
  ];
  const sliderBox = el("div", { class: "field-stack" }, ...styleSliders());
  const resetAppearance = () => {
    viewerPrefs.appearance = freshAppearance(); savePrefs();
    sliderBox.replaceChildren(...styleSliders());
    syncStyleControls();
    cellStyleBox.replaceChildren(...cellStyleControls());
    renderElementStyles();
    rebuildAll();
    elementColoursChanged();
  };

  // Element visibility: unchecked elements are hidden (with their bonds).
  const elementBoxes = elementBoxesFor("hiddenElements", sliceChanged, "Show");

  // Miller planes and planes through atoms (see createPlaneControls); the
  // latter are picked with the measure panel's clicks.
  const planePanel = createPlaneControls(() => structure.cell, () => { rebuildAll(); renderMeasurements(); }, () => scheduleRebuild(),
    { structures: () => page.structures, measure: () => measure });
  // Measurements (see createMeasurePanel); the page's atom colours share the clicks.
  const measure = createMeasurePanel({ structures: () => page.structures, panels: () => page.panels, stages, clickMode,
    onChange: () => renderPaint() });
  measure.listen(() => planePanel.update());
  const measureControls = measure.controls;
  function renderMeasurements() { measure.render(); }
  function measurementsChanged() { measure.changed(); }
  page.cancelMeasure = measure.cancel;

  // Atom colours: select atoms by clicking (shares the click with Measure),
  // then give them a colour; see paintState.
  const atomLabel = (r) => `${r.symbol}${r.index}`;
  const selectBox = el("input", { type: "checkbox", onchange: (event) => {
    measureState.mode = event.target.checked ? "select" : "off";
    measureState.pending = [];
    measurementsChanged();
  } });
  const paintColour = el("input", { type: "color", value: paintState.colour, "aria-label": "Colour for the selected atoms", "data-control": "highlight.apply" });
  const applyButton = el("button", { type: "button", class: "small", "data-control": "highlight.apply", onclick: () => {
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
      return el("div", { class: "measure-row", "data-control": "highlight.groups" },
        el("input", { type: "color", class: "group-colour", value: group.colour, "aria-label": `Colour of ${names}`, title: "Change this colour",
          oninput: (event) => { group.colour = event.target.value; paintState.colour = group.colour; scheduleRebuild(); } }),
        el("span", { class: "measure-atoms", title: group.atoms.map(atomLabel).join(", ") }, names),
        el("button", { type: "button", class: "small", title: "Remove", "aria-label": "Remove colour", onclick: () => {
          paintState.groups.splice(k, 1); measurementsChanged();
        } }, "×"));
    }));
    if (paintState.groups.length) {
      paintList.append(el("button", { type: "button", class: "small", "data-control": "highlight.remove-all", onclick: () => {
        paintState.groups = []; measurementsChanged();
      } }, "Remove all colours"));
    }
  }
  const paintControls = el("div", { class: "measure-controls" },
    el("label", { class: "check", "data-control": "highlight.select" }, selectBox, "Select atoms by clicking"),
    el("div", { class: "button-row" },
      el("button", { type: "button", class: "small", title: "Select every atom the slice shows", "data-control": "highlight.select-all", onclick: () => {
        const shown = page.structures[0];
        const indices = [...new Set((page.panels[0].scene?.atoms ?? []).map((a) => a.index))].sort((a, b) => a - b);
        paintState.selected = indices.map((index) => ({ index, symbol: shown.symbols[index], count: shown.symbols.length }));
        measurementsChanged();
      } }, "All shown atoms"),
      el("button", { type: "button", class: "small", "data-control": "highlight.clear-selection", onclick: () => { paintState.selected = []; measurementsChanged(); } }, "Clear selection")),
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
  tripodSelect.addEventListener("change", () => { setTripodAxes(tripodSelect.value); savePrefs(); rebuildAll(); });
  const labelSelect = el("select", { "aria-label": "Atom labels" },
    [["off", "None"], ["index", "Index"], ["element", "Element"], ["element-index", "Element and index"], ["value", "Colour value"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.labels === value }, label)));
  labelSelect.addEventListener("change", () => { viewerPrefs.labels = labelSelect.value; savePrefs(); rebuildAll(); });
  // Drawing style and radius type (see STYLES); settings that do nothing in
  // a style are disabled (styleLocks), also the atom size slider above.
  const styleSelect = el("select", { "aria-label": "Model" },
    STYLES.map((value) => el("option", { value, selected: viewerPrefs.style === value }, STYLE_LABELS[value])));
  const radiusTypeSelect = el("select", { "aria-label": "Radius type" },
    RADIUS_TYPES.map((value) => el("option", { value, selected: viewerPrefs.radiusType === value }, RADIUS_TYPE_LABELS[value])));
  const bondsCheck = tagControl(checkbox("Bonds", "bonds", rebuildAll), "bonds.show");
  const polyhedraCheck = tagControl(checkbox("Polyhedra", "polyhedra", () => { syncStyleControls(); rebuildAll(); }), "polyhedra.show");
  // Polyhedra without their centre atoms (viewerPrefs.polyhedraCentres).
  const centresCheck = tagControl(checkbox("Show centre atoms", "polyhedraCentres", rebuildAll), "polyhedra.centre-atoms");
  const radiusTypeField = el("label", { class: "field", "data-control": "style.radius-type" }, el("span", { class: "field-label" }, "Radius type"), radiusTypeSelect);
  const syncStyleControls = () => {
    const locks = styleLocks();
    for (const [label, lock] of [[bondsCheck, locks.bonds], [polyhedraCheck, locks.polyhedra], [centresCheck, locks.polyhedraCentres],
      [radiusTypeField, locks.radiusType], [sliderBox.querySelector('[data-setting="atomScale"]'), locks.atomScale]]) {
      label.querySelector("input, select").disabled = Boolean(lock);
      label.title = lock ?? "";
      label.classList.toggle("muted", Boolean(lock));
    }
  };
  syncStyleControls();
  styleSelect.addEventListener("change", () => { viewerPrefs.style = styleSelect.value; savePrefs(); syncStyleControls(); rebuildAll(); });
  radiusTypeSelect.addEventListener("change", () => { viewerPrefs.radiusType = radiusTypeSelect.value; savePrefs(); rebuildAll(); });
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

  // Bond cutoffs and polyhedron centres (see createCutoffControls, createCentreControls).
  const cutoffPanel = createCutoffControls(species, () => rebuildAll());
  const bondSearch = createBondSearchControls(() => rebuildAll());
  const pairs = cutoffPanel.pairs;
  const centrePanel = createCentreControls(species, () => rebuildAll());

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
  const ringMethodSelect = el("select", { "aria-label": "Ring method", "data-control": "rings.method" },
    [["planar", "Flat: surface, overlayer, 2D material"],
      ["shortest-path", "3D: bulk, zeolite, amorphous"]].map(([value, label]) =>
      el("option", { value, selected: rings.method === value }, label)));
  const searchSizeInput = el("input", { type: "number", min: 3, max: 24, step: 1, class: "num-input", value: rings.searchSize,
    "aria-label": "Largest ring searched", onchange: (event) => {
      const value = Math.round(Number(event.target.value));
      rings.searchSize = value >= 3 ? Math.min(24, value) : 12;
      event.target.value = rings.searchSize; ringsChanged();
    } });
  const searchSizeField = el("div", { class: "inline-fields", "data-control": "rings.search-size" }, el("span", { class: "field-label" }, "Largest ring searched (atoms)"), searchSizeInput);
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
  const ringElementTable = el("table", { class: "stats cutoffs", "data-control": "rings.elements" },
    el("thead", {}, el("tr", {}, el("th", {}, "element"), el("th", {}, "height from"), el("th", {}, "to (Å)"))), el("tbody", {}, ringElementRows));
  const syncRingElements = () => ringElementTable.querySelectorAll("tbody tr").forEach((row, n) => {
    const setting = ringElement(species[n]);
    const [use, zmin, zmax] = row.querySelectorAll("input");
    use.checked = setting.use; zmin.value = setting.zmin ?? ""; zmax.value = setting.zmax ?? "";
  });
  const ringHint = el("p", { class: "muted hint" });
  // Height windows from the atoms selected under Colour (± 0.05 Å);
  // elements without selected atoms are left out.
  const fromSelection = el("button", { type: "button", class: "small", "data-control": "rings.from-selection", title: "Use only the elements and heights of the atoms selected in the Colour tab",
    onclick: () => {
      const shown = page.structures[0];
      if (!paintState.selected.length || !fitsStructure(shown, paintState.selected)) {
        ringHint.textContent = "First select some of the network's atoms in the Colour tab (Highlight selected atoms: click them, or slice and use All shown atoms).";
        return;
      }
      const normal = surfaceNormal(shown);
      for (const sym of species) {
        const hs = paintState.selected.filter((r) => r.symbol === sym).map((r) => dot(positionsOf(shown)[r.index], normal));
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
  const ringCustomColours = tagControl(customPaletteInputs(() => customPaletteChanged()), "rings.custom-palette");
  ringCustomColours.hidden = rings.scheme !== "custom";
  ringSchemeSelect.addEventListener("change", () => {
    rings.scheme = ringSchemeSelect.value; ringCustomColours.hidden = rings.scheme !== "custom"; ringsChanged();
  });
  ringCountSelect.addEventListener("change", () => { rings.count = ringCountSelect.value; ringsChanged(); });
  const sizeInput = (key, label) => el("input", { type: "number", min: 0, step: 1, class: "num-input", value: rings[key] ?? "",
    placeholder: key === "minSize" ? "min" : "max", "aria-label": label,
    onchange: (event) => { rings[key] = optionalNumber(event.target.value); ringsChanged(); } });
  // A result: GUI profiles never hide it (see applyProfile).
  const ringSummary = el("div", { class: "ring-summary", "data-profile-content": "" });
  const enclosedBox = tagControl(ringCheck("enclosed", "Count atoms inside a ring (labelled e.g. 6+1Cu)", "Network atoms that are pruned or unbonded count as inside the smallest ring around them"), "rings.enclosed");
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
        el("button", { type: "button", class: "small", "data-control": "rings.all-atoms", onclick: () => { rings.elements = {}; syncRingElements(); ringHint.textContent = ""; ringsChanged(); } }, "All atoms")),
      ringHint),
    ringStep(3, "Bonds",
      tagControl(ringCheck("alternating", "Only bonds between different elements", "For networks that alternate between elements, such as metal–oxygen or Si–O; ignored with only one element"), "rings.alternating"),
      el("details", { "data-control": "rings.cutoffs" }, el("summary", { class: "muted" }, "Bond cutoffs for rings"),
        el("p", { class: "muted hint" }, "Blank: the bond cutoff of the Style tab (shown greyed). Turn on Bonds there to see the network."),
        el("table", { class: "stats cutoffs" }, el("tbody", {}, ringCutoffRows)))),
    ringStep(4, "Ring size",
      el("label", { class: "palette-field", "data-control": "rings.count" }, el("span", { class: "muted" }, "Count"), ringCountSelect),
      el("p", { class: "muted hint" }, "A ring of 6 Cu and 6 O atoms is a 6-ring counting pairs or Cu atoms, a 12-ring counting all atoms. Automatic counts pairs when every bond joins two different elements, otherwise all atoms."),
      enclosedBox),
    el("details", { class: "ring-step" }, el("summary", { class: "ring-step-title" }, "Appearance"),
      el("div", { class: "ring-controls" },
        el("div", { class: "inline-fields", "data-control": "rings.size-range" }, el("span", { class: "muted" }, "Show sizes"), sizeInput("minSize", "Smallest ring size shown"), "–",
          sizeInput("maxSize", "Largest ring size shown")),
        el("label", { class: "palette-field", "data-control": "rings.scheme" }, el("span", { class: "muted" }, "Colours"), ringSchemeSelect),
        ringCustomColours,
        slider("alpha", "Ring opacity", { group: "rings", control: "rings.opacity" }),
        tagControl(ringCheck("outline", "Ring outlines"), "rings.outline"),
        tagControl(ringCheck("labels", "Ring size labels"), "rings.labels"),
        slider("labelScale", "Ring label size", { min: 0.5, max: 4, step: 0.1, format: (value) => `${value.toFixed(1)}×`, group: "rings", control: "rings.label-size" }))));
  showMethod();
  const ringShowBox = el("label", { class: "check", "data-control": "rings.show" }, el("input", { type: "checkbox", checked: rings.show, onchange: (event) => {
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
    const colourInput = (size) => el("input", { type: "color", value: ringColour(size, range), "aria-label": `Colour of ${size}-rings`, "data-control": "rings.size-colour",
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
              el("button", { type: "button", class: "small reset-colour", title: "Default colour", "aria-label": `Default colour of ${size}-rings`, "data-control": "rings.size-colour",
                onclick: (event) => {
                  delete rings.colours[size]; savePrefs();
                  event.currentTarget.previousSibling.value = ringColour(size, range);
                  scheduleRebuild();
                } }, "↺"))))))
        : el("p", { class: "muted hint" }, "No rings found: check the atoms, heights and cutoffs (turn on Bonds to see the network)."),
      data.signature ? el("p", { class: "hint ring-signature" }, el("span", { class: "muted" }, "Signature "), el("code", {}, data.signature),
        tagControl(copyButton(data.signature), "rings.summary-actions")) : null,
      el("div", { class: "button-row" },
        el("button", { type: "button", class: "small", title: "The rings of this structure (atoms, polygons, sizes, areas) as JSON", "data-control": "rings.summary-actions", onclick: () => {
          const s = page.structures[0];
          downloadText(`${s.formula}-${s.id}.rings.json`, `${JSON.stringify(ringsJson(s, page.panels[0].ringData), null, 1)}\n`, "application/json");
        } }, "Save rings (JSON)"),
        page.stepList ? el("button", { type: "button", class: "small", title: `Ring sizes of every structure stepped through (${page.stepList.list.length}) as CSV`, "data-control": "rings.summary-actions",
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
  const forceVectorField = el("label", { "data-control": "arrows.vector" }, el("span", { class: "muted" }, "Property"), forceVectorSelect);
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
  const autoScaleButton = el("button", { type: "button", class: "small", title: "Largest included arrow → 1.5 Å", onclick: async () => {
    const shown = (page.arrowData ?? []).filter(Boolean).map((d) => ({ values: d.magnitudes, included: d.included }));
    const max = viewerPrefs.arrows.source === "displacement"
      ? await scaleMax("displacement", displacementValues, shown) : await scaleMax("force", forceValues, shown);
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
      el("div", { class: "arrow-length", "data-control": "arrows.length" }, el("span", { class: "muted" }, "Length, ", scaleUnit),
        el("div", { class: "inline-fields" }, scaleInput, autoScaleButton)),
      slider("width", "Arrow width", { min: 0.01, max: 0.2, step: 0.01, format: (value) => `${value.toFixed(2)} Å`, group: "arrows", control: "arrows.width" }),
      el("div", { class: "inline-fields", "data-control": "arrows.colour" }, el("span", { class: "muted" }, "Colour"), colourInput,
        el("button", { type: "button", class: "small", title: "Use the page's text colour", onclick: () => {
          viewerPrefs.arrows.colour = null; colourInput.value = themeTextColour(); arrowStyleChanged();
        } }, "Theme")),
      el("div", { class: "inline-fields", "data-control": "arrows.min-magnitude" }, el("span", { class: "muted" }, "Hide below"), minMagnitudeInput, el("span", { class: "muted arrow-unit" })),
      el("button", { type: "button", class: "small", "data-control": "arrows.reset-style", onclick: () => {
        viewerPrefs.arrows = { ...DEFAULT_ARROWS, show: viewerPrefs.arrows.show, source: viewerPrefs.arrows.source }; savePrefs();
        arrowStyleControls.replaceChildren(arrowStyleControls.firstChild, ...arrowStyleBody());
        updateForceSummary(); rebuildAll();
      } }, "Reset arrow style"),
    ];
  };
  const arrowStyleControls = el("details", { class: "appearance" }, el("summary", { class: "muted" }, "Arrow style"), ...arrowStyleBody());

  const forceSliceTable = tagControl(sliceTableFor("forceSlice", updateOverlays, "Forces "), "forces.include-bounds");
  const forceElementBoxes = tagControl(elementBoxesFor("forceHiddenElements", updateOverlays, "Include forces of"), "forces.include-elements");
  const forceCount = el("span", { class: "muted" });
  // Own elements and bounds, shown only when the selection does not follow the slice.
  const ownSelection = el("div", { hidden: viewerPrefs.forceFollowsSlice },
    forceElementBoxes, forceSliceTable,
    el("button", { type: "button", class: "small", "data-control": "forces.include-all", onclick: () => {
      resetFilter("forceSlice", "forceHiddenElements", forceSliceTable, forceElementBoxes);
      updateOverlays();
    } }, "Include all"));
  const followSliceBox = el("label", { class: "check", "data-control": "forces.follow-slice" }, el("input", { type: "checkbox", checked: viewerPrefs.forceFollowsSlice,
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
    const data = page.arrowData?.[0];
    const unit = viewerPrefs.arrows.source === "displacement" ? "Å"
      : data?.unit || page.force.evaluation?.vectors.find((v) => v.name === page.force.name)?.unit || "";
    arrowStyleControls.querySelectorAll(".arrow-unit").forEach((node) => { node.textContent = unit; });
    scaleUnit.textContent = unit ? `Å per ${unit}` : "Å per unit";
    autoScaleButton.disabled = !(page.arrowData ?? []).some(Boolean);
    const included = forceIncluded(structure).filter(Boolean).length;
    forceCount.textContent = `${included} of ${structure.positions.length} atoms included`;
  }

  // Arrows of an evaluation's per-atom vectors, or of displacements.
  const arrowSourceSelect = el("select", { "aria-label": "Arrows of" },
    el("option", { value: "vectors", disabled: !vectorEvaluations.length }, "Per-atom vectors of an evaluation"),
    el("option", { value: "displacement" }, "Displacements from a reference"));
  const vectorSourceBox = el("div", { class: "field-stack" }, ...(vectorEvaluations.length
    ? [el("label", { "data-control": "arrows.evaluation" }, el("span", { class: "muted" }, "Evaluation"), forceEvaluationSelect), forceVectorField]
    : [el("p", { class: "muted", "data-control": "arrows.evaluation" }, "No evaluations with per-atom vectors.")]));
  const displacementControls = createDisplacementControls({ compared: true, count: () => page.stepList?.list.length ?? null,
    onChange: () => updateOverlays() });
  page.displacementControls = displacementControls;
  const displacementBox = el("div", { class: "field-stack" }, displacementControls.element,
    el("p", { class: "muted hint" }, "Each atom's displacement Δr from the same atom of the reference, over the shortest periodic image. "
      + "The reference is the structure in the other panel, or one of the step list below the structure."));
  const showArrowSource = () => {
    const displacement = viewerPrefs.arrows.source === "displacement";
    arrowSourceSelect.value = viewerPrefs.arrows.source;
    vectorSourceBox.hidden = displacement;
    displacementBox.hidden = !displacement;
  };
  arrowSourceSelect.addEventListener("change", () => {
    viewerPrefs.arrows.source = arrowSourceSelect.value; savePrefs(); showArrowSource(); updateOverlays();
  });
  showArrowSource();
  const forceControls = el("div", { class: "force-controls" },
    el("label", { "data-control": "arrows.source" }, el("span", { class: "muted" }, "Arrows of"), arrowSourceSelect),
    vectorSourceBox, displacementBox,
    el("label", { class: "check", "data-control": "arrows.show" }, el("input", { type: "checkbox", checked: viewerPrefs.arrows.show, onchange: (event) => {
      viewerPrefs.arrows.show = event.target.checked; savePrefs(); updateOverlays();
    } }), "Show arrows"),
    arrowStyleControls,
    inclusionControls);

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
      ? el("p", { class: "muted", "data-control": "colour.error-pair" }, "Needs two evaluations with per-atom vectors (e.g. forces).")
      : [el("label", { "data-control": "colour.error-pair" }, el("span", { class: "muted" }, "Reference (A)"), pairSelect(0)),
        el("label", { "data-control": "colour.error-pair" }, el("span", { class: "muted" }, "Compared (B)"), pairSelect(1))]);
  // Atomic property colouring (see createPropertyControls).
  const propertyPanel = createPropertyControls(propertyOptions(structure), () => updateOverlays());
  const propertyControls = propertyPanel.element;
  propertyControls.hidden = viewerPrefs.colour !== "property";
  const colourSelect = el("select", { "aria-label": "Colour atoms by", "data-control": "colour.mode" },
    [["element", "Element"], ["height", "Height"], ["force", "Force magnitude"], ["error", "Per-atom force difference"],
      ["property", "Atomic property"]].map(([value, label]) =>
      el("option", { value, selected: viewerPrefs.colour === value }, label)));

  // Custom palette colours changed (here or under Rings): colour again.
  let customFrame = 0;
  const customPaletteChanged = () => {
    cancelAnimationFrame(customFrame);
    customFrame = requestAnimationFrame(() => updateOverlays());
  };
  // Colour map of the current value colouring (see createPaletteControls).
  const palettePanel = createPaletteControls(() => updateOverlays(), customPaletteChanged);
  const colourMapSection = palettePanel.element;
  const fillPaletteSelect = palettePanel.refresh;
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
  // A transformation matrix replaces the repeat, single cell only both (see
  // shownCell).
  const syncRepeatInputs = () => repeatInputs.forEach((input, k) => {
    input.value = viewerPrefs.singleCell ? 1 : viewerPrefs.repeat[k];
    input.disabled = !structure.pbc[k] || Boolean(viewerPrefs.repeatMatrix) || viewerPrefs.singleCell;
    input.title = singleCellLock() ?? (viewerPrefs.repeatMatrix ? "The transformation matrix sets the shown cell" : "");
  });
  syncRepeatInputs();
  const repeatMatrixControls = createRepeatMatrixControls({ structure: () => structure, onChange: () => {
    syncRepeatInputs(); rebuildAll(); page.panels[0].fit(); viewChanged(); renderInfo();
  } });

  // --- vibrational modes (see createVibrationPanel).
  const vibration = modes ? createVibrationPanel({ structure, modes, figures, panel: () => page.panels[0], disposed: () => page.disposed,
    repeatChanged: () => { syncRepeatInputs(); repeatMatrixControls.sync(); rebuildAll(); },
    axesChanged: () => { tripodSelect.value = viewerPrefs.tripod.axes; rebuildAll(); } }) : null;
  const vibrationControls = vibration?.controls ?? null;
  if (vibration?.stop) page.stopVibration = vibration.stop;

  const compareSelect = el("select", { class: "compare-select", "aria-label": "Compare with", "data-control": "compare.with" }, el("option", { value: "" }, "No comparison"));
  compareSelect.addEventListener("change", () => { location.hash = hash(structure.id, { compare: compareSelect.value || null }); });

  // Compare bar: the compared structure (from the step list, or opened from
  // files, which are then stepped through on the right), which panel steps
  // through the list while the other stays as reference, swap and close.
  const compareFiles = el("input", { type: "file", multiple: true, hidden: true, "aria-label": "Structure files to compare with" });
  const openFileButton = el("button", { type: "button", class: "small", "data-control": "compare.open-file", title: "Open structure files (extxyz, POSCAR, CIF, …) and compare with them",
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
      el("div", { class: "inline-fields" }, el("span", { class: "field-label", "data-control": "compare.with" }, "Compare with"), compareSelect, openFileButton, compareFiles),
      comparing ? el("div", { class: "inline-fields" }, el("span", { class: "field-label", "data-control": "compare.steps-side" }, "Steps move"),
        el("div", { class: "segmented", role: "group", "aria-label": "Panel that steps", "data-control": "compare.steps-side" }, segment("left", "Left"), segment("right", "Right")),
        el("button", { type: "button", class: "small", title: "Swap the two structures", "data-control": "compare.swap", onclick: () => {
          location.hash = hash(page.originals[1].id, { compare: structure.id });
        } }, "⇄ Swap"),
        el("button", { type: "button", class: "small", title: "Show one structure", "data-control": "compare.close", onclick: () => {
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
    editor = el("div", { class: "element-editor", role: "dialog", "aria-label": `Style of ${sym}`, "data-control": "elements.editor" },
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
    // Symmetry, when the server can compute it (spglib is an optional extra).
    const canSymmetry = shown.some(symmetryAvailable);
    const syms = canSymmetry ? await Promise.all(shown.map((s) => loadSymmetry(s).catch((error) => ({ error: error.message })))) : [];
    if (token !== infoToken || page.disposed) return;
    const names = shown.length > 1 ? ["Left", "Right"] : [null];
    const lattice = shown.some(hasCell);
    const facts = shown.map((s) => cellFacts(s, lattice));
    if (canSymmetry) {
      facts.forEach((f, k) => {
        const sym = syms[k];
        f.push(["Space group", el("span", { class: "space-group", title: sym?.reason ?? sym?.error ?? "" }, spaceGroupText(sym)), ""],
          ["Crystal system", sym?.crystal_system ?? "–", ""]);
      });
    }
    const factTable = el("table", { class: "stats info-facts" },
      shown.length > 1 ? el("thead", {}, el("tr", {}, el("th", {}, ""), names.map((n) => el("th", { class: "num" }, n)))) : null,
      el("tbody", {}, facts[0].map(([label, , unit], row) => el("tr", {},
        el("th", {}, label, unit ? el("span", { class: "muted" }, ` (${unit})`) : null),
        facts.map((f) => el("td", { class: row > 2 ? "num" : null }, f[row][1]))))));
    const matrices = shown.filter(hasCell).map((s, k) => {
      const reciprocalRows = reciprocal(s.cell).map((row) => mul(row, 2 * Math.PI));
      return el("div", { class: "info-block" },
        names[k] ? el("h4", {}, `${names[k]}: ${s.formula}`) : null,
        el("div", { class: "button-row" }, el("span", { class: "field-label" }, "Cell vectors (rows, Å)"), tagControl(copyButton(matrixText(s.cell, 6)), "info.copy-cell")),
        matrixTable(s.cell, ["a", "b", "c"], 4),
        el("div", { class: "button-row" }, el("span", { class: "field-label" }, "Reciprocal vectors (rows, 2π/Å)"), tagControl(copyButton(matrixText(reciprocalRows, 6)), "info.copy-cell")),
        matrixTable(reciprocalRows, ["a*", "b*", "c*"], 4));
    });
    const extras = shown.map((s, k) => {
      const prefix = names[k] ? `${names[k]}: ` : "";
      const positions = el("details", { "data-control": "info.atom-positions" }, el("summary", {}, `${prefix}Atom positions`));
      positions.addEventListener("toggle", () => {
        if (positions.open && positions.children.length === 1) positions.append(...positionsTable(s).filter(Boolean));
      });
      return [positions,
        Object.keys(s.info ?? {}).length ? el("details", { "data-control": "info.structure-info" }, el("summary", {}, `${prefix}Structure info (${Object.keys(s.info).length})`), jsonTree(s.info, "info")) : null,
        Object.keys(s.metadata ?? {}).length ? el("details", { "data-control": "info.provenance" }, el("summary", {}, `${prefix}Provenance metadata`), jsonTree(s.metadata, "metadata")) : null];
    });
    // Sections the reader opened stay open when the info is rebuilt.
    const open = new Set([...infoPanel.querySelectorAll("details[open] > summary")].map((summary) => summary.textContent));
    // Displacements, while shown as arrows or colours (see updateOverlays).
    const moved = (page.displacements ?? []).slice(0, shown.length);
    const displacementTable = moved.some(Boolean) ? el("table", { class: "stats info-displacements" },
      shown.length > 1 ? el("thead", {}, el("tr", {}, el("th", {}, ""), names.map((n) => el("th", { class: "num" }, n)))) : null,
      el("tbody", {}, [
        ["RMSD", (d) => fixed(d.rmsd, 3), "Å"],
        ["Largest", (d) => fixed(d.max, 3), "Å"],
        ["Largest at", (d) => (d.maxIndex >= 0 ? `${shown[moved.indexOf(d)].symbols[d.maxIndex]} ${d.maxIndex}` : "–"), ""],
      ].map(([label, value, unit]) => el("tr", {},
        el("th", {}, label, unit ? el("span", { class: "muted" }, ` (${unit})`) : null),
        moved.map((d) => el("td", { class: "num" }, d ? value(d) : "–")))))) : null;
    // A transformation matrix is display only: say so above the stored cell's numbers.
    const transform = shown.map(transformNote).find(Boolean);
    infoPanel.replaceChildren(
      el("section", { class: "control-section" }, el("h4", {}, lattice ? "Structure and lattice" : "Structure"),
        transform ? el("p", { class: "muted hint transform-note" }, transform) : null, factTable,
        ...symmetryInfo(shown, syms, names, canSymmetry)),
      ...(displacementTable ? [el("section", { class: "control-section" },
        el("h4", {}, `Displacements from ${displacementReferenceText()}`), displacementTable)] : []),
      ...(matrices.length ? [el("section", { class: "control-section" }, el("h4", {}, "Cell"), ...matrices)] : []),
      el("section", { class: "control-section info-extras" }, ...extras.flat().filter(Boolean)));
    for (const details of infoPanel.querySelectorAll("details")) if (open.has(details.firstChild.textContent)) details.open = true;
  }

  // Below the facts: without spglib one line naming the extra; else the
  // tolerance (changing it computes again), why a structure has no space
  // group, and its inequivalent sites.
  function symmetryInfo(shown, syms, names, canSymmetry) {
    if (!canSymmetry) return [el("p", { class: "muted hint symmetry-hint" }, SYMMETRY_INSTALL)];
    const tolerance = el("input", { type: "number", class: "num-input", min: MIN_SYMMETRY_TOLERANCE, max: MAX_SYMMETRY_TOLERANCE, step: 0.001,
      value: viewerPrefs.symmetry.tolerance, "aria-label": "Symmetry tolerance", onchange: () => {
        const value = Number(tolerance.value);
        if (!(value >= MIN_SYMMETRY_TOLERANCE && value <= MAX_SYMMETRY_TOLERANCE)) { tolerance.value = viewerPrefs.symmetry.tolerance; return; }
        viewerPrefs.symmetry.tolerance = value; savePrefs();
        updateOverlays();
      } });
    const notes = syms.map((sym, k) => {
      const why = sym?.error ?? sym?.reason;
      return why ? el("p", { class: "muted hint symmetry-note" }, `${names[k] ? `${names[k]}: ` : ""}${why}`) : null;
    });
    const sites = shown.map((s, k) => {
      const sym = syms[k];
      if (!symmetrySites(sym, s)) return null;
      const list = symmetrySiteList(sym, s);
      return el("details", { "data-control": "info.inequivalent-sites" }, el("summary", {}, `${names[k] ? `${names[k]}: ` : ""}Inequivalent sites (${list.length})`),
        el("div", { class: "table-scroll" }, el("table", { class: "stats symmetry-sites" },
          el("thead", {}, el("tr", {}, ["Site", "Wyckoff", "Site symmetry", "Atoms", ""].map((h) => el("th", {}, h)))),
          el("tbody", {}, list.map((site) => el("tr", {}, el("td", {}, site.label), el("td", {}, site.wyckoff), el("td", {}, site.site),
            el("td", { class: "num" }, String(site.atoms.length)),
            el("td", { class: "muted" }, site.atoms.slice(0, 12).join(", ") + (site.atoms.length > 12 ? " …" : ""))))))));
    });
    return [el("label", { class: "field symmetry-tolerance", "data-control": "symmetry.tolerance", title: "Distance tolerance of the symmetry search (spglib's symprec)" },
      el("span", { class: "field-label" }, "Symmetry tolerance (Å)"), tolerance), ...notes.filter(Boolean), ...sites.filter(Boolean)];
  }

  // Clear all: back to the plain structure. Orientation, zoom and pan, cell
  // repeats, slicing and hidden elements, measurements, selected and coloured
  // atoms, atom labels and the colouring (to element colours) are reset;
  // rings, planes and force arrows are switched off but keep their settings,
  // as do element styles, cutoffs and palettes.
  function resetView() {
    // Measurements and atom colours cannot be restored: ask first.
    const losing = [measureState.items.length ? `${measureState.items.length} measurement${measureState.items.length === 1 ? "" : "s"}` : null,
      measureState.polyhedra.length ? `${measureState.polyhedra.length} polyhedr${measureState.polyhedra.length === 1 ? "on" : "a"}` : null,
      paintState.groups.length ? `${paintState.groups.length} atom colour${paintState.groups.length === 1 ? "" : "s"}` : null].filter(Boolean);
    if (losing.length && !window.confirm(`Clear all? This removes ${losing.join(" and ")}.`)) return;
    Object.assign(viewerPrefs, { repeat: [1, 1, 1], repeatMatrix: null, slice: emptySlice(), hiddenElements: [], labels: "off", colour: "element" });
    viewerPrefs.rings.show = false;
    viewerPrefs.arrows.show = false;
    for (const plane of viewerPrefs.planes) plane.show = false;
    savePrefs();
    Object.assign(measureState, { mode: "off", pending: [], items: [], polyhedra: [] });
    Object.assign(paintState, { selected: [], groups: [] });
    Object.assign(sharedView, { R: presetRotation(structure, "top"), scale: null, pan: [0, 0] });
    renderStructurePage(structureId, params);
  }
  const resetViewButton = el("button", { type: "button", class: "small reset-view", "data-control": "footer.clear-all",
    title: "Back to the plain structure (r): top view, fitted; no repeats or transformation matrix, slicing, hidden elements, measurements, atom colours, labels, rings, planes or arrows. Styles, cutoffs and other settings are kept." },
  "⟲ Clear all");
  resetViewButton.addEventListener("click", resetView);
  // The structure panels as SVG, beside Clear all (the Save tab has PNG too).
  const saveViewButton = el("button", { type: "button", class: "small save-view", "data-control": "footer.save-svg", title: "Save the structure panels as an SVG image",
    onclick: () => saveImage("svg") }, "Save SVG");
  viewerMain.querySelector(".viewer-footer").append(el("div", { class: "footer-actions", "data-profile-place": "Footer" }, saveViewButton, resetViewButton));

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
  // Under View: the settings set how the viewer looks (remembered in this browser).
  const settingsSection = section("Viewer settings",
    el("div", { class: "button-row" },
      tagControl(button("Export", () => {
        downloadText("stoms-viewer-settings.json", `${JSON.stringify({ stoms_viewer_settings: 1, settings: viewerPrefs }, null, 2)}\n`, "application/json");
      }, "Save all viewer settings to a file"), "settings.export-import"),
      tagControl(button("Import", () => settingsInput.click(), "Load viewer settings from a file"), "settings.export-import"), settingsInput,
      tagControl(button("Restore defaults", () => {
        if (!window.confirm("Reset all viewer settings to their defaults? This also removes your planes and custom cutoffs.")) return;
        for (const key of Object.keys(viewerPrefs)) delete viewerPrefs[key];
        Object.assign(viewerPrefs, defaultPrefs());
        savePrefs();
        Object.assign(sharedView, { R: null, scale: null, pan: [0, 0], panelCount: 0 });
        renderStructurePage(structureId, params);
      }, "Reset every viewer setting to its default"), "settings.restore-defaults")));
  // Cell outline style (viewerPrefs.appearance.cell*); colour null = theme.
  const themeCellColour = () => themeColours(page.panels[0]?.stage ?? document.documentElement).cell;
  const cellStyleControls = () => {
    const colourInput = el("input", { type: "color", "aria-label": "Cell outline colour", value: viewerPrefs.appearance.cellColour ?? themeCellColour(),
      oninput: (event) => { viewerPrefs.appearance.cellColour = event.target.value; savePrefs(); scheduleRebuild(); } });
    const dashSelect = el("select", { "aria-label": "Cell outline style", onchange: (event) => {
      viewerPrefs.appearance.cellDash = event.target.value; savePrefs(); scheduleRebuild();
    } }, Object.keys(CELL_DASHES).map((value) => el("option", { value, selected: value === viewerPrefs.appearance.cellDash }, value)));
    return [
      slider("cellWidth", "Outline width", { min: 0.5, max: MAX_CELL_WIDTH, step: 0.5, format: (value) => `${value} px`, control: "cell.outline-width" }),
      el("div", { class: "inline-fields" }, el("span", { class: "muted", "data-control": "cell.outline-colour" }, "Colour"), tagControl(colourInput, "cell.outline-colour"),
        el("button", { type: "button", class: "small", title: "Use the theme's cell colour", "data-control": "cell.outline-colour", onclick: () => {
          viewerPrefs.appearance.cellColour = null; colourInput.value = themeCellColour(); savePrefs(); scheduleRebuild();
        } }, "Theme"),
        el("span", { class: "muted", "data-control": "cell.outline-style" }, "Style"), tagControl(dashSelect, "cell.outline-style")),
    ];
  };
  const cellStyleBox = el("div", { class: "field-stack" }, ...cellStyleControls());
  // The cell outline at every copy (viewerPrefs.repeatCellOutline): off
  // while the outline is.
  const everyCopyCheck = tagControl(checkbox("Outline every copy", "repeatCellOutline", () => { repeatMatrixControls.sync(); rebuildAll(); }), "cell.outline-every-copy");
  const syncEveryCopy = () => {
    // One cell has no copies to outline (single cell only).
    const lock = singleCellLock() ?? (viewerPrefs.cell ? null : "The cell outline is off");
    // Shown unticked with single cell only: one cell, no copies to outline.
    everyCopyCheck.querySelector("input").checked = !viewerPrefs.singleCell && viewerPrefs.repeatCellOutline;
    everyCopyCheck.querySelector("input").disabled = Boolean(lock);
    everyCopyCheck.title = lock ?? EVERY_COPY_TITLE;
    everyCopyCheck.classList.toggle("muted", Boolean(lock));
  };
  syncEveryCopy();
  const wrapCheck = Object.assign(tagControl(checkbox("Wrap atoms into cell", "wrap", () => { rebuildAll(); updateOverlays(); }), "cell.wrap"), {
    title: "Draw every atom inside the cell (and each repeated copy inside its own): atoms outside are moved by a lattice vector, along periodic axes only. The Info tab and saved files keep the stored positions." });
  // Single cell only (viewerPrefs.singleCell, see SINGLE_CELL_LOCK) and the
  // controls it overrides.
  const syncSingleCell = () => {
    syncRepeatInputs();
    repeatMatrixControls.sync();
    syncEveryCopy();
    // Atoms are wrapped: Wrap shows ticked.
    wrapCheck.querySelector("input").checked = viewerPrefs.singleCell || viewerPrefs.wrap;
    lockControl(wrapCheck, singleCellLock());
    bondSearch.syncOutside();
    planePanel.syncLocks();
    vibration?.syncApply?.();
  };
  const singleCellCheck = Object.assign(tagControl(checkbox("Single cell only", "singleCell", () => {
    syncSingleCell(); rebuildAll(); updateOverlays(); page.panels[0].fit(); viewChanged(); renderInfo();
  }), "cell.single-cell"), { title: SINGLE_CELL_TITLE });
  syncSingleCell();
  const tabs = {
    info: ["Info", [infoPanel]],
    view: ["View", [
      section("Orientation",
        el("div", { class: "button-grid" },
          tagControl(button("Top", preset("top"), "Look down the surface normal (t)"), "view.preset"),
          tagControl(button("Side a", preset("side-a"), "Side view with b across the screen"), "view.preset"),
          tagControl(button("Side b", preset("side-b"), "Side view with a across the screen"), "view.preset"),
          tagControl(button("⟲ 90°", roll(Math.PI / 2), "Turn the view 90° anticlockwise in the screen plane"), "view.roll"),
          tagControl(button("⟳ 90°", roll(-Math.PI / 2), "Turn the view 90° clockwise in the screen plane"), "view.roll"),
          tagControl(button("Fit", () => { page.panels[0].fit(); viewChanged(); }, "Zoom to fit (f)"), "view.fit"))),
      section("Cell",
        structure.pbc.some(Boolean) ? singleCellCheck : null,
        el("div", { class: "inline-fields repeat-row", "data-control": "cell.repeat" }, el("span", { class: "field-label" }, "Repeat"), repeatInputs[0], "×", repeatInputs[1], "×", repeatInputs[2]),
        structure.pbc.some(Boolean) ? repeatMatrixControls.element : null,
        el("div", { class: "check-row" }, tagControl(checkbox("Cell outline", "cell", () => { syncEveryCopy(); rebuildAll(); }), "cell.outline"), everyCopyCheck),
        cellStyleBox,
        wrapCheck),
      section("Axes",
        tagControl(field("Tripod", tripodSelect), "axes.tripod"),
        slider("size", "Size", { min: TRIPOD_SIZES.min, max: TRIPOD_SIZES.max, step: 0.25, group: "tripod", control: "axes.size" }),
        slider("axesSize", "Axis arrows", { min: TRIPOD_PART_SIZES.min, max: TRIPOD_PART_SIZES.max, step: 0.1, group: "tripod", control: "axes.axes-size" }),
        structure.has_modes && structure.pbc.some(Boolean) ? slider("waveSize", "q, v_g arrows", { min: TRIPOD_PART_SIZES.min, max: TRIPOD_PART_SIZES.max, step: 0.1, group: "tripod", control: "axes.wave-size" }) : null,
        el("label", { class: "check", "data-control": "axes.in-images" }, el("input", { type: "checkbox", checked: viewerPrefs.tripod.export, onchange: (event) => {
          viewerPrefs.tripod.export = event.target.checked; savePrefs();
        } }), "Show in saved images")),
      settingsSection,
      el("details", { class: "help", "data-control": "help.mouse-keys" }, el("summary", {}, "Mouse and keys"),
        el("ul", {},
          el("li", {}, "Drag to rotate; right-drag or Shift-drag to pan; scroll to zoom."),
          el("li", {}, "Click an axis of the tripod, or press a b c x y z, to look along it; again (or with Shift) for the other side."),
          el("li", {}, "f fits, t shows the top view, r clears all (back to the plain structure); ←/→ step, space plays."),
          el("li", {}, "/ finds a control by name (↓/↑ and Enter choose, Esc clears)."),
          el("li", {}, "Below the structure: click an element to hide it, right-click to change its colour and size."),
          el("li", {}, "Drag the bottom-right corner to resize the panel."))),
    ]],
    style: ["Style", [
      section("Show",
        tagControl(field("Model", styleSelect), "style.model"),
        radiusTypeField,
        el("div", { class: "check-row" }, bondsCheck, polyhedraCheck, centresCheck),
        tagControl(field("Atom labels", labelSelect), "labels.mode")),
      section("Elements",
        el("table", { class: "stats cutoffs radii" },
          el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "colour"), el("th", {}, "radius (Å)"), el("th", {}, ""))),
          elementStyles),
        el("p", { class: "muted hint" }, "Blank radius: automatic (Atom size scales it in ball and stick).")),
      section("Sizes and opacity", sliderBox),
      el("details", {}, el("summary", {}, "Bond cutoffs"), cutoffPanel.element,
        el("p", { class: "muted hint" }, "Bonds from Min up to Max long are drawn; Min separates, say, covalent from hydrogen bonds."),
        tagControl(button("Reset cutoffs", () => {
          for (const [a, b] of pairs) { viewerPrefs.cutoffs[pairKey(a, b)] = defaultCutoff(a, b); delete viewerPrefs.bondMinimums[pairKey(a, b)]; }
          savePrefs(); renderStructurePage(structureId, params);
        }), "bonds.reset-cutoffs")),
      el("details", {}, el("summary", {}, "Bond search"), bondSearch.hbonds, bondSearch.outside),
      el("details", {}, el("summary", {}, "Polyhedron centres"), centrePanel.element),
      section(null, tagControl(button("Reset appearance", resetAppearance), "style.reset-appearance")),
    ]],
    colour: ["Colour", [
      section("Colour atoms by", colourSelect, propertyControls, errorControls),
      colourMapSection,
      section("Highlight selected atoms", paintControls),
    ]],
    slice: ["Slice", [
      section("Elements", tagControl(elementBoxes, "slice.elements")),
      section("Fractional coordinates", tagControl(sliceTable, "slice.bounds"),
        el("div", { class: "inline-fields" }, sliceCount, tagControl(button("Show all", () => {
          resetFilter("slice", "hiddenElements", sliceTable, elementBoxes);
          sliceChanged();
        }), "slice.show-all"))),
    ]],
    measure: ["Measure", [section("Measure", measureControls)]],
    planes: ["Planes", [section("Planes", planePanel.element,
      el("p", { class: "muted hint" }, "Plane through atoms: click 3 atoms (more for a best-fit plane), then Make plane. "
        + "It follows the atoms through frames and compared structures; Measure has plane angles and distances to a plane."))]],
    rings: ["Rings", [section(null,
      el("p", { class: "hint" }, "Finds the rings (closed loops of bonds) of a network of atoms and colours them by size: "
        + "hexagons and 5–7 defects in graphene, the 4- and 8-rings of an oxide overlayer, the rings of silica or a zeolite."),
      ringShowBox, ringBody)]],
    forces: ["Forces", [section(null, forceControls)]],
    // Only for structures served with vibrational modes (v_sim or phonopy).
    ...(vibrationControls ? { vibrations: ["Vibrations", [section(null, ...vibrationControls)]] } : {}),
    save: ["Save", [
      section("Structure",
        tagControl(field("Format", formatSelect), "save.format"),
        el("p", { class: "muted hint" }, "extxyz includes the evaluation chosen in the Forces tab; POSCAR and CIF hold the geometry only."),
        el("div", { class: "button-row" },
          tagControl(button("Save structure", (event) => saveStructure(event), "Save the structure on the left"), "save.structure"),
          page.structures.length > 1
            ? tagControl(button("Save compared", (event) => saveStructure(event, page.structures[1]), "Save the structure on the right"), "save.structure") : null)),
      section("Image",
        el("div", { class: "button-row" }, tagControl(button("Save SVG", () => saveImage("svg"), "The panels as shown, as a vector image"), "save.svg"),
          tagControl(button("Save PNG", () => saveImage("png"), "The panels as shown, as a bitmap image"), "save.png")),
        tagControl(checkbox("Transparent background", "svgTransparent"), "save.transparent"),
        el("div", { class: "inline-fields", "data-control": "save.png-scale" }, el("span", { class: "field-label" }, "PNG resolution ×"), pngScaleInput)),
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
    const info = renderInfo();
    // The tab left may now disappear (profiles: see applyProfile).
    page.profileView?.apply();
    // Done when the Info tab is built (it is built only while open).
    return info;
  }
  const tabBar = el("div", { class: "tab-bar", role: "tablist", "aria-label": "Viewer settings", "data-control": "tabs.bar" }, Object.values(tabButtons));
  // The tabs the profile shows (see applyProfile).
  const shownTabs = () => Object.keys(tabs).filter((key) => !tabButtons[key].hasAttribute("data-profile-hidden"));
  // Rows of at most five tabs, filled evenly (11 tabs: 4, 4 and 3).
  const layoutTabs = () => {
    const count = shownTabs().length, rows = Math.ceil(count / 5);
    tabBar.style.gridTemplateColumns = `repeat(${Math.ceil(count / rows)}, 1fr)`;
  };
  layoutTabs();
  // Arrow keys move between the shown tabs.
  tabBar.addEventListener("keydown", (event) => {
    const keys = shownTabs(), at = keys.indexOf(viewerPrefs.tab);
    const next = event.key === "ArrowRight" ? at + 1 : event.key === "ArrowLeft" ? at - 1 : null;
    if (next === null) return;
    event.preventDefault(); event.stopPropagation();
    const key = keys[(next + keys.length) % keys.length];
    showTab(key); tabButtons[key].focus();
  });
  // The profile switch (Simple | Advanced) in one row above the tabs; both
  // stay at the top while the settings scroll.
  const profileRow = el("div", { class: "profile-row" });
  controls.append(el("div", { class: "settings-head" }, profileRow, tabBar), ...Object.values(tabPanels));
  showTab(viewerPrefs.tab);
  // Which controls the page shows (profiles; see createProfileView): the
  // whole page, as some controls sit outside the settings box.
  page.profileView = createProfileView(controls.closest("#main") ?? controls, {
    profile: storedProfile(), context: page.controlContext, onApply: layoutTabs });
  page.profileView.listeners.add(storeProfile);
  // The count of advanced settings in use beside it; its list jumps to them.
  const [countButton, countList] = createProfileCount(page.profileView);
  // The search for a control (also one the profile hides). The Info tab is
  // built only while open: its controls are found there, built on choice.
  const infoControls = new Set(["info.copy-cell", "info.atom-positions", "info.structure-info", "info.provenance",
    "info.inequivalent-sites", "symmetry.tolerance"]);
  const search = createControlSearch(page.profileView, { context: page.controlContext,
    build: (id) => (infoControls.has(id) && viewerPrefs.tab !== "info" ? () => showTab("info") : null) });
  page.focusSearch = search.focus;
  profileRow.append(el("span", { class: "field-label" }, "Controls"), createProfileSwitch(page.profileView), countButton,
    search.field, countList, search.list);

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
    const sourceSelect = el("select", { class: "related-source", "aria-label": "Step through", "data-control": "step.source" },
      el("option", { value: "tags", selected: !byAggregation }, "Structures sharing a tag prefix"),
      fromAgg ? el("option", { value: "selected", selected: bySelection }, `Selected members of ${fromAgg.name}`) : null,
      state.aggregations.length ? el("optgroup", { label: "Aggregation members" },
        state.aggregations.map((a) => el("option", { value: a.id, selected: a.id === cycle }, a.name))) : null);
    sourceSelect.addEventListener("change", () => { location.hash = hash(structure.id, { cycle: sourceSelect.value }); });
    const prefixInput = el("input", { type: "text", value: viewerPrefs.prefix, class: "prefix-input", spellcheck: "false", "aria-label": "Tag prefix", "data-control": "step.prefix" });
    prefixInput.addEventListener("change", () => { viewerPrefs.prefix = prefixInput.value; savePrefs(); loadRelated(); });
    const hint = el("span", { class: "muted related-hint" });
    relatedSection.replaceChildren(
      el("div", { class: "inline-fields" }, el("span", { class: "muted" }, "Step through"), sourceSelect,
        byAggregation ? null : [el("span", { class: "muted", "data-control": "step.prefix" }, "with prefix"), prefixInput], hint));
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
    page.displacementControls?.sync();
    if (displacementInUse() && viewerPrefs.displacement.reference !== "compared") updateOverlays();
    // Outside the list (e.g. not a member of the aggregation), ← / → enter it from the end / start.
    const position = list.findIndex((r) => r.id === stepping.id);
    const step = (delta) => {
      const from = page.movie ? page.movie.index : position;
      const next = list[from < 0 ? (delta > 0 ? 0 : list.length - 1) : from + delta];
      if (next) location.hash = go(next.id);
    };
    let picker;
    if (list.length <= MAX_RELATED_CHIPS) {
      picker = el("div", { class: "chips related-chips", "data-control": "step.picker" }, list.map((r) => el("a", {
        class: "chip", href: go(r.id), "aria-pressed": String(r.id === stepping.id), title: r.id,
      }, label(r))));
    } else {
      const input = el("input", { type: "number", min: 1, max: list.length, step: 1, value: position >= 0 ? position + 1 : "",
        class: "num-input", "aria-label": "Position" });
      input.addEventListener("change", () => { const next = list[Number(input.value) - 1]; if (next) location.hash = go(next.id); });
      picker = el("span", { class: "inline-fields", "data-control": "step.picker" }, input, el("span", { class: "muted" },
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
      el("button", { type: "button", class: "small", disabled: position === 0, onclick: () => step(-1), "data-control": "step.previous-next" }, "← Previous"),
      picker,
      el("button", { type: "button", class: "small", disabled: position === list.length - 1, onclick: () => step(1), "data-control": "step.previous-next" }, "Next →")));
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
    const playButton = el("button", { type: "button", class: "small play-button", "data-control": "movie.play" }, "▶ Play");
    const frameSlider = el("input", { type: "range", min: first, max: last, step: 1, value: startAt(),
      class: "frame-slider", "aria-label": "Frame", "data-control": "movie.frame-slider" });
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
    const loopBox = el("label", { class: "check", "data-control": "movie.loop" }, el("input", { type: "checkbox", checked: viewerPrefs.player.loop,
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
      el("span", { class: "inline-fields", "data-control": "movie.fps" }, fpsInput, el("span", { class: "muted" }, "fps")), loopBox),
    el("div", { class: "player-range inline-fields", "data-control": "movie.range" }, el("span", { class: "muted" }, "Frames"), firstInput, "–", lastInput,
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
    // "/" goes to the search for a control (and not the browser's find), also
    // from a check box or button (where a search result leaves the focus);
    // not from a field that takes text or a select.
    const textField = "textarea, select, input:not([type=checkbox], [type=radio], [type=range], [type=button], [type=color])";
    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest(textField) && page.focusSearch) {
      event.preventDefault();
      page.focusSearch();
      return;
    }
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
    page.profileView?.dispose();
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
