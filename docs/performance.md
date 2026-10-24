# Performance

This page records what that engine costs on a machine, with the exact command that
produced each row. It is a single-machine baseline, not a guarantee.

## Method

The harness is `benchmarks/run.py`. It builds a themed synthetic graph in an in-memory
database, measures the same statements before and after declaring indexes, compares
whole-graph traversal with bounded traversal, and reports the median of several
repetitions. The query table also includes one bounded quantified path. Index declaration
and seeding happen outside the measured window.

```console
hatch run python benchmarks/run.py --nodes 20000 --relationships 60000
hatch run python benchmarks/run.py --nodes 200000 --relationships 400000
```

Dataset shape: one node in ten carries the `Program` label, every node carries a
`cycles` integer in a 97-value cycle and a `region` string, and one relationship in a
hundred has the `TRANSMISSION` type. All relationships carry a `since_cycle` integer.

Declared indexes for the measured runs: `cycles` on nodes and `since_cycle` on
relationships.

Environment: Linux 7.3, AMD Ryzen 9 6900HX, Python 3.14.8, SQLite 3.53.4, in-memory
database, single process, warm connection.

## Results

### 20,000 nodes / 60,000 relationships

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| Property equality | 7.38 ms | 0.46 ms | 16.0x |
| Property range | 8.11 ms | 1.44 ms | 5.6x |
| Selective type filter | 5.23 ms | 5.35 ms | 1.0x |
| `find_nodes` lookup | 8.39 ms | 0.17 ms | 49.3x |

| Write | No index | Indexed |
| --- | ---: | ---: |
| Insert nodes | 99,068/s | 87,402/s |
| Update property | 61,882/s | 54,903/s |

### 200,000 nodes / 400,000 relationships

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| Property equality | 75.20 ms | 2.71 ms | 27.7x |
| Property range | 83.02 ms | 14.54 ms | 5.7x |
| Selective type filter | 46.12 ms | 46.81 ms | 1.0x |
| `find_nodes` lookup | 81.48 ms | 1.77 ms | 46.0x |

| Write | No index | Indexed |
| --- | ---: | ---: |
| Insert nodes | 97,427/s | 78,726/s |
| Update property | 62,461/s | 56,551/s |

The scaling behaviour matters more than the ratios. Without an index, a property
equality filter grows with the number of candidate nodes: 7.7 ms at 20,000 nodes and
77 ms at 200,000. With the index, the same filter stays in the low milliseconds.

The type filter is the honest exception. The plan uses the relationship-type index
instead of scanning every relationship, but the measured statement still joins the
matching rows to their endpoint nodes and counts them, so wall-clock time is dominated by
that work at these selectivities. The index is doing its job; the query shape is what
sets the floor.

### Quantified matching

A bounded quantified pattern selects its start nodes through the same indexed predicates
and then expands the declared number of hops in the pattern engine. On the same
20,000-node / 60,000-relationship dataset:

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| `MATCH (a:Program {cycles: 36})-[:ALLIES_WITH*1..2]->(b)` | 14.70 ms | 5.46 ms | 2.7x |

The command is the same `benchmarks/run.py --nodes 20000 --relationships 60000` run
shown above; the `quantified` row is reported in its query table. The indexed gain comes
from finding the start nodes by `cycles` instead of scanning the node table. Expansion
work itself is bounded by the region the start node can reach within two hops, not by
the size of the database.

## What the numbers do not promise

- They are not a comparison with another database engine. They describe this engine on
  one machine with one synthetic workload.
- They are in-memory numbers. A file-backed database adds I/O and write-ahead-log
  traffic, and the first query after opening a cold file is slower.
- They are single-threaded. The library uses one connection and is not thread-safe.
- They include result materialization. Every statement returns a fully materialized
  result, so a query that projects many large rows pays for those rows.
- Index benefit depends on selectivity. An index on a key with few distinct values, or a
  filter that matches most rows, can be slower than a scan.
- Write throughput falls by roughly 10 to 15 percent per declared index on the measured
  workload, because SQLite maintains the index inside the same transaction.

## Traversal

Traversal captures only the region its depth and direction bounds can reach. The
whole-graph column reproduces the previous access pattern: build a snapshot from every
node and relationship, then search it. The bounded column uses the public entry points.
Measured on the 20,000-node / 60,000-relationship dataset, median of three repetitions:

| Operation | Whole graph | Bounded | Speedup |
| --- | ---: | ---: | ---: |
| `traverse`, depth 1 | 343.47 ms | 0.09 ms | 3779x |
| `traverse`, depth 3 | 335.52 ms | 0.25 ms | 1328x |
| `paths`, depth 3, limit 50 | 333.75 ms | 0.24 ms | 1364x |
| `shortest_path`, depth 3 | 329.96 ms | 0.13 ms | 2465x |

The important property is the shape, not the ratio. Every whole-graph figure is roughly
the cost of reading the database, independent of the answer. The bounded figures are
neighbourhood-sized and grow with the explored region. At 200,000 nodes and 400,000
relationships the whole-graph figures rise to about 3.8 seconds per call while the
bounded figures stay at a fraction of a millisecond, which is the scaling behaviour the
change is for. An unbounded `shortest_path` on a dense component still explores that
component, because that region is the answer's search space.
