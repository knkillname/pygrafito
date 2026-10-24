# Proposal

## Why

Every traversal materializes the entire graph before it starts. `Graph.traverse`,
`Graph.shortest_path`, and `Graph.paths` all capture an adjacency snapshot by loading
every node and every relationship into Python dictionaries, so a one-hop neighborhood
query costs the same as a full graph scan: measured on a 20,000-node / 60,000-relationship
graph, depth 1 took 268 ms and depth 3 took 282 ms. Memory use is the same story, and it
grows with the database rather than with the answer.

The previous change made selective lookups indexable. This one makes traversal cost
proportional to the region actually explored, which is the other half of the embedded
cost promise.

## What Changes

- Replace whole-graph snapshot capture with level-wise capture: fetch the relationships
  incident to a frontier set, fetch only the nodes those relationships reach, and repeat
  until the depth bound is spent.
- Bound `traverse` capture by its required `max_depth`, and bound `paths` capture by its
  required `max_depth` so the enumerated region contains every trail that can exist
  within the bound.
- Keep `shortest_path` as a bidirectional search, but expand two frontiers with level
  queries instead of building a snapshot first, stopping when they meet or the depth
  bound is exhausted.
- Add a frontier query on the relationship repository that resolves one level in a single
  statement, chunked under SQLite's parameter limit.
- Preserve snapshot semantics exactly: the explored region is materialized when the call
  is made, so a later write cannot change an in-progress result. No live read transaction
  and no change to iteration behavior.
- State the cost property in the durable specification: traversal work is proportional to
  the explored region, not to the size of the graph.
- Extend `docs/performance.md` with the measured traversal improvement and record the
  change in `CHANGELOG.md`.

## Capabilities

### New Capabilities

<!-- None. This change refines traversal execution under an existing capability. -->

### Modified Capabilities

- `graph-traversal`: snapshot capture becomes bounded by the traversal's depth and
  direction, and a requirement states that traversal work is proportional to the explored
  region. Result shape, ordering, validation, and laziness are unchanged.

## Impact

- `src/pygrafito/engine/traversal.py`: `AdjacencySnapshot` capture, reachability, shortest
  path, and trail enumeration.
- `src/pygrafito/engine/graph.py`: the three traversal entry points and their snapshot
  construction.
- `src/pygrafito/storage/relationships.py`: the level-frontier query.
- `docs/performance.md`, `CHANGELOG.md`, and traversal tests covering the required
  diamond, directed cycle, parallel relationship, and self-loop fixtures.
