# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1] - 2026-10-22

### Added

- Embedded property-graph engine backed by a single SQLite database or an
  in-memory database.
- Nodes with multiple labels and strict typed properties: booleans, signed
  64-bit integers, finite floats, strings, and homogeneous lists of those
  scalars.
- Canonical JSON property storage with type-sensitive and list-order-sensitive
  equality lookups.
- Directed typed relationships, including self-loops and parallel
  relationships.
- Immutable `Node`, `Relationship`, and `Path` snapshots and a domain error
  hierarchy.
- Explicit transactions using `BEGIN IMMEDIATE`, with commit on success and
  rollback on failure; every convenience write is atomic on its own.
- Detaching node deletion, with connected-node protection by default.
- Direction-aware reachability traversal that yields each node once at its
  shortest depth.
- Shortest-path search using bidirectional breadth-first search.
- Lazy, depth-bounded enumeration of relationship-unique trails with optional
  result limits.
- Snapshot-consistent traversal results unaffected by later writes.
- Python 3.14 packaging with strict type hints, numpydoc docstrings, Ruff, mypy
  strict, pytest, and a coverage gate.
- README documentation for persistence, CRUD, transactions, deletion, and
  traversal.

### Changed

- Raised the minimum Python version from 3.8 to 3.14.
- Configured Hatch `check` and `test` as the project quality gates.
