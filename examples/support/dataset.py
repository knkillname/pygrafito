# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Shared dataset loading, validation, and synthetic generation for examples."""

import dataclasses
import json
import math
import pathlib
import random
import typing
from collections.abc import Mapping, Sequence

from pygrafito import Graph, Node, PygrafitoError
from pygrafito.model import Value


class DatasetError(PygrafitoError):
    """Raised when an example dataset is malformed or cannot be merged."""


@dataclasses.dataclass(frozen=True, slots=True)
class NodeSpec:
    """One validated node declaration.

    Parameters
    ----------
    key : str
        Stable string handle used by relationships and merges.
    labels : tuple[str, ...]
        Labels attached to the node.
    properties : Mapping[str, Value]
        Typed properties attached to the node.
    """

    key: str
    labels: tuple[str, ...]
    properties: Mapping[str, Value]


@dataclasses.dataclass(frozen=True, slots=True)
class RelationshipSpec:
    """One validated relationship declaration.

    Parameters
    ----------
    start : str
        Handle of the first endpoint.
    end : str
        Handle of the second endpoint.
    labels : tuple[str, ...]
        Labels attached to the relationship.
    directed : bool
        Whether the endpoints carry source and destination meaning.
    properties : Mapping[str, Value]
        Typed properties attached to the relationship.
    """

    start: str
    end: str
    labels: tuple[str, ...]
    directed: bool
    properties: Mapping[str, Value]


@dataclasses.dataclass(frozen=True, slots=True)
class IndexSpec:
    """One declared property index.

    Parameters
    ----------
    kind : str
        ``node`` or ``relationship``.
    key : str
        Property key the index covers.
    """

    kind: str
    key: str


@dataclasses.dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """One declared uniqueness constraint.

    Parameters
    ----------
    kind : str
        ``node`` or ``relationship``.
    scope : str
        Label the constraint covers.
    key : str
        Property key whose values must stay distinct.
    """

    kind: str
    scope: str
    key: str


@dataclasses.dataclass(frozen=True, slots=True)
class DatasetDocument:
    """One validated dataset document.

    Parameters
    ----------
    name : str
        Dataset name.
    revision : int
        Source revision number.
    nodes : tuple[NodeSpec, ...]
        Declared nodes.
    relationships : tuple[RelationshipSpec, ...]
        Declared relationships.
    indexes : tuple[IndexSpec, ...]
        Property indexes applied to database output.
    constraints : tuple[ConstraintSpec, ...]
        Uniqueness constraints applied to database output.
    """

    name: str
    revision: int
    nodes: tuple[NodeSpec, ...]
    relationships: tuple[RelationshipSpec, ...]
    indexes: tuple[IndexSpec, ...] = ()
    constraints: tuple[ConstraintSpec, ...] = ()


@dataclasses.dataclass(frozen=True, slots=True)
class SeedSummary:
    """Counts produced by seeding one dataset.

    Parameters
    ----------
    nodes : int
        Number of created nodes.
    relationships : int
        Number of created relationships.
    """

    nodes: int
    relationships: int


class Dataset:
    """Load, validate, merge, and seed the curated example datasets."""

    DATA_DIRECTORY: typing.ClassVar[pathlib.Path] = (
        pathlib.Path(__file__).resolve().parents[1] / "data"
    )
    NAMES: typing.ClassVar[tuple[str, ...]] = ("grid", "cast", "places", "all")
    SOURCE_NAMES: typing.ClassVar[tuple[str, ...]] = ("grid", "cast", "places")
    KINDS: typing.ClassVar[tuple[str, ...]] = ("node", "relationship")

    @classmethod
    def path(cls, name: str) -> pathlib.Path:
        """Return the source path of one dataset.

        Parameters
        ----------
        name : str
            Dataset name.

        Returns
        -------
        pathlib.Path
            Path to the dataset JSON file.

        Raises
        ------
        DatasetError
            If the name is not a declared source dataset.
        """
        if name not in cls.SOURCE_NAMES:
            message = f"unknown dataset {name!r}; expected one of {', '.join(cls.SOURCE_NAMES)}"
            raise DatasetError(message)
        return cls.DATA_DIRECTORY / f"{name}.json"

    @classmethod
    def load(cls, name: str) -> DatasetDocument:
        """Load one dataset, merging sources when asked for ``all``.

        Parameters
        ----------
        name : str
            Dataset name, including ``all``.

        Returns
        -------
        DatasetDocument
            Validated document.

        Raises
        ------
        DatasetError
            If the name is unknown or the source is malformed.
        """
        if name == "all":
            return cls.merge([cls.load(source) for source in cls.SOURCE_NAMES], name=name)
        path = cls.path(name)
        if not path.exists():
            message = f"dataset source does not exist: {path}"
            raise DatasetError(message)
        return cls.parse(json.loads(path.read_text(encoding="utf-8")), name=name)

    @classmethod
    def parse(cls, payload: object, *, name: str = "dataset") -> DatasetDocument:
        """Validate one decoded JSON document.

        Parameters
        ----------
        payload : object
            Decoded JSON value.
        name : str, optional
            Fallback dataset name, by default ``dataset``.

        Returns
        -------
        DatasetDocument
            Validated document.

        Raises
        ------
        DatasetError
            If the document shape, handles, endpoints, or values are invalid.
        """
        if not isinstance(payload, dict):
            message = "dataset must be a JSON object"
            raise DatasetError(message)
        document_name = payload.get("name", name)
        if not isinstance(document_name, str) or not document_name:
            message = "dataset name must be a non-empty string"
            raise DatasetError(message)
        revision = payload.get("revision", 1)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            message = "dataset revision must be a positive integer"
            raise DatasetError(message)
        raw_nodes = payload.get("nodes", [])
        raw_relationships = payload.get("relationships", [])
        if not isinstance(raw_nodes, list):
            message = "dataset nodes must be a list"
            raise DatasetError(message)
        if not isinstance(raw_relationships, list):
            message = "dataset relationships must be a list"
            raise DatasetError(message)
        nodes = tuple(cls._parse_node(raw) for raw in raw_nodes)
        seen: set[str] = set()
        for node in nodes:
            if node.key in seen:
                message = f"duplicate node handle: {node.key}"
                raise DatasetError(message)
            seen.add(node.key)
        relationships = tuple(cls._parse_relationship(raw) for raw in raw_relationships)
        for relationship in relationships:
            for endpoint in (relationship.start, relationship.end):
                if endpoint not in seen:
                    message = f"relationship names unknown endpoint: {endpoint}"
                    raise DatasetError(message)
        cls._require_identifier_keys((*nodes, *relationships))
        return DatasetDocument(
            name=document_name,
            revision=revision,
            nodes=nodes,
            relationships=relationships,
            indexes=tuple(cls._parse_index(raw) for raw in cls._list_field(payload, "indexes")),
            constraints=tuple(
                cls._parse_constraint(raw) for raw in cls._list_field(payload, "constraints")
            ),
        )

    @classmethod
    def merge(cls, documents: Sequence[DatasetDocument], *, name: str = "all") -> DatasetDocument:
        """Merge datasets by handle, rejecting conflicting values.

        Parameters
        ----------
        documents : Sequence[DatasetDocument]
            Documents to merge in order.
        name : str, optional
            Name of the merged document, by default ``all``.

        Returns
        -------
        DatasetDocument
            Merged document with union labels and properties.

        Raises
        ------
        DatasetError
            If one handle carries conflicting labels or property values.
        """
        nodes: dict[str, NodeSpec] = {}
        relationships: list[RelationshipSpec] = []
        seen_relationships: set[tuple[object, ...]] = set()
        indexes: dict[tuple[str, str], IndexSpec] = {}
        constraints: dict[tuple[str, str, str], ConstraintSpec] = {}
        for document in documents:
            for node in document.nodes:
                current = nodes.get(node.key)
                nodes[node.key] = node if current is None else cls._merge_node(current, node)
            for relationship in document.relationships:
                key = cls._relationship_key(relationship)
                if key not in seen_relationships:
                    seen_relationships.add(key)
                    relationships.append(relationship)
            for index in document.indexes:
                indexes[(index.kind, index.key)] = index
            for constraint in document.constraints:
                constraints[(constraint.kind, constraint.scope, constraint.key)] = constraint
        return DatasetDocument(
            name=name,
            revision=max((document.revision for document in documents), default=1),
            nodes=tuple(sorted(nodes.values(), key=lambda node: node.key)),
            relationships=tuple(relationships),
            indexes=tuple(indexes.values()),
            constraints=tuple(constraints.values()),
        )

    @classmethod
    def seed(cls, document: DatasetDocument, graph: Graph) -> SeedSummary:
        """Create every node and relationship in one transaction.

        Parameters
        ----------
        document : DatasetDocument
            Validated dataset document.
        graph : Graph
            Writable graph to populate.

        Returns
        -------
        SeedSummary
            Number of created nodes and relationships.

        Raises
        ------
        DatasetError
            If a value cannot be passed to the public API.
        """
        created: dict[str, Node] = {}
        relationships = 0
        with graph.transaction() as transaction:
            for node in sorted(document.nodes, key=lambda item: item.key):
                cls._require_identifier_properties(node)
                created[node.key] = transaction.add_node(*node.labels, **node.properties)
            for relationship in sorted(document.relationships, key=cls._relationship_key):
                cls._require_identifier_properties(relationship)
                transaction.add_relationship(
                    created[relationship.start],
                    relationship.labels,
                    created[relationship.end],
                    directed=relationship.directed,
                    **relationship.properties,
                )
                relationships += 1
        return SeedSummary(nodes=len(created), relationships=relationships)

    @classmethod
    def apply_schema(cls, document: DatasetDocument, graph: Graph) -> None:
        """Create the document's indexes and constraints.

        Parameters
        ----------
        document : DatasetDocument
            Validated dataset document.
        graph : Graph
            Writable graph whose current state should be indexed.

        Raises
        ------
        DatasetError
            If an index or constraint kind is unknown.
        """
        for index in document.indexes:
            if index.kind == "node":
                graph.create_node_index(index.key)
            elif index.kind == "relationship":
                graph.create_relationship_index(index.key)
            else:
                message = f"unknown index kind: {index.kind}"
                raise DatasetError(message)
        for constraint in document.constraints:
            if constraint.kind == "node":
                graph.create_node_uniqueness_constraint(constraint.scope, constraint.key)
            elif constraint.kind == "relationship":
                graph.create_relationship_uniqueness_constraint(constraint.scope, constraint.key)
            else:
                message = f"unknown constraint kind: {constraint.kind}"
                raise DatasetError(message)

    @classmethod
    def _parse_node(cls, payload: object) -> NodeSpec:
        """Validate one raw node declaration.

        Parameters
        ----------
        payload : object
            Decoded node declaration.

        Returns
        -------
        NodeSpec
            Validated node.

        Raises
        ------
        DatasetError
            If the declaration is malformed.
        """
        if not isinstance(payload, dict):
            message = "node declaration must be an object"
            raise DatasetError(message)
        key = cls._string(payload.get("key"), "node key")
        labels = cls._labels(payload.get("labels", []), f"node {key} labels")
        properties = cls._properties(payload.get("properties", {}), f"node {key} properties")
        return NodeSpec(key=key, labels=labels, properties=properties)

    @classmethod
    def _parse_relationship(cls, payload: object) -> RelationshipSpec:
        """Validate one raw relationship declaration.

        Parameters
        ----------
        payload : object
            Decoded relationship declaration.

        Returns
        -------
        RelationshipSpec
            Validated relationship.

        Raises
        ------
        DatasetError
            If the declaration is malformed.
        """
        if not isinstance(payload, dict):
            message = "relationship declaration must be an object"
            raise DatasetError(message)
        start = cls._string(payload.get("from"), "relationship source")
        end = cls._string(payload.get("to"), "relationship target")
        labels = cls._labels(payload.get("labels", []), f"relationship {start}->{end} labels")
        directed = payload.get("directed", True)
        if not isinstance(directed, bool):
            message = f"relationship {start}->{end} directed must be a boolean"
            raise DatasetError(message)
        properties = cls._properties(
            payload.get("properties", {}),
            f"relationship {start}->{end} properties",
        )
        return RelationshipSpec(
            start=start,
            end=end,
            labels=labels,
            directed=directed,
            properties=properties,
        )

    @classmethod
    def _parse_index(cls, payload: object) -> IndexSpec:
        """Validate one index declaration.

        Parameters
        ----------
        payload : object
            Decoded index declaration.

        Returns
        -------
        IndexSpec
            Validated index.

        Raises
        ------
        DatasetError
            If the kind or key is invalid.
        """
        if not isinstance(payload, dict):
            message = "index declaration must be an object"
            raise DatasetError(message)
        kind = cls._string(payload.get("kind"), "index kind")
        if kind not in cls.KINDS:
            message = f"unknown index kind: {kind}"
            raise DatasetError(message)
        key = cls._string(payload.get("key"), "index key")
        return IndexSpec(kind=kind, key=key)

    @classmethod
    def _parse_constraint(cls, payload: object) -> ConstraintSpec:
        """Validate one constraint declaration.

        Parameters
        ----------
        payload : object
            Decoded constraint declaration.

        Returns
        -------
        ConstraintSpec
            Validated constraint.

        Raises
        ------
        DatasetError
            If the kind, scope, or key is invalid.
        """
        if not isinstance(payload, dict):
            message = "constraint declaration must be an object"
            raise DatasetError(message)
        kind = cls._string(payload.get("kind"), "constraint kind")
        if kind not in cls.KINDS:
            message = f"unknown constraint kind: {kind}"
            raise DatasetError(message)
        scope = cls._string(payload.get("scope"), "constraint scope")
        key = cls._string(payload.get("key"), "constraint key")
        return ConstraintSpec(kind=kind, scope=scope, key=key)

    @classmethod
    def _merge_node(cls, current: NodeSpec, incoming: NodeSpec) -> NodeSpec:
        """Merge two declarations of the same handle.

        Parameters
        ----------
        current : NodeSpec
            Node already merged.
        incoming : NodeSpec
            Node from the next document.

        Returns
        -------
        NodeSpec
            Node with union labels and properties.

        Raises
        ------
        DatasetError
            If a shared property key carries different values.
        """
        properties = dict(current.properties)
        for key, value in incoming.properties.items():
            if key in properties and properties[key] != value:
                message = f"conflicting property {key!r} on node {current.key!r}"
                raise DatasetError(message)
            properties[key] = value
        return NodeSpec(
            key=current.key,
            labels=tuple(sorted(set(current.labels) | set(incoming.labels))),
            properties=properties,
        )

    @classmethod
    def _relationship_key(cls, relationship: RelationshipSpec) -> tuple[object, ...]:
        """Return a deterministic identity for one relationship declaration.

        Parameters
        ----------
        relationship : RelationshipSpec
            Relationship to identify.

        Returns
        -------
        tuple[object, ...]
            Endpoint, label, direction, and canonical property values.
        """
        return (
            relationship.start,
            relationship.end,
            relationship.labels,
            relationship.directed,
            json.dumps(relationship.properties, sort_keys=True, separators=(",", ":")),
        )

    @classmethod
    def _require_identifier_keys(cls, specs: Sequence[NodeSpec | RelationshipSpec]) -> None:
        """Require identifier-safe property keys for every declaration.

        Parameters
        ----------
        specs : Sequence[NodeSpec | RelationshipSpec]
            Declarations whose property keys are checked.

        Raises
        ------
        DatasetError
            If a property key is not a Python identifier.
        """
        for spec in specs:
            cls._require_identifier_properties(spec)

    @classmethod
    def _require_identifier_properties(cls, spec: NodeSpec | RelationshipSpec) -> None:
        """Require property keys that can be passed as keyword arguments.

        Parameters
        ----------
        spec : NodeSpec | RelationshipSpec
            Declaration whose properties are checked.

        Raises
        ------
        DatasetError
            If a property key is not a Python identifier.
        """
        for key in spec.properties:
            if not key.isidentifier():
                message = f"property key {key!r} is not an identifier"
                raise DatasetError(message)

    @classmethod
    def _properties(cls, payload: object, field: str) -> dict[str, Value]:
        """Validate one property map.

        Parameters
        ----------
        payload : object
            Decoded property map.
        field : str
            Human-readable field name for error messages.

        Returns
        -------
        dict[str, Value]
            Validated properties.

        Raises
        ------
        DatasetError
            If the map or a value is invalid.
        """
        if not isinstance(payload, dict):
            message = f"{field} must be an object"
            raise DatasetError(message)
        properties: dict[str, Value] = {}
        for key, value in payload.items():
            if not isinstance(key, str) or not key:
                message = f"{field} keys must be non-empty strings"
                raise DatasetError(message)
            properties[key] = cls._value(value, f"{field}.{key}")
        return properties

    @classmethod
    def _value(cls, value: object, field: str) -> Value:
        """Validate one property value.

        Parameters
        ----------
        value : object
            Candidate value.
        field : str
            Human-readable field name for error messages.

        Returns
        -------
        Value
            Validated value.

        Raises
        ------
        DatasetError
            If the value is not a scalar or a homogeneous scalar list.
        """
        if isinstance(value, list):
            kind: str | None = None
            items: list[bool | int | float | str] = []
            for item in value:
                item_kind = cls._scalar_kind(item, field)
                if kind is None:
                    kind = item_kind
                elif kind != item_kind:
                    message = f"{field} must contain values of one scalar type"
                    raise DatasetError(message)
                items.append(typing.cast(bool | int | float | str, item))
            return items
        cls._scalar_kind(value, field)
        return typing.cast(Value, value)

    @classmethod
    def _scalar_kind(cls, value: object, field: str) -> str:
        """Return the kind of one scalar, rejecting unsupported values.

        Parameters
        ----------
        value : object
            Candidate scalar.
        field : str
            Human-readable field name for error messages.

        Returns
        -------
        str
            ``bool``, ``int``, ``float``, or ``str``.

        Raises
        ------
        DatasetError
            If the value is unsupported, non-finite, or out of range.
        """
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            if not -(2**63) <= value <= 2**63 - 1:
                message = f"{field} integer is outside the signed 64-bit range"
                raise DatasetError(message)
            return "int"
        if isinstance(value, float):
            if not math.isfinite(value):
                message = f"{field} float must be finite"
                raise DatasetError(message)
            return "float"
        if isinstance(value, str):
            return "str"
        message = f"{field} has unsupported value type: {type(value).__name__}"
        raise DatasetError(message)

    @classmethod
    def _labels(cls, payload: object, field: str) -> tuple[str, ...]:
        """Validate a label list.

        Parameters
        ----------
        payload : object
            Decoded label list.
        field : str
            Human-readable field name for error messages.

        Returns
        -------
        tuple[str, ...]
            Sorted unique labels.

        Raises
        ------
        DatasetError
            If the list contains an invalid label.
        """
        if not isinstance(payload, list):
            message = f"{field} must be a list"
            raise DatasetError(message)
        return tuple(sorted({cls._string(item, field) for item in payload}))

    @classmethod
    def _string(cls, value: object, field: str) -> str:
        """Validate a non-empty string.

        Parameters
        ----------
        value : object
            Candidate string.
        field : str
            Human-readable field name for error messages.

        Returns
        -------
        str
            Validated string.

        Raises
        ------
        DatasetError
            If the value is not a non-empty string.
        """
        if not isinstance(value, str) or not value:
            message = f"{field} must be a non-empty string"
            raise DatasetError(message)
        return value

    @classmethod
    def _list_field(cls, payload: Mapping[str, object], key: str) -> list[object]:
        """Return an optional list field.

        Parameters
        ----------
        payload : Mapping[str, object]
            Decoded document.
        key : str
            Field name.

        Returns
        -------
        list[object]
            Field value, or an empty list when absent.

        Raises
        ------
        DatasetError
            If the field is not a list.
        """
        value = payload.get(key, [])
        if not isinstance(value, list):
            message = f"dataset {key} must be a list"
            raise DatasetError(message)
        return value


class Synthetic:
    """Seed a deterministic themed graph for scale demonstrations.

    Parameters
    ----------
    nodes : int
        Number of nodes to create.
    relationships : int
        Number of relationships to create.
    seed : int, optional
        Seed used to select names and regions, by default 0.
    """

    NAMES: typing.ClassVar[tuple[str, ...]] = (
        "tron",
        "flynn",
        "quorra",
        "rinzler",
        "sark",
        "yori",
        "ram",
        "crom",
        "dumont",
        "mcp",
        "clu",
        "ares",
        "athena",
        "eve-kim",
        "tess-kim",
        "seth",
        "julian-dillinger",
        "elisabeth-dillinger",
        "anjay",
        "jolene",
    )
    REGIONS: typing.ClassVar[tuple[str, ...]] = (
        "the-grid",
        "real-world",
        "encom",
        "dillinger-systems",
        "outlands",
        "sea-of-simulation",
        "end-of-line",
    )
    CYCLE_MODULUS: typing.ClassVar[int] = 97
    CHAIN_LENGTH: typing.ClassVar[int] = 5
    MINIMUM_RELATIONSHIP_NODES: typing.ClassVar[int] = 2

    def __init__(self, nodes: int, relationships: int, seed: int = 0) -> None:
        if isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 0:
            message = "nodes must be a non-negative integer"
            raise DatasetError(message)
        if (
            isinstance(relationships, bool)
            or not isinstance(relationships, int)
            or relationships < 0
        ):
            message = "relationships must be a non-negative integer"
            raise DatasetError(message)
        if relationships and nodes < Synthetic.MINIMUM_RELATIONSHIP_NODES:
            message = "synthetic relationships require at least two nodes"
            raise DatasetError(message)
        if isinstance(seed, bool) or not isinstance(seed, int):
            message = "seed must be an integer"
            raise DatasetError(message)
        self._nodes = nodes
        self._relationships = relationships
        self._seed = seed

    def build(self, graph: Graph) -> list[Node]:
        """Create the synthetic graph.

        Parameters
        ----------
        graph : Graph
            Graph to populate.

        Returns
        -------
        list[Node]
            Created nodes in insertion order.
        """
        generator = random.Random(self._seed)
        created: list[Node] = []
        with graph.transaction() as transaction:
            for position in range(self._nodes):
                label = "Program" if position % 10 == 0 else "Agent"
                name = generator.choice(self.NAMES)
                created.append(
                    transaction.add_node(
                        label,
                        designation=f"{name}-{position}",
                        cycles=position % self.CYCLE_MODULUS,
                        region=generator.choice(self.REGIONS),
                    )
                )
        if not created:
            return created
        chain = min(self.CHAIN_LENGTH, self._relationships, len(created) - 1)
        random_relationships = self._relationships - chain
        with graph.transaction() as transaction:
            for position in range(random_relationships):
                start = created[position % len(created)]
                end = created[(position * 7 + 13) % len(created)]
                if start.id == end.id:
                    end = created[(position * 7 + 14) % len(created)]
                label = "TRANSMISSION" if position % 100 == 0 else "ALLIES_WITH"
                transaction.add_relationship(
                    start,
                    label,
                    end,
                    directed=position % 10 != 0,
                    since_cycle=2000 + position % 20,
                )
        if chain:
            with graph.transaction() as transaction:
                for position in range(chain):
                    transaction.add_relationship(
                        created[position],
                        "TRANSITION",
                        created[position + 1],
                    )
        return created
