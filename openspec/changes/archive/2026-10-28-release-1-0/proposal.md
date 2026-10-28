# Proposal

## Why

The GQL profile is complete and the hardening work is archived: the 1.0 release gate, fuzz and
crash proof, cross-platform CI, the frozen version 2 formats, the migration policy, and the public
API contract are done. The package is still `0.9.0`, the distribution still labels itself Beta, and
the documentation still describes 1.0 as something that has not happened yet. The first full
release cannot be published or accurately described until those three things agree.

## What Changes

- Set the package version to `1.0.0` with `hatch version 1.0.0`; never edit the version file
  directly.
- Change the distribution classifier from `Development Status :: 4 - Beta` to
  `Development Status :: 5 - Production/Stable`.
- Move every `[Unreleased]` changelog entry into `## [1.0.0] - 2026-10-28` and leave an empty
  `## [Unreleased]` section at the top. Keep the entries in end-user language and preserve every
  **BREAKING** marker.
- Remove the remaining future-1.0 framing from the documentation:
  - `docs/reference/gql-profile.md`: rewrite the introduction, collapse the
    "Current release / 1.0 target" status table into one supported-surface column, put the release
    gate and profile-freeze section in past tense, replace the stale
    "1.0 gate: add a focused parser test" cell with the real corpus case, and replace the
    "pre-1.0 target" sentence in the migration guidance.
  - Rename "supported 1.0 platform" to "supported 1.x platform" in `README.md`, `docs/index.md`,
    `docs/getting-started/quickstart.md`, and `docs/reference/platform-support.md`, and change the
    "1.0 contract" sentence in `docs/reference/query-language.md`.
  - Update the shell and CLI session banners from `0.9.0` to `1.0.0`.
- Add a Bit cameo to the quickstart node example: `Bit` as a `Program` with `cycles=1` and
  `active=True`, plus a boolean `find_nodes` query. This teaches the strict boolean value model and
  puts the character in reader-facing examples for the first time.
- Run the full gate (`scripts/verify --docs`), build the distributions, smoke-test the installed
  wheel and CLI, commit the release, and create the annotated `v1.0.0` tag. Pushing the tag is the
  separate publication step.
- No migration page and no separate release-notes page. The `1.0.0` changelog section is the
  release record; the profile already carries the migration guidance and the out-of-profile list.

**Non-goals:** no parser, engine, storage, dependency, or public API behavior; no new GQL
construct; no in-place migration; no claim of ISO conformance; no ingestion fast path; no
release-workflow automation beyond the existing tag-driven publish.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a release, packaging, and documentation change. `.openspec.yaml` sets
`skip_specs: true` because the 1.0 release gate is a process gate, not a new behavioral
requirement.

## Impact

- `src/pygrafito/__about__.py` through `hatch version 1.0.0`.
- `pyproject.toml`: the development-status classifier.
- `CHANGELOG.md`: the `1.0.0` section and the empty `Unreleased` section.
- `docs/`: the GQL profile, platform-support, landing, quickstart, query-language reference, shell
  guide, and CLI reference, including one new executable quickstart snippet.
- No runtime code, schema, snapshot format, dependency, or public API change.
- The `v1.0.0` tag and the existing tag-triggered release workflow.
