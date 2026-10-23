# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for parsing query statements and expressions."""

import pytest

from pygrafito.engine.query.ast import (
    Binary,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    Operators,
    Parameter,
    Property,
    Star,
    Unary,
    Variable,
)
from pygrafito.engine.query.parser import Parser
from pygrafito.model import Direction, QuerySemanticError, QuerySyntaxError


class TestAcceptedSyntax:
    """Verify accepted statements and their parsed shape."""

    def parse(self, text: str) -> object:
        return Parser.parse_statement(text)

    def test_minimal_query(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n.designation AS name")
        assert len(statement.pattern.nodes) == 1
        assert statement.pattern.nodes[0].labels == ("Program",)
        assert statement.return_items[0].alias == "name"
        assert statement.return_items[0].text == "n.designation"

    def test_keywords_are_case_insensitive(self) -> None:
        statement = Parser.parse_statement("match (n) where true return n")
        assert statement.where == Literal(value=True)

    def test_keyword_casing_does_not_change_identifiers(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n")
        assert statement.pattern.nodes[0].labels == ("Program",)

    def test_comments_are_ignored(self) -> None:
        statement = Parser.parse_statement("MATCH // line\n (n) /* block */ RETURN n // trailing")
        assert statement.pattern.nodes[0].variable == "n"

    def test_node_labels_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (p:Program:ISO {designation: 'Quorra', cycles: $cycles}) RETURN p"
        )
        node = statement.pattern.nodes[0]
        assert node.labels == ("Program", "ISO")
        assert [entry.key for entry in node.properties] == ["designation", "cycles"]
        cycles = node.properties[1].value
        assert isinstance(cycles, Parameter)
        assert cycles.name == "cycles"

    def test_anonymous_node_and_relationship(self) -> None:
        statement = Parser.parse_statement("MATCH (:Program)-[]->(:Program) RETURN 1")
        assert statement.pattern.nodes[0].variable is None
        assert statement.pattern.relationships[0].variable is None
        assert statement.pattern.nodes[1].variable is None

    def test_path_variable(self) -> None:
        statement = Parser.parse_statement("MATCH p = (a)-[r]->(b) RETURN p")
        assert statement.pattern.variable == "p"

    def test_relationship_directions(self) -> None:
        outgoing = Parser.parse_statement("MATCH (a)-->(b) RETURN b")
        incoming = Parser.parse_statement("MATCH (a)<--(b) RETURN b")
        both = Parser.parse_statement("MATCH (a)--(b) RETURN b")
        bracketed = Parser.parse_statement("MATCH (a)-[r]-(b) RETURN b")
        assert outgoing.pattern.relationships[0].direction is Direction.OUTGOING
        assert incoming.pattern.relationships[0].direction is Direction.INCOMING
        assert both.pattern.relationships[0].direction is Direction.BOTH
        assert bracketed.pattern.relationships[0].direction is Direction.BOTH

    def test_relationship_types_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a)-[r:ALLIES_WITH|TRUSTS {since_cycle: 2020}]->(b) RETURN r"
        )
        relationship = statement.pattern.relationships[0]
        assert relationship.types == ("ALLIES_WITH", "TRUSTS")
        assert relationship.properties[0].key == "since_cycle"
        assert relationship.direction is Direction.OUTGOING

    def test_multiple_segments(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program)-[:ALLIES_WITH]->(b)-[:TRUSTS]->(c) RETURN c"
        )
        assert len(statement.pattern.nodes) == 3
        assert len(statement.pattern.relationships) == 2

    def test_backtick_identifiers(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (`a.b`:`Grid Node`)-[`r.x`:`GRID LINK` {`a.b`: 1}]->(b) "
            "RETURN `a.b`.`a.b` AS `the value`"
        )
        node = statement.pattern.nodes[0]
        assert node.variable == "a.b"
        assert node.labels == ("Grid Node",)
        relationship = statement.pattern.relationships[0]
        assert relationship.variable == "r.x"
        assert relationship.types == ("GRID LINK",)
        assert relationship.properties[0].key == "a.b"
        assert statement.return_items[0].alias == "the value"

    def test_property_map_with_list_and_negative_number(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n {tags: ['ISO', 'Program'], offset: -3}) RETURN n"
        )
        values = [entry.value for entry in statement.pattern.nodes[0].properties]
        assert isinstance(values[0], ListLiteral)
        assert isinstance(values[1], Unary)

    def test_where_distinct_order_skip_limit_and_semicolon(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) WHERE n.cycles > 1 "
            "RETURN DISTINCT n.designation AS name, n.cycles "
            "ORDER BY n.cycles DESC, name ASC SKIP 2 LIMIT 5;"
        )
        assert isinstance(statement.where, Binary)
        assert statement.distinct
        assert statement.order_by[0].descending
        second_sort = statement.order_by[1].expression
        assert isinstance(second_sort, Variable)
        assert second_sort.name == "name"
        assert statement.skip == Literal(value=2)
        assert statement.limit == Literal(value=5)

    def test_parameterized_pagination(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN n SKIP $skip LIMIT $limit")
        assert isinstance(statement.skip, Parameter)
        assert statement.skip.name == "skip"
        assert isinstance(statement.limit, Parameter)
        assert statement.limit.name == "limit"

    def test_function_calls(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) RETURN count(*), count(DISTINCT n.designation), labels(n)"
        )
        first, second, third = statement.return_items
        assert isinstance(first.expression, FunctionCall)
        assert isinstance(first.expression.arguments[0], Star)
        assert isinstance(second.expression, FunctionCall)
        assert second.expression.distinct
        assert isinstance(third.expression, FunctionCall)
        assert third.expression.name == "labels"

    def test_numeric_and_boolean_literals(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN 36, 36.5, 'text', true, false, null")
        expressions = [item.expression for item in statement.return_items]
        assert all(isinstance(expression, Literal) for expression in expressions)
        literals = [
            expression.value for expression in expressions if isinstance(expression, Literal)
        ]
        assert literals == [
            36,
            36.5,
            "text",
            True,
            False,
            None,
        ]

    def test_list_literal(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN [1, 2, n.cycles]")
        expression = statement.return_items[0].expression
        assert isinstance(expression, ListLiteral)
        assert len(expression.items) == 3

    def test_operator_precedence(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN n.cycles + n.cycles * 2")
        expression = statement.return_items[0].expression
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.ADD
        assert isinstance(expression.right, Binary)
        assert expression.right.operator == Operators.MULTIPLY

    def test_boolean_precedence(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE NOT n.active AND n.visible OR n.pinned RETURN n"
        )
        expression = statement.where
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.OR
        assert isinstance(expression.left, Binary)
        assert expression.left.operator == Operators.AND
        assert isinstance(expression.left.left, Unary)

    def test_parentheses_change_grouping(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN (n.cycles + n.cycles) * n.cycles")
        expression = statement.return_items[0].expression
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.MULTIPLY
        assert isinstance(expression.left, Binary)

    def test_unary_minus_and_positive(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN -1, +2")
        assert isinstance(statement.return_items[0].expression, Unary)
        assert isinstance(statement.return_items[1].expression, Unary)

    def test_comparisons_and_membership(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.cycles >= 36 AND n.designation IN ['Quorra', 'Tron'] RETURN n"
        )
        assert statement.where is not None
        assert isinstance(statement.where, Binary)

    def test_not_equal_spellings_are_normalized(self) -> None:
        first = Parser.parse_statement("MATCH (n) WHERE n.cycles != 36 RETURN n")
        second = Parser.parse_statement("MATCH (n) WHERE n.cycles <> 36 RETURN n")
        assert isinstance(first.where, Binary)
        assert isinstance(second.where, Binary)
        assert first.where.operator == Operators.NOT_EQUAL
        assert second.where.operator == Operators.NOT_EQUAL

    def test_null_tests(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.cycles IS NULL OR n.designation IS NOT NULL RETURN n"
        )
        assert isinstance(statement.where, Binary)
        assert isinstance(statement.where.left, IsNull)
        assert not statement.where.left.negated
        assert isinstance(statement.where.right, IsNull)
        assert statement.where.right.negated

    def test_string_predicates(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.designation STARTS WITH 'Qu' "
            "AND n.designation ENDS WITH 'ra' "
            "AND n.designation CONTAINS 'orr' RETURN n"
        )
        assert isinstance(statement.where, Binary)
        assert statement.where.operator == Operators.AND
        assert isinstance(statement.where.left, Binary)
        assert statement.where.left.operator == Operators.AND

    def test_property_access_chain(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN properties(n).cycles")
        expression = statement.return_items[0].expression
        assert isinstance(expression, Property)
        assert isinstance(expression.target, FunctionCall)
        assert expression.target.name == "properties"


class TestParserErrors:
    """Verify syntax errors report line, column, and a pointed message."""

    @pytest.mark.parametrize(
        ("text", "line", "column", "fragment"),
        [
            ("", 1, 1, "expected a MATCH clause"),
            ("RETURN 1", 1, 1, "expected a MATCH clause"),
            ("MATCH (n)", 1, 10, "expected a RETURN clause"),
            ("MATCH (n RETURN n", 1, 10, "expected ')'"),
            ("MATCH n RETURN n", 1, 7, "expected '('"),
            ("MATCH (n) RETURN", 1, 17, "unexpected token"),
            ("MATCH (n) WHERE RETURN n", 1, 17, "unexpected token"),
            ("MATCH (n) RETURN n AS", 1, 22, "expected an alias"),
            ("MATCH (n) RETURN n trailing", 1, 20, "unexpected token"),
            ("MATCH (n) RETURN n ORDER n", 1, 26, "expected BY"),
            ("MATCH (n)-[r RETURN n", 1, 14, "expected ']'"),
        ],
    )
    def test_syntax_error_positions(
        self,
        text: str,
        line: int,
        column: int,
        fragment: str,
    ) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement(text)
        assert fragment in caught.value.message
        assert caught.value.line == line
        assert caught.value.column == column

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("MATCH (a)-[r*1..3]->(b) RETURN b", "variable-length"),
            ("MATCH (a)-[*]->(b) RETURN b", "variable-length"),
            ("MATCH (a)-[:ALLIES_WITH*]->(b) RETURN b", "variable-length"),
            ("MATCH (a), (b) RETURN a", "multiple path patterns"),
            ("MATCH (a) MATCH (b) RETURN a", "multiple MATCH"),
            ("OPTIONAL MATCH (a) RETURN a", "OPTIONAL MATCH"),
            ("MATCH (a) OPTIONAL MATCH (b) RETURN a", "OPTIONAL MATCH"),
            ("MATCH (a) WITH a RETURN a", "WITH"),
            ("MATCH (a) UNWIND [1] AS x RETURN a", "UNWIND"),
            ("CREATE (a) RETURN a", "CREATE"),
            ("MATCH (a) CREATE (b) RETURN a", "CREATE"),
            ("MATCH (a) MERGE (b) RETURN a", "MERGE"),
            ("MATCH (a) SET a.x = 1 RETURN a", "SET"),
            ("MATCH (a) REMOVE a.x RETURN a", "REMOVE"),
            ("MATCH (a) DELETE a RETURN a", "DELETE"),
            ("MATCH (a) DETACH DELETE a RETURN a", "DETACH"),
            ("MATCH (a) RETURN CASE WHEN true THEN 1 END", "CASE"),
            ("MATCH (a) RETURN {x: 1}", "map literals"),
            ("MATCH (a) RETURN a.list[0]", "index access"),
            ("MATCH (a) CALL { MATCH (b) RETURN b } RETURN a", "subqueries"),
            ("MATCH (a) WHERE EXISTS { MATCH (b) RETURN b } RETURN a", "subqueries"),
        ],
    )
    def test_unsupported_constructs_are_semantic_errors(
        self,
        text: str,
        fragment: str,
    ) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement(text)
        assert fragment in caught.value.message
        assert caught.value.line is not None
        assert caught.value.column is not None

    def test_multiple_statements_are_rejected(self) -> None:
        with pytest.raises(QuerySemanticError) as caught:
            Parser.parse_statement("MATCH (a) RETURN a; MATCH (b) RETURN b")
        assert "multiple statements" in caught.value.message

    def test_star_outside_count_is_rejected_by_semantics(self) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH (n) RETURN *")
