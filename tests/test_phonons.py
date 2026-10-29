"""Phonons from phonopy input: modes at any q, bands, DOS, serving them."""

import json
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pytest

pytest.importorskip("phonopy")
pytest.importorskip("seekpath")

from stoms.atomsledger import AtomsLedger  # noqa: E402
from stoms.cli import main  # noqa: E402
from stoms.web import create_server, load_phonons, load_v_sim  # noqa: E402
from stoms.web.phonons import (  # noqa: E402
    PhononInputError,
    load_phonopy,
    parse_band,
    parse_dim,
    parse_dos_mesh,
)
from stoms.web.phonons import _seekpath as seekpath_path  # noqa: E402

# Si from phonopy: forces of a 3x3x3 supercell of the conventional cell.
SI = Path(__file__).parent / "data" / "phonopy" / "si_phonopy_params.yaml"
V_SIM = Path(__file__).parent / "data" / "v_sim" / "q_000.ascii"
# Polar InAs: primitive POSCAR, force constants of its 5x5x5 supercell, BORN.
INAS = Path(__file__).parent / "data" / "phonopy" / "inas"
INAS_TO, INAS_LO = 5.771802, 6.30224


@pytest.fixture(scope="module")
def model() -> Any:
    return load_phonopy(SI)


def test_primitive_cell_and_gamma_modes(model: Any) -> None:
    atoms = model.atoms
    modes = model.modes((0.0, 0.0, 0.0))

    assert atoms.get_chemical_symbols() == ["Si", "Si"]
    assert atoms.pbc.all()
    np.testing.assert_allclose(
        np.abs(modes["frequencies"][:3]), 0.0, atol=1e-4
    )
    np.testing.assert_allclose(modes["frequencies"][3:], 15.077051, atol=1e-5)
    d = np.array(modes["displacements"])
    norms = (d**2).sum(axis=(1, 2)) * 28.0855
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


@pytest.mark.parametrize(
    "q_conv", [[1 / 3, 0, 0], [1 / 3, 1 / 3, 0], [0, 1 / 3, 2 / 3]]
)
def test_served_modes_are_normal_modes_with_full_position_phase(
    model: Any, q_conv: list[float]
) -> None:
    # The viewer moves a copy of atom j at fractional r = n + x_j with
    # exp(2 pi i q.r). Check that pattern against the supercell force
    # constants: sum Phi U = omega^2 m U for every mode.
    phonon = model.phonon
    primitive, supercell = phonon.primitive, phonon.supercell
    q = np.array(phonon.primitive_matrix).T @ np.array(q_conv)
    modes = model.modes(tuple(q))
    r = supercell.positions @ np.linalg.inv(primitive.cell)
    p2s = list(primitive.p2s_map)
    j_of = np.array([p2s.index(p) for p in primitive.s2p_map])
    fc = phonon.force_constants
    full = fc.shape[0] == len(supercell)
    masses = supercell.masses
    frequencies = np.array(modes["frequencies"])
    omega2 = np.sign(frequencies) * (frequencies / 15.633302) ** 2
    for b, rows in enumerate(np.array(modes["displacements"])):
        d = rows[:, :3] + 1j * rows[:, 3:]
        u = d[j_of] * np.exp(2j * np.pi * r @ q)[:, None]
        for k, s in enumerate(p2s):
            force = np.einsum("tab,tb->a", fc[s if full else k], u)
            # Served values are rounded to 6 decimals; another phase
            # convention would be off by order 1.
            np.testing.assert_allclose(
                force, omega2[b] * masses[s] * u[s], rtol=1e-3, atol=1e-4
            )


def test_bands_follow_the_seekpath_path(model: Any) -> None:
    bands = model.bands()
    segments = bands["segments"]

    assert [s["labels"] for s in segments] == [
        ["Γ", "X"],
        ["X", "U"],
        ["K", "Γ"],
        ["Γ", "L"],
        ["L", "W"],
        ["W", "X"],
    ]
    assert [s["connected"] for s in segments] == [
        True,
        False,
        True,
        True,
        True,
        False,
    ]
    first = segments[0]
    assert first["start"] == [0.0, 0.0, 0.0]
    assert first["distances"][0] == 0.0
    assert segments[1]["distances"][0] == first["distances"][-1]
    at_x = sorted(first["frequencies"][-1])
    np.testing.assert_allclose(
        at_x, model.modes(tuple(first["end"]))["frequencies"], atol=1e-4
    )


def test_seekpath_points_follow_the_cell_axes(model: Any) -> None:
    # The same crystal with its axes permuted: X moves with the axes.
    primitive = model.phonon.primitive

    class Permuted:
        cell = np.array(primitive.cell)[[2, 0, 1]]
        scaled_positions = np.array(primitive.scaled_positions)[:, [2, 0, 1]]
        numbers = primitive.numbers

    original, _, _ = seekpath_path(primitive)
    permuted, _, _ = seekpath_path(Permuted)

    for (a0, a1), (b0, b1) in zip(original, permuted, strict=True):
        np.testing.assert_allclose(b0, a0[[2, 0, 1]], atol=1e-9)
        np.testing.assert_allclose(b1, a1[[2, 0, 1]], atol=1e-9)


def test_band_path_can_be_given(model: Any) -> None:
    band = parse_band("0 0 0  0.5 0 0.5, 0.5 0.5 0.5  0 0 0", "G X L G")
    given = load_phonopy(SI, band).bands()

    assert band.parts[0] == ((0.0, 0.0, 0.0), (0.5, 0.0, 0.5))
    assert [s["labels"] for s in given["segments"]] == [
        ["G", "X"],
        ["L", "G"],
    ]
    assert [s["connected"] for s in given["segments"]] == [False, False]


@pytest.mark.parametrize(
    ("text", "labels", "message"),
    [
        ("0 0 0  0.5 x 0.5", None, "non-number"),
        ("0 0 0", None, "at least two q-points"),
        ("0 0 0  0.5 0", None, "at least two q-points"),
        ("0 0 0  0.5 0 0.5", "G", "1 labels for 2 q-points"),
    ],
)
def test_band_path_errors(text: str, labels: str | None, message: str) -> None:
    with pytest.raises(PhononInputError, match=message):
        parse_band(text, labels)


def test_dos_counts_every_mode(model: Any) -> None:
    dos = model.dos()
    frequencies = np.array(dos["frequencies"])
    total = np.array(dos["total"])

    assert list(dos["elements"]) == ["Si"]
    np.testing.assert_allclose(dos["elements"]["Si"], total)
    # Six modes per q-point (two atoms).
    assert np.trapezoid(total, frequencies) == pytest.approx(6, rel=0.02)


def _get(base: str, route: str) -> Any:
    with urlopen(f"{base}/api/{route}") as response:
        return json.load(response)


def test_served_phonons(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "view.ledger")
    _, phonons = load_phonons(ledger, SI)
    _, v_sim = load_v_sim(ledger, V_SIM)
    [structure_id], [v_sim_id] = phonons, v_sim
    server = create_server(
        ledger, str(SI), port=0, modes=v_sim, phonons=phonons
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        structure = _get(base, f"structures/{structure_id}")
        assert (structure["has_modes"], structure["has_phonons"]) == (
            True,
            True,
        )
        other = _get(base, f"structures/{v_sim_id}")
        assert (other["has_modes"], other["has_phonons"]) == (True, False)

        modes = _get(base, f"structures/{structure_id}/modes?q=0.5,0,0.5")
        assert modes["any_q"] is True
        [point] = modes["qpoints"]
        assert point["q"] == [0.5, 0.0, 0.5]
        assert point["frequencies"][0] == pytest.approx(3.96136, abs=1e-4)
        gamma = _get(base, f"structures/{structure_id}/modes")
        assert gamma["qpoints"][0]["q"] == [0.0, 0.0, 0.0]

        with pytest.raises(HTTPError) as error:
            _get(base, f"structures/{structure_id}/modes?q=0.5,x,0")
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            _get(base, f"structures/{v_sim_id}/phonons/bands")
        assert error.value.code == 404

        bands = _get(base, f"structures/{structure_id}/phonons/bands")
        assert bands["segments"][0]["labels"] == ["Γ", "X"]
        dos = _get(base, f"structures/{structure_id}/phonons/dos")
        assert list(dos["elements"]) == ["Si"]
    finally:
        server.shutdown()
        server.server_close()


def test_cli_band_options(tmp_path: Path, capsys) -> None:
    assert main(["--file", str(V_SIM), "serve", "--band", "0 0 0 1 1 1"]) == 1
    assert "work only with phonopy input" in capsys.readouterr().err

    assert main(["--file", str(SI), "serve", "--band", "0 0 0"]) == 1
    assert "at least two q-points" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        main(["--ledger", str(tmp_path / "x.ledger"), "serve", "--band", "0"])
    assert "work only with --file" in capsys.readouterr().err


def test_input_without_forces_is_an_error(tmp_path: Path) -> None:
    text = SI.read_text()
    bare = tmp_path / "phonopy_disp.yaml"
    bare.write_text(text[: text.index("displacements:")])

    with pytest.raises(PhononInputError, match="no force constants or forces"):
        load_phonopy(bare)


def test_phonopy_v_sim_file_matches_served_modes(
    model: Any, tmp_path: Path
) -> None:
    # The same modes through both inputs: phonopy's own v_sim writer, read
    # back, against the modes computed from the force constants.
    from phonopy.phonon.animation import Animation

    from stoms.parsers.v_sim import read

    q = (0.25, 0.0, 0.25)
    path = tmp_path / "anime.ascii"
    Animation(q, model.phonon.dynamical_matrix).write_v_sim(filename=path)
    atoms, [from_file] = read(path)
    served = model.modes(q)

    np.testing.assert_allclose(from_file.qpoint, q)
    np.testing.assert_allclose(
        from_file.frequencies, served["frequencies"], atol=1e-5
    )
    # v_sim rotates the cell (a along x). Eigenvectors are fixed only up to a
    # phase, and within a degenerate group up to a rotation: compare the
    # projector onto each group of equal frequency.
    lattice = model.phonon.primitive.cell
    rows = np.array(served["displacements"])
    cartesian = rows[:, :, :3] + 1j * rows[:, :, 3:]
    rotated = (cartesian @ np.linalg.inv(lattice) @ atoms.cell.array).reshape(
        len(rows), -1
    )
    read_back = from_file.displacements.reshape(len(rows), -1)
    frequencies = np.round(from_file.frequencies, 3)
    for frequency in np.unique(frequencies):
        group = frequencies == frequency
        np.testing.assert_allclose(
            read_back[group].T @ read_back[group].conj(),
            rotated[group].T @ rotated[group].conj(),
            atol=5e-5,
        )


@pytest.mark.parametrize(
    ("text", "matrix"),
    [
        ("5", [[5, 0, 0], [0, 5, 0], [0, 0, 5]]),
        ("4 4 2", [[4, 0, 0], [0, 4, 0], [0, 0, 2]]),
        ("-1 1 1  1 -1 1  1 1 -1", [[-1, 1, 1], [1, -1, 1], [1, 1, -1]]),
    ],
)
def test_dim_takes_one_three_or_nine_integers(
    text: str, matrix: list[list[int]]
) -> None:
    assert parse_dim(text) == matrix


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("5 5", "1, 3 or 9 integers, not 2"),
        ("2.5", "must hold integers"),
        ("1 0 0  0 1 0  0 0 0", "determinant must be positive"),
    ],
)
def test_dim_errors(text: str, message: str) -> None:
    with pytest.raises(PhononInputError, match=message):
        parse_dim(text)


@pytest.fixture(scope="module")
def inas() -> Any:
    return load_phonopy(
        INAS / "POSCAR", dim="5", force_constants=INAS / "FORCE_CONSTANTS"
    )


def test_structure_file_with_dim_and_force_constants(inas: Any) -> None:
    # BORN next to the POSCAR turns NAC on; the POSCAR is primitive, so
    # its axes are kept (phonopy's 'auto' would reorder them).
    assert inas.nac is True
    assert inas.atoms.get_chemical_symbols() == ["In", "As"]
    a = 6.059141 / 2
    np.testing.assert_allclose(
        inas.atoms.cell.array, [[0, a, a], [a, 0, a], [a, a, 0]], atol=1e-6
    )
    gamma = inas.modes((0.0, 0.0, 0.0))
    assert gamma["direction"] is None
    np.testing.assert_allclose(gamma["frequencies"][3:], INAS_TO, atol=1e-5)


@pytest.mark.parametrize("direction", [(1, 0, 0), (0.5, 0.5, 0), (1, 1, 1)])
def test_nac_splits_lo_from_to_at_gamma(
    inas: Any, direction: tuple[float, float, float]
) -> None:
    modes = inas.modes((0.0, 0.0, 0.0), direction)

    assert modes["direction"] == list(map(float, direction))
    np.testing.assert_allclose(
        modes["frequencies"][3:], [INAS_TO, INAS_TO, INAS_LO], atol=1e-5
    )
    # Cubic, diatomic: w_LO^2 - w_TO^2 = Z^2 e^2 / (eps0 eps_inf V mu).
    masses = inas.phonon.primitive.masses
    mu = masses[0] * masses[1] / masses.sum() * 1.66053906660e-27
    volume = abs(np.linalg.det(inas.atoms.cell.array)) * 1e-30
    shift = (2.67810 * 1.602176634e-19) ** 2 / (
        8.8541878128e-12 * 19.643 * volume * mu
    )
    to = 2 * np.pi * INAS_TO * 1e12
    lo = np.sqrt(to**2 + shift) / (2 * np.pi * 1e12)
    assert modes["frequencies"][5] == pytest.approx(lo, abs=1e-4)
    # The LO mode is longitudinal: In and As move against each other along q.
    d = np.array(modes["displacements"])[5, :, :3]
    q = np.array(direction) @ np.linalg.inv(inas.atoms.cell.array).T
    assert np.dot(d[0], d[1]) < 0
    cosine = abs(d[0] @ q) / np.linalg.norm(d[0]) / np.linalg.norm(q)
    assert cosine == pytest.approx(1.0, abs=1e-6)


def test_direction_is_used_at_gamma_only(inas: Any) -> None:
    modes = inas.modes((0.5, 0.0, 0.5), (1, 0, 0))

    assert modes["direction"] is None
    assert modes["frequencies"] == inas.modes((0.5, 0.0, 0.5))["frequencies"]


def test_bands_approach_gamma_along_each_segment(inas: Any) -> None:
    bands = inas.bands()

    assert bands["nac"] is True
    first = bands["segments"][0]
    assert first["labels"] == ["Γ", "X"]
    np.testing.assert_allclose(
        sorted(first["frequencies"][0])[3:],
        [INAS_TO, INAS_TO, INAS_LO],
        atol=1e-4,
    )


def test_without_born_there_is_no_nac(tmp_path: Path) -> None:
    for name in ("POSCAR", "FORCE_CONSTANTS"):
        (tmp_path / name).write_bytes((INAS / name).read_bytes())

    model = load_phonopy(
        tmp_path / "POSCAR",
        dim="5 5 5",
        force_constants=tmp_path / "FORCE_CONSTANTS",
    )
    assert model.nac is False
    modes = model.modes((0.0, 0.0, 0.0), (1, 0, 0))
    assert modes["direction"] is None
    np.testing.assert_allclose(modes["frequencies"][3:], INAS_TO, atol=1e-5)

    given = load_phonopy(
        tmp_path / "POSCAR",
        dim="5",
        force_constants=tmp_path / "FORCE_CONSTANTS",
        born=INAS / "BORN",
    )
    assert given.nac is True


def test_force_constants_from_hdf5(tmp_path: Path, inas: Any) -> None:
    pytest.importorskip("h5py")
    from phonopy.file_IO import write_force_constants_to_hdf5

    path = tmp_path / "force_constants.hdf5"
    write_force_constants_to_hdf5(
        inas.phonon.force_constants,
        filename=str(path),
        p2s_map=inas.phonon.primitive.p2s_map,
    )
    model = load_phonopy(
        INAS / "POSCAR",
        dim="5 0 0  0 5 0  0 0 5",
        force_constants=path,
    )
    assert model.modes((0.5, 0.25, 0.75))["frequencies"] == pytest.approx(
        inas.modes((0.5, 0.25, 0.75))["frequencies"]
    )


def test_dim_that_does_not_fit_the_force_constants(
    tmp_path: Path, inas: Any
) -> None:
    pytest.importorskip("h5py")
    from phonopy.file_IO import write_force_constants_to_hdf5

    # Compact force constants: phonopy notices, the error names the size.
    with pytest.raises(PhononInputError, match="supercell has 128 atoms"):
        load_phonopy(
            INAS / "POSCAR", dim="4", force_constants=INAS / "FORCE_CONSTANTS"
        )
    # Full ones (250 x 250) phonopy reads as they are; checked after loading.
    full = tmp_path / "force_constants.hdf5"
    write_force_constants_to_hdf5(
        _full(inas.phonon.force_constants, inas.phonon),
        filename=str(full),
    )
    with pytest.raises(
        PhononInputError, match=r"250 atoms, but the supercell \(DIM\) has 128"
    ):
        load_phonopy(INAS / "POSCAR", dim="4", force_constants=full)


def _full(compact: np.ndarray, phonon: Any) -> np.ndarray:
    from phonopy.harmonic.force_constants import compact_fc_to_full_fc

    return compact_fc_to_full_fc(phonon.primitive, compact)


def test_structure_file_needs_dim() -> None:
    with pytest.raises(
        PhononInputError, match="give the supercell with --dim"
    ):
        load_phonopy(INAS / "POSCAR", force_constants=INAS / "FORCE_CONSTANTS")


def test_yaml_takes_no_dim() -> None:
    with pytest.raises(
        PhononInputError, match="--dim and --calculator are only for structure"
    ):
        load_phonopy(SI, dim="2")


def test_yaml_with_python_tags_is_refused_before_phonopy(
    tmp_path: Path,
) -> None:
    # phonopy's loader would call the function a tag names: here, make a
    # directory. STOMS refuses the file before phonopy reads it.
    called = tmp_path / "called"
    hostile = tmp_path / "phonopy_params.yaml"
    hostile.write_text(
        SI.read_text()
        + f'marker: !!python/object/apply:os.mkdir ["{called}"]\n'
    )
    with pytest.raises(PhononInputError, match="Python tags"):
        load_phonopy(hostile)
    assert not called.exists()


def test_invalid_yaml_is_refused(tmp_path: Path) -> None:
    broken = tmp_path / "phonopy_params.yaml"
    broken.write_text("phonopy: [unclosed\n")
    with pytest.raises(PhononInputError, match="not valid yaml"):
        load_phonopy(broken)


def test_served_direction_at_gamma(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "view.ledger")
    _, phonons = load_phonons(
        ledger,
        INAS / "POSCAR",
        dim="5",
        force_constants=INAS / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    server = create_server(ledger, "InAs", port=0, phonons=phonons)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        route = f"structures/{structure_id}/modes?q=0,0,0"
        [plain] = _get(base, route)["qpoints"]
        [split] = _get(base, f"{route}&direction=0.5,0,0.5")["qpoints"]
        assert plain["nac"] is True and plain["direction"] is None
        assert split["direction"] == [0.5, 0.0, 0.5]
        assert max(plain["frequencies"]) == pytest.approx(INAS_TO, abs=1e-5)
        assert max(split["frequencies"]) == pytest.approx(INAS_LO, abs=1e-5)
        with pytest.raises(HTTPError) as error:
            _get(base, f"{route}&direction=1,0")
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_cli_structure_file_options(tmp_path: Path, capsys) -> None:
    poscar = str(INAS / "POSCAR")
    assert main(["--file", poscar, "serve", "--dim", "5"]) == 1
    assert "give the supercell with --dim" in capsys.readouterr().err

    assert (
        main(["--file", str(V_SIM), "serve", "--born", str(INAS / "BORN")])
        == 1
    )
    assert "work only with phonopy input" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        main(
            [
                "--file",
                poscar,
                "serve",
                "--force-constants",
                "a",
                "--force-sets",
                "b",
            ]
        )
    assert "not allowed with argument" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        main(["--ledger", str(tmp_path / "x.ledger"), "serve", "--dim", "5"])
    assert "work only with --file" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "mesh"), [("50", 50.0), ("12.5", 12.5), ("8 8 8", [8, 8, 8])]
)
def test_dos_mesh_is_a_length_or_three_integers(
    text: str, mesh: float | list[int]
) -> None:
    assert parse_dos_mesh(text) == mesh


@pytest.mark.parametrize("text", ["0", "8 8", "8 8 8.5", "x", "-4 4 4"])
def test_dos_mesh_errors(text: str) -> None:
    with pytest.raises(PhononInputError, match="DOS mesh"):
        parse_dos_mesh(text)


def test_dos_mesh_is_used_with_tetrahedra() -> None:
    model = load_phonopy(
        INAS / "POSCAR",
        dim="5",
        force_constants=INAS / "FORCE_CONSTANTS",
        dos_mesh="8 8 8",
    )
    dos = model.dos()

    assert dos["mesh"] == [8, 8, 8]
    assert dos["method"] == "tetrahedron"
    frequencies = np.array(dos["frequencies"])
    # 6 modes, up to the error of sampling sharp peaks on the frequency grid.
    count = np.trapezoid(dos["total"], frequencies)
    assert count == pytest.approx(6.0, rel=0.05)
    # Tetrahedra give no DOS above the highest phonon frequency (smearing would).
    assert np.array(dos["total"])[frequencies > INAS_LO + 0.2].max() == 0


def test_cli_dos_mesh_errors(capsys) -> None:
    assert main(["--file", str(SI), "serve", "--dos-mesh", "8 8"]) == 1
    assert "DOS mesh" in capsys.readouterr().err

    assert main(["--file", str(V_SIM), "serve", "--dos-mesh", "8"]) == 1
    assert "work only with phonopy input" in capsys.readouterr().err


def test_nac_can_be_switched_off(inas: Any) -> None:
    off = inas.modes((0.0, 0.0, 0.0), (1, 0, 0), nac=False)
    on = inas.modes((0.0, 0.0, 0.0), (1, 0, 0))

    assert (off["nac"], off["has_nac"], off["direction"]) == (
        False,
        True,
        None,
    )
    np.testing.assert_allclose(off["frequencies"][3:], INAS_TO, atol=1e-5)
    assert on["nac"] is True
    assert on["frequencies"][5] == pytest.approx(INAS_LO, abs=1e-5)
    # Away from Γ NAC matters too, and each setting has its own bands.
    assert (
        inas.modes((0.1, 0.0, 0.1), nac=False)["frequencies"][5]
        < inas.modes((0.1, 0.0, 0.1))["frequencies"][5] - 0.2
    )
    bands_off, bands_on = inas.bands(nac=False), inas.bands()
    assert (bands_off["nac"], bands_off["has_nac"]) == (False, True)
    assert max(bands_off["segments"][0]["frequencies"][0]) == pytest.approx(
        INAS_TO, abs=1e-4
    )
    assert max(bands_on["segments"][0]["frequencies"][0]) == pytest.approx(
        INAS_LO, abs=1e-4
    )


def test_structure_from_ase_formats(tmp_path: Path, inas: Any) -> None:
    import ase.io

    atoms = ase.io.read(INAS / "POSCAR")
    q = (0.5, 0.25, 0.75)
    for name in ("InAs.extxyz", "InAs.vasp"):
        ase.io.write(tmp_path / name, atoms)
        model = load_phonopy(
            tmp_path / name,
            dim="5",
            force_constants=INAS / "FORCE_CONSTANTS",
            born=INAS / "BORN",
        )
        assert model.atoms.get_chemical_symbols() == ["In", "As"]
        assert model.modes(q)["frequencies"] == pytest.approx(
            inas.modes(q)["frequencies"], abs=1e-5
        )

    ase.io.write(tmp_path / "two.extxyz", [atoms, atoms])
    with pytest.raises(PhononInputError, match="holds 2 structures"):
        load_phonopy(
            tmp_path / "two.extxyz",
            dim="5",
            force_constants=INAS / "FORCE_CONSTANTS",
        )


def test_structure_of_another_code_in_its_units(
    tmp_path: Path, inas: Any
) -> None:
    import ase.io
    from phonopy.interface.calculator import get_calculator_physical_units

    path = tmp_path / "pw.in"
    ase.io.write(
        path,
        ase.io.read(INAS / "POSCAR"),
        format="espresso-in",
        pseudopotentials={"In": "In.UPF", "As": "As.UPF"},
    )
    model = load_phonopy(
        path,
        dim="5",
        force_constants=INAS / "FORCE_CONSTANTS",
        calculator="qe",
    )

    # phonopy keeps QE cells in bohr; the viewer gets Angstrom.
    np.testing.assert_allclose(
        model.atoms.cell.array, inas.atoms.cell.array, atol=1e-6
    )
    # The same numbers as force constants in Ry/bohr^2, not eV/Angstrom^2.
    ratio = (
        get_calculator_physical_units("qe").factor
        / get_calculator_physical_units("vasp").factor
    )
    q = (0.5, 0.0, 0.5)
    np.testing.assert_allclose(
        model.modes(q)["frequencies"],
        np.array(inas.modes(q, nac=False)["frequencies"]) * ratio,
        rtol=1e-5,
    )


@pytest.mark.parametrize(
    ("path", "options", "message"),
    [
        (INAS / "POSCAR", {"calculator": "nwchem"}, "unknown calculator"),
        (SI, {"calculator": "qe"}, "--calculator are only for structure"),
    ],
)
def test_calculator_errors(
    path: Path, options: dict[str, str], message: str
) -> None:
    inputs: dict[str, Any] = {
        "dim": "5",
        "force_constants": INAS / "FORCE_CONSTANTS",
    }
    if path == SI:
        inputs = {}
    with pytest.raises(PhononInputError, match=message):
        load_phonopy(path, **inputs, **options)


def test_served_nac_switch(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "view.ledger")
    _, phonons = load_phonons(
        ledger,
        INAS / "POSCAR",
        dim="5",
        force_constants=INAS / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    server = create_server(ledger, "InAs", port=0, phonons=phonons)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        route = f"structures/{structure_id}"
        [off] = _get(base, f"{route}/modes?q=0,0,0&direction=1,0,0&nac=0")[
            "qpoints"
        ]
        assert off["nac"] is False
        assert max(off["frequencies"]) == pytest.approx(INAS_TO, abs=1e-5)
        assert _get(base, f"{route}/phonons/bands?nac=0")["nac"] is False
        assert _get(base, f"{route}/phonons/bands")["nac"] is True
        assert _get(base, f"{route}/phonons/dos?nac=0")["mesh"] == [14, 14, 14]
        with pytest.raises(HTTPError) as error:
            _get(base, f"{route}/phonons/bands?nac=no")
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
