# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Smoke tests for the package skeleton."""

import pygrafito
import pygrafito.engine
import pygrafito.engine.graph
import pygrafito.engine.query.ast
import pygrafito.engine.query.compiler
import pygrafito.engine.query.executor
import pygrafito.engine.query.lexer
import pygrafito.engine.query.parser
import pygrafito.engine.query.plan
import pygrafito.engine.query.prepared
import pygrafito.engine.query.results
import pygrafito.engine.query.semantic
import pygrafito.engine.query.tokens
import pygrafito.engine.query.values
import pygrafito.engine.transaction
import pygrafito.engine.traversal
import pygrafito.model
import pygrafito.storage
import pygrafito.storage.codec
import pygrafito.storage.connection
import pygrafito.storage.nodes
import pygrafito.storage.relationships
import pygrafito.storage.schema


class TestPackage:
    """Verify that every package module can be imported."""

    def test_package_imports(self) -> None:
        modules = (
            pygrafito,
            pygrafito.engine,
            pygrafito.engine.graph,
            pygrafito.engine.query.ast,
            pygrafito.engine.query.compiler,
            pygrafito.engine.query.executor,
            pygrafito.engine.query.lexer,
            pygrafito.engine.query.parser,
            pygrafito.engine.query.plan,
            pygrafito.engine.query.prepared,
            pygrafito.engine.query.results,
            pygrafito.engine.query.semantic,
            pygrafito.engine.query.tokens,
            pygrafito.engine.query.values,
            pygrafito.engine.transaction,
            pygrafito.engine.traversal,
            pygrafito.model,
            pygrafito.storage,
            pygrafito.storage.codec,
            pygrafito.storage.connection,
            pygrafito.storage.nodes,
            pygrafito.storage.relationships,
            pygrafito.storage.schema,
        )
        assert all(module.__name__.startswith("pygrafito") for module in modules)

    def test_public_exports(self) -> None:
        expected = {
            "ConnectedNodeError",
            "Direction",
            "Graph",
            "GraphClosedError",
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
            "Relationship",
            "Row",
            "Transaction",
            "TransactionError",
            "TraversalStep",
            "UnsupportedSqliteError",
            "ValidationError",
        }
        assert set(pygrafito.__all__) == expected
        assert all(hasattr(pygrafito, name) for name in expected)
