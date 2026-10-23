# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for frozen query AST nodes."""

import dataclasses

import pytest

from pygrafito.engine.query.ast import (
    Binary,
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
from pygrafito.engine.query.tokens import Span
from pygrafito.model import Direction

SPAN = Span(line=1, column=1, offset=0, end=1)


class TestAstNodes:
    """Verify construction, equality, immutability, and slotted storage."""

    def test_literal(self) -> None:
        node = Literal(value=36)
        assert node.value == 36
        assert node == Literal(value=36)

    def test_list_literal(self) -> None:
        node = ListLiteral(items=(Literal(value=1), Literal(value=2)))
        second = node.items[1]
        assert isinstance(second, Literal)
        assert second.value == 2

    def test_variable_and_parameter(self) -> None:
        variable = Variable(name="n", span=SPAN)
        parameter = Parameter(name="cycles")
        assert variable.name == "n"
        assert parameter.name == "cycles"

    def test_property_access(self) -> None:
        node = Property(target=Variable(name="n"), key="a.b")
        assert node.key == "a.b"
        assert node.target == Variable(name="n")

    def test_function_call_with_star_and_distinct(self) -> None:
        call = FunctionCall(name="count", arguments=(Star(),))
        distinct = FunctionCall(
            name="count",
            arguments=(Variable(name="n"),),
            distinct=True,
        )
        assert isinstance(call.arguments[0], Star)
        assert distinct.distinct

    def test_unary_binary_is_null(self) -> None:
        unary = Unary(operator=Operators.NOT, operand=Literal(value=True))
        binary = Binary(
            left=Literal(value=1),
            operator=Operators.LESS,
            right=Literal(value=2),
        )
        is_null = IsNull(operand=Variable(name="n"), negated=True)
        assert isinstance(unary.operand, Literal)
        assert unary.operand.value is True
        assert binary.operator == "<"
        assert is_null.negated

    def test_patterns(self) -> None:
        node = NodePattern(
            variable="n",
            labels=("Program", "ISO"),
            properties=(PropertyEntry(key="designation", value=Literal(value="Quorra")),),
        )
        relationship = RelationshipPattern(
            variable="r",
            types=("ALLIES_WITH", "TRUSTS"),
            direction=Direction.OUTGOING,
        )
        path = PathPattern(
            nodes=(node, NodePattern(variable="b")),
            relationships=(relationship,),
            variable="p",
        )
        assert path.nodes[0].labels == ("Program", "ISO")
        assert path.relationships[0].direction is Direction.OUTGOING

    def test_statement(self) -> None:
        statement = Statement(
            pattern=PathPattern(nodes=(NodePattern(variable="n"),)),
            return_items=(ReturnItem(expression=Variable(name="n"), text="n"),),
            where=Literal(value=True),
            distinct=True,
            order_by=(SortItem(expression=Variable(name="n"), descending=True),),
            skip=Literal(value=1),
            limit=Literal(value=2),
        )
        assert statement.distinct
        assert statement.order_by[0].descending

    def test_every_node_is_frozen(self) -> None:
        nodes = [
            Literal(value=1),
            ListLiteral(items=()),
            Variable(name="n"),
            Parameter(name="p"),
            Property(target=Variable(name="n"), key="k"),
            FunctionCall(name="id", arguments=(Variable(name="n"),)),
            Unary(operator=Operators.NOT, operand=Literal(value=True)),
            Binary(
                left=Literal(value=1),
                operator=Operators.ADD,
                right=Literal(value=2),
            ),
            IsNull(operand=Literal(value=None)),
            Star(),
            NodePattern(),
            RelationshipPattern(),
            PathPattern(nodes=(NodePattern(),)),
            ReturnItem(expression=Literal(value=1)),
            SortItem(expression=Literal(value=1)),
        ]
        for node in nodes:
            assert not hasattr(node, "__dict__")
            fields = dataclasses.fields(node)
            if not fields:
                continue
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(node, fields[0].name, None)

    def test_equality_uses_all_fields(self) -> None:
        assert Variable(name="n") == Variable(name="n")
        assert Variable(name="n") != Variable(name="m")
        assert Literal(value="1") != Literal(value=1)
