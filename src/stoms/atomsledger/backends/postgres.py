from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from typing import Any

import psycopg
from psycopg import sql
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..exceptions import (
    AggregationConflictError,
    AggregationNotFoundError,
    AggregationValidationError,
    DuplicateRecordError,
    IntegrityError,
    RecordNotFoundError,
    SerializationError,
    StoredQueryInUseError,
    StructureContentConflictError,
)
from ..model import (
    Aggregation,
    AggregationMember,
    AggregationSummary,
    EvaluationQuery,
    EvaluationRecord,
    EvaluatorCatalogEntry,
    RecordId,
    StoredQuery,
    StoredQuerySummary,
    StructureCatalogEntry,
    StructureContentConflict,
    StructureContentMatch,
    StructureQuery,
    StructureRecord,
    TrajectoryFrame,
    TrajectoryRecord,
    utc_now,
)
from ..serialization import (
    aggregation_membership_hash,
    atoms_from_binary_payload,
    atoms_to_binary_payload,
    dataset_query_from_dict,
    dataset_query_to_dict,
    evaluation_content_hash,
    method_content_hash,
    method_from_dict,
    method_to_dict,
    properties_from_binary_payload,
    properties_to_binary_payload,
    provenance_from_dict,
    provenance_to_dict,
    structure_content_hash,
    structure_source_content_hash,
    structure_source_from_dict,
    structure_source_to_dict,
    to_plain,
    trajectory_frames_to_dict,
)

SCHEMA_NAME = "atomsledger"
SCHEMA_VERSION = 8


class PostgresRepository:
    """PostgreSQL storage for current core ledger records.

    Connections are deliberately short-lived so callers can use a normal DSN
    with an external pooler. Each public batch write is one transaction.
    """

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = SCHEMA_NAME,
        initialize: bool = True,
    ) -> None:
        self.dsn = dsn
        self.schema = schema
        if initialize:
            self.initialize()
        else:
            self.validate()

    def _table(self, name: str) -> sql.Identifier:
        return sql.Identifier(self.schema, name)

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def validate(self) -> None:
        """Verify that the target schema is a current atomsledger store."""
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT key, value FROM {}").format(
                        self._table("schema_info")
                    )
                )
                info = {row["key"]: row["value"] for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = %s",
                    (self.schema,),
                )
                columns: dict[str, set[str]] = {}
                for row in cursor.fetchall():
                    columns.setdefault(row["table_name"], set()).add(
                        row["column_name"]
                    )
        except psycopg.DatabaseError as error:
            raise IntegrityError(
                "PostgreSQL schema is not a readable atomsledger store"
            ) from error
        if info.get("schema_name") != SCHEMA_NAME:
            raise IntegrityError(
                "PostgreSQL schema is not an atomsledger store"
            )
        if int(info.get("schema_version", -1)) != SCHEMA_VERSION:
            raise IntegrityError(
                "Unsupported atomsledger PostgreSQL schema version"
            )
        required_columns = {
            "structure_source_specs": {"id", "specification"},
            "structures": {
                "id",
                "created_at",
                "structure_content_hash",
                "formula",
                "atoms_metadata",
                "atoms_payload",
                "source_spec_id",
                "provenance",
                "purpose",
            },
            "structure_tags": {"structure_id", "tag"},
            "method_specs": {"id", "specification"},
            "evaluations": {
                "id",
                "structure_id",
                "created_at",
                "content_hash",
                "method_family",
                "method_name",
                "method_version",
                "method_code",
                "method_identifier",
                "method_id",
                "properties_metadata",
                "properties_payload",
                "units",
                "provenance",
                "purpose",
            },
            "evaluation_tags": {"evaluation_id", "tag"},
            "evaluation_properties": {"evaluation_id", "name"},
            "trajectories": {
                "id",
                "created_at",
                "kind",
                "frames",
                "provenance",
            },
            "stored_queries": {
                "id",
                "label",
                "description",
                "query",
                "created_at",
                "hidden_at",
                "provenance",
            },
            "aggregations": {
                "id",
                "name",
                "description",
                "created_at",
                "metadata",
                "source_stored_query_id",
                "source_query_snapshot",
                "external_key",
                "membership_hash",
                "supersedes_id",
            },
            "aggregation_members": {
                "aggregation_id",
                "ordinal",
                "structure_id",
                "evaluation_id",
            },
        }
        if any(
            not required.issubset(columns.get(table, set()))
            for table, required in required_columns.items()
        ):
            raise IntegrityError(
                "Unsupported atomsledger PostgreSQL schema layout"
            )

    def initialize(self) -> None:
        schema = sql.Identifier(self.schema)
        statements = (
            """CREATE TABLE IF NOT EXISTS {} (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, specification JSONB NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL,
                structure_content_hash TEXT NOT NULL, formula TEXT NOT NULL,
                atoms_metadata JSONB NOT NULL, atoms_payload BYTEA NOT NULL,
                source_spec_id TEXT NOT NULL REFERENCES {} (id),
                provenance JSONB NOT NULL, purpose TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                structure_id TEXT NOT NULL REFERENCES {} (id), tag TEXT NOT NULL,
                PRIMARY KEY (structure_id, tag))""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, specification JSONB NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY,
                structure_id TEXT NOT NULL REFERENCES {} (id),
                created_at TIMESTAMPTZ NOT NULL, content_hash TEXT NOT NULL,
                method_family TEXT NOT NULL, method_name TEXT NOT NULL,
                method_version TEXT, method_code TEXT,
                method_identifier TEXT NOT NULL,
                method_id TEXT NOT NULL REFERENCES {} (id),
                properties_metadata JSONB NOT NULL, properties_payload BYTEA NOT NULL,
                units JSONB NOT NULL, provenance JSONB NOT NULL, purpose TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                evaluation_id TEXT NOT NULL REFERENCES {} (id), tag TEXT NOT NULL,
                PRIMARY KEY (evaluation_id, tag))""",
            """CREATE TABLE IF NOT EXISTS {} (
                evaluation_id TEXT NOT NULL REFERENCES {} (id), name TEXT NOT NULL,
                PRIMARY KEY (evaluation_id, name))""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL,
                kind TEXT NOT NULL, frames JSONB NOT NULL, provenance JSONB NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, label TEXT NOT NULL, description TEXT NOT NULL,
                query JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL,
                hidden_at TIMESTAMPTZ, provenance JSONB NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS {} (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                created_at TIMESTAMPTZ NOT NULL, metadata JSONB NOT NULL,
                source_stored_query_id TEXT REFERENCES {} (id) ON DELETE SET NULL,
                source_query_snapshot JSONB, external_key TEXT UNIQUE,
                membership_hash TEXT NOT NULL,
                supersedes_id TEXT REFERENCES {} (id) ON DELETE RESTRICT)""",
            """CREATE TABLE IF NOT EXISTS {} (
                aggregation_id TEXT NOT NULL REFERENCES {} (id) ON DELETE RESTRICT,
                ordinal INTEGER NOT NULL, structure_id TEXT NOT NULL REFERENCES {} (id) ON DELETE RESTRICT,
                evaluation_id TEXT REFERENCES {} (id) ON DELETE RESTRICT,
                PRIMARY KEY (aggregation_id, ordinal),
                UNIQUE (aggregation_id, structure_id, evaluation_id))""",
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema)
            )
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"atomsledger-schema:{self.schema}",),
            )
            cursor.execute(
                sql.SQL(statements[0]).format(self._table("schema_info"))
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {} (key, value) VALUES "
                    "('schema_name', %s), ('schema_version', %s) "
                    "ON CONFLICT (key) DO NOTHING"
                ).format(self._table("schema_info")),
                (SCHEMA_NAME, str(SCHEMA_VERSION)),
            )
            cursor.execute(
                sql.SQL(statements[1]).format(
                    self._table("structure_source_specs")
                )
            )
            cursor.execute(
                sql.SQL(statements[2]).format(
                    self._table("structures"),
                    self._table("structure_source_specs"),
                )
            )
            cursor.execute(
                sql.SQL(statements[3]).format(
                    self._table("structure_tags"), self._table("structures")
                )
            )
            cursor.execute(
                sql.SQL(statements[4]).format(self._table("method_specs"))
            )
            cursor.execute(
                sql.SQL(statements[5]).format(
                    self._table("evaluations"),
                    self._table("structures"),
                    self._table("method_specs"),
                )
            )
            cursor.execute(
                sql.SQL(statements[6]).format(
                    self._table("evaluation_tags"), self._table("evaluations")
                )
            )
            cursor.execute(
                sql.SQL(statements[7]).format(
                    self._table("evaluation_properties"),
                    self._table("evaluations"),
                )
            )
            cursor.execute(
                sql.SQL(statements[8]).format(self._table("trajectories"))
            )
            cursor.execute(
                sql.SQL(statements[9]).format(self._table("stored_queries"))
            )
            cursor.execute(
                sql.SQL(statements[10]).format(
                    self._table("aggregations"),
                    self._table("stored_queries"),
                    self._table("aggregations"),
                )
            )
            cursor.execute(
                sql.SQL(statements[11]).format(
                    self._table("aggregation_members"),
                    self._table("aggregations"),
                    self._table("structures"),
                    self._table("evaluations"),
                )
            )
            for name, table, columns in (
                (
                    "structures_content_hash_idx",
                    "structures",
                    "structure_content_hash",
                ),
                ("structures_formula_idx", "structures", "formula"),
                ("structures_created_at_idx", "structures", "created_at"),
                (
                    "structure_tags_tag_idx",
                    "structure_tags",
                    "tag, structure_id",
                ),
                (
                    "evaluations_structure_id_idx",
                    "evaluations",
                    "structure_id",
                ),
                (
                    "evaluations_method_idx",
                    "evaluations",
                    "method_name, method_version, method_identifier",
                ),
                ("evaluations_family_idx", "evaluations", "method_family"),
                ("evaluations_created_at_idx", "evaluations", "created_at"),
                (
                    "evaluation_tags_tag_idx",
                    "evaluation_tags",
                    "tag, evaluation_id",
                ),
                (
                    "evaluation_properties_name_idx",
                    "evaluation_properties",
                    "name, evaluation_id",
                ),
                ("trajectories_kind_idx", "trajectories", "kind, created_at"),
                (
                    "stored_queries_created_at_idx",
                    "stored_queries",
                    "created_at, id",
                ),
                (
                    "aggregations_external_key_idx",
                    "aggregations",
                    "external_key",
                ),
                (
                    "aggregations_name_idx",
                    "aggregations",
                    "name, created_at, id",
                ),
                (
                    "aggregations_source_query_idx",
                    "aggregations",
                    "source_stored_query_id",
                ),
                (
                    "aggregation_members_aggregation_idx",
                    "aggregation_members",
                    "aggregation_id, ordinal",
                ),
                (
                    "aggregation_members_structure_idx",
                    "aggregation_members",
                    "structure_id, aggregation_id",
                ),
            ):
                cursor.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
                        sql.Identifier(name),
                        self._table(table),
                        sql.SQL(columns),
                    )
                )
        self.validate()

    @staticmethod
    def _validate_structure(record: StructureRecord) -> None:
        if (
            structure_content_hash(record.atoms)
            != record.structure_content_hash
        ):
            raise IntegrityError(
                f"Structure content hash does not match payload: {record.id}"
            )

    @staticmethod
    def _validate_evaluation(record: EvaluationRecord) -> None:
        if (
            evaluation_content_hash(
                record.structure_id,
                record.method,
                record.properties,
                record.units,
            )
            != record.content_hash
        ):
            raise IntegrityError(
                f"Evaluation content hash does not match payload: {record.id}"
            )

    def _structure_rows(
        self, records: Sequence[StructureRecord]
    ) -> tuple[
        list[tuple[Any, ...]], list[tuple[Any, ...]], list[tuple[str, str]]
    ]:
        rows: list[tuple[Any, ...]] = []
        source_rows: dict[str, tuple[Any, ...]] = {}
        tag_rows: list[tuple[str, str]] = []
        for record in records:
            self._validate_structure(record)
            metadata, payload = atoms_to_binary_payload(record.atoms)
            source_id = structure_source_content_hash(record.source_spec)
            source_rows[source_id] = (
                source_id,
                Jsonb(structure_source_to_dict(record.source_spec)),
            )
            rows.append(
                (
                    record.id,
                    record.created_at,
                    record.structure_content_hash,
                    record.atoms.get_chemical_formula(mode="hill"),
                    Jsonb(metadata),
                    payload,
                    source_id,
                    Jsonb(provenance_to_dict(record.provenance)),
                    record.provenance.purpose,
                )
            )
            tag_rows.extend((record.id, tag) for tag in record.provenance.tags)
        return rows, list(source_rows.values()), tag_rows

    def _insert_structures(
        self, cursor: psycopg.Cursor[Any], records: Sequence[StructureRecord]
    ) -> None:
        rows, source_rows, tag_rows = self._structure_rows(records)
        cursor.executemany(
            sql.SQL(
                "INSERT INTO {} (id, specification) VALUES (%s, %s) "
                "ON CONFLICT (id) DO NOTHING"
            ).format(self._table("structure_source_specs")),
            source_rows,
        )
        cursor.executemany(
            sql.SQL(
                "INSERT INTO {} (id, created_at, structure_content_hash, formula, "
                "atoms_metadata, atoms_payload, source_spec_id, provenance, purpose) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            ).format(self._table("structures")),
            rows,
        )
        cursor.executemany(
            sql.SQL(
                "INSERT INTO {} (structure_id, tag) VALUES (%s, %s)"
            ).format(self._table("structure_tags")),
            tag_rows,
        )

    def put_structure(self, record: StructureRecord) -> None:
        self.put_structures((record,))

    def put_structures(self, records: Sequence[StructureRecord]) -> None:
        if not records:
            return
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._insert_structures(cursor, records)
        except UniqueViolation as error:
            raise DuplicateRecordError(
                "Structure record already exists"
            ) from error

    def put_structures_deduplicating(
        self, records: Sequence[StructureRecord]
    ) -> Sequence[StructureRecord]:
        return self.put_structures_content_aware(records)

    def put_structures_content_aware(
        self,
        records: Sequence[StructureRecord],
        *,
        allow_equivalent_atoms: bool = False,
    ) -> Sequence[StructureRecord]:
        if not records:
            return ()
        for record in records:
            self._validate_structure(record)
        persisted: list[StructureRecord] = []
        planned: dict[str, list[StructureRecord]] = {}
        known: dict[str, list[StructureRecord]] = {}
        conflicts: list[StructureContentConflict] = []
        to_write: list[StructureRecord] = []
        statement = self._structure_select("s.structure_content_hash = %s")
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                for content_hash in sorted(
                    {r.structure_content_hash for r in records}
                ):
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (content_hash,),
                    )
                for index, record in enumerate(records):
                    candidates = known.get(record.structure_content_hash)
                    if candidates is None:
                        cursor.execute(
                            statement, (record.structure_content_hash,)
                        )
                        candidates = [
                            self._structure_from_row(row)
                            for row in cursor.fetchall()
                        ]
                        known[record.structure_content_hash] = candidates
                    exact = next(
                        (
                            candidate
                            for candidate in candidates
                            if candidate.source_spec == record.source_spec
                            and candidate.provenance == record.provenance
                        ),
                        None,
                    )
                    if exact is not None:
                        persisted.append(exact)
                        continue
                    if candidates and not allow_equivalent_atoms:
                        conflicts.append(
                            StructureContentConflict(
                                index,
                                tuple(
                                    StructureContentMatch(
                                        candidate.id,
                                        candidate.structure_content_hash,
                                        candidate.provenance,
                                        candidate.source_spec,
                                    )
                                    for candidate in candidates
                                ),
                            )
                        )
                        continue
                    planned_candidates = planned.setdefault(
                        record.structure_content_hash, []
                    )
                    exact = next(
                        (
                            candidate
                            for candidate in planned_candidates
                            if candidate.source_spec == record.source_spec
                            and candidate.provenance == record.provenance
                        ),
                        None,
                    )
                    if exact is not None:
                        persisted.append(exact)
                    elif planned_candidates and not allow_equivalent_atoms:
                        conflicts.append(StructureContentConflict(index))
                    else:
                        planned_candidates.append(record)
                        to_write.append(record)
                        persisted.append(record)
                if conflicts:
                    raise StructureContentConflictError(tuple(conflicts))
                self._insert_structures(cursor, to_write)
        except UniqueViolation as error:
            raise DuplicateRecordError(
                "Structure record already exists"
            ) from error
        return tuple(persisted)

    def _structure_select(
        self, condition: sql.Composable | str | None = None
    ) -> sql.Composed:
        if condition is None:
            condition = sql.SQL("TRUE")
        elif isinstance(condition, str):
            condition = sql.SQL(condition)
        return sql.SQL(
            "SELECT s.*, ss.specification AS source_specification, "
            "COALESCE(ARRAY(SELECT tag FROM {} st WHERE st.structure_id = s.id), "
            "ARRAY[]::text[]) AS association_tags FROM {} s JOIN {} ss "
            "ON ss.id = s.source_spec_id WHERE {}"
        ).format(
            self._table("structure_tags"),
            self._table("structures"),
            self._table("structure_source_specs"),
            condition,
        )

    def _effective_tag_condition(
        self,
        *,
        association_table: str,
        association_id: str,
        record_alias: str,
        tag_operator: str,
        negate: bool = False,
    ) -> sql.Composed:
        condition = sql.SQL(
            "EXISTS (SELECT 1 FROM {} tags WHERE tags.{} = {}.id "
            "AND tags.tag {}) OR EXISTS (SELECT 1 FROM "
            "jsonb_array_elements_text(COALESCE({}.provenance -> 'tags', "
            "'[]'::jsonb)) provenance_tag WHERE provenance_tag {})"
        ).format(
            self._table(association_table),
            sql.Identifier(association_id),
            sql.Identifier(record_alias),
            sql.SQL(tag_operator),
            sql.Identifier(record_alias),
            sql.SQL(tag_operator),
        )
        return sql.SQL("NOT ({})").format(condition) if negate else condition

    def _structure_query_conditions(
        self, query: StructureQuery
    ) -> tuple[list[sql.Composable], list[Any]]:
        conditions: list[sql.Composable] = []
        parameters: list[Any] = []
        if query.ids is not None:
            conditions.append(
                sql.SQL("FALSE")
                if not query.ids
                else sql.SQL("s.id = ANY(%s)")
            )
            if query.ids:
                parameters.append(list(query.ids))
        for value, field in (
            (query.structure_content_hash, "structure_content_hash"),
            (query.formula, "formula"),
        ):
            if value is not None:
                conditions.append(sql.SQL(f"s.{field} = %s"))
                parameters.append(value)
        for value, operator in (
            (query.created_after, ">="),
            (query.created_before, "<"),
        ):
            if value is not None:
                conditions.append(sql.SQL(f"s.created_at {operator} %s"))
                parameters.append(value)
        for tag in query.tags_all:
            conditions.append(
                self._effective_tag_condition(
                    association_table="structure_tags",
                    association_id="structure_id",
                    record_alias="s",
                    tag_operator="= %s",
                )
            )
            parameters.extend((tag, tag))
        if query.tags_any:
            conditions.append(
                self._effective_tag_condition(
                    association_table="structure_tags",
                    association_id="structure_id",
                    record_alias="s",
                    tag_operator="= ANY(%s)",
                )
            )
            parameters.extend((list(query.tags_any), list(query.tags_any)))
        for tag in query.tags_none:
            conditions.append(
                self._effective_tag_condition(
                    association_table="structure_tags",
                    association_id="structure_id",
                    record_alias="s",
                    tag_operator="= %s",
                    negate=True,
                )
            )
            parameters.extend((tag, tag))
        return conditions, parameters

    @staticmethod
    def _structure_from_row(row: dict[str, Any]) -> StructureRecord:
        source_spec = structure_source_from_dict(row["source_specification"])
        if structure_source_content_hash(source_spec) != row["source_spec_id"]:
            raise IntegrityError(
                f"Structure source hash verification failed: {row['id']}"
            )
        provenance = provenance_from_dict(row["provenance"])
        record = StructureRecord(
            id=row["id"],
            created_at=row["created_at"],
            structure_content_hash=row["structure_content_hash"],
            source_spec=source_spec,
            provenance=provenance,
            _atoms=atoms_from_binary_payload(
                row["atoms_metadata"], bytes(row["atoms_payload"])
            ),
            _effective_tags=tuple(
                sorted(set(provenance.tags).union(row["association_tags"]))
            ),
        )
        if (
            structure_content_hash(record.atoms)
            != record.structure_content_hash
        ):
            raise IntegrityError(
                f"Structure hash verification failed: {record.id}"
            )
        return record

    def get_structure(self, record_id: RecordId) -> StructureRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._structure_select("s.id = %s"), (record_id,))
            row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._structure_from_row(row)

    def iter_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureRecord]:
        query = query or StructureQuery()
        conditions, parameters = self._structure_query_conditions(query)
        condition = (
            sql.SQL(" AND ").join(conditions)
            if conditions
            else sql.SQL("TRUE")
        )
        statement = self._structure_select(condition) + sql.SQL(
            " ORDER BY s.created_at, s.id"
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            records = [
                self._structure_from_row(row) for row in cursor.fetchall()
            ]
        return (record for record in records if query.matches(record))

    def catalog_structures(
        self, query: StructureQuery | None = None
    ) -> tuple[StructureCatalogEntry, ...]:
        return tuple(self.iter_catalog_structures(query))

    def iter_catalog_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureCatalogEntry]:
        """Yield metadata and evaluator availability without reading payload blobs."""
        query = query or StructureQuery()
        conditions, parameters = self._structure_query_conditions(query)
        condition = (
            sql.SQL(" AND ").join(conditions)
            if conditions
            else sql.SQL("TRUE")
        )
        statement = sql.SQL(
            "SELECT s.id, s.created_at, s.structure_content_hash, s.formula, "
            "s.provenance, s.purpose, COALESCE(ARRAY(SELECT tag FROM {} st "
            "WHERE st.structure_id = s.id), ARRAY[]::text[]) AS association_tags, "
            "e.id AS evaluation_id, e.created_at AS evaluation_created_at, "
            "ms.specification AS method_specification, e.units, "
            "e.provenance AS evaluation_provenance, COALESCE(ARRAY(SELECT tag "
            "FROM {} et WHERE et.evaluation_id = e.id), ARRAY[]::text[]) "
            "AS evaluation_tags, COALESCE(ARRAY(SELECT name FROM {} ep "
            "WHERE ep.evaluation_id = e.id), ARRAY[]::text[]) AS property_names "
            "FROM {} s LEFT JOIN {} e ON e.structure_id = s.id "
            "LEFT JOIN {} ms ON ms.id = e.method_id WHERE {} "
            "ORDER BY s.created_at, s.id, e.created_at, e.id"
        ).format(
            self._table("structure_tags"),
            self._table("evaluation_tags"),
            self._table("evaluation_properties"),
            self._table("structures"),
            self._table("evaluations"),
            self._table("method_specs"),
            condition,
        )

        def entries() -> Iterator[StructureCatalogEntry]:
            current_id: str | None = None
            current_entry: StructureCatalogEntry | None = None
            evaluators: list[EvaluatorCatalogEntry] = []
            needle = (
                query.purpose_contains.casefold()
                if query.purpose_contains is not None
                else None
            )
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                for row in cursor:
                    if (
                        needle is not None
                        and needle not in row["purpose"].casefold()
                    ):
                        continue
                    if row["id"] != current_id:
                        if current_entry is not None:
                            yield current_entry
                        provenance = provenance_from_dict(row["provenance"])
                        current_id = row["id"]
                        evaluators = []
                        current_entry = StructureCatalogEntry(
                            id=row["id"],
                            created_at=row["created_at"],
                            structure_content_hash=row[
                                "structure_content_hash"
                            ],
                            formula=row["formula"],
                            created_by=provenance.created_by,
                            purpose=provenance.purpose,
                            tags=tuple(
                                sorted(
                                    set(provenance.tags).union(
                                        row["association_tags"]
                                    )
                                )
                            ),
                        )
                    if row["evaluation_id"] is not None:
                        provenance = provenance_from_dict(
                            row["evaluation_provenance"]
                        )
                        evaluators.append(
                            EvaluatorCatalogEntry(
                                id=row["evaluation_id"],
                                created_at=row["evaluation_created_at"],
                                method=method_from_dict(
                                    row["method_specification"]
                                ),
                                property_names=tuple(row["property_names"]),
                                units=row["units"],
                                created_by=provenance.created_by,
                                purpose=provenance.purpose,
                                tags=tuple(
                                    sorted(
                                        set(provenance.tags).union(
                                            row["evaluation_tags"]
                                        )
                                    )
                                ),
                            )
                        )
                    if current_entry is not None:
                        current_entry = replace(
                            current_entry, evaluators=tuple(evaluators)
                        )
            if current_entry is not None:
                yield current_entry

        return entries()

    def put_evaluation(self, record: EvaluationRecord) -> None:
        self.put_evaluations((record,))

    def put_evaluations(self, records: Sequence[EvaluationRecord]) -> None:
        if not records:
            return
        methods: dict[str, tuple[Any, ...]] = {}
        rows: list[tuple[Any, ...]] = []
        tag_rows: list[tuple[str, str]] = []
        property_rows: list[tuple[str, str]] = []
        for record in records:
            self._validate_evaluation(record)
            metadata, payload = properties_to_binary_payload(record.properties)
            method_id = method_content_hash(record.method)
            methods[method_id] = (
                method_id,
                Jsonb(method_to_dict(record.method)),
            )
            rows.append(
                (
                    record.id,
                    record.structure_id,
                    record.created_at,
                    record.content_hash,
                    record.method.family,
                    record.method.name,
                    record.method.version,
                    record.method.code,
                    record.method.method_identifier,
                    method_id,
                    Jsonb(metadata),
                    payload,
                    Jsonb(dict(record.units)),
                    Jsonb(provenance_to_dict(record.provenance)),
                    record.provenance.purpose,
                )
            )
            tag_rows.extend((record.id, tag) for tag in record.provenance.tags)
            property_rows.extend(
                (record.id, name) for name in record.properties
            )
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (id, specification) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING"
                    ).format(self._table("method_specs")),
                    methods.values(),
                )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (id, structure_id, created_at, content_hash, method_family, method_name, method_version, method_code, method_identifier, method_id, properties_metadata, properties_payload, units, provenance, purpose) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ).format(self._table("evaluations")),
                    rows,
                )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (evaluation_id, tag) VALUES (%s, %s)"
                    ).format(self._table("evaluation_tags")),
                    tag_rows,
                )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (evaluation_id, name) VALUES (%s, %s)"
                    ).format(self._table("evaluation_properties")),
                    property_rows,
                )
        except ForeignKeyViolation as error:
            raise IntegrityError(
                "Evaluation references an unknown structure"
            ) from error
        except UniqueViolation as error:
            raise DuplicateRecordError(
                "Evaluation record already exists"
            ) from error

    def _evaluation_select(
        self, condition: sql.Composable | str | None = None
    ) -> sql.Composed:
        if condition is None:
            condition = sql.SQL("TRUE")
        elif isinstance(condition, str):
            condition = sql.SQL(condition)
        return sql.SQL(
            "SELECT e.*, ms.specification AS method_specification, COALESCE(ARRAY(SELECT tag FROM {} et WHERE et.evaluation_id = e.id), ARRAY[]::text[]) AS association_tags FROM {} e JOIN {} ms ON ms.id = e.method_id WHERE {}"
        ).format(
            self._table("evaluation_tags"),
            self._table("evaluations"),
            self._table("method_specs"),
            condition,
        )

    @staticmethod
    def _evaluation_from_row(row: dict[str, Any]) -> EvaluationRecord:
        provenance = provenance_from_dict(row["provenance"])
        record = EvaluationRecord(
            id=row["id"],
            structure_id=row["structure_id"],
            created_at=row["created_at"],
            content_hash=row["content_hash"],
            method=method_from_dict(row["method_specification"]),
            properties=properties_from_binary_payload(
                row["properties_metadata"], bytes(row["properties_payload"])
            ),
            units=row["units"],
            provenance=provenance,
            _effective_tags=tuple(
                sorted(set(provenance.tags).union(row["association_tags"]))
            ),
        )
        if (
            evaluation_content_hash(
                record.structure_id,
                record.method,
                record.properties,
                record.units,
            )
            != record.content_hash
        ):
            raise IntegrityError(
                f"Evaluation hash verification failed: {record.id}"
            )
        return record

    def get_evaluation(self, record_id: RecordId) -> EvaluationRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._evaluation_select("e.id = %s"), (record_id,))
            row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._evaluation_from_row(row)

    def list_method_identifiers(self) -> Iterable[str]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT DISTINCT method_identifier FROM {} ORDER BY method_identifier"
                ).format(self._table("evaluations"))
            )
            return tuple(row["method_identifier"] for row in cursor.fetchall())

    def iter_evaluations(
        self, query: EvaluationQuery | None = None
    ) -> Iterable[EvaluationRecord]:
        query = query or EvaluationQuery()
        conditions: list[sql.Composable] = []
        parameters: list[Any] = []
        for values, field in (
            (query.ids, "id"),
            (query.structure_ids, "structure_id"),
        ):
            if values is not None:
                conditions.append(
                    sql.SQL("FALSE")
                    if not values
                    else sql.SQL(f"e.{field} = ANY(%s)")
                )
                if values:
                    parameters.append(list(values))
        for values, field in (
            (query.method_families, "method_family"),
            (query.method_names, "method_name"),
            (query.method_versions, "method_version"),
            (query.method_codes, "method_code"),
            (query.method_identifiers, "method_identifier"),
        ):
            if values:
                conditions.append(sql.SQL(f"e.{field} = ANY(%s)"))
                parameters.append(list(values))
        for name in query.properties_all:
            conditions.append(
                sql.SQL(
                    "EXISTS (SELECT 1 FROM {} ep WHERE ep.evaluation_id = e.id AND ep.name = %s)"
                ).format(self._table("evaluation_properties"))
            )
            parameters.append(name)
        for tag in query.tags_all:
            conditions.append(
                self._effective_tag_condition(
                    association_table="evaluation_tags",
                    association_id="evaluation_id",
                    record_alias="e",
                    tag_operator="= %s",
                )
            )
            parameters.extend((tag, tag))
        if query.tags_any:
            conditions.append(
                self._effective_tag_condition(
                    association_table="evaluation_tags",
                    association_id="evaluation_id",
                    record_alias="e",
                    tag_operator="= ANY(%s)",
                )
            )
            parameters.extend((list(query.tags_any), list(query.tags_any)))
        for tag in query.tags_none:
            conditions.append(
                self._effective_tag_condition(
                    association_table="evaluation_tags",
                    association_id="evaluation_id",
                    record_alias="e",
                    tag_operator="= %s",
                    negate=True,
                )
            )
            parameters.extend((tag, tag))
        for value, operator in (
            (query.created_after, ">="),
            (query.created_before, "<"),
        ):
            if value is not None:
                conditions.append(sql.SQL(f"e.created_at {operator} %s"))
                parameters.append(value)
        condition = (
            sql.SQL(" AND ").join(conditions)
            if conditions
            else sql.SQL("TRUE")
        )
        statement = self._evaluation_select(condition) + sql.SQL(
            " ORDER BY e.created_at, e.id"
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            records = [
                self._evaluation_from_row(row) for row in cursor.fetchall()
            ]
        return (record for record in records if query.matches(record))

    @staticmethod
    def _tag_target(record_id: RecordId) -> tuple[str, str, str]:
        if not isinstance(record_id, str):
            raise TypeError("Record IDs must be strings")
        if record_id.startswith("str_"):
            return "structures", "structure_tags", "structure_id"
        if record_id.startswith("eval_"):
            return "evaluations", "evaluation_tags", "evaluation_id"
        raise TypeError(
            "Post-ingestion tags support structure (str_) and "
            "evaluation (eval_) records only"
        )

    @staticmethod
    def _validated_tags(tags: Iterable[str]) -> tuple[str, ...]:
        if isinstance(tags, str):
            raise TypeError(
                "Tags must be an iterable of strings, not a string"
            )
        try:
            values = tuple(tags)
        except TypeError as error:
            raise TypeError("Tags must be an iterable of strings") from error
        for tag in values:
            if not isinstance(tag, str):
                raise TypeError("Tags must be strings")
            if not tag or tag.strip() != tag:
                raise ValueError(
                    "Tags must be non-empty and have no leading or trailing whitespace"
                )
        return tuple(sorted(set(values)))

    def get_post_ingestion_tags(self, record_id: RecordId) -> frozenset[str]:
        table, association_table, association_id = self._tag_target(record_id)
        statement = sql.SQL(
            "SELECT tag FROM {} tags WHERE tags.{} = %s AND NOT EXISTS "
            "(SELECT 1 FROM {} records, jsonb_array_elements_text("
            "COALESCE(records.provenance -> 'tags', '[]'::jsonb)) provenance_tag "
            "WHERE records.id = %s AND provenance_tag = tags.tag)"
        ).format(
            self._table(association_table),
            sql.Identifier(association_id),
            self._table(table),
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, (record_id, record_id))
            tags = cursor.fetchall()
            if not tags:
                cursor.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE id = %s").format(
                        self._table(table)
                    ),
                    (record_id,),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFoundError(record_id)
        return frozenset(row["tag"] for row in tags)

    def add_tags_many(
        self, records: Mapping[RecordId, Iterable[str]]
    ) -> dict[RecordId, frozenset[str]]:
        prepared: dict[RecordId, tuple[str, ...]] = {}
        targets: dict[RecordId, tuple[str, str, str]] = {}
        for record_id, tags in records.items():
            targets[record_id] = self._tag_target(record_id)
            prepared[record_id] = self._validated_tags(tags)
        if not prepared:
            return {}
        with self._connect() as connection, connection.cursor() as cursor:
            for record_id, (table, _, _) in targets.items():
                cursor.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE id = %s").format(
                        self._table(table)
                    ),
                    (record_id,),
                )
                if cursor.fetchone() is None:
                    raise RecordNotFoundError(record_id)
            for record_id, tags in prepared.items():
                _, association_table, association_id = targets[record_id]
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} ({}, tag) VALUES (%s, %s) "
                        "ON CONFLICT DO NOTHING"
                    ).format(
                        self._table(association_table),
                        sql.Identifier(association_id),
                    ),
                    [(record_id, tag) for tag in tags],
                )
        return {record_id: self.get_tags(record_id) for record_id in prepared}

    def get_tags(self, record_id: RecordId) -> frozenset[str]:
        table, _, _ = self._tag_target(record_id)
        if table == "structures":
            return frozenset(self.get_structure(record_id).effective_tags)
        return frozenset(self.get_evaluation(record_id).effective_tags)

    def put_trajectory(self, record: TrajectoryRecord) -> None:
        self.put_trajectories((record,))

    def put_trajectories(self, records: Sequence[TrajectoryRecord]) -> None:
        if not records:
            return
        structure_ids = {
            frame.structure_id for record in records for frame in record.frames
        }
        evaluation_ids = {
            evaluation_id
            for record in records
            for frame in record.frames
            for evaluation_id in frame.evaluation_ids
        }
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT id FROM {} WHERE id = ANY(%s)").format(
                        self._table("structures")
                    ),
                    (list(structure_ids),),
                )
                known_structures = {row["id"] for row in cursor.fetchall()}
                if known_structures != structure_ids:
                    raise IntegrityError(
                        f"Trajectory references unknown structures: {sorted(structure_ids - known_structures)}"
                    )
                cursor.execute(
                    sql.SQL(
                        "SELECT id, structure_id FROM {} WHERE id = ANY(%s)"
                    ).format(self._table("evaluations")),
                    (list(evaluation_ids),),
                )
                evaluation_structures = {
                    row["id"]: row["structure_id"] for row in cursor.fetchall()
                }
                if set(evaluation_structures) != evaluation_ids:
                    raise IntegrityError(
                        f"Trajectory references unknown evaluations: {sorted(evaluation_ids - set(evaluation_structures))}"
                    )
                for record in records:
                    for frame in record.frames:
                        if any(
                            evaluation_structures[evaluation_id]
                            != frame.structure_id
                            for evaluation_id in frame.evaluation_ids
                        ):
                            raise IntegrityError(
                                "Trajectory evaluation does not belong to its structure"
                            )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (id, created_at, kind, frames, provenance) VALUES (%s, %s, %s, %s, %s)"
                    ).format(self._table("trajectories")),
                    [
                        (
                            record.id,
                            record.created_at,
                            record.kind,
                            Jsonb(trajectory_frames_to_dict(record.frames)),
                            Jsonb(provenance_to_dict(record.provenance)),
                        )
                        for record in records
                    ],
                )
        except UniqueViolation as error:
            raise DuplicateRecordError(
                "Trajectory record already exists"
            ) from error

    @staticmethod
    def _trajectory_from_row(row: dict[str, Any]) -> TrajectoryRecord:
        return TrajectoryRecord(
            id=row["id"],
            created_at=row["created_at"],
            kind=row["kind"],
            frames=tuple(
                TrajectoryFrame(
                    item["structure_id"], tuple(item.get("evaluation_ids", ()))
                )
                for item in row["frames"]
            ),
            provenance=provenance_from_dict(row["provenance"]),
        )

    def get_trajectory(self, record_id: RecordId) -> TrajectoryRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                    self._table("trajectories")
                ),
                (record_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._trajectory_from_row(row)

    def iter_trajectories(self) -> Iterable[TrajectoryRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} ORDER BY created_at, id").format(
                    self._table("trajectories")
                )
            )
            return iter(
                [self._trajectory_from_row(row) for row in cursor.fetchall()]
            )

    def put_stored_query(self, record: StoredQuery) -> None:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, label, description, query, created_at, hidden_at, provenance) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    ).format(self._table("stored_queries")),
                    (
                        record.id,
                        record.label,
                        record.description,
                        Jsonb(dataset_query_to_dict(record.query)),
                        record.created_at,
                        record.hidden_at,
                        Jsonb(provenance_to_dict(record.provenance)),
                    ),
                )
        except UniqueViolation as error:
            raise DuplicateRecordError(
                "Stored query already exists"
            ) from error

    @staticmethod
    def _stored_query_from_row(row: dict[str, Any]) -> StoredQuery:
        return StoredQuery(
            id=row["id"],
            label=row["label"],
            description=row["description"],
            query=dataset_query_from_dict(row["query"]),
            created_at=row["created_at"],
            provenance=provenance_from_dict(row["provenance"]),
            hidden_at=row["hidden_at"],
        )

    def get_stored_query(self, record_id: RecordId) -> StoredQuery:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                    self._table("stored_queries")
                ),
                (record_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._stored_query_from_row(row)

    def iter_stored_query_summaries(self) -> Iterable[StoredQuerySummary]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE hidden_at IS NULL ORDER BY created_at, id"
                ).format(self._table("stored_queries"))
            )
            rows = cursor.fetchall()
        return iter(
            StoredQuerySummary(
                row["id"],
                row["label"],
                dataset_query_from_dict(row["query"]),
                row["created_at"],
            )
            for row in rows
        )

    def iter_stored_queries(self) -> Iterable[StoredQuery]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} ORDER BY created_at, id").format(
                    self._table("stored_queries")
                )
            )
            rows = cursor.fetchall()
        return iter(self._stored_query_from_row(row) for row in rows)

    def hide_stored_query(self, record_id: RecordId) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("UPDATE {} SET hidden_at = %s WHERE id = %s").format(
                    self._table("stored_queries")
                ),
                (utc_now(), record_id),
            )
            if cursor.rowcount == 0:
                raise RecordNotFoundError(record_id)

    def delete_stored_query(
        self, record_id: RecordId, *, force: bool = False
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT id FROM {} WHERE id = %s").format(
                    self._table("stored_queries")
                ),
                (record_id,),
            )
            if cursor.fetchone() is None:
                raise RecordNotFoundError(record_id)
            cursor.execute(
                sql.SQL(
                    "SELECT id FROM {} WHERE source_stored_query_id = %s ORDER BY id"
                ).format(self._table("aggregations")),
                (record_id,),
            )
            refs = tuple(row["id"] for row in cursor.fetchall())
            if refs and not force:
                raise StoredQueryInUseError(record_id, refs)
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE id = %s").format(
                    self._table("stored_queries")
                ),
                (record_id,),
            )

    @staticmethod
    def _validate_aggregation_members(record: Aggregation) -> None:
        members = record.members
        if not members:
            raise AggregationValidationError(
                "An aggregation must contain at least one structure"
            )
        if tuple(member.ordinal for member in members) != tuple(
            range(len(members))
        ):
            raise AggregationValidationError(
                "Aggregation member ordinals must start at zero and be contiguous"
            )
        pairs = tuple(
            (member.structure_id, member.evaluation_id) for member in members
        )
        if any(not isinstance(member.structure_id, str) for member in members):
            raise AggregationValidationError("Structure IDs must be strings")
        if len(set(pairs)) != len(pairs):
            raise AggregationValidationError(
                "An aggregation cannot contain duplicate structure/evaluation pairs"
            )
        if aggregation_membership_hash(pairs) != record.membership_hash:
            raise IntegrityError(
                f"Aggregation membership hash does not match: {record.id}"
            )
        if not record.name:
            raise AggregationValidationError("An aggregation name is required")
        if record.external_key == "":
            raise AggregationValidationError("External keys must not be empty")

    @classmethod
    def _aggregation_from_row(
        cls,
        row: dict[str, Any],
        member_rows: Sequence[dict[str, Any]] = (),
        *,
        validate_members: bool = False,
    ) -> Aggregation:
        record = Aggregation(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            metadata=row["metadata"],
            source_stored_query_id=row["source_stored_query_id"],
            source_query_snapshot=row["source_query_snapshot"],
            external_key=row["external_key"],
            membership_hash=row["membership_hash"],
            supersedes_id=row["supersedes_id"],
            members=tuple(
                AggregationMember(**member_row) for member_row in member_rows
            ),
        )
        if validate_members:
            cls._validate_aggregation_members(record)
        return record

    @staticmethod
    def _aggregation_compatible(
        existing: Aggregation, requested: Aggregation
    ) -> bool:
        return (
            existing.name == requested.name
            and existing.description == requested.description
            and existing.metadata == requested.metadata
            and existing.source_stored_query_id
            == requested.source_stored_query_id
            and existing.source_query_snapshot
            == requested.source_query_snapshot
            and existing.external_key == requested.external_key
            and existing.membership_hash == requested.membership_hash
            and existing.supersedes_id == requested.supersedes_id
            and existing.members == requested.members
        )

    def _aggregation_with_members(
        self,
        cursor: psycopg.Cursor[Any],
        row: dict[str, Any],
        *,
        include_members: bool,
    ) -> Aggregation:
        member_rows: Sequence[dict[str, Any]] = ()
        if include_members:
            cursor.execute(
                sql.SQL(
                    "SELECT ordinal, structure_id, evaluation_id FROM {} WHERE aggregation_id = %s ORDER BY ordinal"
                ).format(self._table("aggregation_members")),
                (row["id"],),
            )
            member_rows = cursor.fetchall()
        return self._aggregation_from_row(
            row, member_rows, validate_members=include_members
        )

    def _existing_aggregation_for_key(
        self, cursor: psycopg.Cursor[Any], external_key: str
    ) -> Aggregation | None:
        cursor.execute(
            sql.SQL("SELECT * FROM {} WHERE external_key = %s").format(
                self._table("aggregations")
            ),
            (external_key,),
        )
        row = cursor.fetchone()
        return (
            None
            if row is None
            else self._aggregation_with_members(
                cursor, row, include_members=True
            )
        )

    def put_aggregation(self, record: Aggregation) -> Aggregation:
        """Atomically insert an aggregation, or resolve its idempotency key."""
        self._validate_aggregation_members(record)
        try:
            metadata = Jsonb(to_plain(record.metadata))
            snapshot = (
                Jsonb(to_plain(record.source_query_snapshot))
                if record.source_query_snapshot is not None
                else None
            )
        except (SerializationError, TypeError, ValueError) as error:
            raise AggregationValidationError(
                "Aggregation metadata must be JSON serializable"
            ) from error

        try:
            with self._connect() as connection, connection.cursor() as cursor:
                if record.external_key is not None:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (record.external_key,),
                    )
                    existing = self._existing_aggregation_for_key(
                        cursor, record.external_key
                    )
                    if existing is not None:
                        if self._aggregation_compatible(existing, record):
                            return existing
                        raise AggregationConflictError(
                            f"External key already identifies a different aggregation: {record.external_key}"
                        )

                structure_ids = {
                    member.structure_id for member in record.members
                }
                cursor.execute(
                    sql.SQL("SELECT id FROM {} WHERE id = ANY(%s)").format(
                        self._table("structures")
                    ),
                    (list(structure_ids),),
                )
                known_structures = {row["id"] for row in cursor.fetchall()}
                if known_structures != structure_ids:
                    raise RecordNotFoundError(
                        f"Aggregation references unknown structures: {sorted(structure_ids - known_structures)}"
                    )
                evaluation_ids = {
                    member.evaluation_id
                    for member in record.members
                    if member.evaluation_id is not None
                }
                if evaluation_ids:
                    cursor.execute(
                        sql.SQL(
                            "SELECT id, structure_id FROM {} WHERE id = ANY(%s)"
                        ).format(self._table("evaluations")),
                        (list(evaluation_ids),),
                    )
                    evaluation_structures = {
                        row["id"]: row["structure_id"]
                        for row in cursor.fetchall()
                    }
                    if set(evaluation_structures) != evaluation_ids:
                        raise RecordNotFoundError(
                            "Aggregation references an unknown evaluation"
                        )
                    if any(
                        member.evaluation_id is not None
                        and evaluation_structures[member.evaluation_id]
                        != member.structure_id
                        for member in record.members
                    ):
                        raise AggregationValidationError(
                            "Evaluation does not belong to aggregation structure"
                        )
                for structure_id in structure_ids:
                    members = [
                        m
                        for m in record.members
                        if m.structure_id == structure_id
                    ]
                    if any(m.evaluation_id is None for m in members) and any(
                        m.evaluation_id is not None for m in members
                    ):
                        raise AggregationValidationError(
                            "A NULL evaluation member cannot coexist with evaluated members"
                        )
                    if sum(m.evaluation_id is None for m in members) > 1:
                        raise AggregationValidationError(
                            "At most one NULL evaluation member is allowed per structure"
                        )

                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, name, description, created_at, metadata, source_stored_query_id, source_query_snapshot, external_key, membership_hash, supersedes_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ).format(self._table("aggregations")),
                    (
                        record.id,
                        record.name,
                        record.description,
                        record.created_at,
                        metadata,
                        record.source_stored_query_id,
                        snapshot,
                        record.external_key,
                        record.membership_hash,
                        record.supersedes_id,
                    ),
                )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} (aggregation_id, ordinal, structure_id, evaluation_id) VALUES (%s, %s, %s, %s)"
                    ).format(self._table("aggregation_members")),
                    [
                        (
                            record.id,
                            member.ordinal,
                            member.structure_id,
                            member.evaluation_id,
                        )
                        for member in record.members
                    ],
                )
        except UniqueViolation as error:
            if error.diag.constraint_name == "aggregations_external_key_key":
                raise AggregationConflictError(
                    f"External key already exists: {record.external_key}"
                ) from error
            raise DuplicateRecordError(
                f"Aggregation record already exists: {record.id}"
            ) from error
        except ForeignKeyViolation as error:
            raise RecordNotFoundError(
                "Aggregation references an unknown saved query or aggregation"
            ) from error
        return record

    def put_aggregations(self, records: Sequence[Aggregation]) -> None:
        for record in records:
            self.put_aggregation(record)

    def get_aggregation(
        self, aggregation_id: str, *, include_members: bool = True
    ) -> Aggregation:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                    self._table("aggregations")
                ),
                (aggregation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise AggregationNotFoundError(aggregation_id)
            return self._aggregation_with_members(
                cursor, row, include_members=include_members
            )

    def get_aggregation_by_external_key(
        self, external_key: str, *, include_members: bool = True
    ) -> Aggregation:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} WHERE external_key = %s").format(
                    self._table("aggregations")
                ),
                (external_key,),
            )
            row = cursor.fetchone()
            if row is None:
                raise AggregationNotFoundError(external_key)
            return self._aggregation_with_members(
                cursor, row, include_members=include_members
            )

    def iter_aggregations(self) -> Iterable[Aggregation]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {} ORDER BY created_at, id").format(
                    self._table("aggregations")
                )
            )
            return iter(
                [
                    self._aggregation_with_members(
                        cursor, row, include_members=True
                    )
                    for row in cursor.fetchall()
                ]
            )

    def iter_aggregation_summaries(
        self,
        *,
        name: str | None = None,
        source_stored_query_id: str | None = None,
    ) -> Iterable[AggregationSummary]:
        conditions: list[sql.Composable] = []
        parameters: list[Any] = []
        if name is not None:
            conditions.append(sql.SQL("a.name = %s"))
            parameters.append(name)
        if source_stored_query_id is not None:
            conditions.append(sql.SQL("a.source_stored_query_id = %s"))
            parameters.append(source_stored_query_id)
        condition = (
            sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)
            if conditions
            else sql.SQL("")
        )
        statement = sql.SQL(
            "SELECT a.*, COUNT(am.ordinal) AS member_count FROM {} a LEFT JOIN {} am "
            "ON am.aggregation_id = a.id{} GROUP BY a.id ORDER BY a.created_at, a.id"
        ).format(
            self._table("aggregations"),
            self._table("aggregation_members"),
            condition,
        )
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
        return iter(
            AggregationSummary(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                created_at=row["created_at"],
                metadata=row["metadata"],
                source_stored_query_id=row["source_stored_query_id"],
                external_key=row["external_key"],
                membership_hash=row["membership_hash"],
                supersedes_id=row["supersedes_id"],
                member_count=row["member_count"],
            )
            for row in rows
        )
