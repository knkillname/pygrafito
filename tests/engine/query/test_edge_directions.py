# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the seven canonical edge-direction forms."""

import pytest

from pygrafito import Graph
from pygrafito.engine.query.ast import EdgeDirection, Match
from pygrafito.engine.query.parser import Parser
from pygrafito.model import QuerySyntaxError


class TestDirectionParsing:
    """Check every direction spelling maps to one admitted-storage value."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("MATCH (a)-[r]->(b) RETURN b", EdgeDirection.OUTGOING),
            ("MATCH (a)-[r]-(b) RETURN b", EdgeDirection.ANY),
            ("MATCH (a)<-[r]-(b) RETURN b", EdgeDirection.INCOMING),
            ("MATCH (a)~[r]~(b) RETURN b", EdgeDirection.UNDIRECTED),
            ("MATCH (a)<-[r]->(b) RETURN b", EdgeDirection.DIRECTED_EITHER),
            ("MATCH (a)<-[r]~(b) RETURN b", EdgeDirection.INCOMING_OR_UNDIRECTED),
            ("MATCH (a)~[r]->(b) RETURN b", EdgeDirection.OUTGOING_OR_UNDIRECTED),
            ("MATCH (a)-->(b) RETURN b", EdgeDirection.OUTGOING),
            ("MATCH (a)<--(b) RETURN b", EdgeDirection.INCOMING),
            ("MATCH (a)-(b) RETURN b", EdgeDirection.ANY),
            ("MATCH (a)<->(b) RETURN b", EdgeDirection.DIRECTED_EITHER),
            ("MATCH (a)<~(b) RETURN b", EdgeDirection.INCOMING_OR_UNDIRECTED),
            ("MATCH (a)~>(b) RETURN b", EdgeDirection.OUTGOING_OR_UNDIRECTED),
        ],
    )
    def test_direction_spelling(self, text: str, expected: EdgeDirection) -> None:
        """Parse one spelling into its direction value."""
        statement = Parser.parse_statement(text)
        clause = statement.clauses[0]
        if not isinstance(clause, Match):
            raise AssertionError("expected a match clause")
        pattern = clause.patterns[0]
        assert pattern.relationships[0].direction is expected

    def test_mismatched_markers_are_a_syntax_error(self) -> None:
        """Reject an opening and closing marker that form no direction."""
        with pytest.raises(QuerySyntaxError, match="relationship direction"):
            Parser.parse_statement("MATCH (a)-[r]~[b] RETURN b")


class TestDirectionMatching:
    """Check the direction matrix through the in-memory quantified matcher."""

    @staticmethod
    def build() -> Graph:
        """Return a graph with one directed and one undirected relationship.

        Returns
        -------
        Graph
            Flynn -> Tron directed, Flynn -- Clu undirected.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "TRUSTS", clu, directed=False)
        return graph

    @staticmethod
    def names(graph: Graph, pattern: str, start: str = "Flynn") -> list[str]:
        """Run a one-hop pattern from ``start`` and return peer names.

        Parameters
        ----------
        graph : Graph
            Graph to query.
        pattern : str
            Direction fragment between ``(a)`` and ``(b)``, such as
            ``'<-[r]-'``.
        start : str, optional
            Designation of the start node, by default ``'Flynn'``.

        Returns
        -------
        list[str]
            Sorted peer designations.
        """
        result = graph.query(
            f"MATCH (a:Program {{designation: '{start}'}}){pattern}(b) "
            "RETURN b.designation AS name ORDER BY name"
        )
        return [str(row["name"]) for row in result.rows]

    def test_outgoing(self) -> None:
        """Follow only the directed outgoing relationship."""
        with self.build() as graph:
            assert self.names(graph, "-[r*1..1]->") == ["Tron"]

    def test_incoming(self) -> None:
        """Follow only the directed incoming relationship."""
        with self.build() as graph:
            assert self.names(graph, "<-[r*1..1]-", start="Tron") == ["Flynn"]

    def test_any(self) -> None:
        """Follow directed and undirected incident relationships."""
        with self.build() as graph:
            assert self.names(graph, "-[r*1..1]-") == ["Clu", "Tron"]

    def test_undirected_only(self) -> None:
        """Follow only the undirected relationship."""
        with self.build() as graph:
            assert self.names(graph, "~[r*1..1]~") == ["Clu"]

    def test_directed_either(self) -> None:
        """Follow a directed relationship in either stored direction."""
        with self.build() as graph:
            assert self.names(graph, "<-[r*1..1]->") == ["Tron"]
            assert self.names(graph, "<-[r*1..1]->", start="Tron") == ["Flynn"]

    def test_incoming_or_undirected(self) -> None:
        """Follow an incoming directed relationship or an undirected one."""
        with self.build() as graph:
            assert self.names(graph, "<-[r*1..1]~") == ["Clu"]
            assert self.names(graph, "<-[r*1..1]~", start="Tron") == ["Flynn"]

    def test_outgoing_or_undirected(self) -> None:
        """Follow an outgoing directed relationship or an undirected one."""
        with self.build() as graph:
            assert self.names(graph, "~[r*1..1]->") == ["Clu", "Tron"]


class TestDirectionCompilerParity:
    """Check the indexed fixed-length path matches the in-memory results."""

    @pytest.mark.parametrize(
        ("pattern", "start", "expected"),
        [
            ("-[r]->", "Flynn", ["Tron"]),
            ("<-[r]-", "Tron", ["Flynn"]),
            ("-[r]-", "Flynn", ["Clu", "Tron"]),
            ("~[r]~", "Flynn", ["Clu"]),
            ("<-[r]->", "Flynn", ["Tron"]),
            ("<-[r]~", "Flynn", ["Clu"]),
            ("~[r]->", "Flynn", ["Clu", "Tron"]),
        ],
    )
    def test_fixed_and_quantified_agree(
        self,
        pattern: str,
        start: str,
        expected: list[str],
    ) -> None:
        """Compare the compiled path with the quantified path for one form."""
        with TestDirectionMatching.build() as graph:
            fixed = TestDirectionMatching.names(graph, pattern, start)
            quantified = TestDirectionMatching.names(
                graph,
                pattern.replace("[r]", "[r*1..1]"),
                start,
            )
        assert fixed == expected
        assert quantified == expected

    def test_directed_either_rejects_an_undirected_edge(self) -> None:
        """Reject the undirected edge under the either-direction arrows."""
        with TestDirectionMatching.build() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})<-[r:TRUSTS]->(b:Place) "
                "RETURN b.designation AS name"
            )
        assert result.rows == ()
