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

`pygrafito` requires Python 3.13 or newer and SQLite 3.38 or newer. Linux with glibc is the
supported 1.0 platform; macOS and Windows are tested nightly as a non-blocking portability signal.
The package is pure Python, so installation needs no compiler or system SQLite build step.

Google Colab currently runs Python 3.13. Install the package in a notebook cell and keep database
files under `/content`, or mount Google Drive when they must outlive the runtime:

```console
!pip install pygrafito
```

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

## Traverse without a depth cap

Add `*`, `+`, or `{m,}` to a relationship to follow it without an upper bound. `TRAIL` stops when
every relationship has been used once; an open `WALK` needs a `LIMIT` or the query budget.

```python
from pygrafito import Graph, QueryBudget, QueryBudgetExceededError

with Graph.open(":memory:") as graph:
    flynn = graph.add_node("Program", designation="Flynn")
    tron = graph.add_node("Program", designation="Tron")
    clu = graph.add_node("Program", designation="Clu")
    graph.add_relationship(flynn, "TRUSTS", tron)
    graph.add_relationship(tron, "TRUSTS", clu)
    graph.add_relationship(clu, "TRUSTS", flynn)

    trail = graph.query(
        "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
        "RETURN b.designation AS name ORDER BY name"
    )
    print([row["name"] for row in trail])  # ['Clu', 'Flynn', 'Tron']

    limited = graph.query(
        "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) "
        "RETURN b.designation AS name LIMIT 5"
    )
    print(len(limited.rows))  # 5

    try:
        graph.query(
            "MATCH (a:Program {designation: 'Flynn'})-[:TRUSTS+]->(b) RETURN b",
            budget=QueryBudget(max_expansions=10),
        )
    except QueryBudgetExceededError as error:
        print(error.counter)  # expansions
```

## Choose the shortest route

A path-search prefix selects among the routes one pattern matches. `ANY SHORTEST` keeps one
shortest route per endpoint pair, `ALL SHORTEST` keeps every shortest route, and `SHORTEST k` keeps
up to `k` routes in increasing length.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("User", designation="Kevin Flynn")
    sam = graph.add_node("User", designation="Sam Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    alan = graph.add_node("User", designation="Alan Bradley")
    graph.add_relationship(kevin, "PARENT_OF", sam)
    graph.add_relationship(kevin, "TRUSTS", quorra)
    graph.add_relationship(sam, "TRUSTS", alan)
    graph.add_relationship(quorra, "TRUSTS", alan)
    graph.add_relationship(sam, "TRUSTS", quorra)

    shortest = graph.query(
        "MATCH p = ANY SHORTEST (a:User {designation: 'Kevin Flynn'})"
        "-[:PARENT_OF|TRUSTS{1,3}]->(b:User {designation: 'Alan Bradley'}) "
        "RETURN length(p) AS hops"
    )
    print(shortest.rows[0]["hops"])  # 2

    routes = graph.query(
        "MATCH p = ALL SHORTEST (a:User {designation: 'Kevin Flynn'})"
        "-[:PARENT_OF|TRUSTS{1,3}]->(b:User {designation: 'Alan Bradley'}) "
        "RETURN length(p) AS hops ORDER BY hops"
    )
    print([row["hops"] for row in routes])  # [2, 2]
```

## Repeat a path shape

A grouped path repeats a whole path segment. Variables first introduced inside the group bind
ordered lists, and a group path variable binds the complete repeated path.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    flynn = graph.add_node("Program", designation="Flynn")
    tron = graph.add_node("Program", designation="Tron")
    clu = graph.add_node("Program", designation="Clu")
    graph.add_relationship(flynn, "TRUSTS", tron)
    graph.add_relationship(tron, "TRUSTS", clu)
    graph.add_relationship(clu, "TRUSTS", flynn)

    result = graph.query(
        "MATCH (s:Program {designation: 'Flynn'}) "
        "(p = (a)-[r:TRUSTS]->(b)){2} "
        "RETURN [x IN nodes(p) | x.designation] AS names"
    )
    print(result.rows[0]["names"])  # ['Flynn', 'Tron', 'Clu']
```

## Features

- A single embedded database file, with no server and no runtime dependencies.
- Nodes with labels, strict typed properties, and indexed lookups.
- Labeled relationships with properties, either directed or undirected.
- A GQL-first query language with writes, aggregation, path modes, a query budget, and
  prepared statements.
- GQL composition with `LET`, `NEXT`/`YIELD`, `GROUP BY`, and `FINISH`, keeping one transaction
  and one query budget per statement.
- Bounded traversal, shortest paths, and relationship-unique trail enumeration in the Python API.
- Property indexes and uniqueness constraints enforced by the database.
- CSV and JSONL import, versioned JSONL export/restore, and read-only SQL views.
- An interactive shell, transactions, read-only handles, backups, and integrity checks.

The query language is GQL-first. The canonical spelling, compatibility aliases, path modes, the
query budget, and pygrafito extensions are documented in the
[GQL profile](https://knkillname.github.io/pygrafito/reference/gql-profile.html).

## Documentation

- [Five-minute quickstart](https://knkillname.github.io/pygrafito/getting-started/quickstart.html)
- [Sample graphs and examples](https://knkillname.github.io/pygrafito/guides/examples.html) for the
  franchise datasets, shell tours, analysis recipes, and algorithm demonstrations.
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
scripts/verify
```

Enable the versioned pre-push hook once per clone with `git config core.hooksPath .githooks`.
The hook runs `scripts/verify` before each push; use `scripts/verify --skip-sqlite` to omit the
pinned SQLite container. The project supports Python 3.13 and 3.14 and keeps its runtime standard
library only. Documentation dependencies are optional and installed by the `docs` Hatch
environment.

## License

`pygrafito` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html)
license.
