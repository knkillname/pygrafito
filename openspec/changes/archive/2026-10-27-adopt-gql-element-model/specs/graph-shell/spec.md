# Spec Delta

## MODIFIED Requirements

### Requirement: Graph introspection commands

The session SHALL provide `.schema`, `.labels`, `.reltypes`, `.indexes`, `.node ID`, `.rel ID`,
`.expand ID [DEPTH]`, `.path START END`, and `.explain STATEMENT`. These commands SHALL report
metadata and neighborhood information without modifying the graph.

#### Scenario: Schema summary

- **WHEN** a caller submits `.schema`
- **THEN** node labels with node counts and property keys, relationship labels with relationship counts and direction counts, and declared indexes are reported in sorted order

#### Scenario: Node details

- **WHEN** a caller submits `.node` with an existing id
- **THEN** its sorted labels, its properties, and its incident relationships with direction and neighbor are shown

#### Scenario: Undirected neighbor

- **WHEN** a node is incident to an undirected relationship
- **THEN** `.node` reports the relationship as undirected and names the other endpoint

#### Scenario: Relationship details

- **WHEN** a caller submits `.rel` with an existing id
- **THEN** its sorted labels, directed flag, start node, end node, and properties are shown

#### Scenario: Expand a neighborhood

- **WHEN** a caller submits `.expand` with an id and an optional depth
- **THEN** a tree of reachable relationships is rendered, the depth defaults to one, each node appears at most once, undirected relationships are followed from either endpoint, and a negative or non-integer depth is rejected

#### Scenario: Shortest path

- **WHEN** a caller submits `.path` with two node ids
- **THEN** the shortest path is rendered, including undirected relationships, or the session reports that no path exists

#### Scenario: Explain without executing

- **WHEN** a caller submits `.explain` with a valid statement
- **THEN** the plan lines are printed and the graph is unchanged

#### Scenario: Missing element

- **WHEN** a caller refers to a node or relationship id that does not exist
- **THEN** the session reports a not-found error and remains usable

### Requirement: Result rendering modes

The session SHALL render results as `table`, `json`, `jsonl`, `csv`, or `line`, selectable by
option and by `.mode`. Columns SHALL appear in projection order. Headers SHALL be shown by default
and toggled by `.headers`. Nulls, lists, maps, and graph entities SHALL have a defined rendering in
every mode.

#### Scenario: Table rendering

- **WHEN** a result renders as a table
- **THEN** a header row names the columns and each value is aligned under its column

#### Scenario: Headers disabled

- **WHEN** headers are disabled
- **THEN** the header row is omitted and rows are unchanged

#### Scenario: JSON rendering

- **WHEN** a result renders as JSON
- **THEN** the output is an array of one object per row, with keys in projection order

#### Scenario: JSON lines rendering

- **WHEN** a result renders as JSON lines
- **THEN** each row is printed as one JSON object on its own line

#### Scenario: CSV quoting

- **WHEN** a value contains a comma, a double quote, or a newline in CSV mode
- **THEN** the field is quoted according to CSV rules so the row parses back unchanged

#### Scenario: Graph entity rendering

- **WHEN** a result contains a node, relationship, or path value
- **THEN** table and line modes show a graph-shaped form and JSON modes emit a tagged object with the entity's id, labels, properties, and, for a relationship, its directed flag and endpoints

#### Scenario: Undirected relationship rendering

- **WHEN** a result contains an undirected relationship
- **THEN** its rendering names both endpoints and shows no source or destination direction

#### Scenario: Null rendering

- **WHEN** a value is null
- **THEN** JSON modes emit `null`, and table, line, and CSV modes mark it distinctly from the empty string
