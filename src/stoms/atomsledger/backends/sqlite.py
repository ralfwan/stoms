from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from ..exceptions import (
    AggregationConflictError,
    AggregationNotFoundError,
    AggregationValidationError,
    DuplicateRecordError,
    IntegrityError,
    RecordNotFoundError,
    SerializationError,
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
    ensure_utc,
    utc_now,
)
from ..serialization import (
    aggregation_membership_hash,
    atoms_from_binary_payload,
    atoms_to_binary_payload,
    dataset_query_from_dict,
    dataset_query_to_dict,
    evaluation_content_hash,
    json_dumps,
    json_loads,
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
    trajectory_frames_to_dict,
)

SCHEMA_NAME = "atomsledger"
SCHEMA_VERSION = 8


class SQLiteRepository:
    """Indexed, single-file implementation of the repository protocol.

    SQLite is the default backend because it provides a transferable database
    file while retaining transactions, foreign keys, and indexed metadata
    queries. The repository opens one short-lived connection per public method.
    Writes are serialized by SQLite and each batch method is transactional.

    The default journal mode is ``DELETE`` so a quiescent database is fully
    represented by one file. ``WAL`` can be selected for local read/write
    concurrency, but callers should checkpoint before copying the database.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        initialize: bool = True,
        timeout: float = 30.0,
        journal_mode: str = "DELETE",
    ) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self.journal_mode = journal_mode.upper()
        if self.journal_mode not in {"DELETE", "WAL", "TRUNCATE", "PERSIST"}:
            raise ValueError(
                f"Unsupported SQLite journal mode: {journal_mode!r}"
            )
        if initialize:
            self.initialize()
        else:
            self.validate()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout,
            isolation_level="DEFERRED",
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA journal_mode = {self.journal_mode}")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def validate(self) -> None:
        """Verify that an existing file has a supported atomsledger schema."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT key, value FROM schema_info"
                ).fetchall()
        except sqlite3.DatabaseError as error:
            raise IntegrityError(
                "SQLite file is not a readable atomsledger store"
            ) from error
        info = {row["key"]: row["value"] for row in rows}
        if info.get("schema_name") != SCHEMA_NAME:
            raise IntegrityError("SQLite file is not an atomsledger store")
        if int(info.get("schema_version", -1)) != SCHEMA_VERSION:
            raise IntegrityError(
                "Unsupported atomsledger SQLite schema version"
            )

    def initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS structure_source_specs (
                    id TEXT PRIMARY KEY,
                    specification TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS structures (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    structure_content_hash TEXT NOT NULL,
                    formula TEXT NOT NULL,
                    atoms_metadata TEXT NOT NULL,
                    atoms_payload BLOB NOT NULL,
                    source_spec_id TEXT NOT NULL
                        REFERENCES structure_source_specs(id) ON DELETE RESTRICT,
                    provenance TEXT NOT NULL,
                    purpose TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS structure_tags (
                    structure_id TEXT NOT NULL
                        REFERENCES structures(id) ON DELETE RESTRICT,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (structure_id, tag)
                );

                CREATE TABLE IF NOT EXISTS method_specs (
                    id TEXT PRIMARY KEY,
                    specification TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY,
                    structure_id TEXT NOT NULL
                        REFERENCES structures(id) ON DELETE RESTRICT,
                    created_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    method_family TEXT NOT NULL,
                    method_name TEXT NOT NULL,
                    method_version TEXT,
                    method_code TEXT,
                    method_identifier TEXT NOT NULL,
                    method TEXT NOT NULL REFERENCES method_specs(id),
                    properties_metadata TEXT NOT NULL,
                    properties_payload BLOB NOT NULL,
                    units TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    purpose TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_tags (
                    evaluation_id TEXT NOT NULL
                        REFERENCES evaluations(id) ON DELETE RESTRICT,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (evaluation_id, tag)
                );

                CREATE TABLE IF NOT EXISTS evaluation_properties (
                    evaluation_id TEXT NOT NULL
                        REFERENCES evaluations(id) ON DELETE RESTRICT,
                    name TEXT NOT NULL,
                    PRIMARY KEY (evaluation_id, name)
                );

                CREATE TABLE IF NOT EXISTS trajectories (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    frames TEXT NOT NULL,
                    provenance TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stored_queries (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL,
                    query TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    hidden_at TEXT,
                    provenance TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS aggregations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    source_stored_query_id TEXT
                        REFERENCES stored_queries(id) ON DELETE SET NULL,
                    source_query_snapshot TEXT,
                    external_key TEXT UNIQUE,
                    membership_hash TEXT NOT NULL,
                    supersedes_id TEXT
                        REFERENCES aggregations(id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS aggregation_members (
                    aggregation_id TEXT NOT NULL
                        REFERENCES aggregations(id) ON DELETE RESTRICT,
                    ordinal INTEGER NOT NULL,
                    structure_id TEXT NOT NULL
                        REFERENCES structures(id) ON DELETE RESTRICT,
                    evaluation_id TEXT
                        REFERENCES evaluations(id) ON DELETE RESTRICT,
                    PRIMARY KEY (aggregation_id, ordinal),
                    UNIQUE (aggregation_id, structure_id, evaluation_id)
                );

                CREATE INDEX IF NOT EXISTS structures_content_hash_idx
                    ON structures(structure_content_hash);
                CREATE INDEX IF NOT EXISTS structures_formula_idx
                    ON structures(formula);
                CREATE INDEX IF NOT EXISTS structures_created_at_idx
                    ON structures(created_at);
                CREATE INDEX IF NOT EXISTS structure_tags_tag_idx
                    ON structure_tags(tag, structure_id);

                CREATE INDEX IF NOT EXISTS evaluations_structure_id_idx
                    ON evaluations(structure_id);
                CREATE INDEX IF NOT EXISTS evaluations_method_idx
                    ON evaluations(method_name, method_version, method_identifier);
                CREATE INDEX IF NOT EXISTS evaluations_family_idx
                    ON evaluations(method_family);
                CREATE INDEX IF NOT EXISTS evaluations_created_at_idx
                    ON evaluations(created_at);
                CREATE INDEX IF NOT EXISTS evaluation_tags_tag_idx
                    ON evaluation_tags(tag, evaluation_id);
                CREATE INDEX IF NOT EXISTS evaluation_properties_name_idx
                    ON evaluation_properties(name, evaluation_id);

                CREATE INDEX IF NOT EXISTS trajectories_kind_idx
                    ON trajectories(kind, created_at);
                CREATE INDEX IF NOT EXISTS stored_queries_created_at_idx
                    ON stored_queries(created_at, id);
                CREATE INDEX IF NOT EXISTS aggregations_external_key_idx
                    ON aggregations(external_key);
                CREATE INDEX IF NOT EXISTS aggregations_name_idx
                    ON aggregations(name, created_at, id);
                CREATE INDEX IF NOT EXISTS aggregations_source_query_idx
                    ON aggregations(source_stored_query_id);
                CREATE INDEX IF NOT EXISTS aggregation_members_aggregation_idx
                    ON aggregation_members(aggregation_id, ordinal);
                CREATE INDEX IF NOT EXISTS aggregation_members_structure_idx
                    ON aggregation_members(structure_id, aggregation_id);
                """
            )
            info_rows = connection.execute(
                "SELECT key, value FROM schema_info"
            ).fetchall()
            info = {row["key"]: row["value"] for row in info_rows}
            if not info:
                connection.executemany(
                    "INSERT INTO schema_info(key, value) VALUES (?, ?)",
                    (
                        ("schema_name", SCHEMA_NAME),
                        ("schema_version", str(SCHEMA_VERSION)),
                    ),
                )
            elif info.get("schema_name") != SCHEMA_NAME:
                raise IntegrityError("SQLite file is not an atomsledger store")
            elif int(info.get("schema_version", -1)) < SCHEMA_VERSION:
                self._upgrade_method_storage(connection)
                self._upgrade_structure_source_storage(connection)
                connection.execute(
                    "UPDATE schema_info SET value = ? "
                    "WHERE key = 'schema_version'",
                    (str(SCHEMA_VERSION),),
                )
            rows = connection.execute(
                "SELECT key, value FROM schema_info"
            ).fetchall()
            info = {row["key"]: row["value"] for row in rows}
            if info.get("schema_name") != SCHEMA_NAME:
                raise IntegrityError("SQLite file is not an atomsledger store")
            if int(info.get("schema_version", -1)) != SCHEMA_VERSION:
                raise IntegrityError(
                    "Unsupported atomsledger SQLite schema version"
                )

    def checkpoint(self, *, truncate: bool = True) -> None:
        """Checkpoint a WAL database before copying or archiving it."""
        with self._connect() as connection:
            mode = "TRUNCATE" if truncate else "FULL"
            connection.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return ensure_utc(value).isoformat()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value)

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
        actual = evaluation_content_hash(
            record.structure_id, record.method, record.properties, record.units
        )
        if actual != record.content_hash:
            raise IntegrityError(
                f"Evaluation content hash does not match payload: {record.id}"
            )

    @staticmethod
    def _upgrade_method_storage(connection: sqlite3.Connection) -> None:
        """Move legacy inline method JSON into the shared method table."""
        rows = connection.execute(
            "SELECT id, method FROM evaluations"
        ).fetchall()
        for row in rows:
            try:
                method = method_from_dict(json_loads(row["method"]))
            except (TypeError, KeyError, ValueError) as error:
                raise IntegrityError(
                    f"Could not migrate method for evaluation {row['id']}"
                ) from error
            method_id = method_content_hash(method)
            connection.execute(
                "INSERT OR IGNORE INTO method_specs(id, specification) "
                "VALUES (?, ?)",
                (method_id, json_dumps(method_to_dict(method))),
            )
            connection.execute(
                "UPDATE evaluations SET method = ? WHERE id = ?",
                (method_id, row["id"]),
            )

    @staticmethod
    def _upgrade_structure_source_storage(
        connection: sqlite3.Connection,
    ) -> None:
        """Rename the legacy structure-source model field in stored JSON."""
        rows = connection.execute(
            "SELECT id, specification FROM structure_source_specs"
        ).fetchall()
        for row in rows:
            value = json_loads(row["specification"])
            if "model_id" not in value:
                continue
            value["model_identifier"] = value.pop("model_id")
            source = structure_source_from_dict(value)
            new_id = structure_source_content_hash(source)
            connection.execute(
                "INSERT OR IGNORE INTO structure_source_specs"
                "(id, specification) VALUES (?, ?)",
                (new_id, json_dumps(structure_source_to_dict(source))),
            )
            connection.execute(
                "UPDATE structures SET source_spec_id = ? "
                "WHERE source_spec_id = ?",
                (new_id, row["id"]),
            )
            connection.execute(
                "DELETE FROM structure_source_specs WHERE id = ?",
                (row["id"],),
            )

    @staticmethod
    def _placeholders(values: Sequence[Any]) -> str:
        return ",".join("?" for _ in values)

    @staticmethod
    def _tag_condition(
        *,
        association_table: str,
        association_id: str,
        record_alias: str,
        provenance_column: str,
        negate: bool = False,
    ) -> str:
        condition = (
            f"EXISTS (SELECT 1 FROM {association_table} tags "
            f"WHERE tags.{association_id} = {record_alias}.id "
            "AND tags.tag = ?) OR EXISTS ("
            f"SELECT 1 FROM json_each({record_alias}.{provenance_column}, '$.tags') "
            "WHERE json_each.value = ?)"
        )
        return f"NOT ({condition})" if negate else f"({condition})"

    @staticmethod
    def _row_tags(
        row: sqlite3.Row, provenance_tags: Sequence[str], column: str
    ) -> tuple[str, ...]:
        indexed = json_loads(row[column]) if row[column] is not None else []
        return tuple(sorted(set(provenance_tags).union(indexed)))

    def put_structure(self, record: StructureRecord) -> None:
        self.put_structures([record])

    @staticmethod
    def _structure_values(
        record: StructureRecord,
    ) -> tuple[tuple[Any, ...], tuple[str, str], list[tuple[str, str]]]:
        atoms = record.atoms
        metadata, payload = atoms_to_binary_payload(atoms)
        source_id = structure_source_content_hash(record.source_spec)
        row = (
            record.id,
            SQLiteRepository._timestamp(record.created_at),
            record.structure_content_hash,
            atoms.get_chemical_formula(mode="hill"),
            json_dumps(metadata),
            payload,
            source_id,
            json_dumps(provenance_to_dict(record.provenance)),
            record.provenance.purpose,
        )
        source_row = (
            source_id,
            json_dumps(structure_source_to_dict(record.source_spec)),
        )
        return (
            row,
            source_row,
            [(record.id, tag) for tag in record.provenance.tags],
        )

    @staticmethod
    def _insert_structure_rows(
        connection: sqlite3.Connection,
        rows: Sequence[tuple[Any, ...]],
        source_rows: Sequence[tuple[str, str]],
        tag_rows: Sequence[tuple[str, str]],
    ) -> None:
        connection.executemany(
            "INSERT OR IGNORE INTO structure_source_specs(id, specification) "
            "VALUES (?, ?)",
            source_rows,
        )
        connection.executemany(
            """
            INSERT INTO structures(
                id, created_at, structure_content_hash, formula, atoms_metadata,
                atoms_payload, source_spec_id, provenance, purpose
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.executemany(
            "INSERT INTO structure_tags(structure_id, tag) VALUES (?, ?)",
            tag_rows,
        )

    def put_structures(self, records: Sequence[StructureRecord]) -> None:
        if not records:
            return
        rows: list[tuple[Any, ...]] = []
        source_rows: list[tuple[str, str]] = []
        tag_rows: list[tuple[str, str]] = []
        for record in records:
            self._validate_structure(record)
            row, source_row, record_tags = self._structure_values(record)
            rows.append(row)
            source_rows.append(source_row)
            tag_rows.extend(record_tags)
        try:
            with self._transaction() as connection:
                self._insert_structure_rows(
                    connection, rows, source_rows, tag_rows
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(
                "Structure record already exists"
            ) from error

    def put_structures_deduplicating(
        self, records: Sequence[StructureRecord]
    ) -> list[StructureRecord]:
        return self.put_structures_content_aware(records)

    def put_structures_content_aware(
        self,
        records: Sequence[StructureRecord],
        *,
        allow_equivalent_atoms: bool = False,
    ) -> list[StructureRecord]:
        if not records:
            return []
        for record in records:
            self._validate_structure(record)

        persisted: list[StructureRecord] = []
        conflicts: list[StructureContentConflict] = []
        known: dict[str, list[StructureRecord]] = {}
        planned: dict[str, list[StructureRecord]] = {}
        to_write: list[StructureRecord] = []
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for input_index, record in enumerate(records):
                content_hash = record.structure_content_hash
                candidates = known.get(content_hash)
                if candidates is None:
                    row = connection.execute(
                        """
                        SELECT s.*, (SELECT json_group_array(st.tag)
                        FROM structure_tags st WHERE st.structure_id = s.id)
                        AS association_tags
                        , ss.specification AS source_specification
                        FROM structures s
                        JOIN structure_source_specs ss
                        ON ss.id = s.source_spec_id
                        WHERE s.structure_content_hash = ?
                        ORDER BY s.created_at, s.id
                        """,
                        (content_hash,),
                    ).fetchall()
                    candidates = [
                        self._structure_from_row(candidate_row)
                        for candidate_row in row
                    ]
                    known[content_hash] = candidates

                exact = next(
                    (
                        candidate
                        for candidate in candidates
                        if (
                            candidate.source_spec == record.source_spec
                            and candidate.provenance == record.provenance
                        )
                    ),
                    None,
                )
                if exact is not None:
                    persisted.append(exact)
                    continue
                if candidates and not allow_equivalent_atoms:
                    conflicts.append(
                        StructureContentConflict(
                            input_index=input_index,
                            matches=tuple(
                                StructureContentMatch(
                                    id=candidate.id,
                                    structure_content_hash=(
                                        candidate.structure_content_hash
                                    ),
                                    provenance=candidate.provenance,
                                    source_spec=candidate.source_spec,
                                )
                                for candidate in candidates
                            ),
                        )
                    )
                    continue

                planned_candidates = planned.setdefault(content_hash, [])
                exact = next(
                    (
                        candidate
                        for candidate in planned_candidates
                        if (
                            candidate.source_spec == record.source_spec
                            and candidate.provenance == record.provenance
                        )
                    ),
                    None,
                )
                if exact is not None:
                    persisted.append(exact)
                    continue
                if planned_candidates and not allow_equivalent_atoms:
                    conflicts.append(
                        StructureContentConflict(input_index=input_index)
                    )
                    continue
                planned_candidates.append(record)
                to_write.append(record)
                persisted.append(record)

            if conflicts:
                raise StructureContentConflictError(tuple(conflicts))
            for record in to_write:
                row_values, source_row, tag_rows = self._structure_values(
                    record
                )
                try:
                    self._insert_structure_rows(
                        connection, [row_values], [source_row], tag_rows
                    )
                except sqlite3.IntegrityError as error:
                    raise DuplicateRecordError(
                        "Structure record already exists"
                    ) from error
        return persisted

    @classmethod
    def _structure_from_row(cls, row: sqlite3.Row) -> StructureRecord:
        atoms = atoms_from_binary_payload(
            json_loads(row["atoms_metadata"]), bytes(row["atoms_payload"])
        )
        provenance = provenance_from_dict(json_loads(row["provenance"]))
        source_spec = structure_source_from_dict(
            json_loads(row["source_specification"])
        )
        if structure_source_content_hash(source_spec) != row["source_spec_id"]:
            raise IntegrityError(
                f"Structure source hash verification failed: {row['id']}"
            )
        record = StructureRecord(
            id=row["id"],
            created_at=cls._parse_timestamp(row["created_at"]),
            structure_content_hash=row["structure_content_hash"],
            source_spec=source_spec,
            provenance=provenance,
            _atoms=atoms,
            _effective_tags=cls._row_tags(
                row, provenance.tags, "association_tags"
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT s.*, (SELECT json_group_array(st.tag) "
                "FROM structure_tags st WHERE st.structure_id = s.id) "
                "AS association_tags, ss.specification AS source_specification "
                "FROM structures s JOIN structure_source_specs ss "
                "ON ss.id = s.source_spec_id WHERE s.id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._structure_from_row(row)

    def _structure_query_statement(
        self, query: StructureQuery, columns: str
    ) -> tuple[str, list[Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        if query.ids is not None:
            if not query.ids:
                return "", []
            conditions.append(f"s.id IN ({self._placeholders(query.ids)})")
            parameters.extend(query.ids)
        if query.structure_content_hash is not None:
            conditions.append("s.structure_content_hash = ?")
            parameters.append(query.structure_content_hash)
        if query.formula is not None:
            conditions.append("s.formula = ?")
            parameters.append(query.formula)
        if query.created_after is not None:
            conditions.append("s.created_at >= ?")
            parameters.append(self._timestamp(query.created_after))
        if query.created_before is not None:
            conditions.append("s.created_at < ?")
            parameters.append(self._timestamp(query.created_before))
        for tag in query.tags_all:
            conditions.append(
                self._tag_condition(
                    association_table="structure_tags",
                    association_id="structure_id",
                    record_alias="s",
                    provenance_column="provenance",
                )
            )
            parameters.extend((tag, tag))
        if query.tags_any:
            conditions.append(
                "EXISTS (SELECT 1 FROM structure_tags st "
                f"WHERE st.structure_id = s.id AND st.tag IN "
                f"({self._placeholders(query.tags_any)})) OR EXISTS ("
                "SELECT 1 FROM json_each(s.provenance, '$.tags') "
                f"WHERE json_each.value IN ({self._placeholders(query.tags_any)}))"
            )
            parameters.extend((*query.tags_any, *query.tags_any))
        for tag in query.tags_none:
            conditions.append(
                self._tag_condition(
                    association_table="structure_tags",
                    association_id="structure_id",
                    record_alias="s",
                    provenance_column="provenance",
                    negate=True,
                )
            )
            parameters.extend((tag, tag))

        if columns == "s.*":
            columns = (
                "s.*, (SELECT json_group_array(st.tag) FROM structure_tags st "
                "WHERE st.structure_id = s.id) AS association_tags, "
                "ss.specification AS source_specification"
            )
        statement = (
            f"SELECT {columns} FROM structures s "
            "JOIN structure_source_specs ss ON ss.id = s.source_spec_id"
        )
        if conditions:
            statement += " WHERE " + " AND ".join(conditions)
        statement += " ORDER BY s.created_at, s.id"
        return statement, parameters

    def iter_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureRecord]:
        query = query or StructureQuery()
        statement, parameters = self._structure_query_statement(query, "s.*")
        if not statement:
            return iter(())

        def records() -> Iterator[StructureRecord]:
            with self._connect() as connection:
                cursor = connection.execute(statement, parameters)
                for row in cursor:
                    record = self._structure_from_row(row)
                    if query.matches(record):
                        yield record

        return records()

    def catalog_structures(
        self, query: StructureQuery | None = None
    ) -> tuple[StructureCatalogEntry, ...]:
        """Search structure metadata without reading structure or result blobs."""
        return tuple(self.iter_catalog_structures(query))

    def iter_catalog_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureCatalogEntry]:
        """Yield catalog entries without materializing the broad result set."""
        query = query or StructureQuery()
        statement, parameters = self._structure_query_statement(
            query,
            "s.id, s.created_at, s.structure_content_hash, s.formula, s.provenance, "
            "(SELECT json_group_array(st.tag) FROM structure_tags st "
            "WHERE st.structure_id = s.id) AS association_tags, "
            "s.purpose, e.id AS evaluation_id, e.created_at AS evaluation_created_at, "
            "ms.specification AS method_specification, e.units, "
            "e.provenance AS evaluation_provenance, "
            "(SELECT json_group_array(et.tag) FROM evaluation_tags et "
            "WHERE et.evaluation_id = e.id) AS evaluation_tags, "
            "GROUP_CONCAT(ep.name) AS property_names",
        )
        if not statement:
            return iter(())
        statement = statement.removesuffix(" ORDER BY s.created_at, s.id")
        join = (
            " LEFT JOIN evaluations e ON e.structure_id = s.id"
            " LEFT JOIN method_specs ms ON ms.id = e.method"
            " LEFT JOIN evaluation_properties ep ON ep.evaluation_id = e.id"
        )
        statement = statement.replace(
            " FROM structures s", " FROM structures s" + join, 1
        )
        statement += (
            " GROUP BY s.id, e.id"
            " ORDER BY s.created_at, s.id, e.created_at, e.id"
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
            with self._connect() as connection:
                for row in connection.execute(statement, parameters):
                    if (
                        needle is not None
                        and needle not in row["purpose"].casefold()
                    ):
                        continue
                    if row["id"] != current_id:
                        if current_entry is not None:
                            yield current_entry
                        provenance = provenance_from_dict(
                            json_loads(row["provenance"])
                        )
                        current_id = row["id"]
                        evaluators = []
                        current_entry = StructureCatalogEntry(
                            id=row["id"],
                            created_at=self._parse_timestamp(
                                row["created_at"]
                            ),
                            structure_content_hash=row[
                                "structure_content_hash"
                            ],
                            formula=row["formula"],
                            created_by=provenance.created_by,
                            purpose=provenance.purpose,
                            tags=self._row_tags(
                                row, provenance.tags, "association_tags"
                            ),
                            evaluators=(),
                        )
                    if row["evaluation_id"] is not None:
                        provenance = provenance_from_dict(
                            json_loads(row["evaluation_provenance"])
                        )
                        evaluators.append(
                            EvaluatorCatalogEntry(
                                id=row["evaluation_id"],
                                created_at=self._parse_timestamp(
                                    row["evaluation_created_at"]
                                ),
                                method=method_from_dict(
                                    json_loads(row["method_specification"])
                                ),
                                property_names=tuple(
                                    sorted(
                                        filter(
                                            None,
                                            (
                                                row["property_names"] or ""
                                            ).split(","),
                                        )
                                    )
                                ),
                                units=json_loads(row["units"]),
                                created_by=provenance.created_by,
                                purpose=provenance.purpose,
                                tags=self._row_tags(
                                    row, provenance.tags, "evaluation_tags"
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
        self.put_evaluations([record])

    def put_evaluations(self, records: Sequence[EvaluationRecord]) -> None:
        if not records:
            return
        rows: list[tuple[Any, ...]] = []
        method_rows: dict[str, tuple[str, str]] = {}
        tag_rows: list[tuple[str, str]] = []
        property_rows: list[tuple[str, str]] = []
        for record in records:
            self._validate_evaluation(record)
            properties_metadata, properties_payload = (
                properties_to_binary_payload(record.properties)
            )
            method_id = method_content_hash(record.method)
            method_rows[method_id] = (
                method_id,
                json_dumps(method_to_dict(record.method)),
            )
            rows.append(
                (
                    record.id,
                    record.structure_id,
                    self._timestamp(record.created_at),
                    record.content_hash,
                    record.method.family,
                    record.method.name,
                    record.method.version,
                    record.method.code,
                    record.method.method_identifier,
                    method_id,
                    json_dumps(properties_metadata),
                    properties_payload,
                    json_dumps(record.units),
                    json_dumps(provenance_to_dict(record.provenance)),
                    record.provenance.purpose,
                )
            )
            tag_rows.extend((record.id, tag) for tag in record.provenance.tags)
            property_rows.extend(
                (record.id, name) for name in record.properties
            )
        try:
            with self._transaction() as connection:
                connection.executemany(
                    "INSERT OR IGNORE INTO method_specs(id, specification) "
                    "VALUES (?, ?)",
                    tuple(method_rows.values()),
                )
                connection.executemany(
                    """
                    INSERT INTO evaluations(
                        id, structure_id, created_at, content_hash,
                        method_family, method_name, method_version, method_code,
                        method_identifier, method, properties_metadata,
                        properties_payload, units, provenance, purpose
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                connection.executemany(
                    "INSERT INTO evaluation_tags(evaluation_id, tag) VALUES (?, ?)",
                    tag_rows,
                )
                connection.executemany(
                    """
                    INSERT INTO evaluation_properties(evaluation_id, name)
                    VALUES (?, ?)
                    """,
                    property_rows,
                )
        except sqlite3.IntegrityError as error:
            message = str(error).lower()
            if "foreign key" in message:
                raise IntegrityError(
                    "Evaluation references an unknown structure"
                ) from error
            raise DuplicateRecordError(
                "Evaluation record already exists"
            ) from error

    @classmethod
    def _evaluation_from_row(cls, row: sqlite3.Row) -> EvaluationRecord:
        provenance = provenance_from_dict(json_loads(row["provenance"]))
        method_specification = row["method_specification"]
        record = EvaluationRecord(
            id=row["id"],
            structure_id=row["structure_id"],
            created_at=cls._parse_timestamp(row["created_at"]),
            content_hash=row["content_hash"],
            method=method_from_dict(
                json_loads(method_specification)
                if method_specification is not None
                else json_loads(row["method"])
            ),
            properties=properties_from_binary_payload(
                json_loads(row["properties_metadata"]),
                bytes(row["properties_payload"]),
            ),
            units=json_loads(row["units"]),
            provenance=provenance,
            _effective_tags=cls._row_tags(
                row, provenance.tags, "association_tags"
            ),
        )
        actual = evaluation_content_hash(
            record.structure_id, record.method, record.properties, record.units
        )
        if actual != record.content_hash:
            raise IntegrityError(
                f"Evaluation hash verification failed: {record.id}"
            )
        return record

    def get_evaluation(self, record_id: RecordId) -> EvaluationRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT e.*, ms.specification AS method_specification, "
                "(SELECT json_group_array(et.tag) "
                "FROM evaluation_tags et WHERE et.evaluation_id = e.id) "
                "AS association_tags FROM evaluations e "
                "LEFT JOIN method_specs ms ON ms.id = e.method "
                "WHERE e.id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._evaluation_from_row(row)

    def list_method_identifiers(self) -> Iterable[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT method_identifier FROM evaluations "
                "ORDER BY method_identifier"
            ).fetchall()
        return tuple(row["method_identifier"] for row in rows)

    def iter_evaluations(
        self, query: EvaluationQuery | None = None
    ) -> Iterable[EvaluationRecord]:
        query = query or EvaluationQuery()
        conditions: list[str] = []
        parameters: list[Any] = []

        sequence_fields = (
            (query.ids, "e.id"),
            (query.structure_ids, "e.structure_id"),
        )
        for values, field_name in sequence_fields:
            if values is not None:
                if not values:
                    return iter(())
                conditions.append(
                    f"{field_name} IN ({self._placeholders(values)})"
                )
                parameters.extend(values)
        method_fields = (
            (query.method_families, "e.method_family"),
            (query.method_names, "e.method_name"),
            (query.method_versions, "e.method_version"),
            (query.method_codes, "e.method_code"),
            (query.method_identifiers, "e.method_identifier"),
        )
        for values, field_name in method_fields:
            if values:
                conditions.append(
                    f"{field_name} IN ({self._placeholders(values)})"
                )
                parameters.extend(values)
        for name in query.properties_all:
            conditions.append(
                "EXISTS (SELECT 1 FROM evaluation_properties ep "
                "WHERE ep.evaluation_id = e.id AND ep.name = ?)"
            )
            parameters.append(name)
        for tag in query.tags_all:
            conditions.append(
                self._tag_condition(
                    association_table="evaluation_tags",
                    association_id="evaluation_id",
                    record_alias="e",
                    provenance_column="provenance",
                )
            )
            parameters.extend((tag, tag))
        if query.tags_any:
            conditions.append(
                "EXISTS (SELECT 1 FROM evaluation_tags et "
                f"WHERE et.evaluation_id = e.id AND et.tag IN "
                f"({self._placeholders(query.tags_any)})) OR EXISTS ("
                "SELECT 1 FROM json_each(e.provenance, '$.tags') "
                f"WHERE json_each.value IN ({self._placeholders(query.tags_any)}))"
            )
            parameters.extend((*query.tags_any, *query.tags_any))
        for tag in query.tags_none:
            conditions.append(
                self._tag_condition(
                    association_table="evaluation_tags",
                    association_id="evaluation_id",
                    record_alias="e",
                    provenance_column="provenance",
                    negate=True,
                )
            )
            parameters.extend((tag, tag))
        if query.created_after is not None:
            conditions.append("e.created_at >= ?")
            parameters.append(self._timestamp(query.created_after))
        if query.created_before is not None:
            conditions.append("e.created_at < ?")
            parameters.append(self._timestamp(query.created_before))

        statement = (
            "SELECT e.*, ms.specification AS method_specification, "
            "(SELECT json_group_array(et.tag) "
            "FROM evaluation_tags et WHERE et.evaluation_id = e.id) "
            "AS association_tags FROM evaluations e "
            "LEFT JOIN method_specs ms ON ms.id = e.method"
        )
        if conditions:
            statement += " WHERE " + " AND ".join(conditions)
        statement += " ORDER BY e.created_at, e.id"

        def records() -> Iterator[EvaluationRecord]:
            with self._connect() as connection:
                cursor = connection.execute(statement, parameters)
                for row in cursor:
                    record = self._evaluation_from_row(row)
                    if query.matches(record):
                        yield record

        return records()

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
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT provenance FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise RecordNotFoundError(record_id)
            provenance = json_loads(row["provenance"])
            tags = connection.execute(
                f"SELECT tag FROM {association_table} WHERE {association_id} = ?",
                (record_id,),
            ).fetchall()
        return frozenset(
            tag["tag"] for tag in tags if tag["tag"] not in provenance["tags"]
        )

    def has_post_ingestion_tags(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM structure_tags st
                    JOIN structures s ON s.id = st.structure_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM json_each(s.provenance, '$.tags')
                        WHERE json_each.value = st.tag
                    )
                    UNION ALL
                    SELECT 1
                    FROM evaluation_tags et
                    JOIN evaluations e ON e.id = et.evaluation_id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM json_each(e.provenance, '$.tags')
                        WHERE json_each.value = et.tag
                    )
                ) AS has_tags
                """
            ).fetchone()
        return bool(row["has_tags"])

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

        with self._transaction() as connection:
            for record_id, (table, _, _) in targets.items():
                if (
                    connection.execute(
                        f"SELECT 1 FROM {table} WHERE id = ?", (record_id,)
                    ).fetchone()
                    is None
                ):
                    raise RecordNotFoundError(record_id)
            for record_id, tags in prepared.items():
                _, association_table, association_id = targets[record_id]
                connection.executemany(
                    f"INSERT OR IGNORE INTO {association_table} "
                    f"({association_id}, tag) VALUES (?, ?)",
                    [(record_id, tag) for tag in tags],
                )

        return {record_id: self.get_tags(record_id) for record_id in prepared}

    def get_tags(self, record_id: RecordId) -> frozenset[str]:
        table, _, _ = self._tag_target(record_id)
        if table == "structures":
            return frozenset(self.get_structure(record_id).effective_tags)
        return frozenset(self.get_evaluation(record_id).effective_tags)

    def put_trajectory(self, record: TrajectoryRecord) -> None:
        self.put_trajectories([record])

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
            with self._transaction() as connection:
                known_structures: set[str] = set()
                if structure_ids:
                    placeholders = self._placeholders(tuple(structure_ids))
                    known_structures = {
                        row["id"]
                        for row in connection.execute(
                            f"SELECT id FROM structures WHERE id IN ({placeholders})",
                            tuple(structure_ids),
                        )
                    }
                if known_structures != structure_ids:
                    missing = structure_ids - known_structures
                    raise IntegrityError(
                        f"Trajectory references unknown structures: {sorted(missing)}"
                    )

                evaluation_structures: dict[str, str] = {}
                if evaluation_ids:
                    placeholders = self._placeholders(tuple(evaluation_ids))
                    evaluation_structures = {
                        row["id"]: row["structure_id"]
                        for row in connection.execute(
                            "SELECT id, structure_id FROM evaluations "
                            f"WHERE id IN ({placeholders})",
                            tuple(evaluation_ids),
                        )
                    }
                if set(evaluation_structures) != evaluation_ids:
                    missing = evaluation_ids - set(evaluation_structures)
                    raise IntegrityError(
                        f"Trajectory references unknown evaluations: {sorted(missing)}"
                    )
                for record in records:
                    for frame in record.frames:
                        for evaluation_id in frame.evaluation_ids:
                            if (
                                evaluation_structures[evaluation_id]
                                != frame.structure_id
                            ):
                                raise IntegrityError(
                                    f"Evaluation {evaluation_id} does not belong to "
                                    f"structure {frame.structure_id}"
                                )

                connection.executemany(
                    """
                    INSERT INTO trajectories(id, created_at, kind, frames, provenance)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            record.id,
                            self._timestamp(record.created_at),
                            record.kind,
                            json_dumps(
                                trajectory_frames_to_dict(record.frames)
                            ),
                            json_dumps(provenance_to_dict(record.provenance)),
                        )
                        for record in records
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(
                "Trajectory record already exists"
            ) from error

    @classmethod
    def _trajectory_from_row(cls, row: sqlite3.Row) -> TrajectoryRecord:
        frames = tuple(
            TrajectoryFrame(
                structure_id=item["structure_id"],
                evaluation_ids=tuple(item.get("evaluation_ids", ())),
            )
            for item in json_loads(row["frames"])
        )
        return TrajectoryRecord(
            id=row["id"],
            created_at=cls._parse_timestamp(row["created_at"]),
            kind=row["kind"],
            frames=frames,
            provenance=provenance_from_dict(json_loads(row["provenance"])),
        )

    def get_trajectory(self, record_id: RecordId) -> TrajectoryRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trajectories WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._trajectory_from_row(row)

    def iter_trajectories(self) -> Iterable[TrajectoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trajectories ORDER BY created_at, id"
            ).fetchall()
        return iter([self._trajectory_from_row(row) for row in rows])

    def put_stored_query(self, record: StoredQuery) -> None:
        records = (record,)
        try:
            with self._transaction() as connection:
                connection.executemany(
                    """
                    INSERT INTO stored_queries(
                        id, label, description, query, created_at, hidden_at, provenance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            record.id,
                            record.label,
                            record.description,
                            json_dumps(dataset_query_to_dict(record.query)),
                            self._timestamp(record.created_at),
                            self._timestamp(record.hidden_at)
                            if record.hidden_at
                            else None,
                            json_dumps(provenance_to_dict(record.provenance)),
                        )
                        for record in records
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateRecordError(
                "Stored query already exists"
            ) from error

    @classmethod
    def _stored_query_from_row(cls, row: sqlite3.Row) -> StoredQuery:
        return StoredQuery(
            id=row["id"],
            label=row["label"],
            description=row["description"],
            query=dataset_query_from_dict(json_loads(row["query"])),
            created_at=cls._parse_timestamp(row["created_at"]),
            provenance=provenance_from_dict(json_loads(row["provenance"])),
            hidden_at=(
                cls._parse_timestamp(row["hidden_at"])
                if row["hidden_at"]
                else None
            ),
        )

    def get_stored_query(self, record_id: RecordId) -> StoredQuery:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM stored_queries WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(record_id)
        return self._stored_query_from_row(row)

    def iter_stored_query_summaries(self) -> Iterable[StoredQuerySummary]:
        statement = "SELECT * FROM stored_queries WHERE hidden_at IS NULL ORDER BY created_at, id"
        with self._connect() as connection:
            rows = connection.execute(statement).fetchall()
        return iter(
            [
                StoredQuerySummary(
                    row["id"],
                    row["label"],
                    dataset_query_from_dict(json_loads(row["query"])),
                    self._parse_timestamp(row["created_at"]),
                )
                for row in rows
            ]
        )

    def iter_stored_queries(self) -> Iterable[StoredQuery]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM stored_queries ORDER BY created_at, id"
            ).fetchall()
        return iter([self._stored_query_from_row(row) for row in rows])

    def hide_stored_query(self, record_id: RecordId) -> None:
        with self._transaction() as connection:
            result = connection.execute(
                "UPDATE stored_queries SET hidden_at = ? WHERE id = ?",
                (self._timestamp(utc_now()), record_id),
            )
            if result.rowcount == 0:
                raise RecordNotFoundError(record_id)

    def delete_stored_query(
        self, record_id: RecordId, *, force: bool = False
    ) -> None:
        from ..exceptions import StoredQueryInUseError

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT id FROM stored_queries WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                raise RecordNotFoundError(record_id)
            refs = tuple(
                r["id"]
                for r in connection.execute(
                    "SELECT id FROM aggregations WHERE source_stored_query_id = ?",
                    (record_id,),
                )
            )
            if refs and not force:
                raise StoredQueryInUseError(record_id, refs)
            connection.execute(
                "DELETE FROM stored_queries WHERE id = ?", (record_id,)
            )

    @staticmethod
    def _aggregation_values(
        record: Aggregation,
    ) -> tuple[Any, ...]:
        return (
            record.id,
            record.name,
            record.description,
            SQLiteRepository._timestamp(record.created_at),
            json_dumps(record.metadata),
            record.source_stored_query_id,
            (
                json_dumps(record.source_query_snapshot)
                if record.source_query_snapshot is not None
                else None
            ),
            record.external_key,
            record.membership_hash,
            record.supersedes_id,
        )

    @staticmethod
    def _validate_aggregation_members(record: Aggregation) -> None:
        members = record.members
        if not members:
            raise AggregationValidationError(
                "An aggregation must contain at least one structure"
            )
        expected_ordinals = tuple(range(len(members)))
        actual_ordinals = tuple(member.ordinal for member in members)
        if actual_ordinals != expected_ordinals:
            raise AggregationValidationError(
                "Aggregation member ordinals must start at zero and be contiguous"
            )
        structure_ids = tuple(member.structure_id for member in members)
        pairs = tuple(
            (member.structure_id, member.evaluation_id) for member in members
        )
        if any(
            not isinstance(structure_id, str) for structure_id in structure_ids
        ):
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
        row: sqlite3.Row,
        member_rows: Sequence[sqlite3.Row] = (),
        *,
        validate_members: bool = False,
    ) -> Aggregation:
        members = tuple(
            AggregationMember(
                ordinal=member_row["ordinal"],
                structure_id=member_row["structure_id"],
                evaluation_id=member_row["evaluation_id"],
            )
            for member_row in member_rows
        )
        record = Aggregation(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=cls._parse_timestamp(row["created_at"]),
            metadata=json_loads(row["metadata"]),
            source_stored_query_id=row["source_stored_query_id"],
            source_query_snapshot=(
                json_loads(row["source_query_snapshot"])
                if row["source_query_snapshot"] is not None
                else None
            ),
            external_key=row["external_key"],
            membership_hash=row["membership_hash"],
            supersedes_id=row["supersedes_id"],
            members=members,
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

    def put_aggregation(self, record: Aggregation) -> Aggregation:
        """Atomically insert an aggregation, or resolve its idempotency key."""
        self._validate_aggregation_members(record)
        try:
            values = self._aggregation_values(record)
        except (SerializationError, TypeError, ValueError) as error:
            raise AggregationValidationError(
                "Aggregation metadata must be JSON serializable"
            ) from error

        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if record.external_key is not None:
                existing_row = connection.execute(
                    "SELECT * FROM aggregations WHERE external_key = ?",
                    (record.external_key,),
                ).fetchone()
                if existing_row is not None:
                    member_rows = connection.execute(
                        "SELECT ordinal, structure_id, evaluation_id FROM aggregation_members "
                        "WHERE aggregation_id = ? ORDER BY ordinal",
                        (existing_row["id"],),
                    ).fetchall()
                    existing = self._aggregation_from_row(
                        existing_row, member_rows, validate_members=True
                    )
                    if self._aggregation_compatible(existing, record):
                        return existing
                    raise AggregationConflictError(
                        f"External key already identifies a different aggregation: "
                        f"{record.external_key}"
                    )

            structure_ids = tuple(
                member.structure_id for member in record.members
            )
            placeholders = self._placeholders(structure_ids)
            known_structures = {
                row["id"]
                for row in connection.execute(
                    f"SELECT id FROM structures WHERE id IN ({placeholders})",
                    structure_ids,
                )
            }
            if known_structures != set(structure_ids):
                missing = sorted(set(structure_ids) - known_structures)
                raise RecordNotFoundError(
                    f"Aggregation references unknown structures: {missing}"
                )
            evaluation_ids = tuple(
                member.evaluation_id
                for member in record.members
                if member.evaluation_id is not None
            )
            if evaluation_ids:
                rows = connection.execute(
                    f"SELECT id, structure_id FROM evaluations WHERE id IN ({self._placeholders(evaluation_ids)})",
                    evaluation_ids,
                ).fetchall()
                known_evaluations = {
                    row["id"]: row["structure_id"] for row in rows
                }
                if set(known_evaluations) != set(evaluation_ids):
                    raise RecordNotFoundError(
                        "Aggregation references an unknown evaluation"
                    )
                for member in record.members:
                    if (
                        member.evaluation_id is not None
                        and known_evaluations[member.evaluation_id]
                        != member.structure_id
                    ):
                        raise AggregationValidationError(
                            "Evaluation does not belong to aggregation structure"
                        )
            for structure_id in set(structure_ids):
                rows = [
                    m for m in record.members if m.structure_id == structure_id
                ]
                if any(m.evaluation_id is None for m in rows) and any(
                    m.evaluation_id is not None for m in rows
                ):
                    raise AggregationValidationError(
                        "A NULL evaluation member cannot coexist with evaluated members"
                    )
                if sum(m.evaluation_id is None for m in rows) > 1:
                    raise AggregationValidationError(
                        "At most one NULL evaluation member is allowed per structure"
                    )

            try:
                connection.execute(
                    """
                    INSERT INTO aggregations(
                        id, name, description, created_at, metadata,
                         source_stored_query_id, source_query_snapshot,
                        external_key, membership_hash, supersedes_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                connection.executemany(
                    """
                    INSERT INTO aggregation_members(
                        aggregation_id, ordinal, structure_id, evaluation_id
                    ) VALUES (?, ?, ?, ?)
                    """,
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
            except sqlite3.IntegrityError as error:
                message = str(error).lower()
                if "unique" in message and "external_key" in message:
                    raise AggregationConflictError(
                        f"External key already exists: {record.external_key}"
                    ) from error
                if "unique" in message or "primary key" in message:
                    raise DuplicateRecordError(
                        f"Aggregation record already exists: {record.id}"
                    ) from error
                if "foreign key" in message:
                    raise RecordNotFoundError(
                        "Aggregation references an unknown saved query or aggregation"
                    ) from error
                raise IntegrityError(
                    "Could not persist aggregation"
                ) from error
        return record

    def put_aggregations(self, records: Sequence[Aggregation]) -> None:
        for record in records:
            self.put_aggregation(record)

    def _aggregation_with_members(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        include_members: bool,
    ) -> Aggregation:
        member_rows: Sequence[sqlite3.Row] = ()
        if include_members:
            member_rows = connection.execute(
                "SELECT ordinal, structure_id, evaluation_id FROM aggregation_members "
                "WHERE aggregation_id = ? ORDER BY ordinal",
                (row["id"],),
            ).fetchall()
        return self._aggregation_from_row(
            row, member_rows, validate_members=include_members
        )

    def get_aggregation(
        self, aggregation_id: str, *, include_members: bool = True
    ) -> Aggregation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM aggregations WHERE id = ?", (aggregation_id,)
            ).fetchone()
            if row is None:
                raise AggregationNotFoundError(aggregation_id)
            return self._aggregation_with_members(
                connection, row, include_members=include_members
            )

    def get_aggregation_by_external_key(
        self, external_key: str, *, include_members: bool = True
    ) -> Aggregation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM aggregations WHERE external_key = ?",
                (external_key,),
            ).fetchone()
            if row is None:
                raise AggregationNotFoundError(external_key)
            return self._aggregation_with_members(
                connection, row, include_members=include_members
            )

    def iter_aggregations(self) -> Iterable[Aggregation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM aggregations ORDER BY created_at, id"
            ).fetchall()
            return iter(
                [
                    self._aggregation_with_members(
                        connection, row, include_members=True
                    )
                    for row in rows
                ]
            )

    def iter_aggregation_summaries(
        self,
        *,
        name: str | None = None,
        source_stored_query_id: str | None = None,
    ) -> Iterable[AggregationSummary]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if name is not None:
            conditions.append("a.name = ?")
            parameters.append(name)
        if source_stored_query_id is not None:
            conditions.append("a.source_stored_query_id = ?")
            parameters.append(source_stored_query_id)
        statement = (
            "SELECT a.*, COUNT(am.ordinal) AS member_count "
            "FROM aggregations a LEFT JOIN aggregation_members am "
            "ON am.aggregation_id = a.id"
        )
        if conditions:
            statement += " WHERE " + " AND ".join(conditions)
        statement += " GROUP BY a.id ORDER BY a.created_at, a.id"
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return iter(
            [
                AggregationSummary(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    created_at=self._parse_timestamp(row["created_at"]),
                    metadata=json_loads(row["metadata"]),
                    source_stored_query_id=row["source_stored_query_id"],
                    external_key=row["external_key"],
                    membership_hash=row["membership_hash"],
                    supersedes_id=row["supersedes_id"],
                    member_count=row["member_count"],
                )
                for row in rows
            ]
        )
