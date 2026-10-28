# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Declared uniqueness constraint identity, discovery, DDL, and enforcement."""

import json
import sqlite3
import typing
from collections.abc import Iterable, Mapping
from sqlite3 import Connection

from pygrafito.model import (
    Constraint,
    ConstraintViolationError,
    ElementKind,
    NotFoundError,
    Value,
)
from pygrafito.storage.codec import PropertyCodec


class ConstraintRegistry:
    """Own the declared uniqueness constraints stored in one database.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    codec : PropertyCodec
        Codec used to render quoted JSON paths and decode values.
    """

    PREFIX: typing.ClassVar[str] = "pygrafito_uniq"
    TOKEN_PREFIX: typing.ClassVar[str] = "pygrafito:constraint"
    TAGS: typing.ClassVar[dict[ElementKind, str]] = {
        ElementKind.NODE: "node",
        ElementKind.RELATIONSHIP: "rel",
    }
    KINDS: typing.ClassVar[dict[str, ElementKind]] = {tag: kind for kind, tag in TAGS.items()}
    SUFFIXES: typing.ClassVar[tuple[str, ...]] = ("_idx", "_props", "_labels")
    NAME_PARTS: typing.ClassVar[int] = 2

    def __init__(self, connection: Connection, codec: PropertyCodec) -> None:
        self._connection = connection
        self._codec = codec

    @classmethod
    def name(cls, constraint: Constraint) -> str:
        """Return the object-name stem for one constraint.

        Parameters
        ----------
        constraint : Constraint
            Declared constraint.

        Returns
        -------
        str
            Name stem such as ``pygrafito_uniq_node_50726f6772616d_6b6579``.
        """
        tag = cls.TAGS[constraint.kind]
        scope = constraint.scope.encode("utf-8").hex()
        key = constraint.key.encode("utf-8").hex()
        return f"{cls.PREFIX}_{tag}_{scope}_{key}"

    @classmethod
    def object_names(cls, constraint: Constraint) -> tuple[str, ...]:
        """Return the SQLite object names that implement one constraint.

        Parameters
        ----------
        constraint : Constraint
            Declared constraint.

        Returns
        -------
        tuple[str, ...]
            A support index and two triggers for either element kind.
        """
        stem = cls.name(constraint)
        return tuple(f"{stem}{suffix}" for suffix in cls.SUFFIXES)

    @classmethod
    def parse_name(cls, name: str) -> Constraint | None:
        """Recover a declared constraint from one SQLite object name.

        Parameters
        ----------
        name : str
            Candidate index or trigger name.

        Returns
        -------
        Constraint | None
            The declared constraint, or ``None`` when the name is not one of
            ours.
        """
        prefix = f"{cls.PREFIX}_"
        if not name.startswith(prefix):
            return None
        rest = name[len(prefix) :]
        tag, separator, body = rest.partition("_")
        if not separator or tag not in cls.KINDS:
            return None
        for suffix in cls.SUFFIXES:
            if body.endswith(suffix):
                body = body[: -len(suffix)]
                break
        parts = body.split("_")
        if len(parts) != cls.NAME_PARTS:
            return None
        try:
            scope = bytes.fromhex(parts[0]).decode("utf-8")
            key = bytes.fromhex(parts[1]).decode("utf-8")
        except ValueError:
            return None
        if not scope or not key:
            return None
        return Constraint(cls.KINDS[tag], scope, key)

    @classmethod
    def token(cls, constraint: Constraint) -> str:
        """Return the trigger diagnostic token for one node constraint.

        Parameters
        ----------
        constraint : Constraint
            Declared node constraint.

        Returns
        -------
        str
            Token such as ``pygrafito:constraint:node:<hex>:<hex>``.
        """
        scope = constraint.scope.encode("utf-8").hex()
        key = constraint.key.encode("utf-8").hex()
        return f"{cls.TOKEN_PREFIX}:{cls.TAGS[constraint.kind]}:{scope}:{key}"

    def all(self) -> tuple[Constraint, ...]:
        """Return every declared constraint in the database.

        Returns
        -------
        tuple[Constraint, ...]
            Declared constraints ordered by element kind, scope, and key.
        """
        declared: set[Constraint] = set()
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('index', 'trigger')"
        ).fetchall()
        for row in rows:
            parsed = self.parse_name(str(row[0]))
            if parsed is not None:
                declared.add(parsed)
        return tuple(sorted(declared, key=lambda item: item.ordering_key))

    def exists(self, constraint: Constraint) -> bool:
        """Report whether one constraint is declared.

        Parameters
        ----------
        constraint : Constraint
            Declared constraint.

        Returns
        -------
        bool
            ``True`` when its objects are present.
        """
        return bool(self._objects(constraint))

    def ddl(self, constraint: Constraint) -> tuple[str, ...]:
        """Render the statements that create one constraint.

        Parameters
        ----------
        constraint : Constraint
            Constraint to render.

        Returns
        -------
        tuple[str, ...]
            One statement for a relationship constraint, or three for a node
            constraint.
        """
        if constraint.kind is ElementKind.RELATIONSHIP:
            return self._relationship_ddl(constraint)
        return self._node_ddl(constraint)

    def create(self, constraint: Constraint) -> None:
        """Declare one constraint after validating the existing data.

        Validation and DDL run inside one ``BEGIN IMMEDIATE`` transaction, so
        a concurrent writer cannot insert a duplicate between the check and the
        trigger that would catch it.

        Parameters
        ----------
        constraint : Constraint
            Constraint to declare.

        Raises
        ------
        ConstraintViolationError
            If existing elements already duplicate a value inside the scope.
        """
        self._validate(constraint)
        if self.exists(constraint):
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            conflict = self.find_conflict(constraint)
            if conflict is not None:
                existing, value = conflict
                raise ConstraintViolationError(
                    constraint.kind,
                    constraint.scope,
                    constraint.key,
                    value,
                    existing,
                )
            for statement in self.ddl(constraint):
                self._connection.execute(statement)
        except BaseException:
            self._rollback()
            raise
        self._connection.execute("COMMIT")

    def drop(self, constraint: Constraint) -> None:
        """Remove every object that implements one constraint.

        Parameters
        ----------
        constraint : Constraint
            Constraint to remove.

        Raises
        ------
        NotFoundError
            If the constraint is not declared.
        """
        self._validate(constraint)
        objects = self._objects(constraint)
        if not objects:
            message = (
                f"uniqueness constraint on {constraint.kind.value} "
                f"{constraint.scope!r} key {constraint.key!r} does not exist"
            )
            raise NotFoundError(message)
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            for object_type, name in objects:
                statement = "DROP TRIGGER" if object_type == "trigger" else "DROP INDEX"
                self._connection.execute(f"{statement} {name}")
        except BaseException:
            self._rollback()
            raise
        self._connection.execute("COMMIT")

    def _relationship_ddl(self, constraint: Constraint) -> tuple[str, ...]:
        """Render the support index and triggers for a relationship constraint.

        Parameters
        ----------
        constraint : Constraint
            Relationship constraint.

        Returns
        -------
        tuple[str, ...]
            Support index, property trigger, and label trigger.
        """
        stem = self.name(constraint)
        path = self._codec.sql_json_path(constraint.key)
        label = self._quote(constraint.scope)
        token = self._quote(self.token(constraint))
        index = (
            f"CREATE INDEX IF NOT EXISTS {stem}_idx ON relationships "
            f"(json_extract(props, {path}), json_type(props, {path}))"
        )
        props = (
            f"CREATE TRIGGER IF NOT EXISTS {stem}_props "
            f"BEFORE UPDATE OF props ON relationships "
            f"WHEN EXISTS (SELECT 1 FROM relationship_labels "
            f"WHERE relationship_id = NEW.id AND label = {label}) "
            f"AND json_extract(NEW.props, {path}) IS NOT NULL "
            f"BEGIN "
            f"SELECT RAISE(ABORT, {token}) WHERE EXISTS ("
            f"SELECT 1 FROM relationships other "
            f"JOIN relationship_labels other_label ON other_label.relationship_id = other.id "
            f"WHERE other.id != NEW.id AND other_label.label = {label} "
            f"AND json_extract(other.props, {path}) IS NOT NULL "
            f"AND json_extract(other.props, {path}) = json_extract(NEW.props, {path}) "
            f"AND json_type(other.props, {path}) = json_type(NEW.props, {path})); "
            f"END"
        )
        labels = (
            f"CREATE TRIGGER IF NOT EXISTS {stem}_labels "
            f"AFTER INSERT ON relationship_labels "
            f"WHEN NEW.label = {label} "
            f"AND json_extract((SELECT props FROM relationships WHERE id = NEW.relationship_id), "
            f"{path}) IS NOT NULL "
            f"BEGIN "
            f"SELECT RAISE(ABORT, {token}) WHERE EXISTS ("
            f"SELECT 1 FROM relationships other "
            f"JOIN relationship_labels other_label ON other_label.relationship_id = other.id "
            f"WHERE other.id != NEW.relationship_id AND other_label.label = {label} "
            f"AND json_extract(other.props, {path}) IS NOT NULL "
            f"AND json_extract(other.props, {path}) = "
            f"json_extract((SELECT props FROM relationships WHERE id = NEW.relationship_id), "
            f"{path}) "
            f"AND json_type(other.props, {path}) = "
            f"json_type((SELECT props FROM relationships WHERE id = NEW.relationship_id), "
            f"{path})); "
            f"END"
        )
        return (index, props, labels)

    def _node_ddl(self, constraint: Constraint) -> tuple[str, ...]:
        """Render the support index and triggers for a node constraint.

        Parameters
        ----------
        constraint : Constraint
            Node constraint.

        Returns
        -------
        tuple[str, ...]
            Support index, property trigger, and label trigger.
        """
        stem = self.name(constraint)
        path = self._codec.sql_json_path(constraint.key)
        label = self._quote(constraint.scope)
        token = self._quote(self.token(constraint))
        index = (
            f"CREATE INDEX IF NOT EXISTS {stem}_idx ON nodes "
            f"(json_extract(props, {path}), json_type(props, {path}))"
        )
        props = (
            f"CREATE TRIGGER IF NOT EXISTS {stem}_props "
            f"BEFORE UPDATE OF props ON nodes "
            f"WHEN EXISTS (SELECT 1 FROM node_labels WHERE node_id = NEW.id AND label = {label}) "
            f"AND json_extract(NEW.props, {path}) IS NOT NULL "
            f"BEGIN "
            f"SELECT RAISE(ABORT, {token}) WHERE EXISTS ("
            f"SELECT 1 FROM nodes other "
            f"JOIN node_labels other_label ON other_label.node_id = other.id "
            f"WHERE other.id != NEW.id AND other_label.label = {label} "
            f"AND json_extract(other.props, {path}) IS NOT NULL "
            f"AND json_extract(other.props, {path}) = json_extract(NEW.props, {path}) "
            f"AND json_type(other.props, {path}) = json_type(NEW.props, {path})); "
            f"END"
        )
        labels = (
            f"CREATE TRIGGER IF NOT EXISTS {stem}_labels "
            f"AFTER INSERT ON node_labels "
            f"WHEN NEW.label = {label} "
            f"AND json_extract((SELECT props FROM nodes WHERE id = NEW.node_id), {path}) "
            f"IS NOT NULL "
            f"BEGIN "
            f"SELECT RAISE(ABORT, {token}) WHERE EXISTS ("
            f"SELECT 1 FROM nodes other "
            f"JOIN node_labels other_label ON other_label.node_id = other.id "
            f"WHERE other.id != NEW.node_id AND other_label.label = {label} "
            f"AND json_extract(other.props, {path}) IS NOT NULL "
            f"AND json_extract(other.props, {path}) = "
            f"json_extract((SELECT props FROM nodes WHERE id = NEW.node_id), {path}) "
            f"AND json_type(other.props, {path}) = "
            f"json_type((SELECT props FROM nodes WHERE id = NEW.node_id), {path})); "
            f"END"
        )
        return (index, props, labels)

    def find_conflict(self, constraint: Constraint) -> tuple[int, Value] | None:
        """Find one existing duplicate inside a constraint scope.

        Parameters
        ----------
        constraint : Constraint
            Constraint whose data is validated.

        Returns
        -------
        tuple[int, Value] | None
            Identifier of one element that holds a duplicated value and the
            value itself, or ``None`` when every value is distinct.
        """
        if constraint.kind is ElementKind.RELATIONSHIP:
            return self._find_relationship_conflict(constraint)
        return self._find_node_conflict(constraint)

    def holder(
        self,
        constraint: Constraint,
        value: Value,
        exclude_id: int | None = None,
    ) -> int | None:
        """Find an element that already holds one value inside a scope.

        Parameters
        ----------
        constraint : Constraint
            Constraint whose scope is searched.
        value : Value
            Value that the write attempted to store.
        exclude_id : int | None, optional
            Element that the write updated, by default ``None``.

        Returns
        -------
        int | None
            Identifier of a holder, or ``None`` when the value is free.
        """
        path = self._codec.sql_json_path(constraint.key)
        json_type = self._codec.json_type(value)
        comparison = self._codec.comparison_value(value)
        if constraint.kind is ElementKind.RELATIONSHIP:
            return self._relationship_holder(constraint, path, json_type, comparison, exclude_id)
        return self._node_holder(constraint, path, json_type, comparison, exclude_id)

    def _node_holder(
        self,
        constraint: Constraint,
        path: str,
        json_type: str,
        comparison: int | float | str,
        exclude_id: int | None,
    ) -> int | None:
        """Find a node that holds one value inside a label scope.

        Parameters
        ----------
        constraint : Constraint
            Node constraint whose scope is searched.
        path : str
            Quoted JSON path of the constrained key.
        json_type : str
            JSON type of the attempted value.
        comparison : int | float | str
            Value compared by SQLite.
        exclude_id : int | None
            Node that the write updated, or ``None``.

        Returns
        -------
        int | None
            Identifier of a holder, or ``None``.
        """
        clause = ""
        parameters: list[object] = [constraint.scope, json_type, comparison]
        if exclude_id is not None:
            clause = "AND nodes.id != ? "
            parameters.append(exclude_id)
        row = self._connection.execute(
            f"SELECT nodes.id FROM nodes "
            f"JOIN node_labels ON node_labels.node_id = nodes.id "
            f"WHERE node_labels.label = ? "
            f"AND json_type(nodes.props, {path}) = ? "
            f"AND json_extract(nodes.props, {path}) = ? "
            f"{clause}"
            f"ORDER BY nodes.id LIMIT 1",
            parameters,
        ).fetchone()
        return None if row is None else int(typing.cast(int, row[0]))

    def _relationship_holder(
        self,
        constraint: Constraint,
        path: str,
        json_type: str,
        comparison: int | float | str,
        exclude_id: int | None,
    ) -> int | None:
        """Find a relationship that holds one value inside a type scope.

        Parameters
        ----------
        constraint : Constraint
            Relationship constraint whose scope is searched.
        path : str
            Quoted JSON path of the constrained key.
        json_type : str
            JSON type of the attempted value.
        comparison : int | float | str
            Value compared by SQLite.
        exclude_id : int | None
            Relationship that the write updated, or ``None``.

        Returns
        -------
        int | None
            Identifier of a holder, or ``None``.
        """
        clause = ""
        parameters: list[object] = [constraint.scope, json_type, comparison]
        if exclude_id is not None:
            clause = "AND relationships.id != ? "
            parameters.append(exclude_id)
        row = self._connection.execute(
            f"SELECT relationships.id FROM relationships "
            f"JOIN relationship_labels ON relationship_labels.relationship_id = relationships.id "
            f"WHERE relationship_labels.label = ? "
            f"AND json_type(relationships.props, {path}) = ? "
            f"AND json_extract(relationships.props, {path}) = ? "
            f"{clause}"
            f"ORDER BY relationships.id LIMIT 1",
            parameters,
        ).fetchone()
        return None if row is None else int(typing.cast(int, row[0]))

    def _find_node_conflict(self, constraint: Constraint) -> tuple[int, Value] | None:
        """Find a duplicated value among nodes that carry one label.

        Parameters
        ----------
        constraint : Constraint
            Node constraint whose data is validated.

        Returns
        -------
        tuple[int, Value] | None
            Later duplicate id and value, or ``None``.
        """
        path = self._codec.sql_json_path(constraint.key)
        label = self._quote(constraint.scope)
        row = self._connection.execute(
            f"SELECT later.id, json_extract(later.props, {path}), "
            f"json_type(later.props, {path}) "
            f"FROM nodes later "
            f"JOIN node_labels later_label ON later_label.node_id = later.id "
            f"WHERE later_label.label = {label} "
            f"AND json_extract(later.props, {path}) IS NOT NULL "
            f"AND EXISTS ("
            f"SELECT 1 FROM nodes earlier "
            f"JOIN node_labels earlier_label ON earlier_label.node_id = earlier.id "
            f"WHERE earlier.id < later.id AND earlier_label.label = {label} "
            f"AND json_extract(earlier.props, {path}) = json_extract(later.props, {path}) "
            f"AND json_type(earlier.props, {path}) = json_type(later.props, {path})) "
            f"ORDER BY later.id LIMIT 1"
        ).fetchone()
        return self._conflict_from_row(row)

    def _find_relationship_conflict(
        self,
        constraint: Constraint,
    ) -> tuple[int, Value] | None:
        """Find a duplicated value among relationships of one type.

        Parameters
        ----------
        constraint : Constraint
            Relationship constraint whose data is validated.

        Returns
        -------
        tuple[int, Value] | None
            Later duplicate id and value, or ``None``.
        """
        path = self._codec.sql_json_path(constraint.key)
        label = self._quote(constraint.scope)
        row = self._connection.execute(
            f"SELECT later.id, json_extract(later.props, {path}), "
            f"json_type(later.props, {path}) "
            f"FROM relationships later "
            f"JOIN relationship_labels later_label "
            f"ON later_label.relationship_id = later.id "
            f"WHERE later_label.label = {label} "
            f"AND json_extract(later.props, {path}) IS NOT NULL "
            f"AND EXISTS ("
            f"SELECT 1 FROM relationships earlier "
            f"JOIN relationship_labels earlier_label "
            f"ON earlier_label.relationship_id = earlier.id "
            f"WHERE earlier.id < later.id AND earlier_label.label = {label} "
            f"AND json_extract(earlier.props, {path}) = json_extract(later.props, {path}) "
            f"AND json_type(earlier.props, {path}) = json_type(later.props, {path})) "
            f"ORDER BY later.id LIMIT 1"
        ).fetchone()
        return self._conflict_from_row(row)

    def _conflict_from_row(self, row: tuple[object, ...] | None) -> tuple[int, Value] | None:
        """Decode one duplicate row into an id and a property value.

        Parameters
        ----------
        row : tuple[object, ...] | None
            Row with id, extracted value, and JSON type.

        Returns
        -------
        tuple[int, Value] | None
            Decoded conflict, or ``None`` for an empty row.
        """
        if row is None:
            return None
        return (int(typing.cast(int, row[0])), self.decode_value(row[1], str(row[2])))

    def decode_value(self, raw: object, json_type: str) -> Value:
        """Rebuild a property value from SQLite's extracted value and type.

        Parameters
        ----------
        raw : object
            Value returned by ``json_extract``.
        json_type : str
            Value returned by ``json_type``.

        Returns
        -------
        Value
            The decoded property value.
        """
        if json_type == "true":
            return bool(int(typing.cast(int, raw)))
        if json_type == "false":
            return False
        if json_type == "array":
            decoded: object = json.loads(str(raw))
            return self._codec.validate_value(decoded)
        if json_type == "integer":
            return int(typing.cast(int, raw))
        if json_type == "real":
            return float(typing.cast(float, raw))
        return str(raw)

    def _objects(self, constraint: Constraint) -> tuple[tuple[str, str], ...]:
        """Return the SQLite objects that implement one constraint.

        Parameters
        ----------
        constraint : Constraint
            Constraint whose objects are looked up.

        Returns
        -------
        tuple[tuple[str, str], ...]
            Object type and name pairs, ordered for deterministic removal.
        """
        names = self.object_names(constraint)
        placeholders = ", ".join("?" for _ in names)
        rows = self._connection.execute(
            f"SELECT type, name FROM sqlite_master "
            f"WHERE type IN ('index', 'trigger') AND name IN ({placeholders}) "
            f"ORDER BY type DESC, name",
            list(names),
        ).fetchall()
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def _validate(self, constraint: Constraint) -> None:
        """Validate the identifiers a constraint embeds in SQL.

        Parameters
        ----------
        constraint : Constraint
            Constraint to validate.

        Raises
        ------
        ValidationError
            If the scope or key cannot be embedded in a statement.
        """
        field = "label"
        self._codec.validate_identifier(constraint.scope, field)
        self._codec.validate_identifier(constraint.key, "property key")

    def _rollback(self) -> None:
        """Roll back the current declaration transaction, ignoring failures."""
        try:
            self._connection.execute("ROLLBACK")
        except sqlite3.Error:
            return

    @staticmethod
    def _quote(value: str) -> str:
        """Render a string as an SQL literal.

        Parameters
        ----------
        value : str
            Text to embed.

        Returns
        -------
        str
            Single-quoted literal with internal quotes doubled.
        """
        return "'" + value.replace("'", "''") + "'"


class ConstraintTranslator:
    """Translate SQLite integrity failures into constraint violations.

    Translation is conservative: a failure counts only when its message names
    an object this registry would have created and that object is still
    declared.

    Parameters
    ----------
    connection : Connection
        Open connection to the graph database.
    codec : PropertyCodec
        Codec used to render quoted JSON paths and type predicates.
    registry : ConstraintRegistry | None, optional
        Registry consulted for decoded names and diagnostic lookups, by
        default a new registry on the same connection.
    """

    INDEX_MARKER: typing.ClassVar[str] = "unique constraint failed: index '"
    TOKEN_PREFIX: typing.ClassVar[str] = "pygrafito:constraint:"
    TOKEN_PARTS: typing.ClassVar[int] = 5

    def __init__(
        self,
        connection: Connection,
        codec: PropertyCodec,
        registry: ConstraintRegistry | None = None,
    ) -> None:
        self._registry = ConstraintRegistry(connection, codec) if registry is None else registry

    def translate(
        self,
        error: sqlite3.IntegrityError,
        *,
        properties: Mapping[str, Value] | None = None,
        labels: Iterable[str] = (),
        rel_labels: Iterable[str] = (),
        exclude_id: int | None = None,
    ) -> ConstraintViolationError | None:
        """Translate one SQLite failure when it is a uniqueness violation.

        Parameters
        ----------
        error : sqlite3.IntegrityError
            Failure raised by SQLite.
        properties : Mapping[str, Value] | None, optional
            Values the failed write attempted to store, by default unknown.
        labels : Iterable[str], optional
            Node labels the failed write touched, by default none.
        rel_labels : Iterable[str], optional
            Relationship labels the failed write touched, by default none.
        exclude_id : int | None, optional
            Element the failed write updated, by default ``None``.

        Returns
        -------
        ConstraintViolationError | None
            The violation, or ``None`` when the failure is not one of ours.
        """
        constraint = self._constraint(str(error))
        if constraint is None:
            return None
        if not self._matches_scope(constraint, labels, rel_labels):
            return None
        value = None if properties is None else properties.get(constraint.key)
        if value is None:
            conflict = self._registry.find_conflict(constraint)
            if conflict is not None:
                return ConstraintViolationError(
                    constraint.kind,
                    constraint.scope,
                    constraint.key,
                    conflict[1],
                    conflict[0],
                )
        existing = None if value is None else self._registry.holder(constraint, value, exclude_id)
        return ConstraintViolationError(
            constraint.kind,
            constraint.scope,
            constraint.key,
            value,
            existing,
        )

    def _constraint(self, message: str) -> Constraint | None:
        """Decode the constraint named by a SQLite failure message.

        Parameters
        ----------
        message : str
            SQLite failure text.

        Returns
        -------
        Constraint | None
            The declared constraint, or ``None`` when the message is not one of
            ours.
        """
        candidate = self._index_constraint(message)
        if candidate is None:
            candidate = self._token_constraint(message)
        if candidate is None or not self._registry.exists(candidate):
            return None
        return candidate

    def _index_constraint(self, message: str) -> Constraint | None:
        """Decode a ``UNIQUE constraint failed: index`` message.

        Parameters
        ----------
        message : str
            SQLite failure text.

        Returns
        -------
        Constraint | None
            The decoded relationship constraint, or ``None``.
        """
        marker = self._find_ignore_case(message, self.INDEX_MARKER)
        if marker < 0:
            return None
        start = marker + len(self.INDEX_MARKER)
        end = message.find("'", start)
        if end <= start:
            return None
        constraint = self._registry.parse_name(message[start:end])
        if constraint is None or constraint.kind is not ElementKind.RELATIONSHIP:
            return None
        return constraint

    def _token_constraint(self, message: str) -> Constraint | None:
        """Decode a trigger diagnostic token.

        Parameters
        ----------
        message : str
            SQLite failure text.

        Returns
        -------
        Constraint | None
            The decoded node constraint, or ``None``.
        """
        index = message.find(self.TOKEN_PREFIX)
        if index < 0:
            return None
        token = message[index:].split()[0]
        parts = token.split(":")
        if len(parts) != self.TOKEN_PARTS:
            return None
        kind = self._registry.KINDS.get(parts[2])
        if kind is None:
            return None
        try:
            scope = bytes.fromhex(parts[3]).decode("utf-8")
            key = bytes.fromhex(parts[4]).decode("utf-8")
        except ValueError:
            return None
        if not scope or not key:
            return None
        return Constraint(kind, scope, key)

    @staticmethod
    def _matches_scope(
        constraint: Constraint,
        labels: Iterable[str],
        rel_labels: Iterable[str],
    ) -> bool:
        """Report whether a write could have touched a constraint scope.

        Parameters
        ----------
        constraint : Constraint
            Candidate constraint.
        labels : Iterable[str]
            Node labels the write touched.
        rel_labels : Iterable[str]
            Relationship labels the write touched.

        Returns
        -------
        bool
            ``True`` when the constraint is relevant to the write.
        """
        if constraint.kind is ElementKind.NODE:
            return not labels or constraint.scope in labels
        return not rel_labels or constraint.scope in rel_labels

    @staticmethod
    def _find_ignore_case(message: str, fragment: str) -> int:
        """Find a fragment ignoring ASCII case.

        Parameters
        ----------
        message : str
            Text to search.
        fragment : str
            Lower-case fragment to find.

        Returns
        -------
        int
            Index of the fragment, or ``-1``.
        """
        return message.lower().find(fragment)
