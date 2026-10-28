# Proposal

## Why

The published profile fixed the target language, but the release still executes the transitional
Cypher dialect: all 36 in-profile rows in the conformance matrix are gated, none is supported, and
the corpus the profile promises does not exist. A reader who follows the README into "GQL" gets
`CREATE`, `UNWIND`, and `-->`, and a matrix of promises.

This change makes the profile executable for the surface that can be honest now: canonical clause
spellings, GQL pattern directions, label expressions, inline element predicates, explicit null
ordering, and explicit errors for the constructs waiting on path semantics, the budget,
composition, and value work. It also builds the conformance corpus and its runner, so every later
query change is verified against the same contract, and closes the evidence debt the archived
`graph-examples` change left in its tests and README.

## What Changes

- **Canonical clause spellings, with the compatibility aliases the profile already commits to**:
  `INSERT` (with `CREATE` for data patterns only), `FOR` (with `UNWIND`), `FILTER` (with a
  stage-level `WHERE`), `OFFSET` (with `SKIP`), `RETURN ALL`, and `RETURN *`. `FOR` ships without
  `WITH ORDINALITY`/`WITH OFFSET`; ordinality stays gated, and `RETURN NO BINDINGS` stays gated
  until its result shape is defined.
- **GQL pattern directions**: `->`, `<-`, `-`, and `~` become the canonical arrows; `-->` and
  `<--` remain aliases. **BREAKING** `--` becomes a line comment, and the undirected `--` alias is
  removed in favor of `-`. A `--` that follows a node or relationship pattern is an explicit
  error rather than a silent truncation of the statement.
- **Label expressions**: `&` conjunction, `|` disjunction, `!` negation, and `%` wildcard for
  node and relationship labels. `IS` is accepted as the explicit label form the profile already
  lists; the profile's current ranking of `:` first is preserved, and reversing it is a separate
  profile decision.
- **Inline element predicates**: `WHERE` inside a node or relationship pattern.
- **Explicit ordering**: `NULLS FIRST` and `NULLS LAST` on each sort key, keeping the current
  default of nulls last ascending and first descending.
- **Explicit delete form**: `NODETACH DELETE` alongside `DELETE` and `DETACH DELETE`, with the
  non-detaching default stated in one place.
- **Transition errors**: a construct the profile lists but this release cannot execute
  (`{n,m}`, the path modes, `<~`/`~>`/`<->`, ordinality, `RETURN NO BINDINGS`, `LET`, `NEXT`,
  `GROUP BY`) fails with an error that names the construct and the follow-up change, instead of a
  generic unexpected-token error. `{n,m}` stays gated until `add-gql-path-semantics`; this change
  parses it only far enough to reject it precisely. Constructs the profile does not list (`CASE`,
  map literals, index access, subqueries) stay out of profile and keep their existing explicit
  rejection.
- **Conformance corpus and runner**: a data-driven case format with small named fixtures, a
  runner wired into the test suite and CI, and matrix rows flipped from `gated` to `supported`
  only where a passing case exists.
- **Tour migration**: `examples/tours/01-match.gql` and `02-write.gql` move to canonical
  spellings and the catalog updates; tours 03 and 04 stay with the changes that own them.
- **Folded maintenance**: prove the archived `graph-examples` determinism scenario across
  processes and hash seeds, reject anonymous `->` in the tour guard, parse the tour catalog rows
  for tier and migration owner instead of matching substrings, and correct the two false
  statements in `examples/README.md`. These implement already-archived requirements; no
  `graph-examples` delta is needed.
- **Out of scope**: executable `{n,m}`, path modes and the budget, `LET`/`NEXT`/`GROUP BY`, value
  features (`CASE`, map literals, list access, `UNION`, `EXISTS`, path functions), procedures,
  sessions, catalog statements, and temporal values.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: clause spellings and aliases, pattern direction grammar, label
  expressions, inline element predicates, null ordering, the explicit non-detaching delete form,
  and transition errors for gated constructs.

The `gql-profile` requirements do not change; the change-control requirement obliges this change
to update the profile page, its matrix, and the corpus in the same change. The folded maintenance
items implement already-archived `graph-examples` requirements, so that capability needs no delta.

## Impact

- Frontend: `engine/query/tokens.py`, `lexer.py`, `parser.py`, `ast.py`, `semantic.py`, `plan.py`,
  `compiler.py`, `executor.py`; `engine/query/mutation.py` for `NODETACH DELETE`.
- Tests: a new corpus runner and fixtures; updates to the query suites; `tests/test_gql_profile.py`
  gains matrix and corpus consistency checks; `tests/test_examples.py` guard, tier, and
  determinism tests.
- Documentation: `docs/reference/query-language.md` (grammar and semantics),
  `docs/reference/gql-profile.md` (current-status banner and matrix), `docs/guides/querying.md`,
  `docs/guides/shell.md`, `docs/guides/examples.md`, `README.md`, and
  `docs/getting-started/quickstart.md`.
- Examples: tours 01 and 02 and their catalog.
- Changelog: `Unreleased` entries under `Changed` and `Removed`, including the `--` break.
- No public Python API, storage layout, snapshot format, or CLI change.
