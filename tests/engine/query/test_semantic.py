# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for static query analysis."""

import pytest

from pygrafito.engine.query.ast import (
    FunctionCall,
    Literal,
    Match,
    MatchMode,
    NodePattern,
    OrdinalityKind,
    Parameter,
    PathMode,
    PathPattern,
    RelationshipPattern,
    Return,
    ReturnItem,
    Set,
    Statement,
    Variable,
)
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.plan import Plan, PlanBuilder
from pygrafito.engine.query.semantic import (
    Analysis,
    CompoundAnalysis,
    LetStage,
    MatchStage,
    NextBoundary,
    OptionalMatchStage,
    SemanticAnalyzer,
    UnwindStage,
    VariableKind,
    WithStage,
    WriteStage,
    YieldStage,
)
from pygrafito.model import QuerySemanticError, QuerySyntaxError


class TestScopesAndKinds:
    """Verify pattern variables, their kinds, and scope rules."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_node_relationship_and_path_kinds(self) -> None:
        analysis = self.analyze("MATCH p = (a)-[r]->(b) RETURN a, r, b, p")
        assert analysis.variable_kinds["a"] is VariableKind.NODE
        assert analysis.variable_kinds["b"] is VariableKind.NODE
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP
        assert analysis.variable_kinds["p"] is VariableKind.PATH

    def test_repeated_node_variable_is_allowed(self) -> None:
        analysis = self.analyze("MATCH (a)-[r]->(a) RETURN a")
        assert analysis.variable_kinds["a"] is VariableKind.NODE

    def test_repeated_relationship_variable_is_allowed(self) -> None:
        analysis = self.analyze("MATCH (a)-[r]->(b)-[r]->(c) RETURN r")
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP

    def test_node_and_relationship_kind_conflict(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (x)-[x]->(b) RETURN x")
        assert "already bound" in caught.value.message

    def test_path_and_node_kind_conflict(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH p = (p) RETURN p")

    def test_path_variable_cannot_be_bound_twice(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH p = (a), p = (b) RETURN p")
        assert "already bound" in caught.value.message

    def test_unbound_variable_in_return(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) RETURN m")
        assert "not bound" in caught.value.message
        assert caught.value.line == 1
        assert caught.value.column is not None

    def test_unbound_variable_in_where(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) WHERE m.cycles = 1 RETURN n")

    def test_unbound_variable_in_order_by(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN n ORDER BY m.cycles")

    def test_path_variable_has_no_properties(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH p = (n) RETURN p.designation")
        assert "path variables" in caught.value.message

    def test_path_variable_can_be_projected(self) -> None:
        analysis = self.analyze("MATCH p = (a)-[r]->(b) RETURN p")
        assert analysis.columns == ("p",)

    def test_variable_kinds_are_read_only(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n")
        with pytest.raises(TypeError):
            analysis.variable_kinds["x"] = VariableKind.NODE  # type: ignore[index]


class TestFunctionChecks:
    """Verify scalar and aggregate function validation."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_valid_scalar_functions(self) -> None:
        analysis = self.analyze(
            "MATCH (n)-[r]->(m) RETURN "
            "id(n), labels(n), type(r), properties(n), keys(r), size(n.name), "
            "coalesce(n.name, 'x'), toInteger('1'), toFloat('1.5'), "
            "toString(1), lower(n.name), upper(n.name), trim(n.name), "
            "abs(n.cycles), concat(n.name, 'x'), startNode(r), endNode(r)"
        )
        assert len(analysis.columns) == 17

    def test_unknown_function(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) RETURN mystery(n)")
        assert "unknown function" in caught.value.message

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (n) RETURN id()",
            "MATCH (n) RETURN id(n, n)",
            "MATCH (n) RETURN coalesce()",
            "MATCH (n) RETURN lower(n, n)",
        ],
    )
    def test_arity_errors(self, text: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze(text)
        assert "expects" in caught.value.message

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (n) RETURN labels(1)",
            "MATCH (n) RETURN type(n)",
            "MATCH (n) RETURN id(1)",
            "MATCH (n) RETURN lower(1)",
            "MATCH (n) RETURN abs('x')",
            "MATCH (n) RETURN startNode(n)",
            "MATCH (n) RETURN properties(1)",
            "MATCH (n) RETURN sum('x')",
        ],
    )
    def test_argument_kind_errors(self, text: str) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze(text)
        assert "expected" in caught.value.message

    def test_aggregate_in_where_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) WHERE count(*) > 1 RETURN n")
        assert "not allowed" in caught.value.message

    def test_nested_aggregate_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) RETURN sum(count(n))")
        assert "nested" in caught.value.message

    def test_star_only_in_count(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN sum(*)")

    def test_distinct_star_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN count(DISTINCT *)")

    def test_distinct_only_on_aggregates(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN lower(DISTINCT n.name)")

    def test_count_star_is_valid(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN count(*)")
        assert analysis.has_aggregates

    def test_aggregate_inside_scalar_function_is_valid(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN abs(sum(n.cycles))")
        assert analysis.has_aggregates


class TestGroupingAndColumns:
    """Verify column names, duplicate rejection, and grouping discovery."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_alias_and_expression_text_column_names(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.designation AS name, n.cycles")
        assert analysis.columns == ("name", "n.cycles")

    def test_expression_text_is_used_without_an_alias(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.cycles + 1")
        assert analysis.columns == ("n.cycles + 1",)

    def test_generated_text_when_source_text_is_missing(self) -> None:
        statement = Statement(
            clauses=(
                Match(patterns=(PathPattern.simple(nodes=(NodePattern(variable="n"),)),)),
                Return(
                    items=(
                        ReturnItem(
                            expression=FunctionCall(
                                name="id",
                                arguments=(Variable(name="n"),),
                            )
                        ),
                    )
                ),
            )
        )
        analysis = SemanticAnalyzer.analyze(statement)
        assert analysis.columns == ("id(n)",)

    def test_duplicate_alias_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) RETURN n.a AS x, n.b AS x")
        assert "duplicate" in caught.value.message

    def test_duplicate_text_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN n.a, n.a")

    def test_grouping_keys_are_non_aggregate_items(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN labels(n), count(*)")
        assert analysis.has_aggregates
        assert len(analysis.grouping) == 1

    def test_mixed_aggregate_and_non_grouped_expression_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) RETURN n.cycles + count(*)")
        assert "grouping key" in caught.value.message

    def test_mixed_expression_is_accepted_when_grouped(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.cycles, n.cycles + count(*)")
        assert len(analysis.grouping) == 1

    def test_aggregate_plus_literal_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN count(*) + 1")
        assert analysis.has_aggregates

    def test_nested_non_grouped_function_call_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN count(*) + toInteger(n.cycles)")

    def test_grouped_subexpression_inside_aggregate_projection(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN labels(n), count(*) + size(labels(n))")
        assert analysis.has_aggregates


class TestParametersAndPagination:
    """Verify parameter collection, missing-parameter checks, and pagination."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_parameters_are_collected_everywhere(self) -> None:
        analysis = self.analyze(
            "MATCH (n {cycles: $pattern}) WHERE n.designation = $name "
            "RETURN n.cycles + $offset ORDER BY n.cycles SKIP $skip LIMIT $limit"
        )
        assert analysis.parameters == {
            "pattern",
            "name",
            "offset",
            "skip",
            "limit",
        }

    def test_require_parameters_rejects_missing(self) -> None:
        analysis = self.analyze("MATCH (n) WHERE n.cycles > $cycles RETURN n")
        with pytest.raises(QuerySemanticError) as caught:
            analysis.require_parameters({})
        assert "$cycles" in caught.value.message

    def test_require_parameters_ignores_extra(self) -> None:
        analysis = self.analyze("MATCH (n) WHERE n.cycles > $cycles RETURN n")
        analysis.require_parameters({"cycles": 1, "unused": 2})

    def test_parameter_in_identifier_position_is_a_syntax_error(self) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH (n:$p) RETURN n")

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (n) RETURN n SKIP -1",
            "MATCH (n) RETURN n SKIP 1.5",
            "MATCH (n) RETURN n SKIP true",
            "MATCH (n) RETURN n SKIP 'one'",
            "MATCH (n) RETURN n SKIP n.cycles",
            "MATCH (n) RETURN n LIMIT -1",
            "MATCH (n) RETURN n LIMIT 1.5",
            "MATCH (n) RETURN n LIMIT n.cycles",
        ],
    )
    def test_invalid_pagination_is_rejected(self, text: str) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze(text)

    def test_parameterized_pagination_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n SKIP $skip LIMIT $limit")
        assert analysis.parameters == {"skip", "limit"}


class TestOrderingResolution:
    """Verify aliases and projected expressions resolve to output columns."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_alias_resolves_to_column(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.designation AS name ORDER BY name DESC")
        assert analysis.sorts[0].column == 0
        assert analysis.sorts[0].descending

    def test_projected_expression_resolves_to_column(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.cycles ORDER BY n.cycles")
        assert analysis.sorts[0].column == 0

    def test_unprojected_expression_stays_an_expression(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN n.designation ORDER BY n.cycles")
        assert analysis.sorts[0].column is None
        assert analysis.sorts[0].expression is not None

    def test_aggregate_alias_resolves_to_column(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN count(*) AS total ORDER BY total")
        assert analysis.sorts[0].column == 0

    def test_unprojected_aggregate_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n) RETURN n.designation ORDER BY count(*)")

    def test_multiple_sort_keys_keep_their_order(self) -> None:
        analysis = self.analyze(
            "MATCH (n) RETURN n.designation AS name, n.cycles ORDER BY name, n.cycles DESC"
        )
        assert [sort.descending for sort in analysis.sorts] == [False, True]


class TestStagePipeline:
    """Verify read clauses are analysed into ordered stages."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_single_match_is_one_stage(self) -> None:
        analysis = self.analyze("MATCH (n:Program) RETURN n")
        assert len(analysis.stages) == 1
        assert isinstance(analysis.stages[0], MatchStage)
        assert analysis.stages[0].patterns[0].nodes[0].labels == ("Program",)

    def test_write_clauses_are_separate_from_stages(self) -> None:
        analysis = self.analyze("MATCH (n:Program) SET n.cycles = 1 RETURN n")
        assert len(analysis.stages) == 1
        assert len(analysis.write_clauses) == 1

    def test_optional_stage_records_introduced_variables(self) -> None:
        analysis = self.analyze(
            "MATCH (a:Program) OPTIONAL MATCH (a)-[r:ALLIES_WITH]->(b) RETURN a, b"
        )
        stage = analysis.stages[1]
        assert isinstance(stage, OptionalMatchStage)
        assert stage.introduced == {"r", "b"}
        assert analysis.variable_kinds["b"] is VariableKind.NODE


class TestWithStage:
    """Verify WITH projection, scope, and aggregation boundaries."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_scope_is_reset(self) -> None:
        analysis = self.analyze("MATCH (a:Program) WITH a.designation AS name RETURN name")
        assert set(analysis.variable_kinds) == {"name"}
        assert analysis.variable_kinds["name"] is VariableKind.SCALAR

    def test_node_alias_keeps_its_kind(self) -> None:
        analysis = self.analyze("MATCH (a:Program) WITH a RETURN a.designation")
        assert analysis.variable_kinds["a"] is VariableKind.NODE

    def test_expression_requires_an_alias(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a:Program) WITH a.cycles + 1 RETURN a")
        assert "must have an alias" in caught.value.message

    def test_duplicate_output_names_are_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a:Program) WITH a AS name, a.designation AS name RETURN name")

    def test_aggregate_alias_is_visible_downstream(self) -> None:
        analysis = self.analyze(
            "MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends WHERE friends > 1 RETURN a"
        )
        assert "friends" in analysis.variable_kinds

    def test_unprojected_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a:Program) WITH a.designation AS name RETURN a")


class TestVariableLength:
    """Verify quantified relationship bounds and the list variable kind."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_relationship_variable_is_a_list(self) -> None:
        analysis = self.analyze("MATCH (a)-[r:ALLIES_WITH*1..3]->(b) RETURN r")
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP_LIST

    def relationship(self, text: str) -> RelationshipPattern:
        analysis = self.analyze(text)
        stage = analysis.stages[0]
        if not isinstance(stage, MatchStage):
            raise AssertionError("expected a match stage")
        return stage.patterns[0].relationships[0]

    def test_bare_quantifier_has_no_upper_bound(self) -> None:
        relationship = self.relationship("MATCH (a)-[*]->(b) RETURN b")
        assert (relationship.min_hops, relationship.max_hops) == (0, None)

    def test_open_range_has_no_upper_bound(self) -> None:
        relationship = self.relationship("MATCH (a)-[*1..]->(b) RETURN b")
        assert (relationship.min_hops, relationship.max_hops) == (1, None)

    def test_negative_bounds_are_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a)-[*1..-2]->(b) RETURN b")

    def test_inverted_bounds_are_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a)-[*3..1]->(b) RETURN b")

    def test_type_rejects_a_relationship_list(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a)-[r*1..2]->(b) RETURN type(r)")

    def test_size_accepts_a_relationship_list(self) -> None:
        analysis = self.analyze("MATCH (a)-[r*1..2]->(b) RETURN size(r) AS length")
        assert analysis.columns == ("length",)

    def test_property_access_rejects_a_relationship_list(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a)-[r*1..2]->(b) RETURN r.since_cycle")

    def test_create_rejects_a_quantified_relationship(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a), (b) CREATE (a)-[*1..2]->(b)")


class TestQuerySurfaceAnalysis:
    """Verify semantic checks for the new expression and query surface."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def analyze_compound(self, text: str) -> CompoundAnalysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, CompoundAnalysis)
        return analysis

    def test_with_star_preserves_kinds(self) -> None:
        analysis = self.analyze(
            "MATCH (a:Program)-[r:TRUSTS]->(b:Program) "
            "WITH * RETURN a.designation AS a, b.designation AS b"
        )
        assert analysis.variable_kinds["a"] is VariableKind.NODE
        assert analysis.variable_kinds["b"] is VariableKind.NODE
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP

    def test_with_star_is_the_only_projection(self) -> None:
        with pytest.raises(QuerySyntaxError):
            self.analyze("MATCH (n:Program) WITH *, n.cycles AS cycles RETURN n")

    def test_list_comprehension_variable_cannot_shadow(self) -> None:
        with pytest.raises(QuerySemanticError, match="already bound"):
            self.analyze("MATCH (n:Program) RETURN [n IN [1, 2] | n] AS values")

    def test_non_list_index_target_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n:Program) RETURN 36[0] AS value")

    def test_non_list_comprehension_source_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (n:Program) RETURN [x IN 36 | x] AS values")

    def test_subquery_analysis_is_recorded(self) -> None:
        analysis = self.analyze(
            "MATCH (n:Program) WHERE EXISTS { MATCH (n)-[:TRUSTS]->(m:Program) } "
            "RETURN n.designation"
        )
        assert analysis.subquery_analyses

    def test_subquery_requires_a_row_source(self) -> None:
        with pytest.raises(QuerySemanticError, match="row source"):
            self.analyze("MATCH (n:Program) RETURN EXISTS { WITH n } AS found")

    def test_subquery_scope_does_not_leak(self) -> None:
        with pytest.raises(QuerySemanticError, match="not bound"):
            self.analyze(
                "MATCH (n:Program) RETURN EXISTS { MATCH (m:Program) } AS found, m.designation"
            )

    def test_subquery_cannot_shadow_with_let(self) -> None:
        with pytest.raises(QuerySemanticError, match="already bound"):
            self.analyze("MATCH (n:Program) RETURN EXISTS { LET n = 1 } AS found")

    def test_compound_columns_must_match(self) -> None:
        with pytest.raises(QuerySemanticError, match="same names"):
            self.analyze_compound(
                "MATCH (n:Program) RETURN n.designation AS name "
                "UNION MATCH (m:Program) RETURN m.designation AS label"
            )

    def test_compound_columns_come_from_the_first_operand(self) -> None:
        analysis = self.analyze_compound(
            "MATCH (n:Program) RETURN n.designation AS name "
            "UNION ALL MATCH (m:User) RETURN m.designation AS name"
        )
        assert analysis.columns == ("name",)

    def test_compound_rejects_writes(self) -> None:
        with pytest.raises(QuerySemanticError, match="read-only"):
            self.analyze_compound("CREATE (n:Program) UNION MATCH (m:Program) RETURN m")

    def test_compound_rejects_finish(self) -> None:
        with pytest.raises(QuerySemanticError, match="FINISH"):
            self.analyze_compound("MATCH (n:Program) FINISH UNION MATCH (m:Program) RETURN m")

    def test_compound_rejects_return_no_bindings(self) -> None:
        with pytest.raises(QuerySemanticError, match="NO BINDINGS"):
            self.analyze_compound(
                "MATCH (n:Program) RETURN NO BINDINGS UNION MATCH (m:Program) RETURN m"
            )

    def test_compound_order_must_name_a_column(self) -> None:
        with pytest.raises(QuerySemanticError, match="output column"):
            self.analyze_compound(
                "MATCH (n:Program) RETURN n.designation AS name "
                "UNION MATCH (m:Program) RETURN m.designation AS name "
                "ORDER BY n.designation"
            )


class TestUnsupportedConstructs:
    """Verify every recognized unsupported construct raises a query error."""

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (a) CALL { MATCH (b) RETURN b } RETURN a",
        ],
    )
    def test_each_boundary_is_rejected(self, text: str) -> None:
        with pytest.raises(QuerySemanticError):
            Parser.parse_statement(text)


class TestExpressionChecks:
    """Verify static arithmetic and string-predicate operand checks."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (n) RETURN 'x' + 1",
            "MATCH (n) RETURN -'x'",
            "MATCH (n) WHERE 1 STARTS WITH 2 RETURN n",
            "MATCH (n) WHERE 1 ENDS WITH 2 RETURN n",
            "MATCH (n) WHERE 1 CONTAINS 2 RETURN n",
        ],
    )
    def test_non_numeric_or_non_string_operands_are_rejected(self, text: str) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze(text)

    def test_parameter_in_pattern_property_map_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (n {designation: $name, tags: [$first, 'ISO']}) RETURN n")
        assert analysis.parameters == {"name", "first"}

    def test_forward_variable_in_pattern_property_map_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n {cycles: n.other}) RETURN n")
        assert "not bound" in caught.value.message

    def test_variable_from_an_earlier_stage_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (m) MATCH (n {cycles: m.cycles}) RETURN n")
        assert analysis.parameters == frozenset()

    def test_unaliasable_column_uses_parameter_text(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN $value")
        assert analysis.columns == ("$value",)
        assert analysis.parameters == {"value"}

    def test_literal_column_text_and_alias(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN 1 AS one")
        assert analysis.columns == ("one",)
        assert isinstance(analysis.items[0].expression, Literal)
        assert analysis.return_clause is not None
        assert isinstance(analysis.return_clause.items[0].expression, Literal)
        assert isinstance(analysis.items[0].expression, Literal)

    def test_parameter_expression_is_preserved(self) -> None:
        analysis = self.analyze("MATCH (n) RETURN $p")
        assert isinstance(analysis.items[0].expression, Parameter)


class TestWriteAnalysis:
    """Verify static analysis of statements that mutate the graph."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_read_statement_is_not_a_write(self) -> None:
        analysis = self.analyze("MATCH (n:Program) RETURN n.designation AS name")
        assert not analysis.is_write
        assert analysis.columns == ("name",)

    def test_write_without_return_has_no_columns(self) -> None:
        analysis = self.analyze("MATCH (n:Program) SET n.cycles = 1")
        assert analysis.is_write
        assert analysis.columns == ()
        assert analysis.return_clause is None

    def test_write_with_return_has_columns(self) -> None:
        analysis = self.analyze("CREATE (n:Program) RETURN n.designation AS name")
        assert analysis.is_write
        assert analysis.columns == ("name",)

    def test_created_variable_is_in_scope_for_later_clauses(self) -> None:
        analysis = self.analyze("CREATE (n:Program) SET n.cycles = 1 RETURN n.cycles AS c")
        assert analysis.variable_kinds["n"] is VariableKind.NODE

    def test_created_relationship_variable_is_in_scope(self) -> None:
        analysis = self.analyze("MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r:TRUSTS]->(b) RETURN r")
        assert analysis.variable_kinds["r"] is VariableKind.RELATIONSHIP

    def test_set_on_unbound_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("SET n.cycles = 1")
        assert "not bound" in caught.value.message

    def test_remove_on_unbound_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("REMOVE n.cycles")
        assert "not bound" in caught.value.message

    def test_delete_on_unbound_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("DELETE n")

    def test_label_on_relationship_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (a)-[r]->(b) SET r:SystemMonitor")
        assert analysis.is_write

    def test_remove_label_from_relationship_is_accepted(self) -> None:
        analysis = self.analyze("MATCH (a)-[r]->(b) REMOVE r:SystemMonitor")
        assert analysis.is_write

    def test_delete_path_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH p = (a)-[r]->(b) DELETE p")
        assert "path variable" in caught.value.message

    def test_create_relationship_requires_bound_endpoints(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("CREATE (a)-[r:ALLIES_WITH]->(b)")
        assert "already bound" in caught.value.message

    def test_create_relationship_with_one_unbound_endpoint_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r:TRUSTS]->(c)")

    def test_create_relationship_allows_no_label(self) -> None:
        analysis = self.analyze("MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r]->(b)")
        assert analysis.is_write

    def test_create_relationship_rejects_multiple_labels(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r:TRUSTS|ISO]->(b)")
        assert "at most one label" in caught.value.message

    def test_create_relationship_requires_outgoing_direction(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)<-[r:TRUSTS]-(b)")
        assert "direction" in caught.value.message

    def test_create_path_variable_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("CREATE p = (n:Program)")
        assert "path variable" in caught.value.message

    def test_create_cannot_change_a_bound_node(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a) CREATE (a:ISO)")
        assert "use SET" in caught.value.message

    def test_return_after_write_keeps_aggregate_checks(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("CREATE (n:Program) SET n.cycles = 1 RETURN count(*) + n.cycles")

    def test_return_after_write_projects_created_variable(self) -> None:
        analysis = self.analyze("CREATE (n:Program) RETURN count(*) AS total")
        assert analysis.columns == ("total",)
        assert analysis.has_aggregates

    def test_create_property_map_accepts_row_expressions(self) -> None:
        analysis = self.analyze("MATCH (m) CREATE (n:Program {designation: m.designation})")
        assert analysis.is_write

    def test_create_property_map_rejects_a_forward_variable(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("CREATE (n:Program {designation: n.designation})")

    def test_create_property_map_accepts_parameters(self) -> None:
        analysis = self.analyze("CREATE (n:Program {designation: $name})")
        assert analysis.parameters == {"name"}


class TestUnwindAndMergeAnalysis:
    """Verify UNWIND stages and MERGE write analysis."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_unwind_stage_and_scalar_kind(self) -> None:
        analysis = self.analyze("UNWIND $rows AS row RETURN row.designation")
        assert isinstance(analysis.stages[0], UnwindStage)
        assert analysis.variable_kinds["row"] is VariableKind.SCALAR
        assert analysis.parameters == {"rows"}
        assert not analysis.is_write

    def test_unwind_only_read_statement_is_valid(self) -> None:
        analysis = self.analyze("UNWIND [1, 2] AS value RETURN value")
        assert analysis.columns == ("value",)

    def test_unwind_null_is_accepted(self) -> None:
        analysis = self.analyze("UNWIND null AS value RETURN value")
        assert isinstance(analysis.stages[0], UnwindStage)

    def test_unwind_rejects_redefinition(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (n) UNWIND [1] AS n RETURN n")
        assert "already bound" in caught.value.message

    def test_unwind_rejects_a_non_list_literal(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("UNWIND 36 AS value RETURN value")
        assert "list" in caught.value.message

    def test_merge_is_a_write_and_binds_its_node(self) -> None:
        analysis = self.analyze("MERGE (n:Program) RETURN n")
        assert analysis.is_write
        assert analysis.variable_kinds["n"] is VariableKind.NODE
        assert analysis.columns == ("n",)

    def test_merge_without_return_has_no_columns(self) -> None:
        analysis = self.analyze("MERGE (n:Program {designation: 'Tron'})")
        assert analysis.is_write
        assert analysis.columns == ()

    def test_merge_rejects_a_path_variable(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MERGE path = (a:Program)-[:TRUSTS]->(b:Program)")
        assert "path variable" in caught.value.message

    def test_merge_rejects_a_quantified_relationship(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MERGE (a)-[:ALLIES_WITH*1..2]->(b)")
        assert "variable-length" in caught.value.message

    def test_merge_rejects_a_missing_type(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MERGE (a:Program)-[]->(b:Program)")
        assert "exactly one type" in caught.value.message

    def test_merge_rejects_an_undirected_relationship(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MERGE (a:Program)-[:TRUSTS]-(b:Program)")
        assert "direction" in caught.value.message

    def test_merge_rejects_a_bound_relationship(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH ()-[r:TRUSTS]->() MERGE (a)-[r:TRUSTS]->(b)")
        assert "rebind" in caught.value.message

    def test_merge_accepts_a_bound_anchor(self) -> None:
        analysis = self.analyze("MATCH (a:Program) MERGE (a)-[:TRUSTS]->(b:Program) RETURN b")
        assert analysis.variable_kinds["b"] is VariableKind.NODE

    def test_merge_rejects_changing_a_bound_node(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            self.analyze("MATCH (a) MERGE (a:ISO) RETURN a")
        assert "use SET" in caught.value.message

    def test_merge_rejects_a_forward_property_value(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MERGE (a:Program {designation: b.designation})-[:TRUSTS]->(b:Program)")

    def test_merge_rejects_an_aggregate_property_value(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MERGE (n:Program {designation: count(*)})")

    def test_merge_accepts_a_row_property_value(self) -> None:
        analysis = self.analyze(
            "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) RETURN n"
        )
        assert analysis.parameters == {"rows"}

    def test_merge_conditional_updates_are_analysed(self) -> None:
        analysis = self.analyze(
            "MERGE (n:Program {designation: 'Tron'}) "
            "ON CREATE SET n.cycles = 40 ON MATCH SET n.cycles = n.cycles + 1 RETURN n"
        )
        assert analysis.is_write

    def test_merge_conditional_unbound_target_is_rejected(self) -> None:
        with pytest.raises(QuerySemanticError):
            self.analyze("MERGE (n:Program) ON CREATE SET m.cycles = 1")

    def test_merge_conditional_label_on_relationship_is_accepted(self) -> None:
        analysis = self.analyze("MERGE (a:Program)-[r:TRUSTS]->(b:Program) ON CREATE SET r:ISO")
        assert analysis.is_write

    def test_merge_conditional_null_removal_is_accepted(self) -> None:
        analysis = self.analyze("MERGE (n:Program) ON MATCH SET n.cycles = null RETURN n")
        assert analysis.is_write


class TestPathModeResolution:
    """Verify the effective path mode and the quantifier mixing rule."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def mode(self, text: str) -> PathMode | None:
        analysis = self.analyze(text)
        stage = analysis.stages[0]
        if not isinstance(stage, MatchStage):
            raise AssertionError("expected a match stage")
        return stage.patterns[0].mode

    def test_default_is_walk(self) -> None:
        """Resolve a plain canonical path to WALK."""
        assert self.mode("MATCH (a)-[:TRUSTS]->(b) RETURN b") is PathMode.WALK

    def test_legacy_quantifier_implies_trail(self) -> None:
        """Resolve a legacy quantifier to TRAIL."""
        assert self.mode("MATCH (a)-[:TRUSTS*1..3]->(b) RETURN b") is PathMode.TRAIL

    def test_clause_mode_wins_over_the_default(self) -> None:
        """Resolve the clause mode before the quantifier default."""
        assert self.mode("MATCH SIMPLE (a)-[:TRUSTS]->(b) RETURN b") is PathMode.SIMPLE

    def test_explicit_path_mode_wins_over_the_clause(self) -> None:
        """Resolve a per-path mode before the clause mode."""
        analysis = self.analyze("MATCH WALK (a), ACYCLIC (b)-[:TRUSTS*1..2]->(c) RETURN c")
        stage = analysis.stages[0]
        if not isinstance(stage, MatchStage):
            raise AssertionError("expected a match stage")
        assert stage.patterns[0].mode is PathMode.WALK
        assert stage.patterns[1].mode is PathMode.ACYCLIC

    def test_canonical_quantifier_implies_walk(self) -> None:
        """Resolve a canonical quantifier to WALK."""
        assert self.mode("MATCH (a)-[:TRUSTS{1,3}]->(b) RETURN b") is PathMode.WALK

    @pytest.mark.parametrize(
        "text",
        [
            "MATCH (a)-[:TRUSTS*]->(b) RETURN b",
            "MATCH (a)-[:TRUSTS+]->(b) RETURN b",
            "MATCH (a)-[:TRUSTS{2,}]->(b) RETURN b",
        ],
    )
    def test_open_canonical_quantifier_implies_walk(self, text: str) -> None:
        """Resolve each canonical open form to WALK."""
        assert self.mode(text) is PathMode.WALK

    def test_open_legacy_quantifier_implies_trail(self) -> None:
        """Keep the legacy open form's TRAIL default."""
        assert self.mode("MATCH (a)-[:TRUSTS*2..]->(b) RETURN b") is PathMode.TRAIL

    def test_explicit_mode_wins_over_an_open_legacy_quantifier(self) -> None:
        """Honor an explicit mode over the legacy open default."""
        assert self.mode("MATCH WALK (a)-[:TRUSTS*2..]->(b) RETURN b") is PathMode.WALK

    def test_explicit_clause_mode_wins_over_canonical(self) -> None:
        """Keep an explicit clause mode over the canonical default."""
        assert self.mode("MATCH TRAIL (a)-[:TRUSTS{1,3}]->(b) RETURN b") is PathMode.TRAIL

    def test_mixed_quantifiers_are_rejected(self) -> None:
        """Reject a path that mixes both quantifier forms without a mode."""
        with pytest.raises(QuerySemanticError) as raised:
            self.analyze("MATCH (a)-[:TRUSTS*1..2]->(b)-[:TRUSTS{1,2}]->(c) RETURN c")
        assert "mix" in raised.value.message

    def test_explicit_mode_resolves_mixed_quantifiers(self) -> None:
        """Accept a mixed path when an explicit mode is named."""
        analysis = self.analyze("MATCH TRAIL (a)-[:TRUSTS*1..2]->(b)-[:TRUSTS{1,2}]->(c) RETURN c")
        stage = analysis.stages[0]
        if not isinstance(stage, MatchStage):
            raise AssertionError("expected a match stage")
        assert stage.patterns[0].mode is PathMode.TRAIL


class TestMatchModeResolution:
    """Verify the clause match mode reaches stages and plans."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def stage(self, text: str) -> MatchStage | OptionalMatchStage:
        analysis = self.analyze(text)
        stage = analysis.stages[0]
        if not isinstance(stage, MatchStage | OptionalMatchStage):
            raise AssertionError("expected a match stage")
        return stage

    def test_default_match_mode_is_repeatable(self) -> None:
        """Default the stage to repeatable elements."""
        assert self.stage("MATCH (a) RETURN a").match_mode is MatchMode.REPEATABLE_ELEMENTS

    def test_explicit_match_mode_reaches_the_stage(self) -> None:
        """Carry DIFFERENT EDGES on a mandatory stage."""
        stage = self.stage("MATCH DIFFERENT EDGES (a) RETURN a")
        assert stage.match_mode is MatchMode.DIFFERENT_EDGES

    def test_optional_stage_carries_the_match_mode(self) -> None:
        """Carry DIFFERENT EDGES on an optional stage."""
        stage = self.stage("OPTIONAL MATCH DIFFERENT EDGES (a) RETURN a")
        assert isinstance(stage, OptionalMatchStage)
        assert stage.match_mode is MatchMode.DIFFERENT_EDGES

    def test_default_and_repeatable_plans_agree(self) -> None:
        """Produce the same operators for the default and explicit repeatable mode."""
        default = PlanBuilder.build(self.analyze("MATCH (a) RETURN a"))
        repeatable = PlanBuilder.build(self.analyze("MATCH REPEATABLE ELEMENTS (a) RETURN a"))
        assert isinstance(default, Plan)
        assert isinstance(repeatable, Plan)
        assert default.operators == repeatable.operators

    def test_plan_distinguishes_different_edges(self) -> None:
        """Expose the explicit mode in the plan operators."""
        analysis = self.analyze("MATCH DIFFERENT EDGES (a) RETURN a")
        plan = PlanBuilder.build(analysis)
        assert isinstance(plan, Plan)
        assert "different_edges" in plan.operators

    def test_adjacent_different_edges_clauses_stay_separate(self) -> None:
        """Do not fuse clauses whose scope must not cross."""
        analysis = self.analyze(
            "MATCH DIFFERENT EDGES (a)-[:TRUSTS]->(b) "
            "MATCH DIFFERENT EDGES (c)-[:TRUSTS]->(d) RETURN c"
        )
        plan = PlanBuilder.build(analysis)
        assert isinstance(plan, Plan)
        assert len(plan.stages) == 2
        for stage in plan.stages:
            if not isinstance(stage.stage, MatchStage | OptionalMatchStage):
                raise AssertionError("expected a match stage")
            assert stage.stage.match_mode is MatchMode.DIFFERENT_EDGES

    def test_default_adjacent_matches_still_fuse(self) -> None:
        """Keep the existing fusion for repeatable clauses."""
        analysis = self.analyze("MATCH (a)-[:TRUSTS]->(b) MATCH (b)-[:TRUSTS]->(c) RETURN c")
        plan = PlanBuilder.build(analysis)
        assert isinstance(plan, Plan)
        assert len(plan.stages) == 1


class TestPlanCarriesPathModes:
    """Verify the resolved mode survives into the execution plan."""

    def test_plan_stage_carries_the_resolved_mode(self) -> None:
        """Expose the resolved mode on the planned match stage."""
        analysis = SemanticAnalyzer.analyze(
            Parser.parse_statement("MATCH TRAIL (a)-[:TRUSTS*1..2]->(b) RETURN b")
        )
        plan = PlanBuilder.build(analysis)
        assert isinstance(plan, Plan)
        stage = plan.stages[0].stage
        if not isinstance(stage, MatchStage):
            raise AssertionError("expected a match stage")
        assert stage.patterns[0].mode is PathMode.TRAIL


class TestOperationPipeline:
    """Verify the analysed operations preserve source order and composition."""

    def analyze(self, text: str) -> Analysis:
        analysis = SemanticAnalyzer.analyze(Parser.parse_statement(text))
        assert isinstance(analysis, Analysis)
        return analysis

    def test_write_stage_sits_between_read_stages(self) -> None:
        analysis = self.analyze(
            "MATCH (n:Program) SET n.cycles = 1 NEXT MATCH (m:Program) RETURN m"
        )
        assert [type(operation).__name__ for operation in analysis.operations] == [
            "MatchStage",
            "WriteStage",
            "NextBoundary",
            "MatchStage",
        ]
        write = analysis.operations[1]
        if not isinstance(write, WriteStage):
            raise AssertionError("expected a write stage")
        assert isinstance(write.clause, Set)
        assert len(analysis.stages) == 2
        assert len(analysis.write_clauses) == 1

    def test_intermediate_return_is_a_segment_projection(self) -> None:
        analysis = self.analyze("MATCH (n:Program) RETURN n AS element NEXT RETURN element")
        stage = analysis.stages[1]
        if not isinstance(stage, WithStage):
            raise AssertionError("expected a projection stage")
        assert stage.segment_return is True
        assert stage.items[0].name == "element"
        assert analysis.columns == ("element",)

    def test_yield_stage_resets_the_scope(self) -> None:
        analysis = self.analyze(
            "MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles "
            "NEXT YIELD name RETURN name"
        )
        stage = analysis.stages[2]
        if not isinstance(stage, YieldStage):
            raise AssertionError("expected a yield stage")
        assert [item.name for item in stage.items] == ["name"]
        assert set(analysis.variable_kinds) == {"name"}

    def test_let_stage_preserves_a_direct_variable_kind(self) -> None:
        analysis = self.analyze(
            "MATCH (n:Program) LET element = n MATCH (element)-[:TRUSTS]->(m) RETURN m"
        )
        stage = analysis.stages[1]
        if not isinstance(stage, LetStage):
            raise AssertionError("expected a LET stage")
        assert stage.assignments[0].name == "element"
        assert analysis.variable_kinds["element"] is VariableKind.NODE

    def test_unwind_stage_carries_the_ordinality(self) -> None:
        analysis = self.analyze("FOR value IN [1, 2] WITH ORDINALITY index RETURN value, index")
        stage = analysis.stages[0]
        if not isinstance(stage, UnwindStage):
            raise AssertionError("expected an UNWIND stage")
        assert stage.index == "index"
        assert stage.ordinality is OrdinalityKind.ORDINALITY

    def test_explicit_grouping_is_recorded(self) -> None:
        analysis = self.analyze("MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles")
        assert analysis.grouping_explicit is True
        assert len(analysis.grouping) == 1

    def test_finish_has_no_result_projection(self) -> None:
        analysis = self.analyze("MATCH (n:Program) FINISH")
        assert analysis.finish is True
        assert analysis.return_clause is None
        assert analysis.columns == ()
        assert analysis.items == ()

    def test_no_bindings_has_an_empty_projection(self) -> None:
        analysis = self.analyze("MATCH (n:Program) RETURN NO BINDINGS")
        assert analysis.columns == ()
        assert analysis.items == ()
        assert analysis.return_clause is not None
        assert analysis.return_clause.no_bindings is True

    def test_next_boundary_is_part_of_the_pipeline(self) -> None:
        analysis = self.analyze(
            "MATCH (n:Program) RETURN n AS element NEXT YIELD element RETURN element"
        )
        assert any(isinstance(operation, NextBoundary) for operation in analysis.operations)
