# Proposal

## Why

The project's examples are a handful of two- and three-node snippets that repeat the same few
characters, and they serve documentation only. There is no sample dataset to explore, nothing
realistic for a data scientist to aggregate, no material for a computer scientist to exercise
traversal semantics, and no themed fixture shared with the benchmark harness. At the same time the
query surface is moving to GQL in staged changes, so every example statement will be rewritten
while the data must stay stable.

This change builds the example layer once, around language-neutral data and explicitly classified
query tours, so the showcase survives the frontend, composition, budget, and path-semantics changes
without being rebuilt.

## What Changes

- Add an `examples/` Python package with a single front door, `python -m examples`, and three
  audience lanes: `tours/` for shell narratives, `analysis/` for tabular and export work, and
  `algorithms/` for traversal semantics and cost.
- Add a curated franchise graph spanning three sources: the 1981 TRON fourth draft, the released
  TRON: Legacy script, and the TRON: Ares script. The graph carries users, programs, organizations,
  places, vehicles, objects, and film provenance, plus cross-film lineage such as succession,
  creation, reprogramming, and Master Control reincarnation.
- Add two derived aggregate datasets: a cast network with weighted co-occurrence and dialogue-turn
  edges, and a place network with containment and scene-transition edges. They merge with the
  franchise graph by shared handles and can be built alone or as one layered graph.
- Author the graphs as declarative, name-keyed JSON documents, and add a deterministic builder that
  loads them through the public Python API and emits either a `.db` database or a version 2 JSONL
  snapshot. No generated GQL seed, so the data is independent of the language changes.
- Add a shared, seeded synthetic generator for scale that borrows the same vocabulary and backs
  both the analysis algorithms lane and `benchmarks/run.py`.
- Add `.gql` tours written in the current transitional dialect, each labelled with its GQL profile
  tier and paired with the follow-up change that will migrate it.
- Add an extractor for local screenplay and transcript files whose outputs are aggregates only.
  The source scripts, dialogue, and action text are never committed or packaged.
- Add `tests/test_examples.py` covering the dataset build, snapshot determinism, tour execution,
  lane entry points, and synthetic generator determinism, and add documentation pages for the
  sample graphs and the example lanes.
- Update Ruff, Pyrefly, and benchmark wiring for the new tree. No runtime dependency, public API,
  storage layout, CLI, or query construct is added, so the GQL profile and its conformance matrix
  are unchanged.

## Capabilities

### New Capabilities

- `graph-examples`: the runnable example layer: curated franchise datasets and their provenance,
  deterministic build and native snapshot export, the `python -m examples` entry points and
  audience lanes, GQL tour tiering and migration, benchmark fixture reuse, and documentation and
  test synchronization.

### Modified Capabilities

None. This change adds a developer-facing capability; it does not change library behavior,
traversal semantics, import behavior, shell behavior, or the query language.

## Impact

- New tree: `examples/` with `data/`, `support/`, `tours/`, `analysis/`, `algorithms/`, `extract/`,
  `build.py`, and `__main__.py`.
- Tests: new `tests/test_examples.py`; no change to existing conformance, traversal, or interop
  suites.
- Benchmarks: `benchmarks/run.py` consumes the shared synthetic generator and runs as a module.
- Documentation: new sample-graph and examples pages, links from the landing page and quickstart,
  and updated benchmark invocation in `docs/reference/performance.md`.
- Configuration: Ruff and Pyrefly include the new tree; coverage does not, because examples are
  developer artifacts rather than product code.
- Changelog: an `Unreleased` `Added` entry for the example layer.
- Not included: screenplay files, dialogue text, action text, or any content derived from a script
  beyond names, aggregates, and structural metadata.
