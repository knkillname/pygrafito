# Move data in and out

Use `Graph.export_jsonl` and `Graph.restore_jsonl` to move a whole graph through a portable file.
Use the read-only SQL views when another process or tool should read the database directly.

This guide covers the common paths. [Snapshot format](../reference/snapshot-format.md) owns the
record grammar, value rules, strictness, restore guarantees, and view schema.

## Export a snapshot

`export_jsonl` writes one consistent committed state, streams the graph, and returns the element
counts. An existing destination is refused unless `overwrite=True`.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    destination = pathlib.Path(directory) / "grid.jsonl"
    with Graph.open(":memory:") as graph:
        tron = graph.add_node("Program", designation="Tron", cycles=40)
        quorra = graph.add_node("Program", designation="Quorra", cycles=37)
        graph.add_relationship(tron, "ALLIES_WITH", quorra, since_cycle=2020)
        summary = graph.export_jsonl(destination)
        print(summary.nodes, summary.relationships)  # 2 1
```

The file starts with a header carrying the format version and counts, followed by tagged node and
relationship records in deterministic order. The live database path and its journal sidecars are
never valid destinations.

## Restore a snapshot

Restore requires an empty target by default. Pass `replace=True` to clear a populated graph and
load the snapshot in one transaction; a failure restores the original graph.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    destination = pathlib.Path(directory) / "grid.jsonl"
    with Graph.open(":memory:") as source:
        source.add_node("Program", designation="Tron", cycles=40)
        source.add_node("Program", designation="Quorra", cycles=37)
        source.export_jsonl(destination)

    with Graph.open(":memory:") as restored:
        summary = restored.restore_jsonl(destination)
        print(summary.nodes, summary.relationships)  # 2 0
        print(sorted(node["designation"] for node in restored.find_nodes("Program")))
        # ['Quorra', 'Tron']
```

Restore remaps node and relationship ids, verifies the header counts, and runs in one transaction.
Indexes and uniqueness constraints stay with the target and are enforced during the load.

## Read through SQL views

A write-capable open publishes four read-only views: `graph_nodes`, `graph_node_labels`,
`graph_relationships`, and `graph_meta`. `graph_relationships` exposes a JSON `labels` array and a
`directed` flag (`1` or `0`) instead of a single relationship type. Open the file read-only from
the external reader.

```python
import pathlib
import sqlite3
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Tron", cycles=40)
        print(graph.view_version)  # 2

    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as reader:
        rows = reader.execute(
            "SELECT id, labels, properties FROM graph_nodes ORDER BY id"
        ).fetchall()
        print(rows[0][1])  # ["Program"]
        version = reader.execute(
            "SELECT value FROM graph_meta WHERE key = 'view_version'"
        ).fetchone()[0]
        print(version)  # 2
```

Properties are canonical JSON text. Use `json_type` and `json_extract` together when a predicate
must be type-sensitive, and quote JSON paths that contain dots or spaces. View row order is not
part of the contract, so add `ORDER BY` when order matters.

```sql
SELECT id,
       json_type(properties, '$."is_iso"') AS value_type,
       json_extract(properties, '$."is_iso"') AS value
  FROM graph_nodes;
```

## Know the guarantees

- Export observes one committed state and refuses to replace the live database or its sidecars.
- Restore is atomic; `replace=True` restores the previous graph if loading fails.
- Views are versioned through `graph_meta`; a read-only open leaves older files untouched.
- A snapshot that is valid without a constraint can fail against a target that declares one.

## Go deeper

- [Snapshot format](../reference/snapshot-format.md) for the header, record tags, value rules,
  ordering, strictness, and view versioning.
- [`InteropSummary`](../api/admin.md#interopsummary) and [`Graph`](../api/graph.md) in the API
  reference.
- [Import rows and files](importing.md) when the source is CSV or JSONL rows rather than a snapshot.
