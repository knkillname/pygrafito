# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the GQL composition surface."""

from collections.abc import Iterator

import pytest

from pygrafito import Graph, QueryBudget
from pygrafito.engine.query.results import QueryResult
from pygrafito.engine.query.values import QueryValue
from pygrafito.model import (
    QueryBudgetExceededError,
    QuerySemanticError,
    QuerySyntaxError,
)


class _CompositionGraph:
    """Provide the shared TRON fixture for composition tests."""

    @pytest.fixture
    def graph(self) -> Iterator[Graph]:
        with Graph.open(":memory:") as graph:
            kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
            quorra = graph.add_node("Program", designation="Quorra", cycles=37)
            tron = graph.add_node("Program", designation="Tron", cycles=40)
            graph.add_node("Program", designation="Clu")
            rinzler = graph.add_node("Program", designation="Rinzler", cycles=38)
            graph.add_node("Program", designation="Sam Flynn")
            graph.add_relationship(kevin, "TRUSTS", tron)
            graph.add_relationship(quorra, "TRUSTS", rinzler)
            graph.add_relationship(kevin, "ALLIES_WITH", quorra)
            yield graph

    @staticmethod
    def values(result: QueryResult) -> list[tuple[QueryValue, ...]]:
        return [tuple(row.values()) for row in result]

    @staticmethod
    def values_for(result: QueryResult, column: str) -> list[QueryValue]:
        return [row[column] for row in result]


class TestLet(_CompositionGraph):
    """Verify additive row-wise bindings."""

    def test_leading_let_is_a_row_source(self, graph: Graph) -> None:
        result = graph.query("LET value = 1 RETURN value")
        assert self.values(result) == [(1,)]

    def test_let_adds_to_the_existing_scope(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Tron'}) "
            "LET following = n.cycles + 1 RETURN n.designation AS name, following"
        )
        assert self.values(result) == [("Tron", 41)]

    def test_let_definitions_evaluate_left_to_right(self, graph: Graph) -> None:
        result = graph.query("LET base = 36, following = base + 1 RETURN following")
        assert self.values(result) == [(37,)]

    def test_direct_variable_keeps_its_kind(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Kevin Flynn'}) LET element = n "
            "MATCH (element)-[:TRUSTS]->(m) RETURN m.designation AS name"
        )
        assert self.values_for(result, "name") == ["Tron"]

    def test_shadowing_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="already bound"):
            graph.query("MATCH (n:Program) LET n = 1 RETURN n")

    def test_duplicate_name_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="already bound"):
            graph.query("LET value = 1, value = 2 RETURN value")

    def test_aggregate_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="aggregate"):
            graph.query("LET value = count(*) RETURN value")

    def test_let_cannot_be_final(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="RETURN"):
            graph.query("MATCH (n:Program) LET value = 1")

    def test_let_after_a_write_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="write clause"):
            graph.query("MATCH (n:Program) SET n.cycles = 1 LET value = 1 RETURN value")

    def test_let_after_return_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="RETURN"):
            graph.query("MATCH (n:Program) RETURN n LET value = 1")

    def test_let_counts_rows_against_the_budget(self, graph: Graph) -> None:
        with pytest.raises(QueryBudgetExceededError):
            graph.query("LET value = 1 RETURN value", budget=QueryBudget(max_rows=0))


class TestOrdinality(_CompositionGraph):
    """Verify one-based ordinality and zero-based offsets."""

    def test_for_ordinality_is_one_based(self, graph: Graph) -> None:
        result = graph.query("FOR value IN [1, 2] WITH ORDINALITY index RETURN value, index")
        assert self.values(result) == [(1, 1), (2, 2)]

    def test_for_offset_is_zero_based(self, graph: Graph) -> None:
        result = graph.query("FOR value IN [1, 2] WITH OFFSET index RETURN value, index")
        assert self.values(result) == [(1, 0), (2, 1)]

    def test_unwind_accepts_ordinality(self, graph: Graph) -> None:
        result = graph.query("UNWIND [10, 20] AS value WITH ORDINALITY index RETURN value, index")
        assert self.values(result) == [(10, 1), (20, 2)]

    def test_index_must_be_fresh(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="differ"):
            graph.query("FOR value IN [1] WITH ORDINALITY value RETURN value")

    def test_index_must_not_shadow_another_binding(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="already bound"):
            graph.query("MATCH (n:Program) FOR value IN [1] WITH ORDINALITY n RETURN n")

    def test_empty_list_has_no_position_rows(self, graph: Graph) -> None:
        result = graph.query("FOR value IN [] WITH ORDINALITY index RETURN index")
        assert result.rows == ()

    def test_null_list_has_no_position_rows(self, graph: Graph) -> None:
        result = graph.query(
            "FOR value IN $values WITH OFFSET index RETURN index",
            {"values": None},
        )
        assert result.rows == ()

    def test_ordinality_and_offset_are_exclusive(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="cannot be combined"):
            graph.query("FOR value IN [1] WITH ORDINALITY index WITH OFFSET other RETURN index")


class TestGroupBy(_CompositionGraph):
    """Verify explicit grouping, deduplication, and edge cases."""

    def test_explicit_grouping(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total "
            "GROUP BY n.cycles ORDER BY cycles"
        )
        assert self.values(result) == [
            (36, 1),
            (37, 1),
            (38, 1),
            (40, 1),
            (None, 2),
        ]

    def test_key_need_not_be_returned(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN count(*) AS total GROUP BY n.cycles")
        assert result.columns == ("total",)
        assert len(result.rows) == 5

    def test_no_aggregate_deduplicates(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles ORDER BY n.cycles"
        )
        assert self.values(result) == [(36,), (37,), (38,), (40,), (None,)]

    def test_group_by_a_let_binding(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) LET cycles = n.cycles RETURN count(*) AS total GROUP BY cycles"
        )
        assert len(result.rows) == 5

    def test_distinct_with_group_by(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN DISTINCT n.cycles GROUP BY n.cycles ORDER BY n.cycles"
        )
        assert self.values(result) == [(36,), (37,), (38,), (40,), (None,)]

    def test_expression_key_extension(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) WHERE n.cycles IS NOT NULL "
            "RETURN n.cycles + 0 AS shifted, count(*) AS total "
            "GROUP BY n.cycles + 0 ORDER BY shifted"
        )
        assert self.values(result) == [(36, 1), (37, 1), (38, 1), (40, 1)]

    def test_empty_key_list_groups_everything(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN count(*) AS total GROUP BY ()")
        assert self.values(result) == [(6,)]

    def test_empty_input_has_no_groups(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Missing) RETURN n.cycles AS cycles, count(*) AS total GROUP BY n.cycles"
        )
        assert self.values(result) == []

    def test_empty_key_list_on_empty_input(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Missing) RETURN count(*) AS total GROUP BY ()")
        assert self.values(result) == [(0,)]

    def test_null_keys_form_one_group(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total GROUP BY n.cycles"
        )
        rows = {row["cycles"]: row["total"] for row in result}
        assert rows[None] == 2

    def test_duplicate_keys_are_deduplicated(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles, n.cycles ORDER BY n.cycles"
        )
        assert len(result.rows) == 5

    def test_return_star_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="RETURN \\*"):
            graph.query("MATCH (n:Program) RETURN * GROUP BY n.cycles")

    def test_no_bindings_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="NO BINDINGS"):
            graph.query("MATCH (n:Program) RETURN NO BINDINGS GROUP BY n.cycles")

    def test_empty_key_list_requires_an_aggregate(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="GROUP BY \\(\\)"):
            graph.query("MATCH (n:Program) RETURN n.cycles GROUP BY ()")

    def test_non_key_expression_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="grouping key"):
            graph.query(
                "MATCH (n:Program) RETURN n.designation, count(*) AS total GROUP BY n.cycles"
            )


class TestFinish(_CompositionGraph):
    """Verify the canonical no-result clause."""

    def test_finish_ends_a_read_without_a_result(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) FINISH")
        assert result.columns == ()
        assert result.rows == ()

    def test_finish_applies_a_write(self, graph: Graph) -> None:
        result = graph.query("CREATE (n:Program {designation: 'Clu'}) FINISH")
        assert result.rows == ()
        assert result.summary.created_nodes == 1

    def test_finish_after_next(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) NEXT FINISH")
        assert result.rows == ()

    def test_finish_alone_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="read or write clause"):
            graph.query("FINISH")

    def test_finish_is_final(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="FINISH"):
            graph.query("MATCH (n:Program) FINISH RETURN n")

    def test_write_only_is_equivalent(self, graph: Graph) -> None:
        result = graph.query("CREATE (n:Program {designation: 'Clu'})")
        assert result.rows == ()
        assert result.summary.created_nodes == 1


class TestReturnNoBindings(_CompositionGraph):
    """Verify the zero-column pygrafito extension."""

    def test_one_empty_row_per_input_binding(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Program) RETURN NO BINDINGS")
        assert result.columns == ()
        assert len(result.rows) == 6
        assert all(row.row_values == () for row in result.rows)

    def test_empty_input(self, graph: Graph) -> None:
        result = graph.query("MATCH (n:Missing) RETURN NO BINDINGS")
        assert result.columns == ()
        assert result.rows == ()

    def test_write_projects_one_empty_row(self, graph: Graph) -> None:
        result = graph.query("CREATE (n:Program {designation: 'Clu'}) RETURN NO BINDINGS")
        assert len(result.rows) == 1
        assert result.rows[0].row_values == ()

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n:Program) RETURN NO BINDINGS ORDER BY n.designation",
            "MATCH (n:Program) RETURN NO BINDINGS LIMIT 1",
            "MATCH (n:Program) RETURN NO BINDINGS OFFSET 1",
            "MATCH (n:Program) RETURN NO BINDINGS SKIP 1",
            "MATCH (n:Program) RETURN DISTINCT NO BINDINGS",
            "MATCH (n:Program) RETURN NO BINDINGS NEXT RETURN n",
        ],
    )
    def test_modifiers_are_rejected(self, graph: Graph, query: str) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.query(query)


class TestNext(_CompositionGraph):
    """Verify segment composition, result flow, and YIELD."""

    def test_intermediate_return_feeds_next(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN n AS element "
            "NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m.designation AS name"
        )
        assert self.values_for(result, "name") == ["Tron"]

    def test_write_only_segment_passes_bindings(self, graph: Graph) -> None:
        result = graph.query(
            "CREATE (n:Program {designation: 'Rinzler'}) "
            "NEXT MATCH (n) RETURN n.designation AS name"
        )
        assert self.values_for(result, "name") == ["Rinzler"]

    def test_later_segment_reads_an_earlier_write(self, graph: Graph) -> None:
        result = graph.query(
            "CREATE (n:Program {designation: 'Ares'}) "
            "NEXT MATCH (m:Program {designation: 'Ares'}) RETURN m.designation AS name"
        )
        assert self.values_for(result, "name") == ["Ares"]

    def test_yield_selects_columns(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles "
            "NEXT YIELD name RETURN name ORDER BY name"
        )
        assert self.values_for(result, "name") == [
            "Clu",
            "Kevin Flynn",
            "Quorra",
            "Rinzler",
            "Sam Flynn",
            "Tron",
        ]

    def test_yield_renames_columns(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Quorra'}) "
            "RETURN n.designation AS name NEXT YIELD name AS designation "
            "RETURN designation"
        )
        assert self.values(result) == [("Quorra",)]

    def test_no_yield_passes_all_columns(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Quorra'}) "
            "RETURN n.designation AS name, n.cycles AS cycles "
            "NEXT RETURN name, cycles"
        )
        assert self.values(result) == [("Quorra", 37)]

    def test_mid_query_grouping(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total "
            "GROUP BY n.cycles NEXT FILTER total > 1 RETURN cycles, total"
        )
        assert self.values(result) == [(None, 2)]

    def test_final_result_comes_from_the_last_return(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program) RETURN n.designation AS name NEXT RETURN name ORDER BY name"
        )
        assert result.columns == ("name",)
        assert len(result.rows) == 6

    def test_yield_unknown_column_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="not bound"):
            graph.query(
                "MATCH (n:Program) RETURN n.designation AS name NEXT YIELD missing RETURN name"
            )

    def test_duplicate_yield_alias_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySemanticError, match="duplicate YIELD"):
            graph.query(
                "MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles "
                "NEXT YIELD name, cycles AS name RETURN name"
            )

    def test_yield_after_a_write_only_segment_is_rejected(self, graph: Graph) -> None:
        with pytest.raises(QuerySyntaxError, match="preceding RETURN"):
            graph.query("CREATE (n:Program) NEXT YIELD n RETURN n")

    @pytest.mark.parametrize(
        "query",
        [
            "NEXT MATCH (n:Program) RETURN n",
            "MATCH (n:Program) RETURN n NEXT",
            "MATCH (n:Program) RETURN n NEXT NEXT RETURN n",
            "MATCH (n:Program) NEXT RETURN n",
            "MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m",
        ],
    )
    def test_placement_errors(self, graph: Graph, query: str) -> None:
        with pytest.raises(QuerySyntaxError):
            graph.query(query)

    def test_budget_rolls_back_an_earlier_segment(self, graph: Graph) -> None:
        with pytest.raises(QueryBudgetExceededError):
            graph.query(
                "CREATE (n:Program {designation: 'Clu'}) "
                "NEXT MATCH (m:Program) RETURN m.designation",
                budget=QueryBudget(max_rows=1),
            )
        result = graph.query("MATCH (n:Program {designation: 'Clu'}) RETURN count(*) AS total")
        assert result.rows[0]["total"] == 1


class TestPipelineParity(_CompositionGraph):
    """Verify one-clause write application matches the previous batch behavior."""

    def test_set_then_remove(self, graph: Graph) -> None:
        result = graph.query(
            "MATCH (n:Program {designation: 'Tron'}) SET n.cycles = 41 "
            "REMOVE n.cycles RETURN n.cycles AS cycles"
        )
        assert self.values(result) == [(None,)]

    def test_create_then_set(self, graph: Graph) -> None:
        result = graph.query(
            "CREATE (n:Program {designation: 'Rinzler'}) SET n.cycles = 38 "
            "RETURN n.cycles AS cycles"
        )
        assert self.values(result) == [(38,)]
