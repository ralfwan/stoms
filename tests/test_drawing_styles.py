"""Drawing styles and radius types (viewer.js, run in Node; and their Python
settings): ball and stick, space-filling, stick and wireframe; covalent, van
der Waals and ionic radii; per-element radii winning over both."""

import json
import re
from typing import Any

import pytest
from ase.data import atomic_numbers
from ase.data.vdw_alvarez import vdw_radii
from test_bond_search import _payload
from test_polyhedra import rutile
from test_web_viewer import _evaluate

from stoms.viewer import view

STYLES = ["ball-and-stick", "space-filling", "stick", "wireframe"]
THEME = (
    "{ text: '#000000', halo: '#ffffff', cell: '#888888', accent: '#ff0000' }"
)


def _rutile() -> dict[str, Any]:
    return _payload(rutile(), "rutile-styles")


# The display list of `structure` drawn with these settings (JS
# assignments), top view at 20 px/Å: primitive counts, sphere radii, line
# widths, and the SVG of the same scene.
def _drawn(settings: str) -> str:
    return (
        "viewerPrefs.cutoffs = bondCutoffs(structure),"
        " sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], sharedView.scale = 20,"
        f" {settings},"
        " (() => { const scene = buildScene(structure, { colour: (i, s) => elementColor(s) }, null);"
        f"   const list = displayList(scene, 400, 400, {THEME}, {{ tripod: false }});"
        "   const count = { sphere: 0, dot: 0, line: 0, polygon: 0 };"
        "   for (const p of list) count[p.kind] = (count[p.kind] ?? 0) + 1;"
        "   const svg = panelsToSvg([{ stage: { clientWidth: 400, clientHeight: 400 }, scene }],"
        "     { transparent: true, tripod: false });"
        "   return { count, halfBonds: scene.halfBonds.length, cell: scene.cellEdges.length,"
        "     sphereRadii: list.filter((p) => p.kind === 'sphere').map((p) => p.r),"
        "     dots: list.filter((p) => p.kind === 'dot').map((p) => [p.x, p.y, p.r, p.colour]),"
        "     widths: list.filter((p) => p.kind === 'line' || p.kind === 'lines').map((p) => p.width),"
        "     wires: list.filter((p) => p.kind === 'lines').reduce((n, p) => n + p.segments.length, 0),"
        "     svg }; })()"
    )


# ---------------------------------------------------------------- settings


def test_old_settings_give_todays_look() -> None:
    # Settings of 0.10.0 (no style, no radius type): ball and stick with
    # covalent radii, the radii as before (a third of the covalent radius
    # with bonds, half without, at least 0.18 Å).
    old = {"version": 2, "bonds": True, "appearance": {"atomScale": 1.5}}
    [prefs, with_bonds, without] = _evaluate(
        (f"normalizePrefs({json.dumps(old)})", {}),
        (
            "viewerPrefs.bonds = true, viewerPrefs.appearance.atomScale = 1.5,"
            " ['O', 'Ti', 'H', 'Xx'].map(autoRadius)",
            {},
        ),
        (
            "viewerPrefs.bonds = false, viewerPrefs.appearance.atomScale = 1,"
            " ['O', 'Ti', 'H', 'Xx'].map(autoRadius)",
            {},
        ),
    )
    assert prefs["style"] == "ball-and-stick"
    assert prefs["radiusType"] == "covalent"
    covalent = {"O": 0.66, "Ti": 1.60, "H": 0.31, "Xx": 1.5}
    assert with_bonds == pytest.approx(
        [max(0.18, r * 0.33) * 1.5 for r in covalent.values()]
    )
    assert without == pytest.approx(
        [max(0.18, r * 0.5) for r in covalent.values()]
    )


def test_unknown_style_and_radius_type_fall_back() -> None:
    bad = {"style": "cartoon", "radiusType": 3}
    [prefs] = _evaluate((f"normalizePrefs({json.dumps(bad)})", {}))
    assert (prefs["style"], prefs["radiusType"]) == (
        "ball-and-stick",
        "covalent",
    )
    good = {"style": "wireframe", "radiusType": "ionic"}
    [prefs] = _evaluate((f"normalizePrefs({json.dumps(good)})", {}))
    assert (prefs["style"], prefs["radiusType"]) == ("wireframe", "ionic")


# ---------------------------------------------------------------- radii


def test_vdw_radii_are_alvarez() -> None:
    [table] = _evaluate(("VDW_RADII", {}))
    assert len(table) == 67
    for symbol, radius in table.items():
        assert radius == pytest.approx(vdw_radii[atomic_numbers[symbol]])


def test_ionic_radii_are_shannon_at_coordination_6() -> None:
    [table, elements] = _evaluate(
        ("IONIC_RADII", {}), ("Object.keys(ELEMENTS)", {})
    )
    # Effective ionic radii, Shannon (1976), CN 6.
    known = {
        "O": (1.40, "O2-"),
        "F": (1.33, "F-"),
        "Cl": (1.81, "Cl-"),
        "Na": (1.02, "Na+"),
        "Mg": (0.72, "Mg2+"),
        "Ti": (0.605, "Ti4+"),
        "Sr": (1.18, "Sr2+"),
        "Zr": (0.72, "Zr4+"),
    }
    for symbol, (radius, ion) in known.items():
        assert table[symbol] == [pytest.approx(radius), ion]
    assert set(table) <= set(elements)
    # No usable ionic radius: H and the noble gases (covalent instead).
    assert not {"H", "He", "Ne", "Ar", "Kr", "Xe"} & set(table)


def test_radius_types_set_the_automatic_radii() -> None:
    expression = (
        "viewerPrefs.style = 'space-filling',"
        " Object.fromEntries(RADIUS_TYPES.map((type) => {"
        "   viewerPrefs.radiusType = type;"
        "   return [type, ['O', 'Ti', 'H', 'Xx'].map(autoRadius)]; }))"
    )
    [radii, ball_and_stick] = _evaluate(
        (expression, {}),
        (
            "viewerPrefs.style = 'ball-and-stick', viewerPrefs.radiusType = 'vdw',"
            " viewerPrefs.bonds = true,"
            " ['O', 'Ti'].map(autoRadius)",
            {},
        ),
    )
    # Space-filling: the radius itself; H has no ionic radius and an
    # unknown element no radius of either kind (the covalent fallback).
    assert radii == {
        "covalent": pytest.approx([0.66, 1.60, 0.31, 1.5]),
        "vdw": pytest.approx([1.50, 2.46, 1.20, 1.5]),
        "ionic": pytest.approx([1.40, 0.605, 0.31, 1.5]),
    }
    assert ball_and_stick == pytest.approx([1.50 * 0.33, 2.46 * 0.33])


def test_stick_and_wireframe_atoms_take_the_bond_radius() -> None:
    [stick, wire] = _evaluate(
        (
            "viewerPrefs.style = 'stick', viewerPrefs.radiusType = 'vdw',"
            " viewerPrefs.appearance.bondRadius = 0.12, ['O', 'Ti'].map(autoRadius)",
            {},
        ),
        ("viewerPrefs.style = 'wireframe', ['O', 'Ti'].map(autoRadius)", {}),
    )
    assert stick == wire == [0.12, 0.12]


@pytest.mark.parametrize("style", ["ball-and-stick", "stick", "wireframe"])
def test_element_radii_win_in_every_style_but_space_filling(
    style: str,
) -> None:
    [drawn] = _evaluate(
        (
            _drawn(
                f"viewerPrefs.style = '{style}', viewerPrefs.radiusType = 'ionic',"
                " viewerPrefs.appearance.radii = { O: 0.9 }"
            ),
            _rutile(),
        )
    )
    # Rutile: 2 Ti and 4 O; the O are spheres of 0.9 Å (18 px) in every
    # style, also in wireframe (where the Ti are bonded: no dot).
    o_spheres = [r for r in drawn["sphereRadii"] if r == pytest.approx(18)]
    assert len(o_spheres) == 4
    if style == "wireframe":
        assert drawn["count"]["sphere"] == 4
        assert drawn["count"]["dot"] == 0


@pytest.mark.parametrize("radius_type", ["covalent", "vdw", "ionic"])
def test_space_filling_uses_the_table_radii(radius_type: str) -> None:
    # An atom size factor other than 1 and a radius set for O change
    # nothing: atomRadius is the radius type's table radius.
    [radii, table] = _evaluate(
        (
            f"viewerPrefs.style = 'space-filling', viewerPrefs.radiusType = '{radius_type}',"
            " viewerPrefs.appearance.atomScale = 1.7,"
            " viewerPrefs.appearance.radii = { O: 0.9 },"
            " ['O', 'Ti', 'H'].map(atomRadius)",
            {},
        ),
        (f"['O', 'Ti', 'H'].map((s) => typedRadius(s, '{radius_type}'))", {}),
    )
    assert radii == table


def test_space_filling_scene_draws_labels_and_rings_at_the_table_radii() -> (
    None
):
    # Every consumer of the scene's atom radius (spheres, labels, pick
    # rings, arrows from the sphere surface) sees the table radius.
    [drawn] = _evaluate(
        (
            "viewerPrefs.style = 'space-filling', viewerPrefs.radiusType = 'vdw',"
            " viewerPrefs.appearance.atomScale = 0.5,"
            " viewerPrefs.appearance.radii = { O: 0.9, Ti: 0.3 },"
            " viewerPrefs.labels = 'element',"
            " paintState.selected = structure.symbols.map((symbol, index) =>"
            "   ({ index, image: [0, 0, 0], symbol, count: structure.symbols.length })),"
            " (() => { const scene = buildScene(structure, { colour: (i, s) => elementColor(s) }, null);"
            "   const bySymbol = (list) => list.map((a) => [structure.symbols[a.index], a.radius]);"
            "   return { atoms: bySymbol(scene.atoms),"
            "     labels: scene.labels.map((l) => [l.text, l.radius]),"
            "     picked: scene.picked.map((p) => p.radius) }; })()",
            _rutile(),
        )
    )
    vdw = {"O": 1.50, "Ti": 2.46}
    assert drawn["atoms"] and all(
        r == pytest.approx(vdw[s]) for s, r in drawn["atoms"]
    )
    assert drawn["labels"] and all(
        r == pytest.approx(vdw[text]) for text, r in drawn["labels"]
    )
    assert sorted(set(round(r, 6) for r in drawn["picked"])) == [1.5, 2.46]


def test_ball_and_stick_brings_the_factor_and_element_radii_back() -> None:
    [filling, back, stored] = _evaluate(
        (
            "viewerPrefs.appearance.atomScale = 1.7,"
            " viewerPrefs.appearance.radii = { O: 0.9 },"
            " viewerPrefs.style = 'space-filling', ['O', 'Ti'].map(atomRadius)",
            {},
        ),
        (
            "viewerPrefs.style = 'ball-and-stick', ['O', 'Ti'].map(atomRadius)",
            {},
        ),
        ("viewerPrefs.appearance", {}),
    )
    assert filling == pytest.approx([0.66, 1.60])
    # Without bonds: half the covalent radius, times the size factor.
    assert back == pytest.approx([0.9, 1.60 * 0.5 * 1.7])
    assert stored["atomScale"] == 1.7
    assert stored["radii"] == {"O": 0.9}


@pytest.mark.parametrize("style", STYLES)
def test_size_controls_lock_where_unused(style: str) -> None:
    [locks] = _evaluate(
        (f"styleLocks({{ ...defaultPrefs(), style: '{style}' }})", {})
    )
    atom_scale = {
        "ball-and-stick": None,
        "space-filling": "Space-filling uses the true radii",
        "stick": "Stick and wireframe atoms take the bond radius",
        "wireframe": "Stick and wireframe atoms take the bond radius",
    }[style]
    assert locks["atomScale"] == atom_scale
    assert locks["elementRadii"] == (
        "Space-filling uses the true radii"
        if style == "space-filling"
        else None
    )


# ---------------------------------------------------------------- styles


def test_ball_and_stick_is_todays_drawing() -> None:
    [drawn] = _evaluate(
        (
            _drawn("viewerPrefs.bonds = true, viewerPrefs.polyhedra = true"),
            _rutile(),
        )
    )
    assert drawn["count"]["sphere"] == 6
    assert drawn["count"]["polygon"] > 0
    assert drawn["halfBonds"] > 0
    # O 0.66 · 0.33 and Ti 1.60 · 0.33 Å, at 20 px/Å.
    assert sorted(set(round(r, 3) for r in drawn["sphereRadii"])) == [
        pytest.approx(0.66 * 0.33 * 20),
        pytest.approx(1.60 * 0.33 * 20),
    ]
    bond_widths = sorted(set(round(w, 6) for w in drawn["widths"]) - {1})
    assert bond_widths == [pytest.approx(2 * 0.08 * 20)]


def test_space_filling_has_no_bonds_or_polyhedra() -> None:
    [drawn] = _evaluate(
        (
            _drawn(
                "viewerPrefs.style = 'space-filling', viewerPrefs.radiusType = 'vdw',"
                " viewerPrefs.bonds = true, viewerPrefs.polyhedra = true"
            ),
            _rutile(),
        )
    )
    assert drawn["halfBonds"] == 0
    assert drawn["count"]["polygon"] == 0
    # Only the cell outline is drawn as lines.
    assert drawn["count"]["line"] == drawn["cell"] == 12
    assert sorted(set(round(r, 3) for r in drawn["sphereRadii"])) == [
        pytest.approx(1.50 * 20),
        pytest.approx(2.46 * 20),
    ]


def test_stick_draws_cylinders_and_joints_of_the_bond_radius() -> None:
    # Bonds are off: stick draws them anyway.
    [drawn] = _evaluate(
        (
            _drawn("viewerPrefs.style = 'stick', viewerPrefs.bonds = false"),
            _rutile(),
        )
    )
    assert drawn["halfBonds"] > 0
    assert drawn["count"]["sphere"] == 6
    assert drawn["sphereRadii"] == [pytest.approx(0.08 * 20)] * 6
    assert drawn["count"]["line"] == 12 + drawn["halfBonds"]
    assert sorted(set(round(w, 6) for w in drawn["widths"])) == [
        1,
        pytest.approx(2 * 0.08 * 20),
    ]


def test_wireframe_draws_thin_lines_and_dots_for_atoms_without_bonds() -> None:
    # Two bonded C and an Ar far away.
    structure = {
        "id": "wire",
        "cell": [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        "pbc": [False, False, False],
        "positions": [[1.0, 1.0, 1.0], [2.4, 1.0, 1.0], [6.0, 6.0, 6.0]],
        "symbols": ["C", "C", "Ar"],
    }
    [drawn] = _evaluate((_drawn("viewerPrefs.style = 'wireframe'"), structure))
    assert drawn["count"]["sphere"] == 0
    assert drawn["halfBonds"] == 2
    # The bonds as batched thin lines (one batch per colour), the cell as lines.
    assert drawn["count"]["line"] == 12
    assert drawn["wires"] == 2
    assert drawn["count"]["lines"] == 1
    assert set(drawn["widths"]) == {1}
    [dot] = drawn["dots"]
    # The Ar: at least 2 px, in the Ar colour.
    assert dot[2] == pytest.approx(max(2, 0.08 * 20))
    assert dot[3] == "#80d1e3"


@pytest.mark.parametrize("style", STYLES)
def test_svg_draws_the_display_list(style: str) -> None:
    [drawn] = _evaluate(
        (
            _drawn(
                f"viewerPrefs.style = '{style}', viewerPrefs.bonds = true,"
                " viewerPrefs.appearance.radii = {}"
            ),
            _rutile(),
        )
    )
    svg = drawn["svg"]
    shaded = re.findall(r'<circle [^>]*fill="url\(#sphere', svg)
    flat = re.findall(r'<circle [^>]*fill="#[0-9a-f]{6}"/>', svg)
    assert len(shaded) == drawn["count"]["sphere"]
    assert len(flat) == drawn["count"]["dot"]
    assert svg.count("<line ") == drawn["count"]["line"] + drawn["wires"]


# ---------------------------------------------------------------- Python


def test_python_style_and_radius_type() -> None:
    viewer = view(rutile(), static=True)
    assert viewer.style == "ball-and-stick"
    assert viewer.radius_type == "covalent"
    viewer.style = "space-filling"
    viewer.radius_type = "vdw"
    assert viewer.settings["style"] == "space-filling"
    assert viewer.settings["radiusType"] == "vdw"
    copy = view(rutile(), static=True, settings=viewer.get_settings())
    assert (copy.style, copy.radius_type) == ("space-filling", "vdw")
    with pytest.raises(ValueError):
        viewer.style = "cartoon"
    with pytest.raises(ValueError):
        viewer.radius_type = "metallic"
    assert viewer.style == "space-filling"


def test_python_settings_without_style_load_unchanged() -> None:
    old = {"stoms_viewer_settings": 1, "settings": {"bonds": True}}
    viewer = view(rutile(), static=True, settings=old)
    assert viewer.style == "ball-and-stick"
    assert viewer.radius_type == "covalent"
    assert "style" not in viewer.settings
