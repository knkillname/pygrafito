# Tasks

## 1. Frontier query in storage

- [x] 1.1 Add `RelationshipRepository.frontier(frontier, direction, types)` returning ordered `(from_id, Relationship, to_id)` triples: frontier position, then relationship id, outgoing arm before incoming, self-loop emitted once in both-direction mode; verify with unit tests for each direction, type filtering, ordering, and the self-loop rule.
- [x] 1.2 Split frontier id lists into chunks under SQLite's parameter bound while preserving order across chunks; verify with a frontier wider than one chunk that returns the complete ordered result.
- [x] 1.3 Add the same chunking to `NodeRepository.get_many`; verify a batch wider than one chunk returns every requested node.

## 2. Traversal source and bounded capture

- [x] 2.1 Introduce the shared source interface (`contains`, `node`, `nodes`, `frontier_edges`) and make the materialized `AdjacencySnapshot` implement it, including ordered `frontier_edges`; verify the existing traversal tests pass unchanged.
- [x] 2.2 Add the live neighborhood source backed by the repositories and codec; verify its `contains`, single-node, batch, and frontier behavior against a themed fixture graph.
- [x] 2.3 Add region capture that expands level by level within the depth bound, collects edges that return to visited nodes, and fetches only discovered nodes; verify on diamond, directed cycle, parallel relationship, and self-loop fixtures that the captured region contains exactly the expected node and relationship ids.
- [x] 2.4 Delete the whole-graph capture and the private snapshot helper from `Graph`; verify no production path calls the repository `all` methods by patching both to raise and exercising `traverse`, `paths`, and `shortest_path`.

## 3. Entry points

- [x] 3.1 Wire `Graph.traverse` to bounded region capture; verify exact result sequence and depths on the four required fixtures, the existing depth and direction cases, and snapshot isolation against a write made during iteration. Create or extend `docs/performance.md` with the measured traversal improvement in this group.
- [x] 3.2 Wire `Graph.paths` to bounded region capture; verify path content, min/max depth, relationship-unique trails, limit, and early-stop behavior on the required fixtures. Note the cost property in the traversal section of the README.
- [x] 3.3 Wire `Graph.shortest_path` to the live source with frontier expansion from both endpoints, stopping when frontiers meet or the bound is exhausted; verify shortest route, unreachable, same-node zero length, missing endpoint, and both-direction cases. Add a delta to `CHANGELOG.md` under `[Unreleased]` describing the bounded traversal cost.
- [x] 3.4 Add instrumentation tests using a wrapper around the repositories that records requested ids; verify that only in-region nodes and relationships are read for each traversal entry point.
- [x] 3.5 Add the traversal scenarios to the benchmark harness, creating it when absent, and run them against the previous whole-graph capture and the bounded implementation on the same data; record both sets of figures in `docs/performance.md` and verify they match a fresh run.

## 4. Integration checks

- [x] 4.1 Run `hatch check --fix` and confirm Ruff and Pyrefly report no issues.
- [x] 4.2 Run `hatch test` and confirm the full suite passes with coverage at or above 80%.

## Workflow follow-up

- Archive the change after review requirements are satisfied.
