# Five-minute quickstart

:::{admonition} tl;dr
:class: tldr

Open a graph, add nodes and a relationship, query them, traverse two hops, and reopen the file.
Five complete snippets, no dependencies.
:::

This page gets you from an empty Python process to a persisted graph you can query, traverse, and
reopen. Every Python block is a complete program, so you can copy one into a file and run it.

```{mermaid}
:alt: Seven steps from installing pygrafito to reopening a persisted graph.

flowchart LR
  I["1. Install"] --> O["2. Open a graph"]
  O --> A["3. Add nodes and properties"]
  A --> R["4. Add a relationship"]
  R --> Q["5. Query"]
  Q --> T["6. Traverse"]
  T --> P["7. Persist and reopen"]
  accTitle: The seven-step quickstart path
  accDescr: Install, open a graph, add nodes and properties, add a relationship, query, traverse, and reopen a file.
```

## 1. Install

```{code-block} console
pip install pygrafito
```

`pygrafito` requires Python 3.13 or newer and SQLite 3.38 or newer.

## Supported platforms

Linux with glibc is the supported platform for the 1.x series. macOS and Windows run the same
test suite nightly as a portability signal, but they are not supported platforms until that signal
is green. The package is pure Python and installs without a compiler. See
[Platform support](../reference/platform-support.md) for the full contract.

## Google Colab

Colab currently runs Python 3.13. Install the package in a notebook cell:

```{code-block} console
!pip install pygrafito
```

The Colab runtime filesystem is ephemeral. Put a database under `/content` while the notebook is
running, or mount Google Drive when the file must survive the runtime:

```{code-block} text
/content/grid.db
```

## 2. Open a graph

`Graph.open(":memory:")` creates a graph that lives for the lifetime of the handle. Use a
filesystem path when the graph should survive the process.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    print(graph.journal_mode)  # memory
```

:::{tip}
Use `:memory:` while you experiment. Switch to a filesystem path when the graph should outlive the
process.
:::

A `Graph` owns one SQLite connection. Keep it in the thread that opened it, and use the context
manager so the connection is closed deterministically.

:::{warning}
A `Graph` handle is not thread-safe. Using it from another thread raises an error instead of
sharing the connection silently. Open one handle per thread.
:::

## 3. Add nodes, labels, and properties

Nodes carry zero or more labels and keyword properties. Property values are booleans, signed
64-bit integers, finite floats, strings, or homogeneous lists of those values.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", "User", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", "ISO", designation="Quorra", cycles=37)
    bit = graph.add_node("Program", designation="Bit", cycles=1, active=True)

    print(sorted(kevin.labels))  # ['Program', 'User']
    print(quorra["designation"], quorra["cycles"])  # Quorra 37
    print(bit["designation"], bit["active"])  # Bit True
```

`find_nodes` matches every supplied label and every exact property value:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_node("ISO", designation="Quorra", cycles=37)
    graph.add_node("Program", designation="Bit", cycles=1, active=True)

    found = graph.find_nodes("Program", cycles=37)
    print([node["designation"] for node in found])  # ['Quorra']

    active = graph.find_nodes("Program", active=True)
    print([node["designation"] for node in active])  # ['Bit']
```

## 4. Add a relationship

Relationships are directed and typed. They can carry properties of their own.

```{mermaid}
:alt: Kevin Flynn has an ALLIES_WITH relationship to Quorra, carrying since_cycle.

flowchart LR
  K["Kevin Flynn<br/><code>Program</code><br/><code>cycles=36</code>"] -->|"<code>ALLIES_WITH</code><br/><code>since_cycle=2020</code>"| Q["Quorra<br/><code>Program</code><br/><code>cycles=37</code>"]
  accTitle: Kevin Flynn allies with Quorra
  accDescr: A directed relationship from Kevin Flynn to Quorra with a since_cycle property.
```

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

:::{admonition} Remember
:class: important

Pass values through the parameter map. Never build statement text from user input: the statement
is parsed and planned once, and the values stay data.
:::

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

:::{admonition} In detail
:class: detail

Write-ahead logging uses `-wal` and `-shm` sidecars next to the database. Do not delete them while
the graph is open; SQLite needs them to recover committed writes after a crash.
:::

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
