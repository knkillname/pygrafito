# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for open-ended traversal and early-stopping execution."""

import typing
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path

import pytest

from pygrafito import Graph, QueryBudgetExceededError, QueryResult, QuerySemanticError
from pygrafito.engine.query.ast import (
    NodePattern,
    PathMode,
    PathPattern,
    RelationshipPattern,
)
from pygrafito.engine.query.executor import RepositorySnapshots
from pygrafito.engine.query.pattern import PatternEngine
from pygrafito.engine.query.values import ExpressionEvaluator, ScalarFunctions
from pygrafito.engine.traversal import (
    AdjacencySnapshot,
    DatabaseNeighborhood,
    TraversalCapture,
)
from pygrafito.model import Direction, Node, QueryBudget, Relationship
from pygrafito.storage.codec import PropertyCodec
from pygrafito.storage.connection import Database
from pygrafito.storage.nodes import NodeRepository
from pygrafito.storage.relationships import RelationshipRepository


class TestOpenFixtures:
    """Build the TRON graphs used by the open-traversal tests."""

    @staticmethod
    def cycle_graph() -> Graph:
        """Return a graph with a directed three-program cycle.

        Returns
        -------
        Graph
            Flynn -> Tron -> Clu -> Flynn.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(tron, "TRUSTS", clu)
        graph.add_relationship(clu, "TRUSTS", flynn)
        return graph

    @staticmethod
    def diamond_graph() -> Graph:
        """Return a graph with two routes from Flynn to the Grid.

        Returns
        -------
        Graph
            Flynn -> Tron -> Grid and Flynn -> Clu -> Grid.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        clu = graph.add_node("Program", designation="Clu")
        grid = graph.add_node("Place", designation="The Grid")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "TRUSTS", clu)
        graph.add_relationship(tron, "TRUSTS", grid)
        graph.add_relationship(clu, "TRUSTS", grid)
        return graph

    @staticmethod
    def parallel_graph() -> Graph:
        """Return a graph with two parallel trust relationships.

        Returns
        -------
        Graph
            Flynn with two separate TRUSTS relationships to Tron.
        """
        graph = Graph.open(":memory:")
        flynn = graph.add_node("Program", designation="Flynn")
        tron = graph.add_node("Program", designation="Tron")
        graph.add_relationship(flynn, "TRUSTS", tron)
        graph.add_relationship(flynn, "TRUSTS", tron)
        return graph

    @staticmethod
    def self_loop_graph() -> Graph:
        """Return a graph with a self-loop and an isolated program.

        Returns
        -------
        Graph
            Quorra with a TRUSTS self-loop and an isolated Tron.
        """
        graph = Graph.open(":memory:")
        quorra = graph.add_node("Program", designation="Quorra")
        graph.add_node("Program", designation="Tron")
        graph.add_relationship(quorra, "TRUSTS", quorra)
        return graph

    @staticmethod
    def names(result: QueryResult) -> list[object]:
        """Return the ``name`` column of a result.

        Parameters
        ----------
        result : QueryResult
            Query result to read.

        Returns
        -------
        list[object]
            Projected names in row order.
        """
        return [row["name"] for row in result.rows]


class TestLiveFrontier(TestOpenFixtures):
    """Verify bounded patterns capture and open patterns read on demand."""

    def test_bounded_query_captures_one_region(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keep the region capture for a bounded quantified pattern."""
        calls: list[int] = []
        original = TraversalCapture.region

        def counted(
            self: TraversalCapture,
            start: Node | int,
            max_depth: int,
            direction: Direction = Direction.OUTGOING,
            labels: Iterable[str] | None = None,
            include: Iterable[int] = (),
        ) -> AdjacencySnapshot:
            calls.append(1)
            return original(self, start, max_depth, direction, labels, include)

        monkeypatch.setattr(TraversalCapture, "region", counted)
        with self.cycle_graph() as graph:
            graph.query("MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{1,2}]->(b) RETURN b")
        assert calls

    def test_open_query_reads_levels_on_demand(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Read an open pattern from the live neighborhood, not a region."""
        region_calls: list[int] = []
        edge_calls: list[int] = []
        original_region = TraversalCapture.region
        original_edges = DatabaseNeighborhood.edges

        def counted_region(
            self: TraversalCapture,
            start: Node | int,
            max_depth: int,
            direction: Direction = Direction.OUTGOING,
            labels: Iterable[str] | None = None,
            include: Iterable[int] = (),
        ) -> AdjacencySnapshot:
            region_calls.append(1)
            return original_region(self, start, max_depth, direction, labels, include)

        def counted_edges(
            self: DatabaseNeighborhood,
            node_id: int,
            direction: Direction,
            labels: frozenset[str] | None,
        ) -> Iterator[tuple[Relationship, int]]:
            edge_calls.append(1)
            return original_edges(self, node_id, direction, labels)

        monkeypatch.setattr(TraversalCapture, "region", counted_region)
        monkeypatch.setattr(DatabaseNeighborhood, "edges", counted_edges)
        with self.cycle_graph() as graph:
            graph.query("MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) RETURN b")
        assert not region_calls
        assert edge_calls


class TestOpenPathModes(TestOpenFixtures):
    """Verify each path mode bounds or repeats an open walk."""

    def test_open_trail_terminates_on_a_cycle(self) -> None:
        """Stop a TRAIL walk when every relationship is used once."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.names(result) == ["Tron", "Clu", "Flynn"]

    def test_open_simple_terminates_on_a_cycle(self) -> None:
        """Stop a SIMPLE walk at the repeated start node."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH SIMPLE (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.names(result) == ["Tron", "Clu", "Flynn"]

    def test_open_acyclic_rejects_the_cycle(self) -> None:
        """Reject a return to any visited node under ACYCLIC."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH ACYCLIC (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name"
            )
        assert self.names(result) == ["Tron", "Clu"]

    def test_open_walk_repeats_an_edge(self) -> None:
        """Let an open WALK revisit the same relationship."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH WALK (a:Program {designation: 'Quorra'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name LIMIT 3"
            )
        assert self.names(result) == ["Quorra", "Quorra", "Quorra"]

    def test_zero_hop_star_binds_the_same_node_and_empty_list(self) -> None:
        """Bind both ends to the start and the relationship list to empty."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[r:TRUSTS*]->(b) "
                "RETURN a.designation AS name, b.designation AS target, size(r) AS hops "
                "LIMIT 1"
            )
        assert result.rows[0]["name"] == "Flynn"
        assert result.rows[0]["target"] == "Flynn"
        assert result.rows[0]["hops"] == 0


class TestOpenPathValues(TestOpenFixtures):
    """Verify path variables, path functions, and relationship lists."""

    def test_path_functions_preserve_order(self) -> None:
        """Expose nodes, relationships, and length in traversal order."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL p = (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN [n IN nodes(p) | n.designation] AS names, "
                "size(relationships(p)) AS edges, length(p) AS hops"
            )
        assert result.rows[0]["names"] == ["Flynn", "Tron"]
        assert result.rows[0]["edges"] == 1
        assert result.rows[0]["hops"] == 1

    def test_relationship_variable_binds_a_list(self) -> None:
        """Bind an open relationship variable to its traversed list."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[r:TRUSTS+]->(b) "
                "RETURN size(r) AS hops ORDER BY hops"
            )
        assert [row["hops"] for row in result.rows] == [1, 2, 3]

    def test_single_relationship_use_is_rejected(self) -> None:
        """Reject property access on an open relationship list."""
        with self.cycle_graph() as graph, pytest.raises(QuerySemanticError):
            graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[r:TRUSTS+]->(b) "
                "RETURN r.since_cycle"
            )

    def test_generator_matches_the_list_form(self) -> None:
        """Agree between list and generator callers on one fixture."""
        database = Database(":memory:")
        try:
            codec = PropertyCodec()
            nodes = NodeRepository(database.connection, codec)
            relationships = RelationshipRepository(database.connection, codec)
            flynn = nodes.create(("Program",), {"designation": "Flynn"})
            tron = nodes.create(("Program",), {"designation": "Tron"})
            quorra = nodes.create(("Program",), {"designation": "Quorra"})
            relationships.create(flynn.id, "TRUSTS", tron.id)
            relationships.create(tron.id, "TRUSTS", quorra.id)
            snapshots = RepositorySnapshots(nodes, relationships)
            evaluator = ExpressionEvaluator(ScalarFunctions(snapshots))
            engine = PatternEngine(
                nodes,
                relationships,
                lambda *_: [flynn],
                {},
                evaluator,
            )
            pattern = PathPattern.simple(
                nodes=(
                    NodePattern(variable="a", labels=("Program",)),
                    NodePattern(variable="b", labels=("Program",)),
                ),
                relationships=(
                    RelationshipPattern(
                        types=("TRUSTS",),
                        min_hops=1,
                        max_hops=None,
                        canonical_quantifier=True,
                    ),
                ),
                mode=PathMode.TRAIL,
            )
            as_list = engine.match([pattern], None, {})
            as_stream = list(engine.iter_match([pattern], None, {}))
        finally:
            database.close()
        assert as_list == as_stream

    def test_closing_the_generator_stops_expansion(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Stop charging expansions when the generator is closed."""
        database = Database(":memory:")
        try:
            codec = PropertyCodec()
            nodes = NodeRepository(database.connection, codec)
            relationships = RelationshipRepository(database.connection, codec)
            flynn = nodes.create(("Program",), {"designation": "Flynn"})
            tron = nodes.create(("Program",), {"designation": "Tron"})
            clu = nodes.create(("Program",), {"designation": "Clu"})
            relationships.create(flynn.id, "TRUSTS", tron.id)
            relationships.create(tron.id, "TRUSTS", clu.id)
            relationships.create(clu.id, "TRUSTS", flynn.id)
            expansions: list[int] = []
            original = PatternEngine._consume_expansion

            def counted(self: PatternEngine) -> None:
                expansions.append(1)
                original(self)

            monkeypatch.setattr(PatternEngine, "_consume_expansion", counted)
            snapshots = RepositorySnapshots(nodes, relationships)
            evaluator = ExpressionEvaluator(ScalarFunctions(snapshots))
            engine = PatternEngine(
                nodes,
                relationships,
                lambda *_: [flynn],
                {},
                evaluator,
            )
            pattern = PathPattern.simple(
                nodes=(
                    NodePattern(variable="a", labels=("Program",)),
                    NodePattern(variable="b", labels=("Program",)),
                ),
                relationships=(
                    RelationshipPattern(
                        types=("TRUSTS",),
                        min_hops=0,
                        max_hops=None,
                        canonical_quantifier=True,
                    ),
                ),
                mode=PathMode.WALK,
            )
            stream = typing.cast(
                Generator[dict[str, object]],
                engine.iter_match([pattern], None, {}),
            )
            assert next(stream) is not None
            stream.close()
        finally:
            database.close()
        assert len(expansions) <= 1


class TestOpenCoverage(TestOpenFixtures):
    """Cover dense, diamond, parallel, self-loop, and unreachable shapes."""

    def test_diamond_open_trail_finds_both_routes(self) -> None:
        """Return both routes from Flynn to the Grid."""
        with self.diamond_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b:Place) "
                "RETURN b.designation AS name"
            )
        assert self.names(result) == ["The Grid", "The Grid"]

    def test_parallel_open_relationships_are_distinct(self) -> None:
        """Return both parallel relationships as separate paths."""
        with self.parallel_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b:Program) "
                "RETURN b.designation AS name"
            )
        assert self.names(result) == ["Tron", "Tron"]

    def test_self_loop_open_walk_repeats(self) -> None:
        """Follow a self-loop repeatedly under an open WALK."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH WALK (a:Program {designation: 'Quorra'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name LIMIT 2"
            )
        assert self.names(result) == ["Quorra", "Quorra"]

    def test_unreachable_target_returns_no_rows(self) -> None:
        """Return no rows when the open walk cannot reach the target."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Quorra'})-[:TRUSTS+]->"
                "(b:Program {designation: 'Tron'}) RETURN b.designation AS name"
            )
        assert result.rows == ()

    def test_optional_open_match_keeps_unmatched_rows(self) -> None:
        """Keep a null-extended row when an optional open pattern misses."""
        with self.self_loop_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Tron'}) "
                "OPTIONAL MATCH (a)-[:TRUSTS+]->(b:Program {designation: 'Quorra'}) "
                "RETURN b.designation AS name"
            )
        assert result.rows[0]["name"] is None

    def test_optional_open_match_binds_matches(self) -> None:
        """Bind the target when the optional open pattern matches."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "OPTIONAL MATCH TRAIL (a)-[:TRUSTS+]->(b:Program) "
                "RETURN b.designation AS name ORDER BY name"
            )
        assert self.names(result) == ["Clu", "Flynn", "Tron"]


class TestDemandExecution(TestOpenFixtures):
    """Verify early stopping, pagination, and materializing shapes."""

    def test_limit_stops_open_walk_expansion(self) -> None:
        """Return five rows without exhausting the open walk."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name LIMIT 5",
                budget=QueryBudget(max_expansions=5),
            )
        assert len(result.rows) == 5

    def test_limit_zero_expands_nothing(self) -> None:
        """Return no rows without expanding a relationship."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name LIMIT 0",
                budget=QueryBudget(max_expansions=0),
            )
        assert result.rows == ()

    def test_offset_skips_without_counting_as_result_rows(self) -> None:
        """Discard the offset rows before the limit is applied."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name OFFSET 1 LIMIT 2"
            )
        assert self.names(result) == ["Clu", "Flynn"]

    def test_filter_before_limit(self) -> None:
        """Apply a filter before the final limit."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "FILTER b.designation = 'Clu' RETURN b.designation AS name LIMIT 1"
            )
        assert self.names(result) == ["Clu"]

    def test_streaming_with_stage_flows(self) -> None:
        """Stream a plain WITH stage before the final limit."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "WITH b RETURN b.designation AS name LIMIT 2",
                budget=QueryBudget(max_expansions=2),
            )
        assert len(result.rows) == 2

    def test_exists_stops_after_the_first_inner_row(self) -> None:
        """Stop an open EXISTS walk as soon as the subquery matches."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH (a:Program {designation: 'Flynn'}) "
                "WHERE EXISTS { MATCH (a)-[:TRUSTS+]->(b) } "
                "RETURN a.designation AS name",
                budget=QueryBudget(max_expansions=2),
            )
        assert self.names(result) == ["Flynn"]

    def test_stage_level_limit_materializes(self) -> None:
        """Runs a WITH limit to completion instead of stopping early."""
        with self.cycle_graph() as graph, pytest.raises(QueryBudgetExceededError):
            graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "WITH b LIMIT 1 RETURN b.designation AS name",
                budget=QueryBudget(max_expansions=5),
            )


class TestFullEvaluation(TestOpenFixtures):
    """Verify shapes that need every row keep the materialized path."""

    def test_order_by_uses_the_requested_order(self) -> None:
        """Sort every open match before applying the limit."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name ORDER BY name DESC LIMIT 2"
            )
        assert self.names(result) == ["Tron", "Flynn"]

    def test_distinct_removes_duplicates(self) -> None:
        """Remove duplicate projected names after full evaluation."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program)-[:TRUSTS+]->(b) "
                "RETURN DISTINCT b.designation AS name ORDER BY name"
            )
        assert self.names(result) == ["Clu", "Flynn", "Tron"]

    def test_aggregation_consumes_every_match(self) -> None:
        """Count every open match before returning."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN count(*) AS total"
            )
        assert result.rows[0]["total"] == 3

    def test_group_by_consumes_every_match(self) -> None:
        """Group every open match before returning."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program)-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name, count(*) AS total "
                "GROUP BY b.designation ORDER BY name"
            )
        assert [row["total"] for row in result.rows] == [3, 3, 3]

    def test_set_operation_runs_each_term_fully(self) -> None:
        """Combine open matches with a set operator."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name "
                "UNION MATCH (b:Program {designation: 'Clu'}) RETURN b.designation AS name"
            )
        assert self.names(result) == ["Tron", "Clu", "Flynn"]

    def test_next_runs_each_segment(self) -> None:
        """Carry open matches through a NEXT boundary."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name NEXT RETURN name ORDER BY name"
            )
        assert self.names(result) == ["Clu", "Flynn", "Tron"]

    def test_finish_returns_no_rows(self) -> None:
        """Finish an open read without a result."""
        with self.cycle_graph() as graph:
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) FINISH"
            )
        assert result.rows == ()

    def test_write_after_an_open_read_applies_to_every_match(self) -> None:
        """Drain the open read before the write clause runs."""
        with self.cycle_graph() as graph:
            graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) SET b.cycles = 1"
            )
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
        assert [row["cycles"] for row in result.rows] == [1, 1, 1]


class TestOpenBudgetAndRecovery(TestOpenFixtures):
    """Verify budget failures, rollback, and handle recovery."""

    def test_no_demand_open_walk_hits_the_budget(self) -> None:
        """Raise a budget error instead of a truncated path set."""
        with self.cycle_graph() as graph, pytest.raises(QueryBudgetExceededError):
            graph.query(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                "RETURN b.designation AS name",
                budget=QueryBudget(max_expansions=10),
            )

    def test_handle_stays_usable_after_a_budget_failure(self) -> None:
        """Accept a later statement after an open walk exceeds the budget."""
        with self.cycle_graph() as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) RETURN b",
                    budget=QueryBudget(max_expansions=5),
                )
            result = graph.query("MATCH (n:Program) RETURN count(*) AS total")
        assert result.rows[0]["total"] == 3

    def test_write_statement_rolls_back_after_a_budget_failure(self) -> None:
        """Undo every open-read write when the statement exceeds the budget."""
        with self.cycle_graph() as graph:
            with pytest.raises(QueryBudgetExceededError):
                graph.query(
                    "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                    "SET b.cycles = 1",
                    budget=QueryBudget(max_rows=0),
                )
            result = graph.query("MATCH (n:Program) RETURN n.cycles AS cycles")
        assert [row["cycles"] for row in result.rows] == [None, None, None]

    def test_reopen_after_an_execution_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Release the statement state after an arbitrary execution failure."""
        path = tmp_path / "failed-walk.db"

        def failing(
            self: DatabaseNeighborhood,
            node_id: int,
            direction: Direction,
            labels: frozenset[str] | None,
        ) -> Iterator[tuple[Relationship, int]]:
            raise RuntimeError("injected failure")

        monkeypatch.setattr(DatabaseNeighborhood, "edges", failing)
        with Graph.open(str(path)) as graph:
            flynn = graph.add_node("Program", designation="Flynn")
            tron = graph.add_node("Program", designation="Tron")
            graph.add_relationship(flynn, "TRUSTS", tron)
            with pytest.raises(RuntimeError):
                graph.query(
                    "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
                    "RETURN b.designation AS name"
                )
            result = graph.query("MATCH (n:Program) RETURN count(*) AS total")
            assert result.rows[0]["total"] == 2
        with Graph.open(str(path)) as graph:
            result = graph.query("MATCH (n:Program) RETURN count(*) AS total")
        assert result.rows[0]["total"] == 2

    def test_open_read_uses_the_statement_snapshot(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ignore a concurrent write during an open read."""
        path = tmp_path / "grid.db"
        original = DatabaseNeighborhood.edges
        write_done: list[bool] = []

        def inject_write(
            self: DatabaseNeighborhood,
            node_id: int,
            direction: Direction,
            labels: frozenset[str] | None,
        ) -> Iterator[tuple[object, int]]:
            if not write_done:
                with Graph.open(str(path)) as other:
                    other.add_node("Program", designation="Rinzler")
                write_done.append(True)
            yield from original(self, node_id, direction, labels)

        monkeypatch.setattr(DatabaseNeighborhood, "edges", inject_write)
        with Graph.open(str(path)) as graph:
            flynn = graph.add_node("Program", designation="Flynn")
            tron = graph.add_node("Program", designation="Tron")
            clu = graph.add_node("Program", designation="Clu")
            graph.add_relationship(flynn, "TRUSTS", tron)
            graph.add_relationship(tron, "TRUSTS", clu)
            graph.add_relationship(clu, "TRUSTS", flynn)
            result = graph.query(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b), "
                "(c:Program) RETURN count(DISTINCT c.designation) AS total"
            )
        with Graph.open(str(path)) as graph:
            stored = graph.query("MATCH (n:Program) RETURN count(*) AS total")
        assert write_done
        assert result.rows[0]["total"] == 3
        assert stored.rows[0]["total"] == 4


class TestOpenExplain(TestOpenFixtures):
    """Verify plan inspection marks an open position."""

    def test_open_pattern_is_marked(self) -> None:
        """Report the open position and its path mode."""
        with self.cycle_graph() as graph:
            plan = graph.explain(
                "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) RETURN b"
            )
        assert "MATCH QUANTIFIED OPEN TRAIL" in plan

    def test_bounded_pattern_keeps_its_line(self) -> None:
        """Keep the depth-bounded explanation for closed patterns."""
        with self.cycle_graph() as graph:
            plan = graph.explain(
                "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS{1,2}]->(b) RETURN b"
            )
        assert "QUANTIFIED PATTERN max_hops=2" in plan
