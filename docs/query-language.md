# Query language

`pygrafito` includes a read-only, pattern-matching query dialect. A query
describes a fixed-length path pattern, filters the matches, and projects values
into a materialized result. The dialect is intentionally small: it supports
reads only, rejects unsupported syntax instead of ignoring it, and runs through
indexed SQL joins over the existing property-graph schema.

## Read-only query execution

One call executes exactly one read-only statement and returns a materialized
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
`PreparedQuery`. Statements containing a write clause are rejected before any
SQL runs and never change data.

## Core dialect profile

A statement has this shape:

```text
MATCH <path pattern>
[WHERE <expression>]
RETURN [DISTINCT] <projection> [, <projection> ...]
[ORDER BY <sort item> [, <sort item> ...]]
[SKIP <expression>]
[LIMIT <expression>]
[;]
```

`MATCH` and `RETURN` are required. There is one path pattern with one or more
node patterns, one `WHERE` clause, and one `RETURN` clause. Multiple statements,
multiple `MATCH` clauses, and multiple path patterns are rejected.

## Node patterns

A node pattern binds an optional variable, zero or more labels, and an optional
property map:

```text
(n)
(:Program)
(p:Program:ISO)
(p:Program {designation: 'Quorra', cycles: 36})
```

Labels are a conjunction: every listed label must be present. Property map
entries compare stored values with the dialect's equality rules. An anonymous
node still participates in path matching but is not bound to a variable.

Property keys may contain dots, spaces, and other punctuation when written in
backticks:

```text
MATCH (n {`a.b`: 1}) RETURN n
MATCH (n) WHERE n.`a b` = 2 RETURN n
```

## Relationship patterns

Relationship patterns bind an optional variable, zero or more types, a
direction, and an optional property map:

```text
(a)-[r:ALLIES_WITH]->(b)          outgoing
(a)<-[r:ALLIES_WITH]-(b)          incoming
(a)-[r:ALLIES_WITH]-(b)           either stored direction
(a)-[r:ALLIES_WITH|TRUSTS]->(b)   type alternatives
(a)-[r {since_cycle: 2020}]->(b)  property filter
(a)-->(b)                         anonymous outgoing relationship
```

A bound relationship snapshot preserves its stored start node, end node, and
type even when the pattern traverses it against its stored direction.

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

## Pattern match row semantics

`MATCH` produces one row per distinct match of the pattern. Parallel
relationships produce one row per relationship, self-loops produce a binding,
and diamonds and cycles produce the matches implied by the graph. Duplicate
projected rows remain until `DISTINCT` is requested.

Undirected relationships are expanded from each endpoint, but an undirected
self-loop is produced once for that node rather than twice.

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
| `labels(n)` | sorted labels of a node |
| `type(r)` | stored type of a relationship |
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
A column takes its alias when present and otherwise its source expression text:

```text
RETURN n.designation AS name, n.cycles
```

produces columns `name` and `n.cycles` in that order. Duplicate column names
raise a semantic error. `DISTINCT` removes duplicate projected rows and applies
after projection and before ordering.

Entity projections return immutable snapshots. A later write does not change a
value obtained from an earlier result.

## Aggregation and grouping

Supported aggregates are `count`, `collect`, `sum`, `avg`, `min`, and `max`,
including `DISTINCT` variants. Non-aggregate `RETURN` expressions form implicit
grouping keys.

```text
MATCH (n:Program) RETURN labels(n) AS labels, count(*) AS total
```

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
(the default) or `DESC`; earlier keys are more significant.

Nulls sort last in ascending order and first in descending order. Other values
order by type family: booleans, numbers, strings, then lists. Entity and map
values are not orderable and raise an execution error if used as a sort key.

`SKIP` and `LIMIT` accept non-negative integers or parameters. Negative,
non-integer, and boolean values are rejected before SQL runs.

```text
MATCH (n:Program) RETURN n.designation ORDER BY n.cycles DESC SKIP 2 LIMIT 5
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

Syntax and semantic errors are raised during preparation, before any query
executes.

## Transaction and lifecycle integration

`Transaction.query` runs on the active transaction's connection and observes
its uncommitted writes without starting or finishing a transaction. `Graph.query`
and `PreparedQuery.execute` raise `TransactionError` while an explicit
transaction is active; use `Transaction.query` inside that block. `Graph.prepare`
is allowed during a transaction because it performs no database work.

Using a closed graph handle for `Graph.query`, `Graph.prepare`, or
`PreparedQuery.execute` raises `GraphClosedError`.

## Query errors and positions

`QuerySyntaxError`, `QuerySemanticError`, and `QueryExecutionError` all derive
from `QueryError` and `PygrafitoError`. Syntax and semantic errors expose
one-based `line` and `column` attributes when a source position is available.
Raw SQLite exceptions do not escape: execution failures are raised as
`QueryExecutionError`.

## Consistent execution snapshot

A query evaluates against one consistent graph state. `Graph.query` and
`PreparedQuery.execute` run inside a short deferred read transaction, materialize
the projected rows, and close the transaction before returning. Later writes do
not change an already returned result.

A query executed through an active transaction includes that transaction's
uncommitted writes and excludes writes from other connections.

## Identifier casing and quoting

Keywords and function names are case-insensitive. Variable names, labels,
relationship types, and property keys are case-sensitive, so `Program` and
`program` are different labels.

Backtick-quoted identifiers may contain spaces, dots, and escaped backticks
(written as doubled backticks) in labels, relationship types, property keys, and
variables.

## Grammar summary

```text
statement        = match-clause [where-clause] return-clause
                   [order-clause] [skip-clause] [limit-clause] [";"]
match-clause     = "MATCH" path-pattern
path-pattern     = [identifier "="] node-pattern
                   { relationship-pattern node-pattern }
node-pattern     = "(" [identifier] { ":" label } [property-map] ")"
relationship     = "-" [ "[" [identifier] [":" type {"|" type}]
                   [property-map] "]" ] "-" [">"]
                 | "<" "-" [ "[" [identifier] [":" type {"|" type}]
                   [property-map] "]" ] "-"
property-map     = "{" [ key ":" expression { "," key ":" expression } ] "}"
where-clause     = "WHERE" expression
return-clause    = "RETURN" ["DISTINCT"] return-item { "," return-item }
return-item      = expression [ "AS" identifier ]
order-clause     = "ORDER" "BY" sort-item { "," sort-item }
sort-item        = expression [ "ASC" | "DESC" ]
skip-clause      = "SKIP" expression
limit-clause     = "LIMIT" expression
```

An identifier is a plain name or a backtick-quoted name. A label, type, key, or
alias may be backtick-quoted. Expression precedence is listed in
[Filtering expressions](#filtering-expressions).

## Unsupported constructs

The following are recognized and rejected with a query error before execution:

- variable-length patterns such as `-[r*1..3]->`
- multiple path patterns or multiple `MATCH` clauses
- `OPTIONAL MATCH`
- `WITH`, `UNWIND`, and subqueries (`CALL { ... }`, `EXISTS { ... }`)
- `CASE` expressions and map literals
- write clauses: `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE`, `DETACH DELETE`
- index access such as `n.list[0]`

These boundaries are deliberate. Extending the dialect requires its own
specification change rather than silently accepting partial behavior.
