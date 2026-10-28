# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for frozen query AST nodes."""

import dataclasses

import pytest

from pygrafito.engine.query.ast import (
    Binary,
    Case,
    CaseBranch,
    CompoundStatement,
    Create,
    Delete,
    EdgeDirection,
    FunctionCall,
    IsNull,
    LabelAssignment,
    LabelRemoval,
    ListAccess,
    ListComprehension,
    ListLiteral,
    ListSlice,
    Literal,
    MapEntry,
    MapLiteral,
    Match,
    Merge,
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
    SetOperation,
    SortItem,
    Star,
    Statement,
    Subquery,
    SubqueryKind,
    Unary,
    Unwind,
    Variable,
)
from pygrafito.engine.query.tokens import Span

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
            direction=EdgeDirection.OUTGOING,
        )
        path = PathPattern.simple(
            nodes=(node, NodePattern(variable="b")),
            relationships=(relationship,),
            variable="p",
        )
        assert path.nodes[0].labels == ("Program", "ISO")
        assert path.relationships[0].direction is EdgeDirection.OUTGOING

    def test_statement(self) -> None:
        statement = Statement(
            clauses=(
                Match(
                    patterns=(PathPattern.simple(nodes=(NodePattern(variable="n"),)),),
                    where=Literal(value=True),
                ),
                Return(
                    items=(ReturnItem(expression=Variable(name="n"), text="n"),),
                    distinct=True,
                    order_by=(SortItem(expression=Variable(name="n"), descending=True),),
                    skip=Literal(value=1),
                    limit=Literal(value=2),
                ),
            )
        )
        returned = statement.clauses[1]
        assert isinstance(returned, Return)
        assert returned.distinct
        assert returned.order_by[0].descending

    def test_expression_surface_nodes(self) -> None:
        case = Case(
            operand=Variable(name="n"),
            branches=(CaseBranch(match=Literal(value=36), result=Literal(value="old")),),
            default=Literal(value="new"),
        )
        map_literal = MapLiteral(
            entries=(MapEntry(key="designation", value=Literal(value="Tron")),)
        )
        access = ListAccess(target=ListLiteral(items=()), index=Literal(value=0))
        slice_ = ListSlice(target=ListLiteral(items=()), start=None, end=Literal(value=1))
        comprehension = ListComprehension(
            variable="x",
            source=ListLiteral(items=(Literal(value=1),)),
        )
        subquery = Subquery(kind=SubqueryKind.EXISTS, clauses=())
        assert case.default is not None
        assert map_literal.entries[0].key == "designation"
        assert isinstance(access.index, Literal)
        assert slice_.end is not None
        assert comprehension.projection is None
        assert subquery.kind is SubqueryKind.EXISTS

    def test_compound_statement_nodes(self) -> None:
        term = Statement(clauses=(Return(items=(ReturnItem(expression=Literal(value=1)),)),))
        compound = CompoundStatement(
            clauses=(),
            terms=(term, term),
            operators=(SetOperation.UNION_ALL,),
            order_by=(SortItem(expression=Variable(name="value")),),
        )
        assert len(compound.terms) == 2
        assert compound.operators == (SetOperation.UNION_ALL,)

    def test_unwind_and_merge_fields(self) -> None:
        unwind = Unwind(expression=ListLiteral(items=()), variable="value")
        merge = Merge(
            pattern=PathPattern.simple(nodes=(NodePattern(variable="n"),)),
            on_create=Set(
                assignments=(PropertyAssignment(variable="n", key="k", value=Literal(value=1)),)
            ),
        )
        assert unwind.variable == "value"
        assert merge.on_create is not None
        assert merge.on_match is None

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
            PathPattern.simple(nodes=(NodePattern(),)),
            ReturnItem(expression=Literal(value=1)),
            SortItem(expression=Literal(value=1)),
            Match(patterns=(PathPattern.simple(nodes=(NodePattern(),)),)),
            Create(pattern=PathPattern.simple(nodes=(NodePattern(),))),
            Set(
                assignments=(PropertyAssignment(variable="n", key="k", value=Literal(value=1)),),
                labels=(LabelAssignment(variable="n", labels=("Program",)),),
            ),
            Remove(
                properties=(PropertyRemoval(variable="n", key="k"),),
                labels=(LabelRemoval(variable="n", labels=("Program",)),),
            ),
            Delete(variables=("n",)),
            Return(items=(ReturnItem(expression=Literal(value=1)),)),
            Statement(clauses=(Delete(variables=("n",)),)),
            Unwind(
                expression=ListLiteral(items=(Literal(value=1),)),
                variable="value",
            ),
            Merge(pattern=PathPattern.simple(nodes=(NodePattern(variable="n"),))),
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
