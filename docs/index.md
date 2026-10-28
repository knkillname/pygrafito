# pygrafito

:::{admonition} tl;dr
:class: tldr

Store nodes, labels, typed properties, and relationships in one SQLite file, query them with GQL,
and reopen the file with no runtime dependencies. This page shows the five-minute path and points
to the guides, reference, and API.
:::

**An embedded property graph for Python, persisted in one SQLite file.**

`pygrafito` stores nodes, labels, typed properties, and labeled directed or undirected
relationships in a single database. It uses only the Python standard library at runtime, writes in explicit ACID
transactions, and includes a pattern-matching query language, traversal, indexes, uniqueness
constraints, batch import, and JSONL interop.

```{mermaid}
:alt: Kevin Flynn and Quorra are Program nodes in one SQLite file, joined by an ALLIES_WITH relationship.

flowchart LR
  subgraph DB["grid.db"]
    K["Kevin Flynn<br/><code>Program, User</code><br/><code>cycles=36</code>"]
    Q["Quorra<br/><code>Program, ISO</code><br/><code>cycles=37</code>"]
    K -->|"<code>ALLIES_WITH</code><br/><code>since_cycle=2020</code>"| Q
  end
  accTitle: One SQLite file holding a small property graph
  accDescr: Kevin Flynn and Quorra are nodes with labels and properties inside grid.db, joined by a directed ALLIES_WITH relationship that carries since_cycle.
```

```{code-block} console
pip install pygrafito
```

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    result = graph.query(
        "MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) "
        "RETURN a.designation AS source, b.designation AS target, r.since_cycle AS since"
    )
    row = result.rows[0]
    print(f"{row['source']} -> {row['target']} since {row['since']}")
```

```{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} 🚀 Five-minute quickstart
:link: getting-started/quickstart
:link-type: doc
Open a graph, add nodes and relationships, query, traverse, and reopen a file.
:::

:::{grid-item-card} 🧭 Guides
:link: guides/querying
:link-type: doc
Task-oriented pages for sample graphs, querying, indexes, constraints, import, interop, the shell,
and embedding.
:::

:::{grid-item-card} 📚 Reference
:link: reference/query-language
:link-type: doc
Grammar, the GQL profile, CLI options, snapshot format, index behavior, and the embedding
contract.
:::

:::{grid-item-card} 🧩 API reference
:link: api/index
:link-type: doc
Generated documentation for the public Python surface.
:::
```

`pygrafito` requires Python 3.13 or newer and SQLite 3.38 or newer. Linux is the supported 1.0
platform; macOS and Windows are tested nightly as a non-blocking portability signal.

```{toctree}
:hidden:
:maxdepth: 2
:caption: Start

getting-started/quickstart
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Guides

guides/examples
guides/querying
guides/indexes
guides/constraints
guides/importing
guides/interop
guides/shell
guides/embedding
guides/production-checklist
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Reference

reference/query-language
reference/gql-profile
reference/cli
reference/snapshot-format
reference/index-behavior
reference/embedding-contract
reference/performance
reference/platform-support
reference/api-stability
reference/known-limitations
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: API reference

api/index
api/graph
api/model
api/query
api/admin
api/errors
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Contributing

contributing/documentation-style
```
