# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Recursive-descent and Pratt parser for the query language."""

import typing
from collections.abc import Sequence

from pygrafito.engine.query.ast import (
    Binary,
    Clause,
    Create,
    Delete,
    Expression,
    FunctionCall,
    IsNull,
    LabelAssignment,
    LabelRemoval,
    ListLiteral,
    Literal,
    Match,
    NodePattern,
    Operators,
    Parameter,
    PathPattern,
    Property,
    PropertyAssignment,
    PropertyEntry,
    PropertyRemoval,
    RelationshipPattern,
    Remove,
    Return,
    ReturnItem,
    Set,
    SortItem,
    Star,
    Statement,
    Unary,
    Variable,
    With,
)
from pygrafito.engine.query.lexer import Lexer
from pygrafito.engine.query.tokens import Keyword, Span, Token, TokenKind
from pygrafito.model import Direction, QuerySemanticError, QuerySyntaxError


class Parser:
    """Parse tokens into one query statement.

    Parameters
    ----------
    tokens : Sequence[Token]
        Positioned tokens ending with an end-of-input token.
    source : str, optional
        Original source text, used to recover projected expression text.
    """

    COMPARISONS: typing.ClassVar[dict[str, str]] = {
        "=": Operators.EQUAL,
        "!=": Operators.NOT_EQUAL,
        "<>": Operators.NOT_EQUAL,
        "<": Operators.LESS,
        "<=": Operators.LESS_EQUAL,
        ">": Operators.GREATER,
        ">=": Operators.GREATER_EQUAL,
    }
    UNSUPPORTED_CLAUSES: typing.ClassVar[frozenset[Keyword]] = frozenset(
        {
            Keyword.UNWIND,
            Keyword.MERGE,
            Keyword.CASE,
        }
    )

    def __init__(self, tokens: Sequence[Token], source: str = "") -> None:
        self._tokens = tuple(tokens)
        self._source = source
        self._position = 0

    @classmethod
    def parse_statement(cls, text: str) -> Statement:
        """Lex and parse one complete statement.

        Parameters
        ----------
        text : str
            Query source text.

        Returns
        -------
        Statement
            Parsed statement.
        """
        return cls(Lexer.tokenize(text), text).parse()

    def parse(self) -> Statement:
        """Parse the token sequence into one statement.

        Returns
        -------
        Statement
            Parsed statement.

        Raises
        ------
        QuerySyntaxError
            If the token sequence does not form a valid statement.
        QuerySemanticError
            If the statement uses a recognized but unsupported construct.
        """
        clauses: list[Clause] = []
        first = self._current()
        while not self._at_statement_end():
            clauses.append(self._next_clause(clauses))
        self._validate_clause_shape(clauses, first)
        self._match_punctuation(";")
        if self._current().kind is not TokenKind.EOF:
            if self._current().kind is TokenKind.KEYWORD:
                self._reject_unsupported(
                    self._current(),
                    "multiple statements are not supported",
                )
            self._fail_syntax("unexpected token after the statement", self._current())
        return Statement(clauses=tuple(clauses))

    def _at_statement_end(self) -> bool:
        """Report whether the clause loop reached the end of the statement.

        Returns
        -------
        bool
            ``True`` at end of input or at a statement terminator.
        """
        current = self._current()
        return current.kind is TokenKind.EOF or (
            current.kind is TokenKind.PUNCTUATION and current.value == ";"
        )

    def _next_clause(self, parsed: Sequence[Clause]) -> Clause:
        """Parse one clause after checking its position.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed, used for order checks.

        Returns
        -------
        Clause
            Parsed clause.
        """
        current = self._current()
        self._reject_unsupported_clause(current)
        if current.is_keyword(Keyword.OPTIONAL):
            self._advance()
            if not self._current().is_keyword(Keyword.MATCH):
                self._fail_syntax("expected MATCH after OPTIONAL", self._current())
            self._guard_match_position(parsed, current)
            self._advance()
            return self._match_clause(optional=True)
        if current.is_keyword(Keyword.MATCH):
            self._guard_match_position(parsed, current)
            self._advance()
            return self._match_clause()
        if current.is_keyword(Keyword.WITH):
            self._guard_with_position(parsed, current)
            self._advance()
            return self._with_clause()
        if current.is_keyword(Keyword.CREATE):
            self._guard_write_position(parsed, current)
            self._advance()
            return Create(pattern=self._clause_pattern())
        if current.is_keyword(Keyword.SET):
            self._guard_write_position(parsed, current)
            self._advance()
            return self._set_clause()
        if current.is_keyword(Keyword.REMOVE):
            self._guard_write_position(parsed, current)
            self._advance()
            return self._remove_clause()
        if current.is_keyword(Keyword.DELETE):
            self._guard_write_position(parsed, current)
            self._advance()
            return self._delete_clause(detach=False)
        if current.is_keyword(Keyword.DETACH):
            self._guard_write_position(parsed, current)
            self._advance()
            self._expect_keyword(Keyword.DELETE, "expected DELETE after DETACH")
            return self._delete_clause(detach=True)
        if current.is_keyword(Keyword.RETURN):
            self._guard_return_position(parsed, current)
            self._advance()
            return self._return_clause()
        self._fail_syntax(f"unexpected token {current.text!r}", current)

    @staticmethod
    def _has_clause(parsed: Sequence[Clause], kinds: tuple[type[object], ...]) -> bool:
        """Report whether a clause of one of the given kinds was parsed.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed.
        kinds : tuple[type[object], ...]
            Clause classes to look for.

        Returns
        -------
        bool
            ``True`` when a clause of any given kind is present.
        """
        return any(isinstance(clause, kinds) for clause in parsed)

    def _guard_match_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a misplaced ``MATCH`` clause.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Create, Set, Remove, Delete)):
            self._fail_syntax("a MATCH clause must precede every write clause", token)
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("RETURN must be the final clause", token)

    def _guard_write_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a write clause that follows ``RETURN``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("RETURN must be the final clause", token)

    def _guard_with_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a ``WITH`` clause after a write or ``RETURN``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("RETURN must be the final clause", token)
        if self._has_clause(parsed, (Create, Set, Remove, Delete)):
            self._fail_syntax("a WITH clause must precede every write clause", token)

    def _guard_return_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a second ``RETURN`` clause.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("a statement may contain only one RETURN clause", token)

    def _validate_clause_shape(self, clauses: Sequence[Clause], first: Token) -> None:
        """Require a read statement to carry both ``MATCH`` and ``RETURN``.

        Parameters
        ----------
        clauses : Sequence[Clause]
            Parsed clauses in source order.
        first : Token
            First token of the statement, used for the missing-clause position.

        Raises
        ------
        QuerySyntaxError
            If the statement has no clause, or has no write clause and omits
            ``MATCH`` or ``RETURN``.
        """
        if not clauses:
            self._fail_syntax("expected a MATCH clause", first)
        is_write = any(isinstance(clause, (Create, Set, Remove, Delete)) for clause in clauses)
        has_match = any(isinstance(clause, Match) for clause in clauses)
        has_return = any(isinstance(clause, Return) for clause in clauses)
        if is_write:
            return
        if not has_match:
            self._fail_syntax("expected a MATCH clause", first)
        if not has_return:
            self._fail_syntax("expected a RETURN clause", self._current())

    def _require_not_after_return(self, seen_return: bool, token: Token) -> None:
        """Reject a clause that follows ``RETURN``.

        Parameters
        ----------
        seen_return : bool
            Whether a ``RETURN`` clause was already parsed.
        token : Token
            Offending clause keyword.

        Raises
        ------
        QuerySyntaxError
            If ``RETURN`` was already parsed.
        """
        if seen_return:
            self._fail_syntax("RETURN must be the final clause", token)

    def _reject_unsupported_clause(self, token: Token) -> None:
        """Reject a recognized clause that this dialect does not support.

        Parameters
        ----------
        token : Token
            Current token.

        Raises
        ------
        QuerySemanticError
            If the token starts an unsupported construct.
        """
        if token.is_keyword(Keyword.CALL):
            self._reject_unsupported(token, "subqueries are not supported")
        if token.kind is TokenKind.KEYWORD and Keyword(token.value) in self.UNSUPPORTED_CLAUSES:
            self._reject_unsupported(token, f"{token.value} is not supported")

    def _match_clause(self, *, optional: bool = False) -> Match:
        """Parse the patterns and optional filter of a ``MATCH`` clause.

        Parameters
        ----------
        optional : bool, optional
            Whether the clause is ``OPTIONAL MATCH``, by default ``False``.

        Returns
        -------
        Match
            Parsed match clause.
        """
        patterns = [self._path_pattern()]
        while self._match_punctuation(","):
            patterns.append(self._path_pattern())
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        return Match(patterns=tuple(patterns), where=where, optional=optional)

    def _clause_pattern(self) -> PathPattern:
        """Parse exactly one path pattern for a clause.

        Returns
        -------
        PathPattern
            Parsed path pattern.
        """
        pattern = self._path_pattern()
        if self._check_punctuation(","):
            self._reject_unsupported(
                self._current(),
                "multiple path patterns are not supported",
            )
        return pattern

    def _set_clause(self) -> Set:
        """Parse the assignments of a ``SET`` clause.

        Returns
        -------
        Set
            Parsed set clause.
        """
        assignments: list[PropertyAssignment] = []
        labels: list[LabelAssignment] = []
        while True:
            variable, span = self._variable_reference("SET")
            if self._match_punctuation("."):
                key = self._property_key()
                self._expect_operator("=", "expected '=' in a SET assignment")
                assignments.append(
                    PropertyAssignment(
                        variable=variable,
                        key=key,
                        value=self._expression(),
                        span=span,
                    )
                )
            elif self._check_punctuation(":"):
                labels.append(
                    LabelAssignment(
                        variable=variable,
                        labels=self._label_list("a node label"),
                        span=span,
                    )
                )
            else:
                self._fail_syntax(
                    "expected '.key = value' or ':Label' after a SET target",
                    self._current(),
                )
            if not self._match_punctuation(","):
                break
        return Set(assignments=tuple(assignments), labels=tuple(labels))

    def _remove_clause(self) -> Remove:
        """Parse the removals of a ``REMOVE`` clause.

        Returns
        -------
        Remove
            Parsed remove clause.
        """
        properties: list[PropertyRemoval] = []
        labels: list[LabelRemoval] = []
        while True:
            variable, span = self._variable_reference("REMOVE")
            if self._match_punctuation("."):
                properties.append(
                    PropertyRemoval(
                        variable=variable,
                        key=self._property_key(),
                        span=span,
                    )
                )
            elif self._check_punctuation(":"):
                labels.append(
                    LabelRemoval(
                        variable=variable,
                        labels=self._label_list("a node label"),
                        span=span,
                    )
                )
            else:
                self._fail_syntax(
                    "expected '.key' or ':Label' after a REMOVE target",
                    self._current(),
                )
            if not self._match_punctuation(","):
                break
        return Remove(properties=tuple(properties), labels=tuple(labels))

    def _delete_clause(self, *, detach: bool) -> Delete:
        """Parse the targets of a ``DELETE`` or ``DETACH DELETE`` clause.

        Parameters
        ----------
        detach : bool
            Whether the clause was written as ``DETACH DELETE``.

        Returns
        -------
        Delete
            Parsed delete clause.
        """
        variables: list[str] = []
        while True:
            name, _span = self._variable_reference("DELETE")
            variables.append(name)
            if not self._match_punctuation(","):
                break
        return Delete(variables=tuple(variables), detach=detach)

    def _with_clause(self) -> With:
        """Parse a ``WITH`` clause and its filter and pagination.

        Returns
        -------
        With
            Parsed ``WITH`` clause.
        """
        if self._check_operator("*"):
            self._reject_unsupported(self._current(), "WITH * is not supported")
        distinct = self._match_keyword(Keyword.DISTINCT)
        items = [self._return_item()]
        while self._match_punctuation(","):
            items.append(self._return_item())
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        order_by = self._order_by()
        skip: Expression | None = None
        limit: Expression | None = None
        if self._match_keyword(Keyword.SKIP):
            skip = self._expression()
        if self._match_keyword(Keyword.LIMIT):
            limit = self._expression()
        return With(
            items=tuple(items),
            distinct=distinct,
            where=where,
            order_by=order_by,
            skip=skip,
            limit=limit,
        )

    def _return_clause(self) -> Return:
        """Parse a ``RETURN`` clause and its pagination.

        Returns
        -------
        Return
            Parsed return clause.
        """
        distinct = self._match_keyword(Keyword.DISTINCT)
        items = [self._return_item()]
        while self._match_punctuation(","):
            items.append(self._return_item())
        order_by = self._order_by()
        skip: Expression | None = None
        limit: Expression | None = None
        if self._match_keyword(Keyword.SKIP):
            skip = self._expression()
        if self._match_keyword(Keyword.LIMIT):
            limit = self._expression()
        return Return(
            items=tuple(items),
            distinct=distinct,
            order_by=order_by,
            skip=skip,
            limit=limit,
        )

    def _variable_reference(self, clause: str) -> tuple[str, Span | None]:
        """Parse the variable named by a write clause.

        Parameters
        ----------
        clause : str
            Clause name used in the error message.

        Returns
        -------
        tuple[str, Span | None]
            Variable name and its source span.
        """
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax(f"expected a variable after {clause}", token)
        self._advance()
        return self._identifier_text(token), token.span

    def _label_list(self, description: str) -> tuple[str, ...]:
        """Parse one or more ``:Label`` items.

        Parameters
        ----------
        description : str
            Human-readable description used in the error message.

        Returns
        -------
        tuple[str, ...]
            Parsed labels.
        """
        labels: list[str] = []
        while self._match_punctuation(":"):
            labels.append(self._label(description))
        if not labels:
            self._fail_syntax(f"expected {description}", self._current())
        return tuple(labels)

    def _path_pattern(self) -> PathPattern:
        """Parse one path pattern.

        Returns
        -------
        PathPattern
            Parsed path pattern.
        """
        variable: str | None = None
        if self._is_identifier(self._current()) and self._peek_is_operator("="):
            variable = self._identifier_text(self._advance())
            self._advance()
        nodes = [self._node_pattern()]
        relationships: list[RelationshipPattern] = []
        while self._current().text in {"-", "<"}:
            relationships.append(self._relationship_pattern())
            nodes.append(self._node_pattern())
        return PathPattern(
            nodes=tuple(nodes),
            relationships=tuple(relationships),
            variable=variable,
        )

    def _node_pattern(self) -> NodePattern:
        """Parse one parenthesized node pattern.

        Returns
        -------
        NodePattern
            Parsed node pattern.
        """
        self._expect_punctuation("(", "expected '(' to start a node pattern")
        variable: str | None = None
        labels: list[str] = []
        properties: tuple[PropertyEntry, ...] = ()
        if self._is_identifier(self._current()):
            variable = self._identifier_text(self._advance())
        while self._match_punctuation(":"):
            labels.append(self._label("a node label"))
        if self._check_punctuation("{"):
            properties = self._property_map()
        self._expect_punctuation(")", "expected ')' to close a node pattern")
        return NodePattern(
            variable=variable,
            labels=tuple(labels),
            properties=properties,
        )

    def _relationship_pattern(self) -> RelationshipPattern:
        """Parse one relationship pattern, including its direction.

        Returns
        -------
        RelationshipPattern
            Parsed relationship pattern.
        """
        if self._match_operator("<"):
            self._expect_operator("-", "expected '-' after '<' in a relationship pattern")
            variable, types, properties, min_hops, max_hops = self._relationship_detail()
            self._expect_operator("-", "expected '-' to close an incoming relationship")
            return RelationshipPattern(
                variable=variable,
                types=types,
                direction=Direction.INCOMING,
                properties=properties,
                min_hops=min_hops,
                max_hops=max_hops,
            )
        self._expect_operator("-", "expected '-' to start a relationship pattern")
        variable, types, properties, min_hops, max_hops = self._relationship_detail()
        self._expect_operator("-", "expected '-' to close a relationship pattern")
        direction = Direction.OUTGOING if self._match_operator(">") else Direction.BOTH
        return RelationshipPattern(
            variable=variable,
            types=types,
            direction=direction,
            properties=properties,
            min_hops=min_hops,
            max_hops=max_hops,
        )

    def _relationship_detail(
        self,
    ) -> tuple[
        str | None,
        tuple[str, ...],
        tuple[PropertyEntry, ...],
        int | None,
        int | None,
    ]:
        """Parse the optional bracket contents of a relationship pattern.

        Returns
        -------
        tuple[str | None, tuple[str, ...], tuple[PropertyEntry, ...], int | None, int | None]
            Variable, accepted types, property map, and quantifier bounds.
        """
        if not self._match_punctuation("["):
            return None, (), (), None, None
        variable: str | None = None
        types: list[str] = []
        properties: tuple[PropertyEntry, ...] = ()
        if self._is_identifier(self._current()):
            variable = self._identifier_text(self._advance())
        if self._match_punctuation(":"):
            types.append(self._label("a relationship type"))
            while self._match_punctuation("|"):
                types.append(self._label("a relationship type"))
        min_hops, max_hops = self._quantifier()
        if self._check_punctuation("{"):
            properties = self._property_map()
        self._expect_punctuation("]", "expected ']' to close a relationship pattern")
        return variable, tuple(types), properties, min_hops, max_hops

    def _quantifier(self) -> tuple[int | None, int | None]:
        """Parse an optional ``*`` relationship quantifier.

        Returns
        -------
        tuple[int | None, int | None]
            Lower and upper hop bounds; both ``None`` for an ordinary
            relationship and for a bare ``*``.

        Raises
        ------
        QuerySyntaxError
            If a bound is not an integer or the range separator is malformed.
        """
        if not self._match_operator("*"):
            return None, None
        lower: int | None = None
        if self._match_operator("-"):
            lower = -self._integer_bound()
        elif self._current().kind is TokenKind.INTEGER:
            lower = self._integer_bound()
        if self._match_punctuation("."):
            self._expect_punctuation(".", "expected '..' in a variable-length pattern")
            upper: int | None = None
            if self._match_operator("-"):
                upper = -self._integer_bound()
            elif self._current().kind is TokenKind.INTEGER:
                upper = self._integer_bound()
            return (1 if lower is None else lower), upper
        if lower is None:
            return 1, None
        return lower, lower

    def _integer_bound(self) -> int:
        """Consume one integer quantifier bound.

        Returns
        -------
        int
            Bound value.

        Raises
        ------
        QuerySyntaxError
            If the current token is not an integer.
        """
        token = self._current()
        if token.kind is not TokenKind.INTEGER:
            self._fail_syntax("expected an integer bound in a variable-length pattern", token)
        self._advance()
        return int(token.value)

    def _property_map(self) -> tuple[PropertyEntry, ...]:
        """Parse a pattern property map.

        Returns
        -------
        tuple[PropertyEntry, ...]
            Constant or parameter entries in source order.
        """
        self._expect_punctuation("{", "expected '{' to start a property map")
        entries: list[PropertyEntry] = []
        if self._match_punctuation("}"):
            return ()
        while True:
            key = self._property_key()
            self._expect_punctuation(":", "expected ':' after a property key")
            entries.append(PropertyEntry(key=key, value=self._expression()))
            if not self._match_punctuation(","):
                break
        self._expect_punctuation("}", "expected '}' to close a property map")
        return tuple(entries)

    def _return_item(self) -> ReturnItem:
        """Parse one projected expression with an optional alias.

        Returns
        -------
        ReturnItem
            Parsed projection item.
        """
        start = self._position
        expression = self._expression()
        end = self._position
        alias: str | None = None
        if self._match_keyword(Keyword.AS):
            if not self._is_identifier(self._current()):
                self._fail_syntax("expected an alias after AS", self._current())
            alias = self._identifier_text(self._advance())
        return ReturnItem(
            expression=expression,
            alias=alias,
            text=self._slice(start, end),
        )

    def _order_by(self) -> tuple[SortItem, ...]:
        """Parse an optional ``ORDER BY`` clause.

        Returns
        -------
        tuple[SortItem, ...]
            Parsed sort keys.
        """
        if not self._match_keyword(Keyword.ORDER):
            return ()
        self._expect_keyword(Keyword.BY, "expected BY after ORDER")
        items = [self._sort_item()]
        while self._match_punctuation(","):
            items.append(self._sort_item())
        return tuple(items)

    def _sort_item(self) -> SortItem:
        """Parse one sort key and its direction.

        Returns
        -------
        SortItem
            Parsed sort key.
        """
        expression = self._expression()
        descending = False
        if self._match_keyword(Keyword.DESC):
            descending = True
        else:
            self._match_keyword(Keyword.ASC)
        return SortItem(expression=expression, descending=descending)

    def _expression(self) -> Expression:
        """Parse one full expression.

        Returns
        -------
        Expression
            Parsed expression.
        """
        return self._or_expression()

    def _or_expression(self) -> Expression:
        """Parse boolean ``OR`` expressions.

        Returns
        -------
        Expression
            Parsed expression.
        """
        left = self._and_expression()
        while self._match_keyword(Keyword.OR):
            left = Binary(left=left, operator=Operators.OR, right=self._and_expression())
        return left

    def _and_expression(self) -> Expression:
        """Parse boolean ``AND`` expressions.

        Returns
        -------
        Expression
            Parsed expression.
        """
        left = self._not_expression()
        while self._match_keyword(Keyword.AND):
            left = Binary(left=left, operator=Operators.AND, right=self._not_expression())
        return left

    def _not_expression(self) -> Expression:
        """Parse prefix ``NOT`` expressions.

        Returns
        -------
        Expression
            Parsed expression.
        """
        if self._match_keyword(Keyword.NOT):
            return Unary(operator=Operators.NOT, operand=self._not_expression())
        return self._comparison_expression()

    def _comparison_expression(self) -> Expression:
        """Parse comparisons, membership, null tests, and string predicates.

        Returns
        -------
        Expression
            Parsed expression.
        """
        left = self._additive_expression()
        while True:
            current = self._current()
            if current.kind is TokenKind.OPERATOR and str(current.value) in self.COMPARISONS:
                operator = self.COMPARISONS[str(current.value)]
                self._advance()
                left = Binary(
                    left=left,
                    operator=operator,
                    right=self._additive_expression(),
                )
                continue
            if self._match_keyword(Keyword.IN):
                left = Binary(
                    left=left,
                    operator=Operators.IN,
                    right=self._additive_expression(),
                )
                continue
            if self._match_keyword(Keyword.IS):
                negated = self._match_keyword(Keyword.NOT)
                self._expect_keyword(Keyword.NULL, "expected NULL after IS")
                left = IsNull(operand=left, negated=negated)
                continue
            if self._match_keyword(Keyword.STARTS):
                self._expect_keyword(Keyword.WITH, "expected WITH after STARTS")
                left = Binary(
                    left=left,
                    operator=Operators.STARTS_WITH,
                    right=self._additive_expression(),
                )
                continue
            if self._match_keyword(Keyword.ENDS):
                self._expect_keyword(Keyword.WITH, "expected WITH after ENDS")
                left = Binary(
                    left=left,
                    operator=Operators.ENDS_WITH,
                    right=self._additive_expression(),
                )
                continue
            if self._match_keyword(Keyword.CONTAINS):
                left = Binary(
                    left=left,
                    operator=Operators.CONTAINS,
                    right=self._additive_expression(),
                )
                continue
            return left

    def _additive_expression(self) -> Expression:
        """Parse addition and subtraction.

        Returns
        -------
        Expression
            Parsed expression.
        """
        left = self._multiplicative_expression()
        while True:
            if self._match_operator("+"):
                left = Binary(
                    left=left,
                    operator=Operators.ADD,
                    right=self._multiplicative_expression(),
                )
            elif self._match_operator("-"):
                left = Binary(
                    left=left,
                    operator=Operators.SUBTRACT,
                    right=self._multiplicative_expression(),
                )
            else:
                return left

    def _multiplicative_expression(self) -> Expression:
        """Parse multiplication, division, and modulo.

        Returns
        -------
        Expression
            Parsed expression.
        """
        left = self._unary_expression()
        while True:
            if self._match_operator("*"):
                left = Binary(
                    left=left,
                    operator=Operators.MULTIPLY,
                    right=self._unary_expression(),
                )
            elif self._match_operator("/"):
                left = Binary(left=left, operator=Operators.DIVIDE, right=self._unary_expression())
            elif self._match_operator("%"):
                left = Binary(left=left, operator=Operators.MODULO, right=self._unary_expression())
            else:
                return left

    def _unary_expression(self) -> Expression:
        """Parse unary plus and minus.

        Returns
        -------
        Expression
            Parsed expression.
        """
        if self._match_operator("-"):
            return Unary(operator=Operators.NEGATE, operand=self._unary_expression())
        if self._match_operator("+"):
            return Unary(operator=Operators.POSITIVE, operand=self._unary_expression())
        return self._postfix_expression()

    def _postfix_expression(self) -> Expression:
        """Parse property access after a primary expression.

        Returns
        -------
        Expression
            Parsed expression.
        """
        expression = self._primary_expression()
        while self._match_punctuation("."):
            token = self._current()
            if not self._is_identifier(token):
                self._fail_syntax("expected a property key after '.'", token)
            self._advance()
            expression = Property(
                target=expression,
                key=self._identifier_text(token),
                span=token.span,
            )
        if self._check_punctuation("["):
            self._reject_unsupported(self._current(), "index access is not supported")
        return expression

    def _primary_expression(self) -> Expression:
        """Parse a literal, variable, parameter, call, or parenthesized expression.

        Returns
        -------
        Expression
            Parsed expression.
        """
        token = self._current()
        if token.kind in {TokenKind.INTEGER, TokenKind.FLOAT, TokenKind.STRING}:
            self._advance()
            return Literal(value=token.value)
        if token.kind is TokenKind.PARAMETER:
            self._advance()
            return Parameter(name=str(token.value), span=token.span)
        if token.is_keyword(Keyword.TRUE):
            self._advance()
            return Literal(value=True)
        if token.is_keyword(Keyword.FALSE):
            self._advance()
            return Literal(value=False)
        if token.is_keyword(Keyword.NULL):
            self._advance()
            return Literal(value=None)
        if token.is_keyword(Keyword.CASE):
            self._reject_unsupported(token, "CASE expressions are not supported")
        if token.is_keyword(Keyword.CALL):
            self._reject_unsupported(token, "subqueries are not supported")
        if token.kind is TokenKind.IDENTIFIER and self._peek_is_punctuation("("):
            return self._function_call()
        if self._is_identifier(token):
            self._advance()
            name = self._identifier_text(token)
            if name.upper() == "EXISTS" and self._check_punctuation("{"):
                self._reject_unsupported(token, "subqueries are not supported")
            return Variable(name=name, span=token.span)
        if self._match_punctuation("("):
            expression = self._expression()
            self._expect_punctuation(")", "expected ')' to close the expression")
            return expression
        if self._match_punctuation("["):
            return self._list_literal()
        if token.kind is TokenKind.PUNCTUATION and token.value == "{":
            self._reject_unsupported(token, "map literals are not supported")
        self._fail_syntax(f"unexpected token {token.text!r}", token)

    def _function_call(self) -> FunctionCall:
        """Parse a function call whose name is the current identifier.

        Returns
        -------
        FunctionCall
            Parsed function call.
        """
        name_token = self._advance()
        name = self._identifier_text(name_token)
        self._expect_punctuation("(", "expected '(' after a function name")
        distinct = self._match_keyword(Keyword.DISTINCT)
        if self._match_operator("*"):
            arguments: tuple[Expression, ...] = (Star(),)
        elif self._check_punctuation(")"):
            arguments = ()
        else:
            items = [self._expression()]
            while self._match_punctuation(","):
                items.append(self._expression())
            arguments = tuple(items)
        self._expect_punctuation(")", "expected ')' to close the function call")
        return FunctionCall(
            name=name,
            arguments=arguments,
            distinct=distinct,
            span=name_token.span,
        )

    def _list_literal(self) -> ListLiteral:
        """Parse the contents of a list literal after its opening bracket.

        Returns
        -------
        ListLiteral
            Parsed list literal.
        """
        items: list[Expression] = []
        if self._match_punctuation("]"):
            return ListLiteral(items=())
        items.append(self._expression())
        while self._match_punctuation(","):
            items.append(self._expression())
        self._expect_punctuation("]", "expected ']' to close the list literal")
        return ListLiteral(items=tuple(items))

    def _label(self, description: str) -> str:
        """Parse an identifier used as a label or relationship type.

        Parameters
        ----------
        description : str
            Human-readable description used in the error message.

        Returns
        -------
        str
            Exact label or relationship type.
        """
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax(f"expected {description}", token)
        self._advance()
        return self._identifier_text(token)

    def _property_key(self) -> str:
        """Parse a property key in a property map.

        Returns
        -------
        str
            Exact property key.
        """
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax("expected a property key", token)
        self._advance()
        return self._identifier_text(token)

    def _slice(self, start: int, end: int) -> str:
        """Return source text covered by a token range.

        Parameters
        ----------
        start : int
            Inclusive token index.
        end : int
            Exclusive token index.

        Returns
        -------
        str
            Trimmed source text, or an empty string without source text.
        """
        if not self._source or end <= start:
            return ""
        first = self._tokens[start].span.offset
        last = self._tokens[end - 1].span.end
        return self._source[first:last].strip()

    def _current(self) -> Token:
        """Return the current token.

        Returns
        -------
        Token
            Current token, or the final token when past the end.
        """
        return self._tokens[min(self._position, len(self._tokens) - 1)]

    def _peek(self, distance: int) -> Token:
        """Return an upcoming token without consuming it.

        Parameters
        ----------
        distance : int
            Positive offset from the current position.

        Returns
        -------
        Token
            The upcoming token, clamped to the final token.
        """
        return self._tokens[min(self._position + distance, len(self._tokens) - 1)]

    def _previous(self) -> Token:
        """Return the most recently consumed token.

        Returns
        -------
        Token
            Previously consumed token.
        """
        return self._tokens[max(self._position - 1, 0)]

    def _advance(self) -> Token:
        """Consume and return the current token.

        Returns
        -------
        Token
            Consumed token.
        """
        token = self._current()
        if self._position < len(self._tokens) - 1:
            self._position += 1
        return token

    def _check_punctuation(self, text: str) -> bool:
        """Report whether the current token is a punctuation mark.

        Parameters
        ----------
        text : str
            Punctuation to test.

        Returns
        -------
        bool
            ``True`` when the current token is that punctuation.
        """
        token = self._current()
        return token.kind is TokenKind.PUNCTUATION and token.value == text

    def _match_punctuation(self, text: str) -> bool:
        """Consume the current punctuation mark when it matches.

        Parameters
        ----------
        text : str
            Punctuation to match.

        Returns
        -------
        bool
            ``True`` when the punctuation was consumed.
        """
        if not self._check_punctuation(text):
            return False
        self._advance()
        return True

    def _expect_punctuation(self, text: str, message: str) -> Token:
        """Consume a required punctuation mark.

        Parameters
        ----------
        text : str
            Required punctuation.
        message : str
            Error message used when it is missing.

        Returns
        -------
        Token
            Consumed punctuation token.
        """
        if not self._check_punctuation(text):
            self._fail_syntax(message, self._current())
        return self._advance()

    def _match_keyword(self, keyword: Keyword) -> bool:
        """Consume the current keyword when it matches.

        Parameters
        ----------
        keyword : Keyword
            Keyword to match.

        Returns
        -------
        bool
            ``True`` when the keyword was consumed.
        """
        if not self._current().is_keyword(keyword):
            return False
        self._advance()
        return True

    def _expect_keyword(self, keyword: Keyword, message: str) -> Token:
        """Consume a required keyword.

        Parameters
        ----------
        keyword : Keyword
            Required keyword.
        message : str
            Error message used when it is missing.

        Returns
        -------
        Token
            Consumed keyword token.
        """
        if not self._current().is_keyword(keyword):
            self._fail_syntax(message, self._current())
        return self._advance()

    def _check_operator(self, text: str) -> bool:
        """Report whether the current token is an operator.

        Parameters
        ----------
        text : str
            Operator to test.

        Returns
        -------
        bool
            ``True`` when the current token is that operator.
        """
        token = self._current()
        return token.kind is TokenKind.OPERATOR and token.value == text

    def _match_operator(self, text: str) -> bool:
        """Consume the current operator when it matches.

        Parameters
        ----------
        text : str
            Operator to match.

        Returns
        -------
        bool
            ``True`` when the operator was consumed.
        """
        if not self._check_operator(text):
            return False
        self._advance()
        return True

    def _expect_operator(self, text: str, message: str) -> Token:
        """Consume a required operator.

        Parameters
        ----------
        text : str
            Required operator.
        message : str
            Error message used when it is missing.

        Returns
        -------
        Token
            Consumed operator token.
        """
        if not self._check_operator(text):
            self._fail_syntax(message, self._current())
        return self._advance()

    def _peek_is_operator(self, text: str) -> bool:
        """Report whether the next token is an operator.

        Parameters
        ----------
        text : str
            Operator to test.

        Returns
        -------
        bool
            ``True`` when the next token is that operator.
        """
        token = self._peek(1)
        return token.kind is TokenKind.OPERATOR and token.value == text

    def _peek_is_punctuation(self, text: str) -> bool:
        """Report whether the next token is a punctuation mark.

        Parameters
        ----------
        text : str
            Punctuation to test.

        Returns
        -------
        bool
            ``True`` when the next token is that punctuation.
        """
        token = self._peek(1)
        return token.kind is TokenKind.PUNCTUATION and token.value == text

    @staticmethod
    def _is_identifier(token: Token) -> bool:
        """Report whether a token can supply an identifier.

        Parameters
        ----------
        token : Token
            Token to test.

        Returns
        -------
        bool
            ``True`` for plain or backtick-quoted identifiers.
        """
        return token.kind in {TokenKind.IDENTIFIER, TokenKind.QUOTED_IDENTIFIER}

    @staticmethod
    def _identifier_text(token: Token) -> str:
        """Return the decoded text of an identifier token.

        Parameters
        ----------
        token : Token
            Identifier token.

        Returns
        -------
        str
            Decoded identifier name.
        """
        return str(token.value)

    @staticmethod
    def _fail_syntax(message: str, token: Token) -> typing.Never:
        """Raise a positioned syntax error.

        Parameters
        ----------
        message : str
            Description of the failure.
        token : Token
            Token where the failure was detected.

        Raises
        ------
        QuerySyntaxError
            Always.
        """
        raise QuerySyntaxError(
            message,
            line=token.span.line,
            column=token.span.column,
        )

    @staticmethod
    def _reject_unsupported(token: Token, message: str) -> typing.Never:
        """Raise a positioned semantic error for an unsupported construct.

        Parameters
        ----------
        token : Token
            Token where the construct starts.
        message : str
            Description of the limitation.

        Raises
        ------
        QuerySemanticError
            Always.
        """
        raise QuerySemanticError(
            message,
            line=token.span.line,
            column=token.span.column,
        )
