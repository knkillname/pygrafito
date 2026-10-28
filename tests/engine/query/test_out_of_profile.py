# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for out-of-profile construct rejection."""

import importlib.util

import pytest

from pygrafito import Graph
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.tokens import KeywordIndex
from pygrafito.model import QuerySemanticError


class TestStatementBoundaries:
    """Verify statement-position constructs are rejected by name."""

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("SELECT 1", "SELECT is not supported: use MATCH ... RETURN"),
            (
                "START TRANSACTION",
                "in-language transaction control is not supported: "
                "the Python API owns transaction boundaries",
            ),
            (
                "COMMIT",
                "in-language transaction control is not supported: "
                "the Python API owns transaction boundaries",
            ),
            (
                "ROLLBACK",
                "in-language transaction control is not supported: "
                "the Python API owns transaction boundaries",
            ),
        ],
    )
    def test_statement_construct_is_named(self, text: str, fragment: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert fragment in caught.value.message
        assert caught.value.line == 1
        assert caught.value.column == 1

    @pytest.mark.parametrize(
        ("text", "column"),
        [
            ("MATCH (n) WHERE n.cycles > DATE '2020-01-01' RETURN n", 28),
            ("MATCH (n) RETURN TIME '12:00'", 18),
            ("MATCH (n) RETURN TIMESTAMP '2020-01-01T00:00:00'", 18),
            ("MATCH (n) RETURN DURATION 'P1D'", 18),
        ],
    )
    def test_temporal_literal_is_named(self, text: str, column: int) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert "temporal literal is not supported" in caught.value.message
        assert "store an integer or string property" in caught.value.message
        assert caught.value.column == column

    @pytest.mark.parametrize(
        ("text", "column"),
        [
            ("DROP GRAPH grid", 1),
            ("CREATE GRAPH grid", 8),
            ("INSERT GRAPH grid", 8),
        ],
    )
    def test_catalog_statement_is_named(self, text: str, column: int) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert "catalog statement is not supported" in caught.value.message
        assert "one embedded graph per handle" in caught.value.message
        assert caught.value.column == column


class TestCallBoundaries:
    """Verify subquery and procedure calls are named separately."""

    def test_subquery_form_names_its_alternatives(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("CALL { MATCH (n) RETURN n } RETURN n")
        assert "CALL { ... } is not supported" in caught.value.message
        assert "EXISTS { ... }" in caught.value.message
        assert "COUNT { ... }" in caught.value.message

    def test_procedure_call_names_procedures(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("CALL tron.proc() YIELD value RETURN value")
        assert "procedure call is not supported" in caught.value.message
        assert "no procedure catalog" in caught.value.message
        assert "subqueries" not in caught.value.message

    def test_subquery_form_after_match_is_named(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("MATCH (a) CALL { MATCH (b) RETURN b } RETURN a")
        assert "CALL { ... } is not supported" in caught.value.message


class TestBoundaryMessageShape:
    """Verify every recognized boundary uses the documented message shape."""

    @pytest.mark.parametrize(
        "text",
        [
            "SELECT 1",
            "START TRANSACTION",
            "COMMIT",
            "ROLLBACK",
            "MATCH (n) WHERE n.cycles > DATE '2020-01-01' RETURN n",
            "DROP GRAPH grid",
            "CREATE GRAPH grid",
            "INSERT GRAPH grid",
            "CALL { MATCH (n) RETURN n } RETURN n",
            "CALL tron.proc() YIELD value RETURN value",
        ],
    )
    def test_message_uses_construct_and_detail(self, text: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert " is not supported: " in caught.value.message


class TestExpressionBoundaries:
    """Verify expression-position constructs are rejected by name."""

    def test_regex_predicate_is_named(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("MATCH (n) WHERE n.designation =~ 'Tr.*' RETURN n")
        assert "regex predicate is not supported" in caught.value.message
        assert "STARTS WITH, ENDS WITH, or CONTAINS" in caught.value.message
        assert caught.value.column == 31

    def test_string_predicates_still_work(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron")
            rows = graph.query(
                "MATCH (n) WHERE n.designation STARTS WITH 'Tr' RETURN n.designation AS name"
            ).rows
            assert rows[0]["name"] == "Tron"

    def test_exists_is_named(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("MATCH (n) WHERE exists(n.designation) RETURN n")
        assert "exists(n.prop) is not supported" in caught.value.message
        assert "use n.prop IS NOT NULL" in caught.value.message
        assert caught.value.column == 17

    def test_is_not_null_still_works(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron")
            graph.add_node("Program", designation="Quorra", cycles=37)
            rows = graph.query(
                "MATCH (n) WHERE n.designation IS NOT NULL "
                "RETURN n.designation AS name ORDER BY name"
            ).rows
            assert [row["name"] for row in rows] == ["Quorra", "Tron"]

    @pytest.mark.parametrize(
        ("text", "construct"),
        [
            ("MATCH p = shortestPath((a)-[*]->(b)) RETURN p", "shortestPath()"),
            ("MATCH p = allShortestPaths((a)-[*]->(b)) RETURN p", "allShortestPaths()"),
        ],
    )
    def test_path_functions_are_named(self, text: str, construct: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert f"{construct} is not supported" in caught.value.message
        assert "ANY SHORTEST or SHORTEST k" in caught.value.message
        assert caught.value.column == 11

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (n) SET n = {designation: 'Tron'} RETURN n",
            "MATCH (n) SET n += {designation: 'Tron'} RETURN n",
        ],
    )
    def test_whole_map_assignment_is_named(self, text: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert "whole-map assignment is not supported" in caught.value.message
        assert "assign or remove properties individually" in caught.value.message
        assert caught.value.column == 17

    def test_property_assignment_still_works(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Program", designation="Tron")
            graph.query("MATCH (n) WHERE n.designation = 'Tron' SET n.cycles = 36 RETURN n")
            assert graph.node(node.id).properties["cycles"] == 36


class TestIdentifiers:
    """Verify out-of-profile words stay usable as identifiers."""

    def test_boundary_words_work_as_variables_and_aliases(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron")
            rows = graph.query("MATCH (date:Program) RETURN date.designation AS select").rows
            assert rows[0]["select"] == "Tron"

    def test_boundary_words_work_in_bindings(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron")
            rows = graph.query(
                "LET date = 1 LET exists = 2 LET shortestPath = 3 "
                "RETURN date AS start, exists AS drop, shortestPath AS select"
            ).rows
            assert dict(rows[0]) == {"start": 1, "drop": 2, "select": 3}

    def test_boundary_words_work_as_labels_and_property_keys(self) -> None:
        with Graph.open(":memory:") as graph:
            start = graph.add_node("start", date="2026", select="Tron")
            end = graph.add_node("drop", date="2026", select="Quorra")
            graph.add_relationship(start, "date", end)
            rows = graph.query(
                "MATCH (date:start)-[drop:date]->(select:drop) "
                "RETURN date.select AS start, select.select AS drop, type(drop) AS date"
            ).rows
            assert dict(rows[0]) == {"start": "Tron", "drop": "Quorra", "date": "date"}

    def test_boundary_words_work_as_aliases(self) -> None:
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", designation="Tron")
            rows = graph.query(
                "MATCH (n:Program) RETURN n.designation AS drop, "
                "n.designation AS start, n.designation AS select, "
                "n.designation AS date"
            ).rows
            assert dict(rows[0]) == {
                "drop": "Tron",
                "start": "Tron",
                "select": "Tron",
                "date": "Tron",
            }


class TestKeywordReservation:
    """Verify boundary words are not reserved keywords."""

    @pytest.mark.parametrize(
        "word",
        ["SELECT", "START", "COMMIT", "ROLLBACK", "DROP", "DATE", "TIME", "TIMESTAMP", "DURATION"],
    )
    def test_boundary_word_is_not_a_keyword(self, word: str) -> None:
        assert KeywordIndex.lookup(word) is None


class TestRejectedWriteAtomicity:
    """Verify a rejected write changes nothing."""

    def test_rejected_write_changes_nothing(self) -> None:
        with Graph.open(":memory:") as graph:
            node = graph.add_node("Program", designation="Tron")
            with pytest.raises(QuerySemanticError):
                graph.query("MATCH (n:Program) SET n += {designation: 'Clu'} RETURN n")
            assert graph.node(node.id).properties == {"designation": "Tron"}


class TestOutOfProfileSurface:
    """Verify non-query capabilities stay absent from the public surface."""

    @pytest.mark.parametrize(
        ("feature", "attributes"),
        [
            ("graph-types", ("define_type", "graph_type")),
            ("sessions", ("session",)),
            ("servers-and-drivers", ("server", "driver", "connect")),
            (
                "clustering-authentication-and-multi-tenancy",
                ("cluster", "authenticate", "tenant"),
            ),
            ("multi-graph-storage", ("graphs", "open_graph")),
            ("graph-algorithm-apis", ("pagerank", "community", "algorithms")),
            ("vector-search", ("vector_search", "create_vector_index")),
            ("full-text-search", ("fulltext_search", "create_fulltext_index")),
        ],
    )
    def test_capability_is_absent(self, feature: str, attributes: tuple[str, ...]) -> None:
        assert feature
        for name in attributes:
            assert not hasattr(Graph, name), name

    @pytest.mark.parametrize(
        "module",
        ["server", "driver", "schema", "session", "cluster", "algorithms", "vector", "fulltext"],
    )
    def test_no_module_provides_the_capability(self, module: str) -> None:
        assert importlib.util.find_spec(f"pygrafito.{module}") is None
