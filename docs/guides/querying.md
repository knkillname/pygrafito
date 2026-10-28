# Query your graph

Use `Graph.query` when one pattern-matching statement should read or change the graph. It returns a
materialized `QueryResult`, so you can inspect the columns, rows, and mutation counts after the
statement finishes.

This guide covers the tasks most programs need. The [query language
reference](../reference/query-language.md) owns the complete grammar, value rules, functions, and
error behavior.

## Run a statement

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    yori = graph.add_node("Program", designation="Yori", cycles=37)
    dumont = graph.add_node("Program", designation="Dumont", cycles=39)
    ram = graph.add_node("Program", designation="Ram", cycles=36)
    graph.add_relationship(yori, "ALLIES_WITH", dumont)
    graph.add_relationship(dumont, "ALLIES_WITH", ram)

    result = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program) "
        "RETURN a.designation AS source, b.designation AS target "
        "ORDER BY target"
    )
    print(result.columns)  # ('source', 'target')
    for row in result:
        print(row["source"], "->", row["target"])
```

`Graph.query` executes exactly one statement. Use a semicolon at the end if you like; multiple
statements are rejected.

## Match nodes and relationships

A pattern can bind variables, require labels on nodes and relationships, filter with an inline
property map, and follow a direction. The arrow determines direction: `->` follows a directed
relationship forward, `<-` follows it backward, and `-` matches any incident relationship,
including an undirected one. A relationship may carry several labels at once.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    alan = graph.add_node("Program", designation="Alan Bradley")
    tron = graph.add_node("Program", designation="Tron")
    dumont = graph.add_node("Program", designation="Dumont")
    graph.add_relationship(alan, "ALLIES_WITH", tron)
    graph.add_relationship(alan, "TRUSTS", dumont)

    incoming = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program {designation: $name}) "
        "RETURN a.designation AS name",
        {"name": "Tron"},
    )
    print([row["name"] for row in incoming])  # ['Alan Bradley']

    optional = graph.query(
        "MATCH (a:Program {designation: 'Dumont'}) "
        "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b:Program) "
        "RETURN a.designation AS name, b.designation AS ally"
    )
    print(tuple(optional.rows[0].values()))  # ('Dumont', None)
```

`OPTIONAL MATCH` is a left join: unmatched rows survive with `None`. For variable-length
patterns, path variables, and repeated variables, see [Relationship
patterns](../reference/query-language.md#relationship-patterns) and [Variable-length
relationships](../reference/query-language.md#variable-length-relationships).

## Filter with parameters

Use `$name` placeholders and pass a mapping. Values are bound, not interpolated, so a value that
looks like query syntax stays a value.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Yori", cycles=37)
    result = graph.query(
        "MATCH (n:Program) WHERE n.cycles > $minimum "
        "RETURN n.designation AS name ORDER BY name",
        {"minimum": 36},
    )
    print([row["name"] for row in result])  # ['Yori']
```

`WHERE` also supports boolean operators, null checks, string predicates, arithmetic, and scalar
functions. See [Filtering expressions](../reference/query-language.md#filtering-expressions) for
the supported set.

## Write from a query

A statement can create elements, set or remove properties and labels, and delete elements. The
result's `summary` reports what changed.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    yori = graph.add_node("Program", designation="Yori", cycles=37)
    dumont = graph.add_node("Program", designation="Dumont", cycles=39)
    graph.add_relationship(yori, "ALLIES_WITH", dumont)

    created = graph.query(
        "MATCH (a:Program {designation: 'Yori'}) "
        "INSERT (b:Program {designation: 'Sark', cycles: 42}) "
        "INSERT (a)-[r:TRUSTS]->(b) "
        "RETURN b.designation AS name"
    )
    print(created.rows[0]["name"])  # Sark
    print(created.summary.created_nodes, created.summary.created_relationships)  # 1 1

    updated = graph.query(
        "MATCH (n:Program {designation: 'Dumont'}) "
        "SET n:ISO, n.cycles = n.cycles + 1"
    )
    print(updated.summary.labels_added, updated.summary.properties_set)  # 1 1

    deleted = graph.query("MATCH (n:Program {designation: 'Sark'}) DETACH DELETE n")
    print(deleted.summary.deleted_nodes)  # 1
```

`DELETE` refuses to remove a node that still has relationships. Use `DETACH DELETE` when the
incident relationships should be removed first. See [Write
clauses](../reference/query-language.md#write-clauses) and [Mutation
cardinality](../reference/query-language.md#mutation-cardinality).

## Compose stages

`WITH` projects a new scope, so grouped results can be filtered, ordered, and paginated before the
final projection. `FOR` expands a list into rows and can feed a write clause.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    yori = graph.add_node("Program", designation="Yori")
    dumont = graph.add_node("Program", designation="Dumont")
    ram = graph.add_node("Program", designation="Ram")
    graph.add_relationship(yori, "ALLIES_WITH", dumont)
    graph.add_relationship(yori, "ALLIES_WITH", ram)

    grouped = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program) "
        "WITH a.designation AS name, count(*) AS allies "
        "FILTER allies > 1 RETURN name, allies"
    )
    print([tuple(row.values()) for row in grouped])  # [('Yori', 2)]
```

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    rows = [
        {"designation": "Sark", "cycles": 42},
        {"designation": "Dumont", "cycles": 39},
        {"designation": "Sark", "cycles": 43},
    ]
    result = graph.query(
        "FOR row IN $rows "
        "MERGE (n:Program {designation: row.designation}) "
        "ON CREATE SET n.cycles = row.cycles "
        "ON MATCH SET n.cycles = n.cycles + 1 "
        "RETURN n.designation AS name, n.cycles AS cycles ORDER BY name",
        {"rows": rows},
    )
    print([tuple(row.values()) for row in result])
    print(result.summary.created_nodes)  # 2
```

`MERGE` matches its whole pattern or creates the unbound elements. It runs once per input row, so
a creation made by one row is visible to later rows in the same statement. See
[FOR](../reference/query-language.md#for), [WITH](../reference/query-language.md#with), and
[MERGE](../reference/query-language.md#merge).

## Prepare a statement

Use `Graph.prepare` when the same statement runs repeatedly. The parsed plan is reused, the columns
are available before the first execution, and parameters can change on every call.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Yori", cycles=37)
    graph.add_node("Program", designation="Dumont", cycles=39)
    graph.add_node("Program", designation="Ram", cycles=36)

    prepared = graph.prepare(
        "MATCH (n:Program) WHERE n.cycles > $minimum RETURN count(*) AS total"
    )
    print(prepared.columns)  # ('total',)
    print(prepared.is_write, sorted(prepared.parameters))  # False ['minimum']
    print(prepared.execute({"minimum": 36}).rows[0]["total"])  # 2
```

## Choose a path mode

A path may repeat nodes or relationships depending on its mode. `WALK` permits both, `TRAIL`
forbids reusing a relationship, `SIMPLE` forbids repeating a node except at the end, and `ACYCLIC`
forbids repeating any node. A clause or a single path may name the mode.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    flynn = graph.add_node("Program", designation="Flynn")
    tron = graph.add_node("Program", designation="Tron")
    clu = graph.add_node("Program", designation="Clu")
    graph.add_relationship(flynn, "TRUSTS", tron)
    graph.add_relationship(tron, "TRUSTS", clu)
    graph.add_relationship(clu, "TRUSTS", flynn)

    walk = graph.query(
        "MATCH WALK (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
        "RETURN count(*) AS routes"
    )
    trail = graph.query(
        "MATCH TRAIL (a:Program {designation: 'Flynn'})-[:TRUSTS*4]->(b) "
        "RETURN count(*) AS routes"
    )
    print(walk.rows[0]["routes"] > 0, trail.rows[0]["routes"])  # True 0
```

A canonical path without an explicit mode uses `WALK`; a path with a legacy `*n..m` quantifier
keeps `TRAIL`. See [Path modes](../reference/query-language.md#path-modes) for the resolution order.

## Bound query work

Every execution runs under a query budget. Two counters bound the work — relationship expansions
and intermediate rows — and an optional wall-clock limit bounds elapsed time. The defaults are
1,000,000 expansions and 100,000 rows, with no time limit. Exceeding a counter raises
`QueryBudgetExceededError` before any result is returned, and a write that exceeds the budget is
rolled back entirely.

```python
from pygrafito import Graph, QueryBudget, QueryBudgetExceededError

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Quorra")
    graph.add_node("Program", designation="Tron")

    try:
        graph.query(
            "FOR value IN [1, 2, 3] RETURN value",
            budget=QueryBudget(max_rows=1),
        )
    except QueryBudgetExceededError as error:
        print(error.counter, error.limit)  # rows 1
```

Pass a budget to `Graph.open` to change the default for every statement, and to `Graph.query`,
`Transaction.query`, or `PreparedQuery.execute` to override one execution without changing that
default. A counter set to `None` is unlimited. The budget does not change the Python traversal API:
`Graph.paths` remains a bounded, relationship-unique trail enumerator.

## Read the result

`QueryResult.columns` is an ordered tuple. Each `Row` supports lookup by column name, iteration
over values, and conversion to a tuple. `QueryResult.summary` is a `MutationSummary`; `QueryResult`
is iterable over its rows. See [Result model](../reference/query-language.md#result-model) for the
full contract.

## Go deeper

- [Query language reference](../reference/query-language.md) for grammar, null semantics,
  functions, aggregation, ordering, and errors.
- [`PreparedQuery`](../api/query.md#preparedquery), [`QueryResult`](../api/query.md#queryresult),
  and [`Row`](../api/query.md#row) in the API reference.
- [Import rows and files](importing.md) when the statement should map a batch of input rows.
