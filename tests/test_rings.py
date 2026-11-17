import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, graphene, molecule, mx2

from stoms.analysis import find_rings
from stoms.analysis.rings import default_cutoff

EDGE = 3.6  # metal-metal along a ring edge; O in the middle


def _overlayer() -> Atoms:
    """A 4.8.8 Cu-O overlayer (Cu at the vertices, O on the edges) at
    z = 10.6-10.9 A on a Cu layer at z = 8, with an unbonded Cu inside one
    octagon and an O adatom at z = 12.6."""
    length = EDGE * (1 + np.sqrt(2))
    r = EDGE / np.sqrt(2)
    cell = np.diag([2 * length, 2 * length, 22.0])
    corners = {}
    for i in range(2):
        for j in range(2):
            centre = np.array([(i + 0.5) * length, (j + 0.5) * length])
            for k, d in enumerate([(r, 0), (0, r), (-r, 0), (0, -r)]):
                corners[i, j, k] = centre + d
    edges = []
    for i in range(2):
        for j in range(2):
            edges += [
                ((i, j, k), (i, j, (k + 1) % 4), (0, 0)) for k in range(4)
            ]
            edges.append(((i, j, 0), ((i + 1) % 2, j, 2), ((i + 1) // 2, 0)))
            edges.append(((i, j, 1), (i, (j + 1) % 2, 3), (0, (j + 1) // 2)))
    symbols = ["Cu"] * len(corners) + ["O"] * len(edges)
    positions = [[*p, 10.6] for p in corners.values()]
    for a, b, shift in edges:
        middle = (corners[a] + corners[b] + np.array(shift) * 2 * length) / 2
        positions.append([*middle, 10.9])
    symbols += ["Cu", "O"] + ["Cu"] * 16
    positions += [[length, length, 10.7], [*corners[0, 0, 0], 12.6]]
    positions += [
        [x, y, 8.0]
        for x in np.arange(4) * length / 2 + 1
        for y in np.arange(4) * length / 2 + 1
    ]
    return Atoms(
        symbols, positions=positions, cell=cell, pbc=[True, True, False]
    )


WINDOWS = {"Cu": (10.0, 11.5), "O": (10.0, 11.5)}


def test_planar_rings_of_an_overlayer_count_pairs() -> None:
    result = find_rings(_overlayer(), heights=WINDOWS)
    # Every bond joins Cu and O (no Cu-Cu or O-O bonds at these distances),
    # so sizes count Cu-O pairs: 4-rings and 8-rings, one enclosing a Cu.
    assert result.unit == "Cu-O pairs"
    assert result.signature == "4,4,4,4,8,8,8,8+1Cu"
    assert (
        result.network == 41
    )  # the window drops the adatom and the layer below
    assert result.bonds == 48
    assert result.pruned == 1 and result.enclosed == 1
    assert {round(ring.area, 2) for ring in result.rings} == {12.96, 62.58}
    eight = next(ring for ring in result.rings if ring.inside)
    assert len(eight.atoms) == 16
    assert len(eight.points) == 16


@pytest.mark.parametrize(
    ("count", "signature"),
    [
        ("all", "8,8,8,8,16,16,16,16+1Cu"),
        ("pairs", "4,4,4,4,8,8,8,8+1Cu"),
        ("Cu", "4,4,4,4,8,8,8,8+1Cu"),
        ("O", "4,4,4,4,8,8,8,8+1Cu"),
    ],
)
def test_ring_sizes_count_atoms_pairs_or_one_element(
    count: str, signature: str
) -> None:
    result = find_rings(_overlayer(), heights=WINDOWS, count=count)
    assert result.signature == signature


def test_auto_counts_atoms_once_bonds_stop_alternating() -> None:
    # By default metals do not bond to metals, so the Cu-O network alternates
    # even without height windows (the layer below stays unbonded).
    default = find_rings(_overlayer(), enclosed=False)
    assert default.unit == "Cu-O pairs"
    assert default.counts() == {4: 4, 8: 4}
    assert all(not ring.inside for ring in default.rings)
    # A Cu-Cu cutoff bonds the overlayer to the layer below: not every bond
    # joins Cu and O any more, so sizes count atoms.
    bonded = find_rings(_overlayer(), cutoffs={"Cu-Cu": 3.0}, enclosed=False)
    assert bonded.unit == "atoms"
    assert bonded.counts() == {8: 4, 16: 4}


def test_default_cutoffs_match_the_viewer() -> None:
    assert default_cutoff("Cu", "O") == 2.28
    assert default_cutoff("O", "Cu") == 2.28
    assert default_cutoff("Cu", "Pt") == 0.0  # no metal-metal bonds
    assert default_cutoff("Si", "Si") == 2.55


def test_planar_rings_of_a_2d_cell_without_c_vector() -> None:
    sheet = graphene(size=(3, 3, 1))  # cell c = 0, periodic in a and b only
    assert not sheet.cell[2].any()
    result = find_rings(sheet)
    assert result.counts() == {6: 9}
    fractions = np.array([ring.points.mean(axis=0) for ring in result.rings])
    fractions = fractions[:, :2] @ np.linalg.inv(sheet.cell[:2, :2])
    assert ((fractions > -1e-3) & (fractions < 1)).all()  # centres in the cell


def test_cutoffs_and_elements_choose_the_network() -> None:
    assert find_rings(_overlayer(), cutoffs={"O-Cu": 1.0}).rings == ()
    assert find_rings(_overlayer(), elements=["Cu"]).rings == ()


def test_graphene_and_benzene_have_six_rings() -> None:
    sheet = graphene(size=(3, 3, 1), vacuum=5)
    for method in ("planar", "shortest-path"):
        assert find_rings(sheet, method=method).counts() == {6: 9}
    benzene = molecule("C6H6")
    assert find_rings(benzene).signature == "6"  # H atoms are pruned
    assert find_rings(benzene, method="shortest-path").counts() == {6: 1}


def test_a_stripe_is_an_open_face_not_a_ring() -> None:
    # A zigzag chain along a closes on itself only through the periodic image.
    stripe = Atoms(
        "C2",
        positions=[[0, 0, 5], [1.2, 0.7, 5]],
        cell=[2.4, 10, 10],
        pbc=[True, True, False],
    )
    result = find_rings(stripe, cutoffs={"C-C": 1.5})
    assert result.rings == ()
    assert len(result.open_faces) == 2
    assert result.signature == "ch,ch"


def test_shortest_path_rings_of_a_3d_network() -> None:
    # Diamond: two six-rings per atom (each atom lies on twelve).
    crystal = bulk("Si", "diamond", cubic=True)
    result = find_rings(crystal, method="shortest-path")
    assert result.counts() == {6: 16}
    assert find_rings(crystal.repeat(2), method="shortest-path").counts() == {
        6: 128
    }
    # Rings longer than max_size are not searched.
    assert find_rings(crystal, method="shortest-path", max_size=5).rings == ()


def test_planar_rings_warn_about_atoms_on_top_of_each_other() -> None:
    # MoS2: the two S layers coincide in the a-b plane, so faces are ambiguous.
    sheet = mx2("MoS2", vacuum=5).repeat((2, 2, 1))
    result = find_rings(sheet)
    assert len(result.warnings) == 1
    assert "4 pairs of network atoms" in result.warnings[0]
    assert result.to_dict()["warnings"] == list(result.warnings)
    # Keeping the top S layer gives the hexagons of Mo-S pairs.
    top = sheet.positions[:, 2].max()
    one_layer = find_rings(sheet, heights={"S": (top - 0.1, None)})
    assert one_layer.counts() == {3: 4}
    assert one_layer.warnings == ()
    assert find_rings(graphene(size=(3, 3, 1), vacuum=5)).warnings == ()


def test_pairs_round_odd_rings_up() -> None:
    # A C5 ring counted in pairs: 2.5 pairs is a 3-ring.
    angles = np.arange(5) * 2 * np.pi / 5
    pentagon = Atoms(
        "C5",
        positions=np.c_[
            1.2 * np.cos(angles), 1.2 * np.sin(angles), 0 * angles
        ],
    )
    assert find_rings(pentagon, count="pairs").counts() == {3: 1}
    assert find_rings(pentagon).counts() == {5: 1}


def test_unknown_method_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown ring method"):
        find_rings(_overlayer(), method="faces")  # type: ignore[arg-type]
