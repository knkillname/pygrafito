# Explore the sample graphs

:::{admonition} tl;dr
:class: tldr

Build one of the runnable TRON datasets, open it in the shell, and follow a tour. The examples are
developer artifacts: they live in the repository and are not installed with the package.
:::

`pygrafito` ships a runnable example layer in the repository's `examples/` tree: three linked
datasets, shell tours, analysis recipes, and algorithm demonstrations. The examples are developer
artifacts, not part of the installed package, so every command below runs from a repository
checkout.

```console
python -m examples
```

:::{tip}
Start with `python -m examples` to list every dataset, lane, and command. The listing is the
shortest path from a checkout to a working graph.
:::

That lists the datasets, lanes, and commands. If the project is not installed in the active
environment, use `hatch run python -m examples` instead. The rest of this page follows the same
order.

## Datasets

| Name | What it contains |
| --- | --- |
| `grid` | Curated franchise graph across the 1981 TRON draft, TRON: Legacy, and TRON: Ares, with film provenance, lineage, places, vehicles, and objects |
| `cast` | Weighted character co-occurrence and dialogue-turn aggregates, each edge carrying a `basis` property |
| `places` | Place containment plus scene-to-scene transitions from the 1981 screenplay |
| `all` | The three datasets merged by shared handles |
| `synthetic` | A seeded scale graph shared with the benchmark harness |

```{mermaid}
:alt: The grid, cast, and places datasets, and the all dataset that merges them by shared handles.

flowchart LR
  subgraph GRID["grid"]
    K["Kevin Flynn"] -->|<code>APPEARS_IN</code>| F["TRON: Legacy"]
    G["The Grid"] -->|<code>HAS_PART</code>| T["I/O Tower"]
  end
  subgraph CAST["cast"]
    K2["Kevin Flynn"] ---|"<code>SHARES_SCENE</code><br/><code>weight=9</code>"| T2["Tron"]
  end
  subgraph PLACES["places"]
    R["Real World"] -->|<code>HAS_PART</code>| A["Flynn's Arcade"]
  end
  ALL["<code>all</code><br/>merged by shared handles"]
  K -.-> ALL
  K2 -.-> ALL
  R -.-> ALL
  accTitle: The three sample datasets and the merged view
  accDescr: Grid holds film, place, and character edges; cast holds weighted scene co-occurrence; places holds containment. The all dataset merges them by shared handles.
```

Build a database or a version 2 JSONL snapshot:

```console
python -m examples build grid --output grid.db
python -m examples build all --output all.jsonl --format jsonl
python -m examples build synthetic --nodes 5000 --relationships 15000
```

:::{warning}
Do not edit `examples/data/grid.jsonl` by hand. Rebuild it with `python -m examples build grid
--output examples/data/grid.jsonl --format jsonl`; the test suite keeps the committed snapshot
identical to a fresh build.
:::

A database build applies the dataset's indexes and uniqueness constraints. A snapshot carries
elements only; see [Snapshot format](../reference/snapshot-format.md). The committed
`examples/data/grid.jsonl` is the snapshot of `grid`, and the test suite keeps it identical to a
fresh build.

Open the database in the shell:

```console
pygrafito grid.db
```

## Shell tours

The `.gql` tours are short narratives that run against the built database:

```console
pygrafito grid.db -f examples/tours/01-match.gql
pygrafito grid.db -f examples/tours/02-write.gql
pygrafito grid.db -f examples/tours/03-compose.gql
pygrafito grid.db -f examples/tours/04-paths.gql
```

The tours use the canonical GQL spellings the release supports. The
[GQL profile](../reference/gql-profile.md) records every construct and its tier; each tour is
catalogued with its tier in `examples/tours/README.md`. `MERGE`, `WITH`, implicit grouping, and
`type()` are pygrafito extensions, not canonical GQL.

:::{admonition} Remember
:class: important

The tours are the canonical examples. Copy their spelling into new queries, and treat `MERGE`,
`WITH`, implicit grouping, and `type()` as pygrafito extensions rather than portable GQL.
:::

| Tour | Focus | Migrated by |
| --- | --- | --- |
| `01-match.gql` | `MATCH`, `OPTIONAL MATCH`, filtering, and ordering | `adopt-gql-query-frontend` (migrated) |
| `02-write.gql` | `INSERT`, `MERGE` extension, labels, and deletion | `adopt-gql-query-frontend` (migrated) |
| `03-compose.gql` | `LET`, `GROUP BY`, `NEXT`/`YIELD`, `FINISH`, and ordinality | `add-gql-composition` (implemented) |
| `04-paths.gql` | closed quantifiers, path modes, directions, and path variables | implemented |

## Analysis recipes

The analysis lane turns the datasets into tables, files, and SQL results:

```console
python -m examples.analysis.rank_by_degree
python -m examples.analysis.aggregate_by_source
python -m examples.analysis.import_csv
python -m examples.analysis.sql_views
python -m examples.analysis.export_report --output report
```

Every recipe runs with no required arguments and uses an in-memory graph by default. Use the flags
each recipe documents for depth, a caller-supplied file, or an output directory.

## Algorithm demonstrations

The algorithms lane shows traversal semantics and cost:

```console
python -m examples.algorithms.reachability
python -m examples.algorithms.trails_vs_walks
python -m examples.algorithms.shortest_path
python -m examples.algorithms.direction
python -m examples.algorithms.scaling --nodes 2000
```

`paths()` enumerates relationship-unique trails. In the query language, `WALK` is the default path
mode for canonical patterns and runs under the query budget; the trails demonstration states that
difference. See the
[GQL profile](../reference/gql-profile.md#path-modes) and the
[graph API](../api/graph.md).

## Where the data comes from

The repository does not contain a screenplay or transcript. The source files live outside version
control, the extractor in `examples/extract/` is a local development tool, and its output is limited
to names, counts, weights, and structural metadata. No dialogue or action text is committed or
packaged. The `basis` property on derived edges records whether a weight came from a shared scene, a
transcript page, a dialogue window, a dialogue turn, or a scene transition.

:::{admonition} In detail
:class: detail

The `basis` property is the provenance handle. `shared_scene`, transcript pages, dialogue windows,
dialogue turns, and scene transitions each produce a different value, so a query can separate
co-occurrence from dialogue order without reading the source material.
:::

### Local extraction

The extractor reads a source file you supply and emits aggregate JSON only:

```console
python -m examples.extract.screenplay path/to/screenplay.txt --format screenplay --kind cast
python -m examples.extract.screenplay path/to/transcript.txt --format transcript --kind cast
```

Use `--kind places` for scene transitions when the source has scene headings. The output contains
handles, weights, counts, and `basis` metadata, never dialogue or action text. The PDF adapter uses
`pdftotext` from poppler as a development-only tool; the package does not depend on it. Tests use an
invented fixture, so no real screenplay is required.

For the full catalog, provenance policy, and the rules for adding an example, see the
[example catalog](https://github.com/knkillname/pygrafito/blob/main/examples/README.md).
