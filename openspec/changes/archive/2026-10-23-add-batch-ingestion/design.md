# Design

## Context

See `proposal.md` for motivation and `specs/` for the behavioral contract.

The query engine is a one-pass pipeline: `Lexer` → `Parser` → `Statement` of frozen clause
nodes → `SemanticAnalyzer` (`Analysis` with ordered read stages plus trailing write clauses) →
`PlanBuilder` → `QueryExecutor`. Fixed-length `MATCH` stages compile to SQL through `Compiler`
and run against SQLite indexes; a stage containing a quantified relationship runs in
`PatternEngine`. Write clauses are applied after every read stage by `MutationExecutor`, which
deduplicates operations by entity id before applying them.

Two current properties shape this change. First, pattern property maps are evaluated with
`ConstantEvaluator`, so they may only contain literals and parameters. Second, the mutation
stage is batch-oriented: it collects all operations for a clause, deduplicates them, and applies
them once. Both are correct today and both are wrong for `UNWIND`-driven upserts.

There is no import surface: `Graph` exposes convenience writes and `query`, and the shell has
only single-statement and dot-command handlers. The storage schema is not affected by this
change.

## Goals / Non-Goals

**Goals:**

- `UNWIND` as a first-class read stage and row source.
- `MERGE` with whole-pattern, row-sequential match-or-create semantics.
- `ON CREATE SET` / `ON MATCH SET` as part of the `MERGE` clause.
- Pattern property values that can be computed from the current row, without giving up indexed
  SQL matching.
- A statement-driven import API and `.import` shell command with explicit batch boundaries.
- Keep existing transaction, snapshot, error, and typing guarantees.

**Non-Goals:**

- `CASE`, map literals, subqueries, `CALL`, and `LOAD CSV`.
- `MERGE` over quantified paths, path variables, or more than one path pattern.
- A column-mapping DSL, CSV type inference, or a schema description language.
- Streaming query results or changes to the materialized `QueryResult` contract.
- Explaining write operators; `Graph.explain` continues to describe read stages.
- Any schema version change, migration, or new dependency.

## Decisions

### D1: `UNWIND` is a read stage; `MERGE` is a write clause

Add frozen `Unwind(expression, variable)` and `Merge(pattern, on_create, on_match)` nodes to
`ast.py`. `Unwind` analyses to a new `UnwindStage` in `ReadStage`, so it participates in the
existing stage loop, `Plan` pipeline, and `WITH`-style scope changes. `Merge` joins `WriteClause`
and is applied with the other write clauses after every read stage. `on_create` and `on_match`
are ordinary `Set` nodes, not top-level clauses.

This keeps the engine's "all reads, then writes" model. The alternative — a general Cypher
pipeline where reads and writes interleave arbitrarily — would require a pull-based iterator
engine and is not justified by batch ingestion.

Consequences: `UNWIND` may appear wherever a read stage may, but not after a write clause;
`MERGE` may appear only in the write section; `RETURN` remains final. The core-profile
requirement records these positions.

### D2: Pattern property values become row expressions

Pattern property maps change from constant-only to non-aggregate expressions evaluated against
the row produced by earlier stages and the statement parameters. This is required, not optional:
`UNWIND $rows AS row MERGE (n:Program {designation: row.designation})` cannot work otherwise.

- The semantic analyzer validates every property expression against a snapshot of the scope
  taken **before** the pattern is bound, so a pattern cannot reference a variable it introduces
  itself. Aggregates are rejected.
- A new `PatternValueResolver` wraps `ExpressionEvaluator` plus a binding and evaluates one
  expression to a `QueryValue`. `Compiler._add_property_predicates` and
  `PatternEngine._properties_match` use it instead of `ConstantEvaluator`. Existing constant
  expressions follow the same path, so there is one evaluator, not two.
- `Compiler.compile` already runs once per input row (`_run_match_stage` calls `_match_rows` per
  binding), so per-row evaluation adds no new recompilation class.
- `Graph.explain` has no row to evaluate. It uses a null placeholder resolver, which compiles a
  valid predicate and keeps the plan representative. Plans for statements whose values can only
  be known at execution time are documented as representative.
- Null behavior differs by clause and is specified: `MATCH` matches nothing, `CREATE` omits the
  key, `MERGE` raises.

This is additive: previously a variable in a pattern map was a semantic error. It also removes
the "literals or parameters" restriction from `CREATE`, which the spec delta records.

### D3: `UNWIND` evaluates one row at a time

`UnwindStage` carries the expression and the new variable name. Execution, per input row:

1. Evaluate the expression in the current binding.
2. `None` → emit no rows.
3. A sequence that is not a string → emit one row per element, preserving order, with the
   variable bound to the element.
4. Anything else → `QueryExecutionError`.

Strings are excluded explicitly even though Python strings are sequences; the dialect's list is
the only iterable value. A statically non-list literal is rejected by the analyzer before
execution. The variable must not already be in scope: the existing `_register` accepts a
same-kind re-registration, so `UNWIND` performs an explicit redefinition check instead of
relying on it.

An `UNWIND`-only read statement is valid because `_validate_clause_shape` gains a "row source"
notion: `MATCH` or `UNWIND` satisfies it, and a write statement still needs neither.

### D4: `MERGE` matches per row, then creates, sequentially

For each input row, in order:

1. Match the whole pattern with `_match_rows` and the row's binding. This reuses the SQL
   compiler, label/property indexes, and bound-variable anchors.
2. If there is at least one match, emit one row per match, apply `on_match` to each, and create
   nothing.
3. If there is no match, create the pattern with a new `PatternCreator` and apply `on_create`
   to the created row.

`PatternCreator` threads one working binding through the pattern. A bound variable is reused;
an unbound node variable is created on first use and reused by later occurrences in the same
pattern, so `MERGE (a)-[:MONITORS]->(a)` creates one node and a self-loop. On the create path,
only variables bound by earlier clauses anchor the pattern; an unbound node is created fresh
even when an equivalent node exists. This is the whole-pattern rule the spec records.

Sequential execution is the central departure from the existing mutation stage. `MERGE` must see
creations made by earlier rows of the same statement, otherwise two input rows with the same key
create two nodes. The existing deduplicate-then-apply model cannot express that, so `MERGE`
bypasses it and writes one row at a time on the same connection, inside the statement's existing
transaction or savepoint. The rest of `MutationExecutor` keeps its batch behavior.

`MERGE` rejects quantified relationships, path variables, multiple patterns, non-outgoing
relationships, missing relationship types, and bound relationship variables. Those restrictions
keep creation unambiguous: a `MERGE` must know exactly which elements it can create.

Alternative considered: compile `MERGE` into `MATCH ... CREATE` in one SQL statement. SQLite
cannot return created rows and bindings from the same statement without a second round trip, and
per-row visibility would still need Python orchestration. The compiler plus `PatternCreator`
path is simpler and preserves the existing snapshot and error mapping.

### D5: Conditional updates are per-row `SET` applications

`Merge.on_create` and `Merge.on_match` hold `Set` nodes, so assignment parsing, validation, null
removal, label rules, and error mapping are reused unchanged. The parser accepts at most one
`ON CREATE SET` followed by at most one `ON MATCH SET`; `ON` becomes a keyword. Adding `SET`
after `MERGE` without `ON` remains an ordinary top-level clause that applies to every row.

`MutationExecutor._set` is refactored into a single-row helper plus the existing batch loop. The
`MERGE` executor calls the single-row helper immediately after a match or creation, so a
conditional assignment is visible to `RETURN` and to later rows. Applying both conditional
clauses after the whole clause would lose which rows were created and which matched.

### D6: Import is a thin runner over prepared statements

New module `engine/importing.py` with:

- `ImportRunner`, which validates the statement, reads batches, executes them, and aggregates
  counters.
- `ImportSummary` (rows, batches, aggregate `MutationSummary`).
- A `RowReader` protocol with `CsvReader` and `JsonLinesReader` implementations, both
  generators so files are never materialized whole.
- Format detection from the explicit argument, then `.csv`, `.jsonl`, or `.ndjson`.

`Graph.import_rows` and `Graph.import_file` construct the runner. The statement is prepared once
through the existing query API. `PreparedQuery` gains read-only `is_write` and `parameters`
properties so the runner can reject a read statement or a statement that never references
`$rows` before reading the file. These properties are additive and useful to any tooling.

Default execution calls `PreparedQuery.execute({"rows": batch})`, which gives each batch its own
`BEGIN IMMEDIATE` transaction. `atomic=True` opens one `graph.transaction()` and calls
`Transaction.query` per batch; that reparses each batch, which is negligible against file I/O
and avoids adding a transaction-aware prepared query for this change. The write guard runs
before the first file read, so a read-only handle fails fast.

Failure handling keeps the original error type and adds a note with the source, one-based row,
and batch number. The batch transaction rolls back through the existing executor paths. In
non-atomic mode earlier batches stay committed; in atomic mode the enclosing transaction rolls
back.

CSV uses `csv.DictReader` with strict header checks: header required, duplicate names rejected,
and row width must equal header width. Values stay strings; the statement converts them. JSONL
uses `json.loads` per non-blank line with a `parse_constant` hook that rejects `NaN` and
infinity, and requires each value to be an object. In-memory rows are validated as mappings with
string keys.

There is deliberately no mapping DSL: the statement is the mapping, which keeps one expression
language and one error surface.

### D7: `.import` is a dot-command with quoted options

`Commands.DESCRIPTIONS` gains `import`; `_command_import` parses the argument with
`shlex.split`, so `--statement "UNWIND $rows AS row MERGE ..."` is one argument and `$rows` is
not expanded. Required `PATH` and `--statement`; optional `--format`, `--batch`, `--atomic`.
Unknown or malformed options raise `ValidationError` with usage text. The command refuses while
an explicit transaction is active, matching `.backup` and index commands, and lets
`ReadOnlyError` propagate in a read-only session.

The command calls `Graph.import_file` and prints one summary line (rows, batches, created and
deleted elements, property and label changes). Failures go through the shell's existing
`PygrafitoError` reporting, so the prompt returns and scripts exit non-zero. `.help import`
works through the existing description table.

### D8: Plans and diagnostics

`PlanOperator` gains `UNWIND` and `MERGE`. `PlanBuilder` maps `UnwindStage` to the `UNWIND`
operator and `Merge` to the `MERGE` write operator. `QueryExecutor.explain` emits a synthetic
`UNWIND` line for an unwind stage; write operators remain outside `explain`, consistent with
`CREATE` and `SET`.

Error classification follows the existing model: clause-shape and grammar failures are
`QuerySyntaxError`; static type, scope, and pattern restrictions are `QuerySemanticError`;
runtime list/type violations and null merge values are `QueryExecutionError`. Parser and
analyzer errors carry the token span.

## Risks / Trade-offs

- **[Whole-pattern creation surprises users]** → The rule is explicit in the spec, documented
  with a worked example, and covered by a scenario; users who need partial reuse split the
  pattern into multiple `MERGE` clauses.
- **[Per-row `MERGE` is slower than a batch upsert]** → It compiles the same SQL the `MATCH`
  path compiles and still uses indexes. Benchmark a 10,000-row merge during implementation and
  add a single-node fast path only if the measurement justifies it.
- **[Conditional updates can be applied twice]** → The conditional `Set` runs exactly once per
  output row, immediately after the match or creation, and is never re-applied by the outer
  mutation pass.
- **[Dynamic pattern values widen the language]** → Scope is snapshotted before the pattern,
  aggregates are rejected, and the resolver is shared by the SQL and pattern engines so both
  paths agree.
- **[CSV strictness rejects real files]** → Errors name the header or row; explicit `--format`
  handles unusual suffixes; delimiter and quoting remain the standard library defaults.
- **[Atomic import grows the write-ahead log]** → Per-batch commit is the default; atomic mode
  is documented as a whole-file transaction.
- **[`UNWIND` with a very large list materializes rows]** → Import batches bound the list;
  direct users are documented to batch as well.
- **[Explain shows representative values for dynamic predicates]** → Documented in the plan
  inspection notes; execution is unaffected.

## Migration Plan

No storage or schema migration. The change accepts syntax that was previously rejected and
relaxes the constant-only rule for pattern properties; existing statements keep their behavior
except that `ON` becomes a reserved word, so an element variable named `on` must be
backtick-quoted. Existing files remain readable and writable by older builds. Rollback is a
code revert with no data conversion. Documentation must remove `UNWIND` and `MERGE` from the
unsupported list and describe the new import surface before release.

## Open Questions

- Should `.import` accept `-` to read from standard input? Deferrable; it adds an input-mode
  branch but no semantic change.
- Should CSV expose a delimiter option? Deferrable; the default comma, quoting, and escaping
  cover the common case.
