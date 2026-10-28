# Enforce unique values

Use a uniqueness constraint when one property value must stay distinct inside one label, whether
the elements are nodes or relationships. The database enforces the rule on every write path,
including writes made by an external SQLite client.

This guide covers declaring, using, diagnosing, and removing a constraint. The API reference
documents [`Constraint`](../api/admin.md#constraint) and
[`ConstraintViolationError`](../api/errors.md#constraintviolationerror).

## Declare a constraint

A constraint is scoped to exactly one label and one property key. A relationship constraint
applies to every relationship carrying that label, including a relationship with other labels.

```python
from pygrafito import ElementKind, Graph

with Graph.open(":memory:") as graph:
    node_constraint = graph.create_node_uniqueness_constraint("Program", "designation")
    relationship_constraint = graph.create_relationship_uniqueness_constraint(
        "ALLIES_WITH",
        "since",
    )

    print(node_constraint.kind is ElementKind.NODE)  # True
    print(relationship_constraint.scope)  # ALLIES_WITH
    print([(item.kind.value, item.scope, item.key) for item in graph.constraints()])
    # [('node', 'Program', 'designation'), ('relationship', 'ALLIES_WITH', 'since')]

    graph.drop_constraint(relationship_constraint)
    print([(item.kind.value, item.scope, item.key) for item in graph.constraints()])
    # [('node', 'Program', 'designation')]
```

A label and property key must be non-empty strings. Declaring the same
constraint twice is a no-op. Declaring a constraint over data that already violates it raises
`ConstraintViolationError` without creating anything. Validation and object creation run in the
same write transaction, so a concurrent writer cannot slip a duplicate between the check and the
enforcing objects.

`Graph.drop_constraint` raises `NotFoundError` when the constraint is not declared. Constraint
changes are refused with `TransactionError` while an explicit transaction is open on the same
handle, and with `ReadOnlyError` on a read-only handle. Listing constraints works on a read-only
handle.

## Understand type-sensitive values

A constraint compares the stored value and its JSON type. `true`, `1`, `1.0`, and `"1"` are four
different values, and lists compare by content and order. An element that does not carry the scope
label, or does not have the property, is exempt.

```python
from pygrafito import ConstraintViolationError, Graph

with Graph.open(":memory:") as graph:
    graph.create_node_uniqueness_constraint("Program", "state")
    graph.add_node("Program", state=True)
    graph.add_node("Program", state=1)      # distinct from true
    graph.add_node("Program", state=1.0)    # distinct from 1
    graph.add_node("Program", state="1")    # distinct from every number
    graph.add_node("ISO", state=True)       # outside the Program scope

    try:
        graph.add_node("Program", state=True)
    except ConstraintViolationError as error:
        print(error.scope, error.key, error.value, error.existing)  # Program state True 1
```

Absent properties are never values, so any number of elements in the scope may omit the key.

## Diagnose a violation

`ConstraintViolationError` carries `kind`, `scope`, `key`, `value`, and `existing`. `existing` is
the identifier of the surviving element that already holds the value, or `None` when the duplicate
was created and rolled back by the same statement. A storage failure that is not a uniqueness
violation is never translated into this error.

## How enforcement works

The database enforces every declared constraint on element creation, property assignment and
removal, label acquisition, statement-driven writes, and batch imports. A write that would create
a duplicate fails and changes nothing; deleting the holder releases the value.

Enforcement is immediate. A violation fails the statement that causes it, not the transaction's
commit, so a transaction never holds a transient duplicate. A failed statement undoes only its own
changes and leaves the transaction usable.

```python
from pygrafito import ConstraintViolationError, Graph

with Graph.open(":memory:") as graph:
    graph.create_node_uniqueness_constraint("Program", "designation")
    with graph.transaction() as transaction:
        yori = transaction.add_node("Program", designation="Yori")
        try:
            transaction.add_node("Program", designation="Yori")
        except ConstraintViolationError:
            pass
        dumont = transaction.add_node("Program", designation="Dumont")

    print(graph.node(dumont.id)["designation"])  # Dumont
```

Assigning two elements each other's values in one statement fails because the statement passes
through a duplicate. Use a temporary value or two statements instead.

## Persistence and storage

Constraints persist in the database file and are reported and enforced after a reopen without
being declared again. They are implemented with standard indexes and triggers, not with a catalog
table, so they do not change the recorded schema version.

Both element kinds use a support index plus one trigger for property updates and one for label
acquisition, because a label lives in a separate table. The support index and the triggers are not
reported by
`Graph.indexes()`; they belong to the constraint and are dropped with it. Declaring an ordinary
index on the same key as a relationship constraint is redundant.

## When the scope changes

Constraints are declared for a label that already exists as a concept; the database does not
create labels. Declaring a constraint whose scope has no elements
succeeds, and the rule starts applying as soon as an element acquires that scope.

## Go deeper

- [`Constraint`](../api/admin.md#constraint), [`ElementKind`](../api/model.md#elementkind), and
  [`ConstraintViolationError`](../api/errors.md#constraintviolationerror) in the API reference.
- [Speed up property filters](indexes.md) for the relationship between ordinary indexes and
  constraint-owned indexes.
- [Import rows and files](importing.md) for constraint behavior during batch loads.
