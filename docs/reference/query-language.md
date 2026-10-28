# Query language reference

:::{note}
This page describes the dialect the current release executes. GQL spellings are canonical; the
compatibility aliases in the [GQL profile](gql-profile.md) are accepted with identical semantics.
Open-ended traversal is the only remaining gated construct; see [Gated constructs](#gated-constructs).
:::

This page is the complete reference for the `pygrafito` query dialect: grammar, pattern
semantics, write clauses, value and null rules, functions, aggregation, ordering, parameters,
and errors. For a task-first introduction, start with [Query your graph](../guides/querying.md).

`pygrafito` includes a pattern-matching query dialect for reading and writing a
property graph. A statement describes a fixed-length path pattern, filters the
matches, mutates them, and projects values into a materialized result. The
dialect is intentionally small: it rejects unsupported syntax instead of
ignoring it, and runs through indexed SQL joins over the existing property-graph
schema.

## Statement execution

One call executes exactly one statement and returns a materialized
`QueryResult`:

```python
from pygrafito import Graph

with Graph.open(":memory:") as graph:
    graph.add_node("Program", designation="Quorra")
    result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
    print(result.columns)  # ('name',)
    print([row["name"] for row in result])  # ['Quorra']
```

`Graph.prepare` parses, validates, and plans once, then returns a reusable
`PreparedQuery`. A statement that contains any write clause is classified as a
write and runs in its own transaction.

## Core dialect profile

A statement is one or more linear segments separated by `NEXT`:

```text
statement        = segment { "NEXT" [ "YIELD" yield-item { "," yield-item } ] segment } [;]
segment          = { [OPTIONAL] MATCH <path pattern> [, ...] [WHERE <expression>]
                   | FOR <identifier> IN <expression> [ordinality]
                   | UNWIND <expression> AS <identifier> [ordinality]
                   | FILTER [WHERE] <expression>
                   | WITH [DISTINCT] <projection> [WHERE <expression>]
                   | LET <identifier> "=" <expression> { "," <identifier> "=" <expression> } }
                 [ {INSERT | CREATE | MERGE | SET | REMOVE | DELETE | DETACH DELETE
                    | NODETACH DELETE} ... ]
                 [ RETURN ... [GROUP BY ...] [ORDER BY ...] [OFFSET|SKIP ...] [LIMIT ...]
                 | RETURN "*"
                 | FINISH ]
ordinality       = "WITH" ( "ORDINALITY" | "OFFSET" ) <identifier>
group-by         = "GROUP" "BY" ( "(" ")" | <expression> { "," <expression> } )
yield-item       = <identifier> [ "AS" <identifier> ]
```

A `MATCH` clause carries one or more comma-separated path patterns and an
optional `WHERE`; `OPTIONAL MATCH` uses the same shape with left-join semantics.
A statement may contain several `MATCH` clauses: each clause is a stage joined
against the rows produced by the previous one. `FOR` (with `UNWIND` as its
alias) is another read stage and a row source, and `FILTER` (with a stage-level
`WHERE` as its alias) keeps only rows whose predicate is true. `LET` is a
row-wise read stage that adds bindings without dropping the current scope.
`MATCH`, `FOR`, and `LET` are row sources; `MATCH` and `FOR` are optional when
the statement contains a write clause.

Within one segment, every read stage precedes every write clause, `RETURN` or
`FINISH` is last, and a segment contains at most one result clause. A read
segment must end with `RETURN` or `FINISH`; a write segment may omit the result
clause. `NEXT` starts a new segment from the preceding `RETURN` table. An
optional `YIELD` selects and renames the columns that pass; without `YIELD`,
every preceding column remains in scope. A non-final `RETURN` is a projection
and scope reset, so it can aggregate, group, order, and paginate. Only the final
segment's `RETURN` or `FINISH` produces the call result, and `FINISH` is always
final. A read statement requires at least one row source and a final result
clause. Multiple statements are rejected.

## FOR

`FOR` expands a list-valued expression into one row per element. `UNWIND
<expression> AS <variable>` is accepted as the compatibility alias:

```text
FOR row IN $rows ...
FOR cycles IN [36, 37, 40] ...
```

A null value or an empty list produces no rows. A value that is not a list is a
query error. The bound variable is available to later stages and write clauses,
and `FOR` may serve as the only row source of a read statement:

```python
graph.query(
    "FOR row IN $rows MERGE (n:Program {designation: row.designation})",
    {"rows": [{"designation": "Tron"}, {"designation": "Quorra"}]},
)
graph.query("FOR value IN [1, 2, 3] RETURN value")
```

A row can be a mapping, so `row.designation` reads a field from the current row.
`WITH ORDINALITY index` binds a one-based position and `WITH OFFSET index` binds
a zero-based position. The suffix is accepted after both `FOR ... IN ...` and
`UNWIND ... AS ...`:

```text
FOR value IN [10, 20] WITH ORDINALITY index RETURN value, index  -- (10, 1), (20, 2)
FOR value IN [10, 20] WITH OFFSET index RETURN value, index      -- (10, 0), (20, 1)
UNWIND ['Tron', 'Quorra'] AS name WITH ORDINALITY position RETURN name, position
```

The index name must be fresh, must differ from the element variable, and the
two suffix forms cannot be combined.

## FILTER

`FILTER` keeps only the rows whose boolean predicate is true. `FILTER WHERE` is
the explicit spelling, and a `WHERE` attached to a `WITH` stage is its alias:

```text
MATCH (n:Program) FILTER n.cycles > 36 RETURN n
MATCH (n:Program) WITH n WHERE n.cycles > 36 RETURN n
```

A filter never introduces a binding. `MATCH ... WHERE` stays part of the match
stage: it filters matches before a later stage sees them, and an
`OPTIONAL MATCH ... WHERE` filters that optional match rather than the input
rows.

## Pattern property expressions

A pattern property map may evaluate an expression against the current row and
the statement parameters. This is how a row drives a match or a merge:

```text
MATCH (n:Program {designation: row.designation}) ...
CREATE (n:Program {designation: row.designation}) ...
MERGE (n:Program {designation: row.designation}) ...
```

A referenced variable must be in scope before the pattern starts, so a pattern
cannot reference a variable it introduces itself. Aggregates are rejected. A
null value matches nothing in `MATCH`, is omitted from the created properties in
`CREATE`, and raises a query error in `MERGE`.


## Node patterns

A node pattern binds an optional variable, zero or more labels, and an optional
property map:

```text
(n)
(:Program)
(p:Program&ISO)
(p:Program|Agent)
(p:Program&!ISO)
(p:%)
(p IS Program&ISO)
(p:Program {designation: 'Quorra', cycles: 36})
(n:Program WHERE n.cycles > 36)
```

Labels form an expression: `&` is conjunction, `|` disjunction, `!` negation,
and `%` the wildcard. `IS` is accepted as the explicit form in place of `:`.
`:A:B` remains a conjunction alias. Property map entries compare stored values
with the dialect's equality rules, and an inline `WHERE` predicate is scoped to
that element. An anonymous node still participates in path matching but is not
bound to a variable.

Property keys may contain dots, spaces, and other punctuation when written in
backticks:

```text
MATCH (n {`a.b`: 1}) RETURN n
MATCH (n) WHERE n.`a b` = 2 RETURN n
```

## Relationship patterns

Relationship patterns bind an optional variable, zero or more labels, a
direction, and an optional property map:

```text
(a)-[r:ALLIES_WITH]->(b)          directed, forward
(a)<-[r:ALLIES_WITH]-(b)          directed, reverse
(a)-[r:ALLIES_WITH]-(b)           any incident relationship
(a)~[r:ALLIES_WITH]~(b)           undirected relationship only
(a)-[r:ALLIES_WITH|TRUSTS]->(b)   label disjunction
(a)-[r {since_cycle: 2020}]->(b)  property filter
(a)->(b)                          anonymous directed relationship
(a)-(b)                           anonymous, any direction
(a)-[:ALLIES_WITH*1..3]->(b)      legacy quantifier, bounded
(a)-[r:TRUSTS WHERE r.since_cycle > 2010]->(b)  inline predicate
```

A bound relationship snapshot preserves its endpoints, labels, and directed
flag even when the pattern traverses it against its stored direction. A
relationship label expression supports the same operators as a node label
expression. `-->` and `<--` are accepted as aliases for `->` and `<-`.

The arrows are storage-direction constraints. Each form admits a different set of stored
relationships:

| Form | Admits |
| --- | --- |
| `-[r]->` | A directed relationship stored from the left node to the right node. |
| `-[r]-` | Every incident relationship, directed or undirected. |
| `<-[r]-` | A directed relationship stored from the right node to the left node. |
| `~[r]~` | Only a relationship stored as undirected. |
| `<-[r]->` | A directed relationship in either stored direction; never an undirected one. |
| `<-[r]~` | A directed relationship stored from the right node to the left node, or an undirected one. |
| `~[r]->` | A directed relationship stored from the left node to the right node, or an undirected one. |

```text
MATCH (a)-[r:TRUSTS]->(b) RETURN b        forward only
MATCH (a)-[r:TRUSTS]-(b) RETURN b         every incident relationship
MATCH (a)<-[r:TRUSTS]-(b) RETURN b        backward only
MATCH (a)~[r:TRUSTS]~(b) RETURN b         undirected only
MATCH (a)<-[r:TRUSTS]->(b) RETURN b       either directed direction
MATCH (a)<-[r:TRUSTS]~(b) RETURN b        backward or undirected
MATCH (a)~[r:TRUSTS]->(b) RETURN b        forward or undirected
```

`-->` and `<--` are accepted as aliases for `->` and `<-`. `--` is a line comment, not an arrow;
see [Comments](#comments).

## Variable-length relationships

A relationship may carry a quantifier after its labels:

```text
(a)-[:ALLIES_WITH*2]->(b)          exactly two hops
(a)-[:ALLIES_WITH*1..3]->(b)       between one and three hops
(a)-[:ALLIES_WITH*0..2]->(b)       zero through two hops
(a)-[*1..2]->(b)                   anonymous, any label
```

Every hop applies the pattern's direction, label alternatives, and property
map. An arrow quantified pattern cannot follow an undirected relationship; use
the `-` form to include undirected relationships in a quantified path. Bounds
are non-negative integers and the lower bound cannot exceed the upper bound.

The canonical closed forms are `{n}` for exactly `n` hops, `{m,n}` for a range,
and `{,n}` for at most `n` hops:

```text
(a)-[:ALLIES_WITH{2}]->(b)         exactly two hops
(a)-[:ALLIES_WITH{1,3}]->(b)       between one and three hops
(a)-[:ALLIES_WITH{,2}]->(b)        zero through two hops
```

The canonical form does not imply `TRAIL`: its mode comes from the
[path-mode rule](#path-modes), so a canonical path without an explicit mode is a
`WALK`. The legacy `*n..m` form keeps its `TRAIL` default. An open-ended upper
bound is deferred: `*`, `+`, `*n..`, and `{m,}` raise a positioned error naming
`add-gql-unbounded-traversal`.

`TRAIL` is relationship-unique: one match never uses the same relationship
twice, while nodes may repeat. That is the same rule the Python `paths()` API
uses; `WALK` removes it. A relationship variable on a quantified pattern binds
the ordered list of traversed relationships, and a path variable includes every
expanded relationship:

```text
MATCH (a)-[r:ALLIES_WITH*1..3]->(b) RETURN r, size(r)
MATCH p = (a)-[:ALLIES_WITH*1..2]->(b) RETURN p
```

A relationship-list variable may be projected or passed to `size`; it cannot be
used where a single relationship is required, so `type(r)` and `r.property` are
semantic errors. Pattern property maps may contain expressions; see
[Pattern property expressions](#pattern-property-expressions).

## Path modes

A match clause or an individual path may name how that path may repeat:

```text
MATCH WALK (a)-[:ALLIES_WITH*1..3]->(b)         nodes and relationships may repeat
MATCH TRAIL (a)-[:ALLIES_WITH*1..3]->(b)        no relationship repeats
MATCH SIMPLE (a)-[:ALLIES_WITH*1..3]->(b)       no node repeats, start may equal end
MATCH ACYCLIC (a)-[:ALLIES_WITH*1..3]->(b)      no node repeats
MATCH WALK (a)-[:TRUSTS]->(b), ACYCLIC (b)-[:TRUSTS]->(c)
```

| Mode | Rule |
| --- | --- |
| `WALK` | A node and a relationship may repeat within one path. |
| `TRAIL` | A relationship may not repeat; a node may. |
| `SIMPLE` | A node may not repeat, except that the start and end node may be the same. |
| `ACYCLIC` | No node may repeat, including the start and end node. |

The effective mode of a path is resolved in this order: an explicit per-path mode, an explicit
clause mode, `TRAIL` when the path contains a legacy `*n..m` quantifier, and `WALK` otherwise. An
explicit mode wins over both defaults, and a path that mixes a legacy and a canonical quantifier
without an explicit mode is a semantic error.

A closed path is the difference between `SIMPLE` and `ACYCLIC`: `SIMPLE` allows the last node to
equal the first, while `ACYCLIC` does not.

```text
MATCH SIMPLE (a)-[:TRUSTS]->(b)-[:TRUSTS]->(c)-[:TRUSTS]->(a) RETURN a
MATCH ACYCLIC (a)-[:TRUSTS]->(b)-[:TRUSTS]->(c)-[:TRUSTS]->(a) RETURN a   -- no rows
```

Reusing a relationship is the difference between `WALK` and `TRAIL`. On a graph with a self-loop,
the two positions may bind the same edge under `WALK` and must bind distinct edges under `TRAIL`.

```text
MATCH WALK (a)-[r:TRUSTS]->(b)-[s:TRUSTS]->(c) RETURN c
MATCH TRAIL (a)-[r:TRUSTS]->(b)-[s:TRUSTS]->(c) RETURN c   -- r and s differ
```

## Pattern variables and paths

A variable used more than once in a pattern refers to the same node or
relationship. For example, `(a)-[r]->(a)` only matches self-loops.

A path variable exposes the matched path:

```text
MATCH p = (a)-[r]->(b) RETURN p
```

The `Path` value contains nodes ordered from the path start to the path end and
relationships in traversal order. For an incoming relationship, nodes still run
from the start of the pattern to its end:

```text
MATCH p = (q)<-[:ALLIES_WITH]-(k) RETURN p
```

## Multiple patterns and match stages

A comma-separated pattern list in one `MATCH` is evaluated as one stage. A
variable shared by two patterns refers to the same element, so the patterns join
on it. Patterns that share no variable produce the cartesian product of their
matches.

```text
MATCH (a:Program)-[:ALLIES_WITH]->(b), (b)-[:ALLIES_WITH]->(c) RETURN c
MATCH (a:Program), (b:System) RETURN a, b
```

Several `MATCH` clauses are several stages. Each clause joins against the rows
the previous clause produced, so a later clause can constrain a variable bound
earlier and introduce new ones:

```text
MATCH (a:Program) MATCH (a)-[:TRUSTS]->(b) RETURN b
```

A row with no match in a later stage is removed. A path variable may be bound
only once, and a variable always keeps one kind: a node cannot later become a
relationship.

## OPTIONAL MATCH

`OPTIONAL MATCH` is a left join. A pattern that matches produces one row per
match; a pattern that matches nothing keeps the input row with the variables the
stage introduces bound to `null`. Variables bound before the stage keep their
values.

```text
MATCH (a:Program) OPTIONAL MATCH (a)-[:TRUSTS]->(b) RETURN a, b
```

The `WHERE` attached to an `OPTIONAL MATCH` is part of the optional stage, so it
filters matches rather than input rows. A null property compares as null, and a
null never satisfies a filter, so a later stage either drops the row or sees
`null` in its projection. A statement may start with `OPTIONAL MATCH`; when
nothing matches it returns one null row.

## LET

`LET` adds row-wise bindings without dropping the current scope. Definitions
evaluate left to right, so a later definition may reference an earlier one. A
direct variable assignment keeps that variable's kind; any other expression
binds a scalar. `LET` can lead a statement and counts as a row source.

```text
LET base = 36, following = base + 1 RETURN following
MATCH (n:Program {designation: 'Kevin Flynn'})
LET next_cycle = n.cycles + 1
RETURN n.designation AS name, next_cycle
MATCH (n:Program) LET element = n MATCH (element)-[:TRUSTS]->(m) RETURN m
```

A `LET` name must be fresh: shadowing an existing variable or repeating a name
in the same clause is a semantic error. Aggregates are not allowed in a `LET`
expression, and `LET` cannot be the final clause of a statement.

## WITH

`WITH` ends a read stage and projects its rows into a new scope. Only the names
it projects remain visible to later stages; a projected variable keeps its kind,
and a non-variable expression requires an alias. Duplicate output names are
rejected.

```text
MATCH (a:Program)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends RETURN a, friends
MATCH (n:Program) WITH n.designation AS name WHERE name STARTS WITH 'Q' RETURN name
```

A `WITH` stage supports `DISTINCT`, `FILTER` (with `WHERE` as its alias),
`ORDER BY`, `OFFSET` (with `SKIP` as its alias), and `LIMIT`, and
its aggregate aliases are ordinary names downstream. This is how a grouped result
is filtered, ordered, or paginated:

```text
MATCH (a)-[:ALLIES_WITH]->(b) WITH a, count(*) AS friends
WHERE friends > 2 RETURN a
```

`WHERE` after `WITH` sees only the projected scope. A `MATCH` may follow a
`WITH`, and a write clause may follow one too. A statement cannot end with
`WITH`: it must be followed by another read stage, a write clause, or `RETURN`.

`WITH` remains a pygrafito extension. The canonical composition form is `LET`
plus `RETURN`/`NEXT` plus `GROUP BY`.

## NEXT and YIELD

`NEXT` starts a new linear segment from the preceding `RETURN` table. A read
segment must end with `RETURN` (or `FINISH` as the statement's final segment);
a write-only segment passes its bindings unchanged, which is the
Cypher-compatible form. Only the final segment produces the result.

`YIELD` after `NEXT` selects and renames columns from the preceding result. An
unknown column or duplicate output name is rejected. Without `YIELD`, every
preceding column remains in scope:

```text
MATCH (n:Program) RETURN n.designation AS name, n.cycles AS cycles
NEXT YIELD name RETURN name

MATCH (n:Program) RETURN n AS element
NEXT MATCH (element)-[:TRUSTS]->(m) RETURN m.designation AS name

MATCH (n:Program) RETURN n.cycles AS cycles, count(*) AS total
GROUP BY n.cycles
NEXT FILTER total > 1 RETURN cycles, total

CREATE (n:Program {designation: 'Rinzler'})
NEXT MATCH (n) RETURN n.designation AS name
```

A non-final `RETURN` is a projection and scope reset: it may aggregate, group,
order, and paginate, so mid-query grouping does not require `WITH`. `NEXT` cannot
start or end a statement, cannot repeat, and cannot follow `FINISH`. `YIELD`
cannot appear outside `NEXT` or after a segment that does not end in `RETURN`.

The whole statement is one transaction and one query budget; a failure in a
later segment rolls back the earlier writes.

## FINISH

`FINISH` ends a statement without producing a result. It applies every preceding
read and write clause and returns an empty result with the mutation summary.
`FINISH` is final: it cannot be followed by another clause or `NEXT`, and it
cannot be the only clause of a statement.

```text
CREATE (n:Program {designation: 'Clu'}) FINISH
MATCH (n:Program) FINISH
MATCH (n:Program) NEXT FINISH
```

A write statement may also omit the result clause; `CREATE (n:Program)` has the
same no-result shape as `CREATE (n:Program) FINISH`. `FINISH` is the canonical
no-result form; `RETURN NO BINDINGS` is a separate zero-column extension.

## Pattern match row semantics

`MATCH` produces one row per distinct match of the pattern. Parallel
relationships produce one row per relationship, self-loops produce a binding,
and diamonds and cycles produce the matches implied by the graph. Duplicate
projected rows remain until `DISTINCT` is requested.

Undirected relationships are expanded from each endpoint, but an undirected
self-loop is produced once for that node rather than twice.

## Write clauses

A write clause operates on the rows produced by `MATCH` or `UNWIND`, or on a
single empty row when the statement has no row source. Write clauses run in
source order, and each one observes the mutations of the clauses before it.

### INSERT

`INSERT` creates nodes and relationships from one pattern. `CREATE` is the
compatibility alias for a data pattern:

```python
graph.query(
    "MATCH (a:Program {designation: 'Kevin Flynn'})-[x:ALLIES_WITH]->(b) "
    "INSERT (a)-[r:TRUSTS {since_cycle: 2020}]->(b)"
)
graph.query("INSERT (n:Program {designation: 'Quorra', cycles: 37})")
# An unlabeled relationship:
graph.query(
    "MATCH (a:Program {designation: 'Kevin Flynn'}), "
    "(b:Program {designation: 'Quorra'}) INSERT (a)-[r]->(b)"
)
```

An `INSERT` pattern creates new elements. A node pattern whose variable is not
yet bound creates a node; a node pattern whose variable is already bound refers
to that node. A created relationship needs at most one label, the `->`
direction, and both endpoints already bound. An unlabeled relationship is
created when the pattern names no label. `CREATE GRAPH` and `INSERT GRAPH` are
out of profile.

`INSERT` never matches an existing element. Property values in a create pattern
may be expressions evaluated against the current row, and a null entry is
ignored.

### MERGE

`MERGE` matches one fixed-length path pattern as a whole, and creates every
unbound element when the pattern does not match:

```python
graph.query(
    "UNWIND $rows AS row "
    "MERGE (n:Program {designation: row.designation}) "
    "ON CREATE SET n.cycles = row.cycles "
    "ON MATCH SET n.cycles = n.cycles + 1",
    {"rows": [{"designation": "Tron", "cycles": 40}]},
)
```

The clause runs once per input row, in order, so a creation made by one row is
visible to later rows in the same statement. A pattern that matches several
existing rows produces several result rows and creates nothing. A pattern that
does not match as a whole creates its unbound elements and reuses only variables
bound by earlier clauses; it does not partially reuse an equivalent node for an
unbound position. Repeating a variable in the pattern creates one element, so
`MERGE (a:Program {designation: 'Rinzler'})-[:MONITORS]->(a)` creates a
self-loop.

`ON CREATE SET` applies only to rows the clause created, and `ON MATCH SET` only
to rows it matched. Each may appear at most once, and `ON CREATE` must come
first. Assignments follow `SET` rules.

A merged pattern must contain one path, one explicit label and the `-->` direction
for every relationship, no path variable, and no quantified relationship. It
cannot rebind a relationship variable. A null property value in a merged pattern
is a query error.

### SET and REMOVE

`SET` assigns a property from an expression, adds labels, or both. `REMOVE`
removes a property or labels:

```python
graph.query("MATCH (n:Program) SET n.cycles = n.cycles + 1, n:SystemMonitor")
graph.query("MATCH ()-[r:ALLIES_WITH]->() SET r:TRUSTS")
graph.query("MATCH (n:Program) REMOVE n.cycles, n:ISO")
```

Assigning null removes the property. Labels can be added to or removed from
nodes and relationships. Removing a property or label that is absent leaves the
element unchanged.

### DELETE and DETACH DELETE

`DELETE` removes relationships and disconnected nodes. A node that still has an
incident relationship is rejected unless `DETACH DELETE` is used, which removes
its incident relationships first. `NODETACH DELETE` is the explicit
non-detaching form and behaves exactly as `DELETE`:

```python
graph.query("MATCH (a)-[r:TRUSTS]->(b) DELETE r")
graph.query("MATCH (n:Program {designation: 'Tron'}) DETACH DELETE n")
graph.query("MATCH (n:Program {designation: 'Quorra'}) NODETACH DELETE n")
```

A `RETURN` clause can still project an element deleted by the same statement.

### Mutation cardinality

Write clauses operate on rows, not entities. When several rows bind the same
element, the element is written or deleted once per statement. Property
assignments keep the value computed from the last row, labels are unioned, and
deletions are deduplicated. This keeps a diamond or a cycle from writing the
same element twice or raising a missing-element error on the second row.

## Value equality and comparison

Query values are wider than stored property values:

```text
null | bool | int | float | str | list | map | Node | Relationship | Path
```

- Integers and floats form one numeric family for equality and ordering.
- Booleans are not numbers: `true` never equals `1`.
- Strings compare by Unicode code point and are case-sensitive.
- Lists compare element-wise with order significant.
- Maps and entity snapshots compare by content or identity as appropriate.
- Comparison propagates null.

This differs from `find_nodes` and `find_relationships`, which are exact-match
storage filters and preserve the stored property type. For example, a stored
integer `36` matches a query predicate comparing against `36.0`, while the
object API's exact-match filter does not treat them as the same stored value.
The dialect is a value model; the object API is a storage filter.

## Null semantics

A missing property evaluates to null. Comparisons, arithmetic, string
predicates, and `IN` propagate null. `IS NULL` and `IS NOT NULL` always return a
boolean. `WHERE` keeps only rows whose predicate is true; false and null are
both discarded.

| Expression | Result |
| --- | --- |
| `missing = 1` | null |
| `missing <> 1` | null |
| `missing IS NULL` | true |
| `missing IS NOT NULL` | false |
| `true AND null` | null |
| `false AND null` | false |
| `true OR null` | true |
| `null IN [1, 2]` | null |

Aggregates also skip null inputs: `count(expr)`, `sum`, `avg`, `min`, `max`, and
`collect` ignore nulls, while `count(*)` counts rows.

## Filtering expressions

`WHERE` supports comparisons (`=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`), `AND`,
`OR`, `NOT`, `IN`, `IS NULL`, `IS NOT NULL`, `STARTS WITH`, `ENDS WITH`,
`CONTAINS`, arithmetic, list literals, parameters, and parentheses.

Precedence, tightest first:

1. Property access and function calls
2. Unary `-` and unary `+`
3. `*`, `/`, `%`
4. `+`, `-`
5. `=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`, `IN`, `IS NULL`, `IS NOT NULL`,
   `STARTS WITH`, `ENDS WITH`, `CONTAINS`
6. `NOT`
7. `AND`
8. `OR`

String predicates are case-sensitive. `STARTS WITH ''`, `ENDS WITH ''`, and
`CONTAINS ''` follow ordinary string semantics.

## Scalar functions

Function names are case-insensitive.

| Function | Behavior |
| --- | --- |
| `id(x)` | id of a node or relationship |
| `labels(x)` | sorted labels of a node or relationship |
| `type(r)` | first sorted label of a relationship, or null when it has none |
| `properties(x)` | property mapping of a node or relationship |
| `keys(x)` | sorted property keys of a node or relationship |
| `size(x)` | length of a list or string |
| `coalesce(a, b, ...)` | first non-null argument |
| `toInteger(x)` | integer conversion, or null when impossible |
| `toFloat(x)` | finite float conversion, or null when impossible |
| `toString(x)` | string conversion, or null when impossible |
| `lower(s)` | lowercase string |
| `upper(s)` | uppercase string |
| `trim(s)` | trim surrounding whitespace |
| `abs(n)` | absolute value |
| `concat(a, b, ...)` | concatenate strings |
| `startNode(r)` | node snapshot where a relationship starts |
| `endNode(r)` | node snapshot where a relationship ends |

Unknown functions and statically invalid argument kinds raise a semantic
error. Null arguments propagate to null for the metadata and string functions.

## Arithmetic

`+`, `-`, `*`, `/`, `%`, and unary minus operate on numeric values. Mixed
integer and float arithmetic promotes to float. Division always returns a
float. Division by zero and signed 64-bit integer overflow raise a query
execution error rather than returning a coerced value.

## Projection and result columns

`RETURN` projects expressions, aliases, and node, relationship, or path values.
A column takes its alias when present and otherwise its source expression text.
`RETURN ALL` is the explicit default, and `RETURN *` projects every variable in
scope in introduction order:

```text
RETURN n.designation AS name, n.cycles
RETURN ALL n.designation AS name
RETURN *
```

produces columns `name` and `n.cycles` in that order. Duplicate column names
raise a semantic error. `DISTINCT` removes duplicate projected rows and applies
after projection and before ordering.

As a pygrafito extension, `RETURN NO BINDINGS` returns zero columns and one
empty row per input binding. It is final-only and does not accept `DISTINCT`,
`ALL`, `*`, `GROUP BY`, `ORDER BY`, `OFFSET`, `SKIP`, or `LIMIT`:

```python
result = graph.query("MATCH (n:Program) RETURN NO BINDINGS")
print(result.columns)  # ()
print(len(result.rows))  # one per matched node
```

Use `FINISH` when no result is wanted; `RETURN NO BINDINGS` is useful when the
row cardinality itself is the observable value.

Entity projections return immutable snapshots. A later write does not change a
value obtained from an earlier result.

## Aggregation and grouping

Supported aggregates are `count`, `collect`, `sum`, `avg`, `min`, and `max`,
including `DISTINCT` variants. Non-aggregate `RETURN` expressions form implicit
grouping keys when there is no explicit `GROUP BY`:

```text
MATCH (n:Program) RETURN labels(n) AS labels, count(*) AS total
```

`GROUP BY` is a suffix of `RETURN`. It groups by the listed keys and produces one
row per distinct key combination. A non-aggregate return item must be one of the
keys; a key may be a direct in-scope variable and need not be returned. `GROUP
BY` without aggregates deduplicates the keys. `RETURN DISTINCT ... GROUP BY ...`
is accepted; `DISTINCT` applies after grouping. `RETURN *` and `RETURN NO
BINDINGS` cannot be combined with `GROUP BY`.

```text
MATCH (n:Program)
RETURN n.cycles AS cycles, count(*) AS total
GROUP BY n.cycles ORDER BY cycles

MATCH (n:Program) RETURN count(*) AS total GROUP BY n.cycles
MATCH (n:Program) RETURN n.cycles GROUP BY n.cycles
MATCH (n:Program) RETURN count(*) AS total GROUP BY ()
```

GQL grouping keys are direct variable references. pygrafito additionally accepts
expressions as a labeled extension, for example `GROUP BY n.cycles + 0`.
`GROUP BY ()` groups every input row into one group and requires at least one
aggregate and no non-aggregate return item. Null keys form one group. Empty input
produces no groups unless `GROUP BY ()` is used.

`count(*)` counts input rows; `count(expr)` counts non-null values. `collect`
preserves input order. Empty input yields:

- `count(*)` and `count(expr)`: `0`
- `collect`: `[]`
- `sum`: `0`
- `avg`, `min`, `max`: `null`

With grouping keys, empty input produces no rows. Nested aggregates, aggregates
in `WHERE`, and a non-grouped expression mixed with an aggregate raise a
semantic error.

## Ordering and pagination

`ORDER BY` accepts projected expressions, projected aliases, or expressions
that can be evaluated from the match binding. Each key may be followed by `ASC`
(the default) or `DESC`, and by `NULLS FIRST` or `NULLS LAST`. Earlier keys are
more significant.

By default, nulls sort last in ascending order and first in descending order.
An explicit `NULLS FIRST` or `NULLS LAST` overrides that placement without
changing the value order. Other values order by type family: booleans, numbers,
strings, then lists. Entity and map values are not orderable and raise an
execution error if used as a sort key.

`OFFSET` (with `SKIP` as its alias) and `LIMIT` accept non-negative integers or
parameters. Negative, non-integer, and boolean values are rejected before SQL
runs.

```text
MATCH (n:Program) RETURN n.designation ORDER BY n.cycles DESC OFFSET 2 LIMIT 5
MATCH (n:Program) RETURN n.designation ORDER BY n.rank ASC NULLS FIRST
```

## Parameters and injection safety

`$name` parameters are supplied as a mapping to `Graph.query`,
`PreparedQuery.execute`, or `Transaction.query`. Parameter values are bound as
data and never interpolated into SQL text or used as identifiers. Extra
parameters are ignored; a referenced parameter that is missing raises a
semantic error.

```python
graph.query(
    "MATCH (n:Program) WHERE n.designation = $name RETURN n",
    {"name": "Quorra' OR 1=1 --"},
)
```

The parameter value is matched literally.

## Result model

`QueryResult` exposes ordered `columns` and iterates immutable `Row` mappings. A
row supports lookup by column name and the usual mapping operations:

```python
result = graph.query("MATCH (n:Program) RETURN n.designation AS name")
row = result.rows[0]
print(result.columns)  # ('name',)
print(row["name"])
print(dict(row))
```

Row order without `ORDER BY` is unspecified. Result values may be null,
booleans, integers, floats, strings, lists, maps, or entity and path snapshots.

Every result also exposes a `MutationSummary` with counts of the operations the
statement applied:

```python
result = graph.query("MATCH (n:Program {designation: 'Quorra'}) SET n.cycles = 38")
print(result.summary.properties_set)  # 1
```

A read statement reports zero counts. A write statement without `RETURN` has no
columns and no rows, and its summary is the whole result.

## Prepared queries

`Graph.prepare` returns a `PreparedQuery` that parses and validates the
statement once. Its `columns` are available before the first execution, and
`execute` may run repeatedly with different parameters:

```python
prepared = graph.prepare(
    "MATCH (n:Program) WHERE n.cycles > $minimum "
    "RETURN n.designation AS name ORDER BY name"
)
print(prepared.columns)  # ('name',)
names = [row["name"] for row in prepared.execute({"minimum": 36})]
```

A prepared statement may be a write. Its `columns` are empty when it has no
`RETURN`:

```python
prepared = graph.prepare("CREATE (n:Program {designation: $name})")
print(prepared.columns)  # ()
prepared.execute({"name": "Quorra"})
```

Syntax and semantic errors are raised during preparation, before any statement
executes.

## Transaction and lifecycle integration

A standalone write statement runs in its own `BEGIN IMMEDIATE` transaction: every
mutation commits together, and any failure rolls all of them back and leaves no
transaction open. A read statement uses a deferred read transaction instead.

`Transaction.query` runs read and write statements on the active transaction's
connection and observes its uncommitted writes without starting or finishing a
transaction. A write statement there runs inside a savepoint, so a failure undoes
only that statement and leaves the transaction usable. `Graph.query` and
`PreparedQuery.execute` raise `TransactionError` while an explicit transaction is
active; use `Transaction.query` inside that block. `Graph.prepare` is allowed
during a transaction because it performs no database work.

Using a closed graph handle for `Graph.query`, `Graph.prepare`, or
`PreparedQuery.execute` raises `GraphClosedError`.

## Query errors and positions

`QuerySyntaxError`, `QuerySemanticError`, and `QueryExecutionError` all derive
from `QueryError` and `PygrafitoError`. Syntax and semantic errors expose
one-based `line` and `column` attributes when a source position is available.
Raw SQLite exceptions do not escape: execution failures are raised as
`QueryExecutionError`.

Write failures follow the same rule. A storage failure such as a protected
deletion, a missing element, or an invalid stored value is raised as
`QueryExecutionError` rather than as a storage or domain exception.

A construct that the GQL profile lists but this release cannot execute is
rejected with a positioned `QuerySemanticError` that names the construct and the
follow-up change. An open-ended upper bound (`*`, `+`, `*n..`, or `{m,}`)
reports `add-gql-unbounded-traversal`. A gated construct stops the whole
statement before execution, so a gated clause never writes data. Constructs the
profile does not list remain out of profile and keep their existing explicit
rejection.

## Consistent execution snapshot

A statement evaluates against one consistent graph state. `Graph.query` and
`PreparedQuery.execute` materialize the projected rows and close their
transaction before returning. Later writes do not change an already returned
result.

Within a write statement, each clause observes the mutations of the clauses
before it, so `SET ... RETURN ...` projects the new value and `CREATE ... RETURN`
projects the created element. A `RETURN` after `DELETE` projects the snapshot
captured before deletion. A write executed through an active transaction
includes that transaction's uncommitted writes and excludes writes from other
connections.

A statement with `NEXT` segments is still one transaction and one query budget.
A later segment sees the writes of an earlier segment, and a failure in any
segment rolls back every mutation of the statement.

## Identifier casing and quoting

Keywords and function names are case-insensitive. Variable names, labels, and
property keys are case-sensitive, so `Program` and `program` are different
labels. `LET`, `NEXT`, `YIELD`, `GROUP`, `ORDINALITY`, and `FINISH` are reserved
keywords; quote a name with backticks when it collides with one, as in
```text
LET `next` = 1 RETURN `next`
```

Backtick-quoted identifiers may contain spaces, dots, and escaped backticks
(written as doubled backticks) in labels, property keys, and variables.

## Grammar summary

```text
statement        = segment { "NEXT" [ "YIELD" yield-item { "," yield-item } ] segment } [";"]
segment          = { match-clause | for-clause | unwind-clause | filter-clause
                 | with-clause | let-clause | insert-clause | create-clause
                 | merge-clause | set-clause | remove-clause | delete-clause }
                 [ return-clause | finish-clause ]
yield-item       = identifier [ "AS" identifier ]
path-mode        = "WALK" | "TRAIL" | "SIMPLE" | "ACYCLIC"
match-clause     = [ "OPTIONAL" ] "MATCH" [path-mode] [path-mode] path-pattern
                   { "," [path-mode] path-pattern } [where-clause]
for-clause       = "FOR" identifier "IN" expression [ordinality]
unwind-clause    = "UNWIND" expression "AS" identifier [ordinality]
ordinality       = "WITH" ( "ORDINALITY" | "OFFSET" ) identifier
filter-clause    = "FILTER" [ "WHERE" ] expression
with-clause      = "WITH" [ "DISTINCT" ] return-item { "," return-item }
                   [where-clause] [order-clause] [offset-clause] [limit-clause]
let-clause       = "LET" assignment { "," assignment }
assignment       = identifier "=" expression
insert-clause    = "INSERT" path-pattern
create-clause    = "CREATE" path-pattern
merge-clause     = "MERGE" path-pattern [on-create] [on-match]
on-create        = "ON" "CREATE" "SET" set-item { "," set-item }
on-match         = "ON" "MATCH" "SET" set-item { "," set-item }
set-clause       = "SET" set-item { "," set-item }
set-item         = identifier "." key "=" expression
                 | identifier { ":" label }
remove-clause    = "REMOVE" remove-item { "," remove-item }
remove-item      = identifier "." key
                 | identifier { ":" label }
delete-clause    = [ "DETACH" | "NODETACH" ] "DELETE" identifier { "," identifier }
return-clause    = "RETURN" [ "ALL" | "DISTINCT" ] return-item { "," return-item }
                   [group-by] [order-clause] [offset-clause] [limit-clause]
                 | "RETURN" "*" [order-clause] [offset-clause] [limit-clause]
                 | "RETURN" "NO" "BINDINGS"
group-by         = "GROUP" "BY" ( "(" ")" | expression { "," expression } )
finish-clause    = "FINISH"
path-pattern     = [identifier "="] node-pattern
                   { relationship-pattern node-pattern }
node-pattern     = "(" [identifier] [label-spec] [property-map] [where-clause] ")"
label-spec       = ( ":" | "IS" ) label-or
label-or         = label-and { "|" label-and }
label-and        = label-not { ( "&" | ":" ) label-not }
label-not        = [ "!" ] ( label | "%" )
relationship     = "-" [relationship-detail] ( "->" | "-" )
                 | "<-" [relationship-detail] ( "-" | "->" | "~" )
                 | "~" [relationship-detail] ( "~" | "->" )
                 | "->" | "<-" | "-" | "~" | "<~" | "~>" | "<->"
relationship-detail = "[" [identifier] [label-spec] [quantifier]
                   [property-map] [where-clause] "]"
quantifier       = "*" [ INTEGER [ ".." [ INTEGER ] ] ]
                 | "{" INTEGER [ "," [ INTEGER ] ] "}"
property-map     = "{" [ key ":" expression { "," key ":" expression } ] "}"
where-clause     = "WHERE" expression
return-item      = expression [ "AS" identifier ]
order-clause     = "ORDER" "BY" sort-item { "," sort-item }
sort-item        = expression [ "ASC" | "DESC" | "ASCENDING" | "DESCENDING" ]
                   [ "NULLS" ( "FIRST" | "LAST" ) ]
offset-clause    = ( "OFFSET" | "SKIP" ) expression
limit-clause     = "LIMIT" expression
```

An identifier is a plain name or a backtick-quoted name. A label, key, or alias
may be backtick-quoted. Keywords are reserved, but a keyword used where a name
is expected — an alias, a label, or a property key — is read as that name. A
write segment may omit `MATCH` and `RETURN`, `RETURN` or `FINISH` ends its
segment, and only the final segment produces the result. `FINISH` is always
final. Expression precedence is listed in
[Filtering expressions](#filtering-expressions).

## Comments

The dialect accepts `//` line comments, `/* ... */` block comments, and `--`
line comments. `-->` and `<--` are arrows and are never read as comments. A `--`
that immediately follows a node or relationship pattern is a syntax error, so
`MATCH (a)--(b)` can never be silently truncated into `MATCH (a)`:

```text
MATCH (n:Program) -- keep the programs
RETURN count(*) AS total
```

Use `-` for an undirected relationship.

## Gated constructs

A construct the profile lists but this release cannot execute raises a
positioned `QuerySemanticError` that names the construct and the follow-up
change, and the statement does not execute:

| Construct | Follow-up change |
| --- | --- |
| Open-ended quantifiers `*`, `+`, `*n..`, `{m,}` | `add-gql-unbounded-traversal` |

## Unsupported constructs

The following are recognized and rejected with a query error before execution:

- `WITH *`
- subqueries (`CALL { ... }`, `EXISTS { ... }`)
- `CASE` expressions and map literals
- whole-map assignment (`SET n = {...}`) and merge assignment (`SET n += {...}`)
- index access such as `n.list[0]`
- `MERGE` over a quantified pattern, a path variable, or more than one pattern
- `INSERT GRAPH` and `CREATE GRAPH`

These boundaries are deliberate. Extending the dialect requires its own
specification change rather than silently accepting partial behavior.
