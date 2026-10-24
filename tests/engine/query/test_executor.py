# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Execution tests for read statements of the query language."""

import dataclasses
import typing
from collections.abc import Iterator

import pytest

from pygrafito import Graph
from pygrafito.engine.query.results import QueryResult, Row
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import (
    Node,
    Path,
    QueryExecutionError,
    QuerySemanticError,
    Relationship,
    TransactionError,
)


class _QueryGraph:
    """Provide the shared TRON fixture for execution tests."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node(
                "Program",
                "ISO",
                designation="Quorra",
                cycles=37,
                tags=["ISO", "Program"],
                active=True,
            )
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            clu = graph.add_node("Program", designation="Clu")
            rinzler = graph.add_node("Program", designation="Rinzler", cycles=36.0)
            sam = graph.add_node("Program", designation="Sam Flynn")
            grid = graph.add_node("System", designation="The Grid")
            encom = graph.add_node("Company", designation="ENCOM")
            graph.add_node("Grid Node", designation="Grid Node", **{"a.b": 1})
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2021)
            graph.add_relationship(kevin, "TRUSTS", tron, since_cycle=2020)
            graph.add_relationship(quorra, "ALLIES_WITH", clu)
            graph.add_relationship(tron, "ALLIES_WITH", clu)
            graph.add_relationship(clu, "OBSERVES", clu)
            graph.add_relationship(rinzler, "OBSERVES", rinzler)
            graph.add_relationship(clu, "TRUSTS", kevin)
            graph.add_relationship(sam, "ALLIES_WITH", kevin)
            graph.add_relationship(grid, "CONTAINS", encom)
            yield graph

    @staticmethod
    def values(result: QueryResult) -> list[tuple[QueryValue, ...]]:
        return [tuple(row.values()) for row in result]

    def designations(self, result: QueryResult) -> list[str]:
        return [str(value) for (value,) in self.values(result)]


class TestQueryExecution(_QueryGraph):
    """Verify matching, filtering, projection, and result values."""

    def test_labels_and_properties(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program:ISO) RETURN n.designation AS name")
        assert result.columns == ("name",)
        assert self.designations(result) == ["Quorra"]

    def test_property_map_numeric_equality(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {cycles: 36}) RETURN n.designation")
        assert sorted(self.designations(result)) == ["Kevin Flynn", "Rinzler"]

    def test_property_map_boolean_and_list(self, graph: Graph) -> None:
        active = graph.query("MATCH (n {active: true}) RETURN n.designation")
        tags = graph.query("MATCH (n {tags: ['ISO', 'Program']}) RETURN n.designation")
        assert self.designations(active) == ["Quorra"]
        assert self.designations(tags) == ["Quorra"]

    def test_backtick_property_key(self, graph: Graph) -> None:
        result = graph.query("MATCH (n {`a.b`: 1}) RETURN n.designation")
        assert self.designations(result) == ["Grid Node"]

    def test_anonymous_pattern_elements(self, graph: Graph) -> None:
        result = graph.query("MATCH (:Program)-[:TRUSTS]->(n) RETURN n.designation")
        assert sorted(self.designations(result)) == ["Kevin Flynn", "Tron"]

    def test_numeric_range_filter(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WHERE n.cycles >= 36 AND n.cycles < 40 "
            "RETURN n.designation ORDER BY n.designation"
        )
        assert self.designations(result) == ["Kevin Flynn", "Quorra", "Rinzler"]

    def test_residual_arithmetic(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) WHERE n.cycles + 1 = 38 RETURN n.designation")
        assert self.designations(result) == ["Quorra"]

    def test_residual_function(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) WHERE abs(n.cycles) = 36 RETURN n.designation")
        assert sorted(self.designations(result)) == ["Kevin Flynn", "Rinzler"]

    def test_residual_parameter_list(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WHERE n.designation IN $names RETURN n.designation "
            "ORDER BY n.designation",
            {"names": ["Quorra", "Tron"]},
        )
        assert self.designations(result) == ["Quorra", "Tron"]

    def test_membership_and_string_predicates(self, graph: Graph) -> None:
        membership = graph.query(
            "MATCH (n:Program) WHERE n.designation IN ['Quorra', 'Tron'] "
            "RETURN n.designation ORDER BY n.designation"
        )
        starts = graph.query(
            "MATCH (n:Program) WHERE n.designation STARTS WITH 'Qu' RETURN n.designation"
        )
        ends = graph.query(
            "MATCH (n:Program) WHERE n.designation ENDS WITH 'ra' RETURN n.designation"
        )
        contains = graph.query(
            "MATCH (n:Program) WHERE n.designation CONTAINS 'orr' RETURN n.designation"
        )
        assert self.designations(membership) == ["Quorra", "Tron"]
        assert self.designations(starts) == ["Quorra"]
        assert self.designations(ends) == ["Quorra"]
        assert self.designations(contains) == ["Quorra"]

    def test_string_predicates_are_case_sensitive(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WHERE n.designation CONTAINS 'LYNN' RETURN n.designation"
        )
        assert result.rows == ()

    def test_boolean_filters(self, graph: Graph) -> None:
        conjunction = graph.query(
            "MATCH (n:Program) WHERE n.cycles >= 36 AND n.cycles < 37 "
            "RETURN n.designation ORDER BY n.designation"
        )
        disjunction = graph.query(
            "MATCH (n:Program) WHERE n.cycles >= 39 OR n.designation = 'Clu' "
            "RETURN n.designation ORDER BY n.designation"
        )
        negation = graph.query(
            "MATCH (n:Program) WHERE NOT n.cycles = 36 RETURN n.designation ORDER BY n.designation"
        )
        assert self.designations(conjunction) == ["Kevin Flynn", "Rinzler"]
        assert self.designations(disjunction) == ["Clu", "Tron"]
        assert self.designations(negation) == ["Quorra", "Tron"]

    def test_null_semantics(self, graph: Graph) -> None:
        projected = graph.query("MATCH (n:Program {designation: 'Clu'}) RETURN n.cycles")
        nulls = graph.query(
            "MATCH (n:Program) WHERE n.cycles IS NULL RETURN n.designation ORDER BY n.designation"
        )
        not_nulls = graph.query(
            "MATCH (n:Program) WHERE n.cycles IS NOT NULL RETURN count(*) AS total"
        )
        missing_equals = graph.query("MATCH (n:Program) WHERE n.missing = 1 RETURN n.designation")
        missing_not_equals = graph.query(
            "MATCH (n:Program) WHERE n.missing <> 1 RETURN n.designation"
        )
        assert self.values(projected) == [(None,)]
        assert self.designations(nulls) == ["Clu", "Sam Flynn"]
        assert self.values(not_nulls) == [(4,)]
        assert missing_equals.rows == ()
        assert missing_not_equals.rows == ()

    def test_relationship_directions(self, graph: Graph) -> None:
        outgoing = graph.query(
            "MATCH (a {designation: 'Quorra'})-[r:ALLIES_WITH]->(b) RETURN b.designation "
            "ORDER BY b.designation"
        )
        incoming = graph.query(
            "MATCH (a {designation: 'Clu'})<-[r:ALLIES_WITH]-(b) RETURN b.designation "
            "ORDER BY b.designation"
        )
        both = graph.query(
            "MATCH (a {designation: 'Quorra'})-[r:ALLIES_WITH]-(b) RETURN b.designation "
            "ORDER BY b.designation"
        )
        assert self.designations(outgoing) == ["Clu"]
        assert self.designations(incoming) == ["Quorra", "Tron"]
        assert self.designations(both) == ["Clu", "Kevin Flynn", "Kevin Flynn"]

    def test_type_alternatives(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH|TRUSTS]->(b) "
            "RETURN type(r) AS kind, b.designation AS name ORDER BY name"
        )
        assert self.values(result) == [
            ("ALLIES_WITH", "Quorra"),
            ("ALLIES_WITH", "Quorra"),
            ("TRUSTS", "Tron"),
        ]

    def test_relationship_property_filter(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH {since_cycle: 2021}]->(b) "
            "RETURN b.designation"
        )
        assert self.designations(result) == ["Quorra"]

    def test_parallel_relationships_are_distinct_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[r:ALLIES_WITH]->(b) RETURN count(*) AS total"
        )
        assert self.values(result) == [(2,)]

    def test_diamond_produces_one_row_per_route(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[]->(b)"
            "-[]->(c:Program {designation: 'Clu'}) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Quorra", "Quorra", "Tron"]

    def test_cycle_is_matched(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[]->(b)"
            "-[:ALLIES_WITH]->(c)-[:TRUSTS]->(a) RETURN b.designation "
            "ORDER BY b.designation"
        )
        assert self.designations(result) == ["Quorra", "Quorra", "Tron"]

    def test_self_loop(self, graph: Graph) -> None:
        directed = graph.query(
            "MATCH (a)-[r:OBSERVES]->(a) RETURN a.designation ORDER BY a.designation"
        )
        undirected = graph.query(
            "MATCH (a)-[r:OBSERVES]-(b) RETURN a.designation AS a, b.designation AS b "
            "ORDER BY a.designation"
        )
        assert self.designations(directed) == ["Clu", "Rinzler"]
        assert self.values(undirected) == [("Clu", "Clu"), ("Rinzler", "Rinzler")]

    def test_repeated_node_variable(self, graph: Graph) -> None:
        result = graph.query("MATCH (a)-[r]->(a) RETURN a.designation ORDER BY a.designation")
        assert self.designations(result) == ["Clu", "Rinzler"]

    def test_repeated_relationship_variable(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[r:OBSERVES]->(b)-[r]->(c) "
            "RETURN a.designation AS a, b.designation AS b, c.designation AS c "
            "ORDER BY a.designation"
        )
        assert self.values(result) == [("Clu", "Clu", "Clu"), ("Rinzler", "Rinzler", "Rinzler")]

    def test_path_projection(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (a:Program {designation: 'Kevin Flynn'})-[:TRUSTS]->(b) RETURN p"
        )
        path = result.rows[0]["p"]
        assert isinstance(path, Path)
        assert [node["designation"] for node in path.nodes] == ["Kevin Flynn", "Tron"]
        assert path.length == 1

    def test_incoming_path_order(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH p = (q:Program {designation: 'Quorra'})<-[:ALLIES_WITH]-"
            "(k:Program {designation: 'Kevin Flynn'}) RETURN p"
        )
        path = result.rows[0]["p"]
        assert isinstance(path, Path)
        assert [node["designation"] for node in path.nodes] == ["Quorra", "Kevin Flynn"]

    def test_single_node_path(self, graph: Graph) -> None:
        result = graph.query("MATCH p = (n:Program {designation: 'Tron'}) RETURN p")
        path = result.rows[0]["p"]
        assert isinstance(path, Path)
        assert path.length == 0
        assert path.start["designation"] == "Tron"

    def test_entity_projection(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[r:TRUSTS]->(b) RETURN a, r, b"
        )
        row = result.rows[0]
        node = row["a"]
        relationship = row["r"]
        target = row["b"]
        assert isinstance(node, Node)
        assert isinstance(relationship, Relationship)
        assert isinstance(target, Node)
        assert node.id > 0
        assert relationship.rel_type == "TRUSTS"
        assert target["designation"] == "Tron"

    def test_scalar_functions(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (q:Program:ISO {designation: 'Quorra'}) RETURN "
            "id(q) AS id, labels(q) AS labels, properties(q).designation AS designation, "
            "keys(q) AS keys, size(q.tags) AS size, coalesce(q.missing, 'fallback') AS fallback, "
            "toInteger('36') AS i, toFloat('36.5') AS f, toString(37) AS s, "
            "lower(q.designation) AS lower, upper(q.designation) AS upper, "
            "trim('  Quorra  ') AS trimmed, abs(-36) AS absolute, "
            "concat('Quorra', ' Flynn') AS joined"
        )
        row = result.rows[0]
        identifier = row["id"]
        assert isinstance(identifier, int)
        assert identifier > 0
        assert row["labels"] == ["ISO", "Program"]
        assert row["designation"] == "Quorra"
        assert row["keys"] == ["active", "cycles", "designation", "tags"]
        assert row["size"] == 2
        assert row["fallback"] == "fallback"
        assert row["i"] == 36
        assert row["f"] == 36.5
        assert row["s"] == "37"
        assert row["lower"] == "quorra"
        assert row["upper"] == "QUORRA"
        assert row["trimmed"] == "Quorra"
        assert row["absolute"] == 36
        assert row["joined"] == "Quorra Flynn"

    def test_relationship_metadata_functions(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'})-[r:TRUSTS]->(b) "
            "RETURN type(r) AS kind, startNode(r).designation AS start, "
            "endNode(r).designation AS end"
        )
        assert self.values(result) == [("TRUSTS", "Kevin Flynn", "Tron")]

    def test_arithmetic_and_division(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN 6 / 2 AS quotient, "
            "2 + 3.5 AS total, 7 % 4 AS remainder"
        )
        assert self.values(result) == [(3.0, 5.5, 3)]

    def test_division_by_zero_and_overflow_are_execution_errors(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN 1 / 0")
        with pytest.raises(QueryExecutionError):
            graph.query(
                "MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN 9223372036854775807 + 1"
            )


class TestComposedMatch(_QueryGraph):
    """Verify multiple patterns and chained match stages."""

    def test_shared_variable_joins_patterns(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'})-[:ALLIES_WITH]->(b), "
            "(b)-[:ALLIES_WITH]->(c) RETURN c.designation"
        )
        assert self.designations(result) == ["Clu", "Clu"]

    def test_disconnected_patterns_form_a_cartesian_product(self, graph: Graph) -> None:
        result = graph.query("MATCH (a:Program), (b:System) RETURN count(*) AS total")
        assert self.values(result) == [(6,)]

    def test_chained_match_stage_joins(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "MATCH (a)-[:TRUSTS]->(b) RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Tron"]

    def test_chained_match_drops_unmatched_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) MATCH (a)-[:TRUSTS]->(b) RETURN b"
        )
        assert self.values(result) == []

    def test_where_filters_the_pattern_set(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program), (b:Program) WHERE a.cycles = b.cycles "
            "AND a.designation <> b.designation RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Kevin Flynn", "Rinzler"]


class TestOptionalMatch(_QueryGraph):
    """Verify left-join semantics and null propagation."""

    def test_zero_matches_produces_a_null_row(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) "
            "OPTIONAL MATCH (a)-[:TRUSTS]->(b) RETURN b.designation"
        )
        assert self.values(result) == [(None,)]

    def test_one_match_is_returned(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "OPTIONAL MATCH (a)-[:TRUSTS]->(b) RETURN b.designation"
        )
        assert self.designations(result) == ["Tron"]

    def test_each_match_expands_the_row(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b) RETURN b.designation"
        )
        assert self.designations(result) == ["Quorra", "Quorra"]

    def test_earlier_variable_is_unchanged(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) "
            "OPTIONAL MATCH (a)-[:TRUSTS]->(b) RETURN a.designation AS a, b.designation AS b"
        )
        assert self.values(result) == [("Sam Flynn", None)]

    def test_optional_where_filters_the_optional_match(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'}) "
            "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b) WHERE b.cycles > 40 "
            "RETURN b.designation"
        )
        assert self.values(result) == [(None,)]

    def test_later_mandatory_match_drops_null_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "MATCH (b)-[:ALLIES_WITH]->(c) RETURN a.designation AS a, c.designation AS c"
        )
        assert self.values(result) == []

    def test_later_mandatory_match_keeps_matched_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Kevin Flynn'}) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "MATCH (b)-[:ALLIES_WITH]->(c) RETURN a.designation AS a, c.designation AS c"
        )
        assert self.values(result) == [("Kevin Flynn", "Clu")]

    def test_downstream_where_excludes_nulls(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "MATCH (a) WHERE b.designation = 'Tron' RETURN b"
        )
        assert self.values(result) == []

    def test_optional_match_may_start_a_statement(self, graph: Graph) -> None:
        result = graph.query("OPTIONAL MATCH (n:Missing) RETURN n.designation")
        assert self.values(result) == [(None,)]

    def test_optional_match_first_returns_every_match(self, graph: Graph) -> None:
        result = graph.query("OPTIONAL MATCH (n:System) RETURN n.designation")
        assert self.designations(result) == ["The Grid"]

    def test_optional_quantified_match_can_be_empty(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Clu'}) "
            "OPTIONAL MATCH (a)-[:ALLIES_WITH*1..2]->(b) RETURN b.designation"
        )
        assert self.values(result) == [(None,)]


class TestWithStage(_QueryGraph):
    """Verify WITH projection, aggregation, and pagination boundaries."""

    def test_projects_a_new_scope(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WITH n.designation AS name RETURN name ORDER BY name"
        )
        assert self.designations(result) == [
            "Clu",
            "Kevin Flynn",
            "Quorra",
            "Rinzler",
            "Sam Flynn",
            "Tron",
        ]

    def test_filters_on_an_aggregate_alias(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends "
            "WHERE friends > 1 RETURN a.designation AS name"
        )
        assert self.designations(result) == ["Kevin Flynn"]

    def test_orders_by_an_aggregate_alias(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a.designation AS name, count(*) AS friends "
            "ORDER BY friends DESC, name LIMIT 1 RETURN name, friends"
        )
        assert self.values(result) == [("Kevin Flynn", 2)]

    def test_paginates_grouped_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a.designation AS name, count(*) AS friends "
            "ORDER BY name SKIP 1 LIMIT 2 RETURN name"
        )
        assert self.designations(result) == ["Quorra", "Sam Flynn"]

    def test_distinct_removes_duplicate_projected_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WITH DISTINCT n.cycles AS cycles RETURN count(*) AS total"
        )
        assert self.values(result) == [(4,)]

    def test_match_after_with_joins_projected_rows(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program) WITH a MATCH (a)-[:TRUSTS]->(b) "
            "RETURN b.designation ORDER BY b.designation"
        )
        assert self.designations(result) == ["Kevin Flynn", "Tron"]

    def test_with_before_write_shapes_mutation_input(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program) WITH a WHERE a.designation = 'Kevin Flynn' "
            "CREATE (b:ISO {designation: 'Tron'}) RETURN b.designation AS name"
        )
        assert self.designations(result) == ["Tron"]
        assert result.summary.created_nodes == 1

    def test_null_from_optional_survives_with(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a {designation: 'Sam Flynn'}) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
            "WITH a, b WHERE b IS NULL RETURN a.designation"
        )
        assert self.designations(result) == ["Sam Flynn"]

    def test_with_then_quantified_path(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'}) WITH a "
            "MATCH (a)-[:ALLIES_WITH*1..2]->(b) RETURN count(*) AS total"
        )
        assert self.values(result) == [(4,)]


class TestAggregationAndOrdering(_QueryGraph):
    """Verify grouping, aggregates, ordering, and pagination."""

    def test_count_rows_and_values(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN count(*) AS rows, count(n.cycles) AS cycles")
        assert self.values(result) == [(6, 4)]

    def test_numeric_aggregates(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN sum(n.cycles) AS total, avg(n.cycles) AS average, "
            "min(n.cycles) AS low, max(n.cycles) AS high"
        )
        assert self.values(result) == [(149.0, 37.25, 36, 40.0)]

    def test_collect_and_distinct_aggregates(self, graph: Graph) -> None:
        collected = graph.query("MATCH (n:Program) RETURN collect(n.designation) AS names")
        distinct = graph.query(
            "MATCH (n:Program) RETURN count(DISTINCT n.cycles) AS cycles, "
            "collect(DISTINCT n.cycles) AS values"
        )
        names = collected.rows[0]["names"]
        assert isinstance(names, list)
        string_names = typing.cast(list[str], names)
        assert sorted(string_names) == [
            "Clu",
            "Kevin Flynn",
            "Quorra",
            "Rinzler",
            "Sam Flynn",
            "Tron",
        ]
        assert distinct.rows[0]["cycles"] == 3
        values = distinct.rows[0]["values"]
        assert isinstance(values, list)
        numeric_values = typing.cast(list[int | float], values)
        assert sorted(numeric_values) == [36, 37, 40]

    def test_grouped_aggregation(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS total ORDER BY labels"
        )
        assert self.values(result) == [
            (["Company"], 1),
            (["Grid Node"], 1),
            (["ISO", "Program"], 1),
            (["Program"], 5),
            (["System"], 1),
        ]

    def test_aggregate_inside_scalar_function(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN abs(sum(n.cycles)) AS total")
        assert self.values(result) == [(149.0,)]

    def test_empty_aggregate_input(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Missing) RETURN count(*) AS rows, collect(n.designation) AS names, "
            "sum(n.cycles) AS total, avg(n.cycles) AS average, "
            "min(n.cycles) AS low, max(n.cycles) AS high"
        )
        assert self.values(result) == [(0, [], 0, None, None, None)]

    def test_empty_grouped_input(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Missing) RETURN labels(n) AS labels, count(*) AS total")
        assert result.rows == ()

    def test_order_ascending_and_descending(self, graph: Graph) -> None:
        ascending = graph.query("MATCH (n:Program) RETURN n.designation ORDER BY n.designation ASC")
        descending = graph.query(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.designation DESC"
        )
        assert [row["n.designation"] for row in ascending] == [
            "Clu",
            "Kevin Flynn",
            "Quorra",
            "Rinzler",
            "Sam Flynn",
            "Tron",
        ]
        assert [row["n.designation"] for row in descending] == [
            "Tron",
            "Sam Flynn",
            "Rinzler",
            "Quorra",
            "Kevin Flynn",
            "Clu",
        ]

    def test_null_ordering(self, graph: Graph) -> None:
        ascending = graph.query(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.cycles ASC, n.designation ASC"
        )
        descending = graph.query(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.cycles DESC, n.designation ASC"
        )
        assert [row["n.designation"] for row in ascending] == [
            "Kevin Flynn",
            "Rinzler",
            "Quorra",
            "Tron",
            "Clu",
            "Sam Flynn",
        ]
        assert [row["n.designation"] for row in descending] == [
            "Clu",
            "Sam Flynn",
            "Tron",
            "Quorra",
            "Kevin Flynn",
            "Rinzler",
        ]

    def test_order_by_alias_and_unprojected_expression(self, graph: Graph) -> None:
        alias = graph.query("MATCH (n:Program) RETURN n.designation AS name ORDER BY name LIMIT 2")
        unprojected = graph.query(
            "MATCH (n:Program) WHERE n.cycles IS NOT NULL "
            "RETURN n.designation AS name ORDER BY n.cycles DESC LIMIT 2"
        )
        assert [row["name"] for row in alias] == ["Clu", "Kevin Flynn"]
        assert [row["name"] for row in unprojected] == ["Tron", "Quorra"]

    def test_order_by_aggregate_alias(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS total "
            "ORDER BY total DESC, labels ASC"
        )
        assert result.rows[0]["labels"] == ["Program"]
        assert result.rows[0]["total"] == 5

    def test_pagination(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.designation SKIP 2 LIMIT 2"
        )
        assert [row["n.designation"] for row in result] == ["Quorra", "Rinzler"]

    def test_parameterized_pagination(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.designation ORDER BY n.designation SKIP $skip LIMIT $limit",
            {"skip": 1, "limit": 2},
        )
        assert [row["n.designation"] for row in result] == ["Kevin Flynn", "Quorra"]

    @pytest.mark.parametrize("value", [-1, 1.5, "one", True])
    def test_invalid_parameterized_pagination(
        self,
        graph: Graph,
        value: QueryValue,
    ) -> None:
        with pytest.raises(QuerySemanticError):
            graph.query(
                "MATCH (n) RETURN n LIMIT $limit",
                {"limit": value},
            )

    def test_distinct(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN DISTINCT labels(n) AS labels ORDER BY labels"
        )
        assert self.values(result) == [(["ISO", "Program"],), (["Program"],)]
        duplicates = graph.query("MATCH (n:Program) RETURN labels(n) AS labels")
        assert len(duplicates) == 6

    def test_order_by_unorderable_value(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n:Program) RETURN n ORDER BY n")


class TestResultsAndSnapshots(_QueryGraph):
    """Verify the result model and snapshot consistency."""

    def test_row_mapping_behavior(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Tron'}) RETURN n.designation AS name, n.cycles"
        )
        row = result.rows[0]
        assert result.columns == ("name", "n.cycles")
        assert len(result) == 1
        assert len(row) == 2
        assert list(row) == ["name", "n.cycles"]
        assert row["name"] == "Tron"
        assert row["n.cycles"] == 40
        assert dict(row) == {"name": "Tron", "n.cycles": 40}
        assert set(row.keys()) == {"name", "n.cycles"}
        assert list(row.values()) == ["Tron", 40]
        with pytest.raises(KeyError):
            row["missing"]

    def test_row_is_immutable_and_validates_arity(self) -> None:
        row = Row(columns=("a",), row_values=(1,))
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.columns = ("b",)  # type: ignore[misc]
        with pytest.raises(ValueError, match="one value per column"):
            Row(columns=("a", "b"), row_values=(1,))

    def test_empty_result(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Missing) RETURN n")
        assert isinstance(result, QueryResult)
        assert result.columns == ("n",)
        assert result.rows == ()
        assert len(result) == 0
        assert list(result) == []

    def test_result_is_unchanged_by_a_later_write(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN n")
        node = result.rows[0]["n"]
        assert isinstance(node, Node)
        graph.set_properties(node, cycles=99)
        snapshot = result.rows[0]["n"]
        assert isinstance(snapshot, Node)
        assert snapshot["cycles"] == 36
        assert (
            graph.query("MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN n.cycles").rows[0][
                "n.cycles"
            ]
            == 99
        )

    def test_read_transaction_is_closed(self, graph: Graph) -> None:
        graph.query("MATCH (n) RETURN n")
        assert not graph._database.connection.in_transaction

    def test_failed_query_rolls_back(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("MATCH (n) RETURN 1 / 0")
        assert not graph._database.connection.in_transaction
        graph.add_node("Program", designation="Yori")
        assert not graph._database.connection.in_transaction

    def test_parameter_injection_is_data(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Quorra' OR 1=1 --")
        result = graph.query(
            "MATCH (n:Program) WHERE n.designation = $name RETURN n.designation",
            {"name": "Quorra' OR 1=1 --"},
        )
        assert result.rows[0]["n.designation"] == "Quorra' OR 1=1 --"
        assert len(graph.query("MATCH (n:Program) RETURN n")) == 7


class TestTransactions(_QueryGraph):
    """Verify transaction visibility and graph-level guards."""

    def test_transaction_query_sees_uncommitted_writes(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            transaction.add_node("ISO", designation="Quorra")
            result = transaction.query("MATCH (n:ISO) RETURN n.designation")
            assert result.rows[0]["n.designation"] == "Quorra"

    def test_staged_query_sees_uncommitted_writes(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            yori = transaction.add_node("Program", designation="Yori")
            castor = transaction.add_node("Program", designation="Castor")
            transaction.add_relationship(yori, "ALLIES_WITH", castor)
            result = transaction.query(
                "MATCH (a:Program {designation: 'Yori'}) WITH a "
                "MATCH (a)-[:ALLIES_WITH]->(b) RETURN b.designation"
            )
            assert [tuple(row.values()) for row in result] == [("Castor",)]

    def test_graph_query_is_blocked_during_transaction(self, graph: Graph) -> None:
        with graph.transaction() as transaction:
            with pytest.raises(TransactionError):
                graph.query("MATCH (n) RETURN n")
            prepared = graph.prepare("MATCH (n) RETURN n")
            with pytest.raises(TransactionError):
                prepared.execute()
            transaction.add_node("Program", designation="Yori")
        assert graph.query("MATCH (n {designation: 'Yori'}) RETURN n").rows

    def test_transaction_query_requires_active_transaction(self, graph: Graph) -> None:
        transaction = graph.transaction()
        with pytest.raises(TransactionError):
            transaction.query("MATCH (n) RETURN n")

    def test_transaction_rollback_hides_writes(self, graph: Graph) -> None:
        try:
            with graph.transaction() as transaction:
                transaction.add_node("Program", designation="Yori")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        assert graph.query("MATCH (n {designation: 'Yori'}) RETURN n").rows == ()


class TestUnwindExecution(_QueryGraph):
    """Verify UNWIND row expansion and its interaction with later stages."""

    def test_expand_literal_in_order(self, graph: Graph) -> None:
        result = graph.query("UNWIND [1, 2, 3] AS value RETURN value")
        assert self.values(result) == [(1,), (2,), (3,)]

    def test_expand_parameter_list(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $names AS name RETURN name",
            {"names": ["Kevin Flynn", "Quorra"]},
        )
        assert self.values(result) == [("Kevin Flynn",), ("Quorra",)]

    def test_expand_mapping_rows(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row RETURN row.designation AS name",
            {"rows": [{"designation": "Tron"}, {"designation": "Clu"}]},
        )
        assert self.values(result) == [("Tron",), ("Clu",)]

    def test_empty_list_and_null_produce_no_rows(self, graph: Graph) -> None:
        assert graph.query("UNWIND [] AS value RETURN value").rows == ()
        assert graph.query("UNWIND $value AS value RETURN value", {"value": None}).rows == ()

    def test_runtime_non_list_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query("UNWIND $value AS value RETURN value", {"value": "Tron"})
        with pytest.raises(QueryExecutionError):
            graph.query("UNWIND $value AS value RETURN value", {"value": {"a": 1}})

    def test_static_non_list_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError):
            graph.query("UNWIND 36 AS value RETURN value")

    def test_unwind_feeds_a_match(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row MATCH (n:Program {designation: row.designation}) "
            "RETURN n.cycles ORDER BY n.cycles",
            {"rows": [{"designation": "Quorra"}, {"designation": "Tron"}]},
        )
        assert self.values(result) == [(37,), (40,)]

    def test_match_feeds_an_unwind(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WITH collect(n.designation) AS names "
            "UNWIND names AS name RETURN count(*) AS total"
        )
        assert self.values(result) == [(6,)]

    def test_null_row_skips_later_stages(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $value AS value MATCH (n:Program {designation: value}) RETURN n",
            {"value": None},
        )
        assert result.rows == ()

    def test_create_from_a_row_expression(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row "
            "CREATE (n:Program {designation: row.designation, cycles: row.cycles}) "
            "RETURN n.cycles AS cycles",
            {"rows": [{"designation": "Marvin", "cycles": 1}]},
        )
        assert self.values(result) == [(1,)]

    def test_null_pattern_value_matches_nothing(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row MATCH (n:Program {designation: row.designation}) RETURN n",
            {"rows": [{"designation": None}]},
        )
        assert result.rows == ()

    def test_null_create_property_is_omitted(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row "
            "CREATE (n:Program {designation: row.designation, cycles: row.cycles}) "
            "RETURN n.designation AS name",
            {"rows": [{"designation": "Marvin", "cycles": None}]},
        )
        assert self.values(result) == [("Marvin",)]
        marvin = next(iter(graph.find_nodes("Program", designation="Marvin")))
        assert "cycles" not in marvin

    def test_large_expansion_is_linear(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $values AS value RETURN count(*) AS total",
            {"values": list(range(10000))},
        )
        assert self.values(result) == [(10000,)]


class TestMergeExecution(_QueryGraph):
    """Verify MERGE matching, creation, and conditional updates."""

    def test_merge_creates_a_missing_node(self, graph: Graph) -> None:
        result = graph.query(
            "MERGE (n:Program {designation: 'Marvin'}) RETURN n.designation AS name"
        )
        assert self.values(result) == [("Marvin",)]
        assert result.summary.created_nodes == 1

    def test_merge_matches_an_existing_node(self, graph: Graph) -> None:
        result = graph.query("MERGE (n:Program {designation: 'Tron'}) RETURN n.cycles AS cycles")
        assert self.values(result) == [(40,)]
        assert result.summary.created_nodes == 0

    def test_on_create_applies_only_to_created_rows(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row "
            "MERGE (n:Program {designation: row.designation}) "
            "ON CREATE SET n.cycles = row.cycles "
            "RETURN n.designation AS name, n.cycles AS cycles",
            {
                "rows": [
                    {"designation": "Tron", "cycles": 99},
                    {"designation": "Marvin", "cycles": 1},
                ]
            },
        )
        assert self.values(result) == [("Tron", 40), ("Marvin", 1)]
        assert result.summary.created_nodes == 1
        assert result.summary.properties_set == 1

    def test_on_match_applies_only_to_matched_rows(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row "
            "MERGE (n:Program {designation: row.designation}) "
            "ON MATCH SET n.cycles = row.cycles "
            "RETURN n.designation AS name, n.cycles AS cycles",
            {
                "rows": [
                    {"designation": "Tron", "cycles": 41},
                    {"designation": "Marvin", "cycles": 1},
                ]
            },
        )
        assert self.values(result) == [("Tron", 41), ("Marvin", None)]
        assert result.summary.created_nodes == 1

    def test_conditional_update_is_visible_to_return(self, graph: Graph) -> None:
        result = graph.query(
            "MERGE (n:Program {designation: 'Clu'}) ON MATCH SET n.cycles = 99 RETURN n.cycles"
        )
        assert self.values(result) == [(99,)]

    def test_duplicate_rows_create_once(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
            "RETURN n.designation AS name",
            {"rows": [{"designation": "Marvin"}, {"designation": "Marvin"}]},
        )
        assert self.values(result) == [("Marvin",), ("Marvin",)]
        assert result.summary.created_nodes == 1

    def test_several_matches_produce_several_rows(self, graph: Graph) -> None:
        graph.add_node("Program", designation="Marvin")
        graph.add_node("Program", designation="Marvin")
        result = graph.query(
            "MERGE (n:Program {designation: 'Marvin'}) RETURN n.designation AS name"
        )
        assert self.values(result) == [("Marvin",), ("Marvin",)]
        assert result.summary.created_nodes == 0

    def test_merge_relationship_between_bound_nodes(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (a:Program {designation: 'Kevin Flynn'}), "
            "(b:Program {designation: 'Sam Flynn'}) "
            "MERGE (a)-[r:TRUSTS]->(b) RETURN type(r) AS kind"
        )
        assert self.values(result) == [("TRUSTS",)]
        assert result.summary.created_relationships == 1

    def test_merge_relationship_properties_from_a_row(self, graph: Graph) -> None:
        result = graph.query(
            "UNWIND $rows AS row "
            "MATCH (a:Program {designation: 'Kevin Flynn'}), "
            "(b:Program {designation: 'Quorra'}) "
            "MERGE (a)-[r:MONITORS {since_cycle: row.since}]->(b) "
            "RETURN r.since_cycle AS since",
            {"rows": [{"since": 2020}]},
        )
        assert self.values(result) == [(2020,)]
        assert result.summary.created_relationships == 1

    def test_whole_pattern_does_not_partially_reuse(self, graph: Graph) -> None:
        before = len(
            [node for node in graph.find_nodes("Program") if node["designation"] == "Tron"]
        )
        graph.query(
            "MERGE (a:Program {designation: 'Tron'})"
            "-[:MONITORS]->(b:Program {designation: 'Quorra'})"
        )
        after = len([node for node in graph.find_nodes("Program") if node["designation"] == "Tron"])
        assert after == before + 1

    def test_repeated_variable_creates_a_self_loop(self, graph: Graph) -> None:
        result = graph.query(
            "MERGE (a:Program {designation: 'Marvin'})"
            "-[:MONITORS]->(a) RETURN a.designation AS name"
        )
        assert self.values(result) == [("Marvin",)]
        node = next(node for node in graph.find_nodes("Program") if node["designation"] == "Marvin")
        relationships = graph.find_relationships("MONITORS")
        assert any(item.start_id == node.id and item.end_id == node.id for item in relationships)

    def test_null_merge_property_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QueryExecutionError):
            graph.query(
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
                {"rows": [{"designation": None}]},
            )

    def test_merge_failure_rolls_back_creations(self, graph: Graph) -> None:
        before = graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"]
        with pytest.raises(QueryExecutionError):
            graph.query(
                "UNWIND $rows AS row "
                "MERGE (n:Program {designation: row.designation, cycles: row.cycles})",
                {
                    "rows": [
                        {"designation": "Marvin", "cycles": 1},
                        {"designation": "Rinzler", "cycles": None},
                    ]
                },
            )
        after = graph.query("MATCH (n:Program) RETURN count(*) AS total").rows[0]["total"]
        assert after == before
