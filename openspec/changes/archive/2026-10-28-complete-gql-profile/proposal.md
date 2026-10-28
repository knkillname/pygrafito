# Proposal

## Why

The language surface is complete: the matrix has 60 supported rows and no `gated` or `deferred`
rows, and every supported row already has a conformance case. The 1.0 gate still fails on its
other half. The profile promises an explicit rejection for 19 out-of-profile constructs, but only
one row approximates that contract, the corpus has no rejection cases, and the query-language
reference still describes a gated surface that no longer exists. A 1.0 cannot claim a complete
profile while its boundary is untested and documented in the wrong tense.

## What Changes

- Define the out-of-profile rejection contract. A recognized out-of-profile construct raises a
  positioned `QuerySemanticError` naming the construct and the supported alternative, before any
  statement text executes. Text the parser cannot place remains a `QuerySyntaxError`.
- Recognize the query-shaped out-of-profile constructs without adding reserved keywords:
  `CALL { ... }` and procedure calls separately, whole-map assignment, `exists(n.prop)`, regex
  predicates, `shortestPath()`/`allShortestPaths()`, `SELECT`, in-language transactions, temporal
  literals, catalog statements including `DROP GRAPH`, and full-Cypher forms that have a named
  counterpart.
- Add `rejection`-tagged conformance cases for every out-of-profile row with query syntax, and
  focused surface tests for the capabilities that have no query syntax: servers and drivers,
  clustering/authentication/multi-tenancy, multi-graph storage, graph-algorithm APIs, vector
  search, and full-text search.
- Remove the stale gated vocabulary from the profile and the query-language reference: the
  "Gated for 1.0" section, the gated matrix guidance, the "Gated constructs" table, and wording
  such as "when they land" or "once open quantifiers land". Keep the four-status vocabulary but
  assert that no row is `gated` or `deferred`.
- Add automated release-gate checks: no `gated` or `deferred` rows, inventory status equals matrix
  status, every out-of-profile row has a rejection case or a surface test, and every supported row
  has a case.
- Reconcile the matrix, construct inventory, rejected-forms table, query-language reference, and
  tours so each construct has one status and one owner.
- Add the changelog entry and update the Sphinx documentation. No new language syntax is added.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gql-profile`: the release gate becomes automated and verifiable, the out-of-profile rows gain a
  tested rejection contract and corpus tag, and the profile stops presenting `gated` as a live
  status.
- `graph-query-language`: recognized out-of-profile constructs raise a positioned semantic error
  that names the construct and its alternative, while unrecognized text remains a syntax error,
  and no statement executes either way.

## Impact

- Query frontend: `src/pygrafito/engine/query/parser.py`, `semantic.py`, and `tokens.py` for
  contextual rejection paths and the `=~` operator token.
- Tests: `tests/conformance/cases.json`, `tests/conformance/runner.py`, `tests/test_gql_profile.py`,
  and focused parser and semantic tests.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md`, affected
  guides and tours, and `CHANGELOG.md`.
- No public API, storage schema, snapshot format, CLI, dependency, or reserved-keyword changes.
