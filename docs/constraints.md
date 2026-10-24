# Uniqueness constraints

A uniqueness constraint keeps one property value distinct inside one label or one relationship
type. Nodes carrying the label, or relationships of the type, must hold different values for the
constraint's property key. The rule is enforced by the database itself, so it also binds writes
made by an older build or by an external SQLite client.

## Declaring a constraint

Constraints are declared on a graph handle and scoped to exactly one label or one relationship
type:

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
```

A label, relationship type, and property key must be non-empty strings. Declaring the same
constraint twice is a no-op, and declaring a constraint over data that already violates it raises
`ConstraintViolationError` without creating anything. Validation and object creation run in the
same write transaction, so a concurrent writer cannot slip a duplicate between the check and the
enforcing objects.

`Graph.drop_constraint` removes a declared constraint and raises `NotFoundError` when it is not
declared. Constraint changes are refused with `TransactionError` while an explicit transaction is
open on the same handle and with `ReadOnlyError` on a read-only handle. Listing constraints works
on a read-only handle.

## Type-sensitive values

A constraint compares the stored value and its JSON type. `true`, `1`, `1.0`, and `"1"` are four
different values, and lists compare by content and order. An element that does not carry the
scope label or type, or that does not have the property, is exempt.

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
        print(error.scope, error.key, error.value)  # Program state True
```

Absent properties are never values, so any number of elements in the scope may omit the key.

## Enforcement

The database enforces every declared constraint on every write path: element creation, property
assignment and removal, label acquisition, statement-driven writes, and batch imports. A write
that would create a duplicate fails and changes nothing; deleting the holder releases the value.

Enforcement is immediate. A violation fails the statement that causes it, not the transaction's
commit, so a transaction never holds a transient duplicate. A failed statement undoes only its
own changes and leaves the transaction usable.

Assigning two elements each other's values in one statement fails because the statement passes
through a duplicate. Use a temporary value or two statements instead.

```python
from pygrafito import ConstraintViolationError, Graph

with Graph.open(":memory:") as graph:
    graph.create_node_uniqueness_constraint("Program", "designation")
    with graph.transaction() as transaction:
        tron = transaction.add_node("Program", designation="Tron")
        try:
            transaction.add_node("Program", designation="Tron")
        except ConstraintViolationError:
            pass
        quorra = transaction.add_node("Program", designation="Quorra")

    print(graph.node(quorra.id)["designation"])  # Quorra
```

## Violation reporting

`ConstraintViolationError` carries `kind`, `scope`, `key`, `value`, and `existing`. `existing` is
the identifier of the surviving element that already holds the value, or `None` when the
duplicate was created and rolled back by the same statement. A storage failure that is not a
uniqueness violation is never translated into this error.

## Persistence and storage

Constraints persist in the database file and are reported and enforced after a reopen without
being declared again. They are implemented with standard indexes and triggers, not with a
catalog table, so they do not change the recorded schema version. A file that carries
constraints remains openable by an older build, which remains bound by them and reports a raw
integrity error instead of a domain error when a write violates one.

A relationship constraint is a partial unique index over the relationship table. A node
constraint is a support index plus one trigger for property updates and one for label
acquisition, because a label lives in a separate table. The support index and the unique index
are not reported by `Graph.indexes()`; they belong to the constraint and are dropped with it.
Declaring an ordinary index on the same key as a relationship constraint is redundant.

## When the scope changes

Constraints are declared for a label or relationship type that already exists as a concept; the
database does not create labels or types. Declaring a constraint whose scope has no elements
succeeds, and the rule starts applying as soon as an element acquires that scope.
