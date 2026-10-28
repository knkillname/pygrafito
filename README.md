# pygrafito

[![PyPI - Version](https://img.shields.io/pypi/v/pygrafito)](https://pypi.org/project/pygrafito)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pygrafito)](https://pypi.org/project/pygrafito)

`pygrafito` is an embedded property graph for Python, persisted in a single SQLite database. It has
no runtime dependencies outside the standard library: nodes carry labels and strict typed
properties, relationships are directed and typed, and writes run in explicit ACID transactions.

## Installation

```console
pip install pygrafito
```

`pygrafito` requires Python 3.14 or newer and SQLite 3.38 or newer.

## Quick start

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

Every Python example in this README is executed by the test suite.

## Features

- A single embedded database file, with no server and no runtime dependencies.
- Nodes with labels, strict typed properties, and indexed lookups.
- Labeled relationships with properties, either directed or undirected.
- A pattern-matching query language with writes, aggregation, and prepared statements.
- Bounded traversal, shortest paths, and relationship-unique trail enumeration.
- Property indexes and uniqueness constraints enforced by the database.
- CSV and JSONL import, versioned JSONL export/restore, and read-only SQL views.
- An interactive shell, transactions, read-only handles, backups, and integrity checks.

The query language is moving to GQL. The target profile, including the canonical spelling,
compatibility aliases, and pygrafito extensions, is documented in the
[GQL profile](https://knkillname.github.io/pygrafito/reference/gql-profile.html).

## Documentation

- [Five-minute quickstart](https://knkillname.github.io/pygrafito/getting-started/quickstart.html)
- [Guides](https://knkillname.github.io/pygrafito/guides/querying.html) for querying, indexes,
  constraints, import, interop, the shell, and embedding.
- [Reference](https://knkillname.github.io/pygrafito/reference/query-language.html) for the query
  grammar, CLI, snapshot format, index behavior, and embedding contract.
- [API reference](https://knkillname.github.io/pygrafito/api/index.html) for the public Python
  surface.

## Development

```console
hatch check --fix
hatch test
hatch run docs:build
```

The project targets Python 3.14 and keeps its runtime standard library only. Documentation
dependencies are optional and installed by the `docs` Hatch environment.

## License

`pygrafito` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html)
license.
