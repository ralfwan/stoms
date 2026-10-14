from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from ase import Atoms
from ase.io import write

from .exceptions import (
    AggregationValidationError,
    EquivalentAtomsWarning,
    IntegrityError,
    SerializationError,
    StoredQueryInUseError,
    StrictSelectionError,
    StructureContentConflictError,
    StructureContentMismatchError,
)
from .model import (
    Aggregation,
    AggregationID,
    AggregationMember,
    AggregationMemberInput,
    AggregationSummary,
    DatasetQuery,
    EvaluationInput,
    EvaluationQuery,
    EvaluationRecord,
    EvaluatorSelector,
    MethodSpec,
    Provenance,
    RecordId,
    SelectedRecord,
    StoredQuery,
    StoredQueryID,
    StoredQuerySummary,
    StrictSelection,
    StructureContentMatch,
    StructureInput,
    StructureQuery,
    StructureRecord,
    StructureSourceSpec,
    TrajectoryFrame,
    TrajectoryRecord,
    new_id,
    utc_now,
)
from .repository import Repository
from .serialization import (
    aggregation_membership_hash,
    dataset_query_to_dict,
    evaluation_content_hash,
    json_dumps,
    structure_content_hash,
    to_plain,
)
from .transfer import (
    ConflictPolicy,
    TransferReport,
    _export_hdf5,
    _import_hdf5,
    export_sqlite,
    import_sqlite,
    transfer_repository,
)

if TYPE_CHECKING:
    from .catalog import SQLiteCatalog

EvaluationPolicy = Literal["none", "latest", "all"]
StructureInputLike = Atoms | StructureInput | Mapping[str, Any]
EvaluationInputLike = EvaluationInput | Mapping[str, Any]
DatasetSelector = str | DatasetQuery | StructureQuery | StoredQuery
EvaluatorSelectorInput = str | MethodSpec | EvaluationQuery | EvaluatorSelector


def _warn_reused_structure_ids(ids: Iterable[RecordId]) -> None:
    reused_ids = tuple(dict.fromkeys(ids))
    if not reused_ids:
        return
    warnings.warn(
        "Returned structure_ids of equivalent atoms: " + ", ".join(reused_ids),
        EquivalentAtomsWarning,
        stacklevel=3,
    )


_STANDARD_UNITS = {
    "energy": "eV",
    "forces": "eV/angstrom",
    "node_energy": "eV",
}

_STANDARD_ASE_RESULTS = {
    "energy",
    "free_energy",
    "forces",
    "stress",
    "stresses",
    "dipole",
    "charges",
    "magmom",
    "magmoms",
}


class AtomsLedger:
    """User-facing application service independent of the storage backend."""

    def __init__(
        self, repository: Repository | str | Path = "atomsledger.sqlite"
    ) -> None:
        """Create a ledger from a repository or a SQLite file path.

        Passing a path is the default and constructs ``SQLiteRepository``.
        Existing explicit repository construction remains supported.
        """
        self.repository: Repository
        if isinstance(repository, str | Path):
            from .backends.sqlite import SQLiteRepository

            self.repository = SQLiteRepository(repository)
        else:
            self.repository = repository

    @classmethod
    def open(cls, path: str | Path = "atomsledger.sqlite") -> AtomsLedger:
        """Open or create the default SQLite-backed ledger."""
        return cls(path)

    @property
    def catalog(self) -> SQLiteCatalog:
        """Return the read-only SQLite metadata catalog for this ledger."""
        from .backends.sqlite import SQLiteRepository
        from .catalog import SQLiteCatalog

        if not isinstance(self.repository, SQLiteRepository):
            raise TypeError("Metadata catalog is only available for SQLite")
        return SQLiteCatalog(self.repository)

    @staticmethod
    def _structure_record(
        atoms: Atoms,
        source_spec: StructureSourceSpec,
        provenance: Provenance,
    ) -> StructureRecord:
        snapshot = atoms.copy()
        snapshot.calc = None
        return StructureRecord(
            id=new_id("str"),
            created_at=utc_now(),
            structure_content_hash=structure_content_hash(snapshot),
            source_spec=source_spec,
            provenance=provenance,
            _atoms=snapshot,
        )

    def add_structure(
        self,
        atoms: Atoms,
        source_spec: StructureSourceSpec,
        provenance: Provenance,
        *,
        report_equivalent_content: bool = False,
        allow_equivalent_atoms: bool = False,
    ) -> RecordId | tuple[StructureContentMatch, ...]:
        """Snapshot one calculator-free structure with immutable provenance.

        An exact content, provenance, and source-specification repeat returns
        the persisted ID. Equivalent content with changed provenance or source
        specification returns existing ``StructureContentMatch`` values unless
        ``allow_equivalent_atoms`` explicitly permits a new record. The
        ``report_equivalent_content`` argument is accepted for compatibility but
        has no effect.
        """
        if not isinstance(source_spec, StructureSourceSpec):
            raise TypeError("source_spec must be a StructureSourceSpec")
        if not isinstance(provenance, Provenance):
            raise TypeError("provenance must be a Provenance")
        record = self._structure_record(atoms, source_spec, provenance)
        try:
            persisted = self.repository.put_structures_content_aware(
                [record], allow_equivalent_atoms=allow_equivalent_atoms
            )
        except StructureContentConflictError as error:
            matches = tuple(
                match
                for conflict in error.conflicts
                for match in conflict.matches
            )
            _warn_reused_structure_ids(match.id for match in matches)
            return matches
        persisted_record = persisted[0]
        if persisted_record.id != record.id:
            _warn_reused_structure_ids([persisted_record.id])
        return persisted_record.id

    def add_structures(
        self,
        items: Iterable[StructureInputLike],
        *,
        source_spec: StructureSourceSpec,
        provenance: Provenance | None = None,
        allow_equivalent_atoms: bool = False,
    ) -> list[RecordId]:
        """Insert a batch of ASE objects atomically where the backend supports it.

        Plain ``Atoms`` objects use the shared ``provenance`` argument. For
        per-structure provenance, pass ``StructureInput`` instances or mappings
        with ``atoms`` and ``provenance`` keys. One source specification applies
        to the complete batch.
        """
        if not isinstance(source_spec, StructureSourceSpec):
            raise TypeError("source_spec must be a StructureSourceSpec")
        records: list[StructureRecord] = []
        for item in items:
            if isinstance(item, Atoms):
                if provenance is None:
                    raise ValueError(
                        "Shared provenance is required for plain Atoms inputs"
                    )
                atoms = item
                item_provenance = provenance
            elif isinstance(item, StructureInput):
                atoms = item.atoms
                item_provenance = item.provenance
            elif isinstance(item, Mapping):
                atoms = item["atoms"]
                item_provenance = item.get("provenance", provenance)
                if not isinstance(atoms, Atoms):
                    raise TypeError(
                        "Structure mapping 'atoms' must be an ASE Atoms"
                    )
                if not isinstance(item_provenance, Provenance):
                    raise TypeError(
                        "Structure mapping requires a Provenance instance"
                    )
            else:
                raise TypeError(f"Unsupported structure input: {type(item)!r}")
            records.append(
                self._structure_record(atoms, source_spec, item_provenance)
            )

        persisted = self.repository.put_structures_content_aware(
            records, allow_equivalent_atoms=allow_equivalent_atoms
        )
        input_ids = {record.id for record in records}
        _warn_reused_structure_ids(
            record.id for record in persisted if record.id not in input_ids
        )
        return [record.id for record in persisted]

    def _evaluation_record(
        self,
        structure_id: RecordId,
        *,
        method: MethodSpec,
        properties: Mapping[str, Any],
        units: Mapping[str, str] | None,
        provenance: Provenance,
        atom_count: int,
    ) -> EvaluationRecord:
        """Validate and construct an immutable evaluation record."""
        self._validate_standard_properties(properties, atom_count)
        resolved_units = dict(units or {})
        for name, default in _STANDARD_UNITS.items():
            if name in properties:
                resolved_units.setdefault(name, default)
        return EvaluationRecord(
            id=new_id("eval"),
            structure_id=structure_id,
            created_at=utc_now(),
            content_hash=evaluation_content_hash(
                structure_id, method, properties, resolved_units
            ),
            method=method,
            properties=properties,
            units=resolved_units,
            provenance=provenance,
        )

    @staticmethod
    def _validate_standard_properties(
        properties: Mapping[str, Any], atom_count: int
    ) -> None:
        """Validate supplied standard properties against the structure size."""
        standard_names = set(_STANDARD_UNITS).intersection(properties)
        if not standard_names:
            raise ValueError(
                "At least one of 'energy', 'forces', or 'node_energy' "
                "must be supplied"
            )
        expected_shapes = {
            "energy": ((), (1,)),
            "forces": ((atom_count, 3),),
            "node_energy": ((atom_count,),),
        }
        for name, shapes in expected_shapes.items():
            if name not in properties:
                continue
            try:
                value = np.asarray(properties[name])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Standard property {name!r} must be numeric"
                ) from error
            if not np.issubdtype(value.dtype, np.number):
                raise ValueError(f"Standard property {name!r} must be numeric")
            if value.shape not in shapes:
                expected = " or ".join(map(str, shapes))
                raise ValueError(
                    f"Standard property {name!r} has shape {value.shape}; "
                    f"expected {expected}"
                )

    def add_evaluation(
        self,
        structure_id: RecordId,
        *,
        method: MethodSpec,
        properties: Mapping[str, Any],
        units: Mapping[str, str] | None = None,
        provenance: Provenance,
    ) -> RecordId:
        """Validate and persist one evaluation for an existing structure."""
        structure = self.repository.get_structure(structure_id)
        record = self._evaluation_record(
            structure_id,
            method=method,
            properties=properties,
            units=units,
            provenance=provenance,
            atom_count=len(structure.atoms),
        )
        self.repository.put_evaluation(record)
        return record.id

    def add_evaluations(
        self,
        items: Iterable[EvaluationInputLike],
    ) -> list[RecordId]:
        """Validate and insert evaluation inputs in one backend batch."""
        records: list[EvaluationRecord] = []
        structures: dict[RecordId, StructureRecord] = {}
        for item in items:
            if isinstance(item, EvaluationInput):
                value = item
            elif isinstance(item, Mapping):
                value = EvaluationInput(
                    structure_id=item["structure_id"],
                    method=item["method"],
                    properties=item["properties"],
                    provenance=item["provenance"],
                    units=item.get("units", {}),
                )
            else:
                raise TypeError(
                    f"Unsupported evaluation input: {type(item)!r}"
                )
            if not isinstance(value.method, MethodSpec):
                raise TypeError("Evaluation method must be a MethodSpec")
            if not isinstance(value.provenance, Provenance):
                raise TypeError("Evaluation provenance must be a Provenance")
            if value.structure_id not in structures:
                structures[value.structure_id] = self.repository.get_structure(
                    value.structure_id
                )
            records.append(
                self._evaluation_record(
                    value.structure_id,
                    method=value.method,
                    properties=value.properties,
                    units=value.units,
                    provenance=value.provenance,
                    atom_count=len(structures[value.structure_id].atoms),
                )
            )

        self.repository.put_evaluations(records)
        return [record.id for record in records]

    def add_trajectory(
        self,
        *,
        kind: str,
        frames: Sequence[TrajectoryFrame],
        provenance: Provenance,
    ) -> RecordId:
        """Create an immutable ordered trajectory from existing record IDs."""
        record = TrajectoryRecord(
            id=new_id("traj"),
            created_at=utc_now(),
            kind=kind,
            frames=tuple(frames),
            provenance=provenance,
        )
        self.repository.put_trajectory(record)
        return record.id

    def create_stored_query(
        self,
        *,
        label: str,
        query: DatasetQuery,
        provenance: Provenance,
        description: str = "",
        hidden_at=None,
    ) -> RecordId:
        """Persist an immutable dataset definition under a nonunique label."""
        record = StoredQuery(
            id=new_id("query"),
            label=label,
            description=description,
            query=query,
            created_at=utc_now(),
            provenance=provenance,
            hidden_at=hidden_at,
        )
        self.repository.put_stored_query(record)
        return record.id

    def list_stored_queries(self) -> tuple[StoredQuerySummary, ...]:
        """List visible stored-query summaries in repository order."""
        return tuple(self.repository.iter_stored_query_summaries())

    def get_stored_query(self, query_id: StoredQueryID) -> StoredQuery:
        """Return a stored query by its ``query_...`` ID, not its label."""
        return self.repository.get_stored_query(query_id)

    def delete_stored_query(
        self, query_id: StoredQueryID, *, force=False
    ) -> None:
        """Delete a stored query, requiring ``force`` when aggregations use it."""
        try:
            self.repository.delete_stored_query(query_id, force=force)
        except StoredQueryInUseError:
            raise

    def hide_stored_query(self, query_id: StoredQueryID) -> None:
        """Hide a stored query from normal listings without deleting it."""
        self.repository.hide_stored_query(query_id)

    # Stored queries are immutable records; this is the only creation API.
    def _stored_query_evaluator(
        self, evaluator: EvaluatorSelectorInput
    ) -> EvaluationQuery:
        if isinstance(evaluator, EvaluationQuery):
            return evaluator
        if isinstance(evaluator, MethodSpec):
            return self._resolve_evaluator(evaluator)
        if isinstance(evaluator, EvaluatorSelector):
            return self._resolve_evaluator(evaluator)
        if isinstance(evaluator, str):
            return EvaluationQuery(method_names=(evaluator,))
        raise TypeError(f"Unsupported evaluator: {type(evaluator)!r}")

    def create_aggregation(
        self,
        *,
        name: str,
        members: Sequence[AggregationMemberInput],
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        external_key: str | None = None,
        supersedes_id: str | None = None,
        _source_stored_query_id: StoredQueryID | None = None,
        _source_query_snapshot: Mapping[str, Any] | None = None,
    ) -> Aggregation:
        """Atomically create an immutable, ordered aggregation."""
        if not isinstance(name, str) or not name:
            raise AggregationValidationError("An aggregation name is required")
        try:
            inputs = tuple(members)
        except TypeError as error:
            raise AggregationValidationError(
                "structure_ids must be a sequence of structure IDs"
            ) from error
        if not inputs:
            raise AggregationValidationError(
                "An aggregation must contain at least one structure"
            )
        if any(
            not isinstance(member, AggregationMemberInput) for member in inputs
        ):
            raise AggregationValidationError(
                "members must contain AggregationMemberInput values"
            )
        if description is not None and not isinstance(description, str):
            raise AggregationValidationError(
                "Aggregation description must be text"
            )
        if metadata is not None and not isinstance(metadata, Mapping):
            raise AggregationValidationError(
                "Aggregation metadata must be a mapping"
            )
        if external_key is not None and not isinstance(external_key, str):
            raise AggregationValidationError("External keys must be strings")

        if supersedes_id is not None:
            self.get_aggregation(supersedes_id, include_members=False)

        aggregation = Aggregation(
            id=new_id("agg"),
            name=name,
            description=description,
            created_at=utc_now(),
            metadata=dict(metadata or {}),
            source_stored_query_id=_source_stored_query_id,
            source_query_snapshot=_source_query_snapshot,
            external_key=external_key,
            membership_hash=aggregation_membership_hash(
                tuple(
                    (member.structure_id, member.evaluation_id)
                    for member in inputs
                )
            ),
            supersedes_id=supersedes_id,
            members=tuple(
                AggregationMember(
                    ordinal=ordinal,
                    structure_id=member.structure_id,
                    evaluation_id=member.evaluation_id,
                )
                for ordinal, member in enumerate(inputs)
            ),
        )
        try:
            json_dumps(aggregation.metadata)
        except (SerializationError, TypeError, ValueError) as error:
            raise AggregationValidationError(
                "Aggregation metadata must be JSON serializable"
            ) from error
        put_aggregation = getattr(self.repository, "put_aggregation", None)
        if put_aggregation is None:
            raise TypeError(
                "Aggregations are only available by supported backends"
            )
        return put_aggregation(aggregation)

    def get_aggregation(
        self,
        aggregation_id: str,
        *,
        include_members: bool = True,
    ) -> Aggregation:
        """Return an aggregation by ID, optionally without its members."""
        get_aggregation = getattr(self.repository, "get_aggregation", None)
        if get_aggregation is None:
            raise TypeError(
                "Aggregations are only available by supported backends"
            )
        return get_aggregation(aggregation_id, include_members=include_members)

    def get_aggregation_by_external_key(
        self,
        external_key: str,
        *,
        include_members: bool = True,
    ) -> Aggregation:
        """Return an aggregation by its caller-defined idempotency key."""
        get_aggregation = getattr(
            self.repository, "get_aggregation_by_external_key", None
        )
        if get_aggregation is None:
            raise TypeError(
                "Aggregations are only available by supported backends"
            )
        return get_aggregation(external_key, include_members=include_members)

    def list_aggregations(
        self,
        *,
        name: str | None = None,
        source_stored_query_id: StoredQueryID | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> list[AggregationSummary]:
        """List aggregation metadata, optionally filtering exact metadata values."""
        iter_summaries = getattr(
            self.repository, "iter_aggregation_summaries", None
        )
        if iter_summaries is None:
            raise TypeError(
                "Aggregations are only available by supported backends"
            )
        if metadata_filter is not None and not isinstance(
            metadata_filter, Mapping
        ):
            raise AggregationValidationError(
                "Metadata filters must be mappings"
            )
        summaries = iter_summaries(
            name=name, source_stored_query_id=source_stored_query_id
        )
        expected = dict(metadata_filter or {})
        return [
            summary
            for summary in summaries
            if all(
                summary.metadata.get(key) == value
                for key, value in expected.items()
            )
        ]

    def get_aggregation_structure_ids(
        self, aggregation_id: str
    ) -> list[RecordId]:
        """Return structure IDs in immutable aggregation member order."""
        aggregation = self.get_aggregation(aggregation_id)
        return [member.structure_id for member in aggregation.members]

    def get_aggregation_structures(self, aggregation_id: str) -> list[Atoms]:
        """Load defensive ASE copies for an aggregation in member order."""
        return [
            self.load_atoms(structure_id)
            for structure_id in self.get_aggregation_structure_ids(
                aggregation_id
            )
        ]

    def materialize_stored_query(
        self,
        *,
        stored_query_id: StoredQueryID,
        name: str,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        external_key: str | None = None,
    ) -> Aggregation:
        """Evaluate a stored query once and freeze current member identities.

        This preserves all evaluations matching the query and is not the strict
        one-evaluation-per-structure selection operation.
        """
        stored_query = self.get_stored_query(stored_query_id)
        structures = tuple(self.find_structures(stored_query.query.structures))
        if stored_query.query.evaluations is None:
            members = tuple(
                AggregationMemberInput(structure.id)
                for structure in structures
            )
        else:
            structure_ids = tuple(structure.id for structure in structures)
            evaluation_query = stored_query.query.evaluations
            if evaluation_query.structure_ids is None:
                evaluation_query = replace(
                    evaluation_query, structure_ids=structure_ids
                )
            else:
                evaluation_query = replace(
                    evaluation_query,
                    structure_ids=tuple(
                        structure_id
                        for structure_id in structure_ids
                        if structure_id in evaluation_query.structure_ids
                    ),
                )
            evaluations = tuple(self.find_evaluations(evaluation_query))
            matching_ids = {
                evaluation.structure_id for evaluation in evaluations
            }
            members = tuple(
                member
                for structure in structures
                for member in (
                    tuple(
                        AggregationMemberInput(structure.id, evaluation.id)
                        for evaluation in evaluations
                        if evaluation.structure_id == structure.id
                    )
                    or (
                        ()
                        if stored_query.query.require_evaluation
                        or structure.id in matching_ids
                        else (AggregationMemberInput(structure.id),)
                    )
                )
            )
            if not members:
                raise AggregationValidationError(
                    "Stored query materialized to an empty aggregation"
                )
        return self.create_aggregation(
            name=name,
            members=members,
            description=description,
            metadata=metadata,
            _source_stored_query_id=stored_query.id,
            _source_query_snapshot=dataset_query_to_dict(stored_query.query),
            external_key=external_key,
        )

    def load_atoms(self, structure_id: RecordId) -> Atoms:
        """Load a defensive ASE copy for one structure ID."""
        return self.repository.get_structure(structure_id).atoms

    def validate_structure_content(
        self, structure_id: RecordId, atoms: Atoms
    ) -> None:
        """Raise if calculator-free atoms content differs from a structure."""
        expected = self.repository.get_structure(structure_id)
        snapshot = atoms.copy()
        snapshot.calc = None
        actual_hash = structure_content_hash(snapshot)
        if actual_hash != expected.structure_content_hash:
            raise StructureContentMismatchError(
                structure_id,
                expected_structure_content_hash=expected.structure_content_hash,
                actual_structure_content_hash=actual_hash,
            )

    def load_evaluation(self, evaluation_id: RecordId) -> EvaluationRecord:
        """Load one immutable evaluation by ID."""
        return self.repository.get_evaluation(evaluation_id)

    def find_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureRecord]:
        """Iterate structures matching indexed metadata criteria."""
        return self.repository.iter_structures(query)

    def find_evaluations(
        self, query: EvaluationQuery | None = None
    ) -> Iterable[EvaluationRecord]:
        """Iterate evaluations matching indexed metadata criteria."""
        return self.repository.iter_evaluations(query)

    def list_method_identifiers(self) -> tuple[str, ...]:
        """Return sorted distinct persisted method identifiers."""
        return tuple(self.repository.list_method_identifiers())

    def _tag_repository(self) -> Any:
        add_tags_many = getattr(self.repository, "add_tags_many", None)
        get_tags = getattr(self.repository, "get_tags", None)
        if add_tags_many is None or get_tags is None:
            raise TypeError(
                "Post-ingestion tags are only supported by SQLite repositories"
            )
        return self.repository

    def add_tags(
        self, record_id: RecordId, tags: Iterable[str]
    ) -> frozenset[str]:
        """Append tags to one existing structure or evaluation."""
        if isinstance(tags, str):
            raise TypeError(
                "Tags must be an iterable of strings, not a string"
            )
        values = tuple(tags)
        if not values:
            raise ValueError("At least one tag is required")
        return self._tag_repository().add_tags_many({record_id: values})[
            record_id
        ]

    def add_tags_many(
        self, records: Mapping[RecordId, Iterable[str]]
    ) -> dict[RecordId, frozenset[str]]:
        """Append tags to multiple records in one transaction."""
        return self._tag_repository().add_tags_many(records)

    def get_tags(self, record_id: RecordId) -> frozenset[str]:
        """Return the effective tags for one existing record."""
        return self._tag_repository().get_tags(record_id)

    def transfer_to(
        self,
        target: Repository,
        *,
        conflict: ConflictPolicy = "verify",
        batch_size: int = 256,
    ) -> TransferReport:
        """Additively transfer every record to a repository with conflict checks."""
        return transfer_repository(
            self.repository,
            target,
            conflict=conflict,
            batch_size=batch_size,
        )

    def export_database(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
        batch_size: int = 256,
    ) -> TransferReport:
        """Export the complete repository to the default SQLite format."""
        return self.export_database_sqlite(
            destination, overwrite=overwrite, batch_size=batch_size
        )

    def import_database(
        self,
        source: str | Path,
        *,
        conflict: ConflictPolicy = "verify",
        batch_size: int = 256,
    ) -> TransferReport:
        """Import a complete repository from the default SQLite format."""
        return self.import_database_sqlite(
            source, conflict=conflict, batch_size=batch_size
        )

    def export_database_sqlite(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
        batch_size: int = 256,
    ) -> TransferReport:
        return export_sqlite(
            self.repository,
            destination,
            overwrite=overwrite,
            batch_size=batch_size,
        )

    def import_database_sqlite(
        self,
        source: str | Path,
        *,
        conflict: ConflictPolicy = "verify",
        batch_size: int = 256,
    ) -> TransferReport:
        return import_sqlite(
            source,
            self.repository,
            conflict=conflict,
            batch_size=batch_size,
        )

    def _export_database_hdf5(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
        batch_size: int = 256,
    ) -> TransferReport:
        """Retained HDF5 export implementation for future reactivation."""
        return _export_hdf5(
            self.repository,
            destination,
            overwrite=overwrite,
            batch_size=batch_size,
        )

    def _import_database_hdf5(
        self,
        source: str | Path,
        *,
        conflict: ConflictPolicy = "verify",
        batch_size: int = 256,
    ) -> TransferReport:
        """Retained HDF5 import implementation for future reactivation."""
        return _import_hdf5(
            source,
            self.repository,
            conflict=conflict,
            batch_size=batch_size,
        )

    def _resolve_dataset(
        self, dataset: DatasetSelector | None
    ) -> DatasetQuery:
        if dataset is None:
            return DatasetQuery()
        if isinstance(dataset, str):
            return self.get_stored_query(dataset).query
        if isinstance(dataset, StoredQuery):
            return dataset.query
        if isinstance(dataset, DatasetQuery):
            return dataset
        raise TypeError(f"Unsupported dataset selector: {type(dataset)!r}")

    @staticmethod
    def _resolve_evaluator(
        evaluator: EvaluatorSelectorInput,
    ) -> EvaluationQuery:
        if isinstance(evaluator, str):
            return EvaluationQuery(method_names=(evaluator,))
        if isinstance(evaluator, EvaluationQuery):
            return evaluator
        exact_match = False
        if isinstance(evaluator, EvaluatorSelector):
            exact_match = evaluator.exact_match
            evaluator = evaluator.method
        if isinstance(evaluator, MethodSpec):
            if not exact_match:
                return EvaluationQuery(
                    method_identifiers=(evaluator.method_identifier,)
                )
            return EvaluationQuery(
                method_families=(evaluator.family,),
                method_names=(evaluator.name,),
                method_versions=(
                    (evaluator.version,)
                    if evaluator.version is not None
                    else ()
                ),
                method_codes=(
                    (evaluator.code,) if evaluator.code is not None else ()
                ),
                method_identifiers=(evaluator.method_identifier,),
            )
        raise TypeError(f"Unsupported evaluator selector: {type(evaluator)!r}")

    def select(
        self,
        query: DatasetSelector | StructureQuery | None = None,
        *,
        evaluator: EvaluatorSelectorInput | None = None,
        exact_match: bool = False,
    ) -> StrictSelection:
        """Strictly pair each matching structure with one evaluation.

        A ``MethodSpec`` selector matches its method identifier by default. Set
        ``exact_match`` (or use ``EvaluatorSelector(..., exact_match=True)``)
        to compare family, name, version, code, method identifier, and
        parameters. ``model_id`` is not compared by the current implementation.
        """
        if isinstance(query, StructureQuery):
            resolved = DatasetQuery(structures=query)
            saved_selector = None
        elif isinstance(query, str):
            resolved = self._resolve_dataset(query)
            saved_selector = None
        elif isinstance(query, StoredQuery):
            resolved = query.query
            saved_selector = None
        else:
            resolved = self._resolve_dataset(query)
            saved_selector = None
        if evaluator is None and resolved.evaluations is None:
            raise ValueError("Strict selection requires an evaluator selector")

        method_selector: EvaluatorSelector | None = None
        if evaluator is None and saved_selector is not None:
            method_selector = saved_selector
        if isinstance(evaluator, EvaluatorSelector):
            method_selector = evaluator
            resolved = resolved.with_evaluator(
                self._resolve_evaluator(evaluator)
            )
        elif isinstance(evaluator, MethodSpec):
            method_selector = EvaluatorSelector(
                evaluator, exact_match=exact_match
            )
            resolved = resolved.with_evaluator(
                self._resolve_evaluator(method_selector)
            )
        elif evaluator is not None:
            resolved = resolved.with_evaluator(
                self._resolve_evaluator(evaluator)
            )

        structures = list(self.repository.iter_structures(resolved.structures))
        structure_ids = tuple(structure.id for structure in structures)
        evaluations_by_structure: dict[
            RecordId, tuple[EvaluationRecord | None, int]
        ] = {}
        if resolved.evaluations is not None and structure_ids:
            evaluation_query = resolved.evaluations
            if evaluation_query.structure_ids is None:
                evaluation_query = replace(
                    evaluation_query, structure_ids=structure_ids
                )
            else:
                selected_ids = tuple(
                    structure_id
                    for structure_id in structure_ids
                    if structure_id in evaluation_query.structure_ids
                )
                evaluation_query = replace(
                    evaluation_query, structure_ids=selected_ids
                )
            for evaluation in self.repository.iter_evaluations(
                evaluation_query
            ):
                if method_selector is not None and not method_selector.matches(
                    evaluation.method
                ):
                    continue
                first_evaluation, count = evaluations_by_structure.get(
                    evaluation.structure_id, (None, 0)
                )
                evaluations_by_structure[evaluation.structure_id] = (
                    first_evaluation or evaluation,
                    count + 1,
                )

        missing: list[RecordId] = []
        ambiguous: list[RecordId] = []
        records: list[SelectedRecord] = []
        for structure in structures:
            selected_evaluation, count = evaluations_by_structure.get(
                structure.id, (None, 0)
            )
            if count == 0 or selected_evaluation is None:
                missing.append(structure.id)
            elif count > 1:
                ambiguous.append(structure.id)
            else:
                records.append(SelectedRecord(structure, selected_evaluation))

        if missing or ambiguous:
            details: list[str] = []
            if missing:
                details.append(f"missing={missing}")
            if ambiguous:
                details.append(f"ambiguous={ambiguous}")
            raise StrictSelectionError(
                "Strict selection requires exactly one evaluation per structure "
                + "; ".join(details),
                missing_structure_ids=tuple(missing),
                ambiguous_structure_ids=tuple(ambiguous),
            )
        return StrictSelection(query=resolved, records=tuple(records))

    def to_extxyz(
        self,
        destination: str | Path,
        *,
        dataset: DatasetSelector | None = None,
        evaluator: EvaluatorSelectorInput | None = None,
        selection: StrictSelection | None = None,
        aggregation_id: AggregationID | None = None,
        energy_label: str = "REF_energy",
        forces_label: str = "REF_forces",
        node_energy_label: str = "REF_node_energy",
        include_node_energy: bool = False,
    ) -> int:
        """Export a saved query, aggregation, or strict selection as extxyz.

        Every selected structure must have exactly one matching evaluation.
        ``selection`` can be supplied when the caller already performed the
        strict selection; otherwise ``dataset`` and ``evaluator`` are resolved
        and selected here. ``aggregation_id`` exports each member's attached
        evaluation in immutable member order.
        """
        return self.export_extxyz(
            destination,
            dataset=dataset,
            evaluator=evaluator,
            selection=selection,
            aggregation_id=aggregation_id,
            energy_label=energy_label,
            forces_label=forces_label,
            node_energy_label=node_energy_label,
            include_node_energy=include_node_energy,
        )

    def export_extxyz(
        self,
        destination: str | Path,
        *,
        query: DatasetQuery | None = None,
        template: str | StoredQuery | None = None,
        dataset: DatasetSelector | None = None,
        evaluator: EvaluatorSelectorInput | None = None,
        selection: StrictSelection | None = None,
        aggregation_id: AggregationID | None = None,
        energy_label: str = "REF_energy",
        forces_label: str = "REF_forces",
        node_energy_label: str = "REF_node_energy",
        include_node_energy: bool = False,
    ) -> int:
        """Export a strict selection as extxyz and return its frame count."""
        if aggregation_id is not None and any(
            value is not None
            for value in (query, template, dataset, evaluator, selection)
        ):
            raise ValueError(
                "aggregation_id cannot be combined with query, template, "
                "dataset, evaluator, or selection"
            )
        if selection is not None and any(
            value is not None
            for value in (query, template, dataset, evaluator)
        ):
            raise ValueError("Provide either selection or query selectors")
        if aggregation_id is not None:
            selection = self._selection_from_aggregation(aggregation_id)
        elif selection is None:
            if query is not None and any(
                value is not None for value in (template, dataset)
            ):
                raise ValueError("Provide only one dataset selector")
            if template is not None:
                dataset = template
            if query is not None:
                selection = self.select(query, evaluator=evaluator)
            else:
                selection = self.select(dataset, evaluator=evaluator)

        assert selection is not None
        selected = selection
        count = 0

        def frames() -> Iterable[Atoms]:
            nonlocal count
            for item in selected.records:
                count += 1
                yield self._export_frame(
                    item.structure,
                    item.evaluation,
                    energy_label=energy_label,
                    forces_label=forces_label,
                    node_energy_label=node_energy_label,
                    include_node_energy=include_node_energy,
                )

        write(
            str(destination),
            frames(),  # type: ignore[arg-type]
            format="extxyz",
            write_info=True,
            write_results=False,
        )
        return count

    def _selection_from_aggregation(
        self, aggregation_id: AggregationID
    ) -> StrictSelection:
        """Resolve an aggregation's exact ordered structure/evaluation pairs."""
        aggregation = self.get_aggregation(aggregation_id)
        records: list[SelectedRecord] = []
        for member in aggregation.members:
            if member.evaluation_id is None:
                raise StrictSelectionError(
                    f"Aggregation {aggregation.id} member {member.ordinal} "
                    "has no evaluation"
                )
            structure = self.repository.get_structure(member.structure_id)
            evaluation = self.repository.get_evaluation(member.evaluation_id)
            if evaluation.structure_id != structure.id:
                raise IntegrityError(
                    f"Aggregation {aggregation.id} member {member.ordinal} "
                    f"pairs structure {structure.id} with evaluation "
                    f"{evaluation.id}, which belongs to "
                    f"{evaluation.structure_id}"
                )
            records.append(SelectedRecord(structure, evaluation))
        return StrictSelection(query=DatasetQuery(), records=tuple(records))

    def _evaluations_for_structure(
        self, structure_id: RecordId, query: EvaluationQuery | None
    ) -> list[EvaluationRecord]:
        effective = (query or EvaluationQuery()).for_structure(structure_id)
        return list(self.repository.iter_evaluations(effective))

    @staticmethod
    def _export_frame(
        structure: StructureRecord,
        evaluation: EvaluationRecord | None,
        *,
        energy_label: str = "REF_energy",
        forces_label: str = "REF_forces",
        node_energy_label: str = "REF_node_energy",
        include_node_energy: bool = False,
    ) -> Atoms:
        atoms = structure.atoms.copy()
        atoms.calc = None
        structure_info = dict(atoms.info)
        atoms.info.clear()
        for name in tuple(atoms.arrays):
            if name not in {"numbers", "positions"}:
                del atoms.arrays[name]
        atoms.info.update(
            {
                "atomsledger_structure_id": structure.id,
                "atomsledger_structure_content_hash": (
                    structure.structure_content_hash
                ),
                "atomsledger_structure_created_at": structure.created_at.isoformat(),
                "atomsledger_structure_tags": ",".join(
                    structure.effective_tags
                ),
                "atomsledger_structure_purpose": structure.provenance.purpose,
            }
        )
        # Without an evaluation the frame carries the structure only.
        exported_names: list[str] = []
        if evaluation is not None:
            if evaluation.structure_id != structure.id:
                raise IntegrityError(
                    "Evaluation and structure IDs do not match"
                )

            evaluation_metadata: dict[str, Any] = {
                "atomsledger_evaluation_id": evaluation.id,
                "atomsledger_evaluation_hash": evaluation.content_hash,
                "atomsledger_evaluation_created_at": evaluation.created_at.isoformat(),
                "atomsledger_method_family": evaluation.method.family,
                "atomsledger_method_name": evaluation.method.name,
                "atomsledger_evaluator_label": evaluation.method.name,
                "atomsledger_units": to_plain(evaluation.units),
                "atomsledger_evaluation_tags": ",".join(
                    evaluation.effective_tags
                ),
            }
            optional_method_metadata = {
                "atomsledger_method_version": evaluation.method.version,
                "atomsledger_method_code": evaluation.method.code,
                "atomsledger_method_identifier": evaluation.method.method_identifier,
            }
            evaluation_metadata.update(
                {
                    key: value
                    for key, value in optional_method_metadata.items()
                    if value
                }
            )
            atoms.info.update(evaluation_metadata)

            def replace_array(name: str, value: Any) -> None:
                """Project an evaluation array over any same-named structure array."""
                if name in atoms.arrays:
                    del atoms.arrays[name]
                atoms.new_array(name, np.array(value, copy=True))

            for name, value in evaluation.properties.items():
                exported_names.append(name)
                if name == "energy":
                    scalar = np.asarray(value).reshape(-1)[0].item()
                    atoms.info[energy_label] = scalar
                    continue
                if name == "forces":
                    replace_array(forces_label, value)
                    continue
                if name == "node_energy":
                    if include_node_energy:
                        replace_array(node_energy_label, value)
                    continue
                if isinstance(value, np.ndarray):
                    if value.shape[:1] == (len(atoms),):
                        replace_array(f"eval_{name}", value)
                    else:
                        atoms.info[f"eval_{name}"] = np.array(value, copy=True)
                    continue
                if value is None or isinstance(
                    value, str | int | float | bool
                ):
                    atoms.info[f"eval_{name}"] = value

        # Evaluation labels and export traceability take precedence over source
        # metadata, which remains useful when it does not name an export field.
        atoms.info.update(
            {
                name: value
                for name, value in structure_info.items()
                if name not in atoms.info
            }
        )

        # An empty value would corrupt the extxyz comment line on reading,
        # so structure-only frames leave the key out.
        if exported_names:
            atoms.info["atomsledger_exported_properties"] = ",".join(
                exported_names
            )
        return atoms
