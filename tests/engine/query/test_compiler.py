# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for SQL compilation, pushdown analysis, and planning."""

import pytest

from pygrafito.engine.query.ast import Binary, Match, Unary
from pygrafito.engine.query.compiler import CompiledMatch, Compiler
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import Plan, PlanBuilder, PlanOperator
from pygrafito.engine.query.semantic import SemanticAnalyzer
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import QuerySemanticError
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository


class TestNodeCompilation:
    """Verify labels, property maps, and anonymous nodes compile to SQL."""

    def compile(
        self,
        text: str,
        parameters: dict[str, QueryValue] | None = None,
    ) -> CompiledMatch:
        statement = Parser.parse_statement(text)
        match = next(clause for clause in statement.clauses if isinstance(clause, Match))
        return Compiler(match).compile(parameters or {})

    def test_from_nodes(self) -> None:
        compiled = self.compile("MATCH (n) RETURN n")
        assert "FROM nodes AS n0" in compiled.sql
        assert "n0.id AS c0" in compiled.sql
        assert compiled.node_columns[0].variable == "n"

    def test_labels_use_exists_and_placeholders(self) -> None:
        compiled = self.compile("MATCH (n:Program:ISO) RETURN n")
        assert compiled.sql.count("EXISTS (SELECT 1 FROM node_labels") == 2
        assert compiled.arguments == ("Program", "ISO")
        assert "= ?" in compiled.sql

    def test_numeric_property_map_uses_type_guard(self) -> None:
        compiled = self.compile("MATCH (n {cycles: 36}) RETURN n")
        assert "json_type(n0.props, '$.\"cycles\"') IN ('integer', 'real')" in compiled.sql
        assert "json_extract(n0.props, '$.\"cycles\"') = ?" in compiled.sql
        assert compiled.arguments == (36,)

    def test_boolean_property_map(self) -> None:
        compiled = self.compile("MATCH (n {active: true}) RETURN n")
        assert "json_type(n0.props, '$.\"active\"') = ?" in compiled.sql
        assert compiled.arguments == ("true", 1)

    def test_string_property_map(self) -> None:
        compiled = self.compile("MATCH (n {designation: 'Quorra'}) RETURN n")
        assert "json_type(n0.props, '$.\"designation\"') = 'text'" in compiled.sql
        assert compiled.arguments == ("Quorra",)

    def test_list_property_map(self) -> None:
        compiled = self.compile("MATCH (n {tags: ['ISO', 'Program']}) RETURN n")
        assert "json_type(n0.props, '$.\"tags\"') = 'array'" in compiled.sql
        assert compiled.arguments == ('["ISO","Program"]',)

    def test_null_property_map_matches_nothing(self) -> None:
        compiled = self.compile("MATCH (n {designation: null}) RETURN n")
        assert compiled.sql.endswith("WHERE (0)")
        assert compiled.arguments == ()

    def test_quoted_property_key(self) -> None:
        compiled = self.compile("MATCH (n {`a.b`: 1}) RETURN n")
        assert "json_extract(n0.props, '$.\"a.b\"') = ?" in compiled.sql
        assert compiled.arguments == (1,)

    def test_property_path_is_inlined_not_bound(self) -> None:
        compiled = self.compile("MATCH (n {`a'b`: 1}) RETURN n")
        assert "json_extract(n0.props, '$.\"a''b\"') = ?" in compiled.sql
        assert compiled.arguments == (1,)
        paths = [
            argument
            for argument in compiled.arguments
            if isinstance(argument, str) and argument.startswith('$."')
        ]
        assert paths == []

    def test_property_map_parameter_is_bound(self) -> None:
        compiled = self.compile(
            "MATCH (n {designation: $name}) RETURN n",
            {"name": "Quorra"},
        )
        assert "Quorra" in compiled.arguments
        assert "Quorra" not in compiled.sql

    def test_anonymous_node_is_selected_but_not_bound(self) -> None:
        compiled = self.compile("MATCH (:Program)-[]->(n) RETURN n")
        assert compiled.node_columns[0].variable is None
        assert compiled.node_columns[1].variable == "n"

    def test_invalid_property_parameter_raises(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.compile(
                "MATCH (n {designation: $value}) RETURN n",
                {"value": {"nested": 1}},
            )


class TestRelationshipCompilation:
    """Verify directions, type alternatives, repeated variables, and paths."""

    def compile(
        self,
        text: str,
        parameters: dict[str, QueryValue] | None = None,
    ) -> CompiledMatch:
        statement = Parser.parse_statement(text)
        match = next(clause for clause in statement.clauses if isinstance(clause, Match))
        return Compiler(match).compile(parameters or {})

    def test_outgoing_join(self) -> None:
        compiled = self.compile("MATCH (a)-[r:ALLIES_WITH]->(b) RETURN b")
        assert "JOIN relationships AS r0 ON r0.src = n0.id" in compiled.sql
        assert "JOIN nodes AS n1 ON n1.id = r0.dst" in compiled.sql
        assert "r0.rel_type IN (?)" in compiled.sql
        assert "ALLIES_WITH" in compiled.arguments

    def test_incoming_join(self) -> None:
        compiled = self.compile("MATCH (a)<-[r:ALLIES_WITH]-(b) RETURN b")
        assert "JOIN relationships AS r0 ON r0.dst = n0.id" in compiled.sql
        assert "JOIN nodes AS n1 ON n1.id = r0.src" in compiled.sql

    def test_both_direction_uses_canonical_orientation(self) -> None:
        compiled = self.compile("MATCH (a)-[r]-(b) RETURN b")
        assert "(r0.src = n0.id OR r0.dst = n0.id)" in compiled.sql
        assert "n1.id = CASE WHEN r0.src = n0.id THEN r0.dst ELSE r0.src END" in compiled.sql

    def test_type_alternatives(self) -> None:
        compiled = self.compile("MATCH (a)-[r:ALLIES_WITH|TRUSTS]->(b) RETURN b")
        assert "r0.rel_type IN (?, ?)" in compiled.sql
        assert compiled.arguments == ("ALLIES_WITH", "TRUSTS")

    def test_relationship_properties(self) -> None:
        compiled = self.compile("MATCH (a)-[r {since_cycle: 2020}]->(b) RETURN r")
        assert "json_extract(r0.props, '$.\"since_cycle\"') = ?" in compiled.sql
        assert compiled.arguments == (2020,)

    def test_repeated_node_variable_adds_constraint(self) -> None:
        compiled = self.compile("MATCH (a)-[r]->(a) RETURN a")
        assert "JOIN nodes AS n1" not in compiled.sql
        assert "(n0.id = r0.dst)" in compiled.sql

    def test_repeated_relationship_variable_reuses_alias(self) -> None:
        compiled = self.compile("MATCH (a)-[r]->(b)-[r]->(c) RETURN r")
        assert compiled.sql.count("JOIN relationships AS r0") == 1
        assert "JOIN relationships AS r1" not in compiled.sql
        assert "(r0.src = n1.id)" in compiled.sql

    def test_path_selection(self) -> None:
        compiled = self.compile("MATCH p = (a)-[r]->(b) RETURN p")
        assert len(compiled.paths) == 1
        path = compiled.paths[0]
        assert path.variable == "p"
        assert len(path.nodes) == 2
        assert len(path.relationships) == 1
        assert path.relationships[0].variable == "r"

    def test_single_node_path_selection(self) -> None:
        compiled = self.compile("MATCH p = (a) RETURN p")
        assert compiled.paths[0].nodes == (compiled.node_columns[0].column,)
        assert compiled.paths[0].relationships == ()


class TestPushdown:
    """Verify WHERE splitting between SQL predicates and residual Python."""

    def compile(
        self,
        text: str,
        parameters: dict[str, QueryValue] | None = None,
    ) -> CompiledMatch:
        statement = Parser.parse_statement(text)
        match = next(clause for clause in statement.clauses if isinstance(clause, Match))
        return Compiler(match).compile(parameters or {})

    def test_and_of_pushable_predicates(self) -> None:
        compiled = self.compile(
            "MATCH (n) WHERE n.cycles > 1 AND n.designation = 'Quorra' RETURN n"
        )
        assert compiled.residual is None
        assert "json_extract(n0.props, '$.\"cycles\"') > ?" in compiled.sql
        assert "json_type(n0.props, '$.\"designation\"') = 'text'" in compiled.sql

    def test_or_of_pushable_predicates(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.cycles > 1 OR n.cycles < 0 RETURN n")
        assert compiled.residual is None
        assert " OR " in compiled.sql

    def test_or_with_residual_keeps_whole_expression(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.cycles > 1 OR abs(n.cycles) > 2 RETURN n")
        assert compiled.residual is not None
        assert isinstance(compiled.residual, Binary)

    def test_not_pushable(self) -> None:
        compiled = self.compile("MATCH (n) WHERE NOT n.cycles > 1 RETURN n")
        assert compiled.residual is None
        assert "NOT (" in compiled.sql

    def test_not_residual(self) -> None:
        compiled = self.compile("MATCH (n) WHERE NOT abs(n.cycles) > 1 RETURN n")
        assert isinstance(compiled.residual, Unary)

    def test_and_with_residual_half(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.cycles > 1 AND abs(n.cycles) > 2 RETURN n")
        assert compiled.residual is not None
        assert "json_extract(n0.props, '$.\"cycles\"') > ?" in compiled.sql

    def test_literal_list_membership_is_pushed_down(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.designation IN ['Quorra', 'Tron'] RETURN n")
        assert compiled.residual is None
        assert " OR " in compiled.sql
        assert "Quorra" in compiled.arguments
        assert "Tron" in compiled.arguments

    def test_empty_list_membership_is_false(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.designation IN [] RETURN n")
        assert compiled.residual is None
        assert "(0)" in compiled.sql

    def test_parameter_list_membership_is_residual(self) -> None:
        compiled = self.compile(
            "MATCH (n) WHERE n.designation IN $names RETURN n",
            {"names": ["Quorra"]},
        )
        assert isinstance(compiled.residual, Binary)
        assert compiled.residual.operator == "IN"

    def test_list_with_parameter_is_residual(self) -> None:
        compiled = self.compile(
            "MATCH (n) WHERE n.designation IN ['Quorra', $other] RETURN n",
            {"other": "Tron"},
        )
        assert isinstance(compiled.residual, Binary)
        assert compiled.residual.operator == "IN"

    def test_function_calls_are_residual(self) -> None:
        compiled = self.compile("MATCH (n) WHERE abs(n.cycles) > 2 RETURN n")
        assert compiled.residual is not None
        assert "n0.props" not in compiled.sql.split("WHERE")[-1]

    def test_arithmetic_is_residual(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.cycles + 1 > 2 RETURN n")
        assert compiled.residual is not None

    def test_null_tests_are_pushed_down(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.cycles IS NULL RETURN n")
        assert compiled.residual is None
        assert "json_type(n0.props, '$.\"cycles\"') IS NULL" in compiled.sql
        compiled = self.compile("MATCH (n) WHERE n.cycles IS NOT NULL RETURN n")
        assert "json_type(n0.props, '$.\"cycles\"') IS NOT NULL" in compiled.sql

    def test_string_predicates(self) -> None:
        starts = self.compile("MATCH (n) WHERE n.designation STARTS WITH 'Qu' RETURN n")
        assert "instr(json_extract(n0.props, '$.\"designation\"'), ?) = 1" in starts.sql
        ends = self.compile("MATCH (n) WHERE n.designation ENDS WITH 'ra' RETURN n")
        assert "substr(json_extract(n0.props, '$.\"designation\"'), -length(?)) = ?" in ends.sql
        contains = self.compile("MATCH (n) WHERE n.designation CONTAINS 'orr' RETURN n")
        assert "instr(json_extract(n0.props, '$.\"designation\"'), ?) > 0" in contains.sql

    def test_empty_ends_with_compiles_to_type_guard(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.designation ENDS WITH '' RETURN n")
        assert "json_type(n0.props, '$.\"designation\"') = 'text'" in compiled.sql
        assert "substr" not in compiled.sql

    def test_reversed_comparison_flips_operator(self) -> None:
        compiled = self.compile("MATCH (n) WHERE 1 < n.cycles RETURN n")
        assert compiled.residual is None
        assert "json_extract(n0.props, '$.\"cycles\"') > ?" in compiled.sql

    def test_property_to_property_comparison_is_residual(self) -> None:
        compiled = self.compile("MATCH (a)-[r]->(b) WHERE a.cycles < b.cycles RETURN a")
        assert isinstance(compiled.residual, Binary)

    def test_null_comparisons_stay_null(self) -> None:
        for text in (
            "MATCH (n) WHERE n.cycles = null RETURN n",
            "MATCH (n) WHERE n.cycles <> null RETURN n",
            "MATCH (n) WHERE n.cycles < null RETURN n",
            "MATCH (n) WHERE n.designation STARTS WITH null RETURN n",
        ):
            compiled = self.compile(text)
            assert compiled.residual is None
            assert "NULL" in compiled.sql

    def test_relationship_properties_are_pushable(self) -> None:
        compiled = self.compile("MATCH (a)-[r]->(b) WHERE r.since_cycle >= 2020 RETURN a")
        assert compiled.residual is None
        assert "json_extract(r0.props, '$.\"since_cycle\"') >= ?" in compiled.sql

    def test_parameter_values_are_never_interpolated(self) -> None:
        value = "Quorra' OR 1=1 --"
        compiled = self.compile(
            "MATCH (n) WHERE n.designation = $name RETURN n",
            {"name": value},
        )
        assert value in compiled.arguments
        assert value not in compiled.sql
        assert "?" in compiled.sql

    def test_boolean_equality(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.active = true RETURN n")
        assert compiled.residual is None
        assert "true" in compiled.arguments
        assert 1 in compiled.arguments

    def test_list_equality(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.tags = ['ISO'] RETURN n")
        assert compiled.residual is None
        assert '["ISO"]' in compiled.arguments

    def test_unorderable_comparison_is_residual(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.tags < [1] RETURN n")
        assert compiled.residual is not None

    def test_string_predicate_with_number_is_residual(self) -> None:
        compiled = self.compile("MATCH (n) WHERE n.designation STARTS WITH 1 RETURN n")
        assert compiled.residual is not None


class TestBatchNodeLoading:
    """Verify batch node loading returns the same snapshots as single reads."""

    def test_get_many_matches_get(self) -> None:
        database = Database(":memory:")
        try:
            repository = NodeRepository(database.connection, PropertyCodec())
            first = repository.create(("Program",), {"designation": "Kevin Flynn"})
            second = repository.create(("Program", "ISO"), {"designation": "Quorra"})
            loaded = repository.get_many([first.id, second.id, first.id, 999])
            assert loaded[first.id] == repository.get(first.id)
            assert loaded[second.id] == repository.get(second.id)
            assert set(loaded) == {first.id, second.id}
            assert repository.get_many([]) == {}
        finally:
            database.close()


class TestPlanPipeline:
    """Verify the physical operator pipeline is built in execution order."""

    def plan(self, text: str) -> Plan:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        return PlanBuilder.build(analysis)

    def test_projection_only(self) -> None:
        plan = self.plan("MATCH (n) RETURN n")
        assert plan.operators == (PlanOperator.MATCH, PlanOperator.PROJECT)

    def test_filter_projection(self) -> None:
        plan = self.plan("MATCH (n) WHERE n.cycles > 1 RETURN n")
        assert plan.operators == (
            PlanOperator.MATCH,
            PlanOperator.FILTER,
            PlanOperator.PROJECT,
        )

    def test_aggregation(self) -> None:
        plan = self.plan("MATCH (n) RETURN count(*)")
        assert plan.operators == (
            PlanOperator.MATCH,
            PlanOperator.PROJECT,
            PlanOperator.AGGREGATE,
        )

    def test_full_pipeline(self) -> None:
        plan = self.plan(
            "MATCH (n) WHERE n.cycles > 1 RETURN DISTINCT n.designation "
            "ORDER BY n.designation SKIP 1 LIMIT 2"
        )
        assert plan.operators == (
            PlanOperator.MATCH,
            PlanOperator.FILTER,
            PlanOperator.PROJECT,
            PlanOperator.DISTINCT,
            PlanOperator.ORDER,
            PlanOperator.SKIP,
            PlanOperator.LIMIT,
        )
        assert plan.includes(PlanOperator.ORDER)
        assert not plan.includes(PlanOperator.AGGREGATE)

    def test_create_only_pipeline(self) -> None:
        plan = self.plan("CREATE (n:Program)")
        assert plan.operators == (PlanOperator.CREATE,)

    def test_write_pipeline_follows_source_order(self) -> None:
        plan = self.plan(
            "MATCH (n:Program) SET n.cycles = 1 REMOVE n.cycles CREATE (m:Program) RETURN n"
        )
        assert plan.operators == (
            PlanOperator.MATCH,
            PlanOperator.SET,
            PlanOperator.REMOVE,
            PlanOperator.CREATE,
            PlanOperator.PROJECT,
        )

    def test_delete_pipeline(self) -> None:
        plan = self.plan("MATCH (n:Program) DETACH DELETE n")
        assert plan.operators == (PlanOperator.MATCH, PlanOperator.DELETE)

    def test_write_without_return_has_no_projection(self) -> None:
        plan = self.plan("MATCH (n:Program) SET n.cycles = 1")
        assert plan.operators == (PlanOperator.MATCH, PlanOperator.SET)
        assert not plan.includes(PlanOperator.PROJECT)
