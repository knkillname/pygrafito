# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for query values, functions, and expression evaluation."""

import typing

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
from pygrafito.engine.query.values import (
    Aggregates,
    ArgumentKind,
    Arithmetic,
    Comparisons,
    ExpressionEvaluator,
    FunctionCatalog,
    ScalarFunctions,
    SnapshotSource,
    ValueKey,
    Values,
)
from pygrafito.model import (
    Node,
    Path,
    QueryExecutionError,
    QuerySemanticError,
    Relationship,
)


class _Source(SnapshotSource):
    """Provide fixed TRON snapshots for function tests."""

    def __init__(self) -> None:
        self.nodes = {
            1: Node(id=1, labels=frozenset({"Program"}), properties={"designation": "Quorra"}),
            2: Node(id=2, labels=frozenset({"Program", "ISO"}), properties={"cycles": 36}),
        }
        self.relationships = {
            1: Relationship(
                id=1,
                start_id=1,
                end_id=2,
                labels=("ALLIES_WITH",),
                properties={"since_cycle": 2020},
            ),
        }

    @typing.override
    def node(self, node_id: int) -> Node:
        return self.nodes[node_id]

    @typing.override
    def relationship(self, relationship_id: int) -> Relationship:
        return self.relationships[relationship_id]


class TestValues:
    """Verify dialect equality, ordering, and canonical keys."""

    def test_number_family_includes_integers_and_floats(self) -> None:
        assert Values.is_number(36)
        assert Values.is_number(36.0)
        assert not Values.is_number(True)

    def test_numeric_equality_across_types(self) -> None:
        assert Values.equals(36, 36.0) is True
        assert Values.equals(36, 37) is False

    def test_booleans_are_not_numbers(self) -> None:
        assert Values.equals(True, 1) is False
        assert Values.equals(False, 0) is False
        assert Values.equals(True, True) is True

    def test_null_propagates(self) -> None:
        assert Values.equals(None, 1) is None
        assert Values.equals(1, None) is None
        assert Values.equals(None, None) is None

    def test_strings_compare_case_sensitively(self) -> None:
        assert Values.equals("Quorra", "Quorra") is True
        assert Values.equals("Quorra", "quorra") is False

    def test_lists_compare_element_wise(self) -> None:
        assert Values.equals([1, 2], [1, 2]) is True
        assert Values.equals([1, 2], [2, 1]) is False
        assert Values.equals([1, 2], [1, 2, 3]) is False
        assert Values.equals([1, None], [1, 2]) is None

    def test_mappings_compare_by_keys_and_values(self) -> None:
        assert Values.equals({"a": 1}, {"a": 1}) is True
        assert Values.equals({"a": 1}, {"a": 2}) is False
        assert Values.equals({"a": 1}, {"b": 1}) is False
        assert Values.equals({"a": None}, {"a": None}) is None

    def test_entities_compare_by_id(self) -> None:
        first = Node(id=1)
        second = Node(id=1, labels=frozenset({"Program"}))
        other = Node(id=2)
        assert Values.equals(first, second) is True
        assert Values.equals(first, other) is False
        assert Values.equals(first, Relationship(1, 1, 2, labels=("TRUSTS",))) is False

    def test_relationships_compare_by_id(self) -> None:
        first = Relationship(1, 1, 2, labels=("TRUSTS",))
        second = Relationship(1, 1, 2, labels=("ALLIES_WITH",))
        assert Values.equals(first, second) is True
        assert Values.equals(first, Relationship(2, 1, 2, labels=("TRUSTS",))) is False

    def test_paths_compare_by_element_sequence(self) -> None:
        node_one = Node(id=1)
        node_two = Node(id=2)
        relationship = Relationship(1, 1, 2, labels=("TRUSTS",))
        first = Path(nodes=(node_one, node_two), relationships=(relationship,))
        second = Path(nodes=(node_one, node_two), relationships=(relationship,))
        reverse = Path(nodes=(node_two, node_one), relationships=(relationship,))
        assert Values.equals(first, second) is True
        assert Values.equals(first, reverse) is False
        assert Values.equals(first, node_one) is False

    def test_ordering_puts_null_last(self) -> None:
        ordered = sorted(
            [None, "a", 1, True, [1]],
            key=Values.ordering_key,
        )
        assert ordered == [True, 1, "a", [1], None]

    def test_ordering_rejects_unorderable_values(self) -> None:
        with pytest.raises(QueryExecutionError):
            Values.ordering_key(Node(id=1))
        with pytest.raises(QueryExecutionError):
            Values.ordering_key({"a": 1})

    def test_value_key_numeric_equality(self) -> None:
        assert ValueKey(36) == ValueKey(36.0)
        assert hash(ValueKey(36)) == hash(ValueKey(36.0))
        assert ValueKey(36) != ValueKey(37)

    def test_value_key_keeps_booleans_distinct(self) -> None:
        assert ValueKey(True) != ValueKey(1)
        assert ValueKey(False) != ValueKey(0)

    def test_value_key_for_containers_and_entities(self) -> None:
        node = Node(id=1)
        relationship = Relationship(1, 1, 2, labels=("TRUSTS",))
        path = Path(nodes=(node, Node(id=2)), relationships=(relationship,))
        assert ValueKey([1, 2]) == ValueKey([1, 2])
        assert ValueKey([1, 2]) != ValueKey([2, 1])
        assert ValueKey({"a": 1}) == ValueKey({"a": 1})
        assert ValueKey(node) == ValueKey(Node(id=1))
        assert ValueKey(relationship) == ValueKey(Relationship(1, 1, 2, labels=("TRUSTS",)))
        assert ValueKey(path) == ValueKey(path)
        assert "ValueKey" in repr(ValueKey(node))

    def test_value_key_is_not_equal_to_other_types(self) -> None:
        assert ValueKey(1) != 1

    def test_snapshot_source_defaults_are_abstract(self) -> None:
        source = SnapshotSource()
        with pytest.raises(NotImplementedError):
            source.node(1)
        with pytest.raises(NotImplementedError):
            source.relationship(1)


class TestFunctionCatalog:
    """Verify signatures, arity checks, and aggregate classification."""

    def test_lookup_is_case_insensitive(self) -> None:
        assert FunctionCatalog.spec("toInteger") is not None
        assert FunctionCatalog.spec("TOINTEGER") is not None
        assert FunctionCatalog.spec("missing") is None
        assert FunctionCatalog.canonical_name("ToInteger") == "tointeger"

    def test_arity_checks(self) -> None:
        spec = FunctionCatalog.spec("id")
        assert spec is not None
        assert spec.accepts_arity(1)
        assert not spec.accepts_arity(0)
        assert not spec.accepts_arity(2)

    def test_variadic_arity_and_kind(self) -> None:
        spec = FunctionCatalog.spec("concat")
        assert spec is not None
        assert spec.accepts_arity(3)
        assert not spec.accepts_arity(0)
        assert spec.kind_at(5) is ArgumentKind.STRING

    def test_aggregate_classification(self) -> None:
        assert FunctionCatalog.is_aggregate("COUNT")
        assert FunctionCatalog.is_aggregate("collect")
        assert not FunctionCatalog.is_aggregate("labels")


class TestScalarFunctions:
    """Verify every scalar function has success and edge behavior."""

    @pytest.fixture
    def functions(self) -> ScalarFunctions:
        return ScalarFunctions(_Source())

    def test_id(self, functions: ScalarFunctions) -> None:
        assert functions.call("id", [Node(id=3)]) == 3
        assert functions.call("id", [Relationship(4, 1, 2, labels=("TRUSTS",))]) == 4
        assert functions.call("id", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("id", [1])

    def test_labels(self, functions: ScalarFunctions) -> None:
        assert functions.call("labels", [Node(id=1, labels=frozenset({"Program", "ISO"}))]) == [
            "ISO",
            "Program",
        ]
        assert functions.call(
            "labels",
            [Relationship(1, 1, 2, labels=("TRUSTS", "ALLIES_WITH"))],
        ) == ["ALLIES_WITH", "TRUSTS"]
        assert functions.call("labels", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("labels", [1])

    def test_type(self, functions: ScalarFunctions) -> None:
        assert (
            functions.call("type", [Relationship(1, 1, 2, labels=("TRUSTS", "ALLIES_WITH"))])
            == "ALLIES_WITH"
        )
        assert functions.call("type", [Relationship(1, 1, 2)]) is None
        assert functions.call("type", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("type", [Node(id=1)])

    def test_properties(self, functions: ScalarFunctions) -> None:
        assert functions.call("properties", [Node(id=1, properties={"a": 1})]) == {"a": 1}
        assert functions.call(
            "properties",
            [Relationship(1, 1, 2, labels=("TRUSTS",), properties={"b": 2})],
        ) == {"b": 2}
        assert functions.call("properties", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("properties", [1])

    def test_keys(self, functions: ScalarFunctions) -> None:
        node = Node(id=1, properties={"b": 2, "a": 1})
        assert functions.call("keys", [node]) == ["a", "b"]
        assert functions.call("keys", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("keys", [1])

    def test_size(self, functions: ScalarFunctions) -> None:
        assert functions.call("size", [[1, 2]]) == 2
        assert functions.call("size", ["Quorra"]) == 6
        assert functions.call("size", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("size", [1])

    def test_coalesce(self, functions: ScalarFunctions) -> None:
        assert functions.call("coalesce", [None, None, "Quorra"]) == "Quorra"
        assert functions.call("coalesce", [None]) is None
        assert functions.call("coalesce", [1, 2]) == 1

    def test_to_integer(self, functions: ScalarFunctions) -> None:
        assert functions.call("toInteger", [36]) == 36
        assert functions.call("toInteger", [36.9]) == 36
        assert functions.call("toInteger", [-36.9]) == -36
        assert functions.call("toInteger", [" 36 "]) == 36
        assert functions.call("toInteger", [True]) == 1
        assert functions.call("toInteger", ["not a number"]) is None
        assert functions.call("toInteger", [None]) is None
        assert functions.call("toInteger", [[1]]) is None
        assert functions.call("toInteger", [1e300]) is None

    def test_to_float(self, functions: ScalarFunctions) -> None:
        assert functions.call("toFloat", [36]) == 36.0
        assert functions.call("toFloat", [36.5]) == 36.5
        assert functions.call("toFloat", [" 36.5 "]) == 36.5
        assert functions.call("toFloat", [True]) == 1.0
        assert functions.call("toFloat", ["nope"]) is None
        assert functions.call("toFloat", [None]) is None
        assert functions.call("toFloat", [[1]]) is None
        assert functions.call("toFloat", [10**400]) is None

    def test_to_string(self, functions: ScalarFunctions) -> None:
        assert functions.call("toString", ["Quorra"]) == "Quorra"
        assert functions.call("toString", [True]) == "true"
        assert functions.call("toString", [False]) == "false"
        assert functions.call("toString", [36]) == "36"
        assert functions.call("toString", [36.5]) == "36.5"
        assert functions.call("toString", [None]) is None
        assert functions.call("toString", [[1]]) is None

    def test_lower_upper_trim(self, functions: ScalarFunctions) -> None:
        assert functions.call("lower", ["Quorra"]) == "quorra"
        assert functions.call("upper", ["Quorra"]) == "QUORRA"
        assert functions.call("trim", ["  Quorra  "]) == "Quorra"
        for name in ("lower", "upper", "trim"):
            assert functions.call(name, [None]) is None
            with pytest.raises(QueryExecutionError):
                functions.call(name, [1])

    def test_abs(self, functions: ScalarFunctions) -> None:
        assert functions.call("abs", [-36]) == 36
        assert functions.call("abs", [-36.5]) == 36.5
        assert functions.call("abs", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("abs", ["x"])
        with pytest.raises(QueryExecutionError):
            functions.call("abs", [-(2**63)])

    def test_concat(self, functions: ScalarFunctions) -> None:
        assert functions.call("concat", ["Quorra", " ", "Flynn"]) == "Quorra Flynn"
        assert functions.call("concat", ["a", None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("concat", ["a", 1])

    def test_start_and_end_node(self, functions: ScalarFunctions) -> None:
        relationship = Relationship(1, 1, 2, labels=("TRUSTS",))
        start = functions.call("startNode", [relationship])
        end = functions.call("endNode", [relationship])
        assert isinstance(start, Node)
        assert isinstance(end, Node)
        assert start.id == 1
        assert end.id == 2
        assert functions.call("startNode", [None]) is None
        assert functions.call("endNode", [None]) is None
        with pytest.raises(QueryExecutionError):
            functions.call("startNode", [Node(id=1)])

    def test_unknown_function(self, functions: ScalarFunctions) -> None:
        with pytest.raises(QueryExecutionError):
            functions.call("mystery", [1])


class TestArithmetic:
    """Verify numeric promotion, overflow, and division errors."""

    def test_addition_and_subtraction(self) -> None:
        assert Arithmetic.operate(Operators.ADD, 1, 2) == 3
        assert Arithmetic.operate(Operators.ADD, 1, 2.5) == 3.5
        assert Arithmetic.operate(Operators.SUBTRACT, 5, 2) == 3
        assert Arithmetic.operate(Operators.ADD, None, 2) is None

    def test_multiplication(self) -> None:
        assert Arithmetic.operate(Operators.MULTIPLY, 3, 4) == 12
        assert Arithmetic.operate(Operators.MULTIPLY, 3, 4.0) == 12.0

    def test_division_always_returns_float(self) -> None:
        assert Arithmetic.operate(Operators.DIVIDE, 6, 2) == 3.0
        assert isinstance(Arithmetic.operate(Operators.DIVIDE, 6, 2), float)

    def test_modulo(self) -> None:
        assert Arithmetic.operate(Operators.MODULO, 7, 4) == 3
        assert Arithmetic.operate(Operators.MODULO, 7.5, 2) == 1.5

    def test_division_by_zero(self) -> None:
        for operator in (Operators.DIVIDE, Operators.MODULO):
            with pytest.raises(QueryExecutionError):
                Arithmetic.operate(operator, 1, 0)

    def test_integer_overflow(self) -> None:
        limit = 2**63 - 1
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate(Operators.ADD, limit, 1)
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate(Operators.SUBTRACT, -limit - 1, 1)
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate(Operators.MULTIPLY, 2**40, 2**40)

    def test_unary_operators(self) -> None:
        assert Arithmetic.negate(36) == -36
        assert Arithmetic.positive(36) == 36
        assert Arithmetic.negate(None) is None
        with pytest.raises(QueryExecutionError):
            Arithmetic.negate(-(2**63))
        with pytest.raises(QueryExecutionError):
            Arithmetic.negate("x")
        with pytest.raises(QueryExecutionError):
            Arithmetic.positive("x")

    def test_non_numeric_operands(self) -> None:
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate(Operators.ADD, True, 1)
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate(Operators.ADD, "1", 2)
        with pytest.raises(QueryExecutionError):
            Arithmetic.operate("??", 1, 2)


class TestComparisons:
    """Verify comparison operators and their null behavior."""

    def test_equality_and_inequality(self) -> None:
        assert Comparisons.compare(Operators.EQUAL, 1, 1.0) is True
        assert Comparisons.compare(Operators.NOT_EQUAL, 1, 2) is True
        assert Comparisons.compare(Operators.EQUAL, None, 1) is None
        assert Comparisons.compare(Operators.NOT_EQUAL, None, 1) is None

    def test_ordering_comparisons(self) -> None:
        assert Comparisons.compare(Operators.LESS, 1, 2) is True
        assert Comparisons.compare(Operators.LESS_EQUAL, 2, 2) is True
        assert Comparisons.compare(Operators.GREATER, 3, 2) is True
        assert Comparisons.compare(Operators.GREATER_EQUAL, 2, 3) is False
        assert Comparisons.compare(Operators.LESS, "a", "b") is True
        assert Comparisons.compare(Operators.LESS, [1], [2]) is True
        assert Comparisons.compare(Operators.LESS, None, 1) is None

    def test_unorderable_values(self) -> None:
        with pytest.raises(QueryExecutionError):
            Comparisons.compare(Operators.LESS, Node(id=1), Node(id=2))

    def test_unknown_comparison(self) -> None:
        with pytest.raises(QueryExecutionError):
            Comparisons.compare("MATCHES", 1, 2)


class TestExpressionEvaluator:
    """Verify evaluation over bindings and parameters."""

    @pytest.fixture
    def evaluator(self) -> ExpressionEvaluator:
        return ExpressionEvaluator(ScalarFunctions(_Source()))

    @staticmethod
    def binary(
        operator: str,
        left: bool | int | float | str | None,
        right: bool | int | float | str | None,
    ) -> Binary:
        return Binary(
            left=Literal(value=left),
            operator=operator,
            right=Literal(value=right),
        )

    def test_literals_and_lists(self, evaluator: ExpressionEvaluator) -> None:
        assert evaluator.evaluate(Literal(value=36), {}, {}) == 36
        assert evaluator.evaluate(
            ListLiteral(items=(Literal(value=1), Literal(value=2))),
            {},
            {},
        ) == [1, 2]

    def test_variables_and_parameters(self, evaluator: ExpressionEvaluator) -> None:
        binding = {"n": Node(id=1)}
        value = evaluator.evaluate(Variable(name="n"), binding, {})
        assert isinstance(value, Node)
        assert value.id == 1
        assert evaluator.evaluate(Parameter(name="p"), {}, {"p": 36}) == 36

    def test_unbound_variable_and_missing_parameter(self, evaluator: ExpressionEvaluator) -> None:
        with pytest.raises(QuerySemanticError):
            evaluator.evaluate(Variable(name="n"), {}, {})
        with pytest.raises(QuerySemanticError):
            evaluator.evaluate(Parameter(name="p"), {}, {})

    def test_property_access(self, evaluator: ExpressionEvaluator) -> None:
        node = Node(id=1, properties={"designation": "Quorra", "a.b": 1})
        binding = {"n": node, "m": {"key": 2}}
        assert (
            evaluator.evaluate(
                Property(target=Variable(name="n"), key="designation"),
                binding,
                {},
            )
            == "Quorra"
        )
        assert (
            evaluator.evaluate(
                Property(target=Variable(name="n"), key="a.b"),
                binding,
                {},
            )
            == 1
        )
        assert (
            evaluator.evaluate(
                Property(target=Variable(name="n"), key="missing"),
                binding,
                {},
            )
            is None
        )
        assert (
            evaluator.evaluate(
                Property(target=Variable(name="m"), key="key"),
                binding,
                {},
            )
            == 2
        )
        assert (
            evaluator.evaluate(
                Property(target=Literal(value=None), key="key"),
                {},
                {},
            )
            is None
        )
        assert evaluator.apply_property(Node(id=1, properties={"x": 1}), "x") == 1
        assert evaluator.apply_property({"x": 1}, "x") == 1
        assert evaluator.apply_property(None, "x") is None
        with pytest.raises(QueryExecutionError):
            evaluator.evaluate(Property(target=Literal(value=1), key="x"), {}, {})

    def test_function_calls(self, evaluator: ExpressionEvaluator) -> None:
        call = FunctionCall(name="size", arguments=(ListLiteral(items=(Literal(value=1),)),))
        assert evaluator.evaluate(call, {}, {}) == 1
        aggregate = FunctionCall(name="count", arguments=(Literal(value=1),))
        with pytest.raises(QuerySemanticError):
            evaluator.evaluate(aggregate, {}, {})

    def test_unary_operators(self, evaluator: ExpressionEvaluator) -> None:
        assert (
            evaluator.evaluate(
                Unary(operator=Operators.NOT, operand=Literal(value=False)),
                {},
                {},
            )
            is True
        )
        assert (
            evaluator.evaluate(
                Unary(operator=Operators.NOT, operand=Literal(value=None)),
                {},
                {},
            )
            is None
        )
        assert (
            evaluator.evaluate(
                Unary(operator=Operators.NEGATE, operand=Literal(value=3)),
                {},
                {},
            )
            == -3
        )
        assert (
            evaluator.evaluate(
                Unary(operator=Operators.POSITIVE, operand=Literal(value=3)),
                {},
                {},
            )
            == 3
        )
        with pytest.raises(QueryExecutionError):
            evaluator.apply_unary("??", 1)

    def test_boolean_logic(self, evaluator: ExpressionEvaluator) -> None:
        assert evaluator.evaluate(self.binary(Operators.AND, True, True), {}, {}) is True
        assert evaluator.evaluate(self.binary(Operators.AND, False, None), {}, {}) is False
        assert evaluator.evaluate(self.binary(Operators.AND, True, None), {}, {}) is None
        assert evaluator.evaluate(self.binary(Operators.OR, True, None), {}, {}) is True
        assert evaluator.evaluate(self.binary(Operators.OR, False, None), {}, {}) is None
        assert evaluator.evaluate(self.binary(Operators.OR, False, False), {}, {}) is False
        assert evaluator.apply_binary(Operators.AND, None, True) is None
        assert evaluator.apply_binary(Operators.OR, None, False) is None
        with pytest.raises(QueryExecutionError):
            evaluator.evaluate(self.binary(Operators.AND, 1, True), {}, {})

    def test_membership(self, evaluator: ExpressionEvaluator) -> None:
        items = ListLiteral(items=(Literal(value="Quorra"), Literal(value="Tron")))
        expression = Binary(
            left=Literal(value="Tron"),
            operator=Operators.IN,
            right=items,
        )
        assert evaluator.evaluate(expression, {}, {}) is True
        missing = Binary(
            left=Literal(value="Clu"),
            operator=Operators.IN,
            right=items,
        )
        assert evaluator.evaluate(missing, {}, {}) is False
        empty = Binary(
            left=Literal(value="Clu"),
            operator=Operators.IN,
            right=ListLiteral(items=()),
        )
        assert evaluator.evaluate(empty, {}, {}) is False
        null_value = Binary(
            left=Literal(value=None),
            operator=Operators.IN,
            right=items,
        )
        assert evaluator.evaluate(null_value, {}, {}) is None
        null_item = Binary(
            left=Literal(value="Clu"),
            operator=Operators.IN,
            right=ListLiteral(items=(Literal(value=None),)),
        )
        assert evaluator.evaluate(null_item, {}, {}) is None
        not_a_list = Binary(
            left=Literal(value=1),
            operator=Operators.IN,
            right=Literal(value=2),
        )
        with pytest.raises(QueryExecutionError):
            evaluator.evaluate(not_a_list, {}, {})

    def test_string_predicates(self, evaluator: ExpressionEvaluator) -> None:
        assert (
            evaluator.evaluate(
                self.binary(Operators.STARTS_WITH, "Quorra", "Qu"),
                {},
                {},
            )
            is True
        )
        assert (
            evaluator.evaluate(
                self.binary(Operators.ENDS_WITH, "Quorra", "ra"),
                {},
                {},
            )
            is True
        )
        assert (
            evaluator.evaluate(
                self.binary(Operators.CONTAINS, "Quorra", "orr"),
                {},
                {},
            )
            is True
        )
        assert (
            evaluator.evaluate(
                self.binary(Operators.CONTAINS, "Quorra", "ORR"),
                {},
                {},
            )
            is False
        )
        assert (
            evaluator.evaluate(
                self.binary(Operators.STARTS_WITH, None, "Qu"),
                {},
                {},
            )
            is None
        )
        with pytest.raises(QueryExecutionError):
            evaluator.evaluate(self.binary(Operators.STARTS_WITH, 1, "Qu"), {}, {})

    def test_null_tests(self, evaluator: ExpressionEvaluator) -> None:
        assert evaluator.evaluate(IsNull(operand=Literal(value=None)), {}, {}) is True
        assert evaluator.evaluate(IsNull(operand=Literal(value=1)), {}, {}) is False
        assert (
            evaluator.evaluate(
                IsNull(operand=Literal(value=None), negated=True),
                {},
                {},
            )
            is False
        )
        assert (
            evaluator.evaluate(
                IsNull(operand=Literal(value=1), negated=True),
                {},
                {},
            )
            is True
        )
        assert evaluator.apply_is_null(None, False)
        assert not evaluator.apply_is_null(1, False)

    def test_star_cannot_be_evaluated(self, evaluator: ExpressionEvaluator) -> None:
        with pytest.raises((QueryExecutionError, QuerySemanticError)):
            evaluator.evaluate(Star(), {}, {})


class TestAggregates:
    """Verify aggregate computation, grouping inputs, and empty semantics."""

    def test_count_rows(self) -> None:
        assert Aggregates.count_rows(10) == 10
        assert Aggregates.count_rows(0) == 0

    def test_count_skips_nulls(self) -> None:
        assert Aggregates.compute("count", [1, None, 2]) == 2

    def test_collect_skips_nulls_and_preserves_order(self) -> None:
        assert Aggregates.compute("collect", ["Quorra", None, "Tron"]) == [
            "Quorra",
            "Tron",
        ]

    def test_distinct_variants(self) -> None:
        assert Aggregates.compute("collect", [1, 1.0, 2], distinct=True) == [1, 2]
        assert Aggregates.compute("count", [1, 1.0, 2], distinct=True) == 2

    def test_sum(self) -> None:
        assert Aggregates.compute("sum", []) == 0
        assert Aggregates.compute("sum", [1, 2, 3]) == 6
        assert Aggregates.compute("sum", [1, 2.5]) == 3.5
        assert Aggregates.compute("sum", [1, None]) == 1
        with pytest.raises(QueryExecutionError):
            Aggregates.compute("sum", [1, "x"])
        with pytest.raises(QueryExecutionError):
            Aggregates.compute("sum", [2**62, 2**62])

    def test_avg(self) -> None:
        assert Aggregates.compute("avg", []) is None
        assert Aggregates.compute("avg", [1, 2, 3]) == 2.0
        assert Aggregates.compute("avg", [1, None, 3]) == 2.0
        with pytest.raises(QueryExecutionError):
            Aggregates.compute("avg", ["x"])

    def test_min_and_max(self) -> None:
        assert Aggregates.compute("min", []) is None
        assert Aggregates.compute("max", []) is None
        assert Aggregates.compute("min", [3, 1, 2]) == 1
        assert Aggregates.compute("max", [3, 1, 2]) == 3
        assert Aggregates.compute("min", [None, 3, 1]) == 1
        assert Aggregates.compute("max", ["a", "c", "b"]) == "c"

    def test_unknown_aggregate(self) -> None:
        with pytest.raises(QueryExecutionError):
            Aggregates.compute("median", [1, 2])
