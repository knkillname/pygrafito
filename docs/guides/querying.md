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
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    tron = graph.add_node("Program", designation="Tron", cycles=40)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(quorra, "ALLIES_WITH", tron)

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
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    sam = graph.add_node("Program", designation="Sam Flynn")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(kevin, "TRUSTS", sam)

    incoming = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program {designation: $name}) "
        "RETURN a.designation AS name",
        {"name": "Quorra"},
    )
    print([row["name"] for row in incoming])  # ['Kevin Flynn']

    optional = graph.query(
        "MATCH (a:Program {designation: 'Sam Flynn'}) "
        "OPTIONAL MATCH (a)-[:ALLIES_WITH]->(b:Program) "
        "RETURN a.designation AS name, b.designation AS ally"
    )
    print(tuple(optional.rows[0].values()))  # ('Sam Flynn', None)
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
    graph.add_node("Program", designation="Quorra", cycles=37)
    result = graph.query(
        "MATCH (n:Program) WHERE n.cycles > $minimum "
        "RETURN n.designation AS name ORDER BY name",
        {"minimum": 36},
    )
    print([row["name"] for row in result])  # ['Quorra']
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
    kevin = graph.add_node("Program", designation="Kevin Flynn", cycles=36)
    quorra = graph.add_node("Program", designation="Quorra", cycles=37)
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)

    created = graph.query(
        "MATCH (a:Program {designation: 'Kevin Flynn'}) "
        "CREATE (b:Program {designation: 'Tron', cycles: 40}) "
        "CREATE (a)-[r:TRUSTS]->(b) "
        "RETURN b.designation AS name"
    )
    print(created.rows[0]["name"])  # Tron
    print(created.summary.created_nodes, created.summary.created_relationships)  # 1 1

    updated = graph.query(
        "MATCH (n:Program {designation: 'Quorra'}) "
        "SET n:ISO, n.cycles = n.cycles + 1"
    )
    print(updated.summary.labels_added, updated.summary.properties_set)  # 1 1

    deleted = graph.query("MATCH (n:Program {designation: 'Tron'}) DETACH DELETE n")
    print(deleted.summary.deleted_nodes)  # 1
```

`DELETE` refuses to remove a node that still has relationships. Use `DETACH DELETE` when the
incident relationships should be removed first. See [Write
clauses](../reference/query-language.md#write-clauses) and [Mutation
cardinality](../reference/query-language.md#mutation-cardinality).

## Compose stages

`WITH` projects a new scope, so grouped results can be filtered, ordered, and paginated before the
final projection. `UNWIND` expands a list into rows and can feed a write clause.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    kevin = graph.add_node("Program", designation="Kevin Flynn")
    quorra = graph.add_node("Program", designation="Quorra")
    tron = graph.add_node("Program", designation="Tron")
    graph.add_relationship(kevin, "ALLIES_WITH", quorra)
    graph.add_relationship(kevin, "ALLIES_WITH", tron)

    grouped = graph.query(
        "MATCH (a:Program)-[:ALLIES_WITH]->(b:Program) "
        "WITH a.designation AS name, count(*) AS allies "
        "WHERE allies > 1 RETURN name, allies"
    )
    print([tuple(row.values()) for row in grouped])  # [('Kevin Flynn', 2)]
```

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
    print(result.summary.created_nodes)  # 2
```

`MERGE` matches its whole pattern or creates the unbound elements. It runs once per input row, so
a creation made by one row is visible to later rows in the same statement. See
[UNWIND](../reference/query-language.md#unwind), [WITH](../reference/query-language.md#with), and
[MERGE](../reference/query-language.md#merge).

## Prepare a statement

Use `Graph.prepare` when the same statement runs repeatedly. The parsed plan is reused, the columns
are available before the first execution, and parameters can change on every call.

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
    print(prepared.is_write, sorted(prepared.parameters))  # False ['minimum']
    print(prepared.execute({"minimum": 36}).rows[0]["total"])  # 2
```

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
