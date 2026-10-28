# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the remaining deferred-construct diagnostics."""

import pytest

from pygrafito import Graph
from pygrafito.model import QuerySemanticError


class TestGatedConstructs:
    """Verify that the remaining open-bound gate fails by name and by owner."""

    CASES: pytest.MarkDecorator = pytest.mark.parametrize(
        "query",
        [
            "MATCH (a)-[*]->(b) RETURN b",
            "MATCH (a)-[*1..]->(b) RETURN b",
            "MATCH (a)-[+]->(b) RETURN b",
        ],
    )

    @CASES
    def test_open_bound_names_the_follow_up(self, query: str) -> None:
        """Require a positioned error naming the follow-up change."""
        with Graph.open(":memory:") as graph, pytest.raises(QuerySemanticError) as caught:
            graph.query(query)
        assert "add-gql-unbounded-traversal" in caught.value.message
        assert caught.value.line is not None
        assert caught.value.column is not None

    def test_gated_write_changes_no_data(self) -> None:
        """Require a gated construct to stop the whole statement."""
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron", cycles=40)
            with pytest.raises(QuerySemanticError):
                graph.query("MATCH (a:Program)-[*]->(b) SET a.cycles = 1")
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
            assert result.rows[0]["cycles"] == 40
