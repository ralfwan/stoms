from __future__ import annotations

import hashlib
import importlib
import importlib.util
import subprocess
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from stoms.atomsledger import Provenance
from stoms.atomsledger.serialization import (
    json_dumps,
    method_to_dict,
    provenance_to_dict,
)

VASPRUN = """\
<?xml version="1.0" encoding="UTF-8"?>
<modeling>
  <generator>
    <i name="version" type="string">6.4.1</i>
  </generator>
  <incar>
    <i name="ENCUT" type="int">520</i>
    <i name="METAGGA" type="string">R2SCAN</i>
    <i name="NCORE" type="int">4</i>
  </incar>
  <parameters>
    <separator name="electronic">
      <i name="ENCUT" type="int">520</i>
      <i name="METAGGA" type="string">R2SCAN</i>
      <i name="GGA" type="string">PE</i>
      <i name="AEXX" type="float">0.0</i>
      <i name="HFSCREEN" type="float">0.0</i>
      <i name="LHFCALC" type="logical">F</i>
      <i name="LDAU" type="logical">F</i>
      <i name="NELM" type="int">60</i>
      <i name="IBRION" type="int">2</i>
      <i name="NSW" type="int">1</i>
    </separator>
  </parameters>
  <kpoints>
    <v name="divisions">1 1 1</v>
    <varray name="kpointlist">
      <v>0.0 0.0 0.0</v>
    </varray>
    <varray name="weights">
      <v>1.0</v>
    </varray>
  </kpoints>
  <atominfo>
    <array name="atoms">
      <set><rc><c>O</c></rc></set>
    </array>
    <array name="atomtypes">
      <set><rc><c>1</c><c>1</c><c>O</c><c>8.0</c><c>PAW_PBE O 08Apr2002</c></rc></set>
    </array>
  </atominfo>
  <structure name="initialpos">
    <crystal>
      <varray name="basis">
        <v>4.0 0.0 0.0</v>
        <v>0.0 4.0 0.0</v>
        <v>0.0 0.0 4.0</v>
      </varray>
    </crystal>
    <varray name="positions"><v>0.0 0.0 0.0</v></varray>
  </structure>
  <calculation>
    <energy>
      <i name="e_fr_energy" type="float">-10.0</i>
      <i name="e_wo_entrp" type="float">-10.1</i>
      <i name="e_0_energy" type="float">-10.2</i>
    </energy>
    <scstep>
      <energy>
        <i name="e_fr_energy" type="float">-10.0</i>
        <i name="e_0_energy" type="float">-10.2</i>
      </energy>
    </scstep>
    <varray name="forces"><v>0.1 -0.2 0.3</v></varray>
  </calculation>
</modeling>
"""

INCAR = "ENCUT = 520\nMETAGGA = R2SCAN\nNCORE = 4\n"
KPOINTS = "Generated\n0\nGamma\n1 1 1\n0 0 0\n"
POTCAR = """\
TITEL  = PAW_PBE O 08Apr2002
VRHFIN = O: s2p4
SHA256 = 818f92134a0a090dccd8ba1447fa70422a3b330e708bb4f08108d8ae51209ddf
End of Dataset
"""

LIVE_VASP_CALCULATION = Path(
    "/home/rwanzenboeck/cellar/vsc5_data/sto-2xn/vasp/uma2x3b_74"
)


def _write_calculation(directory: Path) -> None:
    (directory / "vasprun.xml").write_text(VASPRUN, encoding="utf-8")
    (directory / "INCAR").write_text(INCAR, encoding="utf-8")
    (directory / "KPOINTS").write_text(KPOINTS, encoding="utf-8")
    (directory / "POTCAR").write_text(POTCAR, encoding="utf-8")
    (directory / "POSCAR").write_text("synthetic POSCAR", encoding="utf-8")


def _vasp() -> Any:
    if importlib.util.find_spec("pymatgen") is None:
        pytest.skip("pymatgen is required for this test")
    return importlib.import_module("stoms.parsers.vasp")


def test_static_vasp_parse_and_conversions(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    vasp = _vasp()

    parsed = vasp.parse_vasp(tmp_path)

    assert isinstance(parsed, vasp.ParsedVaspEvaluation)
    assert parsed.vasp_version == "6.4.1"
    assert parsed.run_type == "R2SCAN"
    assert parsed.explicit_incar["ENCUT"] == 520
    assert parsed.effective_incar["ENCUT"] == 520
    assert parsed.actual_kpoints == ((0.0, 0.0, 0.0),)
    assert parsed.actual_kpoint_weights == (1.0,)
    assert parsed.properties == {
        "energy": -10.2,
        "forces": ((0.1, -0.2, 0.3),),
    }
    assert parsed.units == {"energy": "eV", "forces": "eV/angstrom"}
    assert parsed.electronic_converged is True
    assert parsed.ionic_converged is True
    assert parsed.converged is True
    assert parsed.ionic_steps == 1
    assert parsed.potcar_datasets[0].symbol == "O"
    assert parsed.potcar_datasets[0].embedded_sha256 == (
        "818f92134a0a090dccd8ba1447fa70422a3b330e708bb4f08108d8ae51209ddf"
    )
    assert vasp.DEFAULT_HASH_FILES == ("INCAR", "KPOINTS", "POTCAR")
    assert set(parsed.file_hashes) == set(vasp.DEFAULT_HASH_FILES)
    assert (
        parsed.file_hashes["INCAR"]
        == hashlib.sha256(INCAR.encode()).hexdigest()
    )
    assert not hasattr(parsed, "structure")

    method = parsed.to_method_spec(protocol="static-v1")
    assert method.family == "dft"
    assert method.name == "r2scan"
    assert method.code == "vasp"
    assert method.parameters["protocol"] == "static-v1"
    assert "NCORE" not in method.parameters["incar"]

    identified = parsed.to_method_spec(
        method_identifier="vasp-r2scan-campaign-1",
        name="human-readable-r2scan",
    )
    assert identified.method_identifier == "vasp-r2scan-campaign-1"
    assert identified.name == "human-readable-r2scan"

    provenance = parsed.to_provenance(
        created_by="test",
        purpose="synthetic VASP evaluation",
        metadata={"ingester": "stoms-0.1.0"},
        execution={"cluster": "local"},
        calculation_id="calc-1",
    )
    assert isinstance(provenance, Provenance)
    assert provenance.metadata["ingester"] == "stoms-0.1.0"
    assert "inputs" not in provenance.metadata
    assert provenance.metadata["execution"] == {"cluster": "local"}
    json_dumps(provenance.metadata)


@pytest.mark.skipif(
    not LIVE_VASP_CALCULATION.is_dir(),
    reason="live VASP calculation is not available",
)
def test_live_uma_calculation_keeps_method_and_provenance_distinct() -> None:
    vasp = _vasp()
    parsed = vasp.parse_vasp(LIVE_VASP_CALCULATION)

    method = parsed.to_method_spec()
    provenance = parsed.to_provenance(
        created_by="test",
        purpose="live UMA VASP calculation",
    )
    method_json = json_dumps(method_to_dict(method))
    provenance_json = json_dumps(provenance_to_dict(provenance))

    assert parsed.vasp_version == "6.2.0"
    assert method.name == "r2scan"
    assert method.parameters["kpoints"]["actual_points"] == (
        (0.25, 0.125, 0.0),
        (0.25, 0.375, 0.0),
    )
    assert tuple(
        dataset["symbol"]
        for dataset in method.parameters["potcar"]["datasets"]
    ) == ("O", "Sr", "Ti")
    assert set(provenance.metadata) == {
        "convergence",
        "energy_components",
        "source_files",
        "file_sha256",
        "parser_warnings",
    }
    assert "inputs" not in provenance.metadata
    assert str(LIVE_VASP_CALCULATION) not in method_json
    assert str(LIVE_VASP_CALCULATION) not in provenance_json


def test_custom_hash_files_silently_omit_missing_files(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    vasp = _vasp()
    (tmp_path / "custom.dat").write_text("custom", encoding="utf-8")

    reparsed = vasp.VaspParser(
        tmp_path,
        hash_files=("vasprun.xml", "custom.dat", "OUTCAR", "missing.dat"),
    ).parse()
    assert set(reparsed.file_hashes) == {"vasprun.xml", "custom.dat"}
    assert "OUTCAR" not in reparsed.file_hashes
    assert "missing.dat" not in reparsed.file_hashes
    assert "custom.dat" not in reparsed.source_files


def test_missing_directory_and_xml_raise(tmp_path: Path) -> None:
    vasp = _vasp()

    with pytest.raises(vasp.VaspParseError, match="not a directory"):
        vasp.VaspParser(tmp_path / "missing").parse()
    with pytest.raises(vasp.VaspParseError, match="Missing vasprun.xml"):
        vasp.VaspParser(tmp_path).parse()


def test_malformed_xml_is_fatal_and_recovery_is_reported(
    tmp_path: Path,
) -> None:
    vasp = _vasp()
    (tmp_path / "vasprun.xml").write_text("<modeling>", encoding="utf-8")

    with pytest.raises(
        vasp.VaspParseError, match="Could not parse vasprun.xml"
    ):
        vasp.VaspParser(tmp_path).parse()

    _write_calculation(tmp_path)
    parsed = vasp.VaspParser(tmp_path, allow_incomplete_xml=True).parse()
    assert not any("recovery" in warning for warning in parsed.warnings)

    (tmp_path / "vasprun.xml").write_text(
        VASPRUN.rsplit("</modeling>", 1)[0], encoding="utf-8"
    )
    recovered = vasp.VaspParser(tmp_path, allow_incomplete_xml=True).parse()
    assert any(
        "recovery was used" in warning for warning in recovered.warnings
    )


def test_result_mappings_are_deeply_immutable(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    vasp = _vasp()
    parsed = vasp.parse_vasp(tmp_path)

    assert isinstance(parsed.properties, MappingProxyType)
    with pytest.raises(TypeError):
        parsed.properties["energy"] = 0.0  # type: ignore[index]
    with pytest.raises(TypeError):
        parsed.original_kpoints["divisions"] = (2, 2, 2)

    supplied = {"nested": {"values": [1]}}
    result = vasp.ParsedVaspEvaluation(
        directory="/tmp/calculation",
        vasp_version=None,
        pymatgen_version="test",
        run_type=None,
        explicit_incar={},
        effective_incar={},
        original_kpoints=None,
        actual_kpoints=(),
        actual_kpoint_weights=(),
        potcar_datasets=(),
        properties=supplied,
        units={},
        energy_components={},
        electronic_converged=None,
        ionic_converged=None,
        converged=None,
        ionic_steps=0,
        file_hashes={},
        source_files=(),
        warnings=(),
    )
    supplied["nested"]["values"].append(2)
    assert result.properties["nested"]["values"] == (1,)
    with pytest.raises(TypeError):
        result.properties["nested"]["values"] += (2,)


def test_force_rows_must_match_final_structure(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    (tmp_path / "vasprun.xml").write_text(
        VASPRUN.replace(
            '<varray name="forces"><v>0.1 -0.2 0.3</v></varray>',
            '<varray name="forces"><v>0.1 -0.2 0.3</v><v>0.4 0.5 0.6</v></varray>',
        ),
        encoding="utf-8",
    )

    vasp = _vasp()
    with pytest.raises(vasp.VaspParseError, match=r"shape \(n_atoms, 3\)"):
        vasp.parse_vasp(tmp_path)


def test_missing_potcar_uses_xml_identity(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    vasp = _vasp()
    (tmp_path / "POTCAR").unlink()

    parsed = vasp.parse_vasp(tmp_path)

    assert parsed.potcar_datasets[0].title == "PAW_PBE O 08Apr2002"
    assert parsed.potcar_datasets[0].embedded_sha256 is None
    assert any(
        "POTCAR is unavailable" in warning for warning in parsed.warnings
    )


def test_potcar_without_dataset_metadata_is_fatal(tmp_path: Path) -> None:
    _write_calculation(tmp_path)
    vasp = _vasp()
    (tmp_path / "POTCAR").write_text(
        "not a POTCAR dataset\n", encoding="utf-8"
    )

    with pytest.raises(vasp.VaspParseError, match="no datasets"):
        vasp.parse_vasp(tmp_path)


def test_atomsledger_import_does_not_require_vasp_parser() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-c", "import stoms.atomsledger"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_vasp_import_reports_missing_optional_dependency() -> None:
    code = """
import builtins

original_import = builtins.__import__

def blocked_import(name, *args, **kwargs):
    if name == "pymatgen" or name.startswith("pymatgen."):
        raise ModuleNotFoundError("blocked for isolated import test")
    return original_import(name, *args, **kwargs)

builtins.__import__ = blocked_import
try:
    import stoms.parsers.vasp
except ModuleNotFoundError as error:
    assert "optional 'pymatgen' dependency" in str(error)
else:
    raise AssertionError("VASP parser unexpectedly imported without pymatgen")
"""
    result = subprocess.run(
        ["uv", "run", "python", "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
