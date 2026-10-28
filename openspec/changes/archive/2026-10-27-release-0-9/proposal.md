# Proposal: release 0.9.0

## Why

The `Unreleased` changelog block now contains the version 2 element model, the GQL path-mode
surface, the query budget, and the composition surface. Shipping it as 0.9.0 gives users a
coherent pre-1.0 checkpoint and gives the next profile-completeness work a stable baseline.
Keeping it unreleased until 1.0 would leave a large breaking change set without a published
version to test against.

The OpenSpec change directory is `release-0-9` because change names cannot contain dots. The
released version is `0.9.0`.

## What Changes

- Set the package version to `0.9.0` with `hatch version 0.9.0`; do not edit the version file
  directly.
- Move every `[Unreleased]` changelog entry into a dated `## [0.9.0]` section and leave an empty
  `## [Unreleased]` section at the top.
- Rewrite the 0.9.0 notes for end users: short, friendly, outcome-focused sentences that say what
  changed and what users can now do. Preserve every user-visible change, but remove internal class
  or function names, SQL details, test names, file paths, and implementation mechanics.
- Add a short 0.9.0 release summary that identifies the composition/path-mode/query-budget
  milestone, states that the language profile is not yet complete, and points to the GQL profile
  for deferred features.
- Preserve and call out the existing **BREAKING** entries: the version 2 element model, the
  relationship `labels`/`directed` change, the `WALK` default, the `--` comment change, and the
  refusal of version 1 databases and snapshots. The release does not provide an in-place
  migration; users with 0.8 data must export with 0.8 first.
- Record the same changelog style rule in `AGENTS.md` so every future change writes release notes
  for users rather than implementers.
- Update the shell and CLI documentation examples that print a stale package version so they show
  `0.9.0`.
- Run the full validation set, build the distributions, smoke-test the installed wheel and CLI,
  and verify the tag/version contract.
- After review, create the `v0.9.0` tag. Pushing the tag triggers the existing release workflow,
  which publishes to PyPI; the push is a separate, explicit release decision.

This change adds no parser, engine, storage, dependency, or public API behavior. The behavior in
the release is the already-implemented `Unreleased` work.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a release and packaging change, so no spec-level behavior changes. The change sets
`skip_specs: true` in `.openspec.yaml` rather than inventing a release requirement.

## Impact

- `src/pygrafito/__about__.py` through `hatch version 0.9.0`.
- `CHANGELOG.md`: the 0.9.0 release section and the empty `Unreleased` section, rewritten in
  concise end-user language.
- `AGENTS.md`: a permanent rule for concise, friendly, end-user changelog entries.
- `docs/guides/shell.md` and `docs/reference/cli.md`: stale version banners in examples.
- The `v0.9.0` git tag and the tag-triggered `.github/workflows/release.yml` publication.
- No runtime code, schema, snapshot format, dependency, or public API change.
