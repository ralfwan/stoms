"""The viewer's control registry (GUI profiles), run in Node.

CONTROLS in viewer.js lists every control of the structure page and the
notebook viewer by a stable ID, with its profile level, a data rule and an
"in use" test (see the comment above CONTROLS). The browser tests that every
tagged element is a registry control are in test_viewer_controls_browser.py.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
VIEWER = ROOT / "src" / "stoms" / "web" / "static" / "viewer.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="needs node"
)

# Loads viewer.js as a classic script and prints the JSON of one expression.
_RUNNER = """
const vm = require("vm"), fs = require("fs");
const context = vm.createContext({ localStorage: { getItem: () => null, setItem() {} }, console });
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], context)));
"""


def _node(expression: str) -> Any:
    result = subprocess.run(
        ["node", "-e", _RUNNER, str(VIEWER), expression],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _registry() -> dict[str, dict[str, Any]]:
    return _node(
        "Object.fromEntries(Object.entries(CONTROLS).map(([id, c]) => [id, {"
        " level: c.level, label: c.label, keywords: c.keywords,"
        " data: typeof c.data === 'function', inUse: typeof c.inUse === 'function' }]))"
    )


# Every control ID ever released. Such an ID is never removed: a renamed
# control keeps its old ID as an entry of CONTROL_ALIASES (old -> new), so
# profile files that name it keep working. New controls are added here too.
# (embed.actions, split into four IDs before any release, is not one.)
PINNED_IDS = [
    "appearance.atom-scale",
    "appearance.bond-radius",
    "appearance.depth-cue",
    "appearance.depth-strength",
    "appearance.plane-opacity",
    "appearance.polyhedra-opacity",
    "appearance.polyhedron-edges",
    "arrows.colour",
    "arrows.displacement-reference",
    "arrows.evaluation",
    "arrows.length",
    "arrows.min-magnitude",
    "arrows.reset-style",
    "arrows.show",
    "arrows.source",
    "arrows.vector",
    "arrows.vectors",
    "arrows.width",
    "axes.axes-size",
    "axes.in-images",
    "axes.size",
    "axes.tripod",
    "axes.wave-size",
    "bonds.cutoffs",
    "bonds.outside",
    "bonds.reset-cutoffs",
    "bonds.show",
    "cell.matrix",
    "cell.matrix-entries",
    "cell.matrix-preset",
    "cell.outline",
    "cell.outline-colour",
    "cell.outline-every-copy",
    "cell.outline-style",
    "cell.outline-width",
    "cell.repeat",
    "cell.single-cell",
    "cell.stored-outline",
    "cell.wrap",
    "colour.component",
    "colour.custom-palette",
    "colour.error-pair",
    "colour.mode",
    "colour.palette",
    "colour.property",
    "colour.range",
    "colour.read-as",
    "colour.symmetric",
    "compare.close",
    "compare.open-file",
    "compare.steps-side",
    "compare.swap",
    "compare.with",
    "elements.bar",
    "elements.colour",
    "elements.editor",
    "elements.radius",
    "elements.reset",
    "embed.measure-toggle",
    "embed.panel-size",
    "embed.pop-out",
    "embed.reset-view",
    "embed.save-html",
    "embed.settings-toggle",
    "footer.clear-all",
    "footer.save-svg",
    "forces.follow-slice",
    "forces.include-all",
    "forces.include-bounds",
    "forces.include-elements",
    "frames.number",
    "frames.play",
    "frames.slider",
    "frames.step",
    "hbonds.acceptors",
    "hbonds.angle",
    "hbonds.distance",
    "hbonds.per-acceptor",
    "hbonds.show",
    "help.mouse-keys",
    "highlight.apply",
    "highlight.clear-selection",
    "highlight.groups",
    "highlight.remove-all",
    "highlight.select",
    "highlight.select-all",
    "info.atom-positions",
    "info.copy-cell",
    "info.inequivalent-sites",
    "info.provenance",
    "info.structure-info",
    "labels.mode",
    "measure.list",
    "measure.mode",
    "measure.plane-choice",
    "measure.polyhedra-clear",
    "measure.polyhedra-csv",
    "measure.polyhedra-list",
    "measure.stop",
    "movie.fps",
    "movie.frame-slider",
    "movie.loop",
    "movie.play",
    "movie.range",
    "page.selected",
    "panel.resize",
    "phonon.nac",
    "phonon.path-slider",
    "phonon.resize",
    "phonon.save-svg",
    "phonon.side",
    "planes.add-miller",
    "planes.colour",
    "planes.extend",
    "planes.fit-text",
    "planes.make",
    "planes.miller-indices",
    "planes.patch",
    "planes.pick-atoms",
    "planes.position",
    "planes.remove",
    "planes.show",
    "polyhedra.centre-atoms",
    "polyhedra.centres",
    "polyhedra.show",
    "rings.all-atoms",
    "rings.alternating",
    "rings.count",
    "rings.custom-palette",
    "rings.cutoffs",
    "rings.elements",
    "rings.enclosed",
    "rings.from-selection",
    "rings.label-size",
    "rings.labels",
    "rings.method",
    "rings.opacity",
    "rings.outline",
    "rings.scheme",
    "rings.search-size",
    "rings.show",
    "rings.size-colour",
    "rings.size-range",
    "rings.summary-actions",
    "save.format",
    "save.png",
    "save.png-scale",
    "save.structure",
    "save.svg",
    "save.transparent",
    "settings.export-import",
    "settings.restore-defaults",
    "slice.bounds",
    "slice.elements",
    "slice.show-all",
    "step.picker",
    "step.prefix",
    "step.previous-next",
    "step.source",
    "style.model",
    "style.radius-type",
    "style.reset-appearance",
    "symmetry.tolerance",
    "tabs.bar",
    "vibration.amplitude",
    "vibration.apply-repeat",
    "vibration.arrows",
    "vibration.bonds",
    "vibration.direction",
    "vibration.mode",
    "vibration.period",
    "vibration.play",
    "vibration.q-point",
    "vibration.record",
    "vibration.unit",
    "vibration.video-fps",
    "vibration.video-periods",
    "vibration.video-size",
    "vibration.wave-colours",
    "vibration.wave-labels",
    "vibration.wave-legend",
    "vibration.wave-styles",
    "vibration.wave-vector",
    "view.along",
    "view.fit",
    "view.preset",
    "view.roll",
]


def test_registry_ids_are_pinned() -> None:
    registry = _registry()
    aliases = _node("CONTROL_ALIASES")
    missing = [
        i
        for i in PINNED_IDS
        if i not in registry and aliases.get(i) not in registry
    ]
    assert missing == [], "removed control IDs need an alias"
    assert sorted(set(registry) - set(PINNED_IDS)) == [], (
        "pin the new control IDs"
    )
    assert all(target in registry for target in aliases.values())
    assert len(set(PINNED_IDS)) == len(PINNED_IDS)


def test_every_control_has_a_label_and_keywords() -> None:
    for key, control in _registry().items():
        assert control["level"] in ("simple", "advanced"), key
        assert control["label"].strip(), key
        assert control["keywords"], key
        assert all(isinstance(k, str) and k for k in control["keywords"])


# Controls that are never revealed because they are in use: actions, outputs,
# the camera, and remembered UI state (the evaluation, vector and pair
# chosen, the property chosen automatically, the open tab, the file format,
# the tag prefix, panel sizes, click modes, movie and vibration state).
NEVER_IN_USE = {
    "info.copy-cell", "info.atom-positions", "info.structure-info",
    "info.provenance", "info.inequivalent-sites", "view.preset",
    "view.along", "view.roll", "view.fit", "cell.matrix-preset",
    "settings.export-import", "settings.restore-defaults",
    "help.mouse-keys", "elements.reset", "bonds.reset-cutoffs",
    "style.reset-appearance", "colour.property", "colour.error-pair",
    "highlight.select", "highlight.select-all", "highlight.clear-selection",
    "highlight.apply", "highlight.remove-all", "slice.show-all",
    "measure.mode", "measure.plane-choice", "measure.polyhedra-csv",
    "measure.polyhedra-clear", "measure.stop", "planes.add-miller",
    "planes.pick-atoms", "planes.make", "planes.remove", "planes.fit-text",
    "rings.summary-actions", "rings.from-selection", "rings.all-atoms",
    "arrows.evaluation", "arrows.vector", "arrows.reset-style",
    "forces.include-all", "vibration.q-point", "vibration.direction",
    "vibration.mode", "vibration.play", "vibration.record",
    "vibration.apply-repeat", "save.format", "save.structure", "save.svg",
    "save.png", "page.selected", "step.source", "step.prefix",
    "step.previous-next", "step.picker", "movie.play", "movie.frame-slider",
    "movie.range", "compare.with", "compare.open-file", "compare.steps-side",
    "compare.swap", "compare.close", "elements.editor", "footer.save-svg",
    "footer.clear-all", "panel.resize", "tabs.bar", "phonon.nac",
    "phonon.save-svg", "phonon.path-slider", "phonon.resize", "frames.step",
    "frames.slider", "frames.number", "frames.play", "embed.pop-out",
    "embed.measure-toggle", "embed.settings-toggle",
    "embed.panel-size", "embed.save-html", "embed.reset-view",
}  # fmt: skip

# An atom reference and a plane through three atoms (rutile: Ti2O4).
_REF = '{ index: 0, image: [0, 0, 0], symbol: "Ti", count: 6 }'
_ATOM_PLANE = (
    "{ atoms: [0, 2, 3].map((index) => ({ index, image: [0, 0, 0],"
    ' symbol: index ? "O" : "Ti", count: 6 })), show: true, patch: false }'
)

# Per control with an "in use" test: a change of the stored settings `p`
# (and of the page state in `ctx`) that puts it in use.
IN_USE_CASES: dict[str, str] = {
    "symmetry.tolerance": "p.symmetry.tolerance = 0.1",
    "cell.single-cell": "p.singleCell = true",
    "cell.repeat": "p.repeat = [1, 2, 1]",
    "cell.matrix": "p.repeatMatrix = [[2, 0, 0], [0, 1, 0], [0, 0, 1]]",
    "cell.matrix-entries": "p.repeatMatrix = [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]",
    "cell.stored-outline": "p.storedCellOutline = true; p.repeatMatrix = [[2, 0, 0], [0, 1, 0], [0, 0, 1]]",
    "cell.outline": "p.cell = false",
    "cell.outline-every-copy": "p.repeatCellOutline = true",
    "cell.outline-width": "p.appearance.cellWidth = 2",
    "cell.outline-colour": 'p.appearance.cellColour = "#ff0000"',
    "cell.outline-style": 'p.appearance.cellDash = "dashed"',
    "cell.wrap": "p.wrap = true",
    "axes.tripod": 'p.tripod.axes = "off"',
    "axes.in-images": "p.tripod.export = false",
    "axes.size": "p.tripod.size = 2",
    "axes.axes-size": "p.tripod.axesSize = 1.5",
    "axes.wave-size": "p.tripod.waveSize = 0.5",
    "style.model": 'p.style = "stick"',
    "style.radius-type": 'p.radiusType = "vdw"',
    "bonds.show": "p.bonds = true",
    "polyhedra.show": "p.polyhedra = true",
    "polyhedra.centre-atoms": "p.polyhedraCentres = false",
    "labels.mode": 'p.labels = "index"',
    "elements.colour": 'p.appearance.colours.O = "#00ff00"',
    "elements.radius": "p.appearance.radii.Ti = 1.2",
    "appearance.atom-scale": "p.appearance.atomScale = 1.5",
    "appearance.bond-radius": "p.appearance.bondRadius = 0.12",
    "appearance.polyhedra-opacity": "p.appearance.polyAlpha = 0.8",
    "appearance.plane-opacity": "p.appearance.planeAlpha = 0.5",
    "appearance.polyhedron-edges": "p.appearance.polyEdges = false",
    "appearance.depth-cue": "p.appearance.depthCue = true",
    "appearance.depth-strength": "p.appearance.depthStrength = 0.3",
    "bonds.cutoffs": 'p.cutoffs["O-Ti"] = 2.8',
    "hbonds.show": "p.hbonds.show = true",
    "hbonds.acceptors": 'p.hbonds.acceptors = ["O"]',
    "hbonds.distance": "p.hbonds.max = 3",
    "hbonds.per-acceptor": "p.hbonds.perAcceptor = true",
    "hbonds.angle": "p.hbonds.angle = 140",
    "bonds.outside": 'p.bondedOutside = "ligands"',
    "polyhedra.centres": "p.polyCenters = []",
    "colour.mode": 'p.colour = "height"',
    "colour.component": 'p.colour = "property"; p.property.component = "z"',
    "colour.read-as": 'p.colour = "property"; p.property.kind = "categories"',
    "colour.range": 'p.colour = "property"; p.property.max = 2',
    "colour.symmetric": 'p.colour = "property"; p.property.symmetric = true',
    "colour.palette": 'p.colour = "height"; p.palettes.height = "viridis"',
    "colour.custom-palette": 'p.colour = "property"; p.palettes.property = "custom"; p.customPalette = ["#000000", "#ffffff"]',
    "highlight.groups": "ctx.highlightGroups = 1",
    "slice.elements": 'p.hiddenElements = ["O"]',
    "slice.bounds": "p.slice[2][0] = 0.5",
    "measure.list": "ctx.measurements = 2",
    "measure.polyhedra-list": "ctx.polyhedra = 1",
    "planes.show": "p.planes = [{ h: 0, k: 0, l: 1, t: 0.5, show: false }]",
    "planes.colour": "p.planes = [{ h: 0, k: 0, l: 1, t: 0.5, show: true }]",
    "planes.miller-indices": "p.planes = [{ h: 1, k: 1, l: 0, t: 0.5, show: true }]",
    "planes.position": "p.planes = [{ h: 0, k: 0, l: 1, t: 0.25, show: true }]",
    "planes.extend": "p.planes = [{ h: 0, k: 0, l: 1, t: 0.5, show: true, scale: 2 }]",
    "planes.patch": f"p.planes = [{{ ...{_ATOM_PLANE}, patch: true }}]",
    "rings.show": "p.rings.show = true",
    "rings.size-colour": 'p.rings.colours[6] = "#123456"',
    "rings.method": 'p.rings.method = "shortest-path"',
    "rings.search-size": "p.rings.searchSize = 16",
    "rings.elements": "p.rings.elements.O = { use: false, zmin: null, zmax: null }",
    "rings.alternating": "p.rings.alternating = true",
    "rings.cutoffs": 'p.rings.cutoffs["O-Ti"] = 2.4',
    "rings.count": 'p.rings.count = "all"',
    "rings.enclosed": "p.rings.enclosed = false",
    "rings.size-range": "p.rings.minSize = 5",
    "rings.scheme": 'p.rings.scheme = "viridis"',
    "rings.custom-palette": 'p.rings.scheme = "custom"; p.customPalette = ["#000000", "#ffffff"]',
    "rings.opacity": "p.rings.alpha = 0.8",
    "rings.outline": "p.rings.outline = false",
    "rings.labels": "p.rings.labels = true",
    "rings.label-size": "p.rings.labelScale = 2",
    "arrows.source": 'p.arrows.source = "displacement"',
    "arrows.vectors": 'p.arrows.source = "displacement"',
    "arrows.displacement-reference": 'p.arrows.show = true; p.arrows.source = "displacement"; p.displacement.reference = "previous"',
    "arrows.show": "p.arrows.show = true",
    "arrows.length": "p.arrows.scale = 3",
    "arrows.width": "p.arrows.width = 0.1",
    "arrows.colour": 'p.arrows.colour = "#ff0000"',
    "arrows.min-magnitude": "p.arrows.minMagnitude = 0.05",
    "forces.follow-slice": "p.forceFollowsSlice = false",
    "forces.include-elements": 'p.forceHiddenElements = ["Ti"]',
    "forces.include-bounds": "p.forceSlice[2][1] = 0.4",
    "vibration.amplitude": "p.vibration.amplitude = 0.5",
    "vibration.period": "p.vibration.periodSeconds = 2",
    "vibration.bonds": 'p.vibration.bonds = "live"',
    "vibration.unit": 'p.vibration.unit = "cm-1"',
    "vibration.arrows": "p.vibration.showArrows = true",
    "vibration.video-periods": "p.vibration.recordPeriods = 4",
    "vibration.video-size": 'p.vibration.videoSize = "1080p"',
    "vibration.video-fps": 'p.vibration.videoFps = "30"',
    "vibration.wave-vector": 'p.tripod.axes = "xyz"; p.vibration.waveVector = true',
    "vibration.wave-colours": 'p.vibration.vgColour = "#000000"',
    "vibration.wave-styles": 'p.vibration.qDash = "dotted"',
    "vibration.wave-labels": "p.vibration.waveLabels = false",
    "vibration.wave-legend": "p.vibration.waveLegend = false",
    "save.transparent": "p.svgTransparent = false",
    "save.png-scale": "p.pngScale = 4",
    "movie.fps": "p.player.fps = 25",
    "movie.loop": "p.player.loop = false",
    "elements.bar": 'p.hiddenElements = ["Ti"]',
    "phonon.side": "p.vibration.plotSide = true",
}  # fmt: skip

# Rutile TiO2: Ti a transition metal; the controls made on load fill the
# bond cutoffs with their defaults (as createCutoffControls does).
_SETUP = """
const ctxFor = () => controlContext([{ symbols: ["Ti", "Ti", "O", "O", "O", "O"], pbc: [true, true, true] }]);
const prefsFor = () => {
  const p = normalizePrefs({});
  for (const [a, b] of [["O", "O"], ["O", "Ti"], ["Ti", "Ti"]]) p.cutoffs[pairKey(a, b)] ??= defaultCutoff(a, b);
  return p;
};
// A change that returns NO_CONTEXT asks without a context (no structure).
const NO_CONTEXT = {};
const inUseAfter = (change) => {
  const p = prefsFor(), ctx = ctxFor();
  const asked = change(p, ctx) === NO_CONTEXT ? undefined : ctx;
  return Object.keys(CONTROLS).filter((id) => controlInUse(id, p, asked));
};
"""


def _in_use_after(changes: dict[str, str]) -> dict[str, list[str]]:
    """The controls in use after each change (JavaScript statements on the
    settings `p` and the context `ctx`, see _SETUP)."""
    body = ", ".join(
        f"{json.dumps(name)}: inUseAfter((p, ctx) => {{ {change}; }})"
        for name, change in changes.items()
    )
    return _node(f"(() => {{ {_SETUP} return {{ {body} }}; }})()")


def test_in_use_tests_cover_the_registry() -> None:
    registry = _registry()
    with_test = {key for key, value in registry.items() if value["inUse"]}
    assert sorted(with_test - set(IN_USE_CASES)) == []
    assert sorted(set(IN_USE_CASES) - with_test) == []
    assert sorted(with_test & NEVER_IN_USE) == []
    assert with_test | NEVER_IN_USE == set(registry)


def test_default_settings_put_no_control_in_use() -> None:
    result = _in_use_after({"defaults": "", "no context": "return NO_CONTEXT"})
    assert result == {"defaults": [], "no context": []}
    # Also the settings as a fresh browser stores them, and as Python sends them.
    assert (
        _node(
            "Object.keys(CONTROLS).filter((id) => controlInUse(id, normalizePrefs(JSON.parse(JSON.stringify(defaultPrefs())))))"
        )
        == []
    )


def test_each_documented_change_puts_its_control_in_use() -> None:
    result = _in_use_after(IN_USE_CASES)
    assert sorted(key for key in IN_USE_CASES if key not in result[key]) == []


def test_bond_cutoffs_compare_each_pair_with_its_default() -> None:
    result = _in_use_after(
        {
            # Filled in with the defaults (as on load): not in use.
            "filled": "",
            "same value again": 'p.cutoffs["O-Ti"] = defaultCutoff("O", "Ti")',
            "a pair of another structure": 'p.cutoffs["Cu-O"] = defaultCutoff("Cu", "O")',
            "changed": 'p.cutoffs["O-O"] = 1.9',
            "a minimum": 'p.bondMinimums["O-Ti"] = 1.5',
        }
    )
    assert result["filled"] == []
    assert result["same value again"] == []
    assert result["a pair of another structure"] == []
    assert result["changed"] == ["bonds.cutoffs"]
    assert result["a minimum"] == ["bonds.cutoffs"]


def test_remembered_ui_state_never_counts() -> None:
    result = _in_use_after(
        {
            "forceChoice": 'p.forceChoice = { spec: "abc", method: "mace", name: "forces" }',
            "pairChoice": 'p.pairChoice = [{ spec: "a", method: "x" }, { spec: "b", method: "y" }]',
            "tab": 'p.tab = "rings"',
            "saveFormat": 'p.saveFormat = "cif"',
            "prefix": 'p.prefix = "iteration:"',
            "panelSize": "p.panelSize = { width: 800, height: 600 }",
            "property.choice": 'p.property.choice = { source: "derived", name: "coordination" }',
            "plot size": "p.vibration.plotWidth = 900; p.vibration.plotHeight = 500",
        }
    )
    assert result == {key: [] for key in result}


_PROPERTY_CONTROLS = [
    "colour.component",
    "colour.read-as",
    "colour.range",
    "colour.symmetric",
]
_PROPERTY_SETTINGS = (
    'p.property.component = "z"; p.property.kind = "categories";'
    " p.property.min = -1; p.property.max = 2; p.property.symmetric = true"
)


def test_settings_of_a_mode_not_in_use_do_not_count() -> None:
    result = _in_use_after(
        {
            # Palettes count only for the colouring in use.
            "palette of another mode": 'p.palettes.height = "viridis"',
            "palette of the mode": 'p.palettes.height = "viridis"; p.colour = "height"',
            # The custom colours only when a custom palette shows them.
            "custom colours unused": 'p.customPalette = ["#000000", "#ffffff"]',
            "custom palette of another mode": 'p.palettes.force = "custom"; p.customPalette = ["#000000", "#ffffff"]',
            "custom palette, default colours": 'p.colour = "force"; p.palettes.force = "custom"',
            "custom colours in capitals": 'p.colour = "force"; p.palettes.force = "custom"; p.customPalette = ["#F2F0E9", "#8C1D40"]',
            # The stored cell outline only with a matrix.
            "stored outline without a matrix": "p.storedCellOutline = true",
            # The displacement reference only while displacements are shown.
            "reference unused": 'p.displacement.reference = "frame"; p.displacement.frame = 3',
            "reference, displacement colours": 'p.displacement.reference = "previous"; p.colour = "property";'
            ' p.property.choice = { source: "derived", name: "displacement" }',
            # The property colouring's settings only in property mode.
            "property settings, element colours": _PROPERTY_SETTINGS,
            "property settings, property colours": f'{_PROPERTY_SETTINGS}; p.colour = "property"',
        }
    )
    assert result["palette of another mode"] == []
    assert result["palette of the mode"] == ["colour.mode", "colour.palette"]
    assert result["custom colours unused"] == []
    assert result["custom palette of another mode"] == []
    assert result["custom palette, default colours"] == [
        "colour.mode",
        "colour.palette",
    ]
    assert result["custom colours in capitals"] == [
        "colour.mode",
        "colour.palette",
    ]
    assert result["stored outline without a matrix"] == []
    assert result["reference unused"] == []
    assert result["reference, displacement colours"] == [
        "colour.mode",
        "arrows.displacement-reference",
    ]
    assert result["property settings, element colours"] == []
    assert result["property settings, property colours"] == [
        "colour.mode",
        *_PROPERTY_CONTROLS,
    ]


def test_locked_settings_count() -> None:
    """Owner decision 11: a setting overridden by a lock is still in use."""
    result = _in_use_after(
        {
            "matrix under single cell only": "p.singleCell = true;"
            " p.repeatMatrix = [[2, 0, 0], [0, 1, 0], [0, 0, 1]]",
            "radius type in stick": 'p.style = "stick"; p.radiusType = "ionic"',
            "every copy without an outline": "p.cell = false; p.repeatCellOutline = true",
        }
    )
    assert result["matrix under single cell only"] == [
        "cell.single-cell",
        "cell.matrix",
        "cell.matrix-entries",
    ]
    assert result["radius type in stick"] == [
        "style.model",
        "style.radius-type",
    ]
    assert result["every copy without an outline"] == [
        "cell.outline",
        "cell.outline-every-copy",
    ]


def test_polyhedron_centres_compare_with_the_transition_metals() -> None:
    result = _in_use_after(
        {
            # null and the list of the structure's transition metals are the same.
            "the transition metals": 'p.polyCenters = ["Ti"]',
            "none": "p.polyCenters = []",
            "without the structure": 'p.polyCenters = ["Ti"]; return NO_CONTEXT',
        }
    )
    assert result == {
        "the transition metals": [],
        "none": ["polyhedra.centres"],
        "without the structure": ["polyhedra.centres"],
    }


def test_data_rules() -> None:
    simple = _node(
        """(() => {
          const ids = ["hbonds.show", "polyhedra.centres", "cell.repeat", "arrows.show", "arrows.evaluation",
            "vibration.mode", "phonon.save-svg", "step.previous-next", "frames.play", "compare.close",
            "page.selected", "bonds.cutoffs", "style.model", "arrows.source"];
          const at = (structures, extra) => {
            const ctx = controlContext(structures, extra);
            return Object.fromEntries(ids.map((id) => [id, controlIsSimple(id, ctx)]));
          };
          return {
            water: at([{ symbols: ["O", "H", "H"], pbc: [false, false, false] }]),
            rutile: at([{ symbols: ["Ti", "O"], pbc: [true, true, true], has_modes: true, has_phonons: true }],
              { hasVectors: true, stepCount: 3, frames: 2, comparing: true, fromAggregation: true }),
            displacements: at([{ symbols: ["Pt"], pbc: [true, true, false] }], { canDisplace: true }),
          };
        })()"""
    )
    water, rutile = simple["water"], simple["rutile"]
    # Simple only with the data: H bonds with H and O, N or F; the
    # polyhedron centres with a metal; the repeat with a periodic axis; ...
    assert water["hbonds.show"] and not rutile["hbonds.show"]
    assert rutile["polyhedra.centres"] and not water["polyhedra.centres"]
    assert rutile["cell.repeat"] and not water["cell.repeat"]
    for key in [
        "arrows.show",
        "arrows.evaluation",
        "vibration.mode",
        "phonon.save-svg",
        "step.previous-next",
        "frames.play",
        "compare.close",
        "page.selected",
    ]:
        assert rutile[key] and not water[key], key
    # Arrows of displacements need no per-atom vectors; the evaluation does.
    assert simple["displacements"]["arrows.show"]
    assert not simple["displacements"]["arrows.evaluation"]
    # The source is simple only with something to displace and no vectors
    # (the structure page does not fall back to displacements by itself).
    assert simple["displacements"]["arrows.source"]
    assert not rutile["arrows.source"] and not water["arrows.source"]
    assert (
        _node(
            "controlIsSimple('arrows.source', controlContext([], { canDisplace: true, hasVectors: true }))"
        )
        is False
    )
    # Without a data rule, the level decides.
    assert not water["bonds.cutoffs"] and not rutile["bonds.cutoffs"]
    assert water["style.model"] and rutile["style.model"]


def test_only_the_settings_button_is_never_hidden() -> None:
    """The profile switch lives in the notebook's ⚙ panel, so no profile
    may hide its button."""
    assert _node(
        "Object.keys(CONTROLS).filter((id) => controlNeverHidden(id))"
    ) == ["embed.settings-toggle"]


def test_control_context_from_structures() -> None:
    ctx = _node(
        'controlContext([{ symbols: ["H", "N", "Cu"], pbc: [false, false, true] }, null], { frames: 3 })'
    )
    assert ctx["species"] == ["Cu", "H", "N"]
    assert ctx["periodic"] and ctx["hasMetal"]
    assert ctx["hasHydrogenBondPartners"]
    assert not ctx["hasModes"] and not ctx["hasSymmetry"]
    assert ctx["frames"] == 3 and ctx["stepCount"] == 0


def test_aliases_resolve_to_controls() -> None:
    assert _node(
        """(() => {
          CONTROL_ALIASES["cell.old-name"] = "cell.repeat";
          return [controlId("cell.old-name"), controlIsSimple("cell.old-name", controlContext([], { periodic: true })),
            controlInUse("cell.old-name", { ...normalizePrefs({}), repeat: [2, 1, 1] })];
        })()"""
    ) == ["cell.repeat", True, True]


def test_profiles_show_controls_by_level_and_use() -> None:
    """Advanced shows every control; simple the simple ones (level or data
    rule), the never-hidden ⚙ button and every control in use (so no setting
    that changes the picture is hidden). Unknown IDs are shown."""
    result = _node(
        f"""(() => {{ {_SETUP}
          const ids = Object.keys(CONTROLS), p = prefsFor(), ctx = ctxFor();
          const shown = (profile, prefs) => ids.filter((id) => controlShown(id, profile, ctx, prefs));
          const changed = prefsFor();
          changed.repeatMatrix = [[2, 1, 0], [-1, 1, 0], [0, 0, 1]];
          return {{
            ids, advanced: shown("advanced", p), simple: shown("simple", p),
            expected: ids.filter((id) => controlIsSimple(id, ctx) || controlNeverHidden(id)),
            matrix: [controlIsSimple("cell.matrix", ctx), shown("simple", changed).includes("cell.matrix")],
            unknown: controlShown("no.such-control", "simple", ctx, p),
            settings: controlShown("embed.settings-toggle", "simple", controlContext([]), normalizePrefs({{}})),
          }};
        }})()"""
    )
    assert result["advanced"] == result["ids"]
    assert result["simple"] == result["expected"]
    assert len(result["simple"]) < len(result["ids"])
    # An advanced control in use is shown in simple.
    assert result["matrix"] == [False, True]
    assert result["unknown"] is True and result["settings"] is True


def test_profile_names() -> None:
    assert _node(
        "[DEFAULT_PROFILE, Object.keys(PROFILES), validProfile('advanced'),"
        " validProfile('expert'), validProfile(null), storedProfile()]"
    ) == [
        "simple",
        ["simple", "advanced"],
        "advanced",
        "simple",
        "simple",
        "simple",
    ]


def test_advanced_controls_for_the_count() -> None:
    """What the count and the "adv." mark consider advanced: not simple by
    level or data rule, and not a control no profile hides."""
    result = _node(
        "(() => { const ctx = controlContext([{ symbols: ['O', 'H', 'H'], pbc: [true, true, true] }]);"
        " const bare = controlContext([{ symbols: ['C'], pbc: [true, true, true] }]);"
        " return { matrix: controlAdvanced('cell.matrix', ctx), repeat: controlAdvanced('cell.repeat', ctx),"
        " hbondsWater: controlAdvanced('hbonds.show', ctx), hbondsCarbon: controlAdvanced('hbonds.show', bare),"
        " settings: controlAdvanced('embed.settings-toggle', ctx), unknown: controlAdvanced('no.such', ctx) }; })()"
    )
    assert result == {
        "matrix": True,
        "repeat": False,
        "hbondsWater": False,
        "hbondsCarbon": True,
        "settings": False,
        "unknown": False,
    }


def test_matrix_entries_count_with_the_matrix() -> None:
    """countsWith: the entries are counted (and listed) as the matrix; every
    countsWith names a control that is no part of another itself."""
    result = _node(
        "({ entries: controlCountedAs('cell.matrix-entries'), matrix: controlCountedAs('cell.matrix'),"
        " repeat: controlCountedAs('cell.repeat'),"
        " links: Object.entries(CONTROLS).filter(([, c]) => c.countsWith).map(([id, c]) => [id, c.countsWith,"
        " Object.hasOwn(CONTROLS, c.countsWith) && !CONTROLS[c.countsWith].countsWith]) })"
    )
    assert result["entries"] == "cell.matrix"
    assert result["matrix"] == "cell.matrix"
    assert result["repeat"] == "cell.repeat"
    assert result["links"] == [["cell.matrix-entries", "cell.matrix", True]]


# ------------------------------------------------------------ feature search

# Search entries from the registry as the structure page builds them (all
# available, place given per ID), for searchControls.
_SEARCH_SETUP = """
  const entry = (id, place = [], available = true) => ({ id, label: CONTROLS[id].label, keywords: CONTROLS[id].keywords,
    place, available });
  const ids = (found) => found.map((e) => e.id);
"""


def test_search_matches_labels_keywords_and_places() -> None:
    """Case-insensitive parts of the label, a keyword, or the tab and section
    names; every word must match somewhere; no docs text."""
    result = _node(
        f"""(() => {{ {_SEARCH_SETUP}
          const entries = [entry("cell.repeat", ["View", "Cell"]), entry("cell.matrix", ["View", "Cell"]),
            entry("hbonds.angle", ["Style", "Bond search"]), entry("save.png", ["Save", "Image"])];
          return {{
            supercell: ids(searchControls("supercell", entries)),
            upper: ids(searchControls("SUPERCELL", entries)),
            label: ids(searchControls("transformation MAT", entries)),
            keyword: ids(searchControls("linear", entries)),
            section: ids(searchControls("bond search", entries)),
            tab: ids(searchControls("save", entries)),
            words: ids(searchControls("matrix  cell", entries)),
            nothing: ids(searchControls("matrix angle", entries)),
            blank: ids(searchControls("   ", entries)),
          }};
        }})()"""
    )
    assert result["supercell"] == ["cell.repeat", "cell.matrix"]
    assert result["upper"] == result["supercell"]
    assert result["label"] == ["cell.matrix"]
    # "linearity" is a keyword of the D–H···A angle.
    assert result["keyword"] == ["hbonds.angle"]
    assert result["section"] == ["hbonds.angle"]
    assert result["tab"] == ["save.png"]
    # Words may match different fields ("cell": the section).
    assert result["words"] == ["cell.matrix"]
    assert result["nothing"] == []
    assert result["blank"] == []


def test_search_ranks_label_before_keyword_before_place() -> None:
    """Best first: the query at the start of the label, in the label, as a
    keyword, in a keyword, in the place; then entries that can be chosen;
    then the given order."""
    result = _node(
        f"""(() => {{ {_SEARCH_SETUP}
          const entries = [entry("rings.outline", ["Rings", "Appearance"]), entry("cell.outline-every-copy", ["View", "Cell"]),
            entry("cell.outline", ["View", "Cell"]), entry("cell.matrix-preset", ["View", "Cell"]),
            entry("vibration.apply-repeat", ["Vibrations"], false), entry("cell.repeat", ["View", "Cell"])];
          return {{
            outline: ids(searchControls("outline", entries)),
            cell: ids(searchControls("cell", entries)),
            supercell: ids(searchControls("supercell", entries)),
          }};
        }})()"""
    )
    # "Outline every copy" (start of the label) before "Ring outlines" and
    # "Cell outline" (in the label), these two in the given order.
    assert result["outline"] == [
        "cell.outline-every-copy",
        "rings.outline",
        "cell.outline",
    ]
    # Label ("Cell outline") before a part of a keyword ("supercell") before
    # the section "Cell" (the matrix preset); the one that cannot be chosen
    # after those that can, within its rank.
    assert result["cell"] == [
        "cell.outline",
        "cell.outline-every-copy",
        "cell.repeat",
        "vibration.apply-repeat",
        "cell.matrix-preset",
    ]
    # The one that cannot be chosen goes after those that can (same rank),
    # although it comes first in the given order.
    assert result["supercell"] == [
        "cell.outline-every-copy",
        "cell.repeat",
        "vibration.apply-repeat",
    ]


def test_search_notes_name_structure_page_controls() -> None:
    """CONTROL_NEEDS: every listed control is a registry control of the
    structure page, listed once; every `after` names another reason with a
    data test; notes are short."""
    result = _node(
        "({ listed: Object.values(CONTROL_NEEDS).flatMap((n) => n.controls),"
        " unknown: Object.values(CONTROL_NEEDS).flatMap((n) => n.controls).filter((id) => !Object.hasOwn(CONTROLS, id) || CONTROLS[id].notebookOnly),"
        " after: Object.values(CONTROL_NEEDS).filter((n) => n.after).map((n) => typeof CONTROL_NEEDS[n.after]?.has),"
        " notes: Object.values(CONTROL_NEEDS).map((n) => n.note) })"
    )
    assert result["unknown"] == []
    assert len(result["listed"]) == len(set(result["listed"]))
    assert result["after"] and set(result["after"]) == {"function"}
    assert all(0 < len(note) <= 60 for note in result["notes"])


def test_search_note_of_a_control_that_needs_data_first() -> None:
    """No modes: the NAC direction needs the modes first (after)."""
    result = _node(
        "(() => { const none = controlContext([{ symbols: ['Si'], pbc: [true, true, true] }]);"
        " const modes = controlContext([{ symbols: ['Si'], pbc: [true, true, true], has_modes: true }]);"
        " return [controlNeed('vibration.direction', none).note, controlNeed('vibration.direction', modes).note,"
        " controlNeed('phonon.nac', none).note, controlNeed('compare.swap', none).note, controlNeed('cell.repeat', none)]; })()"
    )
    assert result == [
        "needs vibrational modes",
        "only at Γ with NAC data",
        "needs phonon data (phonopy)",
        "only while comparing",
        None,
    ]


def test_notebook_only_controls() -> None:
    """The structure page's search leaves out the notebook's own controls."""
    assert sorted(
        _node(
            "Object.keys(CONTROLS).filter((id) => CONTROLS[id].notebookOnly)"
        )
    ) == [
        "arrows.vectors",
        "embed.measure-toggle",
        "embed.panel-size",
        "embed.pop-out",
        "embed.reset-view",
        "embed.save-html",
        "embed.settings-toggle",
        "frames.number",
        "frames.play",
        "frames.slider",
        "frames.step",
        "view.along",
    ]


def test_search_reasons_that_are_settings_name_their_control() -> None:
    """`requires`: a reason that is another setting names the control of
    that setting (a structure-page control outside the reason); reasons
    about the data (with a data test, `has`) name none."""
    result = _node(
        "Object.entries(CONTROL_NEEDS).map(([key, n]) => [key, n.requires ?? null,"
        " n.requires ? Object.hasOwn(CONTROLS, n.requires) && !CONTROLS[n.requires].notebookOnly"
        " && !n.controls.includes(n.requires) : null, typeof n.has === 'function'])"
    )
    requires = {key: req for key, req, _, _ in result if req}
    assert requires == {
        "matrix": "cell.matrix",
        "property": "colour.mode",
        "vectorProperty": "colour.property",
        "forceDifference": "colour.mode",
        "valueColour": "colour.mode",
        "customPalette": "colour.palette",
        "rings": "rings.show",
        "displacements": "arrows.source",
        "forceSelection": "forces.follow-slice",
        "tagPrefix": "step.source",
    }
    assert all(valid for _, req, valid, _ in result if req)
    assert not [key for key, req, _, has in result if req and has]


def test_phonon_and_vibration_keywords() -> None:
    """Every phonon and vibration control is found by "phonon", every
    vibration control by "vibration"; no keyword twice."""
    registry = _registry()
    for key, control in registry.items():
        words = [k.lower() for k in control["keywords"]]
        assert len(words) == len(set(words)), key
        if key.startswith(("phonon.", "vibration.")):
            assert "phonon" in words, key
        if key.startswith("vibration."):
            assert "vibration" in words, key
