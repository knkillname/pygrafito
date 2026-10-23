# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Domain model for the embedded property graph."""

import dataclasses
import typing
from collections.abc import Iterator, Mapping
from enum import Enum
from types import MappingProxyType
from typing import ClassVar

type Scalar = bool | int | float | str
"""A scalar value accepted by the property store."""

type Value = Scalar | list[Scalar]
"""A property value accepted by the property store."""


class Direction(Enum):
    """Relationship direction used by traversal operations."""

    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class PygrafitoError(Exception):
    """Base class for every error raised by pygrafito."""


class GraphClosedError(PygrafitoError):
    """Raised when an operation uses a graph handle that is already closed."""


class ValidationError(PygrafitoError):
    """Raised when a value, identifier, or traversal request is invalid."""


class NotFoundError(PygrafitoError):
    """Raised when a requested node or relationship does not exist."""


class ConnectedNodeError(PygrafitoError):
    """Raised when deleting a node that still has relationships."""


class TransactionError(PygrafitoError):
    """Raised when a transaction cannot be started, committed, or reused."""


class UnsupportedSqliteError(PygrafitoError):
    """Raised when the SQLite runtime cannot provide the required features."""


class QueryError(PygrafitoError):
    """Base class for every query-language failure.

    Parameters
    ----------
    message : str
        Description of the failure.
    line : int | None, optional
        One-based source line of the failure, by default ``None``.
    column : int | None, optional
        One-based source column of the failure, by default ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        location = ""
        if line is not None and column is not None:
            location = f" (line {line}, column {column})"
        super().__init__(f"{message}{location}")


class QuerySyntaxError(QueryError):
    """Raised when a query cannot be lexed or parsed."""


class QuerySemanticError(QueryError):
    """Raised when a parsed query violates the dialect's static rules."""


class QueryExecutionError(QueryError):
    """Raised when a query fails while it is being evaluated."""


class _PropertyMapping(Mapping[str, Value]):
    """Read-only mapping behavior shared by element snapshots."""

    __slots__: ClassVar[tuple[str, ...]] = ()

    @property
    def properties(self) -> Mapping[str, Value]:
        """Return the immutable property mapping.

        Returns
        -------
        Mapping[str, Value]
            Properties exposed by the concrete snapshot.
        """
        raise NotImplementedError

    @typing.override
    def __getitem__(self, key: str) -> Value:
        """Return one property value.

        Parameters
        ----------
        key : str
            Property key to look up.

        Returns
        -------
        Value
            The stored property value.
        """
        return self.properties[key]

    @typing.override
    def __iter__(self) -> Iterator[str]:
        """Iterate over property keys.

        Returns
        -------
        Iterator[str]
            Iterator over the property keys.
        """
        return iter(self.properties)

    @typing.override
    def __len__(self) -> int:
        """Return the number of properties.

        Returns
        -------
        int
            Number of stored properties.
        """
        return len(self.properties)

    @staticmethod
    def _freeze(
        properties: Mapping[str, Value],
    ) -> MappingProxyType[str, Value]:
        """Copy a property mapping into an immutable proxy.

        Parameters
        ----------
        properties : Mapping[str, Value]
            Properties to protect.

        Returns
        -------
        MappingProxyType[str, Value]
            A read-only copy of the properties.
        """
        return MappingProxyType(dict(properties))


@dataclasses.dataclass(frozen=True, slots=True)
class Node(_PropertyMapping):
    """An immutable snapshot of a graph node.

    Parameters
    ----------
    id : int
        Database identifier of the node.
    labels : frozenset[str]
        Labels attached to the node.
    properties : Mapping[str, Value]
        Properties attached to the node.
    """

    id: int
    labels: frozenset[str] = dataclasses.field(default_factory=frozenset)
    properties: Mapping[str, Value] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze labels and properties into immutable containers."""
        object.__setattr__(self, "labels", frozenset(self.labels))
        object.__setattr__(self, "properties", self._freeze(self.properties))


@dataclasses.dataclass(frozen=True, slots=True)
class Relationship(_PropertyMapping):
    """An immutable snapshot of a directed, typed relationship.

    Parameters
    ----------
    id : int
        Database identifier of the relationship.
    rel_type : str
        Non-empty relationship type.
    start_id : int
        Identifier of the start node.
    end_id : int
        Identifier of the end node.
    properties : Mapping[str, Value]
        Properties attached to the relationship.
    """

    id: int
    rel_type: str
    start_id: int
    end_id: int
    properties: Mapping[str, Value] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze properties into an immutable container."""
        object.__setattr__(self, "properties", self._freeze(self.properties))


@dataclasses.dataclass(frozen=True, slots=True)
class Path:
    """An immutable sequence of nodes connected by relationships.

    Parameters
    ----------
    nodes : tuple[Node, ...]
        Nodes ordered from the start of the path to the end.
    relationships : tuple[Relationship, ...]
        Relationships in traversal order.

    Raises
    ------
    ValidationError
        If the path is empty or its node and relationship counts disagree.
    """

    nodes: tuple[Node, ...]
    relationships: tuple[Relationship, ...]

    def __post_init__(self) -> None:
        """Materialize and validate the path sequences."""
        nodes = tuple(self.nodes)
        relationships = tuple(self.relationships)
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "relationships", relationships)
        if not nodes:
            message = "a path must contain at least one node"
            raise ValidationError(message)
        if len(nodes) != len(relationships) + 1:
            message = "a path must contain exactly one more node than relationships"
            raise ValidationError(message)

    @property
    def length(self) -> int:
        """Return the number of relationships in the path.

        Returns
        -------
        int
            Number of relationships in the path.
        """
        return len(self.relationships)

    @property
    def start(self) -> Node:
        """Return the first node of the path.

        Returns
        -------
        Node
            The start node.
        """
        return self.nodes[0]

    @property
    def end(self) -> Node:
        """Return the last node of the path.

        Returns
        -------
        Node
            The end node.
        """
        return self.nodes[-1]


@dataclasses.dataclass(frozen=True, slots=True)
class TraversalStep:
    """A node reached by traversal together with its shortest depth.

    Parameters
    ----------
    node : Node
        The reached node.
    depth : int
        Number of relationships between the traversal start and this node.
    """

    node: Node
    depth: int


__all__ = [
    "ConnectedNodeError",
    "Direction",
    "GraphClosedError",
    "Node",
    "NotFoundError",
    "Path",
    "PygrafitoError",
    "QueryError",
    "QueryExecutionError",
    "QuerySemanticError",
    "QuerySyntaxError",
    "Relationship",
    "Scalar",
    "TransactionError",
    "TraversalStep",
    "UnsupportedSqliteError",
    "ValidationError",
    "Value",
]
