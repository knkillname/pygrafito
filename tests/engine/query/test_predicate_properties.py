# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Property tests for quoted property predicates and type guards."""

import typing

import hypothesis
import hypothesis.strategies

from pygrafito import Graph
from pygrafito.engine.query.ast import Match
from pygrafito.engine.query.compiler import Compiler
from pygrafito.engine.query.parser import Parser
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import Value
from pygrafito.storage.codec import PropertyCodec


class TestPredicateProperties:
    """Exercise adversarial property keys through storage and query predicates."""

    KEY_ALPHABET: typing.ClassVar[str] = "abcXYZ019_\"'\\\n\t$.[]{}: ,éΩ☃"
    VALUE_ALPHABET: typing.ClassVar[str] = "abcXYZ019_\"'\\\n\t$.[]{}: ,éΩ☃"
    KEY: typing.ClassVar[hypothesis.strategies.SearchStrategy[str]] = hypothesis.strategies.text(
        alphabet=KEY_ALPHABET,
        min_size=1,
        max_size=8,
    )
    VALUE: typing.ClassVar[hypothesis.strategies.SearchStrategy[Value]] = typing.cast(
        hypothesis.strategies.SearchStrategy[Value],
        hypothesis.strategies.one_of(
            hypothesis.strategies.booleans(),
            hypothesis.strategies.integers(min_value=-(2**63), max_value=2**63 - 1),
            hypothesis.strategies.floats(allow_nan=False, allow_infinity=False),
            hypothesis.strategies.text(alphabet=VALUE_ALPHABET, max_size=12),
        ),
    )

    @classmethod
    def assert_find_matches(cls, key: str, value: Value, indexed: bool) -> None:
        """Find exactly the node that carries the generated key and value.

        Parameters
        ----------
        key : str
            Adversarial property key.
        value : object
            Valid scalar property value.
        indexed : bool
            Whether to declare an index on the key first.
        """
        with Graph.open(":memory:") as graph:
            if indexed:
                graph.create_node_index(key)
            graph.add_node("Program", **{key: value})
            graph.add_node("Program", **{f"{key}x": value})
            found = list(graph.find_nodes("Program", **{key: value}))
            assert len(found) == 1
            assert found[0][key] == value

    @hypothesis.given(key=KEY, value=VALUE)
    def test_find_nodes_without_index(self, key: str, value: Value) -> None:
        """Match a generated key through the unindexed storage predicate."""
        self.assert_find_matches(key, value, indexed=False)

    @hypothesis.given(key=KEY, value=VALUE)
    def test_find_nodes_with_index(self, key: str, value: Value) -> None:
        """Match a generated key through an expression index."""
        self.assert_find_matches(key, value, indexed=True)

    @hypothesis.given(key=KEY, value=VALUE)
    def test_gql_where_matches_generated_key(self, key: str, value: Value) -> None:
        """Match a generated key through the query compiler and executor."""
        quoted = "`" + key.replace("`", "``") + "`"
        with Graph.open(":memory:") as graph:
            graph.add_node("Program", **{key: value})
            result = graph.query(
                f"MATCH (n:Program) WHERE n.{quoted} = $value RETURN n",
                {"value": typing.cast(QueryValue, value)},
            )
        assert len(result.rows) == 1

    @hypothesis.given(key=KEY)
    def test_compiler_pairs_type_guard_and_path(self, key: str) -> None:
        """Compile a generated key with both the type guard and extraction."""
        quoted = "`" + key.replace("`", "``") + "`"
        statement = f"MATCH (n {{{quoted}: 'Tron'}}) RETURN n"
        parsed = Parser.parse_statement(statement)
        match = next(clause for clause in parsed.clauses if isinstance(clause, Match))
        compiled = Compiler(match).compile({})
        codec = PropertyCodec()
        type_expression = codec.property_type_expression("n0.props", key)
        value_expression = codec.property_value_expression("n0.props", key)
        assert f"{type_expression} = 'text'" in compiled.sql
        assert f"{value_expression} = ?" in compiled.sql
        assert compiled.arguments == ("Tron",)

    @hypothesis.given(key=KEY)
    def test_boolean_and_numeric_values_do_not_conflate(self, key: str) -> None:
        """Keep booleans distinct from the numeric class for generated keys."""
        with Graph.open(":memory:") as graph:
            graph.create_node_index(key)
            graph.add_node("Program", **{key: True})
            graph.add_node("Program", **{key: 1})
            graph.add_node("Program", **{key: 1.0})
            assert len(list(graph.find_nodes("Program", **{key: True}))) == 1
            assert len(list(graph.find_nodes("Program", **{key: 1}))) == 1
            assert len(list(graph.find_nodes("Program", **{key: 1.0}))) == 1
