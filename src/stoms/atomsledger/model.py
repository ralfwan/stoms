from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import Any
from uuid import uuid4

import numpy as np
from ase import Atoms

RecordId = str
StructureID = RecordId
StoredQueryID = RecordId
AggregationID = RecordId
JSONValue = Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> RecordId:
    return f"{prefix}_{uuid4().hex}"


def _freeze(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        array = np.array(value, copy=True)
        array.setflags(write=False)
        return array
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return _freeze(dict(value))


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{path} must contain only finite JSON numbers")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            _validate_json_value(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    raise TypeError(
        f"{path} must contain only JSON values; got {type(value).__name__}"
    )


def _validate_identifier(
    value: str | None, path: str, *, required: bool
) -> None:
    if value is None:
        if required:
            raise ValueError(f"{path} is required")
        return
    if not isinstance(value, str):
        raise TypeError(f"{path} must be a string")
    if not value:
        raise ValueError(f"{path} must not be empty")
    if value != value.strip():
        raise ValueError(
            f"{path} must not have leading or trailing whitespace"
        )


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _optional_intersection(
    left: tuple[str, ...] | None,
    right: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if left is None:
        return right
    if right is None:
        return left
    return tuple(sorted(set(left).intersection(right)))


def _choice_intersection(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    if not left:
        return right
    if not right:
        return left
    return tuple(sorted(set(left).intersection(right)))


@dataclass(frozen=True, slots=True)
class Provenance:
    """Human- and machine-readable account of why a record is held.

    ``created_by`` and ``purpose`` are the required minimum provenance.
    ``metadata`` and ``notes`` provide additional per-record audit context.
    Tags are exact, case-sensitive strings. They are deduplicated and sorted at
    construction time, which makes their stored representation deterministic.
    Metadata mappings are restricted to strict JSON values and copied into
    immutable values.
    """

    created_by: str
    purpose: str
    tags: tuple[str, ...] = ()
    notes: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", _ordered_unique(self.tags))
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a JSON object")
        _validate_json_value(self.metadata, "metadata")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class StructureSourceSpec:
    """Immutable description of the process that produced a structure."""

    kind: str
    name: str
    version: str | None = None
    tool: str | None = None
    model_identifier: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(self.kind, "kind", required=True)
        _validate_identifier(self.name, "name", required=True)
        _validate_identifier(self.version, "version", required=False)
        _validate_identifier(self.tool, "tool", required=False)
        _validate_identifier(
            self.model_identifier, "model_identifier", required=False
        )
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a JSON object")
        _validate_json_value(self.parameters, "parameters")
        object.__setattr__(
            self, "parameters", _freeze_mapping(self.parameters)
        )


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """Description of the method that produced an evaluation.

    ``method_identifier`` is the user-defined identity used for ordinary
    evaluator matching. The remaining fields describe the method and
    ``parameters`` stores method configuration used for the evaluation.
    ``model_id`` is accepted as descriptive input, but the current SQLite
    serialization and selector implementation do not preserve or compare it.
    Use ``method_identifier`` and ``parameters`` for durable identity.
    """

    method_identifier: str
    family: str  # e.g. DFT, MLIP, CCSD(T)
    name: str  # e.g. VASP-r2SCAN, MACE-MATPES, ORCA-DLPNO-CCSD(T)
    version: str | None = None
    code: str | None = None
    model_id: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_identifier(
            self.method_identifier, "method_identifier", required=True
        )
        object.__setattr__(
            self, "parameters", _freeze_mapping(self.parameters)
        )


@dataclass(frozen=True, slots=True)
class StructureRecord:
    """Immutable calculator-free structure snapshot and source provenance."""

    id: RecordId
    created_at: datetime
    structure_content_hash: str
    source_spec: StructureSourceSpec
    provenance: Provenance
    _atoms: Atoms = field(repr=False, compare=False)
    _effective_tags: tuple[str, ...] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "_atoms", self._atoms.copy())
        object.__setattr__(
            self,
            "_effective_tags",
            _ordered_unique(
                self.provenance.tags
                if self._effective_tags is None
                else self._effective_tags
            ),
        )

    @property
    def effective_tags(self) -> tuple[str, ...]:
        """Return ingestion and post-ingestion tags together."""
        assert self._effective_tags is not None
        return self._effective_tags

    @property
    def tags(self) -> tuple[str, ...]:
        """Return the effective tags for convenient record inspection."""
        return self.effective_tags

    @property
    def atoms(self) -> Atoms:
        """Return a defensive copy; mutating it cannot change the stored snapshot."""
        return self._atoms.copy()


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """Immutable numerical evaluation associated with one structure."""

    id: RecordId
    structure_id: RecordId
    created_at: datetime
    content_hash: str
    method: MethodSpec
    properties: Mapping[str, Any]
    units: Mapping[str, str]
    provenance: Provenance
    _effective_tags: tuple[str, ...] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "properties", _freeze_mapping(self.properties)
        )
        object.__setattr__(self, "units", _freeze_mapping(self.units))
        object.__setattr__(
            self,
            "_effective_tags",
            _ordered_unique(
                self.provenance.tags
                if self._effective_tags is None
                else self._effective_tags
            ),
        )

    @property
    def effective_tags(self) -> tuple[str, ...]:
        """Return ingestion and post-ingestion tags together."""
        assert self._effective_tags is not None
        return self._effective_tags

    @property
    def tags(self) -> tuple[str, ...]:
        """Return the effective tags for convenient record inspection."""
        return self.effective_tags


@dataclass(frozen=True, slots=True)
class EvaluatorSelector:
    """Select evaluations by the populated fields of one method specification.

    By default, matching uses the required ``method_identifier`` only.
    ``exact_match=True`` instead matches family, name, version, code,
    ``method_identifier``, and parameters. It does not match ``model_id``.
    """

    method: MethodSpec
    exact_match: bool = False

    def matches(self, method: MethodSpec) -> bool:
        expected = self.method
        if not self.exact_match:
            return method.method_identifier == expected.method_identifier
        if (expected.family and method.family != expected.family) or (
            expected.name and method.name != expected.name
        ):
            return False
        for field_name in ("version", "code", "method_identifier"):
            expected_value = getattr(expected, field_name)
            if (
                expected_value is not None
                and getattr(method, field_name) != expected_value
            ):
                return False
        return method.parameters == expected.parameters


@dataclass(frozen=True, slots=True)
class SelectedRecord:
    """One structure and its uniquely selected evaluation."""

    structure: StructureRecord
    evaluation: EvaluationRecord


@dataclass(frozen=True, slots=True)
class NumericalProjection:
    """Aligned numerical values produced by a strict selection."""

    property_name: str
    structure_ids: tuple[RecordId, ...]
    evaluation_ids: tuple[RecordId, ...]
    values: np.ndarray
    unit: str
    query: DatasetQuery

    def __post_init__(self) -> None:
        if len(self.structure_ids) != len(self.evaluation_ids):
            raise ValueError("Projection identities must have the same length")
        values = np.array(self.values, copy=True)
        if not np.issubdtype(values.dtype, np.number):
            raise ValueError("Projection values must be numeric")
        values.setflags(write=False)
        object.__setattr__(self, "structure_ids", tuple(self.structure_ids))
        object.__setattr__(self, "evaluation_ids", tuple(self.evaluation_ids))
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class StrictSelection:
    """Structures paired one-to-one with evaluations by a strict query."""

    query: DatasetQuery
    records: tuple[SelectedRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))

    @property
    def structure_ids(self) -> tuple[RecordId, ...]:
        return tuple(item.structure.id for item in self.records)

    @property
    def evaluation_ids(self) -> tuple[RecordId, ...]:
        return tuple(item.evaluation.id for item in self.records)

    def project(self, property_name: str) -> NumericalProjection:
        """Return one aligned numerical property from every selected record."""
        if not property_name:
            raise ValueError("A projection property name is required")
        arrays: list[np.ndarray] = []
        units: set[str] = set()
        for item in self.records:
            evaluation = item.evaluation
            if property_name not in evaluation.properties:
                raise ValueError(
                    f"Evaluation {evaluation.id} has no property "
                    f"{property_name!r}"
                )
            if property_name not in evaluation.units:
                raise ValueError(
                    f"Evaluation {evaluation.id} has no declared unit for "
                    f"{property_name!r}"
                )
            units.add(evaluation.units[property_name])
            value = np.asarray(evaluation.properties[property_name])
            if not np.issubdtype(value.dtype, np.number):
                raise ValueError(
                    f"Property {property_name!r} must contain numerical values"
                )
            if property_name == "energy" and value.shape == (1,):
                value = value.reshape(())
            arrays.append(value)

        if len(units) > 1:
            raise ValueError(
                f"Projection property {property_name!r} has mixed units: "
                f"{sorted(units)}"
            )
        if not arrays:
            values = np.empty((0,), dtype=float)
        else:
            try:
                values = np.stack(arrays)
            except ValueError as error:
                raise ValueError(
                    f"Projection property {property_name!r} has inconsistent shapes"
                ) from error
        unit = next(iter(units), "")
        return NumericalProjection(
            property_name=property_name,
            structure_ids=self.structure_ids,
            evaluation_ids=self.evaluation_ids,
            values=values,
            unit=unit,
            query=self.query,
        )

    def project_energy(self) -> NumericalProjection:
        """Return the standard total-energy projection."""
        return self.project("energy")


@dataclass(frozen=True, slots=True)
class EvaluatorCatalogEntry:
    """Metadata about one evaluation without its numerical properties."""

    id: RecordId
    created_at: datetime
    method: MethodSpec
    property_names: tuple[str, ...]
    units: Mapping[str, str] = field(default_factory=dict)
    created_by: str = ""
    purpose: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "property_names", tuple(sorted(self.property_names))
        )
        object.__setattr__(self, "units", _freeze_mapping(self.units))
        object.__setattr__(self, "tags", _ordered_unique(self.tags))


@dataclass(frozen=True, slots=True)
class StructureCatalogEntry:
    """Structure metadata and evaluator availability for catalog discovery."""

    id: RecordId
    created_at: datetime
    structure_content_hash: str
    formula: str
    created_by: str
    purpose: str
    tags: tuple[str, ...]
    evaluators: tuple[EvaluatorCatalogEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", _ordered_unique(self.tags))
        object.__setattr__(self, "evaluators", tuple(self.evaluators))

    @property
    def available_property_names(self) -> tuple[str, ...]:
        """Return all property names available from this structure's evaluations."""
        return tuple(
            sorted(
                {
                    name
                    for evaluator in self.evaluators
                    for name in evaluator.property_names
                }
            )
        )


@dataclass(frozen=True, slots=True)
class StructureInput:
    """Input object for batch structure insertion."""

    atoms: Atoms
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class StructureContentMatch:
    """Existing structure content and its immutable ingestion provenance."""

    id: RecordId
    structure_content_hash: str
    provenance: Provenance
    source_spec: StructureSourceSpec | None = None


@dataclass(frozen=True, slots=True)
class StructureContentConflict:
    """One batch item whose content matches different provenance."""

    input_index: int
    matches: tuple[StructureContentMatch, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "matches", tuple(self.matches))


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    """Input object for batch evaluation insertion.

    Standard property units are optional and receive ingestion defaults.
    """

    structure_id: RecordId
    method: MethodSpec
    properties: Mapping[str, Any]
    provenance: Provenance
    units: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrajectoryFrame:
    """References one structure and the evaluations attached to its frame."""

    structure_id: RecordId
    evaluation_ids: tuple[RecordId, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_ids", tuple(self.evaluation_ids))


@dataclass(frozen=True, slots=True)
class TrajectoryRecord:
    """Immutable ordered trajectory made from structure and evaluation IDs."""

    id: RecordId
    created_at: datetime
    kind: str
    frames: tuple[TrajectoryFrame, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", tuple(self.frames))


@dataclass(frozen=True, slots=True)
class StructureQuery:
    """Filter for structures by identity, metadata, tags, and creation time.

    Empty tuple filters impose no restriction. Tag filters operate on effective
    tags, combining ``tags_all`` as a conjunction, ``tags_any`` as a
    disjunction, and ``tags_none`` as an exclusion.
    """

    ids: tuple[RecordId, ...] | None = None
    structure_content_hash: str | None = None
    formula: str | None = None
    tags_all: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    tags_none: tuple[str, ...] = ()
    purpose_contains: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None

    def matches(self, record: StructureRecord) -> bool:
        """Return whether a structure satisfies every configured filter."""
        if self.ids is not None and record.id not in self.ids:
            return False
        if (
            self.structure_content_hash is not None
            and record.structure_content_hash != self.structure_content_hash
        ):
            return False
        if self.formula is not None:
            formula = record.atoms.get_chemical_formula(mode="hill")
            if formula != self.formula:
                return False
        record_tags = set(record.effective_tags)
        if not set(self.tags_all).issubset(record_tags):
            return False
        if self.tags_any and record_tags.isdisjoint(self.tags_any):
            return False
        if self.tags_none and not record_tags.isdisjoint(self.tags_none):
            return False
        if (
            self.purpose_contains is not None
            and self.purpose_contains.casefold()
            not in record.provenance.purpose.casefold()
        ):
            return False
        if (
            self.created_after is not None
            and record.created_at < self.created_after
        ):
            return False
        return not (
            self.created_before is not None
            and record.created_at >= self.created_before
        )


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    """Filter for evaluations by identity, method, properties, tags, and time.

    Empty tuple filters impose no restriction. Method and property filters are
    exact; ``properties_all`` requires every named property to be present.
    Tag filters use the same effective-tag semantics as ``StructureQuery``.
    """

    ids: tuple[RecordId, ...] | None = None
    structure_ids: tuple[RecordId, ...] | None = None
    method_families: tuple[str, ...] = ()
    method_names: tuple[str, ...] = ()
    method_versions: tuple[str, ...] = ()
    method_codes: tuple[str, ...] = ()
    method_identifiers: tuple[str, ...] = ()
    properties_all: tuple[str, ...] = ()
    tags_all: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    tags_none: tuple[str, ...] = ()
    created_after: datetime | None = None
    created_before: datetime | None = None

    def for_structure(self, structure_id: RecordId) -> EvaluationQuery:
        """Return a copy restricted to evaluations for one structure."""
        if (
            self.structure_ids is not None
            and structure_id not in self.structure_ids
        ):
            return replace(self, structure_ids=())
        return replace(self, structure_ids=(structure_id,))

    def intersect(self, other: EvaluationQuery) -> EvaluationQuery:
        """Return the logical intersection of two evaluation filters."""
        if (
            self.tags_any
            and other.tags_any
            and self.tags_any != other.tags_any
        ):
            raise ValueError(
                "Cannot flatten the intersection of two different tags_any filters"
            )

        ids = _optional_intersection(self.ids, other.ids)
        structure_ids = _optional_intersection(
            self.structure_ids, other.structure_ids
        )
        choice_pairs = (
            (self.method_families, other.method_families),
            (self.method_names, other.method_names),
            (self.method_versions, other.method_versions),
            (self.method_codes, other.method_codes),
            (self.method_identifiers, other.method_identifiers),
        )
        choice_results = tuple(
            _choice_intersection(left, right) for left, right in choice_pairs
        )
        impossible = any(
            left and right and not result
            for (left, right), result in zip(
                choice_pairs, choice_results, strict=True
            )
        )

        created_after_values = [
            value
            for value in (self.created_after, other.created_after)
            if value is not None
        ]
        created_before_values = [
            value
            for value in (self.created_before, other.created_before)
            if value is not None
        ]
        created_after = (
            max(created_after_values) if created_after_values else None
        )
        created_before = (
            min(created_before_values) if created_before_values else None
        )
        if (
            created_after is not None
            and created_before is not None
            and created_after >= created_before
        ):
            impossible = True

        return EvaluationQuery(
            ids=() if impossible else ids,
            structure_ids=structure_ids,
            method_families=choice_results[0],
            method_names=choice_results[1],
            method_versions=choice_results[2],
            method_codes=choice_results[3],
            method_identifiers=choice_results[4],
            properties_all=_ordered_unique(
                (*self.properties_all, *other.properties_all)
            ),
            tags_all=_ordered_unique((*self.tags_all, *other.tags_all)),
            tags_any=self.tags_any or other.tags_any,
            tags_none=_ordered_unique((*self.tags_none, *other.tags_none)),
            created_after=created_after,
            created_before=created_before,
        )

    def matches(self, record: EvaluationRecord) -> bool:
        """Return whether an evaluation satisfies every configured filter."""
        if self.ids is not None and record.id not in self.ids:
            return False
        if (
            self.structure_ids is not None
            and record.structure_id not in self.structure_ids
        ):
            return False
        if (
            self.method_families
            and record.method.family not in self.method_families
        ):
            return False
        if self.method_names and record.method.name not in self.method_names:
            return False
        if (
            self.method_versions
            and record.method.version not in self.method_versions
        ):
            return False
        if self.method_codes and record.method.code not in self.method_codes:
            return False
        if (
            self.method_identifiers
            and record.method.method_identifier not in self.method_identifiers
        ):
            return False
        if not set(self.properties_all).issubset(record.properties):
            return False
        record_tags = set(record.effective_tags)
        if not set(self.tags_all).issubset(record_tags):
            return False
        if self.tags_any and record_tags.isdisjoint(self.tags_any):
            return False
        if self.tags_none and not record_tags.isdisjoint(self.tags_none):
            return False
        if (
            self.created_after is not None
            and record.created_at < self.created_after
        ):
            return False
        return not (
            self.created_before is not None
            and record.created_at >= self.created_before
        )


@dataclass(frozen=True, slots=True)
class DatasetQuery:
    """Combine structure criteria with optional evaluation requirements.

    ``require_evaluation`` controls whether stored-query materialization keeps
    structures without matching evaluations. It does not supply the evaluator
    criterion required by ``AtomsLedger.select``.
    """

    structures: StructureQuery = field(default_factory=StructureQuery)
    evaluations: EvaluationQuery | None = None
    require_evaluation: bool = False

    def with_evaluator(self, evaluator: EvaluationQuery) -> DatasetQuery:
        """Return a copy requiring and intersecting the supplied evaluator."""
        evaluations = (
            evaluator
            if self.evaluations is None
            else self.evaluations.intersect(evaluator)
        )
        return replace(self, evaluations=evaluations, require_evaluation=True)


@dataclass(frozen=True, slots=True)
class StoredQuery:
    """Immutable persisted dataset query definition with a nonunique label."""

    id: RecordId
    label: str
    description: str
    query: DatasetQuery
    created_at: datetime
    provenance: Provenance
    hidden_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("A stored query label is required")


@dataclass(frozen=True, slots=True)
class StoredQuerySummary:
    id: StoredQueryID
    label: str
    criteria: DatasetQuery
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AggregationMember:
    """One ordered structure reference with an optional paired evaluation."""

    ordinal: int
    structure_id: StructureID
    evaluation_id: RecordId | None = None


@dataclass(frozen=True, slots=True)
class AggregationMemberInput:
    structure_id: StructureID
    evaluation_id: RecordId | None = None


@dataclass(frozen=True, slots=True)
class Aggregation:
    """Named, immutable ordered structure/evaluation membership.

    A member always identifies a structure and can optionally identify one of
    its evaluations. SQLite validates references and membership consistency.
    """

    id: AggregationID
    name: str
    description: str | None
    created_at: datetime
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    source_stored_query_id: StoredQueryID | None = None
    source_query_snapshot: Mapping[str, JSONValue] | None = None
    external_key: str | None = None
    membership_hash: str = ""
    supersedes_id: AggregationID | None = None
    members: tuple[AggregationMember, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if self.source_query_snapshot is not None:
            object.__setattr__(
                self,
                "source_query_snapshot",
                _freeze_mapping(self.source_query_snapshot),
            )
        object.__setattr__(self, "members", tuple(self.members))


@dataclass(frozen=True, slots=True)
class AggregationSummary:
    """Metadata-only view of an immutable aggregation."""

    id: AggregationID
    name: str
    description: str | None
    created_at: datetime
    metadata: Mapping[str, JSONValue]
    source_stored_query_id: StoredQueryID | None
    external_key: str | None
    membership_hash: str
    supersedes_id: AggregationID | None
    member_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(UTC)


def latest(records: Sequence[EvaluationRecord]) -> EvaluationRecord:
    if not records:
        raise ValueError("No evaluation records supplied")
    return max(records, key=lambda item: (item.created_at, item.id))
