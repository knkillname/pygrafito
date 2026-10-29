# Import rows and files

:::{admonition} tl;dr
:class: tldr

Map a batch of rows, a CSV file, or a JSONL file into the graph with one write statement. Each
batch binds to `$rows`, and the importer reports rows, batches, and mutations.
:::

Use `Graph.import_rows` or `Graph.import_file` when a write statement should map many input rows.
Each batch binds to `$rows`, so the statement is the mapping; there is no separate column
configuration.

:::{admonition} Remember
:class: important

The import statement must contain a write clause and reference `$rows`. Both are checked before any
row is read.
:::

This guide covers in-memory rows, CSV, JSONL, batching, and failure reporting. The [CLI
reference](../reference/cli.md#import) documents the shell's `.import` command, and
[`ImportSummary`](../api/query.md#importsummary) documents the returned counts.

```{mermaid}
:alt: Rows from memory, CSV, or JSONL flow through a batch and a write statement into the graph.

flowchart LR
  S["Rows, <code>CSV</code>, or <code>JSONL</code>"] --> B["Batch of rows"]
  B --> Q["<code>UNWIND $rows AS row</code><br/>write statement"]
  Q --> G["Graph"]
  Q -->|"first failing row"| E["Error with source,<br/>row, and batch"]
  accTitle: The import pipeline
  accDescr: Input rows are read in batches, each batch runs the write statement against the graph, and a failure stops at the first bad row with its source, row number, and batch number.
```

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

:::{tip}
Use `MERGE` for a restartable import. A duplicate row matches the element the earlier row created
instead of adding a second copy.
:::

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
count are rejected. Blank lines are skipped, and quoted fields and escaped quotes follow the
standard CSV rules. A newline inside a quoted field is preserved exactly: an LF sequence stays LF
and a CRLF sequence stays CRLF on every host platform.

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

The default is non-atomic for throughput: every batch commits on its own. If the process is
terminated during an import, the batches that already committed remain and the interrupted batch
does not. The graph is never corrupt, but a bulk load can be partially present. Pass
`atomic=True` when a bulk load must be all-or-nothing: the whole import is one transaction, so a
failure or a termination leaves no imported row behind. An atomic import holds the write lock for
the whole file and uses more memory for the transaction, so prefer the default for large,
restartable loads.

:::{warning}
The default import is non-atomic. A failure or a termination can leave the batches that already
committed. Pass `atomic=True` when a partial load would be worse than a failed one.
:::

:::{admonition} In detail
:class: detail

With `atomic=True`, the whole file runs in one transaction. A failure rolls back every batch, and a
termination leaves no imported row behind. The cost is a longer write lock and memory proportional
to the transaction.
:::

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
