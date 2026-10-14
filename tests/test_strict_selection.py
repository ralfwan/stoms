from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    EvaluatorSelector,
    MethodSpec,
    Provenance,
    StrictSelectionError,
    StructureQuery,
    StructureSourceSpec,
)

METHOD = MethodSpec(
    method_identifier="mace-small",
    family="MLIP",
    name="MACE",
    version="1",
    parameters={"r_max": 5.0},
)
SOURCE = StructureSourceSpec(kind="direct", name="test")


@pytest.mark.parametrize("identifier", ["", "  mace  "])
def test_method_identifier_is_required_and_trimmed(identifier: str) -> None:
    with pytest.raises(ValueError, match="method_identifier"):
        MethodSpec(
            method_identifier=identifier,
            family="MLIP",
            name="MACE",
        )


def add_structure(ledger: AtomsLedger, purpose: str) -> str:
    position = tuple(
        (ord(purpose[index]) if index < len(purpose) else 0) / 100
        for index in range(3)
    )
    result = ledger.add_structure(
        Atoms("H", positions=(position,)),
        SOURCE,
        Provenance(created_by="test", purpose=purpose),
    )
    assert isinstance(result, str)
    return result


def add_energy(
    ledger: AtomsLedger,
    structure_id: str,
    energy: float,
    *,
    method: MethodSpec = METHOD,
    unit: str = "eV",
) -> str:
    return ledger.add_evaluation(
        structure_id,
        method=method,
        properties={"energy": energy},
        units={"energy": unit},
        provenance=Provenance(created_by="test", purpose="Labels"),
    )


def test_strict_selection_and_energy_projection_preserve_alignment(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "selection.sqlite")
    first = add_structure(ledger, "first")
    second = add_structure(ledger, "second")
    first_evaluation = add_energy(ledger, first, -1.0)
    second_evaluation = add_energy(ledger, second, -2.0)
    query = StructureQuery(ids=(first, second))

    selection = ledger.select(query, evaluator=METHOD, exact_match=True)
    projection = selection.project_energy()

    assert projection.structure_ids == (first, second)
    assert projection.evaluation_ids == (first_evaluation, second_evaluation)
    np.testing.assert_array_equal(projection.values, np.array([-1.0, -2.0]))
    assert projection.unit == "eV"
    assert projection.query.structures == query
    assert selection.records[0].evaluation.properties["energy"] == -1.0


def test_strict_selection_reports_missing_structure(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "missing.sqlite")
    selected = add_structure(ledger, "selected")
    missing = add_structure(ledger, "missing")
    add_energy(ledger, selected, -1.0)

    with pytest.raises(StrictSelectionError, match=missing) as error:
        ledger.select(
            StructureQuery(ids=(selected, missing)), evaluator=METHOD
        )
    assert error.value.missing_structure_ids == (missing,)


def test_strict_selection_reports_ambiguous_structure(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "ambiguous.sqlite")
    structure_id = add_structure(ledger, "ambiguous")
    add_energy(ledger, structure_id, -1.0)
    add_energy(ledger, structure_id, -2.0)

    with pytest.raises(StrictSelectionError, match=structure_id) as error:
        ledger.select(StructureQuery(ids=(structure_id,)), evaluator=METHOD)
    assert error.value.ambiguous_structure_ids == (structure_id,)


def test_exact_method_selector_matches_parameters(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "parameters.sqlite")
    structure_id = add_structure(ledger, "parameter match")
    add_energy(
        ledger,
        structure_id,
        -1.0,
        method=MethodSpec(
            family=METHOD.family,
            name=METHOD.name,
            version=METHOD.version,
            method_identifier=METHOD.method_identifier,
            parameters={"r_max": 6.0},
        ),
    )
    matching_id = add_energy(ledger, structure_id, -2.0)

    selection = ledger.select(
        DatasetQuery(structures=StructureQuery(ids=(structure_id,))),
        evaluator=EvaluatorSelector(METHOD, exact_match=True),
    )

    assert selection.evaluation_ids == (matching_id,)


def test_method_identifier_matches_different_specs_by_default(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "method-identifier.sqlite")
    structure_id = add_structure(ledger, "identifier")
    shared_identifier_method = MethodSpec(
        method_identifier=METHOD.method_identifier,
        family="MLIP",
        name="different-description",
        parameters={"r_max": 9.0},
    )
    evaluation_id = add_energy(
        ledger,
        structure_id,
        -1.0,
        method=shared_identifier_method,
    )

    selection = ledger.select(
        StructureQuery(ids=(structure_id,)), evaluator=METHOD
    )

    assert selection.evaluation_ids == (evaluation_id,)


def test_list_method_identifiers_is_sorted_and_distinct(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "method-identifiers.sqlite")
    for purpose, method_identifier in (
        ("first", "z-method"),
        ("second", "a-method"),
        ("third", "z-method"),
    ):
        structure_id = add_structure(ledger, purpose)
        add_energy(
            ledger,
            structure_id,
            -1.0,
            method=replace(METHOD, method_identifier=method_identifier),
        )

    assert ledger.list_method_identifiers() == ("a-method", "z-method")


def test_projection_rejects_mixed_units(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "units.sqlite")
    first = add_structure(ledger, "first")
    second = add_structure(ledger, "second")
    add_energy(ledger, first, -1.0, unit="eV")
    add_energy(ledger, second, -2.0, unit="hartree")
    selection = ledger.select(
        StructureQuery(ids=(first, second)), evaluator=METHOD
    )

    with pytest.raises(ValueError, match="mixed units"):
        selection.project("energy")
