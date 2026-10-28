# Design: GQL match modes

## Context

See `proposal.md` — Why. Relevant current state:

- `Match` in `ast.py` carries `mode: PathMode | None`, which is the clause's path mode. There is no
  clause-level match-mode field.
- `SemanticAnalyzer._resolve_path_modes` replaces each pattern's mode with the resolved path mode
  and builds `MatchStage` or `OptionalMatchStage`.
- A stage whose patterns contain no quantified relationship compiles to SQL through
  `Compiler`, which already appends per-path uniqueness predicates in `_add_mode_predicates`.
- A stage with any quantified relationship uses `PatternEngine`, which walks with a `WalkState`
  holding `used` (relationship ids) and `visited` (node ids). `PatternEngine.match` iterates the
  clause patterns sequentially and merges their bindings.
- `PatternEngine.match` returns a list, so every matched row is complete before the next pattern
  starts.
- The profile's two match-mode rows are gated and name this change.

## Goals / Non-Goals

**Goals:**

- Add the clause-level mode without disturbing path-mode resolution or the default results.
- Make fixed and quantified stages enforce exactly the same rule.
- Keep indexed SQL matching for fully fixed clauses.
- Make the rule visible in explain output and documentation.

**Non-Goals:**

- No `DIFFERENT NODES`, `DIFFERENT RELATIONSHIPS` alias, or Cypher-specific uniqueness extension.
- No match mode on write clauses or inside subqueries beyond the subquery's own `MATCH`.
- No change to `REPEATABLE ELEMENTS` behavior; it is the current behavior.

## Decisions

### A separate `MatchMode` enum on the clause

Add:

```text
MatchMode.REPEATABLE_ELEMENTS (default)
MatchMode.DIFFERENT_EDGES
```

`Match` gains `match_mode: MatchMode = MatchMode.REPEATABLE_ELEMENTS`, and
`MatchStage`/`OptionalMatchStage` carry it. The existing `Match.mode` remains the clause path mode.
Keeping them separate avoids overloading one field with two orthogonal rules and makes the
intersection explicit at each matcher.

Alternative considered: reuse `PathMode.TRAIL` for `DIFFERENT EDGES`. It is wrong at clause scope:
`TRAIL` resets per path and `DIFFERENT EDGES` spans all paths.

### Parser position and keywords

The grammar becomes:

```text
match-clause = [ "OPTIONAL" ] "MATCH" [ match-mode ] [ path-mode ] path-pattern
               { "," [ path-mode ] path-pattern } [ where-clause ]
match-mode   = "DIFFERENT" "EDGES" | "REPEATABLE" "ELEMENTS"
```

- `DIFFERENT`, `EDGES`, `REPEATABLE`, and `ELEMENTS` become reserved keywords.
- The mode is read after `MATCH` and before any path mode. `MATCH DIFFERENT EDGES WALK ...` and
  `MATCH WALK ...` are both accepted.
- A per-path path mode is still accepted after each comma.
- `INSERT`, `CREATE`, and `MERGE` parse their patterns through the existing clause-pattern path and
  never read a match mode. The reserved words produce a positioned syntax error there.
- The parser reports a missing `EDGES`/`ELEMENTS` with the position of the offending token.

Alternative considered: accept `DIFFERENT RELATIONSHIPS` as an alias. The profile does not list it,
and adding an alias needs its own equivalence case. Rejected for 1.0.

### Fixed patterns: cross-pattern inequalities in SQL

`Compiler` records every relationship table alias in clause order while it compiles the patterns.
After all patterns are compiled and before the SQL is rendered, a `DIFFERENT EDGES` clause appends
pairwise `left.id <> right.id` predicates for distinct aliases. A repeated variable reuses one
alias and is therefore skipped, as the same binding is intentional. Existing per-path predicates
from `TRAIL`, `SIMPLE`, and `ACYCLIC` stay; duplicated pairs are harmless but the helper deduplicates
them to keep SQL short.

Bound relationship variables from earlier stages are not part of the clause's alias list, so they
can be rebound. This matches the profile's clause scope.

Alternative considered: route every `DIFFERENT EDGES` clause through `PatternEngine`. It would
enforce the rule in one place but lose the indexed node and property pushdown for ordinary fixed
patterns. Rejected.

### Quantified and mixed stages: one used-edge set per clause

`PatternEngine.match` becomes a wrapper around a usage-aware generator:

- `_match_pattern_with_usage(pattern, base, used)` yields `(binding, used_after)`.
- The first pattern starts with an empty set.
- Each subsequent pattern starts from the union produced by the previous one.
- `_extend_memory` checks the path mode first, then rejects an edge already in the clause set when
  the match mode is `DIFFERENT EDGES`.
- `_finish` and fixed-position completion add their traversed edge ids to the set.
- `REPEATABLE ELEMENTS` keeps an empty clause set; the existing `TRAIL` set remains per path.

Mixed clauses already route the whole stage to `PatternEngine` when any pattern is quantified, so
there is exactly one matcher per stage.

Alternative considered: store the used set in the binding dictionary under a private key. It would
leak into projection and `RETURN *`. Rejected. An explicit return pair keeps the binding clean.

### Budget and counts

A candidate edge is counted as an expansion before the match-mode check, because the engine read
it. Rejected candidates do not add rows. The rule never adds work beyond enumerating the same
candidate edges.

### Explain output

For a `DIFFERENT EDGES` stage, explain starts the stage with `MATCH DIFFERENT EDGES` followed by
the existing operator lines. `REPEATABLE ELEMENTS` is the default and is omitted from explain, like
`WALK` is.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| SQL compiler and `PatternEngine` disagree | A shared semantic fixture runs the same clause in fixed and quantified forms and asserts equal row counts and bindings |
| Existing queries change because the default changes | The default is `REPEATABLE ELEMENTS`, which is the current behavior; regression tests pin it |
| Reserved words break variables named `edges` or `elements` | Document the backtick migration in the reference and changelog; add a lexer test |
| `DIFFERENT EDGES` plus `WALK` surprises users | The profile states that the two rules intersect; the reference includes a worked cycle example |
| Optional match becomes expensive | The rule only filters candidates; budget behavior is unchanged |
| Cross-pattern SQL predicates hurt an index plan | Predicates compare relationship primary keys; run the existing query benchmarks and compare |

## Migration Plan

1. Land lexer, AST, parser, and semantic changes with regression tests for the default.
2. Land the SQL compiler rule and the pattern-engine rule behind the same fixtures.
3. Update explain output, profile rows, reference, guide, tour, and changelog.
4. Rollback is a code revert; no data or format changes.
