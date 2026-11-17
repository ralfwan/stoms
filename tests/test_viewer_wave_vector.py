"""The wave vector and group velocity on the axis tripod (viewer.js, in Node).

q is reduced to the first Brillouin zone (the Wigner-Seitz cell of the
reciprocal lattice, without 2 pi) and drawn to the scale of its farthest
point; it needs the Cartesian axes alone.
"""

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

VIEWER = (
    Path(__file__).parents[1]
    / "src"
    / "stoms"
    / "web"
    / "static"
    / "viewer.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="needs node"
)

_RUNNER = """
const vm = require("vm"), fs = require("fs");
const context = vm.createContext({ localStorage: { getItem: () => null, setItem() {} }, console });
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
process.stdout.write(JSON.stringify(vm.runInContext(process.argv[2], context)));
"""

SC = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
FCC = [[0, 0.5, 0.5], [0.5, 0, 0.5], [0.5, 0.5, 0]]
HEX = [[1, 0, 0], [-0.5, math.sqrt(3) / 2, 0], [0, 0, 1.6]]


def _node(expression: str) -> Any:
    result = subprocess.run(
        ["node", "-e", _RUNNER, str(VIEWER), expression],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _zone(cell: list[list[float]], q: list[float]) -> list[float]:
    return _node(
        f"firstZonePoint({json.dumps(cell)}, {json.dumps(q)}).reduced"
    )


@pytest.mark.parametrize(
    ("cell", "extent"),
    [
        (SC, math.sqrt(3) / 2),  # corner R
        (FCC, math.sqrt(1.25)),  # W = (1, 1/2, 0) / a
        (HEX, math.hypot(2 / 3, 1 / 3.2)),  # H, above K
    ],
)
def test_zone_extent_is_the_farthest_corner(
    cell: list[list[float]], extent: float
) -> None:
    assert _node(f"zoneExtent({json.dumps(cell)})") == pytest.approx(extent)


@pytest.mark.parametrize(
    ("q", "reduced"),
    [
        ([0.7, 0, 0], [-0.3, 0, 0]),
        ([2, 1, -3], [0, 0, 0]),
        # On the boundary q itself is kept ...
        ([0.5, 0, 0], [0.5, 0, 0]),
        ([-0.5, 0, 0], [-0.5, 0, 0]),
        ([-0.5, 0.5, 0.5], [-0.5, 0.5, 0.5]),
        # ... else the equivalent point with the largest coordinates.
        ([1.5, 0, 0], [0.5, 0, 0]),
        ([1.5, -0.5, 1.5], [0.5, 0.5, 0.5]),
    ],
)
def test_simple_cubic_reduction(q: list[float], reduced: list[float]) -> None:
    assert _zone(SC, q) == pytest.approx(reduced)


def test_reduction_takes_the_shortest_equivalent_vector() -> None:
    # fcc: (0.6, 0.6, 0) lies beyond X; its equivalent inside is shorter.
    # Reduced coordinates in [-1/2, 1/2) would not do: W = (3/4, 1/2, 1/4)
    # is in the zone and stays.
    assert _zone(FCC, [0.6, 0.6, 0]) == pytest.approx([-0.4, -0.4, 0])
    assert _zone(FCC, [0.75, 0.5, 0.25]) == pytest.approx([0.75, 0.5, 0.25])
    # Hexagonal (reciprocal axes at 60 degrees): K = (1/3, 1/3, 0) stays,
    # (2/3, 1/3, 0) is the point (-1/3, 1/3, 0) inside the zone.
    assert _zone(HEX, [1 / 3, 1 / 3, 0]) == pytest.approx([1 / 3, 1 / 3, 0])
    assert _zone(HEX, [2 / 3, 1 / 3, 0]) == pytest.approx([-1 / 3, 1 / 3, 0])


def test_wave_vector_needs_the_cartesian_axes() -> None:
    result = _node(
        """(() => {
          const stored = (axes) => normalizePrefs({ tripod: { axes, export: true }, vibration: { waveVector: true } }).vibration.waveVector;
          const chosen = (axes) => {
            viewerPrefs.tripod.axes = "xyz"; viewerPrefs.vibration.waveVector = true;
            setTripodAxes(axes);
            return viewerPrefs.vibration.waveVector;
          };
          return { stored: ["xyz", "abc", "both", "off"].map(stored), chosen: ["xyz", "abc", "both", "off"].map(chosen) };
        })()"""
    )
    assert result == {
        "stored": [True, False, False, False],
        "chosen": [True, False, False, False],
    }


def test_wave_style_settings_are_checked() -> None:
    vibration = _node(
        "normalizePrefs({ vibration: { qColour: 'red', vgColour: '#123456',"
        " qDash: 'wavy', vgDash: 'dotted', waveLabels: 1, waveLegend: false } }).vibration"
    )
    assert vibration["qColour"] == "#e67700"
    assert vibration["vgColour"] == "#123456"
    assert vibration["qDash"] == "solid"
    assert vibration["vgDash"] == "dotted"
    assert vibration["waveLabels"] is True
    assert vibration["waveLegend"] is False


def test_tripod_draws_q_to_scale_and_v_g_as_a_direction() -> None:
    layout = _node(
        """(() => {
          sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
          const scene = { tripod: "xyz", structure: { cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] },
            wave: { q: [0.35, 0.35, 0], vg: [0, 1, 0], qColour: "#e67700", vgColour: "#9c36b5", qDash: "solid", vgDash: "dashed", labels: true } };
          const arrows = tripodLayout(scene, 200);
          const prims = tripodPrims(arrows, { halo: "#ffffff" }, null);
          return { arrows: arrows.map((a) => ({ name: a.name, wave: Boolean(a.wave), dx: a.tip[0] - a.origin[0], dy: a.tip[1] - a.origin[1] })),
            dashes: prims.filter((p) => p.kind === "arrow").map((p) => p.dash),
            labels: prims.filter((p) => p.kind === "label").map((p) => p.text + (p.sub ? "_" + p.sub : "")),
            hit: tripodHit(arrows, arrows.find((a) => a.name === "q").tip[0], arrows.find((a) => a.name === "q").tip[1]) };
        })()"""
    )
    by_name = {arrow["name"]: arrow for arrow in layout["arrows"]}
    assert by_name["q"]["wave"] and by_name["v_g"]["wave"]
    # To scale: 0.35 of an axis length along x and y; v_g one axis length, up.
    assert by_name["q"]["dx"] == pytest.approx(0.35 * by_name["x"]["dx"])
    assert by_name["q"]["dy"] == pytest.approx(0.35 * by_name["y"]["dy"])
    assert by_name["v_g"]["dy"] == pytest.approx(by_name["y"]["dy"])
    assert [5, 3] in layout["dashes"]
    assert {"q", "v_g", "x", "y", "z"} <= set(layout["labels"])
    # A click on q looks along no axis.
    assert layout["hit"] is None


def test_tripod_size_scales_axes_q_and_v_g_together() -> None:
    layout = _node(
        """(() => {
          sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
          const scene = (size) => ({ tripod: "xyz", tripodSize: size, structure: { cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] },
            wave: { q: [0.35, 0, 0], vg: [0, 1, 0], qColour: "#e67700", vgColour: "#9c36b5", qDash: "solid", vgDash: "dashed", labels: true } });
          const lengths = (size) => Object.fromEntries(tripodLayout(scene(size), 400)
            .map((a) => [a.name, Math.hypot(a.tip[0] - a.origin[0], a.tip[1] - a.origin[1])]));
          const origin = (size) => tripodLayout(scene(size), 400)[0].origin;
          return { one: lengths(1), two: lengths(2), origins: [origin(1), origin(2)] };
        })()"""
    )
    for name in ("x", "y", "q", "v_g"):
        assert layout["two"][name] == pytest.approx(2 * layout["one"][name])
    # The ratio of q to the axes stays: q is still to scale.
    assert layout["two"]["q"] == pytest.approx(0.35 * layout["two"]["x"])
    # Size 1 is where the tripod always sat; a larger one moves inwards.
    assert layout["origins"][0] == [48, 352]
    assert layout["origins"][1][0] > 48 + 34


def test_q_and_v_g_are_outlined_with_a_larger_head_bold_italic_and_v_g_subscripted() -> (
    None
):
    result = _node(
        """(() => {
          sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
          const scene = { tripod: "xyz", structure: { cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] },
            wave: { q: [0.5, 0, 0], vg: [0, 1, 0], qColour: "#e67700", vgColour: "#9c36b5", qDash: "solid", vgDash: "dashed", labels: true } };
          const prims = tripodPrims(tripodLayout(scene, 200), { halo: "#ffffff" }, null);
          const arrows = prims.filter((p) => p.kind === "arrow");
          const axis = arrows.find((p) => !p.outline), wave = arrows.filter((p) => p.outline);
          const label = prims.find((p) => p.kind === "label" && p.sub);
          const labels = prims.filter((p) => p.kind === "label");
          // The SVG of just these primitives.
          displayList = () => prims;
          const svg = panelsToSvg([{ stage: { clientWidth: 200, clientHeight: 200 }, scene }], { transparent: true });
          return { axisWidth: axis.width, waveWidths: wave.map((p) => p.width), heads: wave.map((p) => p.head),
            label: [label.text, label.sub], svgSub: /v<tspan[^>]*>g<\\/tspan>/.test(svg),
            weights: Object.fromEntries(labels.map((p) => [p.text, p.weight ?? null])),
            embolden: Object.fromEntries(labels.map((p) => [p.text, p.embolden ?? null])),
            italic: Object.fromEntries(labels.map((p) => [p.text, Boolean(p.italic)])),
            svgItalic: (svg.match(/<text[^>]*font-style="italic"/g) ?? []).length,
            svgUprightSub: /<tspan[^>]*font-style="normal"[^>]*>g</.test(svg),
            svgBold: (svg.match(/<text[^>]*font-weight="800"/g) ?? []).length, svgSubWeight: /<tspan[^>]*font-weight="600"[^>]*>g</.test(svg),
            svgEmbolden: (svg.match(/<text[^>]*stroke="#(e67700|9c36b5)" stroke-width="1"/g) ?? []).length,
            svgPlainSub: /<tspan[^>]*stroke-width="0"[^>]*>g</.test(svg),
            svgOutline: (svg.match(/fill="none" stroke="#/g) ?? []).length };
        })()"""
    )
    assert len(result["waveWidths"]) == 2
    assert all(w > result["axisWidth"] for w in result["waveWidths"])
    assert all(h > 1 for h in result["heads"])
    assert result["label"] == ["v", "g"]
    assert result["svgSub"]
    assert result["svgOutline"] == 2
    # Vectors get bold labels; the subscript and the axes keep the normal weight.
    assert result["weights"] == {
        "x": None,
        "y": None,
        "z": None,
        "q": 800,
        "v": 800,
    }
    # A font without a weight above bold would show no change, so the vector
    # labels are also stroked in their colour (an extra SVG text each), the
    # subscript not.
    assert result["embolden"] == {
        "x": None,
        "y": None,
        "z": None,
        "q": 1,
        "v": 1,
    }
    assert result["svgBold"] == 4
    assert result["svgEmbolden"] == 2
    assert result["svgSubWeight"]
    assert result["svgPlainSub"]
    # Italic too (the subscript upright: g names the group velocity).
    assert result["italic"] == {
        "x": False,
        "y": False,
        "z": False,
        "q": True,
        "v": True,
    }
    assert result["svgItalic"] == 4
    assert result["svgUprightSub"]


def test_axes_and_wave_vector_sizes_scale_their_own_arrows() -> None:
    layout = _node(
        """(() => {
          sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
          const scene = (sizes) => ({ tripod: "xyz", structure: { cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]] }, ...sizes,
            wave: { q: [0.5, 0, 0], vg: [0, 1, 0], qColour: "#e67700", vgColour: "#9c36b5", qDash: "solid", vgDash: "dashed", labels: true } });
          const measure = (sizes) => {
            const arrows = tripodLayout(scene(sizes), 400);
            const out = Object.fromEntries(arrows.map((a) => [a.name, Math.hypot(a.tip[0] - a.origin[0], a.tip[1] - a.origin[1])]));
            out.origin = arrows[0].origin;
            out.labelSize = Object.fromEntries(tripodPrims(arrows, { halo: "#ffffff" }, null)
              .filter((p) => p.kind === "label").map((p) => [p.text, p.size]));
            return out;
          };
          return { plain: measure({}), axes: measure({ tripodAxesSize: 2 }), wave: measure({ tripodWaveSize: 2 }),
            both: measure({ tripodSize: 2, tripodAxesSize: 0.5, tripodWaveSize: 1.5 }) };
        })()"""
    )
    plain, axes, wave, both = (
        layout[k] for k in ("plain", "axes", "wave", "both")
    )
    # Axes alone: the axes double, q and v_g stay; the origin makes room.
    assert axes["x"] == pytest.approx(2 * plain["x"])
    assert axes["q"] == pytest.approx(plain["q"])
    assert axes["v_g"] == pytest.approx(plain["v_g"])
    assert axes["origin"][0] > plain["origin"][0]
    assert axes["labelSize"]["x"] > plain["labelSize"]["x"]
    assert axes["labelSize"]["q"] == plain["labelSize"]["q"]
    # q and v_g alone: the reverse, also with room for the longer arrows.
    assert wave["x"] == pytest.approx(plain["x"])
    assert wave["q"] == pytest.approx(2 * plain["q"])
    assert wave["v_g"] == pytest.approx(2 * plain["v_g"])
    assert wave["origin"][0] > plain["origin"][0]
    assert wave["labelSize"]["v"] > plain["labelSize"]["v"]
    # The overall size multiplies both.
    assert both["x"] == pytest.approx(plain["x"])
    assert both["q"] == pytest.approx(3 * plain["q"])


def test_tripod_part_sizes_are_checked() -> None:
    sizes = _node(
        "[1.5, 0.1, 9, 'big', null].map((s) => { const t = normalizePrefs({ tripod: { axes: 'xyz', export: true, size: 1, axesSize: s, waveSize: s } }).tripod; return [t.axesSize, t.waveSize]; })"
    )
    assert sizes == [[1.5, 1.5], [1, 1], [1, 1], [1, 1], [1, 1]]


def test_tripod_size_setting_is_checked() -> None:
    sizes = _node(
        "[2, 0.1, 9, 'big', null].map((size) => normalizePrefs({ tripod: { axes: 'abc', export: true, size } }).tripod.size)"
    )
    assert sizes == [2, 1, 1, 1, 1]
