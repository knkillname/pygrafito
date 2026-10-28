# Spec Delta

## MODIFIED Requirements

### Requirement: JSONL snapshot structure

A snapshot SHALL be UTF-8 JSONL with one object per line. The first non-blank line SHALL be a header carrying the format name `pygrafito-jsonl`, version `2`, and the node and relationship counts. Every following record SHALL be tagged `node` or `relationship`, and every node record SHALL precede every relationship record.

#### Scenario: Header and phases

- **WHEN** a snapshot contains two nodes and one relationship
- **THEN** the header is the first non-blank line, both node records precede the relationship, and the header counts are two and one

#### Scenario: Blank lines

- **WHEN** a snapshot contains blank lines between records
- **THEN** the blank lines are ignored and the record counts are unchanged

#### Scenario: Missing header

- **WHEN** the first non-blank line is not a valid header
- **THEN** restore rejects the file before writing anything

#### Scenario: Version 2 header

- **WHEN** a snapshot is exported
- **THEN** the header reports version 2

#### Scenario: Unsupported version

- **WHEN** a snapshot header declares a version other than 2
- **THEN** restore rejects the file with an error that names the supported version

### Requirement: JSONL record shape

A node record SHALL carry `kind`, a positive integer source `id`, an array of labels, and a properties object. A relationship record SHALL carry `kind`, a positive integer source `id`, an array of labels, a boolean `directed`, positive integer `start_id` and `end_id`, and a properties object. Records SHALL contain no other fields.

#### Scenario: Node record

- **WHEN** a node record carries labels and typed properties
- **THEN** export and restore preserve those labels and properties

#### Scenario: Relationship record

- **WHEN** a relationship record carries labels, a directed flag, endpoints, and properties
- **THEN** export and restore preserve the labels, direction, endpoints, and properties

#### Scenario: Unlabeled relationship

- **WHEN** a relationship record carries an empty labels array
- **THEN** export and restore preserve the empty label set

#### Scenario: Undirected relationship

- **WHEN** a relationship record carries `"directed": false`
- **THEN** export and restore preserve the undirected flag

#### Scenario: Unknown field

- **WHEN** a record contains an unknown field
- **THEN** restore rejects the file with the line number

#### Scenario: Missing field

- **WHEN** a record omits a required field
- **THEN** restore rejects the file with the line number

### Requirement: Property and identifier values

Labels and property keys SHALL be non-empty strings without null characters. A relationship label array MAY be empty. Property values SHALL follow the graph's strict value model: booleans, signed 64-bit integers, finite floats, strings, and homogeneous lists of those scalars. Maps, nested lists, null values, NaN, and infinities SHALL be rejected.

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

#### Scenario: Empty relationship labels

- **WHEN** a relationship record carries an empty labels array
- **THEN** restore accepts it and stores an unlabeled relationship

### Requirement: Deterministic canonical output

Export SHALL order nodes and relationships by source id, sort each node's and relationship's labels, encode properties as canonical JSON with sorted keys and compact separators, and end every record with a newline. Exporting the same committed graph twice SHALL produce identical bytes.

#### Scenario: Stable bytes

- **WHEN** the same committed graph is exported twice without changes
- **THEN** the two files are byte-identical

#### Scenario: Sorted labels

- **WHEN** a node has several labels
- **THEN** the exported labels are sorted

#### Scenario: Sorted relationship labels

- **WHEN** a relationship has several labels
- **THEN** the exported labels are sorted

#### Scenario: Canonical properties

- **WHEN** a node has properties
- **THEN** their keys are sorted and the JSON is compact

#### Scenario: No ambient data

- **WHEN** a graph is exported
- **THEN** the file contains no timestamp, path, or library version

### Requirement: Read-only interop views

A graph database SHALL expose read-only views named `graph_nodes`, `graph_node_labels`, `graph_relationships`, and `graph_meta`. `graph_nodes` SHALL expose `id`, `labels`, and `properties`; `graph_node_labels` SHALL expose `node_id` and `label`; `graph_relationships` SHALL expose `id`, `start_id`, `end_id`, `labels`, `directed`, and `properties`; `graph_meta` SHALL expose `key` and `value`.

#### Scenario: Node view

- **WHEN** an external reader selects from `graph_nodes`
- **THEN** each row has the node id, a JSON array of labels, and canonical JSON properties

#### Scenario: Label view

- **WHEN** an external reader selects from `graph_node_labels`
- **THEN** each row pairs a node id with one label

#### Scenario: Relationship view

- **WHEN** an external reader selects from `graph_relationships`
- **THEN** each row has a JSON array of labels, the directed flag, and both endpoints

#### Scenario: Undirected relationship view

- **WHEN** an external reader selects an undirected relationship from `graph_relationships`
- **THEN** the row reports `directed` as false and both endpoints

#### Scenario: Metadata view

- **WHEN** an external reader selects `view_version` from `graph_meta`
- **THEN** the value is the current view version

#### Scenario: Read-only

- **WHEN** an external reader tries to update or delete through a view
- **THEN** SQLite refuses the write

### Requirement: Restore identity and remapping

Restore SHALL assign new node ids in file order and map every relationship endpoint through that mapping. Source relationship ids SHALL be replaced and SHALL NOT be preserved. A relationship that refers to a node id not seen in the node phase SHALL reject the file.

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
- **THEN** labels, direction, endpoints, and property values match


