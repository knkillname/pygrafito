# Design

## Context

See `proposal.md` for motivation and `specs/graph-query-language/spec.md` for the behavior
contract. The current tree has a clean one-way layering, a single SQLite connection per `Graph`,
immutable snapshots, strict property encoding, and traversal evaluators that materialize a whole
graph snapshot. The query language must reuse the storage model and SQLite backend without
inheriting the whole-graph snapshot cost on every query.

The target workload remains thousands of elements with read-heavy access. The existing traversal
APIs stay as they are; the language gets its own execution path.

## Goals / Non-Goals

**Goals:**

- Add a read-only dialect front-end with precise syntax, semantics, and errors.
- Execute fixed-length patterns through indexed SQL joins and predicates.
- Keep one clear value model across filtering, projection, grouping, ordering, and results.
- Preserve snapshot consistency without holding a transaction across user iteration.
- Keep the public object API source-compatible and leave the schema unchanged.
- Make the dialect's boundaries and divergences explicit and testable.

**Non-Goals:**

- Variable-length patterns, recursive traversal, or path enumeration through the language.
- Write clauses, property indexes, `OPTIONAL MATCH`, `WITH`, `UNWIND`, subqueries, or `MERGE`.
- A streaming result cursor, a cost-based optimizer, or a query timeout.
- Changing `find_nodes` / `find_relationships` equality semantics.
- Making `Node` and `Relationship` publicly hashable.

## Decisions

### D1: The language is the interface; the object API is the substrate

The dialect becomes the primary query surface. `Graph.query`, `Graph.prepare`, and `PreparedQuery`
are the public entry points; the existing `Graph` and `Transaction` object methods remain as a
lower-level escape hatch. A parallel public query-builder DSL is deliberately not built, because
it would duplicate the language's semantics and split the surface.

Alternative considered: expose a composable Python predicate/query builder first. Rejected because
the language is the stated destination; the internal IR is still built, but it is not a second
public product.

### D2: A query subpackage inside `engine`

The front-end and executor live under `src/pygrafito/engine/query/` rather than in a new top-level
layer. `Graph` and `Transaction` call into it, so a separate `pygrafito/query/` package imported by
`engine` would create a cycle.

```
model <- storage <- engine <- __init__
                         |
                         +-- engine/query/
                              tokens.py      token kinds and source spans
                              lexer.py       text -> tokens
                              ast.py         frozen statement and expression nodes
                              parser.py      tokens -> AST
                              semantic.py    scopes, types, aggregates, columns
                              plan.py        logical and physical operators
                              compiler.py    pattern/expression -> SQL + residual
                              values.py      query values, equality keys, ordering keys
                              executor.py    plan execution, aggregation, result assembly
                              prepared.py    PreparedQuery and plan reuse
                              result.py      QueryResult and Row
```

Query errors are added to `model.py` with the rest of the domain hierarchy. The query subpackage
may import `model`, `storage`, and the rest of `engine`; nothing in `storage` or `engine` may
import the query subpackage except `Graph` and `Transaction` as entry points. No module-level
functions are introduced; lexer, parser, analyser, compiler, and executor are classes.

### D3: Hand-written lexer, recursive-descent parser, Pratt expressions

The runtime is standard-library only, so the front-end is hand-written. The lexer produces tokens
with line, column, and offset. Keywords and function names are case-insensitive; identifiers are
case-sensitive; backticks quote arbitrary identifiers for labels, types, property keys, and
variables. The lexer recognizes unsupported clause keywords (`OPTIONAL`, `WITH`, `UNWIND`,
`CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE`, `CASE`) so the parser can produce a pointed error
instead of a generic unexpected-token message.

The parser is recursive descent for clauses and Pratt for expressions. Precedence, tightest first:
postfix property access and calls; unary minus and `NOT`; `*`, `/`, `%`; `+`, `-`; comparisons,
`IN`, `IS NULL`, `IS NOT NULL`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`; `AND`; `OR`. The parser
accepts one statement with an optional trailing semicolon and rejects additional statements.

Alternatives considered: a parser generator or an external parser library. Rejected because the
runtime must remain dependency-free and because the project style keeps helpers in classes.

### D4: Fixed patterns compile to indexed SQL joins

The compiler builds a join tree from the path pattern. Each node pattern becomes a `nodes` scan
with label and property predicates; each relationship pattern joins `relationships` and the next
node. Direction maps directly to the indexed endpoint columns:

- outgoing: `r.src = current.id AND r.dst = next.id`
- incoming: `r.dst = current.id AND r.src = next.id`
- both: a canonical-orientation subquery so a self-loop is produced exactly once

```
undirected expansion

SELECT r.id, r.src, r.dst, r.rel_type, r.props,
       CASE WHEN r.src = ? THEN r.dst ELSE r.src END AS next_id
FROM relationships AS r
WHERE r.src = ? OR r.dst = ?
```

The join then uses `next_id` instead of a direction-specific endpoint. This preserves the existing
traversal rule that an undirected self-loop is yielded once.

Labels become `EXISTS` subqueries over `node_labels`, which use the primary key and the label
index. Property predicates always pair `json_type` with `json_extract` and use quoted JSON paths:

- numeric equality: `json_type(alias.props, ?) IN ('integer','real') AND json_extract(...) = ?`
- boolean equality: `json_type(...) = 'true'` / `'false'`
- string equality: `json_type(...) = 'text' AND json_extract(...) = ?`
- list equality: `json_type(...) = 'array' AND json_extract(...) = ?` with canonical JSON text
- numeric range: numeric type guard plus the comparison operator
- null test: `json_type(...) IS NULL` / `IS NOT NULL`
- string predicates: type guard plus `instr` / `substr`, which are case-sensitive

All values are bound as `?` parameters. Labels, relationship types, and property keys are
validated literals; they are never interpolated as data. The compiler is a class that accumulates
selected columns, joins, predicates, and parameters, so there is no ad-hoc string concatenation at
call sites.

Repeated variables add equality constraints instead of new joins. Anonymous pattern elements get
generated aliases but are not projected.

### D5: Hybrid pushdown with a Python residual

Not every expression is worth or able to compile to SQL. A pushdown analyser splits `WHERE`:

- `AND` pushes each pushable side independently.
- `OR` pushes only when both sides are pushable.
- `NOT` pushes only when its operand is pushable.
- Variable, literal, parameter, property access, comparison, `IN` with a literal list,
  `IS NULL`, `IS NOT NULL`, and the string predicates are pushable.
- Function calls that need decoded graph values, `IN` with a parameter list, and anything
  referencing an unsupported construct remain residual.
- Arithmetic remains residual and is evaluated in Python, so division-by-zero and overflow
  semantics are exact rather than SQLite's null-and-coercion behavior.

Pattern matching and pushable property predicates run in SQL; the residual predicate, projection,
aggregation, ordering, and pagination run in Python over the matched rows. This keeps the common
label/property filters indexed while avoiding a second full expression compiler for the first
slice.

Projection, grouping, ordering, and pagination are Python-side for this change. SQLite's ordering
does not express the dialect's mixed-type total order or its null placement, and Python-side
aggregation makes `collect`, `DISTINCT`, and empty-input semantics straightforward. Pushing those
operators into SQL is a later optimization, not a behavior change.

### D6: Value model

Stored properties keep their existing strict types. Query values are a wider result-only model:

```
type QueryValue = (
    None
    | bool
    | int
    | float
    | str
    | list[QueryValue]
    | Mapping[str, QueryValue]
    | Node
    | Relationship
    | Path
)
```

Integers and floats are one numeric family for equality and ordering; booleans are tagged apart.
Strings compare by Unicode code point. Lists compare element-wise with order significant. Null is
query-only: missing properties, null literals, and null aggregate results. Maps appear only as
query results, chiefly from `properties()`.

This deliberately differs from `find_nodes` / `find_relationships`, which are exact-match storage
filters. The language reference will document the difference: the object API preserves stored
types; the dialect compares numbers numerically.

Equality, `DISTINCT`, and grouping use a canonical `ValueKey`: tagged null, bool, number, string,
list, map, node, relationship, and path keys. Python already treats `36 == 36.0` and equal hashes,
so numbers need no special case beyond the bool tag. Entity keys use ids; path keys use the
relationship ids in order. This avoids changing `Node.__hash__` in this change.

Ordering uses a key tuple: null last in ascending order, then booleans, numbers, strings, and
lists; descending reverses the key so null sorts first. Entity and map sort keys are rejected
with a semantic or execution error rather than given an arbitrary order.

### D7: Execution under a short read transaction

`Graph.query` and `PreparedQuery.execute` acquire the graph connection, start a deferred read
transaction (`BEGIN`), run the plan, materialize the projected rows, and then `COMMIT` or
`ROLLBACK`. The result is returned only after the transaction is closed, so no transaction is held
across user iteration. At the target size, materializing the projected result is acceptable, and
it makes the snapshot guarantee simple to reason about.

`Transaction.query` does not start or finish a transaction; it uses the active transaction's
connection and sees its uncommitted writes. `Graph.query` and `PreparedQuery.execute` raise
`TransactionError` while a transaction is active, matching the existing convenience-write guard.
`Graph.prepare` is allowed while a transaction is active because it performs no database work, but
executing the prepared query through the graph is rejected.

The executor reads nodes in batches after the SQL phase: it collects the bound node ids, loads
their labels and properties in one batch, and builds immutable snapshots. Relationship rows carry
all fields. This avoids a per-node query and preserves snapshot consistency.

### D8: Planning and execution pipeline

```
tokens -> AST -> bound syntax -> logical plan -> SQL fragment + residual expression
                                                    |
                                                    v
                                      SQL match rows -> bindings
                                                    |
                                                    v
                            residual filter -> projection -> grouping -> distinct
                                                    |
                                                    v
                                        order -> skip -> limit -> QueryResult
```

The plan is a small operator pipeline, not a general optimizer. The driving node is the first
node pattern; the path order determines expansion order. A later planner can reorder joins or push
limit, but this change keeps the first plan predictable and testable.

Aggregation is a Python operator over projected expressions. If no aggregate is present, each
matched row produces one output row. With aggregates and no grouping keys, zero input still
produces one aggregate row. With grouping keys and zero input, it produces no rows. `count(*)`
uses the input row count; other aggregates skip null inputs. `collect` preserves input order.
`DISTINCT` applies after projection and before ordering, using `ValueKey`.

Ordering is a stable multi-key sort from the least significant key to the most significant key, so
each key's `ASC` / `DESC` direction is honored. `SKIP` and `LIMIT` slice after ordering. A query
without `ORDER BY` has unspecified row order; tests that care about order must specify it.

### D9: Public API and lifecycle

```python
class Graph:
    def query(self, text: str, parameters: Mapping[str, QueryValue] | None = None) -> QueryResult: ...
    def prepare(self, text: str) -> PreparedQuery: ...

class PreparedQuery:
    @property
    def columns(self) -> tuple[str, ...]: ...
    def execute(self, parameters: Mapping[str, QueryValue] | None = None) -> QueryResult: ...

class Transaction:
    def query(self, text: str, parameters: Mapping[str, QueryValue] | None = None) -> QueryResult: ...
```

`QueryResult` exposes ordered `columns` and an iterable of immutable `Row` mappings. A row supports
`row["alias"]`. Result values are the `QueryValue` model. `PreparedQuery` holds the parsed,
analysed, and planned statement and the graph it belongs to; it does not hold parameter values.
`Graph.query` is prepare plus execute for callers who do not need reuse; an internal parse cache
may be added later without changing behavior.

### D10: Error hierarchy

```text
PygrafitoError
  QueryError
    QuerySyntaxError
    QuerySemanticError
    QueryExecutionError
```

The three concrete errors carry `line` and `column` when a source position exists. Syntax errors
come from the lexer or parser; semantic errors cover unbound variables, kind mismatches, invalid
aggregate use, duplicate columns, unknown functions, missing parameters, and unsupported clauses;
execution errors cover arithmetic overflow, division by zero, and runtime type failures. SQLite
errors are caught at the execution boundary and wrapped as `QueryExecutionError`; raw SQLite
exceptions never escape.

### D11: Testing and documentation strategy

- Lexer and parser tests cover accepted syntax, rejected syntax, keyword casing, identifiers,
  backticks, literals, parameters, comments, and source positions.
- Semantic tests cover scopes, variable kinds, aggregate rules, columns, functions, and missing
  parameters.
- Execution tests use TRON fixtures and cover labels, types, directions, property maps, paths,
  repeated variables, diamonds, cycles, parallel relationships, self-loops, distinct, aggregates,
  ordering, nulls, numeric equality, string predicates, and pagination.
- Security tests pass quoted strings, backticks, and SQL-looking text as parameters and assert
  that they are data, never structure.
- Lifecycle tests cover prepared reuse, transaction visibility, the active-transaction guard, and
  closed handles.
- A dialect conformance suite contains representative queries and expected rows, written against
  the spec rather than another product's suite.
- README language examples run through the existing snippet test. A language reference document
  records the grammar, semantics, and divergences; no product names or trademarks appear in code,
  tests, specs, or docs.

## Risks / Trade-offs

- **Numeric equality diverges from the object API** -> Document it prominently, test both paths,
  and describe the dialect as a value model rather than a storage filter.
- **Undirected self-loops can duplicate rows** -> Use the canonical-orientation subquery and test
  self-loops, parallel relationships, diamonds, and cycles.
- **SQL construction is a security boundary** -> Build SQL from the AST, bind every value, validate
  every literal identifier, and test with adversarial parameter values.
- **Python-side ordering and aggregation materialize rows** -> Acceptable at the stated target;
  keep `LIMIT` behavior correct, document the cost, and leave pushdown as a later optimization.
- **No property indexes yet** -> Label and endpoint indexes cover pattern traversal; property
  predicates may scan matching candidates. Measure before adding indexes and do not promise
  indexed property lookup in this change.
- **A read transaction on the shared connection can conflict with writes** -> Close the read
  transaction before returning results and reject graph-level queries while an explicit
  transaction is active; use `Transaction.query` inside a transaction.
- **`Node` remains unhashable** -> Use `ValueKey` internally for distinct and grouping; a public
  hashing decision is a separate change.
- **Parser scope can grow without a boundary** -> Reject unsupported clauses explicitly, keep the
  core profile in the spec, and add new syntax only with its own spec change.
- **Documentation drift** -> Execute README examples and keep the conformance suite in the same
  task group as the implementation.

## Migration Plan

No schema or data migration is required. The change is additive: new modules, new public API, new
errors, and new documentation. Existing databases and object-API calls continue to work. Rollback
is removing the query subpackage and its exports; no data changes are involved.

## Open Questions

- The public language name is a branding decision. The grammar keywords are generic, so the
  technical work can proceed under a neutral working name; a trademark check belongs before any
  public naming commitment.
- Streaming results, SQL pushdown of projection/aggregation, and property indexes are deliberate
  later optimizations. They do not change this change's behavior, approach, or task breakdown.
