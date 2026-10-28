# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for parsing query statements and expressions."""

import pytest

from pygrafito.engine.query.ast import (
    Binary,
    Case,
    CompoundStatement,
    Create,
    Delete,
    EdgeDirection,
    Finish,
    FunctionCall,
    IsNull,
    LabelOr,
    Let,
    ListAccess,
    ListComprehension,
    ListLiteral,
    ListSlice,
    Literal,
    MapLiteral,
    Match,
    MatchMode,
    Merge,
    Next,
    Operators,
    OrdinalityKind,
    Parameter,
    PathMode,
    Property,
    Remove,
    Return,
    Set,
    SetOperation,
    Star,
    Subquery,
    SubqueryKind,
    Unary,
    Unwind,
    Variable,
    With,
    Yield,
)
from pygrafito.engine.query.parser import Parser
from pygrafito.model import QuerySemanticError, QuerySyntaxError


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
        assert len(self.match(statement).patterns[0].nodes) == 1
        assert self.match(statement).patterns[0].nodes[0].labels == ("Program",)
        assert self.returned(statement).items[0].alias == "name"
        assert self.returned(statement).items[0].text == "n.designation"

    def test_two_patterns_in_one_match(self) -> None:
        statement = Parser.parse_statement("MATCH (a:Program), (b:ISO) RETURN a, b")
        clause = self.match(statement)
        assert len(clause.patterns) == 2
        assert clause.patterns[0].nodes[0].labels == ("Program",)
        assert clause.patterns[1].nodes[0].labels == ("ISO",)

    def test_three_patterns_in_one_match(self) -> None:
        statement = Parser.parse_statement("MATCH (a), (b), (c) RETURN a, b, c")
        assert len(self.match(statement).patterns) == 3

    def test_multiple_match_clauses(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program) MATCH (a)-[:ALLIES_WITH]->(b:Program) RETURN b"
        )
        clauses = [clause for clause in statement.clauses if isinstance(clause, Match)]
        assert len(clauses) == 2
        assert len(clauses[0].patterns) == 1
        assert clauses[1].patterns[0].relationships[0].types == ("ALLIES_WITH",)

    def test_optional_match_with_where(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program) OPTIONAL MATCH (a)-[r:ALLIES_WITH]->(b) "
            "WHERE b.cycles > 40 RETURN a, b"
        )
        clauses = [clause for clause in statement.clauses if isinstance(clause, Match)]
        assert len(clauses) == 2
        assert clauses[1].optional
        assert clauses[1].where is not None
        assert clauses[1].patterns[0].relationships[0].types == ("ALLIES_WITH",)

    def test_with_projection_filter_and_pagination(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program) WITH DISTINCT a.designation AS name "
            "WHERE name STARTS WITH 'Q' ORDER BY name DESC SKIP 1 LIMIT 2 RETURN name"
        )
        clause = next(clause for clause in statement.clauses if isinstance(clause, With))
        assert clause.distinct
        assert clause.where is not None
        assert clause.order_by[0].descending
        assert clause.skip is not None
        assert clause.limit is not None

    def test_with_can_be_followed_by_match(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program) WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b"
        )
        kinds = [type(clause).__name__ for clause in statement.clauses]
        assert kinds == ["Match", "With", "Match", "Return"]

    def test_quantified_relationship_forms(self) -> None:
        forms = {
            "MATCH (a)-[:ALLIES_WITH*2]->(b) RETURN b": (2, 2),
            "MATCH (a)-[:ALLIES_WITH*1..3]->(b) RETURN b": (1, 3),
            "MATCH (a)-[:ALLIES_WITH*0..2]->(b) RETURN b": (0, 2),
            "MATCH (a)-[*1..2]->(b) RETURN b": (1, 2),
        }
        for text, expected in forms.items():
            relationship = self.match(Parser.parse_statement(text)).patterns[0].relationships[0]
            assert (relationship.min_hops, relationship.max_hops) == expected

    def test_bare_quantifier_is_zero_or_more(self) -> None:
        relationship = (
            self.match(Parser.parse_statement("MATCH (a)-[*]->(b) RETURN b"))
            .patterns[0]
            .relationships[0]
        )
        assert (relationship.min_hops, relationship.max_hops) == (0, None)
        assert relationship.canonical_quantifier

    def test_canonical_quantifier_forms(self) -> None:
        forms = {
            "MATCH (a)-[:ALLIES_WITH{2}]->(b) RETURN b": (2, 2),
            "MATCH (a)-[:ALLIES_WITH{1,3}]->(b) RETURN b": (1, 3),
            "MATCH (a)-[:ALLIES_WITH{,2}]->(b) RETURN b": (0, 2),
            "MATCH (a)-[:ALLIES_WITH{0}]->(b) RETURN b": (0, 0),
        }
        for text, expected in forms.items():
            relationship = self.match(Parser.parse_statement(text)).patterns[0].relationships[0]
            assert (relationship.min_hops, relationship.max_hops) == expected
            assert relationship.canonical_quantifier

    def test_canonical_quantifier_is_marked_canonical(self) -> None:
        legacy = (
            self.match(Parser.parse_statement("MATCH (a)-[:ALLIES_WITH*1..2]->(b) RETURN b"))
            .patterns[0]
            .relationships[0]
        )
        assert not legacy.canonical_quantifier

    @pytest.mark.parametrize(
        ("text", "expected", "canonical"),
        [
            ("MATCH (a)-[:ALLIES_WITH{1,}]->(b) RETURN b", (1, None), True),
            ("MATCH (a)-[:ALLIES_WITH*1..]->(b) RETURN b", (1, None), False),
            ("MATCH (a)-[:ALLIES_WITH*]->(b) RETURN b", (0, None), True),
            ("MATCH (a)-[:ALLIES_WITH+]->(b) RETURN b", (1, None), True),
        ],
    )
    def test_open_ended_quantifier_is_accepted(
        self,
        text: str,
        expected: tuple[int, int | None],
        canonical: bool,
    ) -> None:
        relationship = self.match(Parser.parse_statement(text)).patterns[0].relationships[0]
        assert (relationship.min_hops, relationship.max_hops) == expected
        assert relationship.canonical_quantifier is canonical

    def test_malformed_quantifier_is_a_syntax_error(self) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH (a)-[:ALLIES_WITH*1.3]->(b) RETURN b")

    def test_keywords_are_case_insensitive(self) -> None:
        statement = Parser.parse_statement("match (n) where true return n")
        assert self.match(statement).where == Literal(value=True)

    def test_keyword_casing_does_not_change_identifiers(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n")
        assert self.match(statement).patterns[0].nodes[0].labels == ("Program",)

    def test_comments_are_ignored(self) -> None:
        statement = Parser.parse_statement("MATCH // line\n (n) /* block */ RETURN n // trailing")
        assert self.match(statement).patterns[0].nodes[0].variable == "n"

    def test_node_labels_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (p:Program:ISO {designation: 'Quorra', cycles: $cycles}) RETURN p"
        )
        node = self.match(statement).patterns[0].nodes[0]
        assert node.labels == ("Program", "ISO")
        assert [entry.key for entry in node.properties] == ["designation", "cycles"]
        cycles = node.properties[1].value
        assert isinstance(cycles, Parameter)
        assert cycles.name == "cycles"

    def test_anonymous_node_and_relationship(self) -> None:
        statement = Parser.parse_statement("MATCH (:Program)-[]->(:Program) RETURN 1")
        assert self.match(statement).patterns[0].nodes[0].variable is None
        assert self.match(statement).patterns[0].relationships[0].variable is None
        assert self.match(statement).patterns[0].nodes[1].variable is None

    def test_path_variable(self) -> None:
        statement = Parser.parse_statement("MATCH p = (a)-[r]->(b) RETURN p")
        assert self.match(statement).patterns[0].variable == "p"

    def test_relationship_directions(self) -> None:
        outgoing = Parser.parse_statement("MATCH (a)-->(b) RETURN b")
        incoming = Parser.parse_statement("MATCH (a)<--(b) RETURN b")
        both = Parser.parse_statement("MATCH (a)-(b) RETURN b")
        bracketed = Parser.parse_statement("MATCH (a)-[r]-(b) RETURN b")
        assert self.match(outgoing).patterns[0].relationships[0].direction is EdgeDirection.OUTGOING
        assert self.match(incoming).patterns[0].relationships[0].direction is EdgeDirection.INCOMING
        assert self.match(both).patterns[0].relationships[0].direction is EdgeDirection.ANY
        assert self.match(bracketed).patterns[0].relationships[0].direction is EdgeDirection.ANY

    def test_double_dash_is_not_an_undirected_arrow(self) -> None:
        with pytest.raises(QuerySyntaxError, match="use '-' for an undirected relationship"):
            Parser.parse_statement("MATCH (a)--(b) RETURN b")

    def test_relationship_types_and_properties(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a)-[r:ALLIES_WITH|TRUSTS {since_cycle: 2020}]->(b) RETURN r"
        )
        relationship = self.match(statement).patterns[0].relationships[0]
        assert relationship.types == ()
        assert isinstance(relationship.label_expression, LabelOr)
        assert relationship.properties[0].key == "since_cycle"
        assert relationship.direction is EdgeDirection.OUTGOING

    def test_multiple_segments(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (a:Program)-[:ALLIES_WITH]->(b)-[:TRUSTS]->(c) RETURN c"
        )
        assert len(self.match(statement).patterns[0].nodes) == 3
        assert len(self.match(statement).patterns[0].relationships) == 2

    def test_backtick_identifiers(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (`a.b`:`Grid Node`)-[`r.x`:`GRID LINK` {`a.b`: 1}]->(b) "
            "RETURN `a.b`.`a.b` AS `the value`"
        )
        node = self.match(statement).patterns[0].nodes[0]
        assert node.variable == "a.b"
        assert node.labels == ("Grid Node",)
        relationship = self.match(statement).patterns[0].relationships[0]
        assert relationship.variable == "r.x"
        assert relationship.types == ("GRID LINK",)
        assert relationship.properties[0].key == "a.b"
        assert self.returned(statement).items[0].alias == "the value"

    def test_property_map_with_list_and_negative_number(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n {tags: ['ISO', 'Program'], offset: -3}) RETURN n"
        )
        values = [entry.value for entry in self.match(statement).patterns[0].nodes[0].properties]
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


class TestUnwindAndMerge:
    """Verify the parsed shape of UNWIND, MERGE, and conditional updates."""

    def test_unwind_clause(self) -> None:
        statement = Parser.parse_statement("UNWIND [1, 2] AS value RETURN value")
        clause = statement.clauses[0]
        assert isinstance(clause, Unwind)
        assert clause.variable == "value"
        assert isinstance(clause.expression, ListLiteral)

    def test_unwind_before_match(self) -> None:
        statement = Parser.parse_statement(
            "UNWIND $rows AS row MATCH (n {designation: row.designation}) RETURN n"
        )
        assert [type(clause) for clause in statement.clauses] == [Unwind, Match, Return]

    def test_unwind_requires_as(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("UNWIND [1] value RETURN value")
        assert "AS" in caught.value.message
        assert caught.value.column is not None

    def test_unwind_after_write_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("CREATE (n) UNWIND [1] AS value RETURN value")
        assert "UNWIND" in caught.value.message

    def test_merge_clause(self) -> None:
        statement = Parser.parse_statement("MERGE (n:Program {designation: 'Tron'})")
        clause = statement.clauses[0]
        assert isinstance(clause, Merge)
        assert clause.on_create is None
        assert clause.on_match is None
        assert clause.pattern.nodes[0].labels == ("Program",)

    def test_merge_conditional_updates(self) -> None:
        statement = Parser.parse_statement(
            "MERGE (n:Program {designation: 'Tron'}) "
            "ON CREATE SET n.cycles = 40 "
            "ON MATCH SET n.cycles = n.cycles + 1"
        )
        clause = statement.clauses[0]
        assert isinstance(clause, Merge)
        assert isinstance(clause.on_create, Set)
        assert isinstance(clause.on_match, Set)
        assert clause.on_create.assignments[0].key == "cycles"

    def test_merge_after_match(self) -> None:
        statement = Parser.parse_statement("MATCH (a) MERGE (a)-[:TRUSTS]->(b:Program) RETURN b")
        assert [type(clause) for clause in statement.clauses] == [Match, Merge, Return]

    def test_merge_rejects_duplicate_on_create(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("MERGE (n) ON CREATE SET n.a = 1 ON CREATE SET n.b = 2")
        assert "ON CREATE" in caught.value.message

    def test_merge_rejects_reversed_conditional_order(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("MERGE (n) ON MATCH SET n.a = 1 ON CREATE SET n.b = 2")
        assert "precede" in caught.value.message

    def test_merge_rejects_multiple_patterns(self) -> None:
        with pytest.raises(QuerySemanticError):
            Parser.parse_statement("MERGE (a:Program), (b:Program)")


class TestParserErrors:
    """Verify syntax errors report line, column, and a pointed message."""

    @pytest.mark.parametrize(
        ("text", "line", "column", "fragment"),
        [
            ("", 1, 1, "expected a MATCH clause"),
            ("RETURN 1", 1, 1, "expected a MATCH or UNWIND clause"),
            ("MATCH (n)", 1, 10, "expected a RETURN clause"),
            ("MATCH (n RETURN n", 1, 10, "expected ')'"),
            ("MATCH n RETURN n", 1, 7, "expected '('"),
            ("MATCH (n) RETURN", 1, 17, "unexpected token"),
            ("MATCH (n) WHERE RETURN n", 1, 17, "unexpected token"),
            ("MATCH (n) RETURN n AS", 1, 22, "expected an alias"),
            ("MATCH (n) RETURN n trailing", 1, 20, "unexpected token"),
            ("MATCH (n) RETURN n ORDER n", 1, 26, "expected BY"),
            ("MATCH (n)-[r RETURN n", 1, 14, "expected ']'"),
            ("MATCH (a) RETURN a RETURN a", 1, 20, "only one RETURN clause"),
            ("MATCH (a) RETURN a CREATE (b)", 1, 20, "RETURN must be the final clause"),
            ("CREATE (a) MATCH (b) RETURN b", 1, 12, "must precede every write clause"),
            ("MATCH (a) DETACH (b)", 1, 18, "expected DELETE after DETACH"),
            ("MATCH (a) OPTIONAL (b) RETURN a", 1, 20, "expected MATCH after OPTIONAL"),
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

    def test_with_must_not_end_a_statement(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("MATCH (a) WITH a")
        assert "RETURN" in caught.value.message

    def test_with_cannot_follow_a_write_clause(self) -> None:
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement("CREATE (n:Program) WITH n RETURN n")
        assert "must precede every write clause" in caught.value.message

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("MATCH (a) CALL { MATCH (b) RETURN b } RETURN a", "subqueries"),
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

    def test_star_cannot_mix_with_other_items(self) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH (n) RETURN *, n")


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


class TestPathModes:
    """Verify explicit path-mode keywords and their placement."""

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
        if not hasattr(statement, "clauses"):
            raise AssertionError("expected a parsed statement")
        clauses = statement.clauses
        if not isinstance(clauses[0], Match):
            raise AssertionError("expected a match clause")
        return clauses[0]

    @pytest.mark.parametrize(
        ("text", "mode"),
        [
            ("MATCH WALK (a) RETURN a", PathMode.WALK),
            ("MATCH TRAIL (a) RETURN a", PathMode.TRAIL),
            ("MATCH SIMPLE (a) RETURN a", PathMode.SIMPLE),
            ("MATCH ACYCLIC (a) RETURN a", PathMode.ACYCLIC),
        ],
    )
    def test_clause_mode(self, text: str, mode: PathMode) -> None:
        """Parse a mode placed after MATCH."""
        clause = self.match(Parser.parse_statement(text))
        assert clause.mode is mode
        assert clause.patterns[0].mode is None

    def test_per_path_mode_overrides_the_clause(self) -> None:
        """Parse a mode before a comma-separated path."""
        clause = self.match(Parser.parse_statement("MATCH WALK (a), ACYCLIC (b) RETURN a"))
        assert clause.mode is PathMode.WALK
        assert clause.patterns[0].mode is None
        assert clause.patterns[1].mode is PathMode.ACYCLIC

    def test_optional_match_takes_a_mode(self) -> None:
        """Parse a mode on OPTIONAL MATCH."""
        clause = self.match(Parser.parse_statement("OPTIONAL MATCH TRAIL (a) RETURN a"))
        assert clause.optional
        assert clause.mode is PathMode.TRAIL

    def test_mode_before_a_bare_relationship(self) -> None:
        """Parse a mode with the bare anonymous relationship form."""
        clause = self.match(Parser.parse_statement("MATCH SIMPLE (a)-(b) RETURN a"))
        assert clause.mode is PathMode.SIMPLE
        assert clause.patterns[0].relationships

    def test_mode_is_rejected_on_create(self) -> None:
        """Reject a path mode where a data pattern is expected."""
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("CREATE WALK (n:Program)")


class TestMatchModes:
    """Verify the clause-level match-mode keyword and its placement."""

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
        if not hasattr(statement, "clauses"):
            raise AssertionError("expected a parsed statement")
        clauses = statement.clauses
        if not isinstance(clauses[0], Match):
            raise AssertionError("expected a match clause")
        return clauses[0]

    def test_default_is_repeatable_elements(self) -> None:
        """Default a clause without a named mode to repeatable elements."""
        clause = self.match(Parser.parse_statement("MATCH (a) RETURN a"))
        assert clause.match_mode is MatchMode.REPEATABLE_ELEMENTS

    @pytest.mark.parametrize(
        ("text", "mode"),
        [
            ("MATCH DIFFERENT EDGES (a) RETURN a", MatchMode.DIFFERENT_EDGES),
            ("MATCH REPEATABLE ELEMENTS (a) RETURN a", MatchMode.REPEATABLE_ELEMENTS),
            ("match different edges (a) return a", MatchMode.DIFFERENT_EDGES),
        ],
    )
    def test_clause_match_mode(self, text: str, mode: MatchMode) -> None:
        """Parse both spellings case-insensitively."""
        assert self.match(Parser.parse_statement(text)).match_mode is mode

    def test_match_mode_precedes_the_path_mode(self) -> None:
        """Accept a path mode after the match mode."""
        clause = self.match(Parser.parse_statement("MATCH DIFFERENT EDGES WALK (a) RETURN a"))
        assert clause.match_mode is MatchMode.DIFFERENT_EDGES
        assert clause.mode is PathMode.WALK

    def test_optional_match_takes_a_match_mode(self) -> None:
        """Accept the mode on OPTIONAL MATCH."""
        clause = self.match(
            Parser.parse_statement("OPTIONAL MATCH REPEATABLE ELEMENTS TRAIL (a) RETURN a")
        )
        assert clause.optional
        assert clause.match_mode is MatchMode.REPEATABLE_ELEMENTS
        assert clause.mode is PathMode.TRAIL

    def test_match_mode_applies_to_every_comma_pattern(self) -> None:
        """Keep per-path modes while the match mode stays clause-wide."""
        clause = self.match(
            Parser.parse_statement("MATCH DIFFERENT EDGES (a), ACYCLIC (b) RETURN a")
        )
        assert clause.match_mode is MatchMode.DIFFERENT_EDGES
        assert clause.patterns[0].mode is None
        assert clause.patterns[1].mode is PathMode.ACYCLIC

    @pytest.mark.parametrize(
        ("text", "column"),
        [
            ("MATCH DIFFERENT (a) RETURN a", 17),
            ("MATCH REPEATABLE (a) RETURN a", 18),
        ],
    )
    def test_missing_match_mode_word_reports_a_position(self, text: str, column: int) -> None:
        """Report the offending token when EDGES or ELEMENTS is missing."""
        with pytest.raises(QuerySyntaxError) as caught:
            Parser.parse_statement(text)
        assert caught.value.line == 1
        assert caught.value.column == column

    @pytest.mark.parametrize(
        "text",
        [
            "INSERT DIFFERENT EDGES (a)-[:TRUSTS]->(b)",
            "CREATE REPEATABLE ELEMENTS (n:Program)",
            "MERGE DIFFERENT EDGES (n:Program)",
        ],
    )
    def test_write_clauses_have_no_match_mode(self, text: str) -> None:
        """Reject a match mode where a data pattern is expected."""
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)

    def test_reserved_words_need_backticks_as_names(self) -> None:
        """Reject a plain match-mode word used as a variable."""
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement("MATCH (different) RETURN different")
        clause = self.match(Parser.parse_statement("MATCH (`different`) RETURN `different`"))
        assert clause.patterns[0].nodes[0].variable == "different"


class TestCompositionSyntax:
    """Verify the parsed shape of the composition clauses."""

    def test_let_assignments_are_ordered(self) -> None:
        statement = Parser.parse_statement("LET base = 36, following = base + 1 RETURN following")
        clause = statement.clauses[0]
        if not isinstance(clause, Let):
            raise AssertionError("expected a LET clause")
        assert [assignment.name for assignment in clause.assignments] == ["base", "following"]

    def test_let_can_follow_a_match(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) LET following = n.cycles + 1 RETURN following"
        )
        assert isinstance(statement.clauses[1], Let)

    def test_let_after_a_write_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="write clause"):
            Parser.parse_statement("MATCH (n:Program) SET n.cycles = 1 LET value = 1 RETURN value")

    def test_let_after_return_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="RETURN"):
            Parser.parse_statement("MATCH (n:Program) RETURN n LET value = 1")

    def test_for_ordinality(self) -> None:
        statement = Parser.parse_statement("FOR value IN [1] WITH ORDINALITY index RETURN index")
        clause = statement.clauses[0]
        if not isinstance(clause, Unwind):
            raise AssertionError("expected an UNWIND clause")
        assert clause.index == "index"
        assert clause.ordinality is OrdinalityKind.ORDINALITY

    def test_for_offset(self) -> None:
        statement = Parser.parse_statement("FOR value IN [1] WITH OFFSET index RETURN index")
        clause = statement.clauses[0]
        if not isinstance(clause, Unwind):
            raise AssertionError("expected an UNWIND clause")
        assert clause.ordinality is OrdinalityKind.OFFSET

    def test_unwind_accepts_ordinality(self) -> None:
        statement = Parser.parse_statement("UNWIND [1] AS value WITH ORDINALITY index RETURN index")
        clause = statement.clauses[0]
        if not isinstance(clause, Unwind):
            raise AssertionError("expected an UNWIND clause")
        assert clause.index == "index"

    def test_ordinality_and_offset_are_exclusive(self) -> None:
        with pytest.raises(QuerySyntaxError, match="cannot be combined"):
            Parser.parse_statement(
                "FOR value IN [1] WITH ORDINALITY index WITH OFFSET other RETURN index"
            )

    def test_group_by_is_a_return_suffix(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN n GROUP BY n")
        clause = statement.clauses[-1]
        if not isinstance(clause, Return):
            raise AssertionError("expected a RETURN clause")
        assert clause.group_by is not None
        assert len(clause.group_by) == 1

    def test_group_by_empty_key_list(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN count(*) GROUP BY ()")
        clause = statement.clauses[-1]
        if not isinstance(clause, Return):
            raise AssertionError("expected a RETURN clause")
        assert clause.group_by == ()

    def test_group_by_rejects_return_star(self) -> None:
        with pytest.raises(QuerySyntaxError, match=r"RETURN \*"):
            Parser.parse_statement("MATCH (n:Program) RETURN * GROUP BY n")

    def test_no_bindings_is_parsed(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) RETURN NO BINDINGS")
        clause = statement.clauses[-1]
        if not isinstance(clause, Return):
            raise AssertionError("expected a RETURN clause")
        assert clause.no_bindings is True
        assert clause.items == ()

    def test_no_bindings_rejects_modifiers(self) -> None:
        with pytest.raises(QuerySyntaxError, match="modifiers"):
            Parser.parse_statement("MATCH (n:Program) RETURN NO BINDINGS LIMIT 1")

    def test_finish_is_parsed(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) FINISH")
        assert isinstance(statement.clauses[-1], Finish)

    def test_finish_alone_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="read or write clause"):
            Parser.parse_statement("FINISH")

    def test_next_and_yield_are_parsed(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) RETURN n AS element NEXT YIELD element RETURN element"
        )
        assert [type(clause).__name__ for clause in statement.clauses] == [
            "Match",
            "Return",
            "Next",
            "Yield",
            "Return",
        ]
        assert isinstance(statement.clauses[2], Next)
        assert isinstance(statement.clauses[3], Yield)

    def test_next_can_precede_finish(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) NEXT FINISH")
        assert [type(clause).__name__ for clause in statement.clauses] == [
            "Match",
            "Next",
            "Finish",
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "NEXT MATCH (n:Program) RETURN n",
            "MATCH (n:Program) RETURN n NEXT",
            "MATCH (n:Program) RETURN n NEXT NEXT RETURN n",
            "MATCH (n:Program) NEXT RETURN n",
            "MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m",
        ],
    )
    def test_next_placement_is_rejected(self, text: str) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(text)

    def test_yield_outside_next_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="YIELD must follow NEXT"):
            Parser.parse_statement("MATCH (n:Program) YIELD n RETURN n")

    def test_finish_can_close_a_write_segment(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) DETACH DELETE n FINISH")
        assert isinstance(statement.clauses[-1], Finish)

    def test_finish_rejects_a_following_return(self) -> None:
        with pytest.raises(QuerySyntaxError, match="FINISH"):
            Parser.parse_statement("MATCH (n:Program) FINISH RETURN n")

    def test_finish_rejects_a_following_next(self) -> None:
        with pytest.raises(QuerySyntaxError, match="FINISH"):
            Parser.parse_statement("MATCH (n:Program) FINISH NEXT RETURN n")


class TestExpressionSurfaceParsing:
    """Verify parsing of the expression surface added for 1.0."""

    @staticmethod
    def expression(text: str) -> object:
        """Return the first projected expression.

        Parameters
        ----------
        text : str
            Expression source.

        Returns
        -------
        object
            Parsed expression node.
        """
        statement = Parser.parse_statement(f"MATCH (n:Program) RETURN {text} AS value")
        clause = statement.clauses[-1]
        assert isinstance(clause, Return)
        return clause.items[0].expression

    def test_simple_case(self) -> None:
        expression = self.expression("CASE n.cycles WHEN 36 THEN 'old' ELSE 'new' END")
        assert isinstance(expression, Case)
        assert isinstance(expression.operand, Property)
        assert expression.operand.key == "cycles"
        assert len(expression.branches) == 1
        assert expression.default is not None

    def test_searched_case(self) -> None:
        expression = self.expression("CASE WHEN n.cycles > 36 THEN 'old' END")
        assert isinstance(expression, Case)
        assert expression.operand is None
        assert expression.default is None

    def test_map_literal_rejects_duplicate_keys(self) -> None:
        with pytest.raises(QuerySyntaxError, match="duplicate map key"):
            self.expression("{designation: 'Tron', designation: 'Clu'}")

    def test_map_literal(self) -> None:
        expression = self.expression("{designation: n.designation, cycles: 36}")
        assert isinstance(expression, MapLiteral)
        assert [entry.key for entry in expression.entries] == ["designation", "cycles"]

    def test_list_access_and_slice(self) -> None:
        access = self.expression("n.tags[0]")
        slice_ = self.expression("n.tags[1:3]")
        assert isinstance(access, ListAccess)
        assert isinstance(slice_, ListSlice)
        assert slice_.start == Literal(value=1)
        assert slice_.end == Literal(value=3)

    def test_list_comprehension(self) -> None:
        expression = self.expression("[x IN n.tags WHERE x STARTS WITH 'ISO' | x]")
        assert isinstance(expression, ListComprehension)
        assert expression.variable == "x"
        assert expression.where is not None
        assert expression.projection is not None

    def test_string_concatenation(self) -> None:
        expression = self.expression("'Tron' || ' ' || 'Clu'")
        assert isinstance(expression, Binary)
        assert expression.operator == Operators.CONCAT

    def test_star_projection(self) -> None:
        statement = Parser.parse_statement("MATCH (n:Program) WITH * RETURN n")
        clause = statement.clauses[0]
        assert isinstance(clause, Match)
        with_clause = statement.clauses[1]
        assert isinstance(with_clause, With)
        assert with_clause.star

    def test_with_star_cannot_mix_items(self) -> None:
        with pytest.raises(QuerySyntaxError, match="WITH \\* cannot be combined"):
            Parser.parse_statement("MATCH (n:Program) WITH *, n.cycles AS cycles RETURN n")

    def test_exists_and_count_subqueries(self) -> None:
        exists = self.expression("EXISTS { MATCH (n)-[:TRUSTS]->(m) }")
        count = self.expression("COUNT { MATCH (n)-[:TRUSTS]->(m) }")
        assert isinstance(exists, Subquery)
        assert exists.kind is SubqueryKind.EXISTS
        assert isinstance(count, Subquery)
        assert count.kind is SubqueryKind.COUNT

    def test_subquery_rejects_result_clause(self) -> None:
        with pytest.raises(QuerySemanticError, match="result clause"):
            self.expression("EXISTS { MATCH (n) RETURN n }")

    def test_compound_query(self) -> None:
        statement = Parser.parse_statement(
            "MATCH (n:Program) RETURN n.designation AS name "
            "UNION ALL MATCH (m:User) RETURN m.designation AS name"
        )
        assert isinstance(statement, CompoundStatement)
        assert len(statement.terms) == 2
        assert statement.operators == (SetOperation.UNION_ALL,)

    def test_operand_ordering_is_rejected(self) -> None:
        with pytest.raises(QuerySyntaxError, match="set operand cannot carry"):
            Parser.parse_statement(
                "MATCH (n:Program) RETURN n ORDER BY n UNION MATCH (m:Program) RETURN m"
            )

    def test_set_quantifiers(self) -> None:
        statement = Parser.parse_statement(
            "UNWIND [1] AS x RETURN x AS n "
            "UNION ALL UNWIND [1] AS x RETURN x AS n "
            "INTERSECT ALL UNWIND [1] AS x RETURN x AS n "
            "EXCEPT ALL UNWIND [1] AS x RETURN x AS n"
        )
        assert isinstance(statement, CompoundStatement)
        assert statement.operators == (
            SetOperation.UNION_ALL,
            SetOperation.INTERSECT_ALL,
            SetOperation.EXCEPT_ALL,
        )

    def test_explicit_distinct_is_the_bare_operator(self) -> None:
        statement = Parser.parse_statement(
            "UNWIND [1] AS x RETURN x AS n "
            "UNION DISTINCT UNWIND [1] AS x RETURN x AS n "
            "INTERSECT DISTINCT UNWIND [1] AS x RETURN x AS n "
            "EXCEPT DISTINCT UNWIND [1] AS x RETURN x AS n"
        )
        assert isinstance(statement, CompoundStatement)
        assert statement.operators == (
            SetOperation.UNION,
            SetOperation.INTERSECT,
            SetOperation.EXCEPT,
        )

    def test_set_operator_takes_one_quantifier(self) -> None:
        with pytest.raises(QuerySyntaxError):
            Parser.parse_statement(
                "UNWIND [1] AS x RETURN x AS n INTERSECT ALL DISTINCT UNWIND [1] AS x RETURN x AS n"
            )
