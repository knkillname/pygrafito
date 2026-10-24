# Import rows and files

Use `Graph.import_rows` or `Graph.import_file` when a write statement should map many input rows.
Each batch binds to `$rows`, so the statement is the mapping; there is no separate column
configuration.

This guide covers in-memory rows, CSV, JSONL, batching, and failure reporting. The [CLI
reference](../reference/cli.md#import) documents the shell's `.import` command, and
[`ImportSummary`](../api/query.md#importsummary) documents the returned counts.

## Import in-memory rows

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    summary = graph.import_rows(
        "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
        [{"designation": "Tron"}, {"designation": "Quorra"}],
    )
    print(summary.rows, summary.batches)  # 2 1
    print(summary.mutations.created_nodes)  # 2
    print(sorted(node["designation"] for node in graph.find_nodes("Program")))
    # ['Quorra', 'Tron']
```

The statement must contain a write clause and must reference `$rows`; both are checked before any
row is read. A read-only handle raises `ReadOnlyError` without reading the file, and a closed
handle raises `GraphClosedError`.

## Import a JSONL file

JSONL preserves JSON scalar, list, and mapping types. Each non-blank line must be a JSON object.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "programs.jsonl"
    path.write_text(
        '{"designation": "Kevin Flynn", "cycles": 36}\n'
        '{"designation": "Quorra", "cycles": 37}\n',
        encoding="utf-8",
    )
    with Graph.open(":memory:") as graph:
        summary = graph.import_file(
            path,
            "UNWIND $rows AS row MERGE (n:Program {designation: row.designation}) "
            "ON CREATE SET n.cycles = row.cycles",
        )
        print(summary.rows, summary.mutations.created_nodes)  # 2 2
        print(sorted(node["designation"] for node in graph.find_nodes("Program")))
        # ['Kevin Flynn', 'Quorra']
```

Use `format="jsonl"` to override a suffix that is not `.jsonl` or `.ndjson`. Arrays, scalars,
invalid JSON, and non-finite numbers are rejected with the line number.

## Import CSV and convert values

Every CSV field is a string. Convert it in the statement with `toInteger`, `toFloat`, or
`toString`. The first record is a header; duplicate header names and records with the wrong field
count are rejected. Blank lines are skipped, and quoted fields, escaped quotes, and embedded
newlines follow the standard CSV rules.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "programs.csv"
    path.write_text(
        'designation,cycles\n"Kevin Flynn",36\nQuorra,37\n',
        encoding="utf-8",
    )
    with Graph.open(":memory:") as graph:
        summary = graph.import_file(
            path,
            "UNWIND $rows AS row "
            "CREATE (n:Program {designation: row.designation, "
            "cycles: toInteger(row.cycles)})",
        )
        print(summary.mutations.created_nodes)  # 2
        print(
            sorted(
                (node["designation"], node["cycles"])
                for node in graph.find_nodes("Program")
            )
        )
        # [('Kevin Flynn', 36), ('Quorra', 37)]
```

Use `format="csv"` to override the suffix. An unknown suffix or format is a validation error
before the file is read.

## Import relationships

The statement can match existing endpoints and merge relationship rows:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Kevin Flynn")
    graph.add_node("Program", designation="Quorra")
    summary = graph.import_rows(
        "UNWIND $rows AS row "
        "MATCH (a:Program {designation: row.source}), "
        "(b:Program {designation: row.target}) "
        "MERGE (a)-[r:ALLIES_WITH]->(b) "
        "ON CREATE SET r.since_cycle = row.since_cycle",
        [
            {
                "source": "Kevin Flynn",
                "target": "Quorra",
                "since_cycle": 2020,
            }
        ],
    )
    print(summary.mutations.created_relationships)  # 1
```

`MERGE` runs once per row in order, so duplicate rows create one element and later rows match it.

## Choose batching and atomicity

Rows are read incrementally and executed in batches of `batch_size` (default 1000). Each batch runs
in its own transaction and commits independently. With `atomic=True`, the whole file runs in one
transaction and any failure rolls back every batch.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "programs.jsonl"
    path.write_text(
        '{"designation": "Tron"}\n'
        '{"designation": "Quorra"}\n'
        '{"designation": "Rinzler"}\n',
        encoding="utf-8",
    )
    with Graph.open(":memory:") as graph:
        summary = graph.import_file(
            path,
            "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
            batch_size=2,
            atomic=True,
        )
        print(summary.rows, summary.batches)  # 3 2
```

The batch size must be a positive integer. Empty input executes no statement and returns a summary
with zero rows and zero batches.

## Read the summary and failures

`ImportSummary` reports `rows`, `batches`, and aggregate `mutations`:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    summary = graph.import_rows(
        "UNWIND $rows AS row MERGE (n:Program {designation: row.designation})",
        [{"designation": "Tron"}],
    )
    print(summary.rows)  # 1
    print(summary.batches)  # 1
    print(summary.mutations.created_nodes)  # 1
    print(summary.mutations.properties_set)  # 0
```

The import stops at the first failing batch. That batch does not commit; earlier batches stay
committed unless `atomic=True`. The raised error keeps its original type and carries a note with
the source, the one-based row number, and the batch number. The importer replays the failing batch
row by row inside a rolled-back transaction to find the offending row; the replay changes nothing.

## Go deeper

- [CLI reference](../reference/cli.md#import) for `.import` options and output.
- [`ImportSummary`](../api/query.md#importsummary) and [`MutationSummary`](../api/query.md#mutationsummary)
  in the API reference.
- [Query your graph](querying.md) for the `UNWIND` and `MERGE` forms used by import statements.
