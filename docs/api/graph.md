# Graph and transactions

`Graph` is the public facade for one embedded property graph. Construct it with
[`Graph.open`](#pygrafito.Graph.open); the constructor is internal.

:::{py:class} pygrafito.Graph
An embedded property graph backed by one SQLite connection.

A graph handle owns one connection and is not thread-safe. Use it from the thread that opened it
and close it with the context manager or `close`.
:::

## Lifecycle

```{eval-rst}
.. automethod:: pygrafito.Graph.open
```


```{eval-rst}
.. autoproperty:: pygrafito.Graph.journal_mode
```

```{eval-rst}
.. autoproperty:: pygrafito.Graph.view_version
```

```{eval-rst}
.. automethod:: pygrafito.Graph.close
```

## Transactions

```{eval-rst}
.. automethod:: pygrafito.Graph.transaction
```

A transaction can be used as a context manager or driven explicitly with `begin`, `commit`, and
`rollback`.

:::{py:class} pygrafito.Transaction
One explicit write transaction started with `BEGIN IMMEDIATE`.

Create it with [`Graph.transaction`](#pygrafito.Graph.transaction). Entering the context block
starts the transaction; leaving it commits or rolls back.
:::

### Transaction lifecycle

```{eval-rst}
.. automethod:: pygrafito.Transaction.begin
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.commit
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.rollback
```

### Transaction writes

```{eval-rst}
.. automethod:: pygrafito.Transaction.add_node
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.add_relationship
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.set_properties
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.remove_properties
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.add_labels
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.remove_labels
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.delete
```

### Transaction reads

```{eval-rst}
.. automethod:: pygrafito.Transaction.node
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.relationship
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.find_nodes
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.find_relationships
```

```{eval-rst}
.. automethod:: pygrafito.Transaction.query
```

## Queries

```{eval-rst}
.. automethod:: pygrafito.Graph.query
```

```{eval-rst}
.. automethod:: pygrafito.Graph.prepare
```

## Import and export

```{eval-rst}
.. automethod:: pygrafito.Graph.import_rows
```

```{eval-rst}
.. automethod:: pygrafito.Graph.import_file
```

```{eval-rst}
.. automethod:: pygrafito.Graph.export_jsonl
```

```{eval-rst}
.. automethod:: pygrafito.Graph.restore_jsonl
```

## Indexes

```{eval-rst}
.. automethod:: pygrafito.Graph.create_node_index
```

```{eval-rst}
.. automethod:: pygrafito.Graph.create_relationship_index
```

```{eval-rst}
.. automethod:: pygrafito.Graph.drop_index
```

```{eval-rst}
.. automethod:: pygrafito.Graph.indexes
```

## Uniqueness constraints

```{eval-rst}
.. automethod:: pygrafito.Graph.create_node_uniqueness_constraint
```

```{eval-rst}
.. automethod:: pygrafito.Graph.create_relationship_uniqueness_constraint
```

```{eval-rst}
.. automethod:: pygrafito.Graph.constraints
```

```{eval-rst}
.. automethod:: pygrafito.Graph.drop_constraint
```

## Maintenance

```{eval-rst}
.. automethod:: pygrafito.Graph.explain
```

```{eval-rst}
.. automethod:: pygrafito.Graph.backup_to
```

```{eval-rst}
.. automethod:: pygrafito.Graph.check_integrity
```

## Writes

```{eval-rst}
.. automethod:: pygrafito.Graph.add_node
```

```{eval-rst}
.. automethod:: pygrafito.Graph.add_relationship
```

```{eval-rst}
.. automethod:: pygrafito.Graph.set_properties
```

```{eval-rst}
.. automethod:: pygrafito.Graph.remove_properties
```

```{eval-rst}
.. automethod:: pygrafito.Graph.add_labels
```

```{eval-rst}
.. automethod:: pygrafito.Graph.remove_labels
```

```{eval-rst}
.. automethod:: pygrafito.Graph.delete
```

## Reads

```{eval-rst}
.. automethod:: pygrafito.Graph.node
```

```{eval-rst}
.. automethod:: pygrafito.Graph.relationship
```

```{eval-rst}
.. automethod:: pygrafito.Graph.find_nodes
```

```{eval-rst}
.. automethod:: pygrafito.Graph.find_relationships
```

## Traversal

```{eval-rst}
.. automethod:: pygrafito.Graph.traverse
```

```{eval-rst}
.. automethod:: pygrafito.Graph.shortest_path
```

```{eval-rst}
.. automethod:: pygrafito.Graph.paths
```
