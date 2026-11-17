"""Viewer geometry helpers, run in Node against the shipped viewer.js."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
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

# Load viewer.js as a classic script, then evaluate one expression per case.
_RUNNER = """
const vm = require("vm"), fs = require("fs");
const [source, cases] = [process.argv[1], JSON.parse(process.argv[2])];
const context = vm.createContext({ localStorage: { getItem: () => null, setItem() {} } });
vm.runInContext(fs.readFileSync(source, "utf8"), context);
const results = cases.map(([expression, structure]) => {
  context.structure = structure;
  return vm.runInContext(expression, context);
});
process.stdout.write(JSON.stringify(results));
"""

ZERO_CELL = [[0.0, 0.0, 0.0]] * 3


def _evaluate(*cases: tuple[str, dict[str, Any]]) -> list[Any]:
    # Other test modules import this helper without the module skip above.
    if shutil.which("node") is None:
        pytest.skip("needs node")
    result = subprocess.run(
        ["node", "-e", _RUNNER, str(VIEWER), json.dumps(cases)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _ring(normal: np.ndarray) -> list[list[float]]:
    """A flat hexagon of radius 1.4 in the plane perpendicular to `normal`."""
    u = np.cross(normal, [1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    angles = np.arange(6) * np.pi / 3
    return (
        1.4 * (np.outer(np.cos(angles), u) + np.outer(np.sin(angles), v))
    ).tolist()


@pytest.mark.parametrize("preset", ["top", "side-a", "side-b"])
def test_presets_without_cell_give_rotations(preset: str) -> None:
    structure = {
        "cell": ZERO_CELL,
        "positions": _ring(np.array([0.0, 0.6, 0.8])),
    }

    [rotation] = _evaluate(
        (f'presetRotation(structure, "{preset}")', structure)
    )

    np.testing.assert_allclose(
        np.array(rotation) @ np.array(rotation).T, np.eye(3), atol=1e-9
    )
    assert np.linalg.det(rotation) == pytest.approx(1.0)


def test_top_view_without_cell_looks_onto_flat_molecule() -> None:
    normal = np.array([0.0, 0.6, 0.8])
    structure = {"cell": ZERO_CELL, "positions": _ring(normal)}

    [rotation] = _evaluate(('presetRotation(structure, "top")', structure))

    assert abs(np.dot(rotation[2], normal)) == pytest.approx(1.0)


def test_heights_without_cell_follow_principal_axis() -> None:
    normal = np.array([0.0, 0.6, 0.8])
    # A chair: alternate atoms 0.25 above and below the ring plane.
    positions = np.array(_ring(normal)) + np.outer([0.25, -0.25] * 3, normal)
    structure = {"cell": ZERO_CELL, "positions": positions.tolist()}

    [heights] = _evaluate(("heights(structure)", structure))

    assert max(heights) - min(heights) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "positions", [[[0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0], [0.0, 0.0, 1.1]]]
)
def test_presets_without_cell_handle_atoms_and_lines(
    positions: list[list[float]],
) -> None:
    structure = {"cell": ZERO_CELL, "positions": positions}

    [rotation] = _evaluate(('presetRotation(structure, "top")', structure))

    np.testing.assert_allclose(
        np.array(rotation) @ np.array(rotation).T, np.eye(3), atol=1e-9
    )


def test_presets_with_cell_still_follow_cell() -> None:
    # A tilted slab: the top view must look down a x b, not a molecular axis.
    cell = [[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.0, 20.0]]
    structure = {"cell": cell, "positions": _ring(np.array([0.0, 1.0, 0.0]))}

    top, side_a = _evaluate(
        ('presetRotation(structure, "top")', structure),
        ('presetRotation(structure, "side-a")', structure),
    )

    np.testing.assert_allclose(top, np.eye(3), atol=1e-9)
    np.testing.assert_allclose(side_a[1], [0.0, 0.0, 1.0], atol=1e-9)


def test_axis_views_without_cell_skip_cell_axes() -> None:
    structure = {
        "cell": ZERO_CELL,
        "positions": _ring(np.array([0.0, 0.6, 0.8])),
    }
    names, rotation = _evaluate(
        (
            "(sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]],"
            ' tripodLayout({ structure, tripod: "both" }, 300).map((a) => a.name))',
            structure,
        ),
        ('axisRotation(structure, "x")', structure),
    )
    assert sorted(names) == ["x", "y", "z"]
    np.testing.assert_allclose(
        np.array(rotation) @ np.array(rotation).T, np.eye(3), atol=1e-9
    )


def test_settings_keep_only_plain_colours() -> None:
    # Settings may come from a file someone else made; colours end up in SVG.
    hostile = '#123456" onload="x'
    raw = {
        "appearance": {"colours": {"Si": hostile, "O": "#a1b2c3"}},
        "rings": {"colours": {"4": "red", "6": "#00ff00"}},
        "arrows": {"colour": "url(#x)"},
        "customPalette": ["#000000", hostile],
        "planes": [{"h": 0, "k": 0, "l": 1, "t": 0.5, "colour": hostile}],
    }
    [prefs] = _evaluate(
        (f"JSON.parse(JSON.stringify(normalizePrefs({json.dumps(raw)})))", {})
    )
    assert prefs["appearance"]["colours"] == {"O": "#a1b2c3"}
    assert prefs["rings"]["colours"] == {"6": "#00ff00"}
    assert prefs["arrows"]["colour"] is None
    assert prefs["customPalette"] == ["#f2f0e9", "#8c1d40"]
    assert "colour" not in prefs["planes"][0]


def test_rings_are_drawn_in_every_cell_copy() -> None:
    ring_data = {
        "rings": [
            {
                "size": 4,
                "label": "4",
                "atoms": [0, 1, 0, 1],
                "points": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                "centre": [0.5, 0.5, 0.0],
            }
        ]
    }
    [centres] = _evaluate(
        (
            "(viewerPrefs.repeat = [2, 1, 1], viewerPrefs.rings.show = true,"
            ' buildScene(structure, { colour: () => "#000000" }, null,'
            f" {json.dumps(ring_data)}).rings.map((ring) => ring.centre))",
            _cubic([True, True, True]),
        )
    )
    assert centres == [[0.5, 0.5, 0.0], [3.5, 0.5, 0.0]]


def _cubic(pbc: list[bool]) -> dict[str, Any]:
    return {
        "cell": [[3.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 5.0]],
        "pbc": pbc,
        "positions": [[0.0, 0.0, 0.0], [1.5, 2.0, 2.5]],
        "symbols": ["Na", "Cl"],
    }


def _scene_with_repeat(repeat: list[int]) -> str:
    return (
        f"(viewerPrefs.repeat = {json.dumps(repeat)},"
        ' buildScene(structure, { colour: () => "#000000" }, null))'
    )


def test_repeat_along_c_adds_shifted_copies() -> None:
    [scene] = _evaluate(
        (_scene_with_repeat([2, 1, 3]), _cubic([True, True, True]))
    )

    assert scene["totalAtoms"] == 2 * 2 * 3
    positions = {tuple(atom["position"]) for atom in scene["atoms"]}
    assert (3.0, 0.0, 10.0) in positions
    assert (4.5, 2.0, 12.5) in positions


def test_repeat_skips_non_periodic_directions() -> None:
    # A slab: c is not periodic, so a c repeat changes nothing.
    [scene] = _evaluate(
        (_scene_with_repeat([2, 2, 3]), _cubic([True, True, False]))
    )

    assert scene["totalAtoms"] == 2 * 2 * 2
    assert max(atom["position"][2] for atom in scene["atoms"]) == 2.5


def test_repeat_planes_span_the_repeated_box() -> None:
    expression = (
        "viewerPrefs.planes = [{ h: 0, k: 0, l: 1, t: 2.5, show: true }], "
        + _scene_with_repeat([1, 1, 3])
        + ".planes[0].polygon.points"
    )

    [points] = _evaluate((expression, _cubic([True, True, True])))

    assert {round(p[2], 9) for p in points} == {12.5}


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ([2, 3], [2, 3, 1]),
        ([2, 3, 4], [2, 3, 4]),
        ([0, "x", 9], [1, 1, 9]),
        ([13, 12, 1.4], [12, 12, 1]),
    ],
)
def test_stored_repeat_is_padded_and_clamped(
    stored: list[Any], expected: list[int]
) -> None:
    [repeat] = _evaluate(
        (f"normalizePrefs({{ repeat: {json.dumps(stored)} }}).repeat", {})
    )

    assert repeat == expected


def _motion(**overrides: Any) -> str:
    motion = {
        "q": [0.0, 0.0, 0.0],
        "vectors": [[0.0, 0.0, 1.0, 0.0, 0.0, 0.0]],
        "scale": 0.3,
        "amplitude": 0.3,
        "phase": 0.0,
        "moving": True,
        "arrows": False,
        "bonds": "live",
        **overrides,
    }
    return json.dumps(motion)


def _scene_with_motion(repeat: list[int], motion: str) -> str:
    return (
        f"(viewerPrefs.repeat = {json.dumps(repeat)},"
        ' buildScene(structure, { colour: () => "#000000" }, null, null,'
        f" {motion}))"
    )


def _atom() -> dict[str, Any]:
    return {
        "cell": [[3.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 3.0]],
        "pbc": [True, True, True],
        "positions": [[0.0, 0.0, 1.0]],
        "symbols": ["Si"],
    }


def test_gamma_mode_moves_every_copy_alike() -> None:
    [start, quarter] = _evaluate(
        (_scene_with_motion([2, 1, 1], _motion()), _atom()),
        (_scene_with_motion([2, 1, 1], _motion(phase=np.pi / 2)), _atom()),
    )

    assert [a["position"][2] for a in start["atoms"]] == [1.3, 1.3]
    np.testing.assert_allclose(
        [a["position"][2] for a in quarter["atoms"]], [1.0, 1.0], atol=1e-12
    )
    # The view centre ignores the displacement.
    assert start["centre"] == [1.5, 0.0, 1.0]


def test_copies_move_with_the_phase_of_q() -> None:
    # q = 0.5 along a: neighbouring copies move against each other.
    [scene] = _evaluate(
        (_scene_with_motion([2, 1, 1], _motion(q=[0.5, 0.0, 0.0])), _atom())
    )

    np.testing.assert_allclose(
        [a["position"] for a in scene["atoms"]],
        [[0.0, 0.0, 1.3], [3.0, 0.0, 0.7]],
        atol=1e-12,
    )


def test_imaginary_part_lags_a_quarter_period() -> None:
    # d = i z: Re[i e^{-i phase}] = sin(phase).
    vectors = [[0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
    [start, quarter] = _evaluate(
        (_scene_with_motion([1, 1, 1], _motion(vectors=vectors)), _atom()),
        (
            _scene_with_motion(
                [1, 1, 1], _motion(vectors=vectors, phase=np.pi / 2)
            ),
            _atom(),
        ),
    )

    assert start["atoms"][0]["position"][2] == pytest.approx(1.0)
    assert quarter["atoms"][0]["position"][2] == pytest.approx(1.3)


def _dimer() -> dict[str, Any]:
    return {
        "cell": ZERO_CELL,
        "pbc": [False, False, False],
        "positions": [[0.0, 0.0, 0.0], [0.9, 0.0, 0.0]],
        "symbols": ["H", "H"],
    }


@pytest.mark.parametrize(("bonds", "expected"), [("live", 0), ("fixed", 2)])
def test_stretched_bond_breaks_only_when_live(
    bonds: str, expected: int
) -> None:
    stretch = _motion(
        vectors=[[-1.0, 0, 0, 0, 0, 0], [1.0, 0, 0, 0, 0, 0]], bonds=bonds
    )
    expression = (
        'viewerPrefs.bonds = true, viewerPrefs.cutoffs = { "H-H": 1.0 }, '
        + _scene_with_motion([1, 1, 1], stretch)
        + ".halfBonds.length"
    )

    [count] = _evaluate((expression, _dimer()))

    assert count == expected


def test_live_bonds_follow_the_atoms() -> None:
    # Squeezed together, the dimer is bonded; the half-bonds end in the middle.
    squeeze = _motion(vectors=[[1.0, 0, 0, 0, 0, 0], [-1.0, 0, 0, 0, 0, 0]])
    expression = (
        'viewerPrefs.bonds = true, viewerPrefs.cutoffs = { "H-H": 1.0 }, '
        + _scene_with_motion([1, 1, 1], squeeze)
        + ".halfBonds"
    )

    [half_bonds] = _evaluate((expression, _dimer()))

    np.testing.assert_allclose(
        [b["from"][0] for b in half_bonds], [0.3, 0.6], atol=1e-12
    )
    np.testing.assert_allclose(
        [b["to"][0] for b in half_bonds], [0.45, 0.45], atol=1e-12
    )


def test_mode_arrows_show_phase_zero_at_rest() -> None:
    motion = _motion(q=[0.5, 0.0, 0.0], moving=False, arrows=True)
    [scene] = _evaluate((_scene_with_motion([2, 1, 1], motion), _atom()))

    # Atoms stay at equilibrium; arrows point along +z, then -z.
    assert [a["position"] for a in scene["atoms"]] == [
        [0.0, 0.0, 1.0],
        [3.0, 0.0, 1.0],
    ]
    directions = [
        np.sign(arrow["to"][2] - arrow["from"][2]) for arrow in scene["arrows"]
    ]
    assert directions == [1.0, -1.0]


def test_stored_vibration_settings_are_checked() -> None:
    [vibration] = _evaluate(
        (
            "normalizePrefs({ vibration: { amplitude: -1, periodSeconds: 2,"
            ' bonds: "sometimes", unit: "cm-1", recordPeriods: 1.5,'
            ' plotSide: "yes", plotWidth: 700, plotHeight: 50 } }).vibration',
            {},
        )
    )

    assert vibration == {
        "amplitude": 0.3,
        "periodSeconds": 2,
        "showArrows": False,
        "bonds": "fixed",
        "unit": "cm-1",
        "recordPeriods": 2,
        "videoSize": "shown",
        "videoFps": "60",
        "plotSide": False,
        "plotWidth": 700,
        "plotHeight": None,
        "waveVector": False,
        "qColour": "#e67700",
        "vgColour": "#9c36b5",
        "qDash": "solid",
        "vgDash": "dashed",
        "waveLabels": True,
        "waveLegend": True,
    }


def _fog(appearance: str, motion: str = "null") -> str:
    """Sphere fog of a display list, front to back, seen along -z."""
    return (
        "sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], sharedView.scale = 10,"
        f" Object.assign(viewerPrefs.appearance, {appearance}),"
        " displayList(buildScene(structure, { colour: () => '#808080' }, null,"
        f" null, {motion}), 200, 200, {{ cell: '#000000', accent: '#0000ff',"
        " text: '#000000', halo: '#ffffff' })"
        ".filter((p) => p.kind === 'sphere')"
        ".sort((p, q) => (p.fog ?? 0) - (q.fog ?? 0)).map((p) => p.fog ?? 0)"
    )


def _column() -> dict[str, Any]:
    # Three atoms one behind the other along z (towards the viewer).
    return {
        "cell": ZERO_CELL,
        "pbc": [False, False, False],
        "positions": [[0.0, 0.0, 2.0], [1.0, 0.0, 1.0], [2.0, 0.0, 0.0]],
        "symbols": ["Si", "Si", "Si"],
    }


def test_depth_cueing_is_off_by_default() -> None:
    [fog] = _evaluate((_fog("{}"), _column()))

    assert fog == [0, 0, 0]


def test_depth_cueing_fades_towards_the_back() -> None:
    [fog] = _evaluate(
        (_fog("{ depthCue: true, depthStrength: 0.6 }"), _column())
    )

    assert fog == pytest.approx([0.0, 0.3, 0.6])


def test_depth_range_ignores_the_vibration() -> None:
    # The front atom swings forwards; the range stays that of the atoms at rest.
    swing = _motion(
        vectors=[[0, 0, 1.0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]],
        scale=1.0,
        amplitude=1.0,
    )
    [fog] = _evaluate(
        (_fog("{ depthCue: true, depthStrength: 0.6 }", swing), _column())
    )

    assert fog == pytest.approx([0.0, 0.3, 0.6])


def test_depth_cueing_mixes_line_colours_towards_the_background() -> None:
    expression = (
        "viewerPrefs.cell = false, viewerPrefs.bonds = true,"
        " viewerPrefs.cutoffs = { 'Si-Si': 1.5 }, "
        + _fog("{ depthCue: true, depthStrength: 0.5 }").split(".filter")[0]
        + ".filter((p) => p.kind === 'line').map((p) => p.colour)"
    )

    [colours] = _evaluate((expression, _column()))

    # Bonds are the atom colour darkened by 20% (#666666); every half-bond
    # lies behind the front atom, at its own depth, so each is lighter.
    assert len(colours) == 4
    assert len(set(colours)) == 4
    assert all(colour > "#666666" for colour in colours)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        # As shown: the panel's device pixels, rounded to even numbers.
        ("shown", {"pixels": [1548, 1240], "layout": [774, 620], "scale": 2}),
        # Wider than the panel: the full height, more scene at the sides.
        (
            "1080p",
            {
                "pixels": [1920, 1080],
                "layout": [1920 / (1080 / 620), 620],
                "scale": 1080 / 620,
            },
        ),
    ],
)
def test_video_frame_keeps_the_panel_view(
    size: str, expected: dict[str, Any]
) -> None:
    [frame] = _evaluate((f'videoFrame("{size}", 774, 620, 2)', {}))

    assert frame["pixels"] == expected["pixels"]
    assert frame["layout"] == pytest.approx(expected["layout"])
    assert frame["scale"] == pytest.approx(expected["scale"])


def test_stored_video_settings_are_checked() -> None:
    [good, bad] = _evaluate(
        (
            'normalizePrefs({ vibration: { videoSize: "720p", videoFps: "30" } })'
            ".vibration",
            {},
        ),
        (
            'normalizePrefs({ vibration: { videoSize: "toString", videoFps: 24 } })'
            ".vibration",
            {},
        ),
    )

    assert (good["videoSize"], good["videoFps"]) == ("720p", "30")
    assert (bad["videoSize"], bad["videoFps"]) == ("shown", "60")


def _chain() -> dict[str, Any]:
    # One atom per cell, bonded to its neighbours along a only.
    return {
        "cell": [[2.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        "pbc": [True, False, False],
        "positions": [[0.0, 0.0, 0.0]],
        "symbols": ["C"],
    }


@pytest.mark.parametrize("motion", ["null", _motion(bonds="fixed"), _motion()])
@pytest.mark.parametrize(("copies", "half_bonds"), [(1, 0), (3, 4)])
def test_no_bonds_to_atoms_outside_the_repeat(
    motion: str, copies: int, half_bonds: int
) -> None:
    # Three copies: two bonds between them, none dangling at the ends.
    expression = (
        'viewerPrefs.bonds = true, viewerPrefs.cutoffs = { "C-C": 2.1 }, '
        + _scene_with_motion([copies, 1, 1], motion)
        + ".halfBonds.length"
    )

    [count] = _evaluate((expression, _chain()))

    assert count == half_bonds


def test_copies_move_with_the_phase_of_their_full_position() -> None:
    # phonopy's modes: a copy at fractional r = n + x moves with exp(2πi q·r).
    # The atom sits at x = 0.5 along a; with q = 0.25 the copies at n = 0, 1
    # have phases π/4 and 3π/4.
    structure = {**_atom(), "positions": [[1.5, 0.0, 1.0]]}
    [scene] = _evaluate(
        (_scene_with_motion([2, 1, 1], _motion(q=[0.25, 0.0, 0.0])), structure)
    )

    np.testing.assert_allclose(
        [a["position"][2] for a in scene["atoms"]],
        [1.0 + 0.3 * np.cos(np.pi / 4), 1.0 + 0.3 * np.cos(3 * np.pi / 4)],
        atol=1e-12,
    )


def _segments() -> list[dict[str, Any]]:
    # Γ–X then X–W, as the server sends them (two points each).
    return [
        {
            "start": [0.0, 0.0, 0.0],
            "end": [0.5, 0.0, 0.5],
            "distances": [0.0, 1.0],
            "frequencies": [[0.0, 10.0], [4.0, 12.0]],
            "connected": True,
        },
        {
            "start": [0.5, 0.0, 0.5],
            "end": [0.5, 0.25, 0.75],
            "distances": [1.0, 1.5],
            "frequencies": [[4.0, 12.0], [6.0, 11.0]],
            "connected": False,
        },
    ]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ([0.25, 0.0, 0.25], [0.5]),
        # X ends one segment and starts the next: one place.
        ([0.5, 0.0, 0.5], [1.0]),
        # A copy shifted by a reciprocal lattice vector lies on the path.
        ([-0.75, 0.0, 0.25], [0.5]),
        ([0.5, 0.125, 0.625], [1.25]),
        ([0.1, 0.2, 0.3], []),
    ],
)
def test_path_positions_find_q_on_the_path(
    q: list[float], expected: list[float]
) -> None:
    [found] = _evaluate(
        (f"pathPositions({json.dumps(_segments())}, {json.dumps(q)})", {})
    )

    assert [place["d"] for place in found] == pytest.approx(expected)


def test_bands_at_interpolates_along_a_segment() -> None:
    [at] = _evaluate(
        (f"bandsAt({json.dumps(_segments()[0])}, 0.25)", {}),
    )

    assert at == pytest.approx([1.0, 10.5])


# Displacements (displacementOf): a 4 Å cubic cell, periodic along a and b.
CUBE = [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]]


def _frame(
    positions: list[list[float]],
    cell: list[list[float]] = CUBE,
    pbc: list[bool] | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "symbols": symbols or ["Cu", "O"][: len(positions)],
        "positions": positions,
        "cell": cell,
        "pbc": [True, True, False] if pbc is None else pbc,
    }


def _displacement(s: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    [result] = _evaluate((f"displacementOf(structure, {json.dumps(ref)})", s))
    return result


def test_displacement_across_a_cell_face_is_the_short_one() -> None:
    reference = _frame([[3.9, 2.0, 1.0], [2.0, 2.0, 2.0]])
    moved = _frame([[0.1, 2.0, 1.0], [2.0, 2.0, 2.5]])

    result = _displacement(moved, reference)

    np.testing.assert_allclose(
        result["vectors"], [[0.2, 0, 0], [0, 0, 0.5]], atol=1e-12
    )
    assert result["max"] == pytest.approx(0.5)
    assert result["maxIndex"] == 1
    assert result["rmsd"] == pytest.approx(np.sqrt((0.04 + 0.25) / 2))
    assert result["cellsDiffer"] is False


def test_displacement_keeps_the_full_jump_along_non_periodic_axes() -> None:
    reference = _frame([[2.0, 2.0, 3.9]])
    moved = _frame([[2.0, 2.0, 0.1]])

    result = _displacement(moved, reference)

    np.testing.assert_allclose(result["vectors"], [[0, 0, -3.8]], atol=1e-12)


def test_displacement_maps_a_strained_reference_into_the_cell() -> None:
    # A homogeneous strain along a: no atom moves relative to the cell.
    strained = [[4.4, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]]
    reference = _frame([[1.0, 1.0, 1.0], [3.0, 2.0, 2.0]])
    moved = _frame([[1.1, 1.0, 1.0], [3.3, 2.0, 2.2]], cell=strained)

    result = _displacement(moved, reference)

    assert result["cellsDiffer"] is True
    np.testing.assert_allclose(
        result["vectors"], [[0, 0, 0], [0, 0, 0.2]], atol=1e-12
    )


def test_displacement_of_molecules_is_the_plain_difference() -> None:
    reference = _frame([[0.0, 0.0, 0.0]], cell=ZERO_CELL, pbc=[False] * 3)
    moved = _frame([[5.0, 0.0, 0.0]], cell=ZERO_CELL, pbc=[False] * 3)

    result = _displacement(moved, reference)

    np.testing.assert_allclose(result["vectors"], [[5.0, 0, 0]])
    assert result["cellsDiffer"] is False


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        (
            _frame([[0.0, 0.0, 0.0]]),
            "the reference has 1 atoms, this structure 2",
        ),
        (
            _frame([[0.0, 0.0, 0.0], [1.0, 0, 0]], symbols=["O", "Cu"]),
            "another order",
        ),
    ],
)
def test_displacement_needs_the_same_atoms(
    reference: dict[str, Any], message: str
) -> None:
    moved = _frame([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])

    result = _displacement(moved, reference)

    assert message in result["error"]


def test_stored_displacement_settings_are_checked() -> None:
    [default, kept, fixed] = _evaluate(
        (
            "(({ arrows, displacement }) => ({ arrows, displacement }))(normalizePrefs({}))",
            {},
        ),
        (
            "normalizePrefs({ arrows: { source: 'displacement' },"
            " displacement: { reference: 'frame', frame: 3 } })",
            {},
        ),
        (
            "normalizePrefs({ arrows: { source: 'nonsense' },"
            " displacement: { reference: 'last', frame: -1 } })",
            {},
        ),
    )

    assert default["arrows"]["source"] == "vectors"
    assert default["displacement"] == {"reference": "first", "frame": 0}
    assert kept["arrows"]["source"] == "displacement"
    assert kept["displacement"] == {"reference": "frame", "frame": 3}
    assert fixed["arrows"]["source"] == "vectors"
    assert fixed["displacement"] == {"reference": "first", "frame": 0}


def test_symmetry_tolerance_setting_is_checked() -> None:
    results = _evaluate(
        ("normalizePrefs({}).symmetry", {}),
        ("normalizePrefs({ symmetry: { tolerance: 0.1 } }).symmetry", {}),
        ("normalizePrefs({ symmetry: { tolerance: 0 } }).symmetry", {}),
        ('normalizePrefs({ symmetry: { tolerance: "1" } }).symmetry', {}),
        ("normalizePrefs({ symmetry: { tolerance: 5 } }).symmetry", {}),
    )
    assert results == [
        {"tolerance": 0.01},
        {"tolerance": 0.1},
        {"tolerance": 0.01},
        {"tolerance": 0.01},
        {"tolerance": 0.01},
    ]


RUTILE_SYMMETRY = {
    "available": True,
    "applicable": True,
    "tolerance": 0.01,
    "international": "P4_2/mnm",
    "number": 136,
    "crystal_system": "tetragonal",
    "wyckoffs": ["a", "a", "f", "f", "f", "f"],
    "site_symmetries": ["m.mm", "m.mm"] + ["m.2m"] * 4,
    "equivalent_atoms": [0, 0, 2, 2, 2, 2],
}


def test_equivalent_sites_are_named_per_element() -> None:
    structure = {
        "id": "r",
        "symbols": ["Ti", "Ti", "O", "O", "O", "O"],
        "evaluations": [],
        "symmetry": {
            **RUTILE_SYMMETRY,
            # Two O orbits, to see the numbering.
            "wyckoffs": ["a", "a", "f", "f", "g", "g"],
            "equivalent_atoms": [0, 0, 2, 2, 4, 4],
        },
    }
    labels, sites, text = _evaluate(
        ("siteLabels(structure.symmetry, structure)", structure),
        (
            "symmetrySiteList(structure.symmetry, structure).map((s) => [s.label, s.atoms])",
            structure,
        ),
        ("spaceGroupText(structure.symmetry)", structure),
    )
    assert labels == [
        "Ti1 (a)",
        "Ti1 (a)",
        "O1 (f)",
        "O1 (f)",
        "O2 (g)",
        "O2 (g)",
    ]
    assert sites == [
        ["Ti1 (a)", [0, 1]],
        ["O1 (f)", [2, 3]],
        ["O2 (g)", [4, 5]],
    ]
    assert text == "P4_2/mnm (136)"


def test_equivalent_site_colours_are_offered_only_with_symmetry() -> None:
    base = {"id": "r", "symbols": ["Ti"], "evaluations": []}
    names = "propertyOptions(structure).map((o) => o.choice.name)"
    without, served, embedded, missing = _evaluate(
        (names, base),
        (names, {**base, "symmetry_available": True}),
        (names, {**base, "symmetry": RUTILE_SYMMETRY}),
        (names, {**base, "symmetry_available": False}),
    )
    assert "equivalent" not in without and "equivalent" not in missing
    assert "equivalent" in served and "equivalent" in embedded


@pytest.mark.parametrize(
    ("symmetry", "text"),
    [
        (None, "–"),
        ({"available": False}, "–"),
        ({"available": True, "applicable": False}, "not applicable"),
        (
            {"available": True, "applicable": True, "number": None},
            "none found",
        ),
    ],
)
def test_space_group_text_says_why_there_is_none(
    symmetry: Any, text: str
) -> None:
    [result] = _evaluate(("spaceGroupText(structure)", symmetry))
    assert result == text


def _octahedron_and_pair() -> dict[str, Any]:
    """Ti0 in an O octahedron (a drawn polyhedron) and Ti7 with two O
    ligands only (no polyhedron); a molecule, no cell."""
    centre, other = np.array([0.0, 0.0, 0.0]), np.array([10.0, 0.0, 0.0])
    steps = [
        [2.0, 0, 0],
        [-2.0, 0, 0],
        [0, 2.0, 0],
        [0, -2.0, 0],
        [0, 0, 2.0],
        [0, 0, -2.0],
    ]
    positions = [centre, *(centre + steps)]
    positions += [other, other + steps[0], other + steps[1]]
    return {
        "cell": ZERO_CELL,
        "pbc": [False, False, False],
        "positions": [list(map(float, p)) for p in positions],
        "symbols": ["Ti"] + ["O"] * 6 + ["Ti", "O", "O"],
    }


def _polyhedron_scene(centres: bool, style: str = "ball-and-stick") -> str:
    return (
        "(Object.assign(viewerPrefs, { bonds: true, polyhedra: true,"
        f" polyhedraCentres: {json.dumps(centres)}, style: {json.dumps(style)},"
        ' labels: "element-index", cutoffs: { [pairKey("Ti", "O")]: 2.5 } }),'
        " sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], sharedView.scale = 10,"
        " (() => { const scene = buildScene(structure,"
        ' { colour: () => "#808080" }, null);'
        " const list = displayList(scene, 200, 200, { cell: '#000000',"
        " accent: '#0000ff', text: '#000000', halo: '#ffffff' });"
        " return { polyhedra: scene.polyhedra,"
        " hidden: scene.atoms.filter((a) => a.hiddenCentre).map((a) => a.index),"
        " atoms: scene.atoms.length, visible: scene.visibleAtoms,"
        " total: scene.totalAtoms,"
        " bondStarts: scene.halfBonds.map((b) => b.from),"
        " bondEnds: scene.halfBonds.map((b) => b.to),"
        " labels: scene.labels.map((l) => l.text),"
        " spheres: list.filter((p) => p.kind === 'sphere').length }; })())"
    )


def test_polyhedron_centres_are_drawn_by_default() -> None:
    [old, wrong, scene] = _evaluate(
        # An old settings file (without the key), and a wrong kind.
        ("normalizePrefs({ polyhedra: true }).polyhedraCentres", {}),
        ('normalizePrefs({ polyhedraCentres: "no" }).polyhedraCentres', {}),
        (_polyhedron_scene(True), _octahedron_and_pair()),
    )

    assert old is True and wrong is True
    assert scene["hidden"] == []
    assert scene["spheres"] == 10
    assert len(scene["polyhedra"]) == 1
    # Ti0: 6 bonds, Ti7: 2 bonds, each as two half-bonds.
    assert len(scene["bondStarts"]) == 16
    assert "Ti0" in scene["labels"]


def test_polyhedra_without_centres_leave_out_only_the_centre() -> None:
    structure = _octahedron_and_pair()
    [shown, hidden] = _evaluate(
        (_polyhedron_scene(True), structure),
        (_polyhedron_scene(False), structure),
    )

    # The polyhedron is unchanged; only Ti0 (a drawn centre) is hidden.
    assert hidden["polyhedra"] == shown["polyhedra"]
    assert hidden["hidden"] == [0]
    assert hidden["spheres"] == shown["spheres"] - 1
    # No half-bond starts at Ti0 or ends half-way to it; Ti7 keeps its bonds.
    centre = structure["positions"][0]
    assert centre not in hidden["bondStarts"]
    assert len(hidden["bondStarts"]) == len(shown["bondStarts"]) - 12
    assert all(
        np.linalg.norm(np.subtract(end, centre)) > 1.5
        for end in hidden["bondEnds"]
    )
    assert "Ti0" not in hidden["labels"] and "Ti7" in hidden["labels"]
    # Still part of the structure: counted and in the scene's atoms.
    assert (hidden["atoms"], hidden["visible"], hidden["total"]) == (
        shown["atoms"],
        shown["visible"],
        shown["total"],
    )


def test_polyhedron_centres_stay_without_polyhedra() -> None:
    structure = _octahedron_and_pair()
    [space_filling, off] = _evaluate(
        (_polyhedron_scene(False, "space-filling"), structure),
        (
            _polyhedron_scene(False).replace(
                "polyhedra: true", "polyhedra: false"
            ),
            structure,
        ),
    )

    for scene in (space_filling, off):
        assert scene["hidden"] == [] and scene["polyhedra"] == []
        assert scene["spheres"] == 10


def test_polyhedron_centre_locks() -> None:
    [on, off, filling] = _evaluate(
        (
            "styleLocks({ ...defaultPrefs(), polyhedra: true }).polyhedraCentres",
            {},
        ),
        ("styleLocks(defaultPrefs()).polyhedraCentres", {}),
        (
            "styleLocks({ ...defaultPrefs(), polyhedra: true,"
            ' style: "space-filling" }).polyhedraCentres',
            {},
        ),
    )

    assert on is None
    assert off == "Polyhedra are off"
    assert filling == "Space-filling draws no polyhedra"


def _arrow_starts(centres: bool, kind: str) -> str:
    """Arrow starts and atom positions (Ti0, Ti7) of the octahedron scene,
    with force arrows (kind "force") or mode arrows ("mode" at rest,
    "moving" while vibrating) of +z on both Ti."""
    up = [[0, 0, 1, 0, 0, 0] if i in (0, 7) else [0] * 6 for i in range(10)]
    if kind == "force":
        forces = json.dumps(
            {
                "vectors": [v[:3] for v in up],
                "magnitudes": [float(any(v)) for v in up],
                "included": [True] * 10,
            }
        )
        motion = "null"
    else:
        forces = "null"
        motion = _motion(
            vectors=up, arrows=True, moving=kind == "moving", phase=0.0
        )
    return (
        "(Object.assign(viewerPrefs, { polyhedra: true,"
        f" polyhedraCentres: {json.dumps(centres)},"
        ' cutoffs: { [pairKey("Ti", "O")]: 2.5 } }),'
        " viewerPrefs.arrows.show = true, (() => {"
        ' const scene = buildScene(structure, { colour: () => "#808080" },'
        f" {forces}, null, {motion});"
        " const at = (i) => scene.atoms.find((a) => a.index === i).position;"
        " return { starts: scene.arrows.map((a) => a.from),"
        " ti0: at(0), ti7: at(7) }; })())"
    )


@pytest.mark.parametrize("kind", ["force", "mode", "moving"])
def test_arrows_start_at_hidden_polyhedron_centres(kind: str) -> None:
    structure = _octahedron_and_pair()
    structure["cell"] = [[20.0, 0, 0], [0, 20.0, 0], [0, 0, 20.0]]
    structure["positions"] = [
        [x + 5.0 for x in p] for p in structure["positions"]
    ]
    [shown, hidden] = _evaluate(
        (_arrow_starts(True, kind), structure),
        (_arrow_starts(False, kind), structure),
    )

    def starts_at(scene: dict[str, Any], key: str) -> bool:
        return any(np.allclose(start, scene[key]) for start in scene["starts"])

    assert len(shown["starts"]) == len(hidden["starts"]) == 2
    # Drawn atoms: on the sphere surface (above the atom along +z).
    assert not starts_at(shown, "ti0") and not starts_at(shown, "ti7")
    assert any(
        np.allclose(start[:2], shown["ti0"][:2]) and start[2] > shown["ti0"][2]
        for start in shown["starts"]
    )
    # The hidden centre Ti0: at the atom; Ti7 (no polyhedron) unchanged.
    assert starts_at(hidden, "ti0") and not starts_at(hidden, "ti7")


def test_position_measurement_follows_each_frame() -> None:
    # One atom, measured on its copy one cell along a: the value is the
    # Cartesian position of that copy on whatever structure is shown, so it
    # follows a movie frame by frame, as distances do.
    item = (
        "{ kind: 'position', atoms: [{ index: 0, image: [1, 0, 0],"
        " symbol: 'Si', count: 1 }] }"
    )
    moved = {**_atom(), "positions": [[0.5, -0.25, 1.0]]}
    first, second = _evaluate(
        (f"measureValue(structure, {item})", _atom()),
        (f"measureValue(structure, {item})", moved),
    )
    assert first["value"] == [3.0, 0.0, 1.0]
    assert first["text"] == "(3.000, 0.000, 1.000) Å"
    assert second["value"] == [3.5, -0.25, 1.0]
    assert second["text"] == "(3.500, -0.250, 1.000) Å"
    # Kept as a measurement and drawn as a label (no line) over the atom.
    [drawn] = _evaluate(
        (
            f"measureState.items = validMeasurements([{item}]),"
            " sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], sharedView.scale = 10,"
            " displayList(buildScene(structure, { colour: () => '#808080' }, null),"
            " 400, 300, LIGHT_THEME, { tripod: false })"
            ".filter((p) => p.kind === 'label' || (p.kind === 'line' && p.dash))",
            moved,
        )
    )
    assert [p["text"] for p in drawn] == ["(3.500, -0.250, 1.000) Å"]
