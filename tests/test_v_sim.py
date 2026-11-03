"""phonopy v_sim files: parser, writer, and serving their modes."""

import json
import shutil
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

import numpy as np
import pytest

from stoms.atomsledger import AtomsLedger
from stoms.cli import main
from stoms.parsers.v_sim import VSimParseError, read, read_many, write
from stoms.web import create_server, load_v_sim

# Diamond Si from phonopy (a 4x4x4 mesh, written per q-point by the owner).
DATA = Path(__file__).parent / "data" / "v_sim"
GAMMA = DATA / "q_000.ascii"
ZONE_EDGE = DATA / "q_002.ascii"  # q = (0, 0, 0.5)
COMPLEX = DATA / "q_015.ascii"  # q = (0, -0.25, -0.25)
SI_MASS = 28.0855


def test_reads_phonopy_gamma_file() -> None:
    atoms, [modes] = read(GAMMA)

    assert atoms.get_chemical_symbols() == ["Si", "Si"]
    assert atoms.pbc.all()
    np.testing.assert_allclose(
        atoms.cell.array,
        [
            [3.865466057, 0.0, 0.0],
            [1.932733029, 3.347591803, 0.0],
            [1.932733029, 1.115863934, 3.156139819],
        ],
    )
    np.testing.assert_allclose(
        atoms.positions[1], [1.932733029, 1.115863934, 0.789034955]
    )
    np.testing.assert_allclose(modes.qpoint, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(
        modes.frequencies,
        [-0.000001, 0.0, 0.0, 15.142223, 15.142223, 15.142223],
    )
    assert modes.displacements.shape == (6, 2, 3)
    assert not modes.displacements.imag.any()
    # Acoustic: both atoms move alike; optical: against each other.
    np.testing.assert_allclose(
        modes.displacements[0, 0], modes.displacements[0, 1]
    )
    np.testing.assert_allclose(
        modes.displacements[3, 0], -modes.displacements[3, 1]
    )


@pytest.mark.parametrize("path", [GAMMA, ZONE_EDGE, COMPLEX])
def test_displacements_are_eigenvectors_over_root_mass(path: Path) -> None:
    _, [modes] = read(path)

    norms = (np.abs(modes.displacements) ** 2).sum(axis=(1, 2)) * SI_MASS
    np.testing.assert_allclose(norms, 1.0, atol=1e-4)


def test_reads_complex_displacements() -> None:
    _, [modes] = read(COMPLEX)

    np.testing.assert_allclose(modes.qpoint, [0.0, -0.25, -0.25])
    assert modes.displacements[0, 0] == pytest.approx(
        np.array(
            [
                -0.126839 - 0.002191j,
                -0.011633 - 0.020848j,
                0.016451 + 0.029483j,
            ]
        )
    )


def test_write_round_trips(tmp_path: Path) -> None:
    atoms, modes = read(COMPLEX)
    path = tmp_path / "anime.ascii"

    write(path, atoms, modes)
    again, again_modes = read(path)

    np.testing.assert_allclose(again.cell.array, atoms.cell.array)
    np.testing.assert_allclose(again.positions, atoms.positions)
    [first], [second] = modes, again_modes
    np.testing.assert_allclose(second.qpoint, first.qpoint)
    np.testing.assert_allclose(second.frequencies, first.frequencies)
    np.testing.assert_allclose(second.displacements, first.displacements)
    assert (
        path.read_text().splitlines()[:5]
        == COMPLEX.read_text().splitlines()[:5]
    )


def test_read_many_joins_q_points_in_file_order() -> None:
    _, modes = read_many([COMPLEX, GAMMA, ZONE_EDGE])

    assert [m.qpoint.tolist() for m in modes] == [
        [0.0, -0.25, -0.25],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.5],
    ]


def test_read_many_rejects_other_structures(tmp_path: Path) -> None:
    atoms, modes = read(GAMMA)
    atoms.positions[1, 2] += 0.1
    other = tmp_path / "other.ascii"
    write(other, atoms, modes)

    with pytest.raises(VSimParseError, match="different structure"):
        read_many([GAMMA, other])


def _broken(tmp_path: Path, old: str, new: str) -> Path:
    path = tmp_path / "broken.ascii"
    path.write_text(GAMMA.read_text().replace(old, new, 1))
    return path


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "#metaData",
            "#keyword: reduced\n#metaData",
            r"line 6: '#keyword: reduced' is not supported",
        ),
        (
            "#; 0.103555; 0.042235; -0.072769; 0.000000; 0.000000; 0.000000 \\\n",
            "",
            r"line 6: expected q, omega and 6 values for each of 2 atoms \(16 numbers\), got 10",
        ),
        ("0.000000000 Si", "0.000000000", r"line 4: expected 'x y z symbol'"),
        (
            "1.932733029    1.115863934    3.156139819",
            "1.9 x 3.1",
            "line 3: expected dzx dzy dzz",
        ),
    ],
)
def test_errors_name_the_line(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(VSimParseError, match=message):
        read(_broken(tmp_path, old, new))


def test_unclosed_mode_block_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "cut.ascii"
    path.write_text("\n".join(GAMMA.read_text().splitlines()[:7]) + "\n")

    with pytest.raises(VSimParseError, match="not closed"):
        read(path)


def test_served_structure_has_modes(tmp_path: Path) -> None:
    directory = tmp_path / "v_sim"
    directory.mkdir()
    for path in (GAMMA, COMPLEX):
        shutil.copy(path, directory)
    (directory / "notes.txt").write_text("ignored\n")
    ledger = AtomsLedger(tmp_path / "view.ledger")
    aggregation, modes = load_v_sim(ledger, directory)
    [structure_id] = modes
    server = create_server(ledger, str(directory), port=0, modes=modes)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(route: str) -> Any:
            with urlopen(f"{base}/api/{route}") as response:
                return json.load(response)

        assert [
            m["structure_id"]
            for m in get(f"aggregations/{aggregation.id}")["members"]
        ] == [structure_id]
        assert get(f"structures/{structure_id}")["has_modes"] is True
        served = get(f"structures/{structure_id}/modes")
        assert served["unit"] == "THz"
        assert [p["q"] for p in served["qpoints"]] == [
            [0.0, 0.0, 0.0],
            [0.0, -0.25, -0.25],
        ]
        complex_point = served["qpoints"][1]
        assert len(complex_point["frequencies"]) == 6
        assert complex_point["displacements"][0][0] == [
            -0.126839,
            -0.011633,
            0.016451,
            -0.002191,
            -0.020848,
            0.029483,
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_ledger_structures_have_no_modes(tmp_path: Path) -> None:
    from stoms.web.server import LedgerView

    ledger = AtomsLedger(tmp_path / "view.ledger")
    _, modes = load_v_sim(ledger, GAMMA)
    [structure_id] = modes
    view = LedgerView(ledger, "plain ledger")

    assert view.structure(structure_id)["has_modes"] is False
    server = create_server(ledger, "plain ledger", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"http://127.0.0.1:{port}/api/structures/{structure_id}/modes"
            )
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_cli_serve_file_reports_v_sim_errors(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["--file", str(empty), "serve"]) == 1
    assert "contains no .ascii files" in capsys.readouterr().err

    broken = tmp_path / "broken.ascii"
    broken.write_text("not a v_sim file\n")
    assert main(["--file", str(broken), "serve"]) == 1
    assert "line 1: expected a '#' comment line" in capsys.readouterr().err
