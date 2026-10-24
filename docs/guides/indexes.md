# Speed up property filters

Use a property index when a `MATCH ... WHERE` filter on one key reads many candidates and returns
few. An index never changes the result; it only changes how much work the engine does.

This guide covers declaring, checking, and removing an index. [Index
behavior](../reference/index-behavior.md) owns the predicate table, planner rules, persistence, and
key-handling details.

## Declare an index

Indexes are key-scoped: one key across every node, or one key across every relationship. Declaring
the same index twice is a no-op.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_node("Program", designation="Tron", cycles=40)

    index = graph.create_node_index("cycles")
    print(index.kind.value, index.key)  # node cycles
    print([item.key for item in graph.indexes()])  # ['cycles']

    result = graph.query(
        "MATCH (n:Program) WHERE n.cycles = 37 RETURN n.designation AS name"
    )
    print([row["name"] for row in result])  # ['Quorra']
```

A relationship index works the same way:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra, since_cycle=2020)

    index = graph.create_relationship_index("since_cycle")
    print(index.kind.value, index.key)  # relationship since_cycle
    result = graph.query(
        "MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) "
        "WHERE r.since_cycle >= 2020 RETURN count(*) AS total"
    )
    print(result.rows[0]["total"])  # 1
    graph.drop_index(index)
```

## Confirm the planner uses it

`Graph.explain` returns the access plan without running the statement. After an index is declared,
equality, range, and `IN` filters on that key should show a `SEARCH ... USING INDEX` line.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    graph.add_node("Program", designation="Quorra", cycles=37)

    statement = "MATCH (n:Program) WHERE n.cycles = 37 RETURN n"
    print(graph.explain(statement))

    graph.create_node_index("cycles")
    plan = graph.explain(statement)
    print(any("pygrafito_idx_node_" in line for line in plan))  # True
```

The plan is read-only: explaining a write statement creates, changes, and deletes nothing. A
statement with no read stage returns an empty tuple.

## Know what it covers

An index covers one key across every node or every relationship. It is not attached to a label, so
`create_node_index("cycles")` helps every query that filters on `cycles`, whatever label it also
requires.

Equality, range, and `IN` predicates can turn a scan into a seek. Negated filters, null checks,
`STARTS WITH`, and `ORDER BY` do not use the index by themselves. The [predicate
table](../reference/index-behavior.md#what-an-index-accelerates) lists each form.

## Understand the cost

Every index adds work to writes of that key and occupies space in the database file. Declare the
keys your queries filter on, not every key you store. Transactions remain ACID: SQLite updates the
index in the same transaction as the row, so a rolled-back write cannot leave a stale entry.

Declared indexes persist in the database file and are discovered on reopen. They do not change the
schema version.

## Remove an index

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Tron", cycles=40)
    index = graph.create_node_index("cycles")
    graph.drop_index(index)
    print(graph.indexes())  # ()
```

Dropping an index that was never declared raises `NotFoundError`. Index changes are rejected with
`TransactionError` while an explicit transaction is open on the same handle. See [Index
behavior](../reference/index-behavior.md#when-an-index-is-not-used) when a filter still scans.

## Go deeper

- [Index behavior](../reference/index-behavior.md) for accelerated predicates, planner choices,
  persistence, constraint interaction, and property-key escaping.
- [`Index`](../api/admin.md#index) and [`IndexKind`](../api/model.md#indexkind) in the API reference.
- [Query your graph](querying.md) for the `MATCH` and `WHERE` forms that indexes accelerate.
