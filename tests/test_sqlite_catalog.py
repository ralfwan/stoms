from pathlib import Path

import numpy as np
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureQuery,
    StructureSourceSpec,
)

SOURCE = StructureSourceSpec(kind="direct", name="test")


def test_catalog_search_returns_metadata_and_evaluator_inventory(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "catalog.atomsledger")
    structure_id = ledger.add_structure(
        Atoms("H2", positions=((0, 0, 0), (0, 0, 0.74))),
        SOURCE,
        Provenance(
            created_by="catalog-test",
            purpose="Catalog candidate",
            tags=("study:h2", "split:train"),
        ),
    )
    assert isinstance(structure_id, str)
    ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace-small",
            family="MLIP",
            name="MACE",
            version="0.3",
            code="mace-torch",
            parameters={"r_max": 6.0},
        ),
        properties={
            "energy": -1.0,
            "forces": np.zeros((2, 3)),
        },
        provenance=Provenance(
            created_by="catalog-test",
            purpose="Catalog labels",
            tags=("quality:reference",),
        ),
    )

    results = ledger.catalog.search(
        StructureQuery(tags_all=("study:h2", "split:train"))
    )

    assert len(results) == 1
    result = results[0]
    assert result.id == structure_id
    assert result.formula == "H2"
    assert result.created_by == "catalog-test"
    assert result.tags == ("split:train", "study:h2")
    assert result.available_property_names == ("energy", "forces")
    assert len(result.evaluators) == 1
    evaluator = result.evaluators[0]
    assert evaluator.method == MethodSpec(
        method_identifier="mace-small",
        family="MLIP",
        name="MACE",
        version="0.3",
        code="mace-torch",
        parameters={"r_max": 6.0},
    )
    assert evaluator.property_names == ("energy", "forces")


def test_catalog_search_does_not_deserialize_payloads(
    tmp_path: Path, monkeypatch
) -> None:
    ledger = AtomsLedger(tmp_path / "catalog-no-payload.atomsledger")
    structure_id = ledger.add_structure(
        Atoms("H"),
        SOURCE,
        Provenance(created_by="catalog-test", purpose="Candidate"),
    )
    assert isinstance(structure_id, str)
    ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="reference", family="DFT", name="Reference"
        ),
        properties={"energy": -1.0},
        provenance=Provenance(created_by="catalog-test", purpose="Label"),
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("catalog search deserialized a payload")

    monkeypatch.setattr(
        "stoms.atomsledger.backends.sqlite.atoms_from_binary_payload", fail
    )
    monkeypatch.setattr(
        "stoms.atomsledger.backends.sqlite.properties_from_binary_payload",
        fail,
    )

    results = ledger.catalog.search(StructureQuery(formula="H"))

    assert [result.id for result in results] == [structure_id]
    assert results[0].available_property_names == ("energy",)


def test_catalog_search_uses_structure_query_purpose_casefold(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "catalog-purpose.atomsledger")
    structure_id = ledger.add_structure(
        Atoms("H"),
        SOURCE,
        Provenance(created_by="catalog-test", purpose="Straße candidate"),
    )
    assert isinstance(structure_id, str)

    results = ledger.catalog.search(StructureQuery(purpose_contains="STRASSE"))

    assert [result.id for result in results] == [structure_id]
