# Performance

This page records what the engine costs on one machine, with the exact command that produced each
row. It is a single-machine baseline, not a guarantee. For the task of making a filter faster, see
[Speed up property filters](../guides/indexes.md).

## Method

The harness is the `benchmarks` module. It builds a themed synthetic graph in an in-memory
database, measures the same statements before and after declaring indexes, compares
whole-graph traversal with bounded traversal, and reports the median of several
repetitions. The query table also includes one bounded quantified path. Index declaration
and seeding happen outside the measured window.

```console
hatch run python -m benchmarks.run --nodes 20000 --relationships 60000
hatch run python -m benchmarks.run --nodes 200000 --relationships 400000
```

Dataset shape: one node in ten carries the `Program` label, every node carries a
`cycles` integer in a 97-value cycle and a `region` drawn from the sample place vocabulary, and
one relationship in a hundred carries the `TRANSMISSION` label. One relationship in ten is
undirected. Every relationship carries a `since_cycle` integer. The generator lives in
`examples/support/dataset.py` and is shared with the example algorithms lane.

Declared indexes for the measured runs: `cycles` on nodes and `since_cycle` on
relationships. Relationship labels have their own structural index.

Environment: Linux 7.3, AMD Ryzen 9 6900HX, Python 3.14.8, SQLite 3.53.4, in-memory
database, single process, warm connection.

## Results

### 20,000 nodes / 60,000 relationships

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| Property equality | 9.68 ms | 0.53 ms | 18.4x |
| Property range | 12.47 ms | 1.59 ms | 7.8x |
| Label filter (no bound endpoint) | 0.81 ms | 0.65 ms | 1.2x |
| Direction filter (indexed start) | 42.53 ms | 0.41 ms | 104.9x |
| `find_nodes` lookup | 9.84 ms | 0.20 ms | 49.2x |
| Composition (`LET` + `GROUP BY` + `NEXT`) | 22.57 ms | 20.28 ms | 1.1x |

The composition row exercises a `LET`, an intermediate `RETURN ... GROUP BY`, and a
`NEXT YIELD` segment in one statement. It is one extra operation per segment and
one grouped scan, so the measured cost is within run-to-run noise of the
equivalent `WITH` pipeline; the ordered pipeline does not add a second
transaction or a second budget.

| Write | No index | Indexed |
| --- | ---: | ---: |
| Insert nodes | 61,631/s | 53,338/s |
| Update property | 52,053/s | 44,211/s |

### 200,000 nodes / 400,000 relationships

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| Property equality | 92.96 ms | 2.78 ms | 33.4x |
| Property range | 102.94 ms | 16.69 ms | 6.2x |
| Label filter (no bound endpoint) | 3.46 ms | 3.47 ms | 1.0x |
| Direction filter (indexed start) | 195.46 ms | 1.12 ms | 174.5x |
| `find_nodes` lookup | 88.51 ms | 1.65 ms | 53.5x |

| Write | No index | Indexed |
| --- | ---: | ---: |
| Insert nodes | 64,590/s | 52,922/s |
| Update property | 56,317/s | 51,825/s |

The scaling behaviour matters more than the ratios. Without an index, a property
equality filter grows with the number of candidate nodes: 9.7 ms at 20,000 nodes and
93 ms at 200,000. With the index, the same filter stays in the low milliseconds.

The label filter is the structural-index case: a relationship label lookup without a
bound endpoint uses the label index and stays in the low milliseconds at both sizes. The
direction filter starts from a `cycles`-indexed node and follows outgoing relationships;
the property index selects the start set, then endpoint indexes drive the expansion. The
unindexed direction figure is the cost of scanning the start candidates, not of
traversing the edges.

### Quantified matching

A bounded quantified pattern selects its start nodes through the same indexed predicates
and then expands the declared number of hops in the pattern engine. On the same
20,000-node / 60,000-relationship dataset:

| Scenario | No index | Indexed | Speedup |
| --- | ---: | ---: | ---: |
| `MATCH (a:Program {cycles: 36})-[:ALLIES_WITH*1..2]->(b)` | 16.33 ms | 6.88 ms | 2.4x |

The command is the same `python -m benchmarks.run --nodes 20000 --relationships 60000` run
shown above; the `quantified` row is reported in its query table. The indexed gain comes
from finding the start nodes by `cycles` instead of scanning the node table. Expansion
work itself is bounded by the region the start node can reach within two hops, not by
the size of the database.

### Path search

A searched pattern always runs in the pattern engine, including a pattern whose relationships are
all fixed. Start nodes still come from the indexed node predicates, but the fixed path loses the
SQL cross-product plan and expands through the same live adjacency source as an open walk. Search
expands in nondecreasing length order: each candidate relationship examined counts once against
the expansion budget, while selecting or deduplicating a completed path adds no expansion.

Per partition, the evaluator keeps at most the selection limit plus one arrival for each state key.
`ANY` and `ANY SHORTEST` keep one result; `SHORTEST k` keeps up to `k`; `ALL SHORTEST` keeps the
arrivals at the minimum length. State keys include the start and current node, pattern position,
mode memory, and element bindings, so a longer arrival to the same key is discarded before it can
expand. This bound, the expansion budget, and a final `LIMIT` keep a cyclic open `WALK` search
finite. A fixed searched path trades index pushdown for one selection implementation; measure it
with the same harness when a fixed route query is latency-sensitive.

### Grouped path patterns

A pattern with a grouped or juxtaposed term always runs in the pattern engine. Opening a group
does not add SQL pushdown, even when every bound is closed, because the group repeats a whole term
and produces list bindings. Start nodes still come from the indexed node predicates; iterations
then expand through the same live adjacency source as an open walk. Each relationship examined
counts once against the expansion budget, and a group iteration adds no separate counter because
the progress rule guarantees at least one relationship per iteration.

Group variables grow with the number of iterations and with the number of distinct elements
bound. For a bounded group the memory is proportional to the selected path and the iteration
count; for an open `WALK` group, use `LIMIT`, `TRAIL`, or a search prefix so the budget stops the
walk before list accumulation becomes large. Nested groups flatten their lists in traversal order,
so their memory is the sum of the nested iteration counts. Keep grouped fixtures small in the guide
and tour; the fixed grouped cases are not an index-pushdown benchmark.

### Path modes

The harness measures the same fixed two-hop pattern under `WALK` and `TRAIL`. `WALK` adds no
uniqueness predicate; `TRAIL` adds one relationship-id inequality for each pair of relationship
positions in the path.

| Scenario | No index | Indexed |
| --- | ---: | ---: |
| `MATCH WALK (a:Program {cycles: 36})-[r]->(b)-[s]->(c)` | 1.94 ms | 2.30 ms |
| `MATCH TRAIL (a:Program {cycles: 36})-[r]->(b)-[s]->(c)` | 1.75 ms | 2.06 ms |

At this scale the predicate cost is within run-to-run noise (`repeats=3`), so the mode does not
change the access plan. The same measurement at 200,000 nodes / 400,000 relationships gives
19.97 ms for `WALK` and 21.48 ms for `TRAIL` without declared indexes, and 19.70 ms and 19.90 ms
with them; the difference remains within noise. The query budget defaults are 1,000,000
relationship expansions and 100,000 intermediate rows, with no time limit. Every benchmark
scenario stays well below both counters, so the budget never fires in these measurements; it
exists for cyclic and dense graphs that the synthetic workload does not model.

The command is the same `python -m benchmarks.run --nodes 20000 --relationships 60000` run shown
above; the `walk path` and `trail path` rows are reported in its query table. The 200,000-node
figures come from `python -m benchmarks.run --nodes 200000 --relationships 400000`.

### Open-ended traversal

The harness also seeds a dedicated directed cycle of 1,000 programs and measures the open forms
in memory and in a temporary file-backed database. The cycle keeps the number of expansion steps
equal to the number of produced rows, so the rates describe traversal and row delivery rather
than a particular dataset's fan-out. The command is the same
`python -m benchmarks.run --nodes 20000 --relationships 60000` run shown above; the
`open walk` table is reported after ingestion.

| Scenario | Rows | Memory | File-backed | Memory rows/s | File-backed rows/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Open `WALK`, `LIMIT 100` | 100 | 8.20 ms | 8.18 ms | 12,199 | 12,230 |
| Open `WALK`, `LIMIT 1000` | 1,000 | 93.22 ms | 97.26 ms | 10,727 | 10,281 |
| Open `TRAIL`, `ORDER BY` | 999 | 110.81 ms | 109.20 ms | 9,016 | 9,148 |
| Open `TRAIL`, aggregation | 999 | 101.65 ms | 100.30 ms | 9,828 | 9,960 |

`LIMIT` is the important lever. The 100-row walk does one tenth of the expansion work of the
1,000-row walk and returns in roughly one tenth of the time, because the evaluator closes the
stream once the demand is met. The rows-per-second rate is stable across the two sizes, which is
the shape to expect from a per-hop walk.

The `TRAIL` rows are full-evaluation shapes. The 1,000-program cycle has 999 relationship-unique
trails from the start node, and both `ORDER BY` and aggregation consume all of them before
returning. Sorting adds about 9 ms over aggregation at this size. A file-backed database is
close to the in-memory figure here because the measured cycle fits in the page cache; a cold
file still pays the first-read and write-ahead-log costs described under "What the numbers do
not promise".

### Ingestion

The harness also measures a 10,000-row `UNWIND` + `MERGE` statement and the
equivalent 10,000-row CSV import on fresh in-memory graphs. The command is the
same `python -m benchmarks.run --nodes 20000 --relationships 60000` run shown above.

| Scenario | Rows per second |
| --- | ---: |
| `UNWIND` + `MERGE`, one statement | 484/s |
| CSV `import_file`, batch size 1000 | 484/s |

The merge path matches and creates one row at a time, and it compiles the
single-node match for each row. That is the price of sequential visibility: a
later row must see an earlier row's creation. At roughly 480 rows/s, a
single-node lookup fast path is needed before this becomes a bulk loader; the
current numbers favor correctness and a small implementation over throughput.

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
| `traverse`, depth 1 | 596.50 ms | 0.15 ms | 4076x |
| `traverse`, depth 3 | 574.50 ms | 0.51 ms | 1123x |
| `paths`, depth 3, limit 50 | 563.09 ms | 0.51 ms | 1100x |
| `shortest_path`, depth 3 | 595.11 ms | 0.32 ms | 1837x |

The important property is the shape, not the ratio. Every whole-graph figure is roughly
the cost of reading the database, independent of the answer. The bounded figures are
neighbourhood-sized and grow with the explored region. At 200,000 nodes and 400,000
relationships the whole-graph figures rise to about 5 seconds per call while the
bounded figures stay at a fraction of a millisecond, which is the scaling behaviour the
change is for. An unbounded `shortest_path` on a dense component still explores that
component, because that region is the answer's search space.
