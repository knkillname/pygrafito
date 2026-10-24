# Data model

The model objects are immutable snapshots. A read returns the state observed inside one committed
snapshot; the object does not change when the graph changes later.

## Node

```{eval-rst}
.. autoclass:: pygrafito.Node
```

A node behaves as a read-only mapping of property names to values:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    node = graph.add_node("Program", designation="Tron", cycles=40)
    print(node["designation"])  # Tron
    print(dict(node))  # {'cycles': 40, 'designation': 'Tron'}
    print("ISO" in node.labels)  # False
```

## Relationship

```{eval-rst}
.. autoclass:: pygrafito.Relationship
```

A relationship preserves its stored start and end nodes. It also behaves as a read-only property
mapping:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    tron = graph.add_node("Program", designation="Tron")
    quorra = graph.add_node("Program", designation="Quorra")
    relationship = graph.add_relationship(tron, "ALLIES_WITH", quorra, since_cycle=2020)
    print(relationship.start_id, relationship.rel_type, relationship.end_id)
    print(relationship["since_cycle"])  # 2020
```

## Path

```{eval-rst}
.. autoclass:: pygrafito.Path
   :members: length, start, end
```

`Path` is returned by `Graph.shortest_path`. A path with one node has zero relationships and a
zero-length path from a node to itself.

## TraversalStep

```{eval-rst}
.. autoclass:: pygrafito.TraversalStep
```

`Graph.traverse` yields `TraversalStep` values. `depth` is the number of relationships between the
traversal start and the reached node.

## Direction

```{eval-rst}
.. autoclass:: pygrafito.Direction
   :no-members:
```

| Member | Value | Meaning |
| --- | --- | --- |
| `OUTGOING` | `outgoing` | Follow relationships from start to end. |
| `INCOMING` | `incoming` | Follow relationships from end to start. |
| `BOTH` | `both` | Follow relationships in either direction. |

## ElementKind

```{eval-rst}
.. autoclass:: pygrafito.ElementKind
   :no-members:
```

| Member | Value | Meaning |
| --- | --- | --- |
| `NODE` | `node` | A node-scoped index or constraint. |
| `RELATIONSHIP` | `relationship` | A relationship-scoped index or constraint. |

## IndexKind

`IndexKind` is a backward-compatible alias for [`ElementKind`](#elementkind). Both names refer to
the same enum, so `IndexKind.NODE is ElementKind.NODE`.

## Values

Property values are `bool`, signed 64-bit `int`, finite `float`, `str`, or a homogeneous list of
those scalars. Maps, nested lists, stored `None`, NaN, and infinities are rejected. Assigning
`None` removes a property. Query values additionally include `None`, mappings, and graph objects.
