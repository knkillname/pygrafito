# Queries and results

`Graph.query` returns a materialized `QueryResult`. Use `Graph.prepare` when the same statement runs
repeatedly.

## PreparedQuery

:::{py:class} pygrafito.PreparedQuery
A parsed, analysed, and planned query that can run repeatedly.

Create it with [`Graph.prepare`](graph.md#queries). The parsed plan is reused by
every execution, and parameters can change on each call.
:::

```{eval-rst}
.. autoproperty:: pygrafito.PreparedQuery.text
```

```{eval-rst}
.. autoproperty:: pygrafito.PreparedQuery.columns
```

```{eval-rst}
.. autoproperty:: pygrafito.PreparedQuery.is_write
```

```{eval-rst}
.. autoproperty:: pygrafito.PreparedQuery.parameters
```

```{eval-rst}
.. automethod:: pygrafito.PreparedQuery.execute
```

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Quorra", cycles=37)
    prepared = graph.prepare(
        "MATCH (n:Program) WHERE n.cycles > $minimum RETURN n.designation AS name"
    )
    print(prepared.columns)  # ('name',)
    print([row["name"] for row in prepared.execute({"minimum": 36})])  # ['Quorra']
```

## QueryResult

```{eval-rst}
.. autoclass:: pygrafito.QueryResult
   :special-members: __iter__, __len__
```

A result is iterable over its rows and supports `len(result)`. `columns` is an ordered tuple, and
`summary` reports the mutation counts even when the statement returns no rows.

## Row

```{eval-rst}
.. autoclass:: pygrafito.Row
```

A row is an immutable mapping from column name to value. Lookup is by name, iteration yields
column names, and `row.values()` yields the projected values in column order.

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Tron", cycles=40)
    result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
    row = result.rows[0]
    print(row["name"])  # Tron
    print(tuple(row.values()))  # ('Tron',)
```

## MutationSummary

```{eval-rst}
.. autoclass:: pygrafito.MutationSummary
   :no-members:
```

`QueryResult.summary` contains one of these. A read statement returns all-zero counts.

## ImportSummary

```{eval-rst}
.. autoclass:: pygrafito.ImportSummary
   :no-members:
```

`Graph.import_rows` and `Graph.import_file` return this summary. `mutations` is the aggregate over
every committed batch.
