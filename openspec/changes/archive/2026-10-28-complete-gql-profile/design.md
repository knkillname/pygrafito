# Design: complete the GQL profile

## Context

See `proposal.md` for motivation. The audit starts from these measured facts:

- The conformance matrix has 79 rows: 60 `supported`, 19 `out of profile`, no `gated` or
  `deferred`.
- The corpus has 152 cases, all `canonical`, `alias`, `compatibility`, or `extension`, and none
  tagged as a rejection.
- `tests/test_gql_profile.py` enforces matrix statuses, tier coverage, case-to-feature mapping,
  one case per supported row, and gated/deferred case rules. It does not check inventory status,
  the absence of gated rows, or out-of-profile rejection coverage.
- The profile and the query-language reference still contain gated sections and target-tense
  wording, even though no row is gated.
- Only `CREATE GRAPH` and `INSERT GRAPH` produce a boundary-like semantic error. `CALL` produces
  "subqueries are not supported" for both subqueries and procedures; `exists` produces "unknown
  function"; the remaining constructs fail as generic syntax errors.

Constraints that shape the approach: standard library only, one-way imports
(`model <- storage <- engine <- __init__`), no new reserved keywords in this release, and Sphinx
documentation updated with warnings as errors.

## Goals / Non-Goals

**Goals:**

- Give every out-of-profile row a single, tested rejection path.
- Make the release gate mechanically checkable from the profile tables and the corpus.
- Remove the gated surface from user-facing documentation without changing the four-status
  vocabulary.
- Keep the audit free of new language features.

**Non-Goals:**

- Adding syntax, semantics, or corpus coverage for supported features beyond the existing gate.
- Changing the Python API, storage format, CLI, or dependencies.
- Hardening work owned by `harden-for-1.0`, including the general error contract outside query
  boundaries.

## Decisions

### Two rejection classes, one per matrix row

Every out-of-profile row is classified as either a **recognized boundary** or an **unrecognized
form**. A recognized boundary is detected at a known position in the grammar and raises a
positioned `QuerySemanticError` with the message pattern
`<construct> is not supported: <alternative or reason>`. Unrecognized text is whatever does not
fit the grammar and is not one of those known positions; it keeps raising `QuerySyntaxError`.

The profile records the class per row in its evidence column. This preserves honest errors: a
typo or an unknown operator is not mislabeled as a deliberate profile boundary.

Alternative considered: make every out-of-profile row a semantic error. This would require
teaching the parser to recognize arbitrary Cypher forms and would blur the line between "not in
the profile" and "not parseable", which the spec already distinguishes.

### Contextual recognition, no new reserved keywords

Recognition happens where the construct can only appear, so no new `Keyword` member is added and
existing identifiers keep working.

| Construct | Detection point | Message alternative or reason |
| --- | --- | --- |
| `CALL { ... }` | Statement or clause position, `CALL` followed by `{` | Use `EXISTS { ... }`, `COUNT { ... }`, or separate statements |
| Procedure call `CALL name(...)` | Statement or clause position, `CALL` followed by an identifier | No procedure catalog exists |
| Whole-map assignment | `SET` target followed by `=` or `+=` | Assign or remove properties individually |
| `exists(n.prop)` | Function-call position, function name `exists` | Use `n.prop IS NOT NULL` |
| `shortestPath()`, `allShortestPaths()` | Function-call position | Use `ANY SHORTEST` or `SHORTEST k` |
| Regex predicate | `=~` token in an expression | Use `STARTS WITH`, `ENDS WITH`, or `CONTAINS` |
| `SELECT` | Statement position, identifier text `select` | Use `MATCH ... RETURN` |
| In-language transactions | Statement position, identifier text `start`, `commit`, or `rollback` | The Python API owns transaction boundaries |
| Temporal literals | Expression position, identifier `date`, `time`, `timestamp`, or `duration` followed by a string | Store an integer or string property |
| Catalog statements | Statement position, `create`, `insert`, or `drop` followed by `graph` | One embedded graph per handle |

Three implementation consequences follow:

1. `=~` is added to the lexer's operator table before `=`. It is punctuation, so it reserves no
   identifier; `~`, `<~`, and `~>` keep their edge-direction meaning.
2. Statement-position words are matched by token text, not by a `Keyword` member. The same words
   remain valid variables, aliases, labels, and property keys elsewhere.
3. Rejection is raised during parsing or semantic analysis, before planning or execution. A
   rejected write never opens its transaction, so atomicity follows from the existing pipeline.

Alternative considered: add `SELECT`, `START`, `DATE`, `DROP`, and function names to `Keyword`.
This would make each word globally reserved, force backticks on existing valid queries, and add a
fourth breaking reserved-word wave to the 1.0 cycle. Rejected.

### One evidence column replaces `Follow-up` and `Corpus`

With no gated rows, the `Follow-up` column is dead weight and `Corpus` duplicates the coverage
test. Both are replaced by a single `Evidence` column in the conformance matrix:

| Row kind | Evidence value |
| --- | --- |
| Supported | One or more corpus case names |
| Out-of-profile, recognized | `rejection:<case name>` |
| Out-of-profile, non-query capability | `test:<TestClass>::<test_method>` |
| Umbrella row such as full Cypher | `rejected forms` |
| Rejected form | The owning test in the rejected-forms table |

The inventory keeps a `Matrix row or rejected form` owner column. Its status must equal the
matrix row's status for every supported and out-of-profile entry; `rejected form` entries are
excluded from that equality and checked against the rejected-forms table instead.

### Rejection cases are first-class corpus cases

`cases.json` gains `rejection`-tagged cases with the existing `expect.error` shape
(`type` plus a message fragment). The runner validates that a `rejection` case expects an error
and that its fragment matches the profile's message pattern. Fixture and query fields stay the
same, so the corpus still exercises parsing, semantic analysis, and the public `Graph.query` entry
point end to end.

Write-shaped rejection cases run on a fresh in-memory graph like every other case. Because
rejection precedes execution, the asserted behavior is the error itself; one focused test asserts
that a rejected write leaves the graph unchanged.

### The gate becomes a test suite

`tests/test_gql_profile.py` gains checks that fail on drift:

1. No matrix row is `gated` or `deferred`.
2. Every matrix row has evidence, and supported-row evidence names at least one existing corpus
   case.
3. Every out-of-profile row's evidence resolves to a `rejection` case, a focused test that
   exists, or the rejected-forms group.
4. Inventory status equals matrix status for every supported and out-of-profile entry.
5. Every `rejection` case names a row whose status is `out of profile`.
6. The query-language reference contains no gated heading and no target-tense wording for a
   construct that is supported.

The focused-test evidence is resolved through a small registry in the test module so a renamed or
deleted test fails the check instead of silently passing.

### Documentation states the boundary in the present tense

`docs/reference/gql-profile.md` loses the `Gated for 1.0` section and the gated wording in its
legend and path-semantics intro. It keeps a short vocabulary definition and states that no row is
gated. `docs/reference/query-language.md` replaces its `Gated constructs` table with a statement
that nothing is gated and that unsupported forms are rejected as documented, and drops the stale
closing paragraph about remaining path constructs. Any guide or tour that calls a supported
feature "gated" or "planned" is corrected.

## Risks / Trade-offs

- **Message wording becomes a public contract** -> freeze the stable prefix
  `<construct> is not supported:` in the profile, and have corpus cases assert fragments rather
  than whole strings so article and punctuation edits do not break tests.
- **Contextual detection shadows identifiers** -> test `date`, `start`, `drop`, `select`, and the
  function names as variables, aliases, labels, and property keys in supported statements.
- **`=~` changes operator lexing** -> add the longest-match token before `=` and keep regression
  tests for `=`, `~`, `<~`, and `~>`.
- **Evidence drifts from reality** -> the consistency test resolves every evidence cell; an
  unknown case, test, or owner fails CI.
- **The audit turns into feature work** -> any missing supported construct becomes a separate
  change; this change may only add rows that reconcile existing behavior, not new syntax.
- **Overlap with hardening** -> this change owns query-boundary rejection only. The Python API
  error contract, deprecation policy, and format freeze remain in `harden-for-1.0`.

## Migration Plan

Valid statements are unaffected. Invalid statements may change from `QuerySyntaxError` to
`QuerySemanticError` with a clearer message; the profile documents this and the changelog records
it under `Changed`. No data migration, schema change, or API change is required. Rolling back
means reverting the parser and semantic changes; the profile and corpus changes are independent
and can remain.

## Open Questions

None. The Python support floor, result streaming, and migration mechanism remain `harden-for-1.0`
decisions and do not affect this design.
