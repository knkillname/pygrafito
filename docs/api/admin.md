# Administration

These value types describe declared indexes, declared uniqueness constraints, and interop counts.

## Index

```{eval-rst}
.. autoclass:: pygrafito.Index
```

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Tron", cycles=40)
    index = graph.create_node_index("cycles")
    print(index.kind.value, index.key)  # node cycles
    print([item.key for item in graph.indexes()])  # ['cycles']
```

## Constraint

```{eval-rst}
.. autoclass:: pygrafito.Constraint
   :members: ordering_key
```

```python
from pygrafito import ElementKind, Graph

with Graph.open(":memory:") as graph:
    constraint = graph.create_node_uniqueness_constraint("Program", "designation")
    print(constraint.kind is ElementKind.NODE)  # True
    print(constraint.scope, constraint.key)  # Program designation
    print(constraint.ordering_key)  # ('node', 'Program', 'designation')

    relationship_constraint = graph.create_relationship_uniqueness_constraint(
        "ALLIES_WITH",
        "since",
    )
    print(relationship_constraint.kind is ElementKind.RELATIONSHIP)  # True
```

## InteropSummary

```{eval-rst}
.. autoclass:: pygrafito.InteropSummary
```

`Graph.export_jsonl` and `Graph.restore_jsonl` return this summary. It reports the number of nodes
and relationships in the operation.
