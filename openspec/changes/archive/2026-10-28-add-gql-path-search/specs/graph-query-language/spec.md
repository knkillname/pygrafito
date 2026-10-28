# Spec Delta: graph-query-language

## MODIFIED Requirements

### Requirement: Pattern match row semantics

`MATCH` SHALL produce one row per distinct match of the pattern, unless a path pattern carries a
path-search prefix, in which case it SHALL produce only the paths that prefix selects. Parallel
relationships, self-loops, diamonds, and cycles SHALL produce the matches implied by the graph, and
duplicate projected rows SHALL be removed only when `DISTINCT` is requested.

#### Scenario: Diamond produces two rows

- **WHEN** two distinct two-hop routes connect the start node to the same end node and both are matched
- **THEN** two rows are returned

#### Scenario: Parallel relationships are distinct

- **WHEN** two separate relationships of the same type connect the same pair of nodes
- **THEN** the pattern produces one row per relationship

#### Scenario: Self-loop

- **WHEN** a relationship starts and ends at the same node and the pattern matches it
- **THEN** the self-loop produces a binding

#### Scenario: Distinct removes duplicate rows

- **WHEN** the projected values of two matched rows are equal and `DISTINCT` is requested
- **THEN** only one of those rows is returned

#### Scenario: Path search reduces rows

- **WHEN** a path pattern carries a path-search prefix and matches several paths for one endpoint pair
- **THEN** only the selected paths become rows

## ADDED Requirements

### Requirement: Path search syntax

A path pattern MAY carry at most one path-search prefix: `ANY`, `ANY SHORTEST`, `ALL SHORTEST`,
or `SHORTEST k`. The prefix SHALL follow the optional path variable and precede any path mode.
`k` SHALL be a non-negative integer literal; parameters and expressions SHALL be rejected. A
path variable SHALL bind the selected path.

#### Scenario: Path variable binds the selection

- **WHEN** a caller writes `MATCH p = ANY SHORTEST (a)-[:TRUSTS]->(b) RETURN p`
- **THEN** `p` is the selected path

#### Scenario: Non-literal k is rejected

- **WHEN** a caller writes `SHORTEST $k` or `SHORTEST 1 + 1`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Negative k is rejected

- **WHEN** a caller writes `SHORTEST -1`
- **THEN** the system raises a query error before execution

### Requirement: Path search selection

Path search SHALL partition matches by the path's first and last node within each input row. It
SHALL select `ANY` one path, `ANY SHORTEST` one minimum-length path, `ALL SHORTEST` every
minimum-length path, and `SHORTEST k` up to `k` paths in increasing length. `k = 0` SHALL select
no path.

#### Scenario: Any selects one path per pair

- **WHEN** two distinct routes connect the same endpoint pair and the pattern uses `ANY`
- **THEN** one row is produced for that pair

#### Scenario: Any shortest selects a minimum path

- **WHEN** routes of length two and three connect the same endpoint pair and the pattern uses
  `ANY SHORTEST`
- **THEN** the selected path has length two

#### Scenario: All shortest selects every minimum path

- **WHEN** two two-hop routes and one three-hop route connect the same endpoint pair and the
  pattern uses `ALL SHORTEST`
- **THEN** two rows are produced

#### Scenario: Shortest k returns increasing lengths

- **WHEN** a pattern uses `SHORTEST 2` and the partition has paths of length two and three
- **THEN** both selected paths are returned, shortest first

#### Scenario: Zero k selects nothing

- **WHEN** a path pattern uses `SHORTEST 0`
- **THEN** the pattern produces no rows

#### Scenario: Unreachable pair is absent

- **WHEN** no path connects a candidate endpoint pair
- **THEN** the partition produces no row

### Requirement: Path identity and ordering

Two paths SHALL be identical when their node and orientation-aware relationship sequences match;
parallel relationships SHALL be distinct paths. `ALL SHORTEST` SHALL return distinct paths. Ties
SHALL break by the lexicographically smaller relationship sequence, then node sequence. Rows SHALL
be ordered by partition and selection order unless the statement has an `ORDER BY`.

#### Scenario: Parallel relationships are distinct paths

- **WHEN** two parallel relationships connect the same nodes and the pattern uses `ALL SHORTEST`
- **THEN** both paths are returned

#### Scenario: Duplicate path is not repeated

- **WHEN** the same node and relationship sequence would be produced twice by the evaluator
- **THEN** only one row is produced

#### Scenario: Tie-break is deterministic

- **WHEN** two shortest paths have the same length and different relationship identifiers
- **THEN** the same path is selected on every run and on every storage plan

#### Scenario: Output order is stable

- **WHEN** two partitions produce selected paths and the statement has no `ORDER BY`
- **THEN** rows appear in ascending start and end node identifier order

### Requirement: Path search mode interaction

Path search SHALL evaluate only paths accepted by the effective path mode and match mode. A
`DIFFERENT EDGES` clause SHALL apply its edge rule before selection. Path search SHALL apply to
whole paths only.

#### Scenario: Different edges narrows the search

- **WHEN** a `DIFFERENT EDGES` clause and a path-search prefix produce an edge-sharing candidate
- **THEN** that candidate is not selected

#### Scenario: Path mode applies before selection

- **WHEN** a `TRAIL` path and an `ALL SHORTEST` prefix find an edge-reusing candidate
- **THEN** that candidate is not selected

### Requirement: Path search termination and budget

Path search SHALL evaluate in nondecreasing length order and SHALL stop a partition once its
selection is complete. `ANY SHORTEST` and `ALL SHORTEST` SHALL stop at the shortest layer.
`SHORTEST k` SHALL stop at its k-th path. Search SHALL terminate for open `WALK` patterns by
pruning states that cannot improve a selection. A final `LIMIT` MAY stop the search. Every
expansion SHALL count against the budget, and a budget failure SHALL raise with no partial result.

#### Scenario: Any shortest does not enumerate longer paths

- **WHEN** `ANY SHORTEST` finds a path at length two for a partition with longer routes
- **THEN** it does not enumerate the longer routes

#### Scenario: Shortest k stops at k

- **WHEN** `SHORTEST 2` finds two paths for a partition and more paths exist
- **THEN** it stops expanding that partition

#### Scenario: Open walk search terminates

- **WHEN** `ANY SHORTEST` or `ALL SHORTEST` runs over an open `WALK` pattern on a cyclic graph
- **THEN** the query completes with the shortest paths

#### Scenario: Limit stops the search

- **WHEN** a path-search query has a final `LIMIT` and enough partitions are discovered
- **THEN** expansion stops when the limit is satisfied

#### Scenario: Budget failure returns nothing

- **WHEN** a path-search query exceeds the expansion budget
- **THEN** the call raises `QueryBudgetExceededError` and returns no rows
