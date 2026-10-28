# Move data in and out

:::{admonition} tl;dr
:class: tldr

Export a consistent snapshot to JSONL, restore it into a graph, or read the database through the
read-only SQL views. Export and restore are the portable path; views are for external readers.
:::

Use `Graph.export_jsonl` and `Graph.restore_jsonl` to move a whole graph through a portable file.
Use the read-only SQL views when another process or tool should read the database directly.

This guide covers the common paths. [Snapshot format](../reference/snapshot-format.md) owns the
record grammar, value rules, strictness, restore guarantees, and view schema.

```{mermaid}
:alt: A graph exports to a JSONL snapshot, which restores into another graph; read-only SQL views expose the live database.

flowchart LR
  G["<code>Graph</code><br/><code>grid.db</code>"] -->|<code>export_jsonl</code>| J["<code>grid.jsonl</code><br/>version 2"]
  J -->|<code>restore_jsonl</code>| R["<code>Graph</code><br/>new or replaced"]
  G ---|"read-only views"| V["<code>graph_nodes</code><br/><code>graph_relationships</code>"]
  accTitle: Snapshot round trip and read-only views
  accDescr: A graph exports to a version 2 JSONL snapshot and restores into a new or replaced graph. Separately, read-only SQL views expose the live database to external readers.
```

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
        ares = graph.add_node("Program", designation="Ares", cycles=60)
        athena = graph.add_node("Program", designation="Athena", cycles=59)
        graph.add_relationship(ares, "ALLIES_WITH", athena, since_cycle=2025)
        summary = graph.export_jsonl(destination)
        print(summary.nodes, summary.relationships)  # 2 1
```

The file starts with a header carrying the format version and counts, followed by tagged node and
relationship records in deterministic order. The live database path and its journal sidecars are
never valid destinations.

:::{tip}
Pass `overwrite=True` only when replacing an old snapshot is the intent. Without it, an existing
destination is refused and left untouched.
:::

:::{warning}
Never export to the live database path or its `-wal`, `-shm`, or `-journal` sidecars. The export
refuses those destinations because replacing them would damage the live store.
:::

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
        source.add_node("Program", designation="Ares", cycles=60)
        source.add_node("Program", designation="Athena", cycles=59)
        source.export_jsonl(destination)

    with Graph.open(":memory:") as restored:
        summary = restored.restore_jsonl(destination)
        print(summary.nodes, summary.relationships)  # 2 0
        print(sorted(node["designation"] for node in restored.find_nodes("Program")))
        # ['Ares', 'Athena']
```

Restore remaps node and relationship ids, verifies the header counts, and runs in one transaction.
Indexes and uniqueness constraints stay with the target and are enforced during the load.

:::{admonition} Remember
:class: important

Restore remaps ids. A node id from the source file is not a stable external key, so look elements up
by a property you control instead of by id.
:::

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
        graph.add_node("Program", designation="Athena", cycles=59)
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

:::{admonition} In detail
:class: detail

The snapshot is a header record followed by node records and then relationship records. The header
counts are part of the contract: restore rejects a truncated file, an extra record, or a header
that claims elements the file does not contain.
:::

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
