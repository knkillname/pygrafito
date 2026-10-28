# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the gated-construct diagnostics."""

import pytest

from pygrafito import Graph
from pygrafito.model import QuerySemanticError


class TestGatedConstructs:
    """Verify that every gated construct fails by name and by owner."""

    CASES: pytest.MarkDecorator = pytest.mark.parametrize(
        ("query", "change"),
        [
            ("UNWIND [1] AS x WITH ORDINALITY i RETURN i", "add-gql-composition"),
            ("UNWIND [1] AS x WITH OFFSET i RETURN i", "add-gql-composition"),
            ("MATCH (n) RETURN NO BINDINGS", "add-gql-composition"),
            ("MATCH (n) LET x = 1 RETURN x", "add-gql-composition"),
            ("MATCH (n) NEXT RETURN n", "add-gql-composition"),
            ("MATCH (n) RETURN n GROUP BY n", "add-gql-composition"),
        ],
    )

    @CASES
    def test_gated_construct_names_the_follow_up(self, query: str, change: str) -> None:
        """Require a positioned error naming the follow-up change."""
        with Graph.open(":memory:") as graph, pytest.raises(QuerySemanticError) as caught:
            graph.query(query)
        assert change in caught.value.message
        assert caught.value.line is not None
        assert caught.value.column is not None

    def test_gated_write_changes_no_data(self) -> None:
        """Require a gated construct to stop the whole statement."""
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron", cycles=40)
            with pytest.raises(QuerySemanticError):
                graph.query("MATCH (n:Program) SET n.cycles = 1 LET x = 1")
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
            assert result.rows[0]["cycles"] == 40
