# Proposal: add GQL match modes

## Why

The profile's `DIFFERENT EDGES` and `REPEATABLE ELEMENTS` rows are gated, and the engine has no
way to say whether the same relationship may satisfy two positions in one match. Path modes only
constrain repetition inside a single path, so a clause with several patterns can silently bind one
relationship twice. Match modes are the missing clause-level rule, and the path-semantics matrix
already fixes how they combine with path modes.

## What Changes

- Add `MATCH DIFFERENT EDGES` and `MATCH REPEATABLE ELEMENTS`, for `MATCH` and `OPTIONAL MATCH`.
- Make `REPEATABLE ELEMENTS` the default so existing queries keep their results.
- Enforce `DIFFERENT EDGES` across every path and every repetition of one clause: a relationship
  binds at most once, while nodes may repeat.
- Combine match modes with path modes by intersection: an extension is accepted only when both
  rules allow it. `TRAIL` and `DIFFERENT EDGES` agree inside a path; `WALK` with `DIFFERENT EDGES`
  forbids edge reuse even in a walk.
- Scope the match mode to its clause. A relationship bound by an earlier `MATCH` stage may be bound
  again in a later stage.
- Implement the fixed-pattern case in the SQL compiler with cross-pattern inequality predicates,
  and the quantified case in `PatternEngine` with a clause-wide used-edge set.
- Reserve `DIFFERENT`, `EDGES`, `REPEATABLE`, and `ELEMENTS` as keywords. Existing variables and
  aliases using those spellings must be backtick-quoted.
- Flip the `DIFFERENT EDGES` and `REPEATABLE ELEMENTS` rows to `supported`, add conformance cases,
  and update the profile, query-language reference, grammar summary, querying guide, tours, and
  changelog.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-query-language`: adds the match-mode vocabulary, its default and scope, its intersection
  with path modes, and its behavior for fixed, quantified, optional, and multi-pattern matches.

## Impact

- Query frontend: `tokens.py` (four keywords), `ast.py` (`MatchMode` and the clause field),
  `parser.py` (match-mode position), `semantic.py` (clause propagation and variable kinds),
  `plan.py` (plan detail).
- Pattern matching: `compiler.py` (cross-pattern edge inequalities for fixed patterns) and
  `pattern.py` (clause-wide used-edge set for quantified patterns).
- Execution: `executor.py` passes the clause mode to the selected matcher and keeps optional-match
  null detection unchanged.
- Compatibility: **BREAKING** for the four newly reserved words. No working query changes unless it
  uses one of those spellings as a name. Default results are unchanged because `REPEATABLE
  ELEMENTS` is the default.
- Documentation: `docs/reference/gql-profile.md`, `docs/reference/query-language.md` (including the
  grammar summary), `docs/guides/querying.md`, `examples/tours/04-paths.gql`, and `CHANGELOG.md`.
- Tests: lexer, parser, semantic, compiler SQL, pattern engine, optional match, conformance,
  profile consistency, and TRON-themed parallel-relationship, cycle, diamond, and self-loop cases.
- Out of scope: new path modes, Cypher uniqueness rules, non-local element predicates, and
  path-pattern union.
