# Spec Delta

## Purpose

Defines the stable external representation of a graph: a strict, self-verifying JSONL snapshot,
an atomic restore path, read-only SQL views, and the rules external readers may rely on.

## ADDED Requirements

### Requirement: JSONL snapshot structure

A snapshot SHALL be UTF-8 JSONL with one object per line. The first non-blank line SHALL be a
header carrying the format name `pygrafito-jsonl`, version `1`, and the node and relationship
counts. Every following record SHALL be tagged `node` or `relationship`, and every node record
SHALL precede every relationship record.

#### Scenario: Header and phases

- **WHEN** a snapshot contains two nodes and one relationship
- **THEN** the header is the first non-blank line, both node records precede the relationship,
  and the header counts are two and one

#### Scenario: Blank lines

- **WHEN** a snapshot contains blank lines between records
- **THEN** the blank lines are ignored and the record counts are unchanged

#### Scenario: Missing header

- **WHEN** the first non-blank line is not a valid header
- **THEN** restore rejects the file before writing anything

### Requirement: JSONL record shape

A node record SHALL carry `kind`, a positive integer source `id`, an array of labels, and a
properties object. A relationship record SHALL carry `kind`, a positive integer source `id`, a
non-empty type, positive integer `start_id` and `end_id`, and a properties object. Records SHALL
contain no other fields.

#### Scenario: Node record

- **WHEN** a node record carries labels and typed properties
- **THEN** export and restore preserve those labels and properties

#### Scenario: Relationship record

- **WHEN** a relationship record carries a type, endpoints, and properties
- **THEN** export and restore preserve the type, endpoints, and properties

#### Scenario: Unknown field

- **WHEN** a record contains an unknown field
- **THEN** restore rejects the file with the line number

#### Scenario: Missing field

- **WHEN** a record omits a required field
- **THEN** restore rejects the file with the line number

### Requirement: Property and identifier values

Labels, relationship types, and property keys SHALL be non-empty strings without null characters.
Property values SHALL follow the graph's strict value model: booleans, signed 64-bit integers,
finite floats, strings, and homogeneous lists of those scalars. Maps, nested lists, null values,
NaN, and infinities SHALL be rejected.

#### Scenario: Typed values

- **WHEN** a node has a boolean, an integer, a float, a string, and a homogeneous list
- **THEN** restore preserves each value with its type

#### Scenario: Nested value

- **WHEN** a property value is an object or a nested list
- **THEN** restore rejects the file and writes nothing

#### Scenario: Non-finite number

- **WHEN** a line contains `NaN`, `Infinity`, or a number that overflows to infinity
- **THEN** restore rejects the file with the line number

#### Scenario: Out-of-range integer

- **WHEN** a property integer exceeds the signed 64-bit range
- **THEN** restore rejects the file

#### Scenario: Null value

- **WHEN** a property value is null
- **THEN** restore rejects the file

### Requirement: Deterministic canonical output

Export SHALL order nodes and relationships by source id, sort each node's labels, encode
properties as canonical JSON with sorted keys and compact separators, and end every record with a
newline. Exporting the same committed graph twice SHALL produce identical bytes.

#### Scenario: Stable bytes

- **WHEN** the same committed graph is exported twice without changes
- **THEN** the two files are byte-identical

#### Scenario: Sorted labels

- **WHEN** a node has several labels
- **THEN** the exported labels are sorted

#### Scenario: Canonical properties

- **WHEN** a node has properties
- **THEN** their keys are sorted and the JSON is compact

#### Scenario: No ambient data

- **WHEN** a graph is exported
- **THEN** the file contains no timestamp, path, or library version

### Requirement: Snapshot integrity and counts

Restore SHALL verify that the number of node and relationship records matches the header counts.
A mismatch, a truncated final object, or a missing header SHALL reject the whole file and roll
back every change. A header-only snapshot SHALL restore an empty graph.

#### Scenario: Truncated file

- **WHEN** a snapshot is cut after the header but declares nodes
- **THEN** restore fails and the target stays unchanged

#### Scenario: Count mismatch

- **WHEN** the header declares more relationships than the file contains
- **THEN** restore fails and rolls back

#### Scenario: Empty graph

- **WHEN** the file contains only a header with zero counts
- **THEN** restore succeeds with zero nodes and zero relationships

#### Scenario: Truncated final record

- **WHEN** the final line is an incomplete JSON object
- **THEN** restore rejects the file with the line number

### Requirement: Export snapshot consistency

`Graph.export_jsonl` SHALL write one consistent committed snapshot of the graph, stream records
instead of materializing the graph, and return the exported node and relationship counts. It
SHALL work on a read-only handle and SHALL refuse while an explicit transaction is active.

#### Scenario: Read-only export

- **WHEN** a caller exports from a read-only handle
- **THEN** the snapshot is written and the counts are returned

#### Scenario: Active transaction

- **WHEN** a caller exports while an explicit transaction is active
- **THEN** the export is refused and no file is written

#### Scenario: Concurrent writer

- **WHEN** another handle commits while an export runs
- **THEN** the file reflects one committed state

### Requirement: Export destination safety

Export SHALL refuse a destination that already exists unless the caller explicitly requests
overwrite. It SHALL always refuse the open database's own path and its journal sidecars. A failed
export SHALL leave an existing destination untouched and SHALL not leave a partial file at the
destination.

#### Scenario: Existing destination

- **WHEN** the destination exists and overwrite is not requested
- **THEN** the export is refused and the file is unchanged

#### Scenario: Explicit overwrite

- **WHEN** the destination exists and overwrite is requested
- **THEN** the destination is replaced atomically

#### Scenario: Live database path

- **WHEN** the destination is the open database file or a sidecar
- **THEN** the export is refused even with overwrite

#### Scenario: Failed export

- **WHEN** writing fails partway
- **THEN** the destination is unchanged and no partial file remains

### Requirement: Export scope

A snapshot SHALL contain node and relationship data only. It SHALL NOT contain declared indexes,
uniqueness constraints, the journal mode, the schema version, or view definitions.

#### Scenario: Constraints omitted

- **WHEN** a graph has a uniqueness constraint and an index
- **THEN** the snapshot contains only node and relationship records

#### Scenario: Restore preserves target schema

- **WHEN** a snapshot is restored into a graph with indexes and constraints
- **THEN** those declarations remain and are enforced

### Requirement: Restore preconditions and atomic replace

`Graph.restore_jsonl` SHALL require a writable handle with no active transaction. It SHALL
restore into an empty graph by default and SHALL refuse a non-empty target. With replace
requested, it SHALL delete all relationships and nodes and restore in the same transaction, so
any failure restores the original graph.

#### Scenario: Empty target

- **WHEN** a snapshot is restored into an empty graph
- **THEN** every node and relationship is created

#### Scenario: Non-empty target

- **WHEN** the target has nodes and replace is not requested
- **THEN** restore is refused and the target is unchanged

#### Scenario: Atomic replace

- **WHEN** replace is requested and a later record fails
- **THEN** the original graph is restored

#### Scenario: Read-only handle

- **WHEN** restore is requested on a read-only handle
- **THEN** it is refused before the file is read

#### Scenario: Active transaction

- **WHEN** restore is requested while a transaction is active
- **THEN** it is refused

### Requirement: Restore identity and remapping

Restore SHALL assign new node ids in file order and map every relationship endpoint through that
mapping. Source relationship ids SHALL be replaced and SHALL NOT be preserved. A relationship
that refers to a node id not seen in the node phase SHALL reject the file.

#### Scenario: Ids remapped

- **WHEN** a snapshot is restored into a fresh graph
- **THEN** nodes receive new ids and relationships point at the live nodes

#### Scenario: Unknown endpoint

- **WHEN** a relationship references a node id absent from the node phase
- **THEN** restore fails and rolls back

#### Scenario: Duplicate node id

- **WHEN** two node records share a source id
- **THEN** restore fails with the line number

#### Scenario: Data round-trip

- **WHEN** a graph is exported, restored into a fresh graph, and exported again
- **THEN** labels, types, endpoints, and property values match

### Requirement: Restore failure reporting

Restore SHALL stop at the first invalid record, raise a validation error that names the one-based
line number, and roll back the entire transaction. A failed restore SHALL not leave a partial
graph, whether the target was empty or replaced.

#### Scenario: Line number

- **WHEN** line 40 contains an unknown field
- **THEN** the error names line 40 and the file

#### Scenario: No partial graph

- **WHEN** restore fails on the last relationship
- **THEN** no node or relationship from the file remains

#### Scenario: Original graph preserved

- **WHEN** replace fails
- **THEN** the pre-restore nodes and relationships remain

### Requirement: Read-only interop views

A graph database SHALL expose read-only views named `graph_nodes`, `graph_node_labels`,
`graph_relationships`, and `graph_meta`. `graph_nodes` SHALL expose `id`, `labels`, and
`properties`; `graph_node_labels` SHALL expose `node_id` and `label`; `graph_relationships` SHALL
expose `id`, `start_id`, `end_id`, `type`, and `properties`; `graph_meta` SHALL expose `key` and
`value`.

#### Scenario: Node view

- **WHEN** an external reader selects from `graph_nodes`
- **THEN** each row has the node id, a JSON array of labels, and canonical JSON properties

#### Scenario: Label view

- **WHEN** an external reader selects from `graph_node_labels`
- **THEN** each row pairs a node id with one label

#### Scenario: Relationship view

- **WHEN** an external reader selects from `graph_relationships`
- **THEN** each row has the type and both endpoints

#### Scenario: Metadata view

- **WHEN** an external reader selects `view_version` from `graph_meta`
- **THEN** the value is the current view version

#### Scenario: Read-only

- **WHEN** an external reader tries to update or delete through a view
- **THEN** SQLite refuses the write

### Requirement: View publication and versioning

A write-capable open SHALL create missing views, replace views from an older version, and leave
views from a newer version untouched. A read-only open SHALL leave views untouched, so a database
that predates the views remains readable. `Graph.view_version` SHALL report the published
version, or zero when the views are absent.

#### Scenario: Missing views

- **WHEN** a write-capable handle opens a database without views
- **THEN** all four views are created and the version is current

#### Scenario: Older version

- **WHEN** a write-capable handle opens a database with an older view version
- **THEN** the views are replaced and the version is current

#### Scenario: Newer version

- **WHEN** a write-capable handle opens a database with a newer view version
- **THEN** the views are left untouched

#### Scenario: Read-only open

- **WHEN** a read-only handle opens a database without views
- **THEN** the handle works and `Graph.view_version` returns zero

#### Scenario: Engine independence

- **WHEN** the views are absent or dropped externally
- **THEN** graph reads, export, and restore still work

### Requirement: View name collisions

A write-capable open SHALL refuse to publish views when a reserved view name is already held by a
table, or by a view that is not identified by `graph_meta`. It SHALL NOT drop the existing object.
A read-only open SHALL not attempt to resolve the collision.

#### Scenario: Table collision

- **WHEN** a table is named `graph_nodes`
- **THEN** a write-capable open fails and the table is unchanged

#### Scenario: Unidentified view

- **WHEN** a view named `graph_relationships` exists without `graph_meta`
- **THEN** a write-capable open fails and the view is unchanged

#### Scenario: Read-only collision

- **WHEN** a read-only handle opens a database with a colliding table
- **THEN** graph reads still work and no object is changed

### Requirement: External reader contract

External readers SHALL open the file read-only and treat the views as the public read interface.
They SHALL use quoted JSON paths and `json_type` to read typed properties, SHALL not rely on view
row order, and SHALL not write through a view. The views SHALL require only SQLite 3.38 or newer.

#### Scenario: Quoted paths

- **WHEN** a property key contains a dot
- **THEN** a reader using `json_extract(properties, '$."key.with.dot"')` returns it

#### Scenario: Type distinction

- **WHEN** one property is `true` and another is `1`
- **THEN** `json_type` distinguishes them

#### Scenario: No row order

- **WHEN** a reader selects without `ORDER BY`
- **THEN** the result order is not part of the contract

#### Scenario: Minimum runtime

- **WHEN** the views are queried on SQLite 3.38
- **THEN** they work
