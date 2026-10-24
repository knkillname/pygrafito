# pygrafito

[![PyPI - Version](https://img.shields.io/pypi/v/pygrafito.svg)](https://pypi.org/project/pygrafito)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pygrafito.svg)](https://pypi.org/project/pygrafito)

`pygrafito` is an embedded property graph for Python, persisted in a single
SQLite database. It has no runtime dependencies outside the standard library:
nodes carry labels and strict typed properties, relationships are directed and
typed, and writes run in explicit ACID transactions. Every Python example in
this README is executed by the test suite.

## Table of Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Command-line shell](#command-line-shell)
- [Nodes, labels, and properties](#nodes-labels-and-properties)
- [Relationships](#relationships)
- [Transactions](#transactions)
- [Deletion](#deletion)
- [Traversal](#traversal)
- [Query language](#query-language)
- [Indexes](#indexes)
- [Uniqueness constraints](#uniqueness-constraints)
- [Import](#import)
- [Data interop](#data-interop)
- [Performance](#performance)
- [Persistence](#persistence)
- [License](#license)

## Installation

```console
pip install pygrafito
```

`pygrafito` requires Python 3.14 or newer and SQLite 3.38 or newer.

## Quick start

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "graph.db"
    with Graph.open(path) as graph:
        ada = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
        grace = graph.add_node("Program", designation="Quorra", cycles=37)
        knows = graph.add_relationship(ada, "ALLIES_WITH", grace, since_cycle=2020)

        graph.set_properties(ada, cycles=37)
        print(graph.node(ada.id)["cycles"])          # 37
        print(graph.relationship(knows.id)["since_cycle"])  # 2020

    with Graph.open(path) as graph:
        people = graph.find_nodes("Program")
        print(sorted(node["designation"] for node in people))  # ['Kevin Flynn', 'Quorra']
```

Open `":memory:"` instead of a filesystem path when the graph should live only
for the lifetime of the handle.

## Command-line shell

The `pygrafito` command opens an interactive shell on a database file;
`python -m pygrafito` is equivalent. With no database argument the shell uses a
transient in-memory graph.

```console
$ pygrafito grid.db
pygrafito 0.6.0 | grid.db | type ".help" for commands
grid.db> CREATE (n:Program {designation: 'Tron', cycles: 40});
1 node created
grid.db> MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles;
+------+--------+
| name | cycles |
+------+--------+
| Tron | 40     |
+------+--------+
1 row
```

Run a one-off statement with `-c`, a script with `-f`, or pipe input. Results go
to standard output and diagnostics to standard error, so a script can select a
machine-readable format:

```console
$ pygrafito grid.db -c "MATCH (n:Program) RETURN n.designation AS name;" --format json
[
  {
    "name": "Tron"
  }
]
$ cat seed.txt | pygrafito grid.db --readonly
```

See [`docs/cli.md`](docs/cli.md) for the statement rules, output modes, shell
commands, transactions, and maintenance commands.

## Nodes, labels, and properties

Nodes are created with zero or more non-empty string labels and keyword
properties. `find_nodes` matches nodes that carry every given label and every
given exact property value. Property matching is type-sensitive and list order
matters.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Program", "ISO", designation="Kevin Flynn", cycles=36)
    print(sorted(ada.labels))  # ['ISO', 'Program']
    print(ada["designation"])         # Kevin Flynn

    ada = graph.add_labels(ada, "SystemMonitor")
    ada = graph.remove_labels(ada, "ISO")
    ada = graph.set_properties(ada, cycles=37)
    print(dict(ada))           # {'cycles': 37, 'designation': 'Kevin Flynn'}

    found = graph.find_nodes("Program", cycles=37)
    print([node["designation"] for node in found])  # ['Kevin Flynn']
```

Property values are booleans, signed 64-bit integers, finite floats, strings,
or homogeneous lists of those scalars. Maps, nested lists, `None`, NaN, and
infinities are rejected. Assigning `None` removes a property. Property keys may
contain dots or spaces:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    node = graph.add_node(**{"a.b": 1, "a b": 2})
    print(dict(node))  # {'a b': 2, 'a.b': 1}
```

## Relationships

Relationships are directed, have one non-empty type, and connect existing
nodes. Reading a relationship preserves its stored start and end nodes.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    first = graph.add_node("Program", designation="Kevin Flynn")
    second = graph.add_node("Program", designation="Quorra")
    relationship = graph.add_relationship(first, "ALLIES_WITH", second, since_cycle=2020)
    print(relationship.start_id, relationship.rel_type, relationship.end_id)
    print(relationship["since_cycle"])  # 2020

    found = graph.find_relationships("ALLIES_WITH", since_cycle=2020)
    print([item.id for item in found])  # [relationship.id]
```

## Transactions

Each convenience write is atomic on its own. Use `graph.transaction()` to group
several writes into one commit; leaving the block with an exception rolls all of
them back.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    with graph.transaction() as tx:
        ada = tx.add_node("Program", designation="Kevin Flynn")
        grace = tx.add_node("Program", designation="Quorra")
        tx.add_relationship(ada, "ALLIES_WITH", grace)
        tx.set_properties(ada, cycles=36)

    print(graph.node(ada.id)["cycles"])  # 36
```

Writes use `BEGIN IMMEDIATE`, and one `Graph` owns exactly one connection. A
graph handle is not thread-safe; using it from another thread raises an error
rather than sharing the connection silently.

A transaction can also be driven without a context block, which is useful when
several statements are decided at runtime:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    active = graph.transaction().begin()
    active.add_node("Program", designation="Tron")
    active.rollback()

    print(graph.query("MATCH (n) RETURN count(*) AS total").rows[0]["total"])  # 0
```

## Deletion

Relationships are deleted directly. A node with relationships is protected
until deletion is requested with `detach=True`, which removes incident
relationships first.

```python
from pygrafito import ConnectedNodeError, Graph

with Graph.open(":memory:") as graph:
    first = graph.add_node("Program")
    second = graph.add_node("Program")
    graph.add_relationship(first, "ALLIES_WITH", second)

    try:
        graph.delete(first)
    except ConnectedNodeError:
        print("delete with detach=True instead")

    graph.delete(first, detach=True)
```

## Traversal

Traversal reads a consistent snapshot that is materialized when the call is
made, so writes performed later do not change an in-progress result. Only the
region the depth bound can reach is materialized, so traversal cost tracks the
size of the answer rather than the size of the database.

`traverse` yields every node reachable within `max_depth` exactly once, together
with its shortest depth. The start node is not yielded.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Program", designation="Kevin Flynn")
    grace = graph.add_node("Program", designation="Quorra")
    bob = graph.add_node("Program", designation="Sam Flynn")
    graph.add_relationship(ada, "ALLIES_WITH", grace)
    graph.add_relationship(grace, "ALLIES_WITH", bob)

    steps = graph.traverse(ada, max_depth=2)
    print([(step.node["designation"], step.depth) for step in steps])
    # [('Quorra', 1), ('Sam Flynn', 2)]
```

`shortest_path` returns one path with the fewest relationships, or `None` when
no path exists within the given direction, type filter, and optional
`max_depth`. A node has a zero-length path to itself.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Program", designation="Kevin Flynn")
    grace = graph.add_node("Program", designation="Quorra")
    bob = graph.add_node("Program", designation="Sam Flynn")
    graph.add_relationship(ada, "ALLIES_WITH", grace)
    graph.add_relationship(grace, "ALLIES_WITH", bob)

    path = graph.shortest_path(ada, bob)
    print(path.length)  # 2
    print([node["designation"] for node in path.nodes])  # ['Kevin Flynn', 'Quorra', 'Sam Flynn']
```

`paths` enumerates relationship-unique trails between two nodes. Nodes may
repeat within a path, but each relationship may be used at most once. Both a
minimum and maximum depth are supported, and `max_depth` is required.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    start = graph.add_node("Grid")
    left = graph.add_node("Safehouse")
    right = graph.add_node("Outlands")
    end = graph.add_node("Portal")
    graph.add_relationship(start, "GRID_LINK", left)
    graph.add_relationship(start, "GRID_LINK", right)
    graph.add_relationship(left, "GRID_LINK", end)
    graph.add_relationship(right, "GRID_LINK", end)

    paths = graph.paths(start, end, min_depth=2, max_depth=2)
    print(len(list(paths)))  # 2
```

Use `direction=Direction.INCOMING` or `Direction.BOTH`, and restrict followed
relationship types with `types=[...]`. An empty or omitted type collection means
all types.

```python
from pygrafito import Direction, Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Program", designation="Kevin Flynn")
    grace = graph.add_node("Program", designation="Quorra")
    graph.add_relationship(ada, "ALLIES_WITH", grace)
    graph.add_relationship(grace, "TRUSTS", ada)

    incoming = graph.traverse(
        grace,
        max_depth=1,
        direction=Direction.INCOMING,
        types=["ALLIES_WITH"],
    )
    print([step.node["designation"] for step in incoming])  # ['Kevin Flynn']
```

Path enumeration is exponential in the worst case because a graph can contain
many trails between the same pair of nodes. Always set the smallest useful
`max_depth`, and pass `limit` when only the first few paths are needed. Paths
are generated lazily, so stopping iteration early stops further computation.

## Query language

`Graph.query` executes one statement and returns a materialized `QueryResult`
with ordered columns and immutable rows. A statement combines an optional
fixed-length `MATCH` pattern with an optional `WHERE` filter, optional write
clauses, and an optional `RETURN` projection. `DISTINCT`, `ORDER BY`, `SKIP`, and
`LIMIT` are supported, as are `$name` parameters.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    result = graph.query(
        "MATCH (p:Program {designation: $name}) RETURN p.designation AS name, p.cycles",
        {"name": "Quorra"},
    )
    print(result.columns)  # ('name', 'p.cycles')
    print([tuple(row.values()) for row in result])  # [('Quorra', 37)]
```

Patterns support labels, relationship types, all three directions, property
maps, path variables, and repeated variables. Projections can contain scalar
functions and aggregates.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    tron = graph.add_node("Program", designation="Tron", cycles=40)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(quorra, "ALLIES_WITH", tron)

    result = graph.query(
        "MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) "
        "RETURN a.designation AS source, type(r) AS kind, b.designation AS target "
        "ORDER BY target"
    )
    print([tuple(row.values()) for row in result])
    # [('Kevin Flynn', 'ALLIES_WITH', 'Quorra'), ('Quorra', 'ALLIES_WITH', 'Tron')]
```

Comma-separated patterns in one `MATCH` join on shared variables, and several
`MATCH` clauses chain as stages:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    tron = graph.add_node("Program", designation="Tron")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(quorra, "ALLIES_WITH", tron)

    result = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b), (b)-[:ALLIES_WITH]->(c) "
        "RETURN a.designation AS start, c.designation AS end"
    )
    print([tuple(row.values()) for row in result])  # [('Kevin Flynn', 'Tron')]

    chained = graph.query(
        "MATCH (a:Program {designation: 'Kevin Flynn'}) "
        "MATCH (a)-[:ALLIES_WITH]->(b) RETURN b.designation AS name"
    )
    print([row["name"] for row in chained])  # ['Quorra']
```

An `OPTIONAL MATCH` is a left join: unmatched rows survive with nulls.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    sam = graph.add_node("Program", designation="Sam Flynn")
    graph.add_relationship(kevin, "TRUSTS", sam)

    result = graph.query(
        "MATCH (a:Program) OPTIONAL MATCH (a)-[:TRUSTS]->(b) "
        "RETURN a.designation AS name, b.designation AS trusted ORDER BY name"
    )
    print([tuple(row.values()) for row in result])
    # [('Kevin Flynn', 'Sam Flynn'), ('Sam Flynn', None)]
```

A `WITH` stage projects rows into a new scope, so grouped results can be
filtered, ordered, and paginated before the final projection:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    tron = graph.add_node("Program", designation="Tron")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(kevin, "ALLIES_WITH", tron)

    result = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b) "
        "WITH a.designation AS name, count(*) AS allies "
        "WHERE allies > 1 RETURN name, allies"
    )
    print([tuple(row.values()) for row in result])  # [('Kevin Flynn', 2)]
```

A quantified relationship follows a bounded number of hops. Trails are
relationship-unique, and the relationship variable binds the traversed list:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    tron = graph.add_node("Program", designation="Tron")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(quorra, "ALLIES_WITH", tron)

    result = graph.query(
        "MATCH (a:Program {designation: 'Kevin Flynn'})-[r:ALLIES_WITH*1..2]->(b) "
        "RETURN b.designation AS name, size(r) AS hops ORDER BY name"
    )
    print([tuple(row.values()) for row in result])  # [('Quorra', 1), ('Tron', 2)]
```

`UNWIND` expands a list into rows and feeds later stages, so one statement can
merge a batch of rows:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    rows = [
        {"designation": "Tron", "cycles": 40},
        {"designation": "Quorra", "cycles": 37},
        {"designation": "Tron", "cycles": 41},
    ]
    result = graph.query(
        "UNWIND $rows AS row "
        "MERGE (n:Program {designation: row.designation}) "
        "ON CREATE SET n.cycles = row.cycles "
        "ON MATCH SET n.cycles = n.cycles + 1 "
        "RETURN n.designation AS name, n.cycles AS cycles ORDER BY name",
        {"rows": rows},
    )
    print([tuple(row.values()) for row in result])
    # [('Quorra', 37), ('Tron', 40), ('Tron', 41)]
    print(result.summary.created_nodes)  # 2
```

`MERGE` matches its whole pattern and creates the unbound elements when no match
exists. It runs once per input row, so a creation made by one row is visible to
later rows in the same statement. A merged pattern uses one explicit type per
relationship and the outgoing direction.

Use `Graph.prepare` when the same statement runs more than once. Prepared
columns are available before the first execution, and parameters may change on
each call.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_node("Program", designation="Tron", cycles=40)

    prepared = graph.prepare(
        "MATCH (n:Program) WHERE n.cycles > $minimum RETURN count(*) AS total"
    )
    print(prepared.columns)  # ('total',)
    print(prepared.execute({"minimum": 36}).rows[0]["total"])  # 2
```

A statement can also write. `CREATE` adds nodes and relationships, `SET` and
`REMOVE` change properties and labels, and `DELETE` or `DETACH DELETE` removes
elements. `RETURN` is optional and a result exposes a `summary` with the counts
of the changes applied:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)

    created = graph.query(
        "MATCH (a:Program {designation: 'Kevin Flynn'}) "
        "CREATE (b:Program {designation: 'Tron', cycles: 40}) "
        "CREATE (a)-[r:TRUSTS]->(b) "
        "RETURN b.designation AS name"
    )
    print([row["name"] for row in created])  # ['Tron']
    print(created.summary.created_nodes)  # 1

    graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n:SystemMonitor")
    print(graph.query("MATCH (n:SystemMonitor) RETURN count(*) AS c").rows[0]["c"])  # 1
```

See [`docs/query-language.md`](docs/query-language.md) for the complete grammar,
write clauses, mutation cardinality, value and null semantics, functions,
aggregation, ordering rules, parameters, errors, and the supported core profile.

## Indexes

Property filters can use a declared index. An index is key-scoped, persists in the
database file, and never changes what a query returns; it only changes how much work the
engine does. See [`docs/indexes.md`](docs/indexes.md) for what indexes accelerate, what
they cost, and when the planner ignores one.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)

    index = graph.create_node_index("cycles")
    print(index.kind.value, index.key)             # node cycles
    print([item.key for item in graph.indexes()])  # ['cycles']

    result = graph.query(
        "MATCH (n:Program) WHERE n.cycles = 37 RETURN n.designation AS name"
    )
    print([row["name"] for row in result])  # ['Quorra']

    plan = graph.explain("MATCH (n:Program) WHERE n.cycles = 37 RETURN n")
    print(any("pygrafito_idx_node_" in line for line in plan))  # True

    graph.drop_index(index)
```

## Uniqueness constraints

A uniqueness constraint keeps one property value distinct inside one label or one relationship
type. The database enforces it on every write, including writes made outside the library, and a
violation raises `ConstraintViolationError` with the offending value and the existing holder.
See [`docs/constraints.md`](docs/constraints.md) for type sensitivity, exemptions, and
transaction behavior.

```python
from pygrafito import ConstraintViolationError, Graph

with Graph.open(":memory:") as graph:
    graph.create_node_uniqueness_constraint("Program", "designation")
    tron = graph.add_node("Program", designation="Tron")

    try:
        graph.add_node("Program", designation="Tron")
    except ConstraintViolationError as error:
        print(error.value, error.existing)  # Tron 1

    quorra = graph.add_node("Program", designation="Quorra")
    print(sorted(node["designation"] for node in graph.find_nodes("Program")))
    # ['Quorra', 'Tron']
    graph.drop_constraint(graph.constraints()[0])
    print(graph.constraints())  # ()
```

## Import

`Graph.import_file` and `Graph.import_rows` bind each batch of rows to `$rows`
and run one write statement. The statement is the mapping: there is no separate
column configuration. JSONL preserves value types; CSV values are strings, and
the statement converts them with `toInteger`, `toFloat`, or `toString`. Batches
commit independently by default; pass `atomic=True` to wrap the whole import in
one transaction.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "programs.jsonl"
    path.write_text(
        '{"designation": "Kevin Flynn", "cycles": 36}\n'
        '{"designation": "Quorra", "cycles": 37}\n',
        encoding="utf-8",
    )
    with Graph.open(":memory:") as graph:
        summary = graph.import_file(
            path,
            "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
            "ON CREATE SET n.cycles = row.cycles",
        )
        print(summary.rows)                    # 2
        print(summary.mutations.created_nodes)  # 2
        print(sorted(node["designation"] for node in graph.find_nodes("Program")))
        # ['Kevin Flynn', 'Quorra']
```

In-memory rows use the same statement through `Graph.import_rows`:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    summary = graph.import_rows(
        "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
        [{"designation": "Tron"}, {"designation": "Clu"}],
    )
    print(summary.rows)  # 2
```

The shell exposes the same importer as `.import`; see
[`docs/cli.md`](docs/cli.md). See [`docs/import.md`](docs/import.md) for formats,
batching, atomicity, and failure reporting.

## Data interop

`Graph.export_jsonl` writes a strict, versioned JSONL snapshot of the graph. The file starts with
a header carrying the format version and element counts, followed by tagged node and
relationship records in deterministic order. Export streams the graph inside one read snapshot,
so the file always describes one committed state.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    destination = pathlib.Path(directory) / "grid.jsonl"
    with Graph.open(":memory:") as graph:
        graph.add_node("Program", designation="Tron")
        graph.add_node("Program", designation="Quorra")
        summary = graph.export_jsonl(destination)
        print(summary.nodes)          # 2
        print(summary.relationships)  # 0

    with Graph.open(":memory:") as restored:
        summary = restored.restore_jsonl(destination)
        print(summary.nodes)  # 2
        print(
            sorted(node["designation"] for node in restored.find_nodes("Program"))
        )  # ['Quorra', 'Tron']
```

An existing destination is refused unless `overwrite=True` is passed, and the live database path
and its journal sidecars are never valid destinations. Restore requires an empty target by
default; pass `replace=True` to replace a populated graph atomically. A file also exposes
read-only SQL views for external readers, versioned through `graph_meta`; see
[`docs/interop.md`](docs/interop.md) for the record grammar, value rules, destination guarantees,
restore behavior, and the view schema.

## Performance

A declared index changes the cost profile of a filter. On a 200,000-node in-memory
graph, a property equality filter measured 77 ms without an index and 2.3 ms with one;
the same filter takes 7.7 ms at 20,000 nodes, so the unindexed cost tracks the number of
candidate nodes while the indexed cost stays in the low milliseconds. Maintaining an
index costs roughly 10 to 15 percent of insert and update throughput.

These are single-machine numbers for one synthetic workload. They are not a comparison
with another database engine, not a promise, and not file-backed. See
[`docs/performance.md`](docs/performance.md) for the dataset, the exact command that
produced each row, and the cases where the planner still scans.

## Persistence

A file-backed graph persists nodes, labels, relationships, and properties
across close and reopen. The database uses write-ahead logging and reports the
mode it obtained through `Graph.journal_mode`; SQLite may reuse an integer id
after an element is deleted, so treat ids as handles for live elements rather
than permanent external keys. See [`docs/embedding.md`](docs/embedding.md) for
thread affinity, lock waits, read snapshots, and the rule that refuses an
unrelated SQLite file.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "graph.db"
    with Graph.open(path) as graph:
        node = graph.add_node("Program", designation="Kevin Flynn")

    with Graph.open(path) as graph:
        print(graph.node(node.id)["designation"])  # Kevin Flynn
```

A file can also be opened read-only. A read-only handle serves reads, queries, and traversal,
rejects every write with `ReadOnlyError`, and never creates a missing file.

```python
import pathlib
import tempfile

from pygrafito import Graph, ReadOnlyError

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "graph.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Kevin Flynn")

    with Graph.open(path, readonly=True) as graph:
        print(graph.query("MATCH (n:Program) RETURN n.designation AS name").rows[0]["name"])
        # Kevin Flynn
        try:
            graph.add_node("Program", designation="Tron")
        except ReadOnlyError:
            print("writes are rejected")  # writes are rejected
```

`Graph.backup_to` writes a consistent copy of a live database, and `Graph.check_integrity`
reports structural problems. Both work on a read-only handle:

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "graph.db"
    backup = pathlib.Path(directory) / "backup.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Tron")
        graph.backup_to(backup)
        print(graph.check_integrity())  # ()

    with Graph.open(backup) as copy:
        print(copy.node(1)["designation"])  # Tron
```

## License

`pygrafito` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
