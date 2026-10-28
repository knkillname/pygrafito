# Proposal: add GQL grouped quantified paths

## Why

Grouped quantified path patterns are the last gated path-engine row. They let a query repeat a
whole path segment, which is what route, transfer, and supply-chain questions actually need. The
engine can repeat a single relationship, but it cannot repeat a two- or three-hop shape, and the
parser has no path-term juxtaposition. The unbounded walker, the match mode, and the path-search
evaluator are prerequisites and land first, so the remaining work is isolated to the pattern
frontend and walker.

## What Changes

- Add juxtaposed path terms. A term is a node pattern followed by relationship-node pairs, or a
  parenthesized path pattern followed by a quantifier. Adjacent terms share their boundary node.
- Add group quantifiers `{n}`, `{m,n}`, `{,n}`, `{m,}`, `*`, and `+`. The legacy `*n..m` spelling is
  rejected on a group.
- Allow an optional path variable and an optional inner path mode inside a group. The outer path
  mode applies to the whole path; the inner mode applies to the group; both are enforced and the
  stricter wins.
- Bind variables first introduced inside a group as ordered lists (group variables). A variable
  bound before the group acts as an equality constraint. Nested groups flatten their lists in
  traversal order.
- Allow zero iterations when the rest of the path supplies at least one relationship; group
  variables then bind empty lists. Reject a lone zero-lower-bound group and any group that cannot
  make progress.
- Keep whole-path search, match modes, path variables, path functions, and the budget working
  across grouped iterations. A search prefix inside a group is rejected.
- Represent paths as a sequence of terms in the AST, route grouped patterns through the pattern
  engine, and reuse the existing walk, match-mode, search, and demand machinery.
- Flip the `Grouped quantified paths` row to `supported`, add conformance cases, and update the
  profile, query-language reference, grammar summary, querying guide, tours, performance notes,
  and changelog.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: adds path-term juxtaposition, grouped path syntax and quantifiers, group
  variable bindings and scopes, inner path modes, zero-iteration and progress rules, and grouped
  interaction with match modes, path search, path variables, and the budget.

## Impact

- Query frontend: `ast.py` (`PathTerm`, `GroupedPath`, path pattern terms), `parser.py` (term
  juxtaposition, group head, quantifier), `semantic.py` (group scopes, list variable kinds,
  restrictions), `plan.py` (group detail).
- Pattern matching: `pattern.py` (group frames in the walk state, list accumulation, nested groups,
  zero iterations, progress enforcement), `compiler.py` (route grouped patterns to the pattern
  engine instead of SQL).
- Execution: `executor.py` passes grouped results through the demand pipeline and explain.
- Compatibility: no existing syntax changes meaning. `((a)-[r]->(b)){2}` was a syntax error
  before; it becomes valid. Variables inside a group are new names only.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md` (including
  grammar), `docs/guides/querying.md`, `docs/reference/performance.md`,
  `examples/tours/04-paths.gql`, `README.md`, and `CHANGELOG.md`.
- Tests: parser, semantic, pattern engine, nested and zero-iteration groups, match-mode and
  search interaction, budget, explain, conformance, profile consistency, and TRON-themed diamond,
  directed-cycle, parallel-relationship, and self-loop fixtures.
- Out of scope: path-pattern union, questioned paths, path predicates, `KEEP`, graph types,
  procedures, and any non-GQL grouping syntax.
