# SPDX-FileCopyrightText: 2026-present Mario Abarca <knkillname@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Runnable benchmark for indexes and traversal cost.

The harness seeds a themed synthetic graph, measures statements with and without
declared indexes, compares whole-graph traversal with bounded traversal, and reports
write throughput for both index states. It is not part of the test suite because a
useful dataset takes seconds to build.
"""

import argparse
import csv
import dataclasses
import functools
import pathlib
import statistics
import tempfile
import time
import typing
from collections.abc import Callable

from pygrafito import Graph, Node
from pygrafito.engine.traversal import (
    AdjacencySnapshot,
    ReachabilityEvaluator,
    ShortestPathEvaluator,
    TrailEnumerator,
)


@dataclasses.dataclass(frozen=True, slots=True)
class Options:
    """Benchmark sizes and repetition count.

    Parameters
    ----------
    nodes : int
        Number of nodes to seed.
    relationships : int
        Number of relationships to seed.
    repeats : int
        Repetitions per query scenario; the median is reported.
    """

    nodes: int = 20_000
    relationships: int = 60_000
    repeats: int = 3


class Timer:
    """Measure a callable several times and keep the median."""

    @staticmethod
    def measure(operation: Callable[[], object], repeats: int) -> float:
        """Return the median elapsed time in milliseconds.

        Parameters
        ----------
        operation : Callable[[], object]
            Work to time.
        repeats : int
            Number of samples.

        Returns
        -------
        float
            Median elapsed time in milliseconds.
        """
        samples: list[float] = []
        for _ in range(max(repeats, 1)):
            started = time.perf_counter()
            operation()
            samples.append(time.perf_counter() - started)
        return statistics.median(samples) * 1000


class Dataset:
    """Seed a deterministic themed graph.

    Parameters
    ----------
    nodes : int
        Number of nodes to create.
    relationships : int
        Number of relationships to create.
    """

    CYCLE_MODULUS: typing.ClassVar[int] = 97

    def __init__(self, nodes: int, relationships: int) -> None:
        self._nodes = nodes
        self._relationships = relationships

    def seed(self, graph: Graph) -> list[Node]:
        """Create the dataset in one transaction.

        Parameters
        ----------
        graph : Graph
            Graph to populate.

        Returns
        -------
        list[Node]
            Created nodes in insertion order.
        """
        created = []
        with graph.transaction() as transaction:
            for position in range(self._nodes):
                label = "Program" if position % 10 == 0 else "Agent"
                created.append(
                    transaction.add_node(
                        label,
                        designation=f"{label.lower()}-{position}",
                        cycles=position % self.CYCLE_MODULUS,
                        region=f"region-{position % 7}",
                    )
                )
        if not created:
            return created
        with graph.transaction() as transaction:
            for position in range(self._relationships):
                start = created[position % len(created)]
                end = created[(position * 7 + 13) % len(created)]
                if start.id == end.id:
                    continue
                rel_type = "TRANSMISSION" if position % 100 == 0 else "ALLIES_WITH"
                transaction.add_relationship(
                    start,
                    rel_type,
                    end,
                    since_cycle=2000 + position % 20,
                )
        with graph.transaction() as transaction:
            for position in range(min(5, len(created) - 1)):
                transaction.add_relationship(
                    created[position],
                    "TRANSITION",
                    created[position + 1],
                )
        return created


class Scenarios:
    """Statement scenarios measured in both index states."""

    @staticmethod
    def equality(graph: Graph) -> None:
        """Filter one property value."""
        graph.query("MATCH (n:Program) WHERE n.cycles = 36 RETURN n")

    @staticmethod
    def range_filter(graph: Graph) -> None:
        """Filter a property range."""
        graph.query("MATCH (n:Program) WHERE n.cycles >= 90 RETURN count(*) AS total")

    @staticmethod
    def type_filter(graph: Graph) -> None:
        """Filter a selective relationship type without a bound endpoint."""
        graph.query("MATCH (a)-[r:TRANSMISSION]->(b) RETURN count(*) AS total")

    @staticmethod
    def node_lookup(graph: Graph) -> None:
        """Run the Python lookup by label and property."""
        list(graph.find_nodes("Program", cycles=36))

    @staticmethod
    def quantified(graph: Graph) -> None:
        """Expand a bounded quantified path from an indexed property filter."""
        graph.query(
            "MATCH (a:Program {cycles: 36})-[:ALLIES_WITH*1..2]->(b) RETURN count(*) AS total"
        )


class Runner:
    """Run the benchmark and print its tables.

    Parameters
    ----------
    options : Options
        Dataset sizes and repetition count.
    """

    CHAIN_STEPS: typing.ClassVar[int] = 3
    INGEST_ROWS: typing.ClassVar[int] = 10_000

    def __init__(self, options: Options) -> None:
        self._options = options
        self._scenarios: dict[str, Callable[[Graph], None]] = {
            "equality": Scenarios.equality,
            "range": Scenarios.range_filter,
            "type filter": Scenarios.type_filter,
            "node lookup": Scenarios.node_lookup,
            "quantified": Scenarios.quantified,
        }

    def run(self) -> None:
        """Run every scenario and print the report."""
        print(
            f"nodes={self._options.nodes} relationships={self._options.relationships} "
            f"repeats={self._options.repeats}"
        )
        graph = Graph.open(":memory:")
        try:
            created = Dataset(self._options.nodes, self._options.relationships).seed(graph)
            baseline = self._measure_queries(graph)
            graph.create_node_index("cycles")
            graph.create_relationship_index("since_cycle")
            indexed = self._measure_queries(graph)
            self._report_queries(baseline, indexed)
            if len(created) > self.CHAIN_STEPS:
                self._report_traversal(
                    graph,
                    created[0],
                    created[self.CHAIN_STEPS],
                )
        finally:
            graph.close()
        self._report_writes()
        self._report_ingestion()

    def _measure_queries(self, graph: Graph) -> dict[str, float]:
        """Time every query scenario in the current index state.

        Parameters
        ----------
        graph : Graph
            Populated graph.

        Returns
        -------
        dict[str, float]
            Median milliseconds keyed by scenario name.
        """
        return {
            name: Timer.measure(functools.partial(scenario, graph), self._options.repeats)
            for name, scenario in self._scenarios.items()
        }

    def _report_queries(
        self,
        baseline: dict[str, float],
        indexed: dict[str, float],
    ) -> None:
        """Print the query comparison table.

        Parameters
        ----------
        baseline : dict[str, float]
            Milliseconds without declared indexes.
        indexed : dict[str, float]
            Milliseconds with declared indexes.
        """
        print()
        print(f"{'scenario':<16}{'no index':>12}{'indexed':>12}{'speedup':>10}")
        for name, plain in baseline.items():
            faster = indexed[name]
            speedup = plain / faster if faster else float("inf")
            print(f"{name:<16}{plain:>10.2f}ms{faster:>10.2f}ms{speedup:>9.1f}x")

    def _report_traversal(self, graph: Graph, start: Node, end: Node) -> None:
        """Print the traversal comparison table.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node for the measured searches.
        end : Node
            End node three hops away along the seeded chain.
        """
        whole = {
            "traverse depth 1": self._measure_whole_traverse(graph, start, 1),
            "traverse depth 3": self._measure_whole_traverse(graph, start, 3),
            "paths limit 50": self._measure_whole_paths(graph, start, end),
            "shortest_path": self._measure_whole_shortest(graph, start, end),
        }
        bounded = {
            "traverse depth 1": self._measure_bounded_traverse(graph, start, 1),
            "traverse depth 3": self._measure_bounded_traverse(graph, start, 3),
            "paths limit 50": self._measure_bounded_paths(graph, start, end),
            "shortest_path": self._measure_bounded_shortest(graph, start, end),
        }
        print()
        print(f"{'traversal':<20}{'whole graph':>14}{'bounded':>12}{'speedup':>10}")
        for name, elapsed in whole.items():
            faster = bounded[name]
            speedup = elapsed / faster if faster else float("inf")
            print(f"{name:<20}{elapsed:>12.2f}ms{faster:>10.2f}ms{speedup:>9.1f}x")

    def _measure_whole_traverse(self, graph: Graph, start: Node, depth: int) -> float:
        """Time a whole-graph reachability search.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        depth : int
            Maximum depth.

        Returns
        -------
        float
            Median milliseconds, including snapshot capture.
        """
        return Timer.measure(
            functools.partial(self.whole_traverse, graph, start, depth),
            self._options.repeats,
        )

    @staticmethod
    def whole_traverse(graph: Graph, start: Node, depth: int) -> None:
        """Run reachability over a whole-graph snapshot.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        depth : int
            Maximum depth.
        """
        snapshot = AdjacencySnapshot(graph.find_nodes(), graph.find_relationships())
        list(ReachabilityEvaluator(snapshot, start, depth))

    def _measure_whole_paths(self, graph: Graph, start: Node, end: Node) -> float:
        """Time trail enumeration over a whole-graph snapshot.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.

        Returns
        -------
        float
            Median milliseconds, including snapshot capture.
        """
        return Timer.measure(
            functools.partial(self.whole_paths, graph, start, end),
            self._options.repeats,
        )

    @staticmethod
    def whole_paths(graph: Graph, start: Node, end: Node) -> None:
        """Enumerate trails over a whole-graph snapshot.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.
        """
        snapshot = AdjacencySnapshot(graph.find_nodes(), graph.find_relationships())
        list(TrailEnumerator(snapshot, start, end, 1, 3, limit=50))

    def _measure_whole_shortest(self, graph: Graph, start: Node, end: Node) -> float:
        """Time a whole-graph shortest-path search.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.

        Returns
        -------
        float
            Median milliseconds, including snapshot capture.
        """
        return Timer.measure(
            functools.partial(self.whole_shortest, graph, start, end),
            self._options.repeats,
        )

    @staticmethod
    def whole_shortest(graph: Graph, start: Node, end: Node) -> None:
        """Search a shortest path over a whole-graph snapshot.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.
        """
        snapshot = AdjacencySnapshot(graph.find_nodes(), graph.find_relationships())
        ShortestPathEvaluator(snapshot, start, end, max_depth=3).evaluate()

    def _measure_bounded_traverse(self, graph: Graph, start: Node, depth: int) -> float:
        """Time a bounded reachability search.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        depth : int
            Maximum depth.

        Returns
        -------
        float
            Median milliseconds.
        """
        return Timer.measure(
            functools.partial(self.bounded_traverse, graph, start, depth),
            self._options.repeats,
        )

    @staticmethod
    def bounded_traverse(graph: Graph, start: Node, depth: int) -> None:
        """Run the public bounded traversal.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        depth : int
            Maximum depth.
        """
        list(graph.traverse(start, max_depth=depth))

    def _measure_bounded_paths(self, graph: Graph, start: Node, end: Node) -> float:
        """Time bounded trail enumeration.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.

        Returns
        -------
        float
            Median milliseconds.
        """
        return Timer.measure(
            functools.partial(self.bounded_paths, graph, start, end),
            self._options.repeats,
        )

    @staticmethod
    def bounded_paths(graph: Graph, start: Node, end: Node) -> None:
        """Run the public bounded path enumeration.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.
        """
        list(graph.paths(start, end, max_depth=3, limit=50))

    def _measure_bounded_shortest(self, graph: Graph, start: Node, end: Node) -> float:
        """Time the public shortest-path search.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.

        Returns
        -------
        float
            Median milliseconds.
        """
        return Timer.measure(
            functools.partial(self.bounded_shortest, graph, start, end),
            self._options.repeats,
        )

    @staticmethod
    def bounded_shortest(graph: Graph, start: Node, end: Node) -> None:
        """Run the public shortest-path search.

        Parameters
        ----------
        graph : Graph
            Populated graph.
        start : Node
            Start node.
        end : Node
            End node.
        """
        graph.shortest_path(start, end, max_depth=3)

    def _report_writes(self) -> None:
        """Print write-throughput results for both index states."""
        print()
        print(f"{'write':<16}{'no index':>14}{'indexed':>14}")
        insert_plain = self._insert_rate(indexed=False)
        insert_indexed = self._insert_rate(indexed=True)
        update_plain = self._update_rate(indexed=False)
        update_indexed = self._update_rate(indexed=True)
        print(f"{'insert':<16}{insert_plain:>12.0f}/s{insert_indexed:>12.0f}/s")
        print(f"{'update':<16}{update_plain:>12.0f}/s{update_indexed:>12.0f}/s")

    def _report_ingestion(self) -> None:
        """Print merge and CSV import throughput."""
        print()
        print(f"{'ingestion':<16}{'rows/s':>14}")
        print(f"{'merge':<16}{self._merge_rate():>12.0f}/s")
        print(f"{'csv import':<16}{self._import_rate():>12.0f}/s")

    def _ingest_count(self) -> int:
        """Return the row count used by the ingestion scenarios.

        Returns
        -------
        int
            At most 10,000 rows, and never more than the seeded node count.
        """
        return min(self.INGEST_ROWS, max(self._options.nodes, 1))

    def _merge_rate(self) -> float:
        """Return rows merged per second by one ``UNWIND`` statement.

        Returns
        -------
        float
            Rows merged per second.
        """
        count = self._ingest_count()
        rows = [
            {
                "designation": f"merge-{position}",
                "cycles": position % Dataset.CYCLE_MODULUS,
            }
            for position in range(count)
        ]
        graph = Graph.open(":memory:")
        try:
            started = time.perf_counter()
            graph.query(
                "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
                "ON CREATE SET n.cycles = row.cycles",
                {"rows": rows},
            )
            elapsed = time.perf_counter() - started
            return count / elapsed if elapsed else float("inf")
        finally:
            graph.close()

    def _import_rate(self) -> float:
        """Return rows imported per second from a CSV file.

        Returns
        -------
        float
            Rows imported per second.
        """
        count = self._ingest_count()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "programs.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["designation", "cycles"])
                for position in range(count):
                    writer.writerow([f"import-{position}", position % Dataset.CYCLE_MODULUS])
            graph = Graph.open(":memory:")
            try:
                started = time.perf_counter()
                graph.import_file(
                    path,
                    "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
                    "ON CREATE SET n.cycles = toInteger(row.cycles)",
                    batch_size=1000,
                )
                elapsed = time.perf_counter() - started
                return count / elapsed if elapsed else float("inf")
            finally:
                graph.close()

    def _insert_rate(self, *, indexed: bool) -> float:
        """Return inserted nodes per second.

        Parameters
        ----------
        indexed : bool
            Whether the index exists before the inserts.

        Returns
        -------
        float
            Nodes inserted per second.
        """
        graph = Graph.open(":memory:")
        try:
            if indexed:
                graph.create_node_index("cycles")
            started = time.perf_counter()
            with graph.transaction() as transaction:
                for position in range(self._options.nodes):
                    transaction.add_node(
                        "Program",
                        designation=f"program-{position}",
                        cycles=position % Dataset.CYCLE_MODULUS,
                    )
            elapsed = time.perf_counter() - started
            return self._options.nodes / elapsed if elapsed else float("inf")
        finally:
            graph.close()

    def _update_rate(self, *, indexed: bool) -> float:
        """Return updated nodes per second.

        Parameters
        ----------
        indexed : bool
            Whether the index exists before the updates.

        Returns
        -------
        float
            Property updates applied per second.
        """
        graph = Graph.open(":memory:")
        try:
            count = min(self._options.nodes, 1000)
            with graph.transaction() as transaction:
                created = [
                    transaction.add_node("Program", cycles=position) for position in range(count)
                ]
            if indexed:
                graph.create_node_index("cycles")
            started = time.perf_counter()
            with graph.transaction() as transaction:
                for position, node in enumerate(created):
                    transaction.set_properties(node, cycles=position + 1)
            elapsed = time.perf_counter() - started
            return count / elapsed if elapsed else float("inf")
        finally:
            graph.close()


class CommandLine:
    """Parse arguments and start the benchmark."""

    DEFAULTS: typing.ClassVar[Options] = Options()

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        """Return the argument parser.

        Returns
        -------
        argparse.ArgumentParser
            Parser with the dataset size flags.
        """
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--nodes", type=int, default=cls.DEFAULTS.nodes)
        parser.add_argument("--relationships", type=int, default=cls.DEFAULTS.relationships)
        parser.add_argument("--repeats", type=int, default=cls.DEFAULTS.repeats)
        return parser

    @classmethod
    def run(cls) -> None:
        """Parse the command line and run the benchmark."""
        arguments = cls.parser().parse_args()
        Runner(
            Options(
                nodes=arguments.nodes,
                relationships=arguments.relationships,
                repeats=arguments.repeats,
            )
        ).run()


if __name__ == "__main__":
    CommandLine.run()
