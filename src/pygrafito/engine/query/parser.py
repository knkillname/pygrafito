# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Recursive-descent and Pratt parser for the read-only query language."""

import typing
from collections.abc import Sequence

from pygrafito.engine.query.ast import (
    Binary,
    Expression,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    NodePattern,
    Operators,
    Parameter,
    PathPattern,
    Property,
    PropertyEntry,
    RelationshipPattern,
    ReturnItem,
    SortItem,
    Star,
    Statement,
    Unary,
    Variable,
)
from pygrafito.engine.query.lexer import Lexer
from pygrafito.engine.query.tokens import Keyword, Token, TokenKind
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
            Keyword.WITH,
            Keyword.UNWIND,
            Keyword.CREATE,
            Keyword.MERGE,
            Keyword.SET,
            Keyword.REMOVE,
            Keyword.DELETE,
            Keyword.DETACH,
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
        current = self._current()
        if current.is_keyword(Keyword.OPTIONAL) and self._peek(1).is_keyword(Keyword.MATCH):
            self._reject_unsupported(current, "OPTIONAL MATCH is not supported")
        if current.kind is TokenKind.KEYWORD and Keyword(current.value) in self.UNSUPPORTED_CLAUSES:
            self._reject_unsupported(current, f"{current.value} is not supported")
        if current.is_keyword(Keyword.CALL):
            self._reject_unsupported(current, "subqueries are not supported")
        if not current.is_keyword(Keyword.MATCH):
            self._fail_syntax("expected a MATCH clause", current)
        self._advance()
        pattern = self._path_pattern()
        if self._match_punctuation(","):
            self._reject_unsupported(self._previous(), "multiple path patterns are not supported")
        where: Expression | None = None
        if self._match_keyword(Keyword.WHERE):
            where = self._expression()
        self._reject_trailing_clauses()
        self._expect_keyword(Keyword.RETURN, "expected a RETURN clause")
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
        self._reject_trailing_clauses()
        self._match_punctuation(";")
        if self._current().kind is not TokenKind.EOF:
            if self._current().kind is TokenKind.KEYWORD:
                self._reject_unsupported(
                    self._current(),
                    "multiple statements are not supported",
                )
            self._fail_syntax("unexpected token after the statement", self._current())
        return Statement(
            pattern=pattern,
            return_items=tuple(items),
            where=where,
            distinct=distinct,
            order_by=order_by,
            skip=skip,
            limit=limit,
        )

    def _reject_trailing_clauses(self) -> None:
        """Reject unsupported or misplaced clauses at the current position.

        Raises
        ------
        QuerySemanticError
            If a recognized unsupported clause appears.
        """
        current = self._current()
        if current.is_keyword(Keyword.OPTIONAL) and self._peek(1).is_keyword(Keyword.MATCH):
            self._reject_unsupported(current, "OPTIONAL MATCH is not supported")
        if current.is_keyword(Keyword.MATCH):
            self._reject_unsupported(current, "multiple MATCH clauses are not supported")
        if current.is_keyword(Keyword.CALL):
            self._reject_unsupported(current, "subqueries are not supported")
        if current.kind is TokenKind.KEYWORD and Keyword(current.value) in self.UNSUPPORTED_CLAUSES:
            self._reject_unsupported(current, f"{current.value} is not supported")

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
            if self._check_punctuation(","):
                self._reject_unsupported(
                    self._current(),
                    "multiple path patterns are not supported",
                )
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
            variable, types, properties = self._relationship_detail()
            self._expect_operator("-", "expected '-' to close an incoming relationship")
            return RelationshipPattern(
                variable=variable,
                types=types,
                direction=Direction.INCOMING,
                properties=properties,
            )
        self._expect_operator("-", "expected '-' to start a relationship pattern")
        variable, types, properties = self._relationship_detail()
        self._expect_operator("-", "expected '-' to close a relationship pattern")
        direction = Direction.OUTGOING if self._match_operator(">") else Direction.BOTH
        return RelationshipPattern(
            variable=variable,
            types=types,
            direction=direction,
            properties=properties,
        )

    def _relationship_detail(
        self,
    ) -> tuple[str | None, tuple[str, ...], tuple[PropertyEntry, ...]]:
        """Parse the optional bracket contents of a relationship pattern.

        Returns
        -------
        tuple[str | None, tuple[str, ...], tuple[PropertyEntry, ...]]
            Variable, accepted types, and property map.
        """
        if not self._match_punctuation("["):
            return None, (), ()
        variable: str | None = None
        types: list[str] = []
        properties: tuple[PropertyEntry, ...] = ()
        if self._is_identifier(self._current()):
            variable = self._identifier_text(self._advance())
        if self._check_operator("*"):
            self._reject_unsupported(
                self._current(),
                "variable-length relationship patterns are not supported",
            )
        if self._match_punctuation(":"):
            types.append(self._label("a relationship type"))
            while self._match_punctuation("|"):
                types.append(self._label("a relationship type"))
        if self._check_operator("*"):
            self._reject_unsupported(
                self._current(),
                "variable-length relationship patterns are not supported",
            )
        if self._check_punctuation("{"):
            properties = self._property_map()
        self._expect_punctuation("]", "expected ']' to close a relationship pattern")
        return variable, tuple(types), properties

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
