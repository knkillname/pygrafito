# Proposal

## Why

Small applications often need graph-shaped data but not a dedicated graph server, its operational footprint, or its network protocol. SQLite demonstrates that an embedded, single-file engine can provide ACID semantics and a familiar model without a service to operate. `pygrafito` should offer the same trade for property graphs: a pure-Python library backed by `sqlite3`, with precise property-graph semantics and a Python-first API.

## What Changes

- Introduce an embedded property-graph engine persisted in a single SQLite database (or `:memory:`), using stdlib `sqlite3` and JSON-encoded properties.
- Implement a property-graph model: nodes with zero or more string labels, directed relationships with one non-empty string type and properties, and strict property values (`bool`, 64-bit `int`, finite `float`, `str`, homogeneous lists of scalars). Maps and stored `None` are rejected; assigning `None` removes a property.
- Expose immutable `Node`, `Relationship`, and `Path` snapshots and explicit writes through `Graph` and `Transaction`. Convenience writes run in one-shot transactions; `with graph.transaction()` groups writes with `BEGIN IMMEDIATE`.
- Add a demand-specific traversal API: `traverse()` for distinct reachable nodes at their shortest depth, `shortest_path()` for one path with the fewest relationships via bidirectional BFS, and `paths()` for relationship-unique trails (nodes may repeat; a relationship may not repeat within one path) enumerated with backward-distance pruning.
- Keep the engine embedded and single-writer: one connection per `Graph`, not thread-safe, WAL for file databases, foreign keys enforced.
- Deleting a connected node SHALL fail unless `detach=True`, in which case incident relationships are removed first.
- Move packaging and quality gates to Python 3.14: strict type hints, numpydoc docstrings, ruff, mypy strict, `hatch check --fix`, `hatch test`, and coverage of at least 80%.
- Defer, explicitly: a declarative textual graph-query language parser, a network protocol or server mode, declared property indexes and uniqueness constraints, path counting and all-shortest-paths, SCC condensation, async, pooling, and multi-process access.

## Capabilities

### New Capabilities

- `property-graph`: the persisted property-graph model, strict property values, node and relationship lifecycle, deletion rules, equality lookups, and transaction/ACID behavior.
- `graph-traversal`: direction-aware neighborhood traversal, relationship-unique path enumeration, depth bounds, and shortest-path results.

### Modified Capabilities

None. This is the project's first change and introduces both capabilities.

## Impact

- Affected code: new modules under `src/pygrafito/` (`model`, `storage`, `engine`), new tests under `tests/`, and `pyproject.toml` updates for Python 3.14 and the `check`/`test` tooling.
- Public API: new `Graph`, `Transaction`, `Node`, `Relationship`, `Path`, `Direction`, and domain error hierarchy.
- Dependencies: runtime remains stdlib-only (`sqlite3`, `json`, `typing`, `dataclasses`, `functools`, `operator`, `itertools`). Development adds `pytest`, `pytest-cov`, `ruff`, and `mypy`.
- Compatibility: greenfield; requires Python 3.14+ and SQLite 3.38+ for built-in JSON1. Existing functionality is unaffected because the package is currently an empty scaffold.
