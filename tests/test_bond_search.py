"""Bond search options (viewer.js, run in Node; and their Python settings):
the neighbour search beyond ±1 images, minimum bond lengths, hydrogen bonds
and atoms bonded to shown ones outside the repeat or the slice."""

import itertools
import json
from typing import Any

import numpy as np
import pytest
from ase import Atoms
from ase.neighborlist import neighbor_list
from test_polyhedra import rutile
from test_web_viewer import _evaluate

from stoms.viewer import view

# A 2 Å cubic cell with one atom and a 4.5 Å cutoff: neighbours up to
# 2.25 cells away along each axis.
THIN = {
    "id": "thin",
    "cell": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]],
    "pbc": [True, True, True],
    "positions": [[0.3, 0.2, 0.1]],
    "symbols": ["C"],
}


def _lattice_neighbours(spacing: float, cutoff: float) -> int:
    reach = int(cutoff // spacing) + 1
    return sum(
        0 < spacing * np.linalg.norm(n) < cutoff
        for n in itertools.product(range(-reach, reach + 1), repeat=3)
    )


def test_small_cells_find_every_bond() -> None:
    [count, offsets] = _evaluate(
        ('neighbours(structure, { "C-C": 4.5 }).length', THIN),
        (
            'neighbours(structure, { "C-C": 4.5 }).map((b) => b.off)'
            ".reduce((m, o) => Math.max(m, ...o.map(Math.abs)), 0)",
            THIN,
        ),
    )

    # 56 images: the old search (±1 cell) found 26.
    assert count == _lattice_neighbours(2.0, 4.5) == 56
    assert offsets == 2
    atoms = Atoms(
        "C", positions=THIN["positions"], cell=THIN["cell"], pbc=True
    )
    assert count == len(neighbor_list("i", atoms, 4.5))


def test_slab_cells_search_their_periodic_axes_only() -> None:
    # A 2D cell with c = 0 (no third vector): bonds within the a-b plane.
    slab = {**THIN, "cell": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0] * 3]}
    slab["pbc"] = [True, True, False]
    [offsets] = _evaluate(
        ('neighbours(structure, { "C-C": 4.5 }).map((b) => b.off)', slab)
    )

    in_plane = [n for n in itertools.product(range(-3, 4), range(-3, 4))]
    expected = sum(0 < 2.0 * np.hypot(*n) < 4.5 for n in in_plane)
    assert len(offsets) == expected
    assert all(o[2] == 0 for o in offsets)


def test_neighbour_cache_follows_the_cell() -> None:
    # Same id and cutoffs, another cell with the same image range (4.5 Å is
    # 2.25 and 3 cells): searched again (the key holds the cell).
    smaller = {
        **THIN,
        "cell": [[1.5, 0.0, 0.0], [0.0, 1.5, 0.0], [0.0, 0.0, 1.5]],
    }
    [first, second] = _evaluate(
        (
            'globalThis.other = structure, neighbours(structure, { "C-C": 4.5 }).length',
            THIN,
        ),
        ('neighbours(structure, { "C-C": 4.5 }).length', smaller),
    )
    assert first == 56
    assert second == _lattice_neighbours(1.5, 4.5)


def test_ordinary_cells_search_no_further_than_before() -> None:
    # Rutile with the default cutoffs: the same bonds as a ±1 search.
    atoms = rutile()
    payload = {
        "id": "rutile",
        "symbols": atoms.get_chemical_symbols(),
        "positions": atoms.positions.tolist(),
        "cell": atoms.cell[:].tolist(),
        "pbc": [True] * 3,
    }
    [bonds] = _evaluate(
        (
            "neighbours(structure, bondCutoffs(structure)).map((b) => [b.i, b.j, ...b.off])",
            payload,
        )
    )
    assert len(bonds) == 6 * 2 + 3 * 4  # Ti: 6 O each; O: 3 Ti each
    assert max(abs(x) for b in bonds for x in b[2:]) == 1


def test_minimum_lengths_drop_short_bonds() -> None:
    atoms = rutile()
    payload = {
        "id": "rutile-min",
        "symbols": atoms.get_chemical_symbols(),
        "positions": atoms.positions.tolist(),
        "cell": atoms.cell[:].tolist(),
        "pbc": [True] * 3,
    }
    # Ti-O: four bonds of 1.948 Å and two of 1.980 Å.
    [all_bonds, long_only, ligands] = _evaluate(
        (
            'neighbours(structure, { "O-Ti": 2.2 }).filter((b) => b.i === 0).length',
            payload,
        ),
        (
            'neighbours(structure, { "O-Ti": 2.2 }, { "O-Ti": 1.96 })'
            ".filter((b) => b.i === 0).length",
            payload,
        ),
        (
            'viewerPrefs.cutoffs["O-Ti"] = 2.2, viewerPrefs.bondMinimums["O-Ti"] = 1.96,'
            " polyhedronOf(structure, 0).cn",
            payload,
        ),
    )
    assert (all_bonds, long_only, ligands) == (6, 2, 2)


def test_settings_from_0_10_load_unchanged() -> None:
    old = {
        "version": 2,
        "bonds": True,
        "cutoffs": {"O-Ti": 2.3, "H-O": 1.1},
        "polyCenters": ["Ti"],
    }
    [prefs] = _evaluate((f"normalizePrefs({json.dumps(old)})", {}))
    assert prefs["cutoffs"] == old["cutoffs"]
    assert prefs["bondMinimums"] == {}
    assert prefs["bondedOutside"] == "hide"
    assert prefs["hbonds"] == {
        "show": False,
        "acceptors": ["O", "N", "F"],
        "min": 1.5,
        "max": 2.5,
        "angle": 120,
        "colour": "#2f7fd0",
        "perAcceptor": False,
        "ranges": {},
    }


def test_issue_04_hbond_settings_load_unchanged() -> None:
    issue_04 = {
        "show": True,
        "acceptors": ["O", "Cl"],
        "min": 1.6,
        "max": 2.2,
        "angle": 130,
        "colour": "#123456",
    }
    [prefs] = _evaluate(
        (f"normalizePrefs({json.dumps({'hbonds': issue_04})}).hbonds", {})
    )
    assert prefs == {**issue_04, "perAcceptor": False, "ranges": {}}


def test_bad_per_acceptor_ranges_are_dropped() -> None:
    ranges = {
        "O": [1.4, 2.0],
        "N": [2.6, 1.6],
        "F": [-1, 2],
        "Cl": [1, "far"],
        "S": [1.0],
        "Br": 2.0,
        "I": [0, 0],
    }
    hbonds = {"perAcceptor": "yes", "ranges": ranges, "min": 1.6, "max": 2.4}
    [prefs, not_a_map] = _evaluate(
        (f"normalizePrefs({json.dumps({'hbonds': hbonds})}).hbonds", {}),
        (
            "normalizePrefs({ hbonds: { perAcceptor: true, ranges: [[1, 2]] } }).hbonds",
            {},
        ),
    )
    assert prefs["ranges"] == {"O": [1.4, 2.0], "I": [0, 0]}
    assert prefs["perAcceptor"] is False
    # The single range is kept as it was (an older stoms reads only it).
    assert (prefs["min"], prefs["max"]) == (1.6, 2.4)
    assert not_a_map["ranges"] == {} and not_a_map["perAcceptor"] is True


def test_bad_bond_settings_fall_back() -> None:
    bad = {
        "cutoffs": {"O-Ti": "far", "H-O": -1, "C-C": 1.6},
        "bondMinimums": {"O-Ti": None, "C-C": 1.2},
        "hbonds": {
            "min": 3,
            "max": 1,
            "angle": 200,
            "colour": "red",
            "acceptors": "O",
        },
        "bondedOutside": "everything",
    }
    [prefs] = _evaluate((f"normalizePrefs({json.dumps(bad)})", {}))
    assert prefs["cutoffs"] == {"C-C": 1.6}
    assert prefs["bondMinimums"] == {"C-C": 1.2}
    assert (prefs["hbonds"]["min"], prefs["hbonds"]["max"]) == (1.5, 2.5)
    assert prefs["hbonds"]["angle"] == 120
    assert prefs["hbonds"]["colour"] == "#2f7fd0"
    assert prefs["hbonds"]["acceptors"] == ["O", "N", "F"]
    assert prefs["bondedOutside"] == "hide"


# ---------------------------------------------------------------- hydrogen bonds


def water_on_surface(angle: float = 170.0) -> Atoms:
    """A surface O (index 0, with a Ti below) and a water molecule above it:
    H1 (index 2) 1.8 Å above the surface O, with the D–H···A angle `angle`
    at H1; H2 (index 3) points away, up."""
    h1 = np.array([5.0, 5.0, 11.8])
    theta = np.radians(angle)
    # Unit vector from H1 to the water O, at `angle` from H1 -> surface O.
    to_donor = np.array([np.sin(theta), 0.0, -np.cos(theta)])
    o_water = h1 + 0.97 * to_donor
    h2 = o_water + 0.97 * np.array([-0.2, 0.0, 0.98]) / np.hypot(0.2, 0.98)
    return Atoms(
        "OOHHTi",
        positions=[[5.0, 5.0, 10.0], o_water, h1, h2, [5.0, 5.0, 8.1]],
        cell=[10.0, 10.0, 25.0],
        pbc=[True, True, False],
    )


def _payload(atoms: Atoms, name: str) -> dict[str, Any]:
    return {
        "id": name,
        "symbols": atoms.get_chemical_symbols(),
        "positions": atoms.positions.tolist(),
        "cell": atoms.cell[:].tolist(),
        "pbc": [bool(p) for p in atoms.pbc],
    }


def test_water_on_a_surface_has_one_hydrogen_bond() -> None:
    [found] = _evaluate(
        (
            "hydrogenBonds(structure).map((hb) => [hb.h, hb.a, hb.donor.j])",
            _payload(water_on_surface(), "water"),
        )
    )
    assert found == [[2, 0, 1]]


@pytest.mark.parametrize(
    ("angle", "minimum", "expected"),
    [(170.0, 120, 1), (110.0, 120, 0), (110.0, 100, 1)],
)
def test_hydrogen_bonds_need_the_angle(
    angle: float, minimum: float, expected: int
) -> None:
    [count] = _evaluate(
        (
            f"viewerPrefs.hbonds.angle = {minimum}, hydrogenBonds(structure).length",
            _payload(water_on_surface(angle), f"water-{angle}"),
        )
    )
    assert count == expected


def test_hydrogen_bonds_follow_range_and_acceptors() -> None:
    water = _payload(water_on_surface(), "water-range")
    [too_far, not_acceptor] = _evaluate(
        (
            "viewerPrefs.hbonds.max = 1.7, hydrogenBonds(structure).length",
            water,
        ),
        (
            'viewerPrefs.hbonds.acceptors = ["N"], hydrogenBonds(structure).length',
            water,
        ),
    )
    assert (too_far, not_acceptor) == (0, 0)


def water_and_amine() -> Atoms:
    """water_on_surface with an N 2.2 Å from the second H (index 3), in line
    with its O–H bond: H1···O (index 0) is 1.8 Å, H2···N (index 5) 2.2 Å."""
    water = water_on_surface()
    p = water.positions
    along = (p[3] - p[1]) / np.linalg.norm(p[3] - p[1])
    return Atoms(
        "OOHHTiN",
        positions=[*p, p[3] + 2.2 * along],
        cell=water.cell,
        pbc=water.pbc,
    )


_HBOND_PAIRS = "hydrogenBonds(structure).map((hb) => [hb.h, hb.a])"


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        # Off, and on without ranges: the single range (1.5–2.5) for both.
        ("", [[2, 0], [3, 5]]),
        ("viewerPrefs.hbonds.perAcceptor = true", [[2, 0], [3, 5]]),
        # Ranges are ignored while per-acceptor is off.
        (
            "viewerPrefs.hbonds.ranges = { O: [1.5, 1.7], N: [1.5, 2.0] }",
            [[2, 0], [3, 5]],
        ),
        # Each acceptor its own range; the others the single one.
        (
            "viewerPrefs.hbonds.perAcceptor = true, viewerPrefs.hbonds.ranges = { O: [1.5, 1.7] }",
            [[3, 5]],
        ),
        (
            "viewerPrefs.hbonds.perAcceptor = true, viewerPrefs.hbonds.ranges = { N: [1.5, 2.0] }",
            [[2, 0]],
        ),
        (
            "viewerPrefs.hbonds.perAcceptor = true, viewerPrefs.hbonds.max = 1.9,"
            " viewerPrefs.hbonds.ranges = { N: [2.1, 2.3] }",
            [[2, 0], [3, 5]],
        ),
        (
            "viewerPrefs.hbonds.perAcceptor = true, viewerPrefs.hbonds.max = 0,"
            " viewerPrefs.hbonds.ranges = { N: [2.1, 2.3] }",
            [[3, 5]],
        ),
    ],
)
def test_hydrogen_bonds_per_acceptor_ranges(
    settings: str, expected: list[list[int]]
) -> None:
    expression = f"{settings}, {_HBOND_PAIRS}" if settings else _HBOND_PAIRS
    [found] = _evaluate((expression, _payload(water_and_amine(), "amine")))
    assert sorted(found) == expected


def test_hydrogen_bonds_are_dashed_lines_in_the_scene() -> None:
    expression = (
        "viewerPrefs.bonds = true, viewerPrefs.hbonds.show = true,"
        " viewerPrefs.cutoffs = bondCutoffs(structure),"
        " sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], sharedView.scale = 20,"
        " (() => { const scene = buildScene(structure, { colour: () => '#000000' }, null);"
        " const theme = { text: '#000000', halo: '#ffffff', cell: '#888888', accent: '#ff0000' };"
        " return { lines: scene.hbonds.length, dashed: displayList(scene, 400, 400, theme, { tripod: false })"
        "   .filter((p) => p.kind === 'line' && p.dash && p.colour === '#2f7fd0').length,"
        "   halfBonds: scene.halfBonds.length }; })()"
    )
    [result] = _evaluate(
        (expression, _payload(water_on_surface(), "water-scene"))
    )
    # One H-bond; the covalent O-H bonds stay half-bonds (2 bonds, 4 halves),
    # Ti-O to the surface O as well.
    assert result["lines"] == result["dashed"] == 1
    assert result["halfBonds"] == 6


# ---------------------------------------------------------------- bonded atoms outside


def _chain() -> dict[str, Any]:
    return {
        "id": "chain",
        "cell": [[2.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]],
        "pbc": [True, False, False],
        "positions": [[0.0, 0.0, 0.0]],
        "symbols": ["C"],
    }


@pytest.mark.parametrize(
    ("mode", "extra", "half_bonds"),
    [("hide", 0, 4), ("partners", 2, 8), ("ligands", 0, 4)],
)
def test_partners_outside_the_repeat(
    mode: str, extra: int, half_bonds: int
) -> None:
    expression = (
        'viewerPrefs.bonds = true, viewerPrefs.cutoffs = { "C-C": 2.1 },'
        f' viewerPrefs.repeat = [3, 1, 1], viewerPrefs.bondedOutside = "{mode}",'
        " (({ visibleAtoms, extraAtoms, halfBonds, atoms }) => ({ visibleAtoms, extraAtoms,"
        "   halfBonds: halfBonds.length, images: atoms.filter((a) => a.extra).map((a) => a.image[0]) }))"
        "(buildScene(structure, { colour: () => '#000000' }, null))"
    )
    [scene] = _evaluate((expression, _chain()))
    assert scene["visibleAtoms"] == 3
    assert scene["extraAtoms"] == extra
    # One step only: the partners at -1 and 3, not their own partners.
    assert sorted(scene["images"]) == ([-1, 3] if extra else [])
    assert scene["halfBonds"] == half_bonds


def test_partners_outside_the_slice_but_not_hidden_elements() -> None:
    water = _payload(water_on_surface(), "water-slice")
    common = (
        "viewerPrefs.bonds = true, viewerPrefs.bondedOutside = 'partners',"
        " viewerPrefs.cutoffs = bondCutoffs(structure),"
        " viewerPrefs.slice = [[null, null], [null, null], [null, 0.5]],"
    )
    [sliced, hidden] = _evaluate(
        (
            common
            + " buildScene(structure, { colour: () => '#000000' }, null).atoms"
            ".filter((a) => a.extra).map((a) => a.index)",
            water,
        ),
        (
            common + " viewerPrefs.hiddenElements = ['O'],"
            " buildScene(structure, { colour: () => '#000000' }, null).atoms"
            ".filter((a) => a.extra).map((a) => a.index)",
            water,
        ),
    )
    # Below 12.5 Å: the surface O, the Ti and H1 (11.8 Å) are shown; the
    # water O (12.75 Å) is H1's partner outside the slice, unless O is
    # hidden.
    assert sliced == [1]
    assert hidden == []


def _rutile_slab() -> dict[str, Any]:
    atoms = rutile()
    return _payload(atoms, "rutile-slab")


@pytest.mark.parametrize("mode", ["hide", "ligands", "partners"])
def test_sliced_rutile_draws_the_ligands_of_cut_octahedra(mode: str) -> None:
    # Slice c to [0, 0.25]: Ti0 (z = 0) and the two O at z = 0 are shown;
    # Ti0's octahedron has four more O at z = ±c/2, outside the slice, and
    # one apical O in the next cell.
    expression = (
        "viewerPrefs.polyhedra = true, viewerPrefs.bonds = true,"
        " viewerPrefs.cutoffs = bondCutoffs(structure),"
        f" viewerPrefs.bondedOutside = '{mode}',"
        " viewerPrefs.slice = [[null, null], [null, null], [0, 0.25]],"
        " (({ atoms, polyhedra, extraAtoms }) => ({ extraAtoms,"
        "   extra: atoms.filter((a) => a.extra).map((a) => structure.symbols[a.index]),"
        "   drawn: atoms.map((a) => a.position),"
        "   vertices: polyhedra.flatMap((p) => p.faces.flatMap((f) => f.points)) }))"
        "(buildScene(structure, { colour: () => '#000000' }, null))"
    )
    [scene] = _evaluate((expression, _rutile_slab()))
    drawn = np.array(scene["drawn"])
    vertices = np.array(scene["vertices"])
    missing = [
        v for v in vertices if np.min(np.linalg.norm(drawn - v, axis=1)) > 1e-6
    ]
    if mode == "hide":
        assert scene["extraAtoms"] == 0
        assert missing
    else:
        assert "O" in scene["extra"]
        assert missing == []
    if mode == "ligands":
        # Only the O of Ti0's octahedron not drawn: the four at z = ±c/2
        # and one apical O, in the cell copy at -a-b (outside the repeat).
        assert scene["extra"] == ["O"] * 5
    if mode == "partners":
        # Also the Ti bonded to the shown O (one step).
        assert set(scene["extra"]) == {"O", "Ti"}


# ---------------------------------------------------------------- Python


def test_python_bond_cutoffs_take_min_max() -> None:
    viewer = view(rutile(), static=True)
    viewer.bond_cutoffs = {"O-Ti": (1.96, 2.2), ("H", "O"): 1.1}
    assert viewer.settings["cutoffs"] == {"O-Ti": 2.2, "H-O": 1.1}
    assert viewer.settings["bondMinimums"] == {"O-Ti": 1.96}
    assert viewer.bond_cutoffs == {"O-Ti": (1.96, 2.2), "H-O": 1.1}
    assert viewer.polyhedron(0)["cn"] == 2
    viewer.bond_cutoffs = {"O-Ti": 2.2}
    assert viewer.settings["bondMinimums"] == {}
    assert viewer.polyhedron(0)["cn"] == 6


@pytest.mark.parametrize(
    "bad", [(2.2, 1.9), "far", (1, 2, 3), -1.0, (None, 2)]
)
def test_python_bond_cutoffs_reject_bad_values(bad: Any) -> None:
    viewer = view(rutile(), static=True)
    with pytest.raises(ValueError):
        viewer.bond_cutoffs = {"O-Ti": bad}


def test_python_settings_from_0_10_load_unchanged() -> None:
    old = {
        "stoms_viewer_settings": 1,
        "settings": {"bonds": True, "cutoffs": {"O-Ti": 2.3}},
    }
    viewer = view(rutile(), static=True, settings=old)
    assert viewer.bond_cutoffs == {"O-Ti": 2.3}
    assert viewer.bonded_outside == "hide"
    assert viewer.hydrogen_bonds is False
    assert viewer.polyhedron(0)["cn"] == 6


def test_python_hydrogen_bond_and_outside_settings() -> None:
    viewer = view(water_on_surface(), static=True)
    assert viewer.hydrogen_bond_distance == (1.5, 2.5)
    viewer.hydrogen_bonds = True
    viewer.hydrogen_bond_acceptors = ["O", "Cl"]
    viewer.hydrogen_bond_distance = (1.6, 2.2)
    viewer.hydrogen_bond_angle = 130
    viewer.hydrogen_bond_colour = "#123456"
    viewer.bonded_outside = "partners"
    assert viewer.settings["hbonds"] == {
        "show": True,
        "acceptors": ["O", "Cl"],
        "min": 1.6,
        "max": 2.2,
        "angle": 130.0,
        "colour": "#123456",
    }
    assert viewer.settings["bondedOutside"] == "partners"
    with pytest.raises(ValueError):
        viewer.bonded_outside = "all"
    with pytest.raises(ValueError):
        viewer.hydrogen_bond_distance = (2.5, 1.5)
    with pytest.raises(ValueError):
        viewer.hydrogen_bond_distance = 2.5
    with pytest.raises(ValueError):
        viewer.hydrogen_bond_angle = 200
    with pytest.raises(TypeError):
        viewer.hydrogen_bonds = "yes"
    with pytest.raises(TypeError):
        viewer.hydrogen_bond_acceptors = "O"


def test_python_hydrogen_bond_distance_per_acceptor() -> None:
    viewer = view(water_and_amine(), static=True)
    viewer.hydrogen_bond_distance = {"O": (1.5, 1.7), "N": [1.6, 2.6]}
    hbonds = viewer.settings["hbonds"]
    assert hbonds == {
        "perAcceptor": True,
        "ranges": {"O": [1.5, 1.7], "N": [1.6, 2.6]},
    }
    # Read: every acceptor with the range it uses (F: the single range).
    in_effect = {"O": (1.5, 1.7), "N": (1.6, 2.6), "F": (1.5, 2.5)}
    assert viewer.hydrogen_bond_distance == in_effect
    # The viewer reads the same settings (and drops nothing).
    [prefs] = _evaluate(
        (f"normalizePrefs({json.dumps(viewer.settings)}).hbonds", {})
    )
    assert prefs["perAcceptor"] is True
    assert prefs["ranges"] == hbonds["ranges"]
    # Round trip: what was read sets the same ranges in effect.
    viewer.hydrogen_bond_distance = viewer.hydrogen_bond_distance
    assert viewer.hydrogen_bond_distance == in_effect
    # (min, max): the single range, per-acceptor off; ranges kept.
    viewer.hydrogen_bond_distance = (1.4, 2.4)
    assert viewer.hydrogen_bond_distance == (1.4, 2.4)
    assert viewer.settings["hbonds"]["perAcceptor"] is False
    assert viewer.settings["hbonds"]["ranges"]["O"] == [1.5, 1.7]
    for bad in ({"O": (2.0, 1.0)}, {"O": 2.0}, {"O": (-1, 2)}):
        with pytest.raises(ValueError):
            viewer.hydrogen_bond_distance = bad
    with pytest.raises(TypeError):
        viewer.hydrogen_bond_distance = {8: (1.5, 2.5)}
