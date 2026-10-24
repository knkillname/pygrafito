# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for parsing query statements and expressions."""

import pytest

from pygrafito.engine.query.ast import (
    Binary,
    Create,
    Delete,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    Match,
    Operators,
    Parameter,
    Property,
    Remove,
    Return,
    Set,
    Star,
    Unary,
    Variable,
)
from pygrafito.engine.query.parser import Parser
from pygrafito.model import Direction, QuerySemanticError, QuerySyntaxError


class TestAcceptedSyntax:
    """Verify accepted statements and their parsed shape."""

    @staticmethod
    def match(statement: object) -> Match:
        """Return the MATCH clause of a parsed statement.

        Parameters
        ----------
        statement : object
            Parsed statement.

        Returns
        -------
        Match
            First match clause.
        """
        return next(
            clause
            for clause in statement.clauses  # type: ignore[attr-defined]
            if isinstance(clause, Match)
        )

    @staticmethod
    def returned(statement: object) -> Return:
        """Return the RETURN clause of a parsed statement.

        Parameters
        ----------
        statement : object
            Parsed statement.

        Returns
        -------
        Return
            Final return clause.
        """
        return next(
            clause
            for clause in statement.clauses  # type: ignore[attr-defined]
            if isinstance(clause, Return)
        )

    def test_minimal_query(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n.designation AS name")
        assert len(self.match(statement).pattern.nodes) == 1
        assert self.match(statement).pattern.nodes[0].labels == ("Program",)
        assert self.returned(statement).items[0].alias == "name"
        assert self.returned(statement).items[0].text == "n.designation"

    def test_keywords_are_case_insensitive(self) -> None:
        statement = Parser.parse_statement("match (n) where true return n")
        assert self.match(statement).where == Literal(value=True)

    def test_keyword_casing_does_not_change_identifiers(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n")
        assert self.match(statement).pattern.nodes[0].labels == ("Program",)

    def test_comments_are_ignored(self) -> None:
        statement = Parser.parse_statement("MATCH // line\n (n) /* block */ RETURN n // trailing")
        assert self.match(statement).pattern.nodes[0].variable == "n"

    def test_node_labels_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (p:Program:ISO {designation: 'Quorra', cycles: $cycles}) RETURN p"
        )
        node = self.match(statement).pattern.nodes[0]
        assert node.labels == ("Program", "ISO")
        assert [entry.key for entry in node.properties] == ["designation", "cycles"]
        cycles = node.properties[1].value
        assert isinstance(cycles, Parameter)
        assert cycles.name == "cycles"

    def test_anonymous_node_and_relationship(self) -> None:
        statement = Parser.parse_statement("MATCH (:Program)-[]->(:Program) RETURN 1")
        assert self.match(statement).pattern.nodes[0].variable is None
        assert self.match(statement).pattern.relationships[0].variable is None
        assert self.match(statement).pattern.nodes[1].variable is None

    def test_path_variable(self) -> None:
        statement = Parser.parse_statement("MATCH p = (a)-[r]->(b) RETURN p")
        assert self.match(statement).pattern.variable == "p"

    def test_relationship_directions(self) -> None:
        outgoing = Parser.parse_statement("MATCH (a)-->(b) RETURN b")
        incoming = Parser.parse_statement("MATCH (a)<--(b) RETURN b")
        both = Parser.parse_statement("MATCH (a)--(b) RETURN b")
        bracketed = Parser.parse_statement("MATCH (a)-[r]-(b) RETURN b")
        assert self.match(outgoing).pattern.relationships[0].direction is Direction.OUTGOING
        assert self.match(incoming).pattern.relationships[0].direction is Direction.INCOMING
        assert self.match(both).pattern.relationships[0].direction is Direction.BOTH
        assert self.match(bracketed).pattern.relationships[0].direction is Direction.BOTH

    def test_relationship_types_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a)-[r:ALLIES_WITH|TRUSTS {since_cycle: 2020}]->(b) RETURN r"
        )
        relationship = self.match(statement).pattern.relationships[0]
        assert relationship.types == ("ALLIES_WITH", "TRUSTS")
        assert relationship.properties[0].key == "since_cycle"
        assert relationship.direction is Direction.OUTGOING

    def test_multiple_segments(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program)-[:ALLIES_WITH]->(b)-[:TRUSTS]->(c) RETURN c"
        )
        assert len(self.match(statement).pattern.nodes) == 3
        assert len(self.match(statement).pattern.relationships) == 2

    def test_backtick_identifiers(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (`a.b`:`Grid Node`)-[`r.x`:`GRID LINK` {`a.b`: 1}]->(b) "
            "RETURN `a.b`.`a.b` AS `the value`"
        )
        node = self.match(statement).pattern.nodes[0]
        assert node.variable == "a.b"
        assert node.labels == ("Grid Node",)
        relationship = self.match(statement).pattern.relationships[0]
        assert relationship.variable == "r.x"
        assert relationship.types == ("GRID LINK",)
        assert relationship.properties[0].key == "a.b"
        assert self.returned(statement).items[0].alias == "the value"

    def test_property_map_with_list_and_negative_number(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n {tags: ['ISO', 'Program'], offset: -3}) RETURN n"
        )
        values = [entry.value for entry in self.match(statement).pattern.nodes[0].properties]
        assert isinstance(values[0], ListLiteral)
        assert isinstance(values[1], Unary)

    def test_where_distinct_order_skip_limit_and_semicolon(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) WHERE n.cycles > 1 "
            "RETURN DISTINCT n.designation AS name, n.cycles "
            "ORDER BY n.cycles DESC, name ASC SKIP 2 LIMIT 5;"
        )
        assert isinstance(self.match(statement).where, Binary)
        assert self.returned(statement).distinct
        assert self.returned(statement).order_by[0].descending
        second_sort = self.returned(statement).order_by[1].expression
        assert isinstance(second_sort, Variable)
        assert second_sort.name == "name"
        assert self.returned(statement).skip == Literal(value=2)
        assert self.returned(statement).limit == Literal(value=5)

    def test_parameterized_pagination(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN n SKIP $skip LIMIT $limit")
        skip = self.returned(statement).skip
        limit = self.returned(statement).limit
        assert isinstance(skip, Parameter)
        assert skip.name == "skip"
        assert isinstance(limit, Parameter)
        assert limit.name == "limit"

    def test_function_calls(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) RETURN count(*), count(DISTINCT n.designation), labels(n)"
        )
        first, second, third = self.returned(statement).items
        assert isinstance(first.expression, FunctionCall)
        assert isinstance(first.expression.arguments[0], Star)
        assert isinstance(second.expression, FunctionCall)
        assert second.expression.distinct
        assert isinstance(third.expression, FunctionCall)
        assert third.expression.name == "labels"

    def test_numeric_and_boolean_literals(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN 36, 36.5, 'text', true, false, null")
        expressions = [item.expression for item in self.returned(statement).items]
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
        expression = self.returned(statement).items[0].expression
        assert isinstance(expression, ListLiteral)
        assert len(expression.items) == 3

    def test_operator_precedence(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN n.cycles + n.cycles * 2")
        expression = self.returned(statement).items[0].expression
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.ADD
        assert isinstance(expression.right, Binary)
        assert expression.right.operator == Operators.MULTIPLY

    def test_boolean_precedence(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE NOT n.active AND n.visible OR n.pinned RETURN n"
        )
        expression = self.match(statement).where
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.OR
        assert isinstance(expression.left, Binary)
        assert expression.left.operator == Operators.AND
        assert isinstance(expression.left.left, Unary)

    def test_parentheses_change_grouping(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN (n.cycles + n.cycles) * n.cycles")
        expression = self.returned(statement).items[0].expression
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.MULTIPLY
        assert isinstance(expression.left, Binary)

    def test_unary_minus_and_positive(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN -1, +2")
        assert isinstance(self.returned(statement).items[0].expression, Unary)
        assert isinstance(self.returned(statement).items[1].expression, Unary)

    def test_comparisons_and_membership(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.cycles >= 36 AND n.designation IN ['Quorra', 'Tron'] RETURN n"
        )
        assert self.match(statement).where is not None
        assert isinstance(self.match(statement).where, Binary)

    def test_not_equal_spellings_are_normalized(self) -> None:
        first = Parser.parse_statement("MATCH (n) WHERE n.cycles != 36 RETURN n")
        second = Parser.parse_statement("MATCH (n) WHERE n.cycles <> 36 RETURN n")
        first_where = self.match(first).where
        second_where = self.match(second).where
        assert isinstance(first_where, Binary)
        assert isinstance(second_where, Binary)
        assert first_where.operator == Operators.NOT_EQUAL
        assert second_where.operator == Operators.NOT_EQUAL

    def test_null_tests(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.cycles IS NULL OR n.designation IS NOT NULL RETURN n"
        )
        assert isinstance(self.match(statement).where, Binary)
        where = self.match(statement).where
        assert isinstance(where, Binary)
        assert isinstance(where.left, IsNull)
        assert not where.left.negated
        assert isinstance(where.right, IsNull)
        assert where.right.negated

    def test_string_predicates(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n) WHERE n.designation STARTS WITH 'Qu' "
            "AND n.designation ENDS WITH 'ra' "
            "AND n.designation CONTAINS 'orr' RETURN n"
        )
        where = self.match(statement).where
        assert isinstance(where, Binary)
        assert where.operator == Operators.AND
        assert isinstance(where.left, Binary)
        assert where.left.operator == Operators.AND

    def test_property_access_chain(self) -> None:
        statement = Parser.parse_statement("MATCH (n) RETURN properties(n).cycles")
        expression = self.returned(statement).items[0].expression
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
            ("MATCH (a) MATCH (b) RETURN a", 1, 11, "only one MATCH clause"),
            ("MATCH (a) RETURN a RETURN a", 1, 20, "only one RETURN clause"),
            ("MATCH (a) RETURN a CREATE (b)", 1, 20, "RETURN must be the final clause"),
            ("CREATE (a) MATCH (b) RETURN b", 1, 12, "must precede every write clause"),
            ("MATCH (a) DETACH (b)", 1, 18, "expected DELETE after DETACH"),
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
            ("OPTIONAL MATCH (a) RETURN a", "OPTIONAL MATCH"),
            ("MATCH (a) OPTIONAL MATCH (b) RETURN a", "OPTIONAL MATCH"),
            ("MATCH (a) WITH a RETURN a", "WITH"),
            ("MATCH (a) UNWIND [1] AS x RETURN a", "UNWIND"),
            ("MATCH (a) MERGE (b) RETURN a", "MERGE"),
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


class TestWriteClauses:
    """Verify the parsed shape of write clauses and their order."""

    def test_write_only_statement(self) -> None:
        statement = Parser.parse_statement("CREATE (n:Program {designation: 'Quorra'})")
        assert len(statement.clauses) == 1
        clause = statement.clauses[0]
        assert isinstance(clause, Create)
        assert clause.pattern.nodes[0].labels == ("Program",)

    def test_match_set_without_return(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) SET n.cycles = 1")
        assert [type(clause) for clause in statement.clauses] == [Match, Set]
        set_clause = statement.clauses[1]
        assert isinstance(set_clause, Set)
        assert set_clause.assignments[0].variable == "n"
        assert set_clause.assignments[0].key == "cycles"

    def test_create_from_match(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a)-[:ALLIES_WITH]->(b) CREATE (a)-[r:TRUSTS]->(b)"
        )
        assert [type(clause) for clause in statement.clauses] == [Match, Create]
        created = statement.clauses[1]
        assert isinstance(created, Create)
        assert created.pattern.relationships[0].types == ("TRUSTS",)

    def test_set_labels_and_expressions(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) SET n.cycles = n.cycles + 1, n:SystemMonitor"
        )
        clause = statement.clauses[1]
        assert isinstance(clause, Set)
        assert isinstance(clause.assignments[0].value, Binary)
        assert clause.labels[0].labels == ("SystemMonitor",)

    def test_remove_properties_and_labels(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) REMOVE n.cycles, n:ISO:Program")
        clause = statement.clauses[1]
        assert isinstance(clause, Remove)
        assert clause.properties[0].key == "cycles"
        assert clause.labels[0].labels == ("ISO", "Program")

    def test_delete_targets(self) -> None:
        statement = Parser.parse_statement("MATCH (a)-[r]->(b) DELETE b, r")
        clause = statement.clauses[1]
        assert isinstance(clause, Delete)
        assert clause.variables == ("b", "r")
        assert not clause.detach

    def test_detach_delete(self) -> None:
        statement = Parser.parse_statement("MATCH (a) DETACH DELETE a")
        clause = statement.clauses[1]
        assert isinstance(clause, Delete)
        assert clause.variables == ("a",)
        assert clause.detach

    def test_write_then_return(self) -> None:
        statement = Parser.parse_statement("CREATE (n:Program) RETURN n.designation AS name")
        assert [type(clause) for clause in statement.clauses] == [Create, Return]
