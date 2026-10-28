# Five-minute quickstart

This page gets you from an empty Python process to a persisted graph you can query, traverse, and
reopen. Every Python block is a complete program, so you can copy one into a file and run it.

## 1. Install

```{code-block} console
pip install pygrafito
```

`pygrafito` requires Python 3.14 or newer and SQLite 3.38 or newer.

## 2. Open a graph

`Graph.open(":memory:")` creates a graph that lives for the lifetime of the handle. Use a
filesystem path when the graph should survive the process.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    print(graph.journal_mode)  # memory
```

A `Graph` owns one SQLite connection. Keep it in the thread that opened it, and use the context
manager so the connection is closed deterministically.

## 3. Add nodes, labels, and properties

Nodes carry zero or more labels and keyword properties. Property values are booleans, signed
64-bit integers, finite floats, strings, or homogeneous lists of those values.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", "User", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)

    print(sorted(kevin.labels))  # ['Program', 'User']
    print(quorra["designation"], quorra["cycles"])  # Quorra 37
```

`find_nodes` matches every supplied label and every exact property value:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_node("ISO", designation="Quorra", cycles=37)

    found = graph.find_nodes("Program", cycles=37)
    print([node["designation"] for node in found])  # ['Quorra']
```

## 4. Add a relationship

Relationships are directed and typed. They can carry properties of their own.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    alliance = graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    print(alliance.start_id, alliance.labels, alliance.directed, alliance.end_id)
    print(alliance["since_cycle"])  # 2020

    found = graph.find_relationships("ALLIES_WITH", since_cycle=2020)
    print([relationship.id for relationship in found])  # [alliance.id]
```

## 5. Query the graph

`Graph.query` runs one pattern-matching statement. `$name` is a parameter, so values are never
interpolated into the statement text.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    result = graph.query(
        "MATCH (program:Program)-[alliance:ALLIES_WITH]->(ally:Program) "
        "WHERE program.designation = $name "
        "RETURN ally.designation AS ally, alliance.since_cycle AS since",
        {"name": "Kevin Flynn"},
    )
    print(result.columns)  # ('ally', 'since')
    print(result.rows[0]["ally"], result.rows[0]["since"])  # Quorra 2020
```

Read more in [Query your graph](../guides/querying.md) and the
[query language reference](../reference/query-language.md).

## 6. Traverse

`traverse` yields every reachable node once, with its shortest depth. `shortest_path` returns one
path with the fewest relationships.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    sam = graph.add_node("Program", designation="Sam Flynn")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(quorra, "ALLIES_WITH", sam)

    steps = graph.traverse(kevin, max_depth=2)
    print([(step.node["designation"], step.depth) for step in steps])
    # [('Quorra', 1), ('Sam Flynn', 2)]

    path = graph.shortest_path(kevin, sam)
    print(path.length, [node["designation"] for node in path.nodes])
    # 2 ['Kevin Flynn', 'Quorra', 'Sam Flynn']
```

## 7. Persist and reopen

A file-backed graph survives close and reopen. File databases prefer write-ahead logging; check
`graph.journal_mode` when that concurrency property matters.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Tron", cycles=40)

    with Graph.open(path) as graph:
        tron = next(iter(graph.find_nodes("Program")))
        print(tron["designation"], tron["cycles"])  # Tron 40
```

## Where next

- [Sample graphs and examples](../guides/examples.md) build a richer franchise graph and show the
  shell tours, analysis recipes, and algorithm demonstrations.
- [Guides](../guides/querying.md) cover the tasks you will do repeatedly.
- [Reference](../reference/query-language.md) holds grammar, formats, and detailed behavior.
- [API reference](../api/index.md) documents the public Python surface.

Writes outside an explicit transaction are atomic on their own. To group several writes, see
[Embed a graph safely](../guides/embedding.md).
