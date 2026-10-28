# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Recursive-descent and Pratt parser for the query language."""

import dataclasses
import typing
from collections.abc import Sequence

from pygrafito.engine.query.ast import (
    Binary,
    Case,
    CaseBranch,
    Clause,
    CompoundStatement,
    Create,
    Delete,
    EdgeDirection,
    Expression,
    Filter,
    Finish,
    FunctionCall,
    GroupedPathTerm,
    HopRange,
    IsNull,
    LabelAnd,
    LabelAssignment,
    LabelExpression,
    LabelName,
    LabelNot,
    LabelOr,
    LabelRemoval,
    LabelWildcard,
    Let,
    LetAssignment,
    ListAccess,
    ListComprehension,
    ListLiteral,
    ListSlice,
    Literal,
    MapEntry,
    MapLiteral,
    Match,
    MatchMode,
    Merge,
    Next,
    NodePattern,
    Operators,
    OrdinalityKind,
    Parameter,
    PathMode,
    PathPattern,
    PathSearch,
    PathSearchKind,
    Property,
    PropertyAssignment,
    PropertyEntry,
    PropertyRemoval,
    RelationshipPattern,
    Remove,
    Return,
    ReturnItem,
    Set,
    SetOperation,
    SimplePathTerm,
    SortItem,
    Star,
    Statement,
    Subquery,
    SubqueryKind,
    Unary,
    Unwind,
    Variable,
    With,
    Yield,
    YieldItem,
)
from pygrafito.engine.query.labels import LabelExpressions
from pygrafito.engine.query.lexer import Lexer
from pygrafito.engine.query.tokens import Keyword, Span, Token, TokenKind
from pygrafito.model import QuerySemanticError, QuerySyntaxError


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
    UNSUPPORTED_CLAUSES: typing.ClassVar[frozenset[Keyword]] = frozenset()

    def __init__(self, tokens: Sequence[Token], source: str = "") -> None:
        self._tokens = tuple(tokens)
        self._source = source
        self._position = 0
        self._previous_segment_has_return = False
        self._segment_has_input = False

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
            Parsed linear or compound statement.
        """
        return cls(Lexer.tokenize(text), text).parse()

    def parse(self) -> Statement:
        """Parse the token sequence into one statement.

        Returns
        -------
        Statement
            Parsed linear or compound statement.

        Raises
        ------
        QuerySyntaxError
            If the token sequence does not form a valid statement.
        QuerySemanticError
            If the statement uses a recognized but unsupported construct.
        """
        first = self._parse_linear_statement()
        if not self._at_set_operator():
            self._finish_statement()
            return first
        terms = [first]
        operators: list[SetOperation] = []
        while self._at_set_operator():
            operators.append(self._set_operator())
            terms.append(self._parse_linear_statement())
        order_by: tuple[SortItem, ...] = ()
        skip: Expression | None = None
        limit: Expression | None = None
        stripped: list[Statement] = []
        for index, term in enumerate(terms):
            final = self._final_return(term)
            has_page = final is not None and (
                bool(final.order_by) or final.skip is not None or final.limit is not None
            )
            if index < len(terms) - 1 and has_page:
                self._fail_syntax(
                    "a set operand cannot carry ORDER BY, OFFSET, or LIMIT",
                    self._current(),
                )
            if index == len(terms) - 1 and final is not None:
                order_by = final.order_by
                skip = final.skip
                limit = final.limit
                clauses = list(term.clauses)
                clauses[-1] = dataclasses.replace(
                    final,
                    order_by=(),
                    skip=None,
                    limit=None,
                )
                stripped.append(Statement(clauses=tuple(clauses)))
            else:
                stripped.append(term)
        self._finish_statement()
        return CompoundStatement(
            clauses=(),
            terms=tuple(stripped),
            operators=tuple(operators),
            order_by=order_by,
            skip=skip,
            limit=limit,
        )

    def _parse_linear_statement(self) -> Statement:
        """Parse one linear statement term.

        Returns
        -------
        Statement
            Parsed linear term.

        Raises
        ------
        QuerySyntaxError
            If the term is malformed.
        """
        clauses: list[Clause] = []
        first = self._current()
        segment_start = 0
        self._previous_segment_has_return = False
        self._segment_has_input = False
        while not self._at_linear_end():
            if self._current().is_keyword(Keyword.NEXT):
                self._parse_next(clauses, segment_start)
                self._advance()
                clauses.append(Next())
                segment_start = len(clauses)
                self._segment_has_input = True
                if self._match_keyword(Keyword.YIELD):
                    if not self._previous_segment_has_return:
                        self._fail_syntax(
                            "YIELD requires a preceding RETURN",
                            self._tokens[self._position - 1],
                        )
                    clauses.append(self._yield_clause())
                continue
            clauses.append(self._next_clause(clauses[segment_start:]))
        self._validate_clause_shape(clauses, first)
        return Statement(clauses=tuple(clauses))

    def _finish_statement(self) -> None:
        """Consume an optional terminator and reject trailing statements.

        Raises
        ------
        QuerySyntaxError
            If more than one statement is present.
        QuerySemanticError
            If a keyword starts another statement.
        """
        self._match_punctuation(";")
        if self._current().kind is TokenKind.EOF:
            return
        if self._current().kind is TokenKind.KEYWORD:
            self._reject_unsupported(
                self._current(),
                "multiple statements are not supported",
            )
        self._fail_syntax("unexpected token after the statement", self._current())

    @staticmethod
    def _final_return(statement: Statement) -> Return | None:
        """Return the final clause when it is a ``RETURN``.

        Parameters
        ----------
        statement : Statement
            Linear term to inspect.

        Returns
        -------
        Return | None
            Final return clause, or ``None``.
        """
        if statement.clauses and isinstance(statement.clauses[-1], Return):
            return statement.clauses[-1]
        return None

    def _at_linear_end(self) -> bool:
        """Report whether a linear statement term has ended.

        Returns
        -------
        bool
            ``True`` at the end of input, a terminator, or a set operator.
        """
        current = self._current()
        return (
            current.kind is TokenKind.EOF
            or (current.kind is TokenKind.PUNCTUATION and current.value == ";")
            or self._at_set_operator()
        )

    def _at_set_operator(self) -> bool:
        """Report whether the current token starts a set operator.

        Returns
        -------
        bool
            ``True`` for UNION, INTERSECT, or EXCEPT.
        """
        return (
            self._current().is_keyword(Keyword.UNION)
            or self._current().is_keyword(Keyword.INTERSECT)
            or self._current().is_keyword(Keyword.EXCEPT)
        )

    def _set_operator(self) -> SetOperation:
        """Parse one set operator.

        Returns
        -------
        SetOperation
            Parsed set operator.

        Raises
        ------
        QuerySyntaxError
            If the token is not a set operator.

        Notes
        -----
        ``ALL`` selects multiset semantics. ``DISTINCT`` is the explicit spelling
        of the bare operator's set semantics and produces the same enum member.
        """
        if self._match_keyword(Keyword.UNION):
            if self._match_keyword(Keyword.ALL):
                return SetOperation.UNION_ALL
            self._match_keyword(Keyword.DISTINCT)
            return SetOperation.UNION
        if self._match_keyword(Keyword.INTERSECT):
            if self._match_keyword(Keyword.ALL):
                return SetOperation.INTERSECT_ALL
            self._match_keyword(Keyword.DISTINCT)
            return SetOperation.INTERSECT
        if self._match_keyword(Keyword.EXCEPT):
            if self._match_keyword(Keyword.ALL):
                return SetOperation.EXCEPT_ALL
            self._match_keyword(Keyword.DISTINCT)
            return SetOperation.EXCEPT
        self._fail_syntax("expected a set operator", self._current())

    def _parse_next(self, clauses: Sequence[Clause], segment_start: int) -> None:
        """Validate the segment before ``NEXT`` and record its result shape.

        Parameters
        ----------
        clauses : Sequence[Clause]
            Clauses parsed before the separator.
        segment_start : int
            Index of the first clause in the current segment.

        Raises
        ------
        QuerySyntaxError
            If ``NEXT`` is misplaced or the segment cannot pass bindings.
        """
        token = self._current()
        segment = clauses[segment_start:]
        if not segment:
            self._fail_syntax("NEXT must follow a segment", token)
        last = segment[-1]
        if isinstance(last, Finish):
            self._fail_syntax("NEXT cannot follow FINISH", token)
        if isinstance(last, Return):
            if last.no_bindings:
                self._fail_syntax("RETURN NO BINDINGS must be the final clause", token)
            self._previous_segment_has_return = True
            return
        if any(isinstance(clause, (Create, Merge, Set, Remove, Delete)) for clause in segment):
            self._previous_segment_has_return = False
            return
        if self._peek_is_keyword(Keyword.FINISH):
            self._previous_segment_has_return = False
            return
        self._fail_syntax(
            "a read segment must end with RETURN or FINISH before NEXT",
            token,
        )

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
        if self._has_clause(parsed, (Finish,)):
            self._fail_syntax("FINISH must be the final clause", current)
        if current.is_keyword(Keyword.YIELD):
            self._fail_syntax("YIELD must follow NEXT", current)
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
        if current.is_keyword(Keyword.UNWIND):
            self._guard_unwind_position(parsed, current)
            self._advance()
            return self._unwind_clause()
        if current.is_keyword(Keyword.FOR):
            self._guard_unwind_position(parsed, current)
            self._advance()
            return self._for_clause()
        if current.is_keyword(Keyword.FILTER):
            self._guard_filter_position(parsed, current)
            self._advance()
            return self._filter_clause()
        if current.is_keyword(Keyword.INSERT):
            self._guard_write_position(parsed, current)
            self._advance()
            self._reject_catalog_graph()
            return Create(pattern=self._clause_pattern())
        if current.is_keyword(Keyword.CREATE):
            self._guard_write_position(parsed, current)
            self._advance()
            self._reject_catalog_graph()
            return Create(pattern=self._clause_pattern())
        if current.is_keyword(Keyword.MERGE):
            self._guard_write_position(parsed, current)
            self._advance()
            return self._merge_clause()
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
        if current.is_keyword(Keyword.NODETACH):
            self._guard_write_position(parsed, current)
            self._advance()
            self._expect_keyword(Keyword.DELETE, "expected DELETE after NODETACH")
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
        if current.is_keyword(Keyword.LET):
            self._guard_let_position(parsed, current)
            self._advance()
            return self._let_clause()
        if current.is_keyword(Keyword.FINISH):
            self._guard_finish_position(parsed, current)
            self._advance()
            return Finish()
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
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Create, Merge, Set, Remove, Delete)):
            self._fail_syntax("a MATCH clause must precede every write clause", token)
        self._reject_after_result(parsed, token)

    def _guard_write_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a write clause that follows ``RETURN`` or ``FINISH``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)

    def _guard_with_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a ``WITH`` clause after a write, ``RETURN``, or ``FINISH``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)
        if self._has_clause(parsed, (Create, Merge, Set, Remove, Delete)):
            self._fail_syntax("a WITH clause must precede every write clause", token)

    def _guard_unwind_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject an ``UNWIND`` clause after a write, ``RETURN``, or ``FINISH``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)
        if self._has_clause(parsed, (Create, Merge, Set, Remove, Delete)):
            self._fail_syntax("an UNWIND clause must precede every write clause", token)

    def _guard_filter_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a ``FILTER`` clause without a preceding read stage.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)
        if self._has_clause(parsed, (Create, Merge, Set, Remove, Delete)):
            self._fail_syntax("a FILTER clause must precede every write clause", token)
        if not self._has_clause(parsed, (Match, Unwind, With, Filter, Let)) and not (
            self._segment_has_input
        ):
            self._fail_syntax("a FILTER clause must follow a read stage", token)

    def _guard_let_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a ``LET`` clause after a write, ``RETURN``, or ``FINISH``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)
        if self._has_clause(parsed, (Create, Merge, Set, Remove, Delete)):
            self._fail_syntax("a LET clause must precede every write clause", token)

    def _guard_finish_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a ``FINISH`` after another result clause.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        self._reject_after_result(parsed, token)

    def _guard_return_position(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a second ``RETURN`` clause in the same segment.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Finish,)):
            self._fail_syntax("FINISH must be the final clause", token)
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("a segment may contain only one RETURN clause", token)

    def _reject_after_result(self, parsed: Sequence[Clause], token: Token) -> None:
        """Reject a clause that follows ``RETURN`` or ``FINISH``.

        Parameters
        ----------
        parsed : Sequence[Clause]
            Clauses already parsed in the current segment.
        token : Token
            Offending keyword.
        """
        if self._has_clause(parsed, (Return,)):
            self._fail_syntax("RETURN must be the final clause", token)
        if self._has_clause(parsed, (Finish,)):
            self._fail_syntax("FINISH must be the final clause", token)

    def _validate_clause_shape(self, clauses: Sequence[Clause], first: Token) -> None:
        """Require every segment and the statement as a whole to be complete.

        Parameters
        ----------
        clauses : Sequence[Clause]
            Parsed clauses in source order.
        first : Token
            First token of the statement, used for the missing-clause position.

        Raises
        ------
        QuerySyntaxError
            If a segment has no result and no write, a trailing ``NEXT`` is
            present, or the statement has no row source.
        """
        if not clauses:
            self._fail_syntax("expected a MATCH clause", first)
        last_next = -1
        for index, clause in enumerate(clauses):
            if isinstance(clause, Next):
                last_next = index
        segment = clauses[last_next + 1 :]
        if not segment:
            self._fail_syntax("NEXT requires a following segment", self._current())
        last = segment[-1]
        has_write = any(
            isinstance(clause, (Create, Merge, Set, Remove, Delete)) for clause in clauses
        )
        has_row_source = any(isinstance(clause, (Match, Unwind, Let)) for clause in clauses)
        if isinstance(last, Finish):
            if not has_write and not has_row_source:
                self._fail_syntax("FINISH requires a read or write clause", first)
            return
        if isinstance(last, Return):
            if not has_write and not has_row_source:
                self._fail_syntax("expected a MATCH or UNWIND clause", first)
            return
        if any(isinstance(clause, (Create, Merge, Set, Remove, Delete)) for clause in segment):
            return
        self._fail_syntax(
            "expected a RETURN clause or FINISH",
            self._current(),
        )

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
        match_mode = self._match_mode()
        mode = self._path_mode()
        patterns = [self._path_pattern(allow_mode=True, allow_search=True)]
        while self._match_punctuation(","):
            patterns.append(self._path_pattern(allow_mode=True, allow_search=True))
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        return Match(
            patterns=tuple(patterns),
            where=where,
            optional=optional,
            mode=mode,
            match_mode=match_mode,
        )

    def _match_mode(self) -> MatchMode:
        """Consume an optional clause match mode.

        Returns
        -------
        MatchMode
            Parsed match mode, or the repeatable default when none is named.

        Raises
        ------
        QuerySyntaxError
            If ``EDGES`` or ``ELEMENTS`` is missing after its first word.
        """
        if self._match_keyword(Keyword.DIFFERENT):
            self._expect_keyword(Keyword.EDGES, "expected EDGES after DIFFERENT")
            return MatchMode.DIFFERENT_EDGES
        if self._match_keyword(Keyword.REPEATABLE):
            self._expect_keyword(Keyword.ELEMENTS, "expected ELEMENTS after REPEATABLE")
            return MatchMode.REPEATABLE_ELEMENTS
        return MatchMode.REPEATABLE_ELEMENTS

    def _clause_pattern(self) -> PathPattern:
        """Parse exactly one path pattern for a clause.

        Returns
        -------
        PathPattern
            Parsed path pattern.
        """
        pattern = self._path_pattern(allow_group=False)
        if self._check_punctuation(","):
            self._reject_unsupported(
                self._current(),
                "multiple path patterns are not supported",
            )
        return pattern

    def _for_clause(self) -> Unwind:
        """Parse a ``FOR <variable> IN <list>`` clause.

        Returns
        -------
        Unwind
            Parsed iteration clause.

        Raises
        ------
        QuerySyntaxError
            If the variable or ``IN`` is missing.
        """
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax("expected a variable after FOR", token)
        self._advance()
        self._expect_keyword(Keyword.IN, "expected IN after the FOR variable")
        expression = self._expression()
        index, ordinality = self._ordinality_suffix()
        return Unwind(
            expression=expression,
            variable=self._identifier_text(token),
            index=index,
            ordinality=ordinality,
        )

    def _filter_clause(self) -> Filter:
        """Parse a ``FILTER`` or ``FILTER WHERE`` clause.

        Returns
        -------
        Filter
            Parsed filter stage.
        """
        self._match_keyword(Keyword.WHERE)
        return Filter(where=self._expression())

    def _unwind_clause(self) -> Unwind:
        """Parse an ``UNWIND <expression> AS <variable>`` clause.

        Returns
        -------
        Unwind
            Parsed unwind clause.

        Raises
        ------
        QuerySyntaxError
            If ``AS`` or the variable is missing.
        """
        expression = self._expression()
        self._expect_keyword(Keyword.AS, "expected AS after the UNWIND expression")
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax("expected a variable after AS", token)
        self._advance()
        index, ordinality = self._ordinality_suffix()
        return Unwind(
            expression=expression,
            variable=self._identifier_text(token),
            index=index,
            ordinality=ordinality,
        )

    def _merge_clause(self) -> Merge:
        """Parse a ``MERGE`` clause and its optional conditional updates.

        Returns
        -------
        Merge
            Parsed merge clause.

        Raises
        ------
        QuerySyntaxError
            If a conditional clause is duplicated or written out of order.
        """
        pattern = self._clause_pattern()
        on_create: Set | None = None
        on_match: Set | None = None
        while self._current().is_keyword(Keyword.ON):
            token = self._current()
            self._advance()
            if self._match_keyword(Keyword.CREATE):
                if on_create is not None:
                    self._fail_syntax("a MERGE may contain only one ON CREATE SET", token)
                if on_match is not None:
                    self._fail_syntax("ON CREATE SET must precede ON MATCH SET", token)
                self._expect_keyword(Keyword.SET, "expected SET after ON CREATE")
                on_create = self._set_clause()
                continue
            if self._match_keyword(Keyword.MATCH):
                if on_match is not None:
                    self._fail_syntax("a MERGE may contain only one ON MATCH SET", token)
                self._expect_keyword(Keyword.SET, "expected SET after ON MATCH")
                on_match = self._set_clause()
                continue
            self._fail_syntax("expected CREATE or MATCH after ON", self._current())
        return Merge(pattern=pattern, on_create=on_create, on_match=on_match)

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
        distinct = self._match_keyword(Keyword.DISTINCT)
        star = self._match_operator("*")
        items: list[ReturnItem] = []
        if not star:
            items.append(self._return_item())
            while self._match_punctuation(","):
                items.append(self._return_item())
        elif self._check_punctuation(","):
            self._fail_syntax("WITH * cannot be combined with other items", self._current())
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        order_by = self._order_by()
        skip: Expression | None = None
        limit: Expression | None = None
        if self._match_keyword(Keyword.OFFSET) or self._match_keyword(Keyword.SKIP):
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
            star=star,
        )

    def _return_clause(self) -> Return:
        """Parse a ``RETURN`` clause and its grouping and pagination.

        Returns
        -------
        Return
            Parsed return clause.
        """
        if self._check_no_bindings():
            self._advance()
            self._advance()
            if (
                self._current().is_keyword(Keyword.ORDER)
                or self._current().is_keyword(Keyword.OFFSET)
                or self._current().is_keyword(Keyword.SKIP)
                or self._current().is_keyword(Keyword.LIMIT)
                or self._current().is_keyword(Keyword.GROUP)
                or self._current().is_keyword(Keyword.DISTINCT)
            ):
                self._fail_syntax(
                    "RETURN NO BINDINGS does not accept modifiers",
                    self._current(),
                )
            return Return(items=(), no_bindings=True)
        star = False
        distinct = False
        items: tuple[ReturnItem, ...] = ()
        if self._check_operator("*"):
            self._advance()
            star = True
        else:
            self._match_keyword(Keyword.ALL)
            distinct = self._match_keyword(Keyword.DISTINCT)
            if self._check_no_bindings():
                self._fail_syntax(
                    "RETURN NO BINDINGS cannot be combined with ALL or DISTINCT",
                    self._current(),
                )
            parsed = [self._return_item()]
            while self._match_punctuation(","):
                parsed.append(self._return_item())
            items = tuple(parsed)
        group_by = self._group_by()
        if group_by is not None and star:
            self._fail_syntax("RETURN * cannot be combined with GROUP BY", self._current())
        order_by = self._order_by()
        skip: Expression | None = None
        limit: Expression | None = None
        if self._match_keyword(Keyword.OFFSET) or self._match_keyword(Keyword.SKIP):
            skip = self._expression()
        if self._match_keyword(Keyword.LIMIT):
            limit = self._expression()
        return Return(
            items=items,
            distinct=distinct,
            order_by=order_by,
            skip=skip,
            limit=limit,
            star=star,
            group_by=group_by,
        )

    def _group_by(self) -> tuple[Expression, ...] | None:
        """Parse an optional ``GROUP BY`` suffix.

        Returns
        -------
        tuple[Expression, ...] | None
            Grouping keys, an empty tuple for ``GROUP BY ()``, or ``None`` when
            the suffix is absent.
        """
        if not self._match_keyword(Keyword.GROUP):
            return None
        self._expect_keyword(Keyword.BY, "expected BY after GROUP")
        if self._match_punctuation("("):
            if self._match_punctuation(")"):
                return ()
            keys = [self._expression()]
            self._expect_punctuation(")", "expected ')' to close GROUP BY")
            while self._match_punctuation(","):
                keys.append(self._expression())
            return tuple(keys)
        keys = [self._expression()]
        while self._match_punctuation(","):
            keys.append(self._expression())
        return tuple(keys)

    def _let_clause(self) -> Let:
        """Parse a ``LET`` clause with one or more assignments.

        Returns
        -------
        Let
            Parsed ``LET`` clause.
        """
        assignments: list[LetAssignment] = []
        while True:
            token = self._current()
            if not self._is_identifier(token):
                self._fail_syntax("expected a variable after LET", token)
            name = self._identifier_text(self._advance())
            self._expect_operator("=", "expected '=' in a LET assignment")
            assignments.append(LetAssignment(name=name, expression=self._expression()))
            if not self._match_punctuation(","):
                break
        return Let(assignments=tuple(assignments))

    def _yield_clause(self) -> Yield:
        """Parse the column projection attached to ``NEXT``.

        Returns
        -------
        Yield
            Parsed ``YIELD`` clause.
        """
        items: list[YieldItem] = []
        while True:
            token = self._current()
            if not self._is_identifier(token):
                self._fail_syntax("expected a column name after YIELD", token)
            name = self._identifier_text(self._advance())
            alias: str | None = None
            if self._match_keyword(Keyword.AS):
                if not self._is_identifier(self._current()):
                    self._fail_syntax("expected an alias after AS", self._current())
                alias = self._identifier_text(self._advance())
            items.append(YieldItem(name=name, alias=alias))
            if not self._match_punctuation(","):
                break
        return Yield(items=tuple(items))

    def _ordinality_suffix(self) -> tuple[str | None, OrdinalityKind | None]:
        """Parse an optional ``WITH ORDINALITY`` or ``WITH OFFSET`` suffix.

        Returns
        -------
        tuple[str | None, OrdinalityKind | None]
            Position variable and its base, or two ``None`` values.
        """
        if not self._current().is_keyword(Keyword.WITH):
            return None, None
        if self._peek_is_keyword(Keyword.ORDINALITY):
            kind = OrdinalityKind.ORDINALITY
        elif self._peek_is_keyword(Keyword.OFFSET):
            kind = OrdinalityKind.OFFSET
        else:
            return None, None
        self._advance()
        self._advance()
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax("expected a variable after the ordinality modifier", token)
        name = self._identifier_text(self._advance())
        if self._current().is_keyword(Keyword.WITH) and (
            self._peek_is_keyword(Keyword.ORDINALITY) or self._peek_is_keyword(Keyword.OFFSET)
        ):
            self._fail_syntax(
                "WITH ORDINALITY and WITH OFFSET cannot be combined",
                self._current(),
            )
        return name, kind

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

    def _path_pattern(
        self,
        *,
        allow_mode: bool = False,
        allow_search: bool = False,
        allow_group: bool = True,
    ) -> PathPattern:
        """Parse one path pattern.

        Parameters
        ----------
        allow_mode : bool, optional
            Whether a per-path mode keyword may precede the pattern, by
            default ``False``.
        allow_search : bool, optional
            Whether a path-search prefix may follow the path variable, by
            default ``False``.
        allow_group : bool, optional
            Whether grouped and juxtaposed terms are accepted, by default
            ``True``.

        Returns
        -------
        PathPattern
            Parsed path pattern.
        """
        variable = self._pattern_variable()
        search = self._path_search() if allow_search else None
        mode = self._path_mode() if allow_mode else None
        if variable is None and search is None and mode is not None:
            variable = self._pattern_variable()
        terms: list[SimplePathTerm | GroupedPathTerm] = [
            self._path_term() if allow_group else self._simple_term()
        ]
        if allow_group:
            while self._check_punctuation("("):
                terms.append(self._path_term())
        return PathPattern(
            terms=tuple(terms),
            variable=variable,
            mode=mode,
            search=search,
        )

    def _path_term(self) -> SimplePathTerm | GroupedPathTerm:
        """Parse one simple or grouped path term.

        Returns
        -------
        SimplePathTerm | GroupedPathTerm
            Parsed term.
        """
        if self._starts_group():
            return self._grouped_term()
        return self._simple_term()

    def _starts_group(self) -> bool:
        """Report whether the current parenthesis starts a grouped term.

        Returns
        -------
        bool
            ``True`` for a nested term, a group path variable, or an inner
            path mode.
        """
        if not self._check_punctuation("("):
            return False
        next_token = self._peek(1)
        if next_token.kind is TokenKind.PUNCTUATION and next_token.value == "(":
            return True
        if next_token.kind is TokenKind.KEYWORD and Keyword(next_token.value) in {
            Keyword.WALK,
            Keyword.TRAIL,
            Keyword.SIMPLE,
            Keyword.ACYCLIC,
        }:
            return True
        return self._is_identifier(next_token) and self._peek_is_operator_at(2, "=")

    def _simple_term(self) -> SimplePathTerm:
        """Parse a node pattern and its relationship-node pairs.

        Returns
        -------
        SimplePathTerm
            Parsed simple term.
        """
        nodes = [self._node_pattern()]
        relationships: list[RelationshipPattern] = []
        while self._is_relationship_start():
            relationships.append(self._relationship_pattern())
            nodes.append(self._node_pattern())
        return SimplePathTerm(nodes=tuple(nodes), relationships=tuple(relationships))

    def _grouped_term(self) -> GroupedPathTerm:
        """Parse a parenthesized path pattern and its quantifier.

        Returns
        -------
        GroupedPathTerm
            Parsed grouped term.

        Raises
        ------
        QuerySyntaxError
            If the closing parenthesis, inner path, or quantifier is missing.
        """
        self._expect_punctuation("(", "expected '(' to start a grouped path pattern")
        variable = self._pattern_variable()
        mode = self._path_mode()
        pattern = self._path_pattern()
        self._expect_punctuation(")", "expected ')' to close a grouped path pattern")
        quantifier = self._group_quantifier()
        return GroupedPathTerm(
            pattern=pattern,
            quantifier=quantifier,
            variable=variable,
            mode=mode,
        )

    def _group_quantifier(self) -> HopRange:
        """Parse the quantifier of a grouped path term.

        Returns
        -------
        HopRange
            Parsed repetition bounds.

        Raises
        ------
        QuerySyntaxError
            If the quantifier is missing or uses the legacy ``*n..m`` form.
        """
        if self._match_operator("*"):
            token = self._previous()
            if self._current().kind is TokenKind.INTEGER or (
                self._current().kind is TokenKind.OPERATOR and self._current().value in {"-", "."}
            ):
                self._fail_syntax(
                    "the legacy *n..m spelling is not allowed on a grouped path",
                    token,
                )
            return HopRange(0, None)
        if self._match_operator("+"):
            return HopRange(1, None)
        if self._check_punctuation("{") and self._starts_quantifier():
            lower, upper, _ = self._canonical_quantifier()
            return HopRange(0 if lower is None else lower, upper)
        self._fail_syntax(
            "expected a quantifier after a grouped path pattern",
            self._current(),
        )

    def _pattern_variable(self) -> str | None:
        """Consume an optional ``identifier =`` path-variable prefix.

        Returns
        -------
        str | None
            Path variable, or ``None`` when the next token is not a variable
            assignment.
        """
        if self._is_identifier(self._current()) and self._peek_is_operator("="):
            variable = self._identifier_text(self._advance())
            self._advance()
            return variable
        return None

    def _path_search(self) -> PathSearch | None:
        """Consume an optional path-search prefix.

        Returns
        -------
        PathSearch | None
            Parsed prefix, or ``None`` when the current token starts no search.

        Raises
        ------
        QuerySyntaxError
            If a prefix is incomplete or ``SHORTEST`` has no integer literal.
        """
        token = self._current()
        if self._match_keyword(Keyword.ANY):
            if self._match_keyword(Keyword.SHORTEST):
                return PathSearch(PathSearchKind.ANY_SHORTEST, span=token.span)
            return PathSearch(PathSearchKind.ANY, span=token.span)
        if self._match_keyword(Keyword.ALL):
            self._expect_keyword(Keyword.SHORTEST, "expected SHORTEST after ALL")
            return PathSearch(PathSearchKind.ALL_SHORTEST, span=token.span)
        if not self._match_keyword(Keyword.SHORTEST):
            return None
        negative = self._match_operator("-")
        value = self._current()
        if value.kind is not TokenKind.INTEGER:
            self._fail_syntax("expected an integer literal after SHORTEST", value)
        self._advance()
        number = int(value.value)
        return PathSearch(
            PathSearchKind.SHORTEST,
            -number if negative else number,
            span=token.span,
        )

    def _path_mode(self) -> PathMode | None:
        """Consume an optional path-mode keyword.

        Returns
        -------
        PathMode | None
            Parsed mode, or ``None`` when the current token is not a mode.
        """
        token = self._current()
        if token.kind is not TokenKind.KEYWORD:
            return None
        modes = {
            Keyword.WALK: PathMode.WALK,
            Keyword.TRAIL: PathMode.TRAIL,
            Keyword.SIMPLE: PathMode.SIMPLE,
            Keyword.ACYCLIC: PathMode.ACYCLIC,
        }
        mode = modes.get(Keyword(token.value))
        if mode is None:
            return None
        self._advance()
        return mode

    def _node_pattern(self) -> NodePattern:
        """Parse one parenthesized node pattern.

        Returns
        -------
        NodePattern
            Parsed node pattern.
        """
        self._expect_punctuation("(", "expected '(' to start a node pattern")
        if self._current().kind is TokenKind.KEYWORD and Keyword(self._current().value) in {
            Keyword.ANY,
            Keyword.ALL,
            Keyword.SHORTEST,
        }:
            self._fail_syntax(
                "a path-search prefix is not allowed inside a node pattern",
                self._current(),
            )
        variable: str | None = None
        properties: tuple[PropertyEntry, ...] = ()
        where: Expression | None = None
        if self._is_identifier(self._current()):
            variable = self._identifier_text(self._advance())
        label_expression = self._label_spec("a node label")
        labels = LabelExpressions.conjunction(label_expression) or ()
        if self._check_punctuation("{"):
            properties = self._property_map()
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        self._expect_punctuation(")", "expected ')' to close a node pattern")
        return NodePattern(
            variable=variable,
            labels=labels,
            properties=properties,
            label_expression=label_expression,
            where=where,
        )

    def _relationship_pattern(self) -> RelationshipPattern:
        """Parse one relationship pattern, including its direction.

        Returns
        -------
        RelationshipPattern
            Parsed relationship pattern.

        Raises
        ------
        QuerySyntaxError
            If the direction token or the closing marker is malformed.
        """
        opening = self._current()
        if opening.kind is not TokenKind.OPERATOR or opening.value not in self._bare_directions():
            self._fail_syntax("expected '-' to start a relationship pattern", opening)
        self._advance()
        if not self._check_punctuation("["):
            return RelationshipPattern(direction=self._bare_directions()[opening.value])
        variable, types, properties, min_hops, max_hops, canonical, label_expression, where = (
            self._relationship_detail()
        )
        closing = self._current()
        if closing.kind is not TokenKind.OPERATOR or closing.value not in {
            "-",
            "->",
            "-->",
            "~",
        }:
            self._fail_syntax(
                "expected '-', '->', or '~' to close a relationship pattern",
                closing,
            )
        self._advance()
        return RelationshipPattern(
            variable=variable,
            types=types,
            direction=self._combined_direction(opening, closing),
            properties=properties,
            min_hops=min_hops,
            max_hops=max_hops,
            canonical_quantifier=canonical,
            label_expression=label_expression,
            where=where,
        )

    @staticmethod
    def _bare_directions() -> dict[str, EdgeDirection]:
        """Return the direction token map for patterns without a detail.

        Returns
        -------
        dict[str, EdgeDirection]
            Operator spelling to admitted storage directions.
        """
        return {
            "->": EdgeDirection.OUTGOING,
            "-->": EdgeDirection.OUTGOING,
            "<-": EdgeDirection.INCOMING,
            "<--": EdgeDirection.INCOMING,
            "-": EdgeDirection.ANY,
            "~": EdgeDirection.UNDIRECTED,
            "<~": EdgeDirection.INCOMING_OR_UNDIRECTED,
            "~>": EdgeDirection.OUTGOING_OR_UNDIRECTED,
            "<->": EdgeDirection.DIRECTED_EITHER,
        }

    @staticmethod
    def _combined_direction(opening: Token, closing: Token) -> EdgeDirection:
        """Resolve the direction from an opening and a closing marker.

        Parameters
        ----------
        opening : Token
            Operator that opened the relationship pattern.
        closing : Token
            Operator that closed it.

        Returns
        -------
        EdgeDirection
            Admitted storage directions.

        Raises
        ------
        QuerySyntaxError
            If the opening and closing markers do not form a direction.
        """
        aliases = {"-->": "->", "<--": "<-"}
        first = aliases.get(str(opening.value), str(opening.value))
        second = aliases.get(str(closing.value), str(closing.value))
        directions = {
            ("-", "->"): EdgeDirection.OUTGOING,
            ("-", "-"): EdgeDirection.ANY,
            ("<-", "-"): EdgeDirection.INCOMING,
            ("<-", "->"): EdgeDirection.DIRECTED_EITHER,
            ("<-", "~"): EdgeDirection.INCOMING_OR_UNDIRECTED,
            ("~", "->"): EdgeDirection.OUTGOING_OR_UNDIRECTED,
            ("~", "~"): EdgeDirection.UNDIRECTED,
        }
        direction = directions.get((first, second))
        if direction is None:
            raise QuerySyntaxError(
                "unsupported relationship direction",
                line=opening.span.line,
                column=opening.span.column,
            )
        return direction

    def _is_relationship_start(self) -> bool:
        """Report whether the current token can start a relationship pattern.

        Returns
        -------
        bool
            ``True`` for any relationship arrow form.
        """
        token = self._current()
        return token.kind is TokenKind.OPERATOR and token.value in {
            "-",
            "->",
            "<-",
            "-->",
            "<--",
            "~",
            "~>",
            "<~",
            "<->",
        }

    def _relationship_detail(
        self,
    ) -> tuple[
        str | None,
        tuple[str, ...],
        tuple[PropertyEntry, ...],
        int | None,
        int | None,
        bool,
        LabelExpression | None,
        Expression | None,
    ]:
        """Parse the optional bracket contents of a relationship pattern.

        Returns
        -------
        tuple[str | None, tuple[str, ...], tuple[PropertyEntry, ...], int | None, int | None, \
bool, LabelExpression | None, Expression | None]
            Variable, accepted types, property map, quantifier bounds,
            canonical-quantifier flag, label expression, and inline predicate.
        """
        if not self._match_punctuation("["):
            return None, (), (), None, None, False, None, None
        variable: str | None = None
        properties: tuple[PropertyEntry, ...] = ()
        where: Expression | None = None
        if self._is_identifier(self._current()):
            variable = self._identifier_text(self._advance())
        label_expression = self._label_spec("a relationship type")
        types = LabelExpressions.conjunction(label_expression) or ()
        min_hops, max_hops, canonical = self._quantifier()
        if self._check_punctuation("{"):
            properties = self._property_map()
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        self._expect_punctuation("]", "expected ']' to close a relationship pattern")
        return variable, types, properties, min_hops, max_hops, canonical, label_expression, where

    def _quantifier(self) -> tuple[int | None, int | None, bool]:
        """Parse an optional relationship quantifier.

        Returns
        -------
        tuple[int | None, int | None, bool]
            Lower and upper hop bounds and whether the canonical spelling was
            used. Both bounds are ``None`` for an ordinary relationship, and a
            missing upper bound means the quantifier is open-ended.

        Raises
        ------
        QuerySyntaxError
            If a bound is not an integer or the range separator is malformed.
        """
        if self._match_operator("*"):
            return self._legacy_quantifier()
        if self._match_operator("+"):
            return 1, None, True
        if self._check_punctuation("{") and self._starts_quantifier():
            return self._canonical_quantifier()
        return None, None, False

    def _legacy_quantifier(self) -> tuple[int | None, int | None, bool]:
        """Parse the body of a legacy ``*`` quantifier.

        Returns
        -------
        tuple[int | None, int | None, bool]
            Lower and upper bounds, and whether the spelling is canonical. A
            bare ``*`` is the canonical zero-or-more form; the legacy
            ``*n..`` spelling keeps ``False`` and an open upper bound.

        Raises
        ------
        QuerySyntaxError
            If a bound is not an integer or the range separator is malformed.
        """
        lower: int | None = None
        if self._current().kind is TokenKind.FLOAT:
            self._fail_syntax(
                "expected an integer bound in a variable-length pattern",
                self._current(),
            )
        if self._match_operator("-"):
            lower = -self._integer_bound()
        elif self._current().kind is TokenKind.INTEGER:
            lower = self._integer_bound()
        if self._match_punctuation("."):
            opening = self._current()
            self._expect_punctuation(".", "expected '..' in a variable-length pattern")
            upper: int | None = None
            if self._match_operator("-"):
                upper = -self._integer_bound()
            elif self._current().kind is TokenKind.INTEGER:
                upper = self._integer_bound()
            if lower is None and upper is None:
                self._fail_syntax("expected a hop count in a variable-length pattern", opening)
            return (1 if lower is None else lower), upper, False
        if lower is None:
            return 0, None, True
        return lower, lower, False

    def _canonical_quantifier(self) -> tuple[int | None, int | None, bool]:
        """Parse the body of a canonical ``{n}``, ``{m,n}``, ``{,n}``, or ``{m,}`` form.

        Returns
        -------
        tuple[int | None, int | None, bool]
            Lower and upper bounds, and ``True`` because the spelling is
            canonical. A missing upper bound means the quantifier is
            open-ended.

        Raises
        ------
        QuerySyntaxError
            If the braces or hop counts are malformed.
        """
        opening = self._current()
        self._expect_punctuation("{", "expected '{' to start a canonical quantifier")
        lower: int | None = None
        if self._current().kind is TokenKind.INTEGER:
            lower = self._integer_bound()
        if self._match_punctuation(","):
            upper: int | None = None
            if self._current().kind is TokenKind.INTEGER:
                upper = self._integer_bound()
            self._expect_punctuation("}", "expected '}' to close a canonical quantifier")
            if lower is None and upper is None:
                self._fail_syntax("expected a hop count in the canonical quantifier", opening)
            return 0 if lower is None else lower, upper, True
        if lower is None:
            self._fail_syntax("expected a hop count in the canonical quantifier", opening)
        self._expect_punctuation("}", "expected '}' to close a canonical quantifier")
        return lower, lower, True

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
        if self._match_keyword(Keyword.DESC) or self._match_keyword(Keyword.DESCENDING):
            descending = True
        elif self._match_keyword(Keyword.ASC):
            descending = False
        else:
            self._match_keyword(Keyword.ASCENDING)
        nulls_first: bool | None = None
        if self._match_keyword(Keyword.NULLS):
            if self._match_keyword(Keyword.FIRST):
                nulls_first = True
            elif self._match_keyword(Keyword.LAST):
                nulls_first = False
            else:
                self._fail_syntax("expected FIRST or LAST after NULLS", self._current())
        return SortItem(
            expression=expression,
            descending=descending,
            nulls_first=nulls_first,
        )

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
        """Parse addition, subtraction, and string concatenation.

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
            elif self._match_operator("||"):
                left = Binary(
                    left=left,
                    operator=Operators.CONCAT,
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
        """Parse property access and list indexing after a primary expression.

        Returns
        -------
        Expression
            Parsed expression.
        """
        expression = self._primary_expression()
        while True:
            if self._match_punctuation("."):
                token = self._current()
                if not self._is_identifier(token):
                    self._fail_syntax("expected a property key after '.'", token)
                self._advance()
                expression = Property(
                    target=expression,
                    key=self._identifier_text(token),
                    span=token.span,
                )
                continue
            if not self._match_punctuation("["):
                return expression
            start: Expression | None = None
            if not self._check_punctuation(":"):
                start = self._expression()
            if self._match_punctuation(":"):
                end = None if self._check_punctuation("]") else self._expression()
                self._expect_punctuation("]", "expected ']' to close the list slice")
                expression = ListSlice(target=expression, start=start, end=end)
                continue
            if start is None:
                self._fail_syntax("expected a list index or a slice", self._current())
            self._expect_punctuation("]", "expected ']' to close the list index")
            expression = ListAccess(target=expression, index=start)

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
            self._advance()
            return self._case_expression()
        if token.is_keyword(Keyword.CALL):
            self._reject_unsupported(token, "subqueries are not supported")
        if self._is_identifier(token) and self._peek_is_punctuation("("):
            return self._function_call()
        if token.kind is TokenKind.KEYWORD:
            self._fail_syntax(f"unexpected token {token.text!r}", token)
        if self._is_identifier(token):
            self._advance()
            name = self._identifier_text(token)
            if name.upper() in {"EXISTS", "COUNT"} and self._check_punctuation("{"):
                kind = SubqueryKind(name.upper())
                return self._subquery_expression(kind)
            return Variable(name=name, span=token.span)
        if self._match_punctuation("("):
            expression = self._expression()
            self._expect_punctuation(")", "expected ')' to close the expression")
            return expression
        if self._match_punctuation("["):
            if self._is_identifier(self._current()) and self._peek_is_keyword(Keyword.IN):
                return self._list_comprehension()
            return self._list_literal()
        if token.kind is TokenKind.PUNCTUATION and token.value == "{":
            return self._map_literal()
        self._fail_syntax(f"unexpected token {token.text!r}", token)

    def _case_expression(self) -> Case:
        """Parse a simple or searched ``CASE`` after the keyword.

        Returns
        -------
        Case
            Parsed case expression.
        """
        operand: Expression | None = None
        if not self._current().is_keyword(Keyword.WHEN):
            operand = self._expression()
        branches: list[CaseBranch] = []
        while self._match_keyword(Keyword.WHEN):
            match = self._expression()
            self._expect_keyword(Keyword.THEN, "expected THEN after a CASE branch")
            branches.append(CaseBranch(match=match, result=self._expression()))
        if not branches:
            self._fail_syntax("CASE requires at least one WHEN branch", self._current())
        default: Expression | None = None
        if self._match_keyword(Keyword.ELSE):
            default = self._expression()
        self._expect_keyword(Keyword.END, "expected END to close the CASE expression")
        return Case(operand=operand, branches=tuple(branches), default=default)

    def _map_literal(self) -> MapLiteral:
        """Parse a map literal whose opening brace is the current token.

        Returns
        -------
        MapLiteral
            Parsed map literal.

        Raises
        ------
        QuerySyntaxError
            If a key is duplicated or the map is malformed.
        """
        self._expect_punctuation("{", "expected '{' to start a map literal")
        entries: list[MapEntry] = []
        keys: set[str] = set()
        if self._match_punctuation("}"):
            return MapLiteral(entries=())
        while True:
            key = self._property_key()
            if key in keys:
                self._fail_syntax(f"duplicate map key {key!r}", self._current())
            keys.add(key)
            self._expect_punctuation(":", "expected ':' after a map key")
            entries.append(MapEntry(key=key, value=self._expression()))
            if not self._match_punctuation(","):
                break
        self._expect_punctuation("}", "expected '}' to close the map literal")
        return MapLiteral(entries=tuple(entries))

    def _list_comprehension(self) -> ListComprehension:
        """Parse a list comprehension after its opening bracket.

        Returns
        -------
        ListComprehension
            Parsed comprehension.
        """
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax("expected a variable in the list comprehension", token)
        variable = self._identifier_text(self._advance())
        self._expect_keyword(Keyword.IN, "expected IN after the list variable")
        source = self._expression()
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        projection: Expression | None = None
        if self._match_punctuation("|"):
            projection = self._expression()
        self._expect_punctuation("]", "expected ']' to close the list comprehension")
        return ListComprehension(
            variable=variable,
            source=source,
            where=where,
            projection=projection,
        )

    def _subquery_expression(self, kind: SubqueryKind) -> Subquery:
        """Parse a read-only subquery expression.

        Parameters
        ----------
        kind : SubqueryKind
            Whether the expression is ``EXISTS`` or ``COUNT``.

        Returns
        -------
        Subquery
            Parsed subquery expression.
        """
        self._expect_punctuation("{", "expected '{' to start a subquery")
        clauses: list[Clause] = []
        while not self._check_punctuation("}"):
            current = self._current()
            if current.kind is TokenKind.EOF:
                self._fail_syntax("expected '}' to close the subquery", current)
            if current.is_keyword(Keyword.RETURN) or current.is_keyword(Keyword.FINISH):
                self._reject_unsupported(
                    current,
                    "a subquery cannot contain a result clause",
                )
            if current.is_keyword(Keyword.NEXT) or current.is_keyword(Keyword.YIELD):
                self._reject_unsupported(
                    current,
                    "NEXT and YIELD are not supported in a subquery",
                )
            write_keywords = {
                Keyword.CREATE,
                Keyword.INSERT,
                Keyword.MERGE,
                Keyword.SET,
                Keyword.REMOVE,
                Keyword.DELETE,
                Keyword.DETACH,
                Keyword.NODETACH,
            }
            if current.kind is TokenKind.KEYWORD and Keyword(current.value) in write_keywords:
                self._reject_unsupported(
                    current,
                    "a subquery is read-only",
                )
            clauses.append(self._next_clause(clauses))
        self._expect_punctuation("}", "expected '}' to close the subquery")
        if not clauses:
            self._fail_syntax("a subquery requires a read stage", self._current())
        return Subquery(kind=kind, clauses=tuple(clauses))

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

    def _label_spec(self, description: str) -> LabelExpression | None:
        """Parse an optional ``:`` or ``IS`` label expression.

        Parameters
        ----------
        description : str
            Human-readable label description for error messages.

        Returns
        -------
        LabelExpression | None
            Parsed expression, or ``None`` when the pattern names no label.
        """
        if self._match_punctuation(":"):
            return self._label_or(description)
        if self._match_keyword(Keyword.IS):
            return self._label_or(description)
        return None

    def _label_or(self, description: str) -> LabelExpression:
        """Parse a label disjunction.

        Parameters
        ----------
        description : str
            Human-readable label description for error messages.

        Returns
        -------
        LabelExpression
            Parsed expression.
        """
        expression = self._label_and(description)
        while self._match_punctuation("|"):
            expression = LabelOr(left=expression, right=self._label_and(description))
        return expression

    def _label_and(self, description: str) -> LabelExpression:
        """Parse a label conjunction, accepting ``&`` and ``:``.

        Parameters
        ----------
        description : str
            Human-readable label description for error messages.

        Returns
        -------
        LabelExpression
            Parsed expression.
        """
        expression = self._label_not(description)
        while True:
            if self._match_operator("&") or self._match_punctuation(":"):
                expression = LabelAnd(left=expression, right=self._label_not(description))
            else:
                return expression

    def _label_not(self, description: str) -> LabelExpression:
        """Parse a negated label expression.

        Parameters
        ----------
        description : str
            Human-readable label description for error messages.

        Returns
        -------
        LabelExpression
            Parsed expression.
        """
        if self._match_operator("!"):
            return LabelNot(operand=self._label_not(description))
        return self._label_primary(description)

    def _label_primary(self, description: str) -> LabelExpression:
        """Parse one label name or the wildcard.

        Parameters
        ----------
        description : str
            Human-readable label description for error messages.

        Returns
        -------
        LabelExpression
            Parsed expression.
        """
        if self._match_operator("%"):
            return LabelWildcard()
        token = self._current()
        if not self._is_identifier(token):
            self._fail_syntax(f"expected {description}", token)
        self._advance()
        return LabelName(name=self._identifier_text(token))

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

    def _check_no_bindings(self) -> bool:
        """Report whether the current tokens spell ``NO BINDINGS``.

        Returns
        -------
        bool
            ``True`` when both words appear as identifiers.
        """
        first, second = self._current(), self._peek(1)
        return (
            first.kind is TokenKind.IDENTIFIER
            and str(first.value).upper() == "NO"
            and second.kind is TokenKind.IDENTIFIER
            and str(second.value).upper() == "BINDINGS"
        )

    def _peek_is_keyword(self, keyword: Keyword, distance: int = 1) -> bool:
        """Report whether an upcoming token is the given keyword.

        Parameters
        ----------
        keyword : Keyword
            Keyword to test.
        distance : int, optional
            Offset from the current position, by default one.

        Returns
        -------
        bool
            ``True`` when that token is the keyword.
        """
        token = self._peek(distance)
        return token.kind is TokenKind.KEYWORD and token.value == keyword.value

    def _starts_quantifier(self) -> bool:
        """Report whether the current ``{`` starts a ``{n,m}`` quantifier.

        Returns
        -------
        bool
            ``True`` when the next token is an integer or a comma.
        """
        token = self._peek(1)
        return token.kind is TokenKind.INTEGER or (
            token.kind is TokenKind.PUNCTUATION and token.value == ","
        )

    def _reject_catalog_graph(self) -> None:
        """Reject ``CREATE GRAPH`` and ``INSERT GRAPH`` as out of profile.

        Raises
        ------
        QuerySemanticError
            If the write clause names a catalog operation.
        """
        token = self._current()
        if token.kind is TokenKind.IDENTIFIER and str(token.value).upper() == "GRAPH":
            self._reject_unsupported(token, "catalog statements are out of profile")

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
        return self._peek_is_operator_at(1, text)

    def _peek_is_operator_at(self, distance: int, text: str) -> bool:
        """Report whether an upcoming token is an operator.

        Parameters
        ----------
        distance : int
            Positive offset from the current position.
        text : str
            Operator to test.

        Returns
        -------
        bool
            ``True`` when the upcoming token is that operator.
        """
        token = self._peek(distance)
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
            ``True`` for a plain, quoted, or keyword token used in a data
            position such as an alias, label, or property key.
        """
        return token.kind in {
            TokenKind.IDENTIFIER,
            TokenKind.QUOTED_IDENTIFIER,
            TokenKind.KEYWORD,
        }

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
            Decoded identifier name, preserving the source case of a keyword
            used in a data position.
        """
        if token.kind is TokenKind.KEYWORD:
            return token.text
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
