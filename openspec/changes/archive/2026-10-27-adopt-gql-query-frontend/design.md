# Design

## Context

See `proposal.md` for motivation and `specs/graph-query-language/spec.md` for the contract.

The frontend is roughly 7,600 lines across `lexer.py` (591), `parser.py` (1,524),
`semantic.py` (1,462), `compiler.py` (1,199), `executor.py` (1,660), `values.py` (1,765),
`ast.py` (623), and `plan.py` (278). The shape that constrains this change:

- `Keyword` is a closed enum in `tokens.py`; `KeywordIndex.BY_NAME` is derived from its members, so
  every new word is a new member.
- `Parser.parse` dispatches clauses through a flat `if` chain over keywords and already has a
  `_reject_unsupported` path (`UNSUPPORTED_CLAUSES` currently holds `CASE`) that raises a
  positioned `QuerySemanticError`.
- `_relationship_pattern` assumes two dashes around an optional detail: `<` `-` `[detail]` `-` or
  `-` `[detail]` `-` `>`. The single-dash GQL forms are a different shape, not a token alias.
- `Direction` lives in `model.py` as a public traversal enum (`OUTGOING`, `INCOMING`, `BOTH`).
  Adding a member is public API surface.
- Label filters are a tuple of labels resolved to SQL against `node_labels` and
  `relationship_labels`.
- No conformance corpus exists. `tests/test_gql_profile.py` checks that the profile page, tier
  headings, and matrix statuses are internally consistent; it executes no query.
- The documentation contract executes Python fences in `docs/index.md`,
  `docs/getting-started/quickstart.md`, and `docs/guides/*.md`. Reference pages are only parsed.
- Tours 01 and 02 are owned by this change; 03 and 04 are owned by `add-gql-composition` and
  `add-gql-path-semantics`.

## Goals / Non-Goals

**Goals:**

- Flip the executable surface to the canonical spellings while keeping the compatibility aliases
  the profile already commits to.
- Make the corpus the definition of "supported": no matrix row flips without a passing case.
- Make gated constructs fail by name and by owner, with a source position.
- Leave the engine's row production, mutation, and value semantics untouched.

**Non-Goals:**

- No change to `Direction` or to the Python traversal API.
- No path-mode vocabulary, budget counters, or `{n,m}` execution in this change.
- No new value types, functions, clauses, or composition stages.
- No change to `gql-profile` requirements; only its page, matrix, and corpus obligation.

## Decisions

### D1. Aliases lower to the same AST node

`INSERT` produces the existing `Create` node; `FOR` produces `Unwind`; `FILTER` produces a new
`Filter` node and a `FilterStage`; `OFFSET` fills the existing skip field; `NODETACH DELETE`
produces the existing non-detaching `Delete`. The canonical spelling is not retained in the AST,
because nothing downstream needs it and column names are already derived from expression text.

*Alternative:* a node per spelling. Rejected: it duplicates every semantic, planner, and executor
branch to express the same behavior, which is exactly the duplication this change is trying to
remove.

### D2. `FILTER` is a stage; `MATCH ... WHERE` is not its alias

`MATCH ... WHERE` stays part of the match stage, as the profile says. A standalone `FILTER`
(including `FILTER WHERE`) is a new `FilterStage` that filters the previous stage's rows and
introduces no bindings. `WHERE` after `WITH` lowers to the same stage. This keeps scope explicit
when `LET`/`NEXT` arrive.

*Alternative:* treat every `WHERE` as a filter stage. Rejected: it would change the scope and the
null-row behavior of `OPTIONAL MATCH ... WHERE`, which is defined as part of the optional stage.

### D3. Arrow grammar is rewritten, not aliased

`_relationship_pattern` becomes: opening dash, optional detail, then a direction suffix.

```
form     meaning                              representation
------   ----------------------------------   ------------------------------
->       directed, traversed forward          Direction.OUTGOING
<-       directed, traversed backward         Direction.INCOMING
-        any incident relationship            Direction.BOTH
~        undirected relationship only         Direction.BOTH + undirected_only
-->      alias of ->                         Direction.OUTGOING
<--      alias of <-                         Direction.INCOMING
<~ ~> <-> not defined by the profile yet      gated-construct error
```

`undirected_only` is a query-pattern flag, not a new `Direction` member, so the public traversal
enum is untouched. `RelationshipPattern` gains the flag and the compiler adds
`relationship_directed = 0` to that join.

*Alternative:* add `Direction.UNDIRECTED`. Rejected: it changes a public enum that traversal and
index filters also use, for a query-only distinction.

### D4. `--` is a comment unless it abuts a pattern

The lexer recognises `-->` and `<--` by maximal munch before comment handling, so arrows survive.
A bare `--` becomes a line comment. To stop `(a)--(b)` from silently becoming `MATCH (a)`, the
parser rejects a comment token whose span starts exactly at the previous token's end when the
previous token closes a node or relationship (`)` or `]`). A comment after whitespace is normal.

*Alternative:* reject `--` after any pattern regardless of spacing. Rejected: it forbids the
ordinary `MATCH (a) -- explain` line, which is a legitimate GQL comment. *Alternative:* keep `--`
as the undirected arrow and drop `--` comments. Rejected: it would make the profile's canonical
comment form unavailable and keep the ambiguity alive.

### D5. Label expressions compile to SQL, with one AST tree

`LabelExpression` is a small tree: `Label`, `And`, `Or`, `Not`, `Wildcard`, with GQL precedence
`!` tightest, then `&`, then `|`. `:` and `IS` both produce the same tree; `:A:B` and `:A&B` are the
same conjunction. The compiler resolves the tree to `EXISTS`/`NOT EXISTS` subqueries over the
label tables so declared indexes still drive the scan.

*Alternative:* evaluate labels in Python after the SQL row set. Rejected: it defeats index
selection and duplicates the existing label-join logic.

### D6. Inline element `WHERE` is scoped to the element

A node or relationship pattern may carry a predicate. Semantic analysis checks it against only the
variables the element pattern can see, and the compiler applies it inside that element's join, per
hop. This is what makes a quantified pattern's per-hop filter correct.

*Alternative:* lower it to a stage filter. Rejected: a stage filter runs after quantization, so it
would filter paths instead of edges.

### D7. `OFFSET`, `NULLS`, and `RETURN *` stay in the existing layers

`OFFSET` reuses the skip field. `SortItem` gains a null-ordering enum, parsed per key and compiled
into the existing `ORDER BY` emission. `RETURN *` expands at semantic analysis into the current
scope's variables in introduction order, so `PreparedQuery.columns` is known before execution.

*Alternatives:* runtime expansion of `*` (rejected: columns must exist at prepare time); Python
null ordering (rejected: sorting already happens in SQL).

### D8. Gated constructs share one table and one error type

A module-level table maps a construct to a message and the follow-up change. The parser and the
semantic analyzer consult it and raise `QuerySemanticError` with a position. No new exception
class is added; the public taxonomy stays `QuerySyntaxError`, `QuerySemanticError`, and
`QueryExecutionError`.

*Alternative:* a `QueryUnsupportedError` subclass. Rejected: it is public API churn for a
transitional state, and callers already catch `QueryError`.

### D9. The corpus is JSON, small, and independent of the example layer

`tests/conformance/cases.json` holds named fixtures and cases; `tests/test_conformance.py` builds
each fixture through the public API, runs the case, and compares rows or the error type and a
message fragment. JSON because the runtime is standard-library only and `tomllib` cannot write.

```json
{
  "fixtures": {"tron-cycle": {"nodes": [], "relationships": []}},
  "cases": [{"name": "...", "feature": "...", "fixture": "...", "query": "...",
             "params": {}, "expect": {"rows": []}, "tags": ["canonical"]}]
}
```

Fixtures are local to the corpus: cycle, diamond, parallel relationships, self-loop, multi-label,
and undirected edges. The 78-node example graph is deliberately not used, so a corpus run stays
fast and the language contract never depends on `examples/`.

*Alternatives:* YAML (no stdlib writer/reader); reusing `examples/data/grid.json` (slow, and
couples two capabilities).

### D10. Matrix flips are mechanical and gated

For each row, the task is: add a case, run it, flip the matrix, and update the status board. Rows
for `{n,m}`, path modes, ordinality, `RETURN NO BINDINGS`, `LET`, `NEXT`, `GROUP BY`, and the
deferred path features stay gated. The consistency test enforces both directions: a `supported`
row needs a passing case, and a gated row may not carry a case tagged `supported`.

### D11. The tour guard is re-aimed, not deleted

After the migration, `01-match` and `02-write` use canonical spellings. The guard test keeps its
purpose — a tour cannot run ahead of the release — by forbidding the *new* target-only set
(`LET`, `NEXT`, `GROUP BY`, `{n,m}`, path modes, `RETURN NO BINDINGS`, `<~`, `~>`, `<->`) and the
anonymous `->` form is removed from the forbidden list because it is now canonical.

## Risks / Trade-offs

- **`--` adjacency surprises a reader.** → Document the rule in the reference and the changelog,
  cover `(a)--(b)` and `(a) -- note` with corpus cases, and keep the error positioned.
- **The arrow rewrite regresses quantified or undirected traversal.** → Run the traversal
  fixtures and the corpus cycle/diamond/parallel/self-loop cases; keep `-->`/`<--` as aliases so
  existing statements stay green.
- **Label expressions produce expensive SQL.** → Compile to `EXISTS` over the label tables, keep
  the existing index-transparency tests green, and add a corpus case for a conjunction and a
  negation.
- **Corpus scope grows without bound.** → Cases cover only rows this change flips, plus one case
  per gated diagnostic. Deferred features get no cases.
- **Error message fragments become a de-facto contract.** → Test only the stable part (construct
  name and follow-up change), and document the shape once in the error section.
- **Tour 03/04 still use legacy forms.** → Their owning changes are named in the catalog; the
  guard permits legacy forms and forbids only the new target-only set.

## Migration Plan

No storage, snapshot, API, or CLI migration. Queries using `--` as an undirected arrow break by
design; the changelog names the replacement (`-`). Rollback reverts the query modules, tests,
docs, and tours; no data is affected.

Land in this order: corpus and runner, vocabulary and diagnostics, clause spellings, pattern
grammar, ordering and projection, then the matrix, documentation, and tour migration, with the
folded maintenance in its own group.

## Open Questions

- Whether `IS` or `:` should rank first as the canonical label form. This change preserves the
  profile's current ranking (`:` first, `IS` accepted) and implements both; reversing it is a
  profile decision.
- Whether `type()` should become "the single label, null or error when ambiguous" instead of
  "first sorted label". It is untouched here; `LABELS()` already returns the full set.
