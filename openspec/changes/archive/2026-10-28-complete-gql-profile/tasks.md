# Tasks

## 1. Statement-level rejection

- [x] 1.1 Add contextual statement-position detection for `SELECT`, in-language transactions
  (`START`, `COMMIT`, `ROLLBACK`), temporal literals (`DATE`, `TIME`, `TIMESTAMP`, `DURATION`
  followed by a string), and catalog statements including `DROP GRAPH`, matching token text
  instead of adding `Keyword` members. Verify focused parser tests assert a positioned
  `QuerySemanticError` naming each construct and its alternative or reason.
- [x] 1.2 Split `CALL { ... }` from procedure calls so a procedure call names procedures and no
  procedure catalog, while the subquery form points to `EXISTS { ... }`, `COUNT { ... }`, or
  separate statements. Verify one focused test per form, including the message fragment.
- [x] 1.3 Standardize every recognized boundary message on `<construct> is not supported:
  <alternative or reason>` and replace the current "catalog statements are out of profile"
  message. Verify a focused test asserts the prefix for each construct in scope.
- [x] 1.4 Update the unsupported-constructs section of `docs/reference/query-language.md` with
  the recognized versus unrecognized rule and the new messages, and add the changelog entry under
  `[Unreleased]`. Verify `hatch run docs:build` passes.

## 2. Expression and write rejection

- [x] 2.1 Add `=~` to the lexer operator table before `=`. Verify tests cover `=~`, `=`, `~`,
  `<~`, and `~>` and that regex predicates raise a semantic error naming `STARTS WITH`,
  `ENDS WITH`, and `CONTAINS`.
- [x] 2.2 Reject `exists(n.prop)` in function-call position with a message pointing to
  `n.prop IS NOT NULL`. Verify a focused test asserts the semantic error and that `IS NOT NULL`
  still works.
- [x] 2.3 Reject `shortestPath()` and `allShortestPaths()` with a message pointing to the
  path-search prefixes. Verify a focused test asserts the semantic error.
- [x] 2.4 Reject whole-map assignment in the `SET` clause when the target is followed by `=` or
  `+=`, pointing to individual property assignment. Verify a focused test asserts the semantic
  error for both forms.
- [x] 2.5 Update the unsupported-constructs section of `docs/reference/query-language.md` for
  the expression and write boundaries, and extend the changelog entry. Verify
  `hatch run docs:build` passes.

## 3. No new reserved words

- [x] 3.1 Add regression tests that use `date`, `start`, `drop`, `select`, and the rejected
  function names as variables, aliases, labels, and property keys in supported statements.
  Verify the tests pass and every identifier stays usable without backticks.
- [x] 3.2 Verify `tests/engine/query/test_lexer.py` and the parser suite have no new failures and
  that no `Keyword` member was added for an out-of-profile word. Run `hatch test tests/engine/query`.

## 4. Rejection corpus

- [x] 4.1 Extend the corpus runner so a `rejection` case must expect an error and a message
  fragment matching the profile's `<construct> is not supported:` pattern; fail when a rejection
  case returns rows. Verify focused runner tests cover both the passing and failing shapes.
- [x] 4.2 Add `rejection` cases for the statement-level rows: `CALL { ... }`, procedure calls,
  `SELECT`, in-language transactions, temporal literals, and catalog statements. Verify
  `hatch test tests/test_conformance.py` runs every case and the new cases fail if the rejection
  is removed.
- [x] 4.3 Add `rejection` cases for the expression and write rows: `exists(n.prop)`, regex
  predicates, `shortestPath()`/`allShortestPaths()`, whole-map assignment, and the remaining
  Cypher-only forms. Verify the corpus passes with TRON-themed fixtures.
- [x] 4.4 Add a focused test that a rejected write leaves the graph unchanged, and surface tests
  for the non-query rows: servers and drivers, clustering/authentication/multi-tenancy,
  multi-graph storage, and graph-algorithm APIs. Verify each asserted capability is absent from
  the public surface.
- [x] 4.5 Update the corpus contract in `docs/reference/gql-profile.md` with the `rejection` tag
  and expected-error shape. Verify the documentation example matches an actual case.

## 5. Profile evidence and gate checks

- [x] 5.1 Replace the matrix `Follow-up` and `Corpus` columns with one `Evidence` column and fill
  every supported row with its corpus case names. Verify every supported row still has at least
  one case and the existing coverage test passes.
- [x] 5.2 Fill the evidence for every out-of-profile row as `rejection:<case>`, `test:<Class>`
  `<method>`, or `rejected forms`, and mark each row as a recognized boundary or unrecognized
  form. Verify a reader can resolve every cell to a case, a test, or the rejected-forms table.
- [x] 5.3 Reconcile the construct inventory with the matrix: one owner per entry, matching status
  for supported and out-of-profile rows, and no duplicate catalog entry. Verify no inventory entry
  is orphaned.
- [x] 5.4 Add the gate checks to `tests/test_gql_profile.py`: no gated or deferred rows, evidence
  present and resolvable, rejection coverage for every out-of-profile row, inventory status equals
  matrix status, rejection cases name out-of-profile rows, and no gated heading or target-tense
  wording in the query-language reference. Verify each check fails when its condition is
  deliberately broken.
- [x] 5.5 Update the release-gate, matrix, and evidence prose in
  `docs/reference/gql-profile.md` so each gate item names its automated check. Verify
  `hatch test tests/test_gql_profile.py` and `hatch run docs:build` pass.

## 6. Documentation sweep

- [x] 6.1 Remove the `Gated for 1.0` section and the target-tense gated wording from
  `docs/reference/gql-profile.md`, keeping the four-status vocabulary and stating that no row is
  gated. Verify no "when they land", "once ... land", or "gated" target wording remains.
- [x] 6.2 Replace the `Gated constructs` section and stale closing paragraph in
  `docs/reference/query-language.md` with a present-tense boundary statement. Verify the
  reference contains no `gated` heading.
- [x] 6.3 Audit the guides, examples, and tours for a construct described as gated or planned and
  correct each occurrence. Verify `hatch run docs:build` passes with warnings as errors.
- [x] 6.4 Finalize the changelog entry under `[Unreleased]` so it covers the clearer rejection
  messages and the frozen 1.0 boundary in user-facing terms. Verify the entry omits internal names,
  paths, and test details.

## 7. Integration verification

- [x] 7.1 Run `hatch check --fix` and verify Ruff and Pyrefly report no errors.
- [x] 7.2 Run `hatch test` and verify the full suite passes with coverage at least 80%.
- [x] 7.3 Run `hatch run docs:build` and verify it passes with warnings treated as errors.
- [x] 7.4 Run `openspec validate complete-gql-profile --strict` and verify the change validates.
- [x] 7.5 Re-run the out-of-profile probe from the audit against every row and verify each
  produces the documented error class and message fragment.

## Workflow follow-up

- Sync the delta specs into the main specs.
- Archive the change after review.
- Create a Git commit after the successful archive, per `AGENTS.md`.
