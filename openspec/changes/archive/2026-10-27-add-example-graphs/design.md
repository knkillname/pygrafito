# Design

## Context

See `proposal.md` for motivation and `specs/graph-examples/spec.md` for the contract.

The current state that shapes this design:

- The element model is version 2: node and relationship label sets, directed and undirected edges,
  stable ids, version 2 snapshots and views. `adopt-gql-element-model` is archived.
- The GQL profile is published in `docs/reference/gql-profile.md`. The current release still
  executes the transitional dialect; `INSERT`, `FOR`, `FILTER`, `LET`, `NEXT`, `GROUP BY`,
  `{n,m}`, the single-dash directions, and path modes are target or gated. `MERGE`, `WITH`
  aggregation and scope, implicit grouping, and `type()` are pygrafito extensions.
- The follow-up changes that will rewrite the surface are named in the profile:
  `adopt-gql-query-frontend`, `add-query-budget`, `add-gql-path-semantics`,
  `add-gql-composition`, `add-gql-values`, and `harden-for-1.0`.
- Documentation tests execute every Python fence in `docs/index.md`,
  `docs/getting-started/quickstart.md`, and `docs/guides/*.md` with the working directory set to a
  temporary path. Reference pages are only parsed. A docs snippet therefore cannot rely on a
  relative path into the repository or on importing a repo-only package.
- `benchmarks/run.py` owns a `Dataset` generator that seeds 20,000 nodes and 60,000 relationships
  with generated designations and regions, and the performance page documents
  `hatch run python benchmarks/run.py`.
- Ruff is configured with `src = ["src", "tests"]`; Pyrefly includes `src/pygrafito` and `tests`.
  Coverage measures `pygrafito` only.
- The source material lives outside version control in `tmp/`, which is ignored: a formatted 1981
  screenplay, a 40-page PDF transcript of the released Legacy script, and a plain Ares transcript.
  The PDF and both transcripts lack reliable scene slugs; only the 1981 screenplay has numbered
  scene headings.
- Project rules require class-based modules, SPDX headers, strict annotations, numpydoc docstrings,
  and one-way package imports. `examples/` is not part of the wheel.

## Goals / Non-Goals

**Goals:**

- Make the example tree a showpiece with a clear entry point for hobbyists, data scientists, and
  computer scientists.
- Keep sample data language-neutral so it survives every GQL change, and keep query tours small,
  classified, and cheap to migrate.
- Give documentation a realistic dataset without breaking the rule that every docs Python snippet
  is a complete, copyable program.
- Share one synthetic generator between the showcase and the benchmark harness.
- Keep screenplay sources, dialogue, and action text out of the repository and out of the package.

**Non-Goals:**

- No engine, storage, public API, CLI, or query-language change; no new query construct; no edit to
  the GQL profile or its conformance matrix.
- No scene-level graph for the transcripts that lack scene slugs; no claim that page- or
  block-level co-occurrence equals shared-scene co-occurrence.
- No notebook runtime, no third-party runtime dependency, no PDF library dependency.
- No per-film dataset fork; the franchise lives in one graph with provenance.
- No committed binary database and no committed screenplay source.

## Decisions

### D1. Audience lanes over one shared data layer

```
examples/
  README.md
  __init__.py
  __main__.py            python -m examples
  build.py               dataset construction and export
  data/
    grid.json            curated franchise graph
    cast.json            derived cast aggregates
    places.json          curated places plus derived transitions
    grid.jsonl           generated version 2 snapshot (committed)
  support/dataset.py     builders, synthetic generator, path resolution
  extract/               local-only screenplay/transcript adapters
  tours/                 shell narratives in .gql
  analysis/              data-science recipes
  algorithms/            semantics and cost demonstrations
```

The lanes map to interaction modes rather than to personas alone: tours produce a session, analysis
produces tables and files, algorithms produce counts and timings. Alternatives considered: an
artifact-first tree (`data/`, `queries/`, `build.py`), which has no entry point for a reader; a
numbered gallery, which implies a learning order and hides task-oriented examples; and a folder
per example, which duplicates setup and produces a dozen READMEs.

### D2. JSON source, generated snapshot, no GQL seed

`data/*.json` is the authored source, keyed by stable string handles. The builder validates the
whole document, then creates elements through the public Python API and optionally writes a
version 2 JSONL snapshot. The snapshot is a generated artifact; `grid.jsonl` is committed so a
reader can restore the main dataset without running the builder, and a drift test keeps it equal to
a fresh build.

Alternatives considered:

- **Snapshot JSONL as the source.** Native import, but numeric ids, strict record order, and header
  counts make it poor for review and hand editing.
- **JSONL rows through `Graph.import_file`.** Engine-native, but a statement cannot parameterize
  labels, `CREATE` is single-label and directed-only, and undirected edges and label sets are
  central to the element model.
- **A GQL seed script.** Nice language demo, but it cannot express undirected edges today, needs
  extra `SET` statements for label sets, and would be rewritten by the frontend, composition, and
  path-semantics changes. It also puts data in the dialect, which is exactly what this change
  avoids.
- **XML.** No engine support and no interoperability requirement that JSON does not satisfy.

### D3. One franchise graph with provenance and lineage

The graph covers three sources with stable identifiers: `tron-1981` (fourth draft), `legacy-2010`
(released script), and `ares-2025`. `Film` nodes carry `title`, `released` (int), and `source_kind`
(`draft`, `final`, `transcript`). Entities carry a `sources` list property.

Labels: `User`, `Program`, `Organization`, `Place`, `Vehicle`, `Object`, plus secondary labels where
the element model is worth showing: `MCP` is `Program` and `System`; `Quorra` is `Program` and
`ISO`; `Tron` is `Program` and `Security`; `Solar Sailer` is `Vehicle` and `Place`.

Relationship labels, all created through the public API:

| Label | Direction | Use |
| --- | --- | --- |
| `APPEARS_IN` | directed | entity to `Film` |
| `CREATED` | directed | user or program to its creation |
| `SUCCEEDED_BY` | directed | corporate and role succession |
| `PARENT_OF` | directed | family lineage |
| `ALLIES_WITH` | undirected | mutual alliance |
| `OPPOSES` | directed | conflict |
| `ENFORCES_FOR` | directed | program to the organization it serves |
| `OWNS`, `CONTROLS` | directed | organization to property or program |
| `CONTAINS`, `LOCATED_IN` | directed | place hierarchy |
| `ALIAS_OF`, `VERSION_OF`, `REPROGRAMMED_AS`, `REINCARNATION_OF` | directed | identity across sources |
| `TRAVELED_ON`, `GUARDS` | directed | vehicles and duties |

Identity policy: merge entities that are clearly the same across sources (`Kevin Flynn`,
`Sam Flynn`, `Alan Bradley`, `Tron`, `Clu`, `ENCOM`, the Grid) and record every source in
`sources`; keep era-specific elements separate (`Rinzler`, `Ares`, `Castor/Zuse`, `Athena`) and
link them with `VERSION_OF`, `REPROGRAMMED_AS`, `REINCARNATION_OF`, or `ALIAS_OF`. The Dillinger
family links `Ed Dillinger`, `Elisabeth Dillinger`, and `Julian Dillinger` through `PARENT_OF`, and
the ENCOM succession chain links `Ed Dillinger`, `Kevin Flynn`, `Sam Flynn`, and `Eve Kim` through
`SUCCEEDED_BY`.

Alternative considered: duplicate per-film nodes linked by `SAME_AS`. It preserves contradictions
between films but doubles the graph and forces every query to cross the identity edge.

### D4. Dataset family and merging

- `grid` is the curated semantic graph, roughly 120 nodes and 200 relationships. It is the docs
  default.
- `cast` contains character handles and weighted edges: `SHARES_SCENE` (undirected, `weight`,
  `basis`), `SAME_PAGE` and `SAME_BLOCK` for the transcript-only sources, and `SPEAKS_AFTER`
  (directed, `weight`). Nodes are a subset of the franchise characters.
- `places` contains curated `CONTAINS` and `LOCATED_IN` edges plus `NEXT_LOCATION` transitions
  (directed, `weight`, `basis`) derived from the 1981 screenplay only.
- `all` merges the three by handle. Identical nodes merge; conflicting property values are an
  error rather than last-write-wins.
- `synthetic` is not a file. It is a generator in `support/dataset.py` used by the algorithms lane
  and the benchmark harness.

Derived datasets are committed as aggregates so CI and readers do not need the source scripts.
`grid.jsonl` is committed; `cast` and `places` snapshots are generated on demand.

### D5. Build and front-door contract

`python -m examples` lists the catalog when no action is given. `python -m examples build <dataset>`
builds `grid`, `cast`, `places`, `all`, or `synthetic` and writes a database or a snapshot:

```
python -m examples build grid --output grid.db
python -m examples build all --output grid.jsonl --format jsonl
python -m examples build synthetic --nodes 5000 --relationships 15000
```

Validation happens before mutation; creation runs in one transaction so a failure leaves no
partial graph. The JSON document may declare indexes and uniqueness constraints, which the builder
applies for database output; snapshots carry elements only, and the documentation states that
difference. Output is deterministic: nodes sort by handle, relationships by endpoints and labels,
properties are canonical, and relationship labels are sorted.

### D6. Execution convention

Every example is a class with a `run()` method returning its result; `__main__` parses arguments and
prints. Examples run with no arguments against an in-memory `grid` (or a small synthetic graph) so a
curious reader gets a result immediately. Optional flags select `--dataset`, `--nodes`, `--seed`,
and `--format`. All examples run as modules from the repository root
(`python -m examples.analysis.rank_by_degree`), never as file paths, so first-party imports resolve
without path manipulation and without installing the examples.

### D7. GQL tours are classified and migration-owned

Four single-concern tours use the current dialect and are catalogued with tier, profile section, and
migrating change:

| Tour | Tier | Migrated by |
| --- | --- | --- |
| `01-match.gql` | canonical GQL (`MATCH ... WHERE`) | `adopt-gql-query-frontend` for `FILTER` alternatives |
| `02-write.gql` | `CREATE` alias; `MERGE` extension | `adopt-gql-query-frontend` for `INSERT` |
| `03-compose.gql` | `UNWIND` alias; `WITH` and implicit grouping extensions | `add-gql-composition` |
| `04-paths.gql` | legacy quantifier compatibility; double-dash direction aliases | `add-gql-path-semantics` |

Tours use `//` comments only, because `--` is not a comment in the current release and collides
with the either-direction form. They use `-->`, `<--`, `--`, and `*n..m`; they do not use `->`,
`~`, `{n,m}`, `FILTER`, `FOR`, or `INSERT`. A tour never claims an extension is GQL, and a missing
construct is a separate profile change, not an example.

Alternatives considered: canonical GQL now, which the current release cannot execute; waiting for
the frontend, which leaves the shell showcase without tours; generating tours from the JSON, which
reintroduces dialect churn into the data layer.

### D8. Local-only extraction with per-source fidelity

`examples/extract/` reads a caller-supplied path; there is no default and no bundled source. Three
adapters reflect the actual formats:

- **Screenplay**: the 1981 draft. Scene headings, page numbers, cues, and scene boundaries.
  Scene-level co-occurrence and location transitions are reliable.
- **Plain transcript**: Ares. Inline `Name: dialogue` prefixes and blank-line blocks. Dialogue
  turns are reliable; co-occurrence uses blocks and records `basis = "same_block"`; there are no
  locations.
- **PDF transcript**: Legacy. `pdftotext -layout` output, cue heuristics, page breaks. Dialogue
  turns are heuristic; co-occurrence uses pages and records `basis = "same_page"`; there are no
  locations.

The PDF adapter shells out to `pdftotext` when it is available and otherwise explains how to export
text. This is a development tool, not a runtime dependency, and it is absent from the wheel. The
extractor emits the same JSON shape as `cast.json` and `places.json`: handles, weights, counts, and
`basis` metadata, never dialogue or action text. Tests use an invented mini-script fixture and do
not require a real screenplay.

### D9. One synthetic generator for examples and benchmarks

`Dataset` moves out of `benchmarks/run.py` into `support/dataset.py` as `Synthetic(nodes,
relationships, seed)`. It keeps the current topology, counts, and label mix, and replaces generated
`program-1234` and `region-3` values with roster names, place-derived regions, and the element
model's label sets. `benchmarks/run.py` imports it and is invoked as `python -m benchmarks.run`, so
the repository root is on `sys.path`; a `benchmarks/__init__.py` makes that explicit. The
performance page is updated.

Alternative considered: keep a second generator in the benchmark. It drifts, and the "benchmark
fixture" purpose disappears.

### D10. Documentation without breaking copyable snippets

A new `docs/guides/examples.md` page describes the datasets, the lanes, the build commands, and the
tour catalog, and is added to the guide toctree. `README.md`, `docs/index.md`, and the quickstart
link to it; the shell guide seeds `grid.db` from the example builder instead of an ad-hoc session.

Executed Python snippets stay self-contained: they do not import `examples/`, because the examples
are not installed and the docs tests run from a temporary directory. The guide uses console blocks
for commands and short inline Python for the dataset shape. Teaching pages diversify their names
from the roster but keep building their own small graphs.

### D11. Test and configuration surface

`tests/test_examples.py` builds every dataset, asserts validation failures, checks snapshot
determinism and restore round-trips, runs every tour through the in-process shell harness, invokes
every analysis and algorithm entry point, checks synthetic determinism and counts, and verifies the
benchmark imports the shared generator. A packaging check asserts the built wheel does not contain
`examples/`.

Ruff gains `examples` in `src`; Pyrefly gains it in `project-includes`. Coverage continues to
measure `pygrafito` only; examples are developer artifacts, not product code. Example modules follow
the repository style, including SPDX headers, class-based methods, and numpydoc docstrings.

## Risks / Trade-offs

- **Derived content drifts into a screenplay digest.** The extractor emits aggregates only, and
  committed data is limited to names, weights, counts, and structural metadata. Review each derived
  file for reconstruction risk before committing.
- **PDF extraction is noisy and version-dependent.** The Legacy adapter is documented as
  heuristic, records its basis, and is tested only with the invented fixture; the committed
  aggregate is curated rather than regenerated in CI.
- **Tours rot with the GQL rewrite.** The tier catalog names the migrating change for each file,
  and tests execute every tour; a failing tour blocks the frontend change until it is migrated.
- **The showcase grows beyond maintainability.** The lanes are capped at five analysis examples and
  six algorithm examples; the catalog table is the contract for what exists.
- **Benchmark invocation changes.** `python -m benchmarks.run` must replace the script path in the
  performance page and any CI command, or the shared generator cannot be imported.
- **Docs snippets stop being copyable.** The rule is explicit: no executed snippet imports
  `examples/`; commands are console blocks.
- **Curated accuracy.** The franchise graph is hand-authored; every relation must be plausible from
  the source material, and uncertain relations are omitted rather than invented.

## Migration Plan

No runtime migration and no compatibility surface. Land in this order: data and support, builder
and tests, lanes, tours and manifest, documentation, benchmark wiring, configuration and changelog.
Rollback removes `examples/` and reverts the benchmark, documentation, configuration, and changelog
edits; no stored data or public API changes.

The follow-up GQL changes own the tour migration named in the catalog. This change does not edit
`docs/reference/gql-profile.md`; if an example needs a construct the profile does not define, it is
left out and handled by a separate profile change.
