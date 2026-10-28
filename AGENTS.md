# AGENTS.md

## Start here

`pygrafito` is an embedded property-graph library backed by stdlib `sqlite3`. Durable specs live in `openspec/specs/`; the archived design and implementation plan for the initial release live in `openspec/changes/archive/2026-10-22-add-embedded-property-graph/`.

- Target Python 3.14, runtime standard library only.
- Durable specs live in `openspec/specs/` and are authoritative.
- Implement through `/opsx-apply`; planning and exploration must not write code.
- Every `/opsx-apply` run MUST update the Sphinx documentation under `docs/` (see [Documentation](#documentation)).
- After every successful archive operation, create a Git commit.

## Commands

- `hatch check --fix` — Ruff lint/format plus Pyrefly, Hatch 1.18's built-in type checker. Do not use `hatch run check` or configure a separate type-checking environment.
- `hatch test` — pytest in the Hatch test environment. Pytest arguments are forwarded: `hatch test tests/test_codec.py::test_name`.
- `hatch run docs:build` — build the Sphinx site with warnings treated as errors. Requires
  Node.js and the pinned Mermaid CLI; the first run downloads Chromium.
- `hatch run docs:serve` — serve a live preview of the documentation site.
- `python -m pygrafito <database> -c "<statement>"` — run the shell against a graph; see `docs/reference/cli.md`.
- `hatch version <version>` — set the project version. Never edit `src/pygrafito/__about__.py` directly.
- `openspec status --change <name> --json`; `openspec validate <name> --strict`.
- `openspec validate --specs --strict`.
- CI runs `hatch check` and `hatch test`; the package job runs `uv build`, installs the wheel in a
  clean environment, and verifies `py.typed` and `LICENSE.txt` are packaged. The docs workflow
  builds the Sphinx site and deploys `main` to GitHub Pages.
- Coverage gate: at least 80%; `fail_under` is enabled in `pyproject.toml`.

Keep Ruff, Pyrefly, pytest, and coverage configuration in `pyproject.toml`; do not invent a parallel workflow.

## Code style (non-default)

- Every function is a method. No module-level functions; put helpers in focused classes as private or static methods.
- Import submodules and CamelCase types only; never import functions or constants. A type may be imported directly regardless of origin when its name is CamelCase (`Node`, `Connection`, `Self`, `PropertyCodec`). Submodules may always be imported (`import dataclasses`, `import collections.abc`, `from pygrafito.storage import nodes`). Keep lowercase callables and values behind their module (`import functools`; use `functools.partial`), and never import them directly (`from dataclasses import dataclass`, `from functools import partial`, `from module import CONSTANT`).
- No `from __future__` imports. Use Python 3.14 typing (`Self`, `type` aliases, `X | Y`).
- Strict type hints on all methods; numpydoc docstrings documenting every parameter.
- Frozen dataclasses, generators, comprehensions, `itertools`, `functools`, `operator`; small testable methods. Readability first; SOLID, DRY, KISS.
- One-way imports only: `model <- storage <- engine <- __init__`. No cycles.
- New Python files start with the existing SPDX header (`SPDX-FileCopyrightText` and `SPDX-License-Identifier: MIT`).

## Architecture and data rules

- SQLite stores properties as canonical JSON text. Labels are in `node_labels`; relationships are indexed by `(src, rel_type)` and `(dst, rel_type)`.
- Strict values: `bool`, signed 64-bit `int`, finite `float`, `str`, or homogeneous lists of those scalars. Reject maps, nested lists, stored `None`, NaN, and infinities. Assigning `None` removes a property.
- SQLite conflates `true` with `1` and `1` with `1.0`. Every property predicate must pair `json_type(...)` with `json_extract(...)`. Always quote JSON paths (`$."key"`); never use `'$.' || key`.
- One `sqlite3.Connection` per `Graph`, `check_same_thread=True`; the library is not thread-safe. Writes use `BEGIN IMMEDIATE`; file databases use WAL; foreign keys are on.
- `INTEGER PRIMARY KEY` ids may be reused after deletion; never treat them as permanent external keys.
- Traversal: `paths()` enumerates relationship-unique trails (nodes may repeat, relationships may not); `traverse()` yields distinct nodes at shortest depth; `shortest_path()` uses bidirectional BFS. A `(node, depth)` DP counts walks and is wrong. `count_paths` is deferred.
- `paths()` requires a maximum depth and supports an optional limit and lazy iteration.
- The target query language is GQL. Canonical spelling, compatibility aliases, compatibility
  constructs, and extensions are defined in `docs/reference/gql-profile.md`. A change that adds or
  changes a query construct MUST update that profile, its conformance matrix, and the conformance
  corpus.

## Testing

- Use `:memory:` SQLite for unit tests and `tmp_path` for reopen/persistence tests.
- Test graphs must be themed on the TRON franchise: name nodes, labels, properties, and
  relationships after TRON characters, programs, and places (for example, Kevin Flynn, Sam Flynn,
  Quorra, Tron, Clu, Rinzler, the Grid, ENCOM, and ISO). Prefer these names over generic
  placeholders such as Alice and Bob. `tests/test_naming_convention.py` enforces this for
  graph-building test files; pure model, codec, package, and schema tests may keep generic values.
- Never name or reference other graph database products or their trademarks in tests, specs,
  docs, or code.
- Every fenced `python` block in `README.md` is executed by `tests/test_readme.py`; keep examples
  runnable.
- Traversal fixtures must cover diamond, directed cycle, parallel relationships, and self-loop.
- Add tests in the same task group as the code they cover; do not defer them.
- Before archive: `hatch check --fix` and `hatch test` pass, coverage at least 80%.

## Versioning and changelog

- `CHANGELOG.md` is required. It follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- Every change affecting behavior, the public API, dependencies, packaging, or the development workflow MUST add an entry under `## [Unreleased]` in the same task group as the code.
- Use the Keep a Changelog categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`. Omit empty categories.
- Write every changelog entry for end users: short, friendly, and outcome-focused. Use one or two sentences per user-visible change, say what changed and what the user can now do, and omit internal class or function names, SQL details, test names, file paths, and implementation mechanics. Mark breaking changes plainly and state the migration step when one is needed.
- Releases rewrite and move the `[Unreleased]` entries into a new `## [X.Y.Z] - YYYY-MM-DD` section using the end-user rule above, then run `hatch version <version>`.
- `hatch version` is the only supported way to change the version; `pyproject.toml` reads it dynamically from `src/pygrafito/__about__.py`.
- Keep an empty `## [Unreleased]` section at the top after every release.

## Documentation

- **Mandatory for every `/opsx-apply` run:** update the Sphinx sources under `docs/` for every
  behavior, public API, CLI, or configuration change the run implements. Add or update pages,
  guides, references, and `toctree` entries as needed; document the change where a reader would
  look for it. Then run `hatch run docs:build` and fix every warning before marking the affected
  tasks complete. An apply run that changes behavior without a matching docs update is incomplete;
  do not mark its tasks `- [x]`.
- Keep `README.md` examples runnable as features land; verify the snippets.
- Describe graph semantics directly; avoid product-name shorthand in specs and docs.

### Documentation voice

The full rulebook is `docs/contributing/documentation-style.md`; these are the non-negotiables.

- **Three zones.** The landing page, quickstart, and guides teach in the second person and lead with
  the outcome. The reference states rules and edge cases without instructional asides. Generated
  API pages keep their generated structure.
- **Five callouts only.** Use `tl;dr` for the page summary, `Tip` for an optional shortcut,
  `Warning` for a data-loss or wrong-result risk, `Remember` for the one rule to carry away, and
  `In detail` for optional technical depth. Keep the fixed titles; never nest callouts.
- **A `tl;dr` on every reader-facing page** except `api/*.md`, immediately after the H1, in at most
  three sentences.
- **Emoji only in card titles and badges.** No emoji in headings, body prose, callout titles, or
  diagrams. Within a grid or badge collection, all items get one or none do.
- **Show the graph before the code.** Every example that introduces a graph shape gets one diagram
  with the same names and relationship types as the snippet; later variations reuse it.
- **Every diagram** uses the `{mermaid}` directive with `:alt:`, `accTitle:`, and `accDescr:`, and
  renders to SVG at build time. `hatch run docs:build` needs Node.js and
  `@mermaid-js/mermaid-cli@12.0.0`; the first run downloads Chromium.
- **Diagram typography.** Keep entity names in Inter and wrap labels, relationship types, property
  keys, values, and syntax in `<code>` so they render in JetBrains Mono. Both fonts are bundled
  under the SIL Open Font License 1.1.
- **Keep the structural checks green.** `tests/test_docs_style.py` enforces summaries, the callout
  vocabulary, emoji consistency, and diagram metadata.
