# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Query values, equality, ordering, functions, and expression evaluation."""

import math
import typing
from collections.abc import Mapping, Sequence
from enum import Enum

from pygrafito.engine.query.ast import (
    Binary,
    Expression,
    FunctionCall,
    IsNull,
    ListLiteral,
    Literal,
    Operators,
    Parameter,
    Property,
    Unary,
    Variable,
)
from pygrafito.model import (
    Node,
    Path,
    QueryExecutionError,
    QuerySemanticError,
    Relationship,
)

type QueryValue = (
    None
    | bool
    | int
    | float
    | str
    | Sequence[QueryValue]
    | Mapping[str, QueryValue]
    | Node
    | Relationship
    | Path
)


class Values:
    """Operations shared by equality, distinctness, grouping, and ordering."""

    INTEGER_MIN: int = -(2**63)
    INTEGER_MAX: int = 2**63 - 1
    NULL_RANK: int = 4
    BOOLEAN_RANK: int = 0
    NUMBER_RANK: int = 1
    STRING_RANK: int = 2
    LIST_RANK: int = 3

    @classmethod
    def is_number(cls, value: QueryValue) -> bool:
        """Report whether a query value belongs to the numeric family.

        Parameters
        ----------
        value : QueryValue
            Value to classify.

        Returns
        -------
        bool
            ``True`` for integers and floats, but not booleans.
        """
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def equals(cls, left: QueryValue, right: QueryValue) -> bool | None:
        """Compare two query values with dialect equality.

        Parameters
        ----------
        left : QueryValue
            Left value.
        right : QueryValue
            Right value.

        Returns
        -------
        bool | None
            ``True`` or ``False`` for a definite comparison, or ``None`` when
            the comparison propagates null.
        """
        if left is None or right is None:
            return None
        if isinstance(left, Node) or isinstance(right, Node):
            return isinstance(left, Node) and isinstance(right, Node) and left.id == right.id
        if isinstance(left, Relationship) or isinstance(right, Relationship):
            return (
                isinstance(left, Relationship)
                and isinstance(right, Relationship)
                and left.id == right.id
            )
        if isinstance(left, Path) or isinstance(right, Path):
            if not isinstance(left, Path) or not isinstance(right, Path):
                return False
            return cls._paths_equal(left, right)
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left is right
        if cls.is_number(left) and cls.is_number(right):
            return left == right
        if isinstance(left, str) and isinstance(right, str):
            return left == right
        if isinstance(left, Sequence) and isinstance(right, Sequence):
            return cls._sequences_equal(left, right)
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            if set(left) != set(right):
                return False
            result: bool | None = True
            for key in left:
                comparison = cls.equals(left[key], right[key])
                if comparison is False:
                    return False
                if comparison is None:
                    result = None
            return result
        return False

    @classmethod
    def ordering_key(cls, value: QueryValue) -> tuple[object, ...]:
        """Build a total-order key for a query value.

        Parameters
        ----------
        value : QueryValue
            Value to order.

        Returns
        -------
        tuple[object, ...]
            Sortable key whose null rank sorts after every other value.

        Raises
        ------
        QueryExecutionError
            If the value has no defined order.
        """
        if value is None:
            return (cls.NULL_RANK, 0)
        if isinstance(value, bool):
            return (cls.BOOLEAN_RANK, int(value))
        if cls.is_number(value):
            return (cls.NUMBER_RANK, value)
        if isinstance(value, str):
            return (cls.STRING_RANK, value)
        if isinstance(value, Sequence):
            return (cls.LIST_RANK, tuple(cls.ordering_key(item) for item in value))
        message = f"{type(value).__name__} values cannot be ordered"
        raise QueryExecutionError(message)

    @classmethod
    def _sequences_equal(
        cls,
        left: Sequence[QueryValue],
        right: Sequence[QueryValue],
    ) -> bool | None:
        """Compare two sequences element-wise.

        Parameters
        ----------
        left : Sequence[QueryValue]
            Left sequence.
        right : Sequence[QueryValue]
            Right sequence.

        Returns
        -------
        bool | None
            Comparison result with null propagation.
        """
        if len(left) != len(right):
            return False
        result: bool | None = True
        for left_item, right_item in zip(left, right, strict=True):
            comparison = cls.equals(left_item, right_item)
            if comparison is False:
                return False
            if comparison is None:
                result = None
        return result

    @classmethod
    def _paths_equal(cls, left: Path, right: Path) -> bool:
        """Compare two paths by their node and relationship ids.

        Parameters
        ----------
        left : Path
            Left path.
        right : Path
            Right path.

        Returns
        -------
        bool
            ``True`` when both paths have the same sequence of elements.
        """
        left_nodes = tuple(node.id for node in left.nodes)
        right_nodes = tuple(node.id for node in right.nodes)
        left_relationships = tuple(item.id for item in left.relationships)
        right_relationships = tuple(item.id for item in right.relationships)
        return left_nodes == right_nodes and left_relationships == right_relationships


class ValueKey:
    """Canonical hashable key used for distinctness and grouping.

    Parameters
    ----------
    value : QueryValue
        Value to canonicalize.
    """

    __slots__ = ("_key",)

    def __init__(self, value: QueryValue) -> None:
        self._key = self._canonical(value)

    @typing.override
    def __hash__(self) -> int:
        """Return the hash of the canonical key.

        Returns
        -------
        int
            Hash of the canonical representation.
        """
        return hash(self._key)

    @typing.override
    def __eq__(self, other: object) -> bool:
        """Compare canonical keys.

        Parameters
        ----------
        other : object
            Candidate key.

        Returns
        -------
        bool
            ``True`` when both keys canonicalize to the same value.
        """
        if not isinstance(other, ValueKey):
            return NotImplemented
        return self._key == other._key

    @typing.override
    def __repr__(self) -> str:
        """Return a debugging representation.

        Returns
        -------
        str
            Representation of the canonical key.
        """
        return f"ValueKey({self._key!r})"

    @classmethod
    def _canonical(cls, value: QueryValue) -> tuple[object, ...]:
        """Build the tagged canonical representation of a value.

        Parameters
        ----------
        value : QueryValue
            Value to canonicalize.

        Returns
        -------
        tuple[object, ...]
            Hashable canonical representation.
        """
        if value is None:
            return ("null",)
        if isinstance(value, Node):
            return ("node", value.id)
        if isinstance(value, Relationship):
            return ("relationship", value.id)
        if isinstance(value, Path):
            return (
                "path",
                tuple(node.id for node in value.nodes),
                tuple(item.id for item in value.relationships),
            )
        if isinstance(value, bool):
            return ("boolean", value)
        if cls._is_number(value):
            return ("number", value)
        if isinstance(value, str):
            return ("string", value)
        if isinstance(value, Sequence):
            return ("list", tuple(cls._canonical(item) for item in value))
        if isinstance(value, Mapping):
            return (
                "map",
                tuple(sorted((key, cls._canonical(item)) for key, item in value.items())),
            )
        return ("unknown", repr(value))

    @classmethod
    def _is_number(cls, value: QueryValue) -> bool:
        """Report whether a value is a non-boolean number.

        Parameters
        ----------
        value : QueryValue
            Value to classify.

        Returns
        -------
        bool
            ``True`` for integers and floats.
        """
        return isinstance(value, (int, float)) and not isinstance(value, bool)


class ArgumentKind(Enum):
    """Expected static kind of one function argument."""

    ANY = "any"
    BOOLEAN = "boolean"
    NODE = "node"
    RELATIONSHIP = "relationship"
    ENTITY = "entity"
    STRING = "string"
    NUMBER = "number"
    LIST = "list"
    MAP = "map"
    PATH = "path"


class FunctionSpec:
    """Static signature of one scalar or aggregate function.

    Parameters
    ----------
    name : str
        Lowercase function name.
    minimum_arguments : int
        Smallest accepted argument count.
    maximum_arguments : int | None
        Largest accepted argument count, or ``None`` for variadic calls.
    kinds : tuple[ArgumentKind, ...]
        Expected kind per position; the final entry repeats for variadic calls.
    """

    __slots__ = ("kinds", "maximum_arguments", "minimum_arguments", "name")

    def __init__(
        self,
        name: str,
        minimum_arguments: int,
        maximum_arguments: int | None,
        kinds: tuple[ArgumentKind, ...],
    ) -> None:
        self.name = name
        self.minimum_arguments = minimum_arguments
        self.maximum_arguments = maximum_arguments
        self.kinds = kinds

    def accepts_arity(self, count: int) -> bool:
        """Report whether an argument count is accepted.

        Parameters
        ----------
        count : int
            Number of arguments.

        Returns
        -------
        bool
            ``True`` when the count is within the signature.
        """
        if count < self.minimum_arguments:
            return False
        return self.maximum_arguments is None or count <= self.maximum_arguments

    def kind_at(self, index: int) -> ArgumentKind:
        """Return the expected kind of one argument position.

        Parameters
        ----------
        index : int
            Zero-based argument position.

        Returns
        -------
        ArgumentKind
            Expected kind.
        """
        if index < len(self.kinds):
            return self.kinds[index]
        return self.kinds[-1]


class FunctionCatalog:
    """Registry of the dialect's scalar and aggregate functions."""

    AGGREGATES: frozenset[str] = frozenset({"count", "collect", "sum", "avg", "min", "max"})
    SPECS: typing.ClassVar[Mapping[str, FunctionSpec]] = {
        "id": FunctionSpec("id", 1, 1, (ArgumentKind.ENTITY,)),
        "labels": FunctionSpec("labels", 1, 1, (ArgumentKind.NODE,)),
        "type": FunctionSpec("type", 1, 1, (ArgumentKind.RELATIONSHIP,)),
        "properties": FunctionSpec("properties", 1, 1, (ArgumentKind.ENTITY,)),
        "keys": FunctionSpec("keys", 1, 1, (ArgumentKind.ENTITY,)),
        "size": FunctionSpec("size", 1, 1, (ArgumentKind.ANY,)),
        "coalesce": FunctionSpec("coalesce", 1, None, (ArgumentKind.ANY,)),
        "tointeger": FunctionSpec("tointeger", 1, 1, (ArgumentKind.ANY,)),
        "tofloat": FunctionSpec("tofloat", 1, 1, (ArgumentKind.ANY,)),
        "tostring": FunctionSpec("tostring", 1, 1, (ArgumentKind.ANY,)),
        "lower": FunctionSpec("lower", 1, 1, (ArgumentKind.STRING,)),
        "upper": FunctionSpec("upper", 1, 1, (ArgumentKind.STRING,)),
        "trim": FunctionSpec("trim", 1, 1, (ArgumentKind.STRING,)),
        "abs": FunctionSpec("abs", 1, 1, (ArgumentKind.NUMBER,)),
        "concat": FunctionSpec("concat", 1, None, (ArgumentKind.STRING,)),
        "startnode": FunctionSpec("startnode", 1, 1, (ArgumentKind.RELATIONSHIP,)),
        "endnode": FunctionSpec("endnode", 1, 1, (ArgumentKind.RELATIONSHIP,)),
        "count": FunctionSpec("count", 1, 1, (ArgumentKind.ANY,)),
        "collect": FunctionSpec("collect", 1, 1, (ArgumentKind.ANY,)),
        "sum": FunctionSpec("sum", 1, 1, (ArgumentKind.NUMBER,)),
        "avg": FunctionSpec("avg", 1, 1, (ArgumentKind.NUMBER,)),
        "min": FunctionSpec("min", 1, 1, (ArgumentKind.ANY,)),
        "max": FunctionSpec("max", 1, 1, (ArgumentKind.ANY,)),
    }

    @classmethod
    def spec(cls, name: str) -> FunctionSpec | None:
        """Resolve a case-insensitive function name.

        Parameters
        ----------
        name : str
            Function name as written.

        Returns
        -------
        FunctionSpec | None
            Registered signature, or ``None`` for an unknown function.
        """
        return cls.SPECS.get(name.lower())

    @classmethod
    def canonical_name(cls, name: str) -> str:
        """Return the canonical lowercase name of a function.

        Parameters
        ----------
        name : str
            Function name as written.

        Returns
        -------
        str
            Lowercase function name.
        """
        return name.lower()

    @classmethod
    def is_aggregate(cls, name: str) -> bool:
        """Report whether a function is an aggregate.

        Parameters
        ----------
        name : str
            Function name.

        Returns
        -------
        bool
            ``True`` for an aggregate function.
        """
        return name.lower() in cls.AGGREGATES


class SnapshotSource:
    """Provide element snapshots to functions that need related nodes."""

    def node(self, node_id: int) -> Node:
        """Read a node snapshot by id.

        Parameters
        ----------
        node_id : int
            Identifier of the node.

        Returns
        -------
        Node
            Node snapshot.
        """
        raise NotImplementedError

    def relationship(self, relationship_id: int) -> Relationship:
        """Read a relationship snapshot by id.

        Parameters
        ----------
        relationship_id : int
            Identifier of the relationship.

        Returns
        -------
        Relationship
            Relationship snapshot.
        """
        raise NotImplementedError


class Arithmetic:
    """Implement numeric operators with the dialect's promotion and errors."""

    INTEGER_MIN: int = -(2**63)
    INTEGER_MAX: int = 2**63 - 1

    @classmethod
    def operate(cls, operator: str, left: QueryValue, right: QueryValue) -> QueryValue:
        """Apply one binary arithmetic operator.

        Parameters
        ----------
        operator : str
            Arithmetic operator spelling.
        left : QueryValue
            Left operand.
        right : QueryValue
            Right operand.

        Returns
        -------
        QueryValue
            Arithmetic result, or ``None`` when an operand is null.

        Raises
        ------
        QueryExecutionError
            If an operand is not numeric, a division has a zero divisor, or an
            integer result overflows the signed 64-bit range.
        """
        if left is None or right is None:
            return None
        if not Values.is_number(left) or not Values.is_number(right):
            message = f"operator {operator!r} requires numeric operands"
            raise QueryExecutionError(message)
        number_left = typing.cast(int | float, left)
        number_right = typing.cast(int | float, right)
        if operator == Operators.ADD:
            return cls._add(number_left, number_right)
        if operator == Operators.SUBTRACT:
            return cls._subtract(number_left, number_right)
        if operator == Operators.MULTIPLY:
            return cls._multiply(number_left, number_right)
        if operator == Operators.DIVIDE:
            return cls._divide(number_left, number_right)
        if operator == Operators.MODULO:
            return cls._modulo(number_left, number_right)
        message = f"unsupported arithmetic operator {operator!r}"
        raise QueryExecutionError(message)

    @classmethod
    def negate(cls, value: QueryValue) -> QueryValue:
        """Apply unary minus.

        Parameters
        ----------
        value : QueryValue
            Operand value.

        Returns
        -------
        QueryValue
            Negated number, or ``None`` for null.

        Raises
        ------
        QueryExecutionError
            If the operand is not numeric or the result overflows.
        """
        if value is None:
            return None
        if not Values.is_number(value):
            message = "unary minus requires a numeric operand"
            raise QueryExecutionError(message)
        result = -typing.cast(int | float, value)
        cls._require_integer_range(result)
        return result

    @classmethod
    def positive(cls, value: QueryValue) -> QueryValue:
        """Apply unary plus.

        Parameters
        ----------
        value : QueryValue
            Operand value.

        Returns
        -------
        QueryValue
            The unchanged number, or ``None`` for null.

        Raises
        ------
        QueryExecutionError
            If the operand is not numeric.
        """
        if value is None:
            return None
        if not Values.is_number(value):
            message = "unary plus requires a numeric operand"
            raise QueryExecutionError(message)
        return value

    @classmethod
    def _add(cls, left: int | float, right: int | float) -> int | float:
        """Add two numbers.

        Parameters
        ----------
        left : int | float
            Left number.
        right : int | float
            Right number.

        Returns
        -------
        int | float
            Sum with integer overflow checking.
        """
        result = left + right
        cls._require_integer_range(result)
        return result

    @classmethod
    def _subtract(cls, left: int | float, right: int | float) -> int | float:
        """Subtract two numbers.

        Parameters
        ----------
        left : int | float
            Left number.
        right : int | float
            Right number.

        Returns
        -------
        int | float
            Difference with integer overflow checking.
        """
        result = left - right
        cls._require_integer_range(result)
        return result

    @classmethod
    def _multiply(cls, left: int | float, right: int | float) -> int | float:
        """Multiply two numbers.

        Parameters
        ----------
        left : int | float
            Left number.
        right : int | float
            Right number.

        Returns
        -------
        int | float
            Product with integer overflow checking.
        """
        result = left * right
        cls._require_integer_range(result)
        return result

    @classmethod
    def _divide(cls, left: int | float, right: int | float) -> float:
        """Divide two numbers as a float.

        Parameters
        ----------
        left : int | float
            Dividend.
        right : int | float
            Divisor.

        Returns
        -------
        float
            Floating-point quotient.

        Raises
        ------
        QueryExecutionError
            If the divisor is zero.
        """
        if right == 0:
            message = "division by zero"
            raise QueryExecutionError(message)
        return float(left) / float(right)

    @classmethod
    def _modulo(cls, left: int | float, right: int | float) -> int | float:
        """Compute the modulo of two numbers.

        Parameters
        ----------
        left : int | float
            Dividend.
        right : int | float
            Divisor.

        Returns
        -------
        int | float
            Remainder with the dividend's sign convention.

        Raises
        ------
        QueryExecutionError
            If the divisor is zero.
        """
        if right == 0:
            message = "division by zero"
            raise QueryExecutionError(message)
        result = left % right
        cls._require_integer_range(result)
        return result

    @classmethod
    def _require_integer_range(cls, result: int | float) -> None:
        """Reject an integer result outside the signed 64-bit range.

        Parameters
        ----------
        result : int | float
            Arithmetic result to validate.

        Raises
        ------
        QueryExecutionError
            If an integer result overflows.
        """
        if (
            isinstance(result, int)
            and not isinstance(result, bool)
            and not cls.INTEGER_MIN <= result <= cls.INTEGER_MAX
        ):
            message = "integer arithmetic overflowed the signed 64-bit range"
            raise QueryExecutionError(message)


class Comparisons:
    """Implement comparison operators over query values."""

    @classmethod
    def compare(cls, operator: str, left: QueryValue, right: QueryValue) -> bool | None:
        """Apply one comparison operator.

        Parameters
        ----------
        operator : str
            Comparison operator spelling.
        left : QueryValue
            Left operand.
        right : QueryValue
            Right operand.

        Returns
        -------
        bool | None
            Comparison result, or ``None`` when it propagates null.
        """
        if operator in {Operators.EQUAL, Operators.NOT_EQUAL}:
            equal = Values.equals(left, right)
            if equal is None or operator == Operators.EQUAL:
                return equal
            return not equal
        if left is None or right is None:
            return None
        left_key = Values.ordering_key(left)
        right_key = Values.ordering_key(right)
        if operator == Operators.LESS:
            return left_key < right_key
        if operator == Operators.LESS_EQUAL:
            return left_key <= right_key
        if operator == Operators.GREATER:
            return left_key > right_key
        if operator == Operators.GREATER_EQUAL:
            return left_key >= right_key
        message = f"unsupported comparison operator {operator!r}"
        raise QueryExecutionError(message)


class ScalarFunctions:
    """Evaluate the dialect's scalar functions.

    Parameters
    ----------
    source : SnapshotSource
        Source used by ``startNode`` and ``endNode``.
    """

    def __init__(self, source: SnapshotSource) -> None:
        self._source = source
        self._handlers: Mapping[str, typing.Callable[[Sequence[QueryValue]], QueryValue]] = {
            "id": self._id,
            "labels": self._labels,
            "type": self._type,
            "properties": self._properties,
            "keys": self._keys,
            "size": self._size,
            "coalesce": self._coalesce,
            "tointeger": self._to_integer,
            "tofloat": self._to_float,
            "tostring": self._to_string,
            "lower": self._lower,
            "upper": self._upper,
            "trim": self._trim,
            "abs": self._abs,
            "concat": self._concat,
            "startnode": self._start_node,
            "endnode": self._end_node,
        }

    def call(self, name: str, arguments: Sequence[QueryValue]) -> QueryValue:
        """Call a scalar function by name.

        Parameters
        ----------
        name : str
            Case-insensitive function name.
        arguments : Sequence[QueryValue]
            Evaluated arguments.

        Returns
        -------
        QueryValue
            Function result.

        Raises
        ------
        QueryExecutionError
            If the function is unknown or an argument has the wrong type.
        """
        handler = self._handlers.get(name.lower())
        if handler is None:
            message = f"unknown function {name!r}"
            raise QueryExecutionError(message)
        return handler(arguments)

    def _id(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the id of a node or relationship.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One entity argument.

        Returns
        -------
        QueryValue
            Entity id, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, (Node, Relationship)):
            return value.id
        return self._type_error("id", "a node or relationship", value)

    def _labels(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return a node's labels in sorted order.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One node argument.

        Returns
        -------
        QueryValue
            Sorted labels, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, Node):
            return typing.cast(QueryValue, sorted(value.labels))
        return self._type_error("labels", "a node", value)

    def _type(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return a relationship's stored type.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One relationship argument.

        Returns
        -------
        QueryValue
            Relationship type, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, Relationship):
            return value.rel_type
        return self._type_error("type", "a relationship", value)

    def _properties(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return an element's property mapping.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One entity argument.

        Returns
        -------
        QueryValue
            A new property mapping, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, (Node, Relationship)):
            return typing.cast(QueryValue, dict(value.properties))
        return self._type_error("properties", "a node or relationship", value)

    def _keys(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return an element's property keys in sorted order.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One entity argument.

        Returns
        -------
        QueryValue
            Sorted property keys, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, (Node, Relationship)):
            return typing.cast(QueryValue, sorted(value.properties))
        return self._type_error("keys", "a node or relationship", value)

    def _size(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the length of a list or string.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One list or string argument.

        Returns
        -------
        QueryValue
            Length, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, (list, str)):
            return len(value)
        return self._type_error("size", "a list or string", value)

    def _coalesce(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the first non-null argument.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            Candidate values.

        Returns
        -------
        QueryValue
            First non-null value, or null when every value is null.
        """
        for value in arguments:
            if value is not None:
                return value
        return None

    def _to_integer(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Convert a compatible scalar to an integer.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One scalar argument.

        Returns
        -------
        QueryValue
            Converted integer, or null when conversion is impossible.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                return None
            converted = math.trunc(value)
            if not Values.INTEGER_MIN <= converted <= Values.INTEGER_MAX:
                return None
            return converted
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    def _to_float(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Convert a compatible scalar to a float.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One scalar argument.

        Returns
        -------
        QueryValue
            Converted float, or null when conversion is impossible.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, bool):
            return float(value)
        if Values.is_number(value):
            try:
                converted = float(typing.cast(int | float, value))
            except OverflowError:
                return None
            return converted if math.isfinite(converted) else None
        if isinstance(value, str):
            try:
                converted = float(value.strip())
            except ValueError:
                return None
            return converted if math.isfinite(converted) else None
        return None

    def _to_string(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Convert a compatible scalar to a string.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One scalar argument.

        Returns
        -------
        QueryValue
            Converted string, or null when conversion is impossible.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(value)
        return None

    def _lower(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Lowercase a string.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One string argument.

        Returns
        -------
        QueryValue
            Lowercased string, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, str):
            return value.lower()
        return self._type_error("lower", "a string", value)

    def _upper(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Uppercase a string.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One string argument.

        Returns
        -------
        QueryValue
            Uppercased string, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, str):
            return value.upper()
        return self._type_error("upper", "a string", value)

    def _trim(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Trim whitespace around a string.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One string argument.

        Returns
        -------
        QueryValue
            Trimmed string, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return self._type_error("trim", "a string", value)

    def _abs(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the absolute value of a number.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One numeric argument.

        Returns
        -------
        QueryValue
            Absolute value, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if not Values.is_number(value):
            return self._type_error("abs", "a number", value)
        result = abs(typing.cast(int | float, value))
        if isinstance(result, int) and result > Values.INTEGER_MAX:
            message = "abs result overflows the signed 64-bit range"
            raise QueryExecutionError(message)
        return result

    def _concat(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Concatenate strings.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            String arguments.

        Returns
        -------
        QueryValue
            Concatenated string, or null when any argument is null.
        """
        pieces: list[str] = []
        for value in arguments:
            if value is None:
                return None
            if not isinstance(value, str):
                return self._type_error("concat", "strings", value)
            pieces.append(value)
        return "".join(pieces)

    def _start_node(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the node where a relationship starts.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One relationship argument.

        Returns
        -------
        QueryValue
            Start node snapshot, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, Relationship):
            return self._source.node(value.start_id)
        return self._type_error("startNode", "a relationship", value)

    def _end_node(self, arguments: Sequence[QueryValue]) -> QueryValue:
        """Return the node where a relationship ends.

        Parameters
        ----------
        arguments : Sequence[QueryValue]
            One relationship argument.

        Returns
        -------
        QueryValue
            End node snapshot, or null for a null argument.
        """
        value = arguments[0]
        if value is None:
            return None
        if isinstance(value, Relationship):
            return self._source.node(value.end_id)
        return self._type_error("endNode", "a relationship", value)

    @staticmethod
    def _type_error(function: str, expected: str, value: QueryValue) -> typing.Never:
        """Raise a query execution error for a bad argument type.

        Parameters
        ----------
        function : str
            Function name.
        expected : str
            Description of the expected argument.
        value : QueryValue
            Offending value.

        Raises
        ------
        QueryExecutionError
            Always.
        """
        message = f"{function}() expects {expected}; got {type(value).__name__}"
        raise QueryExecutionError(message)


class Aggregates:
    """Compute aggregate function results over one input group."""

    NAMES: frozenset[str] = frozenset({"count", "collect", "sum", "avg", "min", "max"})

    @classmethod
    def count_rows(cls, rows: int) -> int:
        """Return ``count(*)`` for a group.

        Parameters
        ----------
        rows : int
            Number of input rows.

        Returns
        -------
        int
            Row count.
        """
        return rows

    @classmethod
    def compute(
        cls,
        name: str,
        values: Sequence[QueryValue],
        *,
        distinct: bool = False,
    ) -> QueryValue:
        """Compute one aggregate over evaluated input values.

        Parameters
        ----------
        name : str
            Case-insensitive aggregate name.
        values : Sequence[QueryValue]
            Evaluated argument value per input row.
        distinct : bool, optional
            Whether to deduplicate inputs, by default ``False``.

        Returns
        -------
        QueryValue
            Aggregate result.

        Raises
        ------
        QueryExecutionError
            If an aggregate receives a non-numeric value or an integer sum
            overflows.
        """
        normalized = name.lower()
        filtered = [value for value in values if value is not None]
        if distinct:
            filtered = cls._distinct(filtered)
        if normalized == "count":
            return len(filtered)
        if normalized == "collect":
            return typing.cast(QueryValue, filtered)
        if normalized in {"sum", "avg"}:
            return cls._numeric(normalized, filtered)
        if normalized in {"min", "max"}:
            return cls._extreme(normalized, filtered)
        message = f"unknown aggregate function {name!r}"
        raise QueryExecutionError(message)

    @classmethod
    def _distinct(cls, values: Sequence[QueryValue]) -> list[QueryValue]:
        """Remove duplicate values by canonical key.

        Parameters
        ----------
        values : Sequence[QueryValue]
            Values to deduplicate.

        Returns
        -------
        list[QueryValue]
            Values in their original order without duplicates.
        """
        seen: set[ValueKey] = set()
        result: list[QueryValue] = []
        for value in values:
            key = ValueKey(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    @classmethod
    def _numeric(cls, name: str, values: Sequence[QueryValue]) -> QueryValue:
        """Compute ``sum`` or ``avg``.

        Parameters
        ----------
        name : str
            Either ``"sum"`` or ``"avg"``.
        values : Sequence[QueryValue]
            Non-null numeric inputs.

        Returns
        -------
        QueryValue
            Aggregate result; ``sum`` of empty input is zero.
        """
        total: int | float = 0
        for value in values:
            if not Values.is_number(value):
                message = f"{name}() requires numeric values"
                raise QueryExecutionError(message)
            total += typing.cast(int | float, value)
            if isinstance(total, int) and not Values.INTEGER_MIN <= total <= Values.INTEGER_MAX:
                message = "aggregate integer sum overflowed the signed 64-bit range"
                raise QueryExecutionError(message)
        if name == "sum":
            return total
        if not values:
            return None
        return float(total) / len(values)

    @classmethod
    def _extreme(cls, name: str, values: Sequence[QueryValue]) -> QueryValue:
        """Compute ``min`` or ``max``.

        Parameters
        ----------
        name : str
            Either ``"min"`` or ``"max"``.
        values : Sequence[QueryValue]
            Non-null inputs.

        Returns
        -------
        QueryValue
            Extreme value, or null for empty input.
        """
        if not values:
            return None
        choose = min if name == "min" else max
        return choose(values, key=Values.ordering_key)


class ExpressionEvaluator:
    """Evaluate scalar expressions against a variable binding.

    Parameters
    ----------
    functions : ScalarFunctions
        Scalar function implementation.
    """

    def __init__(self, functions: ScalarFunctions) -> None:
        self._functions = functions

    def evaluate(
        self,
        expression: Expression,
        binding: Mapping[str, QueryValue],
        parameters: Mapping[str, QueryValue],
    ) -> QueryValue:
        """Evaluate one expression.

        Parameters
        ----------
        expression : Expression
            Expression to evaluate.
        binding : Mapping[str, QueryValue]
            Variables bound by the pattern match.
        parameters : Mapping[str, QueryValue]
            Query parameter values.

        Returns
        -------
        QueryValue
            Evaluated value.
        """
        if isinstance(expression, Literal):
            return expression.value
        if isinstance(expression, ListLiteral):
            return [self.evaluate(item, binding, parameters) for item in expression.items]
        if isinstance(expression, Variable):
            if expression.name not in binding:
                message = f"variable {expression.name!r} is not bound"
                raise QuerySemanticError(message)
            return binding[expression.name]
        if isinstance(expression, Parameter):
            if expression.name not in parameters:
                message = f"missing query parameter ${expression.name}"
                raise QuerySemanticError(message)
            return parameters[expression.name]
        if isinstance(expression, Property):
            target = self.evaluate(expression.target, binding, parameters)
            return self.apply_property(target, expression.key)
        if isinstance(expression, FunctionCall):
            if FunctionCatalog.is_aggregate(expression.name):
                message = "aggregate functions are not valid in this position"
                raise QuerySemanticError(message)
            arguments = [self.evaluate(item, binding, parameters) for item in expression.arguments]
            return self._functions.call(expression.name, arguments)
        if isinstance(expression, Unary):
            return self.apply_unary(
                expression.operator,
                self.evaluate(expression.operand, binding, parameters),
            )
        if isinstance(expression, Binary):
            if expression.operator == Operators.AND:
                left = self.evaluate(expression.left, binding, parameters)
                if self._truth(left) is False:
                    return False
                return self.apply_binary(
                    expression.operator,
                    left,
                    self.evaluate(expression.right, binding, parameters),
                )
            if expression.operator == Operators.OR:
                left = self.evaluate(expression.left, binding, parameters)
                if self._truth(left) is True:
                    return True
                return self.apply_binary(
                    expression.operator,
                    left,
                    self.evaluate(expression.right, binding, parameters),
                )
            return self.apply_binary(
                expression.operator,
                self.evaluate(expression.left, binding, parameters),
                self.evaluate(expression.right, binding, parameters),
            )
        if isinstance(expression, IsNull):
            value = self.evaluate(expression.operand, binding, parameters)
            return self.apply_is_null(value, expression.negated)
        message = "cannot evaluate this expression form"
        raise QueryExecutionError(message)

    def apply_property(self, target: QueryValue, key: str) -> QueryValue:
        """Read one property from an already evaluated target.

        Parameters
        ----------
        target : QueryValue
            Node, relationship, mapping, or null.
        key : str
            Property key.

        Returns
        -------
        QueryValue
            Property value, or null when the target is null or lacks the key.
        """
        if target is None:
            return None
        if isinstance(target, (Node, Relationship)):
            return typing.cast(QueryValue | None, target.properties.get(key))
        if isinstance(target, Mapping):
            return target.get(key)
        message = f"cannot read property {key!r} from {type(target).__name__}"
        raise QueryExecutionError(message)

    def apply_unary(self, operator: str, operand: QueryValue) -> QueryValue:
        """Apply a prefix operator to an evaluated operand.

        Parameters
        ----------
        operator : str
            Unary operator spelling.
        operand : QueryValue
            Evaluated operand.

        Returns
        -------
        QueryValue
            Operator result.
        """
        if operator == Operators.NOT:
            truth = self._truth(operand)
            return None if truth is None else not truth
        if operator == Operators.NEGATE:
            return Arithmetic.negate(operand)
        if operator == Operators.POSITIVE:
            return Arithmetic.positive(operand)
        message = f"unsupported unary operator {operator!r}"
        raise QueryExecutionError(message)

    def apply_binary(self, operator: str, left: QueryValue, right: QueryValue) -> QueryValue:
        """Apply an infix operator to evaluated operands.

        Parameters
        ----------
        operator : str
            Operator spelling.
        left : QueryValue
            Evaluated left operand.
        right : QueryValue
            Evaluated right operand.

        Returns
        -------
        QueryValue
            Operator result.
        """
        if operator == Operators.AND:
            left_truth = self._truth(left)
            right_truth = self._truth(right)
            if left_truth is False or right_truth is False:
                return False
            if left_truth is None or right_truth is None:
                return None
            return True
        if operator == Operators.OR:
            left_truth = self._truth(left)
            right_truth = self._truth(right)
            if left_truth is True or right_truth is True:
                return True
            if left_truth is None or right_truth is None:
                return None
            return False
        if operator == Operators.IN:
            return self._membership(left, right)
        if operator in {
            Operators.EQUAL,
            Operators.NOT_EQUAL,
            Operators.LESS,
            Operators.LESS_EQUAL,
            Operators.GREATER,
            Operators.GREATER_EQUAL,
        }:
            return Comparisons.compare(operator, left, right)
        if operator in {
            Operators.STARTS_WITH,
            Operators.ENDS_WITH,
            Operators.CONTAINS,
        }:
            return self._string_predicate(operator, left, right)
        return Arithmetic.operate(operator, left, right)

    @staticmethod
    def apply_is_null(value: QueryValue, negated: bool) -> bool:
        """Apply an ``IS NULL`` or ``IS NOT NULL`` test.

        Parameters
        ----------
        value : QueryValue
            Evaluated operand.
        negated : bool
            Whether the test is ``IS NOT NULL``.

        Returns
        -------
        bool
            Test result.
        """
        return (value is not None) if negated else (value is None)

    def _membership(self, left: QueryValue, right: QueryValue) -> QueryValue:
        """Evaluate the ``IN`` operator.

        Parameters
        ----------
        left : QueryValue
            Candidate value.
        right : QueryValue
            List to search.

        Returns
        -------
        QueryValue
            Membership result with null propagation.
        """
        if left is None:
            return None
        if right is None:
            return None
        if not isinstance(right, list):
            message = "the right operand of IN must be a list"
            raise QueryExecutionError(message)
        result: bool | None = False
        for item in right:
            comparison = Values.equals(left, item)
            if comparison is True:
                return True
            if comparison is None:
                result = None
        return result

    def _string_predicate(
        self,
        operator: str,
        left: QueryValue,
        right: QueryValue,
    ) -> QueryValue:
        """Evaluate a case-sensitive string predicate.

        Parameters
        ----------
        operator : str
            Predicate spelling.
        left : QueryValue
            String being searched.
        right : QueryValue
            Prefix, suffix, or substring.

        Returns
        -------
        QueryValue
            Predicate result with null propagation.
        """
        if left is None or right is None:
            return None
        if not isinstance(left, str) or not isinstance(right, str):
            message = f"operator {operator!r} requires string operands"
            raise QueryExecutionError(message)
        if operator == Operators.STARTS_WITH:
            return left.startswith(right)
        if operator == Operators.ENDS_WITH:
            return left.endswith(right)
        return right in left

    @staticmethod
    def _truth(value: QueryValue) -> bool | None:
        """Interpret a predicate value as three-valued truth.

        Parameters
        ----------
        value : QueryValue
            Predicate value.

        Returns
        -------
        bool | None
            Boolean truth, or ``None`` for null.

        Raises
        ------
        QueryExecutionError
            If the value is not a boolean.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        message = f"predicate must be a boolean; got {type(value).__name__}"
        raise QueryExecutionError(message)


class PatternValueResolver:
    """Evaluate pattern property expressions against one input row.

    Parameters
    ----------
    evaluator : ExpressionEvaluator
        Scalar expression evaluator.
    parameters : Mapping[str, QueryValue]
        Query parameter values.
    lenient : bool, optional
        Whether an expression that cannot be evaluated without a row resolves
        to null, by default ``False``. Plan inspection uses the lenient mode.
    """

    def __init__(
        self,
        evaluator: ExpressionEvaluator,
        parameters: Mapping[str, QueryValue],
        *,
        lenient: bool = False,
    ) -> None:
        self._evaluator = evaluator
        self._parameters = parameters
        self._lenient = lenient

    def resolve(
        self,
        expression: Expression,
        binding: Mapping[str, QueryValue],
    ) -> QueryValue:
        """Evaluate one pattern property expression.

        Parameters
        ----------
        expression : Expression
            Expression to evaluate.
        binding : Mapping[str, QueryValue]
            Variables bound by earlier stages.

        Returns
        -------
        QueryValue
            Evaluated value, or null when lenient and the row cannot supply it.
        """
        try:
            return self._evaluator.evaluate(expression, binding, self._parameters)
        except QuerySemanticError:
            if self._lenient:
                return None
            raise


__all__ = [
    "Aggregates",
    "ArgumentKind",
    "Arithmetic",
    "Comparisons",
    "ExpressionEvaluator",
    "FunctionCatalog",
    "FunctionSpec",
    "PatternValueResolver",
    "QueryValue",
    "ScalarFunctions",
    "SnapshotSource",
    "ValueKey",
    "Values",
]
