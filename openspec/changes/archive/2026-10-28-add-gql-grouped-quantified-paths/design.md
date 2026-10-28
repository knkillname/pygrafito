# Design: grouped quantified path patterns

## Context

See `proposal.md` — Why. The current frontend and walker assume one linear shape:

- `PathPattern` holds flat `nodes` and `relationships` tuples and one path variable. The parser
  builds exactly one node followed by alternating relationship-node pairs.
- `SemanticAnalyzer._bind_pattern` walks those flat tuples and registers node, relationship, and
  relationship-list variables.
- `Compiler._compile_pattern` emits SQL for fixed patterns; `PatternEngine` walks the same flat
  tuples for quantified patterns.
- `WalkState` tracks a relationship position, the current node, hops inside one quantified segment,
  accumulated path nodes and relationships, and mode memory.
- The unbounded change adds a live frontier and a demand pipeline; the match-mode change adds a
  clause-wide used-edge set; the path-search change adds a length-ordered evaluator.

## Goals / Non-Goals

**Goals:**

- Add a compositional path-term structure without breaking simple paths.
- Parse and validate the GQL group syntax, including inner modes, group variables, and bounds.
- Reuse one walker for deep-first matching and length-ordered search.
- Keep group memory proportional to the selected paths and the iteration counters, not to the whole
  reachable graph.

**Non-Goals:**

- No path-pattern union, questioned paths, path predicates, or `KEEP`.
- No SQL compilation of grouped patterns; grouped patterns use the pattern engine.
- No new budget counter.
- No streaming result API.

## Decisions

### Path patterns become a sequence of terms

Add:

```text
SimplePathTerm(nodes, relationships)
GroupedPathTerm(pattern: PathPattern, quantifier: HopRange, variable: str | None, mode: PathMode | None)
PathPattern(variable, mode, search, terms: tuple[PathTerm, ...])
```

A simple path is a one-term pattern. Parsing keeps the current fast path for simple patterns by
building one `SimplePathTerm`; grouped syntax builds `GroupedPathTerm` nodes. The semantic
analyzer, compiler, walker, and search evaluator iterate terms. A `flatten()` helper returns the
flat nodes and relationships when the pattern has only simple terms, so explain and existing
simple-path tests keep their shape.

Alternative considered: keep flat `nodes`/`relationships` and add a parallel group list. It makes
every consumer responsible for reconciling two structures. Rejected.

### Unambiguous group detection without backtracking

A `(` starts a grouped term when the token after it is one of:

- `(` for a nested term.
- A path-mode keyword (`WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`).
- An identifier immediately followed by `=` for the group path variable.

Otherwise it starts a node pattern. A group is then parsed as:

```text
group = "(" [identifier "="] [path-mode] path-pattern ")" quantifier
```

and the closing `)` must be followed by `{...}`, `*`, or `+`. A parenthesized path without a
quantifier is a syntax error, and a node pattern followed by `{` is still a property map because
the group decision is made after the opening parenthesis.

Adjacent terms are parsed while the next token is `(`. The walker treats the boundary node of one
term as the first node of the next. A group path variable is optional; `(p = (a)-[r]->(b)){2}`
binds `p` to the two-iteration path.

Alternative considered: speculative parse with a checkpoint and backtrack. It handles edge cases
but complicates error positions. The lookahead rule covers every valid group spelling.

### Group scopes and variable kinds

- Variables first introduced in a group are local to that group and become group variables.
- Nested groups cannot reference an enclosing group's local variables; they may reference variables
  bound before the outermost group, which act as equality constraints.
- A variable may occur at most once in the group that introduces it. A name that already exists
  before the group cannot be introduced again; the analyzer rejects the shadowing with a positioned
  semantic error.
- A group node variable registers as `NODE_LIST`; a group relationship variable registers as
  `RELATIONSHIP_LIST`; a group path variable registers as `PATH`.
- Property access and `type()` on a list variable keep the existing list-variable rejection. Users
  write a list comprehension instead.

### Walker frames

`WalkState` gains `frames: tuple[GroupFrame, ...]` and `terms: tuple[PathTerm, ...]`. A
`GroupFrame` holds:

- The group term index and inner path pattern.
- The current iteration count.
- The accumulated node and relationship lists per group variable.
- The inner path nodes and relationships, including the shared boundary node exactly once.
- The mode memory for the group and the outer path.

Walking a grouped term:

1. If the lower bound is zero, first try the zero-iteration transition: keep the boundary node,
   bind every group variable to an empty list, and continue to the next outer term.
2. Push a frame and walk the inner terms from the current boundary node.
3. When the inner pattern completes, add its elements to the frame, increment the iteration count,
   and either:
   - continue the group when the maximum is not reached and the path mode allows another
     iteration, or
   - close the group when the minimum is reached, merge the flattened lists and the group path,
     pop the frame, and continue the outer term.
4. A group iteration starts at the node where the previous one ended, so the boundary node is
   shared rather than repeated in the path value.

The inner path mode is applied as an additional constraint in `_extend_memory`; the outer mode is
already enforced on the accumulated path. The clause match-mode used-edge set is threaded through
the frame and iteration exactly as it is for simple quantified segments.

Risks of the frame model are bounded by the progress rule: every iteration consumes at least one
relationship, so the expansion counter grows and the budget stops an open group. Group variable
lists grow with iterations; an open `WALK` group therefore needs demand or a repetition restriction,
which the profile documents.

Alternative considered: unroll bounded groups into repeated simple terms at analysis time. It is a
useful optimization for small fixed counts and can be added later underneath the same AST, but it
cannot express open bounds and would create two execution models now.

### Search and demand

The path-search evaluator walks the same terms and frame states. Its state key adds the frame stack:
group term index, iteration count, boundary node, and accumulated mode memory. The selection
partition is still the whole path's first and last node. Search stops a partition at its selected
k-th path, and the demand pipeline still stops the whole statement at `LIMIT`.

### Compiler routing

Any pattern containing a `GroupedPathTerm` routes to the pattern engine, even when all bounds are
closed. Simple and quantified-segment patterns keep their current routing. This intentionally
trades index pushdown for a single, correct grouped implementation; the performance page records
the cost on the fixed grouped fixtures.

### Explain output

A grouped stage adds `GROUP {m,n}` or `GROUP OPEN` to its explain line, in addition to the existing
`MATCH QUANTIFIED` marker and the path mode. `PATH SEARCH` remains the first line when a prefix is
present.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| The AST refactor touches every pattern consumer | A `flatten()` helper and a test that all existing simple-path queries produce identical plans and rows |
| Parser ambiguity around `(` | The documented lookahead rule and parser tests for node, property map, nested group, group path variable, and inner mode |
| Group variable lists surprise users | Profile and reference state list bindings, empty-list zero iterations, and the list-comprehension alternative |
| Nested groups flatten incorrectly | One test per nesting shape with node and relationship variables, plus a path-order test |
| Inner and outer mode precedence drifts | One `_extend_memory` path applies both modes; a mode matrix test reuses the path-semantics fixtures |
| Open group memory grows | Progress rule, expansion budget, demand pipeline, and performance documentation |
| No SQL pushdown for grouped patterns | Keep grouped fixtures small in the guide and record the measured trade-off |
| Group search expands too many frames | Reuse the search pruning and state key, including the frame stack, and add a termination test |

## Migration Plan

1. Introduce the term AST and parse simple patterns into one term; keep all current tests green.
2. Add group parsing and semantic scopes with rejection tests.
3. Add the frame walker for bounded groups, then open groups, then search and match-mode
   integration.
4. Route grouped patterns through the pattern engine and update explain.
5. Update the profile, corpus, reference, guide, tour, performance notes, and changelog.
6. Rollback is a code revert; no data change.
