# Proposal: add GQL path search

## Why

The profile's path-search rows are gated. Today a caller who wants one route, a shortest route, or
the two shortest routes must enumerate every match and filter in application code. That is
impossible for an open-ended walk, and it hides a semantic decision — how ties, duplicates, and
endpoint pairs are handled — behind ad hoc code. Path search makes the selection part of the
query, uses the unbounded engine, and builds on the clause-level match mode.

## What Changes

- Add the path-search prefixes `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k`.
- Place a prefix at the path head, after the optional path variable and before the path mode:
  `MATCH p = ANY SHORTEST WALK (a)-[:TRUSTS]->{1,}(b) RETURN p`.
- Partition matches by the path's first and last node within each input row, then select per
  partition:
  - `ANY` returns one path.
  - `ANY SHORTEST` returns one path of minimum length.
  - `ALL SHORTEST` returns every path of minimum length.
  - `SHORTEST k` returns up to `k` paths in increasing length; `k` is a non-negative integer
    literal and `k = 0` selects no path.
- Apply a deterministic tie-break: shorter first, then the lexicographically smaller
  orientation-aware relationship sequence, then the smaller node sequence.
- Deduplicate by path identity: the same node sequence and orientation-aware relationship
  sequence is one path, while parallel relationships are different paths.
- Evaluate search in nondecreasing length order with a bounded frontier, so `ANY SHORTEST` and
  `ALL SHORTEST` stop at the shortest layer per partition and `SHORTEST k` stops at its k-th
  path. A final `LIMIT` still stops the whole statement early.
- Combine search with path modes and `DIFFERENT EDGES`: the search evaluates only paths that the
  effective mode and match mode accept.
- Reserve `ANY` and `SHORTEST` as keywords.
- Flip the `Path search prefixes`, `ANY`, `ANY SHORTEST`, `ALL SHORTEST`, and `SHORTEST k` rows to
  `supported`, add conformance cases, and update the profile, query-language reference, grammar
  summary, querying guide, performance notes, path tour, README, and changelog.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: adds the path-search prefix syntax, per-endpoint selection, duplicate
  and tie-breaking rules, deterministic ordering, and termination and budget behavior for bounded
  and open patterns.

## Impact

- Query frontend: `tokens.py` (two keywords), `ast.py` (`PathSearch` and the pattern field),
  `parser.py` (prefix position), `semantic.py` (one prefix, non-negative integer `k`, path-variable
  interaction), `plan.py` (search detail).
- Pattern matching: `pattern.py` (length-ordered search evaluator over the live frontier and the
  clause-wide match-mode state) and `compiler.py` (selection after the fixed-pattern matcher).
- Execution: `executor.py` passes search rows into the demand pipeline and explain output.
- Compatibility: **BREAKING** for variables and aliases named `any` or `shortest`, which now need
  backticks. Queries without a prefix keep returning every match, so results do not change.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md` (including
  grammar), `docs/guides/querying.md`, `docs/reference/performance.md`,
  `examples/tours/04-paths.gql`, `README.md`, and `CHANGELOG.md`.
- Tests: lexer, parser, semantic, pattern search, fixed-pattern selection, open-walk selection,
  match-mode interaction, budget, explain, conformance, profile consistency, and TRON-themed
  diamond, directed-cycle, parallel-relationship, self-loop, and unreachable fixtures.
- Out of scope: the `ALL` search prefix, path-pattern union, questioned paths, weighted search,
  `shortestPath()` and `allShortestPaths()` aliases, graph-algorithms API, and grouped path patterns
  (which land in the next change and must then compose with search).
