# Proposal

## Why

The GQL profile declares a canonical path surface that the engine cannot run yet: `WALK` is the
default path mode, `{n,m}` is the canonical quantifier, and `<~`, `~>`, and `<->` are canonical
directions, but every one of them is gated. The engine is hardwired to relationship-unique trails,
and there is no query budget, so the canonical default cannot be enabled safely on a cyclic graph.
This is also the only breaking change left in the profile plan: every release that ships without it
adds migration debt to examples, documentation, and user queries. It must land before composition
and expression vocabulary build more language surface on top of trail semantics.

## What Changes

- **BREAKING**: canonical GQL path patterns default to `WALK` instead of the current
  relationship-unique trail. A query that relied on the implicit trail must use `MATCH TRAIL` or
  keep the legacy `*n..m` quantifier.
- Add explicit path modes `WALK`, `TRAIL`, `SIMPLE`, and `ACYCLIC`, accepted per path and per
  segment, with the profile's resolution rule: explicit per-path mode, then explicit clause mode,
  then `TRAIL` when the path contains a legacy quantifier, then `WALK`.
- Add the canonical closed quantifier forms `{n}`, `{m,n}`, and `{,n}`. Keep `*n`, `*n..m`, and
  `*0..m` as a compatibility construct whose default mode remains `TRAIL`. Mixing a legacy and a
  canonical quantifier in one path without an explicit mode SHALL be a semantic error.
- Add the remaining canonical edge directions: `<->` for either stored direction but never an
  undirected relationship, `<~` for incoming-or-undirected, and `~>` for outgoing-or-undirected.
- Add a query budget with relationship-expansion and intermediate-row counters, an opt-in wall-clock
  limit, documented defaults, and a per-query override. Exceeding it raises a query execution error
  naming the counter and the limit, returns no partial result, and rolls a write statement back
  entirely.
- Add `QueryBudget` and `QueryBudgetExceededError` to the public API, and accept a budget override
  on `Graph.open`, `Graph.query`, and `PreparedQuery.execute`.
- Keep the Python `paths()` API a relationship-unique, bounded trail enumerator. It does not follow
  the query language's `WALK` default.
- Defer open-ended upper bounds: `{m,}`, `*`, and `+` remain rejected with a deferred-construct
  error until lazy traversal and the budget support unbounded walks.
- Flip the `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`, `{n,m}`, and edge-direction rows in the profile
  matrix to supported, add the conformance corpus cases that back them, and update the profile,
  query-language reference, guides, examples tour, README, and changelog.

## Capabilities

### New Capabilities

None. Path semantics are part of the query language, not a separate durable behavior; a
per-feature capability would fragment the profile's existing organization.

### Modified Capabilities

- `graph-query-language`: path modes and their resolution rule, the canonical `{n,m}` quantifier,
  the remaining edge directions, the query budget and its error/rollback behavior, and the trail
  compatibility contract replace the trail-only rules.
- `gql-profile`: the path-mode, quantifier, direction, and budget rows move from gated to
  supported; the status wording changes now that the path-semantics and budget changes have landed;
  open-ended upper bounds are recorded as deferred.
- `graph-examples`: the tour classification requirement no longer demands a migrating change from a
  tour that relies only on supported constructs, and the path tour states the implemented canonical
  forms.

## Impact

- Engine: `engine/query/pattern.py` (mode-aware walk state, budget counters), `parser.py` (modes,
  `{n,m}`, direction forms), `semantic.py` (mode resolution, quantifier mixing), `plan.py` (mode and
  budget in the plan), `executor.py` (stage row counter, budget errors, rollback).
- Public API: `model.py` (`QueryBudget`, `QueryBudgetExceededError`), `engine/graph.py`
  (`Graph.open(budget=...)`, `Graph.query(budget=...)`), `engine/query/prepared.py`
  (`PreparedQuery.execute(budget=...)`), `__init__.py` exports.
- Compatibility: the `WALK` default changes results for queries that repeat a relationship. Only
  quantified paths and repeated self-loops are affected; non-repeating fixed-length patterns are
  unchanged, and legacy `*n..m` queries keep `TRAIL`.
- Python traversal API is unchanged; a test pins `paths()` to trail semantics.
- Data, schema, storage layout, and the CLI command set are unchanged.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`,
  `docs/guides/querying.md`, `docs/reference/performance.md` (budget defaults and cost),
  `examples/tours/04-paths.gql`, `README.md`, and `CHANGELOG.md`.
- Tests: `tests/conformance/cases.json`, `tests/test_gql_profile.py` coverage, and new engine,
  API, and rollback tests.
