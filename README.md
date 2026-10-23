# pygrafito

[![PyPI - Version](https://img.shields.io/pypi/v/pygrafito.svg)](https://pypi.org/project/pygrafito)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pygrafito.svg)](https://pypi.org/project/pygrafito)

`pygrafito` is an embedded property graph for Python, persisted in a single
SQLite database. It has no runtime dependencies outside the standard library:
nodes carry labels and strict typed properties, relationships are directed and
typed, and writes run in explicit ACID transactions.

## Table of Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Nodes, labels, and properties](#nodes-labels-and-properties)
- [Relationships](#relationships)
- [Transactions](#transactions)
- [Deletion](#deletion)
- [Traversal](#traversal)
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
        ada = graph.add_node("Person", name="Ada", age=36)
        grace = graph.add_node("Person", name="Grace", age=37)
        knows = graph.add_relationship(ada, "KNOWS", grace, since=2020)

        graph.set_properties(ada, age=37)
        print(graph.node(ada.id)["age"])          # 37
        print(graph.relationship(knows.id)["since"])  # 2020

    with Graph.open(path) as graph:
        people = graph.find_nodes("Person")
        print(sorted(node["name"] for node in people))  # ['Ada', 'Grace']
```

Open `":memory:"` instead of a filesystem path when the graph should live only
for the lifetime of the handle.

## Nodes, labels, and properties

Nodes are created with zero or more non-empty string labels and keyword
properties. `find_nodes` matches nodes that carry every given label and every
given exact property value. Property matching is type-sensitive and list order
matters.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Person", "Employee", name="Ada", age=36)
    print(sorted(ada.labels))  # ['Employee', 'Person']
    print(ada["name"])         # Ada

    ada = graph.add_labels(ada, "Manager")
    ada = graph.remove_labels(ada, "Employee")
    ada = graph.set_properties(ada, age=37)
    print(dict(ada))           # {'age': 37, 'name': 'Ada'}

    found = graph.find_nodes("Person", age=37)
    print([node["name"] for node in found])  # ['Ada']
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
    first = graph.add_node("Person", name="Ada")
    second = graph.add_node("Person", name="Grace")
    relationship = graph.add_relationship(first, "KNOWS", second, since=2020)
    print(relationship.start_id, relationship.rel_type, relationship.end_id)
    print(relationship["since"])  # 2020

    found = graph.find_relationships("KNOWS", since=2020)
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
        ada = tx.add_node("Person", name="Ada")
        grace = tx.add_node("Person", name="Grace")
        tx.add_relationship(ada, "KNOWS", grace)
        tx.set_properties(ada, age=36)

    print(graph.node(ada.id)["age"])  # 36
```

Writes use `BEGIN IMMEDIATE`, and one `Graph` owns exactly one connection. A
graph handle is not thread-safe; using it from another thread raises an error
rather than sharing the connection silently.

## Deletion

Relationships are deleted directly. A node with relationships is protected
until deletion is requested with `detach=True`, which removes incident
relationships first.

```python
from pygrafito import ConnectedNodeError, Graph

with Graph.open(":memory:") as graph:
    first = graph.add_node("Person")
    second = graph.add_node("Person")
    graph.add_relationship(first, "KNOWS", second)

    try:
        graph.delete(first)
    except ConnectedNodeError:
        print("delete with detach=True instead")

    graph.delete(first, detach=True)
```

## Traversal

Traversal reads a consistent snapshot that is materialized when the call is
made, so writes performed later do not change an in-progress result.

`traverse` yields every node reachable within `max_depth` exactly once, together
with its shortest depth. The start node is not yielded.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Person", name="Ada")
    grace = graph.add_node("Person", name="Grace")
    bob = graph.add_node("Person", name="Bob")
    graph.add_relationship(ada, "KNOWS", grace)
    graph.add_relationship(grace, "KNOWS", bob)

    steps = graph.traverse(ada, max_depth=2)
    print([(step.node["name"], step.depth) for step in steps])
    # [('Grace', 1), ('Bob', 2)]
```

`shortest_path` returns one path with the fewest relationships, or `None` when
no path exists within the given direction, type filter, and optional
`max_depth`. A node has a zero-length path to itself.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Person", name="Ada")
    grace = graph.add_node("Person", name="Grace")
    bob = graph.add_node("Person", name="Bob")
    graph.add_relationship(ada, "KNOWS", grace)
    graph.add_relationship(grace, "KNOWS", bob)

    path = graph.shortest_path(ada, bob)
    print(path.length)  # 2
    print([node["name"] for node in path.nodes])  # ['Ada', 'Grace', 'Bob']
```

`paths` enumerates relationship-unique trails between two nodes. Nodes may
repeat within a path, but each relationship may be used at most once. Both a
minimum and maximum depth are supported, and `max_depth` is required.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    start = graph.add_node("start")
    left = graph.add_node("left")
    right = graph.add_node("right")
    end = graph.add_node("end")
    graph.add_relationship(start, "ROUTE", left)
    graph.add_relationship(start, "ROUTE", right)
    graph.add_relationship(left, "ROUTE", end)
    graph.add_relationship(right, "ROUTE", end)

    paths = graph.paths(start, end, min_depth=2, max_depth=2)
    print(len(list(paths)))  # 2
```

Use `direction=Direction.INCOMING` or `Direction.BOTH`, and restrict followed
relationship types with `types=[...]`. An empty or omitted type collection means
all types.

```python
from pygrafito import Direction, Graph

with Graph.open(":memory:") as graph:
    ada = graph.add_node("Person", name="Ada")
    grace = graph.add_node("Person", name="Grace")
    graph.add_relationship(ada, "KNOWS", grace)
    graph.add_relationship(grace, "LIKES", ada)

    incoming = graph.traverse(
        grace,
        max_depth=1,
        direction=Direction.INCOMING,
        types=["KNOWS"],
    )
    print([step.node["name"] for step in incoming])  # ['Ada']
```

Path enumeration is exponential in the worst case because a graph can contain
many trails between the same pair of nodes. Always set the smallest useful
`max_depth`, and pass `limit` when only the first few paths are needed. Paths
are generated lazily, so stopping iteration early stops further computation.

## Persistence

A file-backed graph persists nodes, labels, relationships, and properties
across close and reopen. The database uses write-ahead logging; SQLite may reuse
an integer id after an element is deleted, so treat ids as handles for live
elements rather than permanent external keys.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "graph.db"
    with Graph.open(path) as graph:
        node = graph.add_node("Person", name="Ada")

    with Graph.open(path) as graph:
        print(graph.node(node.id)["name"])  # Ada
```

## License

`pygrafito` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
