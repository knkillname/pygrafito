# pygrafito

**An embedded property graph for Python, persisted in one SQLite file.**

`pygrafito` stores nodes, labels, typed properties, and labeled directed or undirected
relationships in a single database. It uses only the Python standard library at runtime, writes in explicit ACID
transactions, and includes a pattern-matching query language, traversal, indexes, uniqueness
constraints, batch import, and JSONL interop.

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

:::{grid-item-card} Five-minute quickstart
:link: getting-started/quickstart
:link-type: doc
Open a graph, add nodes and relationships, query, traverse, and reopen a file.
:::

:::{grid-item-card} Guides
:link: guides/querying
:link-type: doc
Task-oriented pages for querying, indexes, constraints, import, interop, the shell, and embedding.
:::

:::{grid-item-card} Reference
:link: reference/query-language
:link-type: doc
Grammar, CLI options, snapshot format, index behavior, and the embedding contract.
:::

:::{grid-item-card} API reference
:link: api/index
:link-type: doc
Generated documentation for the public Python surface.
:::
```

`pygrafito` requires Python 3.14 or newer and SQLite 3.38 or newer.

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

guides/querying
guides/indexes
guides/constraints
guides/importing
guides/interop
guides/shell
guides/embedding
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Reference

reference/query-language
reference/cli
reference/snapshot-format
reference/index-behavior
reference/embedding-contract
reference/performance
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
