# Errors

Every library error inherits from `PygrafitoError`. Query failures additionally inherit from
`QueryError`, which carries the source position when it is known.

```text
PygrafitoError
|-- GraphClosedError
|-- ValidationError
|-- NotFoundError
|-- ConnectedNodeError
|-- TransactionError
|-- ReadOnlyError
|-- UnsupportedSqliteError
|-- HandleAffinityError
|-- LockTimeoutError
|-- ConstraintViolationError
`-- QueryError
    |-- QuerySyntaxError
    |-- QuerySemanticError
    `-- QueryExecutionError
```

## PygrafitoError

```{eval-rst}
.. autoexception:: pygrafito.PygrafitoError
```

Catch this base class only at a boundary where the program can recover from any library failure.
Prefer a narrower type inside application logic.

## GraphClosedError

```{eval-rst}
.. autoexception:: pygrafito.GraphClosedError
```

## ValidationError

```{eval-rst}
.. autoexception:: pygrafito.ValidationError
```

## NotFoundError

```{eval-rst}
.. autoexception:: pygrafito.NotFoundError
```

## ConnectedNodeError

```{eval-rst}
.. autoexception:: pygrafito.ConnectedNodeError
```

Pass `detach=True` to `Graph.delete` when incident relationships should be removed with the node.

## TransactionError

```{eval-rst}
.. autoexception:: pygrafito.TransactionError
```

## ReadOnlyError

```{eval-rst}
.. autoexception:: pygrafito.ReadOnlyError
```

## UnsupportedSqliteError

```{eval-rst}
.. autoexception:: pygrafito.UnsupportedSqliteError
```

## HandleAffinityError

```{eval-rst}
.. autoexception:: pygrafito.HandleAffinityError
```

Open and use a handle in the same thread.

## LockTimeoutError

```{eval-rst}
.. autoexception:: pygrafito.LockTimeoutError
```

Retry later, or increase `busy_timeout` for a known long writer.

## ConstraintViolationError

```{eval-rst}
.. autoexception:: pygrafito.ConstraintViolationError
```

| Attribute | Meaning |
| --- | --- |
| `kind` | `ElementKind` the constraint covers. |
| `scope` | Label scoped by the constraint, for either element kind. |
| `key` | Property key whose values must stay distinct. |
| `value` | Offending value, or `None` when it is unknown. |
| `existing` | Identifier of the surviving holder, or `None` when the duplicate was rolled back. |

## QueryError

```{eval-rst}
.. autoexception:: pygrafito.QueryError
```

| Attribute | Meaning |
| --- | --- |
| `message` | Description of the failure without the location suffix. |
| `line` | One-based source line, or `None` when unknown. |
| `column` | One-based source column, or `None` when unknown. |

## QuerySyntaxError

```{eval-rst}
.. autoexception:: pygrafito.QuerySyntaxError
```

## QuerySemanticError

```{eval-rst}
.. autoexception:: pygrafito.QuerySemanticError
```

## QueryExecutionError

```{eval-rst}
.. autoexception:: pygrafito.QueryExecutionError
```
