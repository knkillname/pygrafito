# Examples

Runnable datasets, shell tours, analysis recipes, and algorithm demonstrations for `pygrafito`.
Everything here is a developer artifact: it is not installed with the package, and every Python
file follows the repository's class-based style.

Run every command from the repository root. The front door lists the catalog:

```console
python -m examples
```

If the project is not installed in the active Python environment, run these commands through
`hatch run python -m examples` instead.

## Who this is for

| You are | Start here | What you get |
| --- | --- | --- |
| Curious | `python -m examples build grid` | the Grid built in memory, with node and relationship counts |
| Hobbyist | `python -m examples build grid --output grid.db` then `pygrafito grid.db -f examples/tours/01-match.gql` | an interactive shell tour |
| Data scientist | `python -m examples.analysis.rank_by_degree` | a weighted cast ranking, with CSV and SQL recipes next to it |
| Computer scientist | `python -m examples.algorithms.trails_vs_walks` | trail semantics on a directed cycle, with the target `WALK` default noted |
| Contributor | `hatch test tests/test_examples.py` | every dataset, tour, and lane entry point executed |

## Datasets

| Name | Nodes | Relationships | What it is |
| --- | ---: | ---: | --- |
| `grid` | 78 | 180 | curated franchise graph across three sources, with provenance and lineage |
| `cast` | 35 | 87 | weighted co-occurrence and dialogue-turn aggregates |
| `places` | 27 | 48 | containment hierarchy and scene transitions |
| `all` | 78 | 290 | `grid`, `cast`, and `places` merged by shared handles |
| `synthetic` | caller | caller | seeded scale fixture shared with the benchmark harness |

```console
python -m examples build grid --output grid.db
python -m examples build all --output all.jsonl --format jsonl
python -m examples build synthetic --nodes 5000 --relationships 15000
```

A database build applies the dataset's declared indexes and uniqueness constraints; a JSONL snapshot
carries elements only. The committed `data/grid.jsonl` is the version 2 snapshot of `grid`, and a
test keeps it byte-identical to a fresh build.

### Sources and provenance

The curated graph covers the 1981 TRON fourth draft, the released TRON: Legacy script, and the
TRON: Ares script. Each film is a `Film` node with `released` and `source_kind`, and every
non-film entity carries a `sources` list. Shared entities merge across sources; era-specific
elements stay separate and link through `ALIAS_OF`, `REPROGRAMMED_AS`, or `REINCARNATION_OF`.

The repository does not contain a screenplay or transcript. `tmp/` is ignored, the extractor is a
local development tool, and its outputs contain names, counts, weights, and structural metadata
only. No dialogue line or action paragraph is committed or packaged.

### Derived aggregates

`cast` records how often characters share a scene, page, or dialogue window, plus who speaks after
whom. `places` records the containment hierarchy plus scene-to-scene transitions from the 1981
screenplay, the only source with reliable scene headings. Every derived edge carries a `basis`
property (`shared_scene`, `same_page`, `dialogue_window`, `dialogue_turn`, or `scene_transition`) so
a reader can tell what a weight means.

## Lanes

- `tours/` holds `.gql` narratives for the shell. They use the current transitional dialect and are
  catalogued by GQL profile tier in `tours/README.md`.
- `analysis/` holds data-science recipes: weighted ranking, per-source aggregation, CSV import, SQL
  views, and snapshot export.
- `algorithms/` holds traversal demonstrations: reachability, trails versus walks, shortest paths,
  direction, and scaling.

```console
pygrafito grid.db -f examples/tours/01-match.gql
python -m examples.analysis.rank_by_degree
python -m examples.algorithms.reachability
```

## Adding an example

1. Put the file in the lane that matches its interaction mode.
2. Give it an SPDX header, a module docstring, and a class with a `run()` method.
3. Make it work with no required arguments, against an in-memory graph.
4. Add a test to `tests/test_examples.py`.
5. Add one row to this catalog or to `tours/README.md`.

The lanes are capped at five analysis recipes and five algorithm demonstrations; the catalog is the
contract for what exists.

## Local extraction

The extractor reads a screenplay or transcript you supply and writes aggregate JSON only:

```console
python -m examples.extract.screenplay path/to/screenplay.txt --format screenplay --kind cast
python -m examples.extract.screenplay path/to/transcript.txt --format transcript --kind cast
python -m examples.extract.screenplay path/to/script.pdf --format pdf --kind cast
```

Use `--kind places` for scene transitions; that requires a source with scene headings. The output
contains character and place handles, weights, counts, and a `basis` property. It never contains
dialogue or action text. The PDF adapter shells out to `pdftotext` from poppler; that is a
development-only requirement, not a package dependency. Tests use an invented mini-screenplay
fixture, so the extractor never needs a real script.
