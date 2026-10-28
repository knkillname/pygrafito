# API stability

`pygrafito` follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The 1.x series keeps
the exported Python surface stable: existing imports, calls, and default behavior keep working.

## What is frozen

The 1.x contract covers:

- every name exported in `pygrafito.__all__`;
- the public methods and properties of `Graph`, `Transaction`, and `PreparedQuery`;
- the fields of exported immutable data objects such as `Node`, `Relationship`, `QueryResult`,
  `QueryBudget`, and the summary types;
- the exception hierarchy rooted at `PygrafitoError`.

Anything not exported by `pygrafito.__all__` is internal, even when it can be imported from a
submodule. Internal modules, helpers, and storage details may change in a minor release.

## Additions and breaking changes

A minor release may add a new exported name, a new method or property, or a new optional parameter
with a default. Existing calls continue to work.

Removing or renaming a public name, changing an existing signature incompatibly, or changing a
documented default requires a major release. The same rule applies to a change in the meaning of an
existing parameter or return value. A major release ships with migration notes in the changelog and
the documentation.

## Deprecation policy

When a public name must go away, the project deprecates it before removing it:

1. The name stays functional and emits `DeprecationWarning` when used.
2. The reference documentation and changelog name the replacement and the release that will remove
   the name.
3. The name remains for at least one minor release.
4. Removal happens only in a major release, normally 2.0.

On Python 3.13 and newer, deprecations also use PEP 702 metadata (`warnings.deprecated`) so static
type checkers report the same warning. Runtime use still emits `DeprecationWarning` for callers that
do not run a type checker.

## How the contract is tested

`tests/test_public_api.py` compares the exported names, core class signatures, dataclass fields,
enums, and exception MROs with `tests/fixtures/public_api.json`. A change to any of them fails the
test until the snapshot is updated deliberately. Updating the snapshot is the review point for the
compatibility decision: an additive change updates it in a minor release, while a removal or
incompatible signature change is rejected unless the release is major.

The public API snapshot is part of the normal test suite on Python 3.13 and 3.14.
