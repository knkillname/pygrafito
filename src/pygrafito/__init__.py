# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Public package surface for the embedded property graph."""

from pygrafito.engine.graph import Graph
from pygrafito.engine.query.prepared import PreparedQuery
from pygrafito.engine.query.results import MutationSummary, QueryResult, Row
from pygrafito.engine.transaction import Transaction
from pygrafito.model import (
    ConnectedNodeError,
    Direction,
    GraphClosedError,
    Index,
    IndexKind,
    Node,
    NotFoundError,
    Path,
    PygrafitoError,
    QueryError,
    QueryExecutionError,
    QuerySemanticError,
    QuerySyntaxError,
    ReadOnlyError,
    Relationship,
    TransactionError,
    TraversalStep,
    UnsupportedSqliteError,
    ValidationError,
)

__all__ = [
    "ConnectedNodeError",
    "Direction",
    "Graph",
    "GraphClosedError",
    "Index",
    "IndexKind",
    "MutationSummary",
    "Node",
    "NotFoundError",
    "Path",
    "PreparedQuery",
    "PygrafitoError",
    "QueryError",
    "QueryExecutionError",
    "QueryResult",
    "QuerySemanticError",
    "QuerySyntaxError",
    "ReadOnlyError",
    "Relationship",
    "Row",
    "Transaction",
    "TransactionError",
    "TraversalStep",
    "UnsupportedSqliteError",
    "ValidationError",
]
