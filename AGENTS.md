# AGENTS.md

## Start here

`pygrafito` is an embedded property-graph library backed by stdlib `sqlite3`. Durable specs live in `openspec/specs/`; the archived design and implementation plan for the initial release live in `openspec/changes/archive/2026-10-22-add-embedded-property-graph/`.

- Target Python 3.14, runtime standard library only.
- Durable specs live in `openspec/specs/` and are authoritative.
- Implement through `/opsx-apply`; planning and exploration must not write code.

## Commands

- `hatch check --fix` — Ruff lint/format plus Pyrefly, Hatch 1.18's built-in type checker. Do not use `hatch run check` or configure a separate type-checking environment.
- `hatch test` — pytest in the Hatch test environment. Pytest arguments are forwarded: `hatch test tests/test_codec.py::test_name`.
- `hatch version <version>` — set the project version. Never edit `src/pygrafito/__about__.py` directly.
- `openspec status --change <name> --json`; `openspec validate <name> --strict`.
- `openspec validate --specs --strict`.
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

## Testing

- Use `:memory:` SQLite for unit tests and `tmp_path` for reopen/persistence tests.
- Traversal fixtures must cover diamond, directed cycle, parallel relationships, and self-loop.
- Add tests in the same task group as the code they cover; do not defer them.
- Before archive: `hatch check --fix` and `hatch test` pass, coverage at least 80%.

## Versioning and changelog

- `CHANGELOG.md` is required. It follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- Every change affecting behavior, the public API, dependencies, packaging, or the development workflow MUST add an entry under `## [Unreleased]` in the same task group as the code.
- Use the Keep a Changelog categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`. Omit empty categories.
- Releases move the `[Unreleased]` entries into a new `## [X.Y.Z] - YYYY-MM-DD` section, then run `hatch version <version>`.
- `hatch version` is the only supported way to change the version; `pyproject.toml` reads it dynamically from `src/pygrafito/__about__.py`.
- Keep an empty `## [Unreleased]` section at the top after every release.

## Documentation

- Keep `README.md` examples runnable as features land; verify the snippets.
- Describe graph semantics directly; avoid product-name shorthand in specs and docs.
