# Design

## Context

`Graph.traverse`, `Graph.shortest_path`, and `Graph.paths` all call a private snapshot
helper that loads every node and every relationship into Python dictionaries before any
search begins. `ReachabilityEvaluator`, `ShortestPathEvaluator`, and `TrailEnumerator`
then operate on that materialized `AdjacencySnapshot`. Relationship iteration reads
through `(src, rel_type, dst)` and `(dst, rel_type, src)`, so a level of a frontier is
already an indexed lookup away; nothing about the storage layer forces a full load.

The durable constraint that shapes this design is the snapshot requirement: results must
reflect the graph at the moment the call is made, so a later write cannot change an
in-progress traversal. Materializing eagerly is what makes that true today, and it must
stay true. See `proposal.md` for motivation and `specs/graph-traversal/spec.md` for the
contract.

## Goals / Non-Goals

**Goals:**

- Bound capture by the caller's direction, type, and depth arguments.
- Keep result content, ordering, laziness, and validation exactly as they are.
- Stop shortest-path search as soon as the two frontiers meet.
- Make the cost property testable without timing assertions.

**Non-Goals:**

- Streaming traversal that holds a read transaction open across iteration.
- Pushing search into SQL with recursive CTEs.
- Changing trail semantics, depth validation, or result ordering.
- Bounding the region for an unbounded shortest-path search on a highly connected
  component; that region is the component.

## Decisions

### D1. Level-wise capture, one indexed query per level

A new capture object walks the graph in breadth-first levels: for the current frontier it
asks the relationship repository for every incident relationship in one statement, then
fetches the newly discovered nodes in one batch. Cost is proportional to the explored
region, not to the database. Alternatives considered: a recursive CTE (pushes row
materialization and trail bookkeeping into SQL, harder to bound and to build snapshots
from) and one query per node (correct but N+1).

The capture materializes the region before returning, so the snapshot guarantee is
preserved without holding a transaction open. Iteration order is then decided by the
existing evaluators, unchanged.

### D2. Capture only the region a bounded search can reach

For a bounded traversal the region is every node within `max_depth` hops and every
relationship whose tail is within `max_depth - 1` hops. Edges that lead back to already
visited nodes are captured deliberately, because trail enumeration needs them even though
reachability discards them. `paths` therefore captures the start radius only: every
trail of length at most `max_depth` lies inside it, so no second capture from the end is
needed for correctness. The existing reverse-distance pruning runs over the captured
region.

### D3. A shared source interface for materialized and live adjacency

Two implementations satisfy one small interface:

```text
contains(node_id) -> bool
node(node_id) -> Node
nodes(node_ids) -> dict[int, Node]
frontier_edges(frontier, direction, types) -> ordered (from_id, Relationship, to_id)
```

- Materialized region: answers from the captured maps; `frontier_edges` walks the
  frontier in order and delegates to the existing adjacency lists.
- Live neighborhood: answers `contains` and node lookups with short queries and
  `frontier_edges` with the repository frontier query, caching nothing.

`traverse` and `paths` use the materialized region, so `ReachabilityEvaluator` and
`TrailEnumerator` keep their current input and behavior. `ShortestPathEvaluator` switches
from `edges(current, ...)` per node to one `frontier_edges(current_frontier, ...)` call
per layer, which keeps its bidirectional algorithm and lets it stop as soon as the
frontiers meet instead of loading a region first.

### D4. Deterministic frontier order and self-loop handling

`RelationshipRepository.frontier` returns edges ordered by frontier position, then by
relationship id, with the outgoing arm before the incoming arm. In both-direction mode a
self-loop is emitted once, from the outgoing arm, matching today's adjacency iteration.
Frontiers become ordered sequences rather than sets, so which minimal-length path is
returned becomes deterministic instead of set-iteration dependent; the shortest-length
guarantee is unchanged.

### D5. Chunk wide frontiers and wide node batches

SQLite bounds the number of bound parameters per statement. Both the frontier query and
the existing batch node read split their id lists into chunks sized under that bound,
preserving order across chunks. A dense level must not turn into a hard failure at some
node count.

### D6. Remove the whole-graph capture path

The private snapshot helper and the full capture entry point are deleted rather than left
as an unused alternative, so no production path can silently regress to loading the
graph. Tests that need a materialized region use the bounded capture with an explicit
depth.

## Risks / Trade-offs

- **Result ordering drifts** because capture order and evaluation order changed. →
  Frontier ordering is specified in D4 and covered by exact-sequence tests on the diamond,
  directed cycle, parallel relationship, and self-loop fixtures.
- **Self-loops counted twice in both-direction mode.** → Single-emit rule in D4 plus a
  dedicated fixture.
- **Wide frontiers exceed the parameter limit.** → Chunking in D5 with a test using a
  frontier wider than one chunk.
- **Double breadth-first pass for `traverse`** (capture, then evaluation). → Accepted for
  simplicity; the second pass is in memory and keeps one authority for ordering. Measured
  separately from capture in the benchmark if it becomes visible.
- **Unbounded shortest path on a dense component** still explores that component. →
  Inherent to the query; documented, and the depth bound is the caller's control.
- **Dense fan-out memory.** → The frontier query holds one level's relationships. No
  whole-graph structure exists, so peak memory tracks the widest level, not the database.
- **Trail enumeration remains exponential in the number of trails.** → Unchanged and
  already documented; the depth bound and result limit are the controls.

## Migration Plan

No data or schema change. The behavior change is internal to traversal execution. A
rollback restores the previous whole-graph capture without affecting stored data.

## Open Questions

- Whether `traverse` should later stream levels instead of materializing the region is a
  semantic change to the snapshot guarantee, so it is deferred rather than assumed.
- Whether the live source should cache levels for repeated lookups inside one call can be
  decided from benchmark data after implementation.
