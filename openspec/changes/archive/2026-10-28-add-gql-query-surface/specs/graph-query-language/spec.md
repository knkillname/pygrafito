# Spec Delta: graph-query-language

## MODIFIED Requirements

### Requirement: Core dialect profile

A linear statement SHALL be an ordered sequence of one or more segments separated by `NEXT`. A compound query SHALL combine two or more linear statements with a set operator. Each linear segment SHALL contain an ordered sequence of read stages, optional write clauses, and a result clause, and every write clause SHALL follow every read stage within its segment.

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

- **WHEN** a caller submits a statement using `CALL { ... }`, `exists(n.prop)`, whole-map assignment, or a regex predicate
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

### Requirement: Statement row sources and result requirements

A read segment SHALL end with `RETURN` or `FINISH`; a write segment MAY omit the result clause. A
read statement SHALL contain at least one row source and a final `RETURN` or `FINISH`; a write
statement MAY end with a write clause. Unsupported forms SHALL be rejected, never ignored.

#### Scenario: UNWIND supplies rows without MATCH

- **WHEN** a caller submits `UNWIND [1, 2] AS value RETURN value` without a `MATCH`
- **THEN** the statement is accepted and returns two rows

#### Scenario: Write-only statement needs no result

- **WHEN** a caller submits `CREATE (n:Program)` with no `MATCH` and no `RETURN`
- **THEN** the statement is accepted and executed

#### Scenario: Unsupported clause is rejected

- **WHEN** a caller submits a statement using `CALL { ... }`, `exists(n.prop)`, whole-map assignment, or a regex predicate
- **THEN** the system raises a query error before execution

### Requirement: Filtering expressions

`WHERE` SHALL accept the dialect's scalar expression surface: comparison operators, `AND`, `OR`, `NOT`, `IN`, `IS NULL`, `IS NOT NULL`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`, arithmetic, string concatenation, list and map literals, list access and comprehensions, `CASE`, path functions, scalar functions, and read-only query expressions. String predicates SHALL be case-sensitive.

#### Scenario: Numeric range

- **WHEN** a caller filters with `p.cycles >= 36 AND p.cycles < 40`
- **THEN** only nodes whose numeric property falls in that range are returned

#### Scenario: Membership

- **WHEN** a caller filters with `p.designation IN ['Quorra', 'Tron']`
- **THEN** only nodes with either exact string value are returned

#### Scenario: String predicate

- **WHEN** a caller filters with `p.designation STARTS WITH 'Qu'`
- **THEN** only values beginning with the exact case-sensitive prefix are returned

#### Scenario: Boolean precedence

- **WHEN** a caller combines `AND`, `OR`, and `NOT` in one predicate
- **THEN** `NOT` binds tighter than `AND`, and `AND` binds tighter than `OR`

#### Scenario: CASE in a filter

- **WHEN** a caller filters with `CASE WHEN n.cycles > 36 THEN true ELSE false END`
- **THEN** only rows whose `CASE` result is true are returned

#### Scenario: List comprehension in a filter

- **WHEN** a caller filters with `size([x IN n.tags WHERE x STARTS WITH 'ISO']) > 0`
- **THEN** only rows whose tags contain a matching element are returned

#### Scenario: Query expression in a filter

- **WHEN** a caller filters with `EXISTS { MATCH (n)-[:TRUSTS]->(m:Program) }`
- **THEN** only rows with at least one matching inner row are returned

### Requirement: Scalar functions

The dialect SHALL support the core functions `id`, `labels`, `type`, `properties`, `keys`, `size`, `coalesce`, `toInteger`, `toFloat`, `toString`, `lower`, `upper`, `trim`, `abs`, `concat`, `startNode`, and `endNode`, plus the extended functions in this spec. Function names SHALL be case-insensitive; `labels` and `keys` SHALL return sorted lists; `labels` SHALL accept a node or relationship; `type` SHALL return the first sorted relationship label or null.

#### Scenario: Entity metadata

- **WHEN** a caller projects `id(n)`, `labels(n)`, or `properties(n)`
- **THEN** the result contains the element id, its sorted labels, or its property mapping respectively

#### Scenario: Relationship metadata

- **WHEN** a caller projects `type(r)`, `startNode(r)`, or `endNode(r)`
- **THEN** the result contains the relationship's first sorted label, or null when it has no labels, or the corresponding node snapshot

#### Scenario: Relationship labels

- **WHEN** a caller projects `labels(r)` for a relationship carrying several labels
- **THEN** the result contains every label in sorted order

#### Scenario: Conversion

- **WHEN** a caller applies `toInteger`, `toFloat`, or `toString` to a compatible scalar
- **THEN** the converted value is returned, and an impossible conversion yields null

#### Scenario: Unknown function

- **WHEN** a caller uses a function name that is not in the supported function catalog
- **THEN** the system raises a semantic query error before execution

### Requirement: Prepared queries

`Graph.prepare` SHALL parse and validate a statement once and return a `PreparedQuery` whose `execute` method may run repeatedly with different parameters. A prepared statement MAY be a write statement. Preparation SHALL reject syntax and semantic errors before execution, and prepared columns SHALL be available before the first execution and SHALL be empty without `RETURN`. For a compound query, prepared columns SHALL be the first operand's columns.

#### Scenario: Reuse a prepared query

- **WHEN** a caller prepares a statement and executes it twice with different parameter values
- **THEN** both executions use the same parsed statement and return their respective results

#### Scenario: Preparation rejects invalid syntax

- **WHEN** a caller prepares a statement with invalid syntax
- **THEN** the system raises a syntax query error and no query executes

#### Scenario: Columns before execution

- **WHEN** a caller prepares a valid statement with `RETURN`
- **THEN** the prepared query exposes its projected column names before execution

#### Scenario: Prepared write

- **WHEN** a caller prepares `CREATE (n:Program {designation: $name})` and executes it twice
- **THEN** the prepared columns are empty and both calls create a node

#### Scenario: Compound columns

- **WHEN** a caller prepares a compound query whose first operand returns `name` and `cycles`
- **THEN** the prepared columns are `name` and `cycles` before execution

## ADDED Requirements

### Requirement: CASE expressions

The dialect SHALL support simple and searched `CASE` expressions. A simple `CASE` SHALL compare its
operand with each `WHEN` operand using dialect equality and select the first matching result. A
searched `CASE` SHALL select the first `WHEN` whose predicate is true. Null SHALL never match, a
missing `ELSE` SHALL produce null, and only the selected branch SHALL be evaluated.

#### Scenario: Simple CASE

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Quorra'}) RETURN CASE n.cycles WHEN 37 THEN 'active' ELSE 'unknown' END AS state`
- **THEN** the result contains `active`

#### Scenario: Searched CASE

- **WHEN** a caller submits `MATCH (n:Program) RETURN CASE WHEN n.cycles > 36 THEN 'veteran' ELSE 'rookie' END AS rank`
- **THEN** each row is classified by its cycle count

#### Scenario: Null does not match

- **WHEN** a caller submits `RETURN CASE null WHEN null THEN 'matched' ELSE 'other' END AS result`
- **THEN** the result is `other`

#### Scenario: Else defaults to null

- **WHEN** a caller submits `RETURN CASE WHEN false THEN 1 END AS result`
- **THEN** the result is null

#### Scenario: Only the selected branch is evaluated

- **WHEN** a caller submits `RETURN CASE WHEN true THEN 1 ELSE 1 / 0 END AS result`
- **THEN** the result is 1 and no division error is raised

### Requirement: Map literals

The dialect SHALL support map literals of the form `{key: expression, ...}`. Keys SHALL be static
identifiers or backtick-quoted names; duplicate keys SHALL be rejected, and values SHALL be
evaluated left to right. A map literal SHALL produce an immutable mapping usable in projections,
list literals, and function arguments. Maps SHALL compare by key set and dialect equality, and
SHALL NOT be orderable.

#### Scenario: Project a map

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) RETURN {designation: n.designation, cycles: n.cycles} AS program`
- **THEN** the result contains a mapping with both fields

#### Scenario: Empty map

- **WHEN** a caller submits `RETURN {} AS empty`
- **THEN** the result contains an empty mapping

#### Scenario: Duplicate key is rejected

- **WHEN** a caller submits `RETURN {designation: 'Tron', designation: 'Clu'} AS program`
- **THEN** the system raises a semantic query error before execution

#### Scenario: Map equality

- **WHEN** a caller submits `RETURN {designation: 'Tron'} = {designation: 'Tron'} AS same`
- **THEN** the result is true

#### Scenario: Map in a list

- **WHEN** a caller submits `RETURN [{designation: 'Tron'}, {designation: 'Clu'}] AS programs`
- **THEN** the result contains a list of two mappings

#### Scenario: Map is not orderable

- **WHEN** a caller submits `UNWIND [{designation: 'Tron'}] AS row RETURN row ORDER BY row`
- **THEN** the system raises a query execution error

#### Scenario: Map property is rejected

- **WHEN** a caller submits `INSERT (n:Program {metadata: {role: 'system'}})`
- **THEN** the system raises a query execution error and creates no node

### Requirement: List indexing and slicing

The dialect SHALL support zero-based list indexing `list[index]` and slicing `list[start:end]` with
either bound optional. A negative index SHALL count from the end, an out-of-range index SHALL
produce null, and a slice SHALL be end-exclusive and clamp to the list bounds. A null list SHALL
produce null, and a non-list target SHALL raise a query error.

#### Scenario: First and last element

- **WHEN** a caller submits `RETURN [36, 37, 38][0] AS first, [36, 37, 38][-1] AS last`
- **THEN** the first value is 36 and the last value is 38

#### Scenario: Out-of-range index

- **WHEN** a caller submits `RETURN [36, 37][5] AS missing`
- **THEN** the result is null

#### Scenario: Slice with both bounds

- **WHEN** a caller submits `RETURN [36, 37, 38][1:3] AS middle`
- **THEN** the result is `[37, 38]`

#### Scenario: Open slice bounds

- **WHEN** a caller submits `RETURN [36, 37, 38][:2] AS first_two, [36, 37, 38][1:] AS last_two`
- **THEN** the first list is `[36, 37]` and the second is `[37, 38]`

#### Scenario: Slice clamps to the list

- **WHEN** a caller submits `RETURN [36, 37][-5:5] AS values`
- **THEN** the result is `[36, 37]`

#### Scenario: Null list

- **WHEN** a caller submits `RETURN null[0] AS value`
- **THEN** the result is null

#### Scenario: Non-list index target

- **WHEN** a caller submits `RETURN 36[0] AS value`
- **THEN** the system raises a query error before execution

### Requirement: List comprehensions

The dialect SHALL support list comprehensions of the form `[variable IN list [WHERE predicate] [| expression]]`.
The list SHALL be evaluated once, the variable SHALL be local and SHALL NOT shadow an enclosing
variable, and only elements whose predicate is true SHALL be emitted. Without a projection the
element SHALL be emitted; with a projection the expression SHALL be evaluated for each emitted
element. A null list SHALL produce null, and a non-list SHALL raise a query error.

#### Scenario: Transform each element

- **WHEN** a caller submits `RETURN [x IN [36, 37] | x + 1] AS cycles`
- **THEN** the result is `[37, 38]`

#### Scenario: Filter elements

- **WHEN** a caller submits `RETURN [x IN [36, 37, 38] WHERE x > 36] AS cycles`
- **THEN** the result is `[37, 38]`

#### Scenario: Filter and transform

- **WHEN** a caller submits `RETURN [x IN [36, 37, 38] WHERE x > 36 | x * 2] AS cycles`
- **THEN** the result is `[74, 76]`

#### Scenario: Comprehension variable is local

- **WHEN** a caller submits `MATCH (n:Program {designation: 'Tron'}) RETURN [x IN [1, 2] | x] AS values, n.designation AS name`
- **THEN** the result contains `[1, 2]` and `Tron`

#### Scenario: Null comprehension list

- **WHEN** a caller submits `RETURN [x IN null | x] AS values`
- **THEN** the result is null

#### Scenario: Non-list comprehension source

- **WHEN** a caller submits `RETURN [x IN 36 | x] AS values`
- **THEN** the system raises a query error before execution

#### Scenario: Comprehension shadowing is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN [n IN [1, 2] | n] AS values`
- **THEN** the system raises a semantic query error before execution

### Requirement: String concatenation

The dialect SHALL support string concatenation with `||`. Both operands SHALL be strings, null SHALL
propagate, and a non-string operand SHALL raise a query error. `+` SHALL remain numeric addition,
except that it SHALL also concatenate when both operands are strings; mixed string and numeric
operands SHALL raise a query error.

#### Scenario: Canonical concatenation

- **WHEN** a caller submits `RETURN 'Kevin' || ' ' || 'Flynn' AS name`
- **THEN** the result is `Kevin Flynn`

#### Scenario: Null propagates

- **WHEN** a caller submits `RETURN 'Tron' || null AS name`
- **THEN** the result is null

#### Scenario: Non-string operand

- **WHEN** a caller submits `RETURN 'Tron' || 1 AS name`
- **THEN** the system raises a query error

#### Scenario: String plus alias

- **WHEN** a caller submits `RETURN 'Quorra' + ' ' + 'ISO' AS name`
- **THEN** the result is `Quorra ISO`

#### Scenario: Numeric plus remains arithmetic

- **WHEN** a caller submits `RETURN 36 + 1 AS cycles`
- **THEN** the result is 37

#### Scenario: Mixed plus is rejected

- **WHEN** a caller submits `RETURN 'Tron' + 1 AS value`
- **THEN** the system raises a query error

### Requirement: Path functions

The dialect SHALL support `nodes(path)`, `relationships(path)`, and `length(path)`. `nodes` SHALL
return the path's node snapshots in traversal order, `relationships` SHALL return its relationship
snapshots in traversal order, and `length` SHALL return the number of relationships. A null path
SHALL produce null, and a non-path argument SHALL raise a query error.

#### Scenario: Nodes in traversal order

- **WHEN** a caller submits `MATCH p = (a:Program {designation: 'Kevin Flynn'})-[:TRUSTS]->(b:Program) RETURN [n IN nodes(p) | n.designation] AS names`
- **THEN** `names` starts with `Kevin Flynn` and has one entry per path node

#### Scenario: Relationships in traversal order

- **WHEN** a caller submits `MATCH p = (a:Program)-[:TRUSTS]->(b:Program) RETURN [r IN relationships(p) | type(r)] AS types`
- **THEN** `types` has one entry per traversed relationship

#### Scenario: Path length

- **WHEN** a caller submits `MATCH p = (a:Program)-[:TRUSTS]->(b:Program) RETURN length(p) AS hops`
- **THEN** every row returns 1

#### Scenario: Null path

- **WHEN** a caller submits `OPTIONAL MATCH p = (a:Program {designation: 'Nobody'})-[:TRUSTS]->(b) RETURN length(p) AS hops`
- **THEN** the result is null

#### Scenario: Non-path argument

- **WHEN** a caller submits `MATCH (n:Program) RETURN nodes(n) AS nodes`
- **THEN** the system raises a semantic query error before execution

### Requirement: List construction functions

The dialect SHALL support `range` and `reverse`. `range(start, end [, step])` SHALL produce an
inclusive integer list; `step` SHALL default to 1 and SHALL NOT be zero. A step whose direction does
not reach the opposite bound SHALL produce an empty list. `reverse` SHALL return a list with its
elements in reverse order. Null arguments SHALL produce null, and wrong types or a zero step SHALL
raise a query error.

#### Scenario: Inclusive range

- **WHEN** a caller submits `RETURN range(36, 38) AS cycles`
- **THEN** the result is `[36, 37, 38]`

#### Scenario: Range with a step

- **WHEN** a caller submits `RETURN range(36, 40, 2) AS cycles`
- **THEN** the result is `[36, 38, 40]`

#### Scenario: Descending range

- **WHEN** a caller submits `RETURN range(40, 36, -2) AS cycles`
- **THEN** the result is `[40, 38, 36]`

#### Scenario: Empty range direction

- **WHEN** a caller submits `RETURN range(36, 40, -1) AS cycles`
- **THEN** the result is `[]`

#### Scenario: Reverse a list

- **WHEN** a caller submits `RETURN reverse([36, 37, 38]) AS cycles`
- **THEN** the result is `[38, 37, 36]`

#### Scenario: Null range argument

- **WHEN** a caller submits `RETURN range(36, null) AS cycles`
- **THEN** the result is null

#### Scenario: Zero range step

- **WHEN** a caller submits `RETURN range(36, 38, 0) AS cycles`
- **THEN** the system raises a query error

#### Scenario: Wrong range type

- **WHEN** a caller submits `RETURN range('36', 38) AS cycles`
- **THEN** the system raises a query error

### Requirement: List element functions

The dialect SHALL support `head`, `last`, and `tail`. `head` SHALL return the first element, `last`
the last element, and `tail` all but the first element. `head` and `last` SHALL return null for an
empty list, and `tail` SHALL return an empty list. Null arguments SHALL produce null, and a non-list
argument SHALL raise a query error.

#### Scenario: Head and last

- **WHEN** a caller submits `RETURN head([36, 37, 38]) AS first, last([36, 37, 38]) AS final`
- **THEN** the first value is 36 and the final value is 38

#### Scenario: Tail

- **WHEN** a caller submits `RETURN tail([36, 37, 38]) AS rest`
- **THEN** the result is `[37, 38]`

#### Scenario: Empty list

- **WHEN** a caller submits `RETURN head([]) AS first, last([]) AS final, tail([]) AS rest`
- **THEN** the first two values are null and the third is `[]`

#### Scenario: Null list argument

- **WHEN** a caller submits `RETURN head(null) AS first`
- **THEN** the result is null

#### Scenario: Non-list argument

- **WHEN** a caller submits `RETURN tail(36) AS rest`
- **THEN** the system raises a query error

### Requirement: String scalar functions

The dialect SHALL support `split`, `substring`, and `replace`. `split(string, delimiter)` SHALL
split on every non-empty delimiter and retain empty segments. `substring(string, start [, length])`
SHALL use a zero-based start and an optional non-negative length. `replace(string, search,
replacement)` SHALL replace every non-empty search occurrence. Null arguments SHALL produce null,
and invalid delimiters, negative positions, or wrong types SHALL raise a query error.

#### Scenario: Split a string

- **WHEN** a caller submits `RETURN split('Kevin Flynn|Quorra', '|') AS names`
- **THEN** the result is `['Kevin Flynn', 'Quorra']`

#### Scenario: Substring to the end

- **WHEN** a caller submits `RETURN substring('Kevin Flynn', 6) AS surname`
- **THEN** the result is `Flynn`

#### Scenario: Substring with a length

- **WHEN** a caller submits `RETURN substring('Quorra', 1, 3) AS value`
- **THEN** the result is `uor`

#### Scenario: Replace every occurrence

- **WHEN** a caller submits `RETURN replace('Tron|Clu|Tron', 'Tron', 'Rinzler') AS value`
- **THEN** the result is `Rinzler|Clu|Rinzler`

#### Scenario: Null string argument

- **WHEN** a caller submits `RETURN split(null, '|') AS values`
- **THEN** the result is null

#### Scenario: Empty delimiter

- **WHEN** a caller submits `RETURN split('Tron', '') AS values`
- **THEN** the system raises a query error

#### Scenario: Negative substring start

- **WHEN** a caller submits `RETURN substring('Tron', -1) AS value`
- **THEN** the system raises a query error

#### Scenario: Wrong string function type

- **WHEN** a caller submits `RETURN replace(36, '3', '4') AS value`
- **THEN** the system raises a query error

### Requirement: Numeric and boolean scalar functions

The dialect SHALL support `toBoolean`, `round`, `ceil`, and `floor`. `toBoolean` SHALL convert
booleans, the strings `true` and `false` case-insensitively, and the numbers 0 and 1; other inputs
SHALL produce null. `round(number [, precision])` SHALL round to the nearest value with ties away
from zero, using a non-negative precision. `ceil` and `floor` SHALL return integers. Null arguments
SHALL produce null, and wrong types or negative precision SHALL raise a query error.

#### Scenario: Convert a boolean string

- **WHEN** a caller submits `RETURN toBoolean('TRUE') AS value`
- **THEN** the result is true

#### Scenario: Convert a numeric boolean

- **WHEN** a caller submits `RETURN toBoolean(0) AS value`
- **THEN** the result is false

#### Scenario: Invalid boolean input

- **WHEN** a caller submits `RETURN toBoolean('maybe') AS value`
- **THEN** the result is null

#### Scenario: Round a number

- **WHEN** a caller submits `RETURN round(36.5) AS value`
- **THEN** the result is 37

#### Scenario: Round with precision

- **WHEN** a caller submits `RETURN round(36.346, 2) AS value`
- **THEN** the result is 36.35

#### Scenario: Ceiling and floor

- **WHEN** a caller submits `RETURN ceil(36.1) AS up, floor(36.9) AS down`
- **THEN** the result is 37 and 36

#### Scenario: Null numeric argument

- **WHEN** a caller submits `RETURN round(null) AS value`
- **THEN** the result is null

#### Scenario: Negative precision

- **WHEN** a caller submits `RETURN round(36.5, -1) AS value`
- **THEN** the system raises a query error

### Requirement: WITH * projection

`WITH *` SHALL project every variable in the current scope in introduction order, preserving each
variable's kind and snapshot. It SHALL be the only projection item in the clause, MAY carry
`DISTINCT`, `WHERE`, `ORDER BY`, `OFFSET`, or `LIMIT`, and SHALL NOT be the final clause of a
statement. A `WITH *` that would duplicate a name SHALL be rejected.

#### Scenario: Preserve the full scope

- **WHEN** a caller submits `MATCH (a:Program)-[r:ALLIES_WITH]->(b:Program) WITH * RETURN a.designation, b.designation`
- **THEN** both nodes and the relationship remain visible

#### Scenario: Keep variable kinds

- **WHEN** a caller submits `MATCH (a:Program) WITH * RETURN labels(a) AS labels`
- **THEN** `a` is still a node binding

#### Scenario: Distinct scope

- **WHEN** a caller submits `MATCH (n:Program) WITH DISTINCT * RETURN count(*) AS total`
- **THEN** duplicate complete bindings are removed before the count

#### Scenario: Filter and paginate the scope

- **WHEN** a caller submits `MATCH (n:Program) WITH * WHERE n.cycles > 36 ORDER BY n.cycles LIMIT 2 RETURN n`
- **THEN** the filter, ordering, and limit apply to the preserved scope

#### Scenario: Mixing star with items is rejected

- **WHEN** a caller submits `MATCH (n:Program) WITH *, n.cycles AS cycles RETURN n`
- **THEN** the system raises a syntax error before execution

#### Scenario: WITH * cannot end a statement

- **WHEN** a statement ends with `WITH *` and has no following clause
- **THEN** the system raises a query error

### Requirement: Query expression subqueries

The dialect SHALL support read-only `EXISTS { ... }` and `COUNT { ... }` query expressions. The
braces SHALL contain a read-only sequence of query stages with at least one row source and no final
result clause. `EXISTS` SHALL return true when the inner query produces at least one row and false
otherwise; `COUNT` SHALL return the number of inner rows. Both SHALL be usable in scalar expression
positions in read stages, projections, `LET`, grouping keys, and ordering.

#### Scenario: Correlated EXISTS

- **WHEN** a caller submits `MATCH (n:Program) WHERE EXISTS { MATCH (n)-[:TRUSTS]->(m:Program) } RETURN n.designation AS name`
- **THEN** only programs with at least one outgoing `TRUSTS` relationship are returned

#### Scenario: Uncorrelated EXISTS

- **WHEN** a caller submits `MATCH (n:Program) WHERE EXISTS { MATCH (m:Program {designation: 'Tron'}) } RETURN n.designation AS name`
- **THEN** every program is returned when the inner graph has Tron

#### Scenario: Correlated COUNT

- **WHEN** a caller submits `MATCH (n:Program) RETURN n.designation AS name, COUNT { MATCH (n)-[:TRUSTS]->(m:Program) } AS trusts`
- **THEN** `trusts` is the number of matching inner rows for each program

#### Scenario: Uncorrelated COUNT

- **WHEN** a caller submits `MATCH (n:Program) RETURN COUNT { MATCH (m:Program) } AS programs`
- **THEN** every row has the same total program count

#### Scenario: No inner match

- **WHEN** a caller evaluates `EXISTS` or `COUNT` for an inner query that matches no rows
- **THEN** the result is false or 0 respectively

#### Scenario: Inner query needs a row source

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { RETURN 1 } AS found`
- **THEN** the system raises a query error before execution

#### Scenario: Write inside a subquery is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { INSERT (m:Program) } AS found`
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Result clause inside a subquery is rejected

- **WHEN** a caller submits `MATCH (n:Program) RETURN EXISTS { MATCH (m:Program) RETURN m } AS found`
- **THEN** the system raises a query error before execution

### Requirement: Subquery scope and correlation

An outer variable referenced inside a subquery SHALL refer to the outer binding. A name introduced
inside the subquery SHALL be local and SHALL NOT leak to the outer scope. A subquery that introduces
a name already bound by `LET` or `WITH` in the same inner scope SHALL be rejected. An uncorrelated
subquery SHALL evaluate independently of the current row; a correlated subquery SHALL evaluate
against the current row.

#### Scenario: Outer variable is visible

- **WHEN** a subquery matches from an outer `n` binding
- **THEN** the inner pattern uses the outer node rather than a new node

#### Scenario: Inner variable is local

- **WHEN** a caller references an inner `m` binding after the subquery
- **THEN** the system raises a semantic query error for the unbound variable

#### Scenario: Shadowing is rejected

- **WHEN** a subquery defines a `LET m = ...` when `m` is already an inner binding
- **THEN** the system raises a semantic query error

#### Scenario: Correlated result varies by row

- **WHEN** a caller evaluates a correlated `COUNT` for several outer rows
- **THEN** each row can return a different count

#### Scenario: Uncorrelated result is constant

- **WHEN** a caller evaluates an uncorrelated `EXISTS` for several outer rows
- **THEN** every row receives the same boolean result

### Requirement: Subquery budget and snapshot

A subquery SHALL share the enclosing statement's query budget, transaction, and consistent
snapshot. Relationship expansions and intermediate rows inside a subquery SHALL count against the
same budget. A budget failure SHALL raise the same query execution error and SHALL NOT produce a
partial result, and a subquery SHALL NOT start a transaction.

#### Scenario: Subquery expansions use the budget

- **WHEN** a subquery expands relationships beyond the enclosing expansion limit
- **THEN** the system raises a query execution error naming the expansion limit

#### Scenario: Subquery rows use the budget

- **WHEN** a subquery produces more intermediate rows than the enclosing row limit
- **THEN** the system raises a query execution error naming the row limit

#### Scenario: No partial result

- **WHEN** a subquery exceeds the budget after producing some rows
- **THEN** the statement raises and returns no rows

#### Scenario: Shared snapshot

- **WHEN** a statement with a subquery runs while another connection changes a row
- **THEN** the outer query and subquery observe the same execution snapshot

### Requirement: Set operations

The dialect SHALL support compound queries built from two or more read-only linear statements with
`UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT`. Operators SHALL be left-associative and SHALL
combine the final `RETURN` tables of their operands. `UNION ALL` SHALL preserve duplicates; the
other forms SHALL use set semantics and remove duplicate rows. A compound query SHALL NOT contain a
write, `FINISH`, or `RETURN NO BINDINGS`.

#### Scenario: UNION ALL preserves rows

- **WHEN** a caller combines two program queries with `UNION ALL`
- **THEN** every row from both operands appears, including duplicates

#### Scenario: UNION removes duplicates

- **WHEN** a caller combines two queries with `UNION`
- **THEN** each distinct row appears once

#### Scenario: INTERSECT keeps common rows

- **WHEN** a caller combines two queries with `INTERSECT`
- **THEN** only rows present in both operands are returned

#### Scenario: EXCEPT removes the second operand

- **WHEN** a caller combines two queries with `EXCEPT`
- **THEN** rows present only in the first operand are returned

#### Scenario: Operators are left-associative

- **WHEN** a caller writes three operands without grouping
- **THEN** the left pair is combined first

#### Scenario: Write operand is rejected

- **WHEN** a caller combines a `CREATE` statement with a read query
- **THEN** the system raises a semantic query error and changes nothing

#### Scenario: Result-less forms are rejected

- **WHEN** a caller uses `FINISH` or `RETURN NO BINDINGS` as a set operand
- **THEN** the system raises a query error before execution

### Requirement: Set operation columns

Every operand of a set operation SHALL produce the same number of columns in the same order with the
same names. The first operand SHALL define the result column names. A mismatch SHALL raise a
semantic query error before execution. Column values SHALL use the dialect's value model; no
implicit type coercion SHALL occur, and duplicate detection SHALL use dialect equality.

#### Scenario: Column count mismatch

- **WHEN** one operand returns one column and another returns two
- **THEN** the system raises a semantic query error

#### Scenario: Column name mismatch

- **WHEN** operands return the same number of columns with different names
- **THEN** the system raises a semantic query error

#### Scenario: First operand names the result

- **WHEN** the first operand returns `name` and the second returns the same column under the same name
- **THEN** the result columns are `name`

#### Scenario: Heterogeneous values are not coerced

- **WHEN** the same column contains an integer in one operand and a string in another
- **THEN** both values remain in the result without coercion

#### Scenario: Numeric duplicates use dialect equality

- **WHEN** one operand returns the integer 36 and another returns the float 36.0
- **THEN** `UNION` treats them as the same value

### Requirement: Set operation ordering and pagination

`ORDER BY`, `OFFSET`, and `LIMIT` after a compound query SHALL apply to the combined result.
Compound ordering keys SHALL be output column names from the first operand. Ordering and pagination
clauses inside an operand's final `RETURN` SHALL be rejected; intermediate `RETURN` clauses in a
`NEXT` segment MAY still carry them.

#### Scenario: Order the combined result

- **WHEN** a caller writes `UNION` followed by `ORDER BY name`
- **THEN** the combined rows are sorted by the output `name` column

#### Scenario: Paginate the combined result

- **WHEN** a caller writes `UNION` followed by `OFFSET` and `LIMIT`
- **THEN** pagination applies after duplicate removal and ordering

#### Scenario: Operand ordering is rejected

- **WHEN** an operand's final `RETURN` carries `ORDER BY`, `OFFSET`, or `LIMIT`
- **THEN** the system raises a syntax error before execution

#### Scenario: Sort expression must be a column

- **WHEN** a compound query orders by an expression that is not an output column
- **THEN** the system raises a semantic query error

#### Scenario: Null ordering is preserved

- **WHEN** a compound query orders an output column with `NULLS FIRST` or `NULLS LAST`
- **THEN** null placement follows the requested rule

### Requirement: Set operation execution

A compound query SHALL execute all operands in one transaction and one snapshot under one budget.
Each operand SHALL be read-only and evaluated in source order; a budget failure SHALL raise and
return no partial result. The result SHALL expose the first operand's columns and a zero mutation
summary.

#### Scenario: One snapshot

- **WHEN** a compound query runs while another connection changes a row between operands
- **THEN** every operand observes the state at execution start

#### Scenario: Shared budget

- **WHEN** the combined operands exceed the row or expansion budget
- **THEN** the system raises a query execution error naming the counter

#### Scenario: Zero mutation summary

- **WHEN** a compound query succeeds
- **THEN** every mutation count in its summary is zero

#### Scenario: No partial rows on failure

- **WHEN** a later operand exceeds the budget
- **THEN** the call raises and returns no rows
