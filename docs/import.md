# Import

`pygrafito` imports rows with one write statement. Each batch of rows binds to
the `$rows` parameter, and the statement performs the mapping. There is no
separate column-mapping configuration and no CSV type inference: JSONL preserves
value types, while CSV values are strings that the statement converts.

## Entry points

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    summary = graph.import_rows(
        "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
        [{"designation": "Tron"}, {"designation": "Quorra"}],
    )
    print(summary.rows)  # 2
```

`Graph.import_file(path, statement, *, format=None, batch_size=1000, atomic=False)`
reads a file. `Graph.import_rows(statement, rows, *, batch_size=1000, atomic=False)`
accepts any iterable of mappings.

The statement must contain a write clause and must reference `$rows`. Both are
checked before any row is read. A read-only handle raises `ReadOnlyError`
without reading the file, and a closed handle raises `GraphClosedError`.

## Formats

| Format | Suffix | Values |
| --- | --- | --- |
| CSV | `.csv` | Every field is a string. |
| JSONL | `.jsonl`, `.ndjson` | JSON scalars, lists, and mappings keep their types. |

`format="csv"` or `format="jsonl"` overrides the suffix. An unknown suffix or
format is a validation error before the file is read.

### CSV

The first record is a header. Duplicate header names are rejected, as are
records whose field count differs from the header. Blank lines are skipped.
Quoted fields, escaped quotes, and embedded newlines follow the standard CSV
rules.

```text
designation,cycles
"Kevin Flynn",36
Quorra,37
```

CSV values are strings, so convert them in the statement:

```python
graph.import_file(
    "programs.csv",
    "UNWIND $rows AS row CREATE (n:Program {designation: row.designation, "
    "cycles: toInteger(row.cycles)})",
)
```

### JSONL

Each non-blank line must be a JSON object. Arrays, scalars, invalid JSON, and
non-finite numbers are rejected with the line number.

```text
{"designation": "Kevin Flynn", "cycles": 36}
{"designation": "Quorra", "cycles": 37, "tags": ["ISO"]}
```

## The statement is the mapping

A row is a mapping, so `row.field` reads one field. The statement can use any
supported write clause, including `MERGE` for idempotent loads:

```text
UNWIND $rows AS row
MERGE (n:Program {designation: row.designation})
ON CREATE SET n.cycles = row.cycles
ON MATCH SET n.cycles = n.cycles + 1
```

Relationship rows work the same way when the endpoints are already imported:

```text
UNWIND $rows AS row
MATCH (a:Program {designation: row.source}), (b:Program {designation: row.target})
MERGE (a)-[r:ALLIES_WITH]->(b)
```

`MERGE` runs once per row in order, so duplicate rows create one element and
later rows match it.

## Batching and atomicity

Rows are read incrementally and executed in batches of `batch_size` (default
1000). Each batch runs in its own transaction and commits independently. With
`atomic=True`, the whole file runs in one transaction and any failure rolls back
every batch.

```python
graph.import_file("programs.jsonl", statement, batch_size=500, atomic=True)
```

The batch size must be a positive integer. Empty input executes no statement and
returns a summary with zero rows and zero batches.

## Summary

The returned `ImportSummary` reports `rows`, `batches`, and aggregate mutation
counts:

```python
summary = graph.import_rows(statement, rows)
print(summary.rows)
print(summary.batches)
print(summary.mutations.created_nodes)
print(summary.mutations.properties_set)
```

Duplicate `MERGE` rows count one creation even when they produce several result
rows.

## Failures

The import stops at the first failing batch. The failing batch does not commit;
earlier batches stay committed unless `atomic=True` is used. The raised error
keeps its original type and carries a note with the source, the one-based row
number, and the batch number:

```text
QueryExecutionError: mappings are not storable property values
  while importing programs.jsonl row 3 (batch 1)
```

When a batch fails, the importer replays that batch row by row inside a
rolled-back transaction to find the offending row. The replay changes nothing.

## Shell

The same importer is available as `.import`:

```console
grid.db> .import programs.jsonl --statement "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})"
imported 2 rows in 1 batches; created 2 nodes/0 relationships; ...
```

See [`cli.md`](cli.md) for the command options.
