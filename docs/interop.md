# Data interop

A graph file is ordinary SQLite, and this change makes that file a supported interface in two
ways: a portable JSONL snapshot and a set of read-only SQL views. This page documents the
snapshot contract first; the export, restore, and view sections follow below.

## Export

`Graph.export_jsonl(path, *, overwrite=False)` writes one consistent committed snapshot of the
graph. It streams nodes and relationships instead of materializing the graph, and returns an
`InteropSummary` with the node and relationship counts.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    destination = pathlib.Path(directory) / "grid.jsonl"
    with Graph.open(":memory:") as graph:
        graph.add_node("Program", designation="Tron")
        graph.add_node("Program", designation="Quorra")
        summary = graph.export_jsonl(destination)
        print(summary.nodes)          # 2
        print(summary.relationships)  # 0
    print(destination.read_text(encoding="utf-8").splitlines()[0])
```

An export runs inside one read snapshot, so a writer committing on another handle cannot produce
a file that mixes two states. It works on a read-only handle. It refuses while an explicit
transaction is active, because the file would otherwise contain uncommitted work.

An existing destination is refused unless `overwrite=True` is passed. Even with overwrite, the
open database path and its `-wal`, `-shm`, and `-journal` sidecars are always refused; exporting
to those paths would replace the live store or leave a file SQLite may treat as a log. A failed
export leaves an existing destination untouched and does not leave a partial file behind.

## Snapshot format

A snapshot is UTF-8 JSONL: one JSON object per line, with `\n` line endings and no byte-order
mark. The first non-blank line is a header, followed by node records and then relationship
records.

```jsonl
{"kind":"header","format":"pygrafito-jsonl","version":1,"nodes":3,"relationships":2}
{"kind":"node","id":1,"labels":["Program"],"properties":{"designation":"Tron"}}
{"kind":"node","id":2,"labels":["Program","ISO"],"properties":{"designation":"Quorra"}}
{"kind":"node","id":3,"labels":[],"properties":{"cycles":37}}
{"kind":"relationship","id":1,"type":"ALLIES_WITH","start_id":1,"end_id":2,"properties":{"since_cycle":2020}}
{"kind":"relationship","id":2,"type":"ALLIES_WITH","start_id":2,"end_id":3,"properties":{}}
```

### Header

The header carries exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | Always `header`. |
| `format` | string | Always `pygrafito-jsonl`. |
| `version` | integer | Snapshot format version, currently `1`. |
| `nodes` | integer | Number of node records that follow. |
| `relationships` | integer | Number of relationship records that follow. |

The counts are part of the contract: restore compares them with the records it actually read.
A truncated file, a file with extra records, or a header-only file that claims elements is
rejected instead of being restored as a smaller graph.

### Node records

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | Always `node`. |
| `id` | positive integer | Source node identifier, used by relationship endpoints. |
| `labels` | array of strings | Labels attached to the node; may be empty. |
| `properties` | object | Typed property values; may be empty. |

### Relationship records

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | Always `relationship`. |
| `id` | positive integer | Source relationship identifier. It is informational and is not preserved. |
| `type` | non-empty string | Relationship type. |
| `start_id` | positive integer | Source id of the start node. |
| `end_id` | positive integer | Source id of the end node. |
| `properties` | object | Typed property values; may be empty. |

Every node record precedes every relationship record. A relationship endpoint must name a node
that appeared in the node phase.

### Values

Labels, relationship types, and property keys are non-empty strings without null characters.
Property values follow the same strict model as the store:

- booleans, signed 64-bit integers, finite floats, and strings;
- homogeneous lists of those scalars;
- no maps, nested lists, stored `null`, `NaN`, or infinities.

A property value the store cannot represent is a malformed snapshot, not a value to coerce.

### Ordering and determinism

Export writes nodes in source-id order, then relationships in source-id order. Each node's labels
are sorted, property keys are sorted, and the JSON is compact. Exporting the same committed graph
twice produces identical bytes. No timestamp, filesystem path, or library version is embedded.

### Strictness

Records contain exactly the fields listed above. Unknown fields, missing fields, duplicate JSON
keys, wrong types, and non-finite numbers are rejected with the one-based line number. Blank
lines are ignored, but the header must be the first non-blank line.

Indexes, uniqueness constraints, the journal mode, the schema version, and the views are not part
of a snapshot. A snapshot preserves node and relationship data; it does not migrate schema
objects.

Node identifiers in the file are source references. Restore assigns new identifiers in file
order, so treat the exported ids as links inside one snapshot rather than durable external keys.

## Restore

`Graph.restore_jsonl(path, *, replace=False)` loads a snapshot in one transaction. By default the
target must be empty; a non-empty target is refused so that a typo cannot silently merge two
graphs.

```python
import pathlib
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    destination = pathlib.Path(directory) / "grid.jsonl"
    with Graph.open(":memory:") as graph:
        graph.add_node("Program", designation="Tron")
        graph.export_jsonl(destination)

    with Graph.open(":memory:") as restored:
        summary = restored.restore_jsonl(destination)
        print(summary.nodes)          # 1
        print(summary.relationships)  # 0
```

With `replace=True`, the current relationships and nodes are deleted and the snapshot is loaded in
the same transaction. If any record fails, the delete is rolled back too, so the original graph
survives a failed replacement. This is safer than clearing the graph in one transaction and
restoring it in another.

Restore reads the header first, then streams records. It assigns new node ids in file order,
rewrites every relationship endpoint through that mapping, and verifies the header counts at the
end of the file. Source relationship ids are replaced and are not preserved. An invalid record,
an unknown endpoint, a duplicate node id, a phase violation, or a count mismatch stops the
restore with the one-based line number and rolls back the whole transaction.

Indexes and uniqueness constraints stay with the target and are enforced during the load. A
snapshot that is valid without a constraint can therefore fail against a target that declares
one; the transaction rolls back and the target is unchanged.

The id map is held in memory for the duration of the restore, so a restore uses memory
proportional to the number of nodes. A large restore also holds the write lock for the whole
file; run it during a quiet period when other writers need the graph.

## SQL views

A graph file exposes four read-only views for external SQL readers:

| View | Columns | Meaning |
| --- | --- | --- |
| `graph_nodes` | `id` INTEGER, `labels` TEXT, `properties` TEXT | One row per node. `labels` is a JSON array and `properties` is canonical JSON text. |
| `graph_node_labels` | `node_id` INTEGER, `label` TEXT | One row per node label, for readers that do not use JSON functions. |
| `graph_relationships` | `id` INTEGER, `start_id` INTEGER, `end_id` INTEGER, `type` TEXT, `properties` TEXT | One row per directed relationship. |
| `graph_meta` | `key` TEXT, `value` TEXT | Metadata records, including `format` and `view_version`. |

```python
import pathlib
import sqlite3
import tempfile

from pygrafito import Graph

with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "grid.db"
    with Graph.open(path) as graph:
        graph.add_node("Program", designation="Tron", cycles=40)
        print(graph.view_version)  # 1

    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as reader:
        rows = reader.execute(
            "SELECT id, labels, properties FROM graph_nodes ORDER BY id"
        ).fetchall()
        print(rows[0][1])  # ["Program"]
        print(
            reader.execute(
                "SELECT value FROM graph_meta WHERE key = 'view_version'"
            ).fetchone()[0]
        )  # 1
```

The views are created on a write-capable open and are never used by the engine for its own
reads. A read-only open leaves them untouched, so a database that predates the views stays
readable; open it with a write-capable handle once to publish them. `Graph.view_version` returns
the published version, or `0` when the views are absent.

Views are versioned through `graph_meta`. A write-capable open creates missing views, replaces
views from an older version, and leaves views from a newer version alone. A reserved
`graph_*` name held by a table, or a reserved view that is not identified by `graph_meta`, makes
the write-capable open fail rather than dropping the existing object. A read-only open does not
resolve collisions.

External readers should open the file read-only. Use quoted JSON paths and `json_type` when
reading typed properties, because SQLite conflates booleans with integers and integers with
reals:

```sql
SELECT id,
       json_type(properties, '$."is_iso"') AS value_type,
       json_extract(properties, '$."is_iso"') AS value
  FROM graph_nodes;
```

Use `json_extract(properties, '$."key.with.dots"')` for a key containing dots; never concatenate
the key into an unquoted path. View row order is not part of the contract, so add `ORDER BY` when
order matters. The views require SQLite 3.38 or newer and are read-only: SQLite refuses `INSERT`,
`UPDATE`, and `DELETE` through a view.
