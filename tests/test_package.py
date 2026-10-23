# SPDX-FileCopyrightText: 2026-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
"""Smoke tests for the package skeleton."""

import pygrafito
import pygrafito.engine
import pygrafito.engine.graph
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
            "Node",
            "NotFoundError",
            "Path",
            "PygrafitoError",
            "Relationship",
            "Transaction",
            "TransactionError",
            "TraversalStep",
            "UnsupportedSqliteError",
            "ValidationError",
        }
        assert set(pygrafito.__all__) == expected
        assert all(hasattr(pygrafito, name) for name in expected)
