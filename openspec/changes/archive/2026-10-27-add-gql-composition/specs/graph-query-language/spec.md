# Spec Delta

## MODIFIED Requirements

### Requirement: Core dialect profile

A statement SHALL be an ordered sequence of one or more linear segments separated by `NEXT`. Each
segment SHALL contain an ordered sequence of read stages, optional write clauses, and a result
clause. A read segment SHALL end with `RETURN` or `FINISH`; a write segment MAY omit the result
clause as a Cypher-compatible extension. Within one segment, every write clause SHALL follow every
read stage. `NEXT` SHALL carry the preceding `RETURN` table into the next segment; an optional
`YIELD` SHALL select and rename its columns, and without `YIELD` every preceding column SHALL remain
in scope. A non-final `RETURN` SHALL act as a projection and scope reset. Only the final segment's
`RETURN` or `FINISH` SHALL produce the statement result. A read statement SHALL contain at least one
row source and a final `RETURN` or `FINISH`; a write statement MAY end with a write clause. `FINISH`
SHALL be final. Unsupported forms SHALL be rejected, never ignored.

#### Scenario: Minimal query

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name`
- **THEN** the statement is accepted and returns one row per matching node

#### Scenario: Chained read stages

- **WHEN** a caller submits `MATCH (a:Program) WITH a MATCH (a)-[:ALLIES_WITH]->(b) RETURN b`
- **THEN** the statement is accepted and the second stage joins against the first

#### Scenario: UNWIND as a row source

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: FOR as a row source

- **WHEN** a caller submits `FOR value IN [1, 2] RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: LET as a row source

- **WHEN** a caller submits `LET value = 1 RETURN value` without a `MATCH`, `FOR`, or write clause
- **THEN** the statement is accepted and returns one row

#### Scenario: FILTER stage

- **WHEN** a caller submits `MATCH (n:Program) FILTER n.cycles > 36 RETURN n`
- **THEN** the statement is accepted and returns only rows whose predicate is true

#### Scenario: Stage WHERE alias

- **WHEN** a caller submits `MATCH (n:Program) WITH n WHERE n.cycles > 36 RETURN n`
- **THEN** the stage filters its rows exactly as the `FILTER` spelling would

#### Scenario: MERGE without MATCH

- **WHEN** a caller submits `MERGE (n:Program {designation: 'Tron'})` without a `MATCH`
- **THEN** the statement is accepted and executes as a write

#### Scenario: Unsupported pattern form

- **WHEN** a caller submits `MATCH (a)-[*]->(b) RETURN b` or `MATCH (a)-[*1..]->(b) RETURN b`
- **THEN** the system raises a semantic query error before execution because the upper bound is missing

#### Scenario: Unsupported clause

- **WHEN** a caller submits a statement using `CALL { ... }`, `EXISTS { ... }`, `CASE`, a map literal, or `WITH *`
- **THEN** the system raises a query error before execution

#### Scenario: Multiple statements

- **WHEN** a caller submits more than one statement separated by semicolons
- **THEN** the system raises a query error before execution

#### Scenario: Write-only statement

- **WHEN** a caller submits `CREATE (n:Program)` with no `MATCH` and no `RETURN`
- **THEN** the statement is accepted and executed

#### Scenario: Match with write and no RETURN

- **WHEN** a caller submits `MATCH (n:Program) SET n.cycles = 1`
- **THEN** the statement is accepted and executed

#### Scenario: RETURN before a write clause

- **WHEN** a caller submits `MATCH (n:Program) RETURN n CREATE (m:Program)`
- **THEN** the system raises a query error before execution in the same segment

#### Scenario: Write clause before MATCH

- **WHEN** a caller submits `CREATE (n:Program) WITH n MATCH (m) RETURN m`
- **THEN** the system raises a query error before execution in the same segment

#### Scenario: Later segment reads after a write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (m:Program {designation: 'Rinzler'}) RETURN m`
- **THEN** the statement is accepted, the later segment sees the created node, and one row is returned

#### Scenario: Read statement without RETURN

- **WHEN** a caller submits a read statement with matching stages but no `RETURN` or `FINISH`
- **THEN** the system raises a query error before execution

#### Scenario: Write after a WITH stage

- **WHEN** a caller submits `MATCH (a:Program) WITH a CREATE (b:Program {designation: 'Tron'}) RETURN b`
- **THEN** the statement is accepted and creates one node per row produced by the `WITH`

#### Scenario: NEXT requires a following segment

- **WHEN** a caller submits `MATCH (n:Program) NEXT`
- **THEN** the system raises a query error before execution

#### Scenario: NEXT after RETURN

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT RETURN n`
- **THEN** the statement is accepted and the final result comes from the last `RETURN`

#### Scenario: Intermediate RETURN feeds NEXT

- **WHEN** a caller submits `MATCH (n:Program) RETURN n AS element NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m`
- **THEN** the later segment matches from the returned element column

#### Scenario: YIELD selects columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name RETURN name`
- **THEN** the later segment sees `name` but not `cycles`

#### Scenario: Write-only segment passes bindings

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (n) RETURN n.designation`
- **THEN** the later segment sees the created node through the unchanged binding

#### Scenario: FINISH ends without a result

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) FINISH`
- **THEN** the node is created and the result has no rows

#### Scenario: FINISH is final

- **WHEN** a caller submits `MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m`
- **THEN** the system raises a query error before execution

#### Scenario: Read segment requires a result

- **WHEN** a caller submits `MATCH (n:Program) NEXT RETURN n`
- **THEN** the system raises a query error because the first read segment has no `RETURN` or `FINISH`

### Requirement: UNWIND clause

`FOR` SHALL expand a list-valued expression into one row per element and bind each element to a
variable. `UNWIND <expression> AS <variable>` SHALL be accepted as an alias for `FOR <variable> IN
<expression>`, including the ordinality suffix. A null value or an empty list SHALL produce no rows.
A value that is not a list SHALL raise a query error. `WITH ORDINALITY <name>` SHALL bind a
one-based position and `WITH OFFSET <name>` SHALL bind a zero-based position. The index name SHALL
be fresh and distinct from the element variable, and the two forms SHALL NOT be combined. The
element and index variables SHALL be available to later clauses, and the clause SHALL be a read
stage that precedes the result clause within its segment.

#### Scenario: Expand a parameter list

- **WHEN** a caller submits `UNWIND $names AS name RETURN name` with `["Kevin Flynn", "Quorra"]`
- **THEN** the result contains two rows in list order

#### Scenario: Canonical FOR spelling

- **WHEN** a caller submits `FOR name IN $names RETURN name` with the same parameter
- **THEN** the result is identical to the `UNWIND` alias

#### Scenario: Expand a list literal

- **WHEN** a caller submits `UNWIND [36, 37] AS cycles RETURN cycles`
- **THEN** the result contains one row for each integer

#### Scenario: Expand a list of mappings

- **WHEN** a caller unwinds a list of mappings and returns `row.designation`
- **THEN** each mapping contributes one row and its field is read as a value

#### Scenario: Empty list

- **WHEN** a caller submits `UNWIND [] AS value RETURN value`
- **THEN** the result contains no rows

#### Scenario: Null value

- **WHEN** a caller unwinds a null parameter
- **THEN** the result contains no rows

#### Scenario: Non-list literal

- **WHEN** a caller submits `UNWIND 36 AS value RETURN value`
- **THEN** the system raises a query error before execution

#### Scenario: Non-list runtime value

- **WHEN** a caller unwinds a parameter whose value is a string or mapping
- **THEN** the system raises an execution query error

#### Scenario: Variable already in scope

- **WHEN** a caller submits `MATCH (n:Program) UNWIND [1] AS n RETURN n`
- **THEN** the system raises a semantic query error before execution

#### Scenario: UNWIND after a write clause

- **WHEN** a caller submits `CREATE (n:Program) UNWIND [1] AS value RETURN value`
- **THEN** the system raises a query error before execution

#### Scenario: Ordinality is gated

- **WHEN** a caller submits `FOR value IN [1, 2] WITH ORDINALITY index RETURN index`
- **THEN** the statement is accepted and returns indexes 1 and 2

#### Scenario: Zero-based offset

- **WHEN** a caller submits `FOR value IN [1, 2] WITH OFFSET index RETURN index`
- **THEN** the statement is accepted and returns indexes 0 and 1

#### Scenario: UNWIND accepts ordinality

- **WHEN** a caller submits `UNWIND [10, 20] AS value WITH ORDINALITY index RETURN value, index`
- **THEN** the result contains `(10, 1)` and `(20, 2)`

#### Scenario: Index name must be fresh

- **WHEN** a caller submits `FOR value IN [1] WITH ORDINALITY value RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Ordinality and offset are exclusive

- **WHEN** a caller submits `FOR value IN [1] WITH ORDINALITY index WITH OFFSET other RETURN index`
- **THEN** the system raises a query error before execution

### Requirement: Projection and result columns

`RETURN` SHALL project expressions, aliases, and node, relationship, or path values. A column SHALL
take its alias when present and otherwise its expression text. `RETURN ALL` SHALL be the explicit
form of the default and `RETURN *` SHALL project every variable in scope in introduction order. As a
pygrafito extension, `RETURN NO BINDINGS` SHALL return zero columns and one empty row per input
binding, SHALL be final-only, and SHALL NOT combine with `DISTINCT`, `ALL`, `*`, `GROUP BY`, `ORDER
BY`, `OFFSET`, or `LIMIT`; GQL's canonical no-result form is `FINISH`. Duplicate column names SHALL
be rejected. `DISTINCT` SHALL remove duplicate projected rows.

#### Scenario: Scalar projection

- **WHEN** a caller returns `n.designation AS name, n.cycles`
- **THEN** the result has columns `name` and `n.cycles` in that order

#### Scenario: Entity projection

- **WHEN** a caller returns a node, relationship, or path variable
- **THEN** the result value is the corresponding immutable snapshot

#### Scenario: Return all bindings

- **WHEN** a caller matches `(a:Program)-[r:ALLIES_WITH]->(b:Program)` and returns `*`
- **THEN** the result has one column per bound variable in introduction order

#### Scenario: Explicit ALL

- **WHEN** a caller returns `ALL n.designation AS name`
- **THEN** the result is identical to the same projection without `ALL`

#### Scenario: Duplicate columns

- **WHEN** two projected items produce the same column name
- **THEN** the system raises a semantic query error

#### Scenario: Distinct projection

- **WHEN** a caller returns `DISTINCT n.designation`
- **THEN** equal projected values appear once

#### Scenario: No bindings is gated

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS`
- **THEN** the result has zero columns and one empty row per matched node

#### Scenario: No bindings with empty input

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN NO BINDINGS`
- **THEN** the result has zero columns and no rows

#### Scenario: No bindings rejects modifiers

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS ORDER BY n.designation`
- **THEN** the system raises a syntax error before execution

#### Scenario: No bindings in a write

- **WHEN** a caller submits `CREATE (n:Program) RETURN NO BINDINGS`
- **THEN** the node is created and the result has one empty row

### Requirement: Aggregation and grouping

The dialect SHALL support `count`, `collect`, `sum`, `avg`, `min`, and `max`, including `DISTINCT`
variants. A non-aggregate `RETURN` expression SHALL form an implicit grouping key when the
projection has no explicit `GROUP BY`. With an explicit `GROUP BY`, the grouping keys SHALL be
exactly the listed keys. `count(*)` SHALL count rows, while `count(expr)` SHALL count non-null
values. Empty input SHALL yield count 0, collect an empty list, sum 0, and null for avg, min, and
max when the projection is a global aggregate.

#### Scenario: Count rows

- **WHEN** a caller returns `count(*)` for a match with ten rows
- **THEN** the result is 10

#### Scenario: Grouped aggregation

- **WHEN** a caller returns `labels(n), count(*)` after matching nodes
- **THEN** one row is returned per distinct non-aggregate value

#### Scenario: Collect values

- **WHEN** a caller returns `collect(n.designation)`
- **THEN** the result is a list of non-null projected values in result order

#### Scenario: Empty aggregate input

- **WHEN** a query matches no rows and returns aggregates
- **THEN** the aggregate row contains count 0, an empty collected list, sum 0, and null for avg, min, and max

#### Scenario: Invalid aggregate use

- **WHEN** a projected expression mixes an aggregate with a non-grouped expression that is not a grouping key
- **THEN** the system raises a semantic query error

#### Scenario: Explicit grouping replaces implicit

- **WHEN** a caller returns `n.cycles, count(*) GROUP BY n.cycles`
- **THEN** one row is returned for each distinct value of `n.cycles`, even if another non-aggregate expression could have formed a different implicit key

#### Scenario: Explicit grouping without aggregates

- **WHEN** a caller returns `n.cycles GROUP BY n.cycles`
- **THEN** one row is returned per distinct value of `n.cycles`

## ADDED Requirements

### Requirement: LET clause

`LET` SHALL be a read stage that adds row-wise bindings without removing existing bindings.
Definitions SHALL evaluate left to right, so a later definition MAY reference an earlier one. A
`LET` assignment that is a direct variable reference SHALL preserve that variable's kind; any other
assignment SHALL bind a scalar. `LET` SHALL be usable as the only row source of a read statement.

#### Scenario: Add a binding

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Kevin Flynn'}) LET cycles = n.cycles + 1 RETURN cycles`
- **THEN** the result contains 37

#### Scenario: Preserve the existing scope

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) LET next = n.cycles + 1 RETURN n.designation, next`
- **THEN** the result contains both the original designation and the new binding

#### Scenario: Left-to-right definitions

- **WHEN** a caller submits `LET base = 36, following = base + 1 RETURN following`
- **THEN** the result contains 37

#### Scenario: Leading row source

- **WHEN** a caller submits `LET value = 1 RETURN value`
- **THEN** the statement is accepted and returns one row

#### Scenario: Direct variable preserves its kind

- **WHEN** a caller submits `MATCH (n:Program) LET element = n MATCH (element)-[:ALLIES_WITH]->(m) RETURN m`
- **THEN** the statement is accepted and the second pattern matches from the bound node

### Requirement: LET binding rules

A `LET` name already bound in the current scope, or repeated in the same clause, SHALL be rejected.
A `LET` expression SHALL NOT contain an aggregate. `LET` SHALL NOT be the final clause of a
statement.

#### Scenario: Shadowing is rejected

- **WHEN** a caller submits `MATCH (n:Program) LET n = 1 RETURN n`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Duplicate name is rejected

- **WHEN** a caller submits `LET value = 1, value = 2 RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Aggregate is rejected

- **WHEN** a caller submits `LET value = count(*) RETURN value`
- **THEN** the system raises a semantic query error before execution

#### Scenario: LET is not a final clause

- **WHEN** a caller submits `MATCH (n:Program) LET value = 1`
- **THEN** the system raises a query error before execution because the read segment has no `RETURN` or `FINISH`

### Requirement: NEXT composition

`NEXT` SHALL separate two linear segments. The preceding segment's `RETURN` table SHALL be the
input to the following segment. A non-final `RETURN` SHALL act as a projection and scope reset and
MAY aggregate, group, order, and paginate. A write-only segment SHALL pass its bindings unchanged
as a Cypher-compatible extension. A statement SHALL remain one transaction and one query budget.

#### Scenario: Intermediate RETURN feeds NEXT

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Kevin Flynn'}) RETURN n AS element NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m.designation AS name`
- **THEN** the result contains Quorra

#### Scenario: Mid-query grouping

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total GROUP BY n.cycles NEXT FILTER total > 1 RETURN cycles, total`
- **THEN** the later segment filters the grouped rows

#### Scenario: Write-only segment passes bindings

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Rinzler'}) NEXT MATCH (n) RETURN n.designation AS name`
- **THEN** the result contains Rinzler

#### Scenario: Later segment reads an earlier write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) NEXT MATCH (m:Program {designation: 'Clu'}) RETURN m.designation AS name`
- **THEN** the result contains Clu

#### Scenario: One transaction and budget

- **WHEN** a later segment exceeds the query budget after an earlier segment wrote
- **THEN** the whole statement rolls back and no earlier mutation remains

### Requirement: NEXT YIELD

`NEXT` MAY carry `YIELD item [AS alias] [, ...]`. Each item SHALL name a column of the preceding
result. `YIELD` SHALL keep only the yielded columns and SHALL apply the aliases; an unknown column
or duplicate output name SHALL be rejected. `YIELD` SHALL be rejected after a segment that does not
end in `RETURN`. Without `YIELD`, every preceding column SHALL remain in scope.

#### Scenario: Select columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name RETURN name`
- **THEN** the later segment sees `name` but not `cycles`

#### Scenario: Rename a column

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT YIELD name AS designation RETURN designation`
- **THEN** the later segment sees the renamed column

#### Scenario: No YIELD passes all columns

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT RETURN name, cycles`
- **THEN** the later segment sees both columns

#### Scenario: Unknown YIELD column

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT YIELD missing RETURN name`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Duplicate YIELD alias

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles NEXT YIELD name, cycles AS name RETURN name`
- **THEN** the system raises a semantic query error before execution

#### Scenario: YIELD after a write-only segment is rejected

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) NEXT YIELD n RETURN n`
- **THEN** the system raises a semantic query error before execution

### Requirement: NEXT placement and result

Each read segment SHALL end with `RETURN` or `FINISH`; a write segment MAY omit the result clause.
Only the final segment's `RETURN` or `FINISH` SHALL produce the statement result; an intermediate
`RETURN` is not the call result. `NEXT` SHALL NOT appear at the start or end of a statement or twice
in a row. `FINISH` SHALL be final, and a statement SHALL contain at most one `FINISH`.

#### Scenario: Final result is the last RETURN

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name NEXT RETURN name`
- **THEN** the statement is accepted and returns the final projected rows

#### Scenario: NEXT at the start is rejected

- **WHEN** a caller submits `NEXT MATCH (n:Program) RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: NEXT at the end is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT`
- **THEN** the system raises a query error before execution

#### Scenario: Consecutive NEXT is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN n NEXT NEXT RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: FINISH after NEXT

- **WHEN** a caller submits `MATCH (n:Program) NEXT FINISH`
- **THEN** the statement is accepted and returns no result

#### Scenario: NEXT after FINISH is rejected

- **WHEN** a caller submits `MATCH (n:Program) FINISH NEXT MATCH (m:Program) RETURN m`
- **THEN** the system raises a query error before execution

### Requirement: FINISH clause

`FINISH` SHALL end a statement without producing a result. It SHALL apply every preceding read and
write clause and SHALL return an empty result table. `FINISH` SHALL appear only in the final
segment and SHALL NOT be followed by another clause. A write statement MAY omit the result clause
instead of using `FINISH`. `FINISH` SHALL NOT be the only clause of a statement.

#### Scenario: Finish a write

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'}) FINISH`
- **THEN** the node is created and the result has no rows

#### Scenario: Finish a read

- **WHEN** a caller submits `MATCH (n:Program) FINISH`
- **THEN** the statement is accepted and the result has no rows

#### Scenario: Finish is final

- **WHEN** a caller submits `MATCH (n:Program) FINISH RETURN n`
- **THEN** the system raises a query error before execution

#### Scenario: Write-only equivalent

- **WHEN** a caller submits `CREATE (n:Program {designation: 'Clu'})` without `FINISH`
- **THEN** the statement is accepted, creates the node, and returns no result

#### Scenario: FINISH alone is rejected

- **WHEN** a caller submits `FINISH` with no row source and no write clause
- **THEN** the system raises a query error before execution

### Requirement: GROUP BY clause

`GROUP BY` SHALL be a suffix of `RETURN`. It SHALL group the input rows by the listed keys and
produce one row per distinct key combination. A non-aggregate return item SHALL be one of the
keys. A key MAY be a direct variable in scope and need not be returned. `GROUP BY` without
aggregates SHALL deduplicate the keys. `RETURN DISTINCT ... GROUP BY ...` SHALL be accepted.

#### Scenario: Explicit grouping

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles, count(*) AS total GROUP BY n.cycles ORDER BY n.cycles`
- **THEN** one row is returned per distinct cycle count with its total

#### Scenario: Key not returned

- **WHEN** a caller submits `MATCH (n:Program) RETURN count(*) AS total GROUP BY n.cycles`
- **THEN** one row is returned per distinct cycle count, with no `n.cycles` column

#### Scenario: No aggregate deduplicates

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles`
- **THEN** one row is returned per distinct cycle count

#### Scenario: Group by a LET binding

- **WHEN** a caller submits `MATCH (n:Program) LET cycles = n.cycles RETURN count(*) AS total GROUP BY cycles`
- **THEN** one row is returned per distinct cycle count

#### Scenario: DISTINCT with GROUP BY

- **WHEN** a caller submits `MATCH (n:Program) RETURN DISTINCT n.cycles GROUP BY n.cycles ORDER BY n.cycles`
- **THEN** the statement is accepted and returns one row per distinct cycle count

### Requirement: GROUP BY keys and grouping rules

GQL grouping keys are direct variable references; pygrafito additionally accepts expressions as a
labeled extension. `GROUP BY ()` SHALL group all input rows into one group and SHALL be valid only
when the projection contains at least one aggregate and no non-aggregate item. `RETURN *` and
`RETURN NO BINDINGS` SHALL NOT be combined with `GROUP BY`. Null key values SHALL form one group.
Empty input SHALL produce no groups unless `GROUP BY ()` is used.

#### Scenario: Expression key extension

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.cycles + 0 AS shifted, count(*) AS total GROUP BY n.cycles + 0`
- **THEN** the statement is accepted and groups by the expression

#### Scenario: Variable key

- **WHEN** a caller submits `MATCH (n:Program) LET cycles = n.cycles RETURN cycles, count(*) AS total GROUP BY cycles`
- **THEN** the statement is accepted and groups by the variable

#### Scenario: Empty key list

- **WHEN** a caller submits `MATCH (n:Program) RETURN count(*) AS total GROUP BY ()`
- **THEN** one row is returned with the total row count

#### Scenario: Empty key list on empty input

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN count(*) AS total GROUP BY ()`
- **THEN** the result contains one row with total 0

#### Scenario: Return star is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN * GROUP BY n.cycles`
- **THEN** the system raises a query error before execution

#### Scenario: No bindings is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN NO BINDINGS GROUP BY n.cycles`
- **THEN** the system raises a query error before execution

#### Scenario: Null keys form one group

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.missing AS missing, count(*) AS total GROUP BY n.missing`
- **THEN** all null values form one group

#### Scenario: Empty input produces no groups

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Nobody'}) RETURN n.cycles, count(*) GROUP BY n.cycles`
- **THEN** the result contains no rows

### Requirement: Deferred construct diagnostics

A construct the profile lists as deferred SHALL raise a semantic query error that names the
construct and the follow-up change that implements it. The error SHALL NOT be reported as an
unexpected token, and the statement SHALL NOT execute or partially execute. Unsupported
out-of-profile constructs SHALL keep their explicit rejection.

#### Scenario: Open-bound gate

- **WHEN** a caller uses an open-ended upper bound (`*`, `+`, `*n..`, or `{m,}`)
- **THEN** the error names the construct and `add-gql-unbounded-traversal`

#### Scenario: Statement does not execute

- **WHEN** a deferred construct appears in a statement that also contains a write clause
- **THEN** the statement changes no data

## REMOVED Requirements

### Requirement: Gated construct diagnostics

**Reason**: Every composition construct in that requirement is now supported. The only remaining
gated syntax is open-ended traversal, which has its own requirement.

**Migration**: Use `add-gql-unbounded-traversal` for open-ended quantifiers. The new `Deferred
construct diagnostics` requirement keeps the positioned-error contract for the remaining deferred
forms; `LET`, `NEXT`, `YIELD`, `FINISH`, `GROUP BY`, ordinality, and `RETURN NO BINDINGS` now
execute.
