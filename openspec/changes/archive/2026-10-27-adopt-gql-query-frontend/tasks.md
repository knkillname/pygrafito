# Tasks

## 1. Conformance corpus foundation

- [x] 1.1 Add `tests/conformance/cases.json` with the named fixture library required by the design: `tron-cycle` (directed cycle), `tron-diamond`, `tron-parallel` (parallel relationships), `tron-self-loop`, `tron-labels` (multi-label nodes), and `tron-undirected`. Verify the document parses and every fixture declares only handles, labels, properties, and directed flags.
- [x] 1.2 Add a class-based corpus runner in `tests/conformance/runner.py` with `tests/conformance/__init__.py`, and `tests/test_conformance.py` with seed cases for a match, a filter, and a write. Verify the suite passes, and that a deliberately wrong expectation fails with the case name and the feature id.
- [x] 1.3 Extend `tests/test_gql_profile.py` with the matrix/corpus consistency checks: every `supported` matrix row has at least one case, no gated row has a case tagged `supported`, and every case feature exists in the matrix. Verify the test passes against the current gated matrix.
- [x] 1.4 Document the corpus authoring rules and the runner command in the conformance-corpus section of `docs/reference/gql-profile.md`. Verify `hatch run docs:build` passes with no warnings.

## 2. Vocabulary and gated diagnostics

- [x] 2.1 Extend `Keyword` in `src/pygrafito/engine/query/tokens.py` with `INSERT`, `FOR`, `FILTER`, `OFFSET`, `NODETACH`, `NULLS`, `FIRST`, `LAST`, `ALL`, `TRAIL`, `WALK`, `SIMPLE`, `ACYCLIC`, `LET`, `NEXT`, `GROUP`, and `ORDINALITY`. Verify lexer tests tokenize each as a keyword and that identifiers such as `grouping` still lex as identifiers.
- [x] 2.2 Add the gated-construct table and a positioned `QuerySemanticError` path consulted by the parser and semantic analyzer, covering `{n,m}`, `TRAIL`/`WALK`/`SIMPLE`/`ACYCLIC`, `<~`/`~>`/`<->`, `WITH ORDINALITY`/`WITH OFFSET`, `RETURN NO BINDINGS`, `LET`, `NEXT`, and `GROUP BY`. Verify each construct raises an error naming the construct and the follow-up change, and that a statement combining a gated construct with a write changes no data.
- [x] 2.3 Document the gated-construct error shape in `docs/reference/query-language.md` and add the `Unreleased` `Changed` entry. Verify `hatch run docs:build` passes.

## 3. Iteration, insertion, and filtering

- [x] 3.1 Make `INSERT` the canonical create clause and keep `CREATE` as the data-pattern alias; update write classification, parsing, and semantic analysis. Verify corpus cases for `INSERT`, the `CREATE` equivalence, `INSERT ... RETURN`, and the `INSERT GRAPH` rejection.
- [x] 3.2 Make `FOR <expression> IN <list>` canonical and keep `UNWIND ... AS ...` as the alias, including `FOR` as a lone row source. Verify corpus cases for both spellings, a null list, an empty list, and the gated `WITH ORDINALITY` form.
- [x] 3.3 Add the `FILTER` and `FILTER WHERE` stage with a `FilterStage`, and lower `WHERE` after `WITH` to the same stage without changing `OPTIONAL MATCH ... WHERE`. Verify corpus cases for filter after match, filter after with, no new binding, and the optional-match scope.
- [x] 3.4 Update the grammar and clause sections of `docs/reference/query-language.md`, the examples in `docs/guides/querying.md`, and the `Unreleased` entries for `INSERT`, `FOR`, and `FILTER`. Verify every changed Python fence still runs and `hatch run docs:build` passes.

## 4. Pattern grammar

- [x] 4.1 Rewrite relationship parsing to the opening-dash, detail, direction-suffix shape for `->`, `<-`, `-`, and `~`, add the `undirected_only` pattern flag, and keep `-->`/`<--` as aliases. Verify the traversal diamond, cycle, parallel, self-loop, and undirected fixtures stay green and add corpus cases for each direction form.
- [x] 4.2 Add `--` line comments with maximal-munch `-->`/`<--` arrows and reject a `--` that abuts a closing `)` or `]` with a positioned syntax error. Verify corpus cases for a dash comment, a trailing comment after whitespace, and the `(a)--(b)` rejection.
- [x] 4.3 Add the label-expression tree for `&`, `|`, `!`, and `%`, parse the `IS` form to the same tree, and compile it to label-table subqueries. Verify corpus cases for conjunction, disjunction, negation, wildcard, and the `IS` equivalence, plus the index-transparency suite.
- [x] 4.4 Add inline element `WHERE` predicates to node and relationship patterns, scoped to the element and applied per hop. Verify corpus cases for a node predicate, a relationship predicate, and the wrong-scope rejection.
- [x] 4.5 Update the pattern and grammar sections of `docs/reference/query-language.md` for the new arrows, comments, label expressions, and inline predicates, and add the `Unreleased` `Changed`/`Removed` entries for the `--` break. Verify `hatch run docs:build` passes.

## 5. Projection, ordering, and deletion

- [x] 5.1 Add `OFFSET` as the canonical offset spelling in `RETURN` and `WITH`, keeping `SKIP` as the alias. Verify corpus cases for both spellings and for parameterized offsets.
- [x] 5.2 Add `RETURN ALL` and `RETURN *`, expanding `*` at semantic analysis into the in-scope variables in introduction order, and confirm prepared columns are available before execution. Verify corpus cases for `ALL`, `*`, and duplicate-name rejection.
- [x] 5.3 Add `NULLS FIRST` and `NULLS LAST` per sort key, keeping the current defaults. Verify corpus cases for both keywords against ascending and descending order.
- [x] 5.4 Add `NODETACH DELETE` as the explicit non-detaching form. Verify corpus cases for `NODETACH DELETE`, `DELETE`, and the connected-node rejection.
- [x] 5.5 Confirm `RETURN NO BINDINGS` reaches the gated table and its error names the follow-up. Verify a corpus case for the rejection.
- [x] 5.6 Update the ordering, projection, and delete sections of `docs/reference/query-language.md` and the pagination guidance in `docs/guides/querying.md`, and add the `Unreleased` entries. Verify `hatch run docs:build` passes.

## 6. Matrix, tours, and profile

- [x] 6.1 Flip the conformance matrix rows whose cases pass, and leave `{n,m}`, the path modes, `<~`/`~>`/`<->`, ordinality, `RETURN NO BINDINGS`, `LET`, `NEXT`, `GROUP BY`, and the deferred path features gated. Verify the matrix consistency test passes and every `supported` row names its case.
- [x] 6.2 Update the current-status table and the banner in `docs/reference/gql-profile.md` so the page describes the implemented surface and still marks the gated constructs. Verify `hatch run docs:build` passes and the consistency test passes.
- [x] 6.3 Migrate `examples/tours/01-match.gql` and `examples/tours/02-write.gql` to canonical spellings, including `//`-only comments and the new arrows, and update `examples/tours/README.md` with the tier and migrating-change columns. Verify `hatch test tests/test_examples.py` runs every tour.
- [x] 6.4 Re-aim `tests/test_examples.py::test_target_only_syntax_is_absent` at the new target-only set (`LET`, `NEXT`, `GROUP BY`, `{n,m}`, path modes, `RETURN NO BINDINGS`, `<~`, `~>`, `<->`) and drop anonymous `->` from the forbidden list. Verify the migrated tours pass and a deliberately added `{1,3}` in a scratch tour fails.
- [x] 6.5 Update `docs/guides/examples.md`, `docs/guides/shell.md`, `README.md`, and `docs/getting-started/quickstart.md` to canonical spellings wherever the release now supports them, and add any remaining `Unreleased` entries. Verify `hatch test tests/test_docs_examples.py tests/test_readme.py` and `hatch run docs:build` pass.

## 7. Folded maintenance

- [x] 7.1 Replace the same-process determinism test in `tests/test_examples.py` with a subprocess build that sets conflicting `PYTHONHASHSEED` values and compares both snapshots to each other and to the committed `examples/data/grid.jsonl`. Verify the test passes and fails when the comparison target is changed.
- [x] 7.2 Replace the substring tier test with a parser over the `examples/tours/README.md` table that requires one row per tour, a tier cell, a profile section, and a migrating-change name. Verify a scratch row with a missing migration owner fails.
- [x] 7.3 Correct `examples/README.md`: remove `VERSION_OF` from the identity vocabulary and scope the `sources` sentence to non-film entities. Verify no remaining sentence names a relationship label or property the data does not have.

## 8. Integration checks

- [x] 8.1 Run `hatch check --fix`, `hatch test`, `hatch run docs:build`, and `git diff --check`, and confirm coverage stays at or above 80% with no documentation warnings.
- [x] 8.2 Run the corpus, all four tours, and one shell session per changed construct (`INSERT`, `FOR`, `FILTER`, `OFFSET`, `RETURN *`, `NODETACH DELETE`, each arrow, a label expression, and a dash comment) from a clean shell, and confirm the results match the reference pages.
- [x] 8.3 Re-read `CHANGELOG.md` and confirm every user-visible change in this run has an `Unreleased` entry, including the `--` removal and the gated diagnostics.

## Workflow follow-up

- Archive the change after review, and confirm the archived profile matrix matches the durable
  `gql-profile` requirement set.
- Hand the tour 03 and tour 04 migrations to `add-gql-composition` and `add-gql-path-semantics`
  respectively; this change must not edit them.
