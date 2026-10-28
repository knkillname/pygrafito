# Design: release 0.9.0

## Context

See `proposal.md` for the motivation. The package version is currently `0.8.0`, read dynamically
from `src/pygrafito/__about__.py` by Hatch and by `docs/conf.py`. The `Unreleased` changelog block
already contains the behavior that will ship: the version 2 element model, the GQL path-mode
surface, the query budget, and the composition surface. No code feature work is needed for this
release.

The release workflow is tag-driven: pushing a `v*` tag runs `hatch check`, `hatch test`, builds
distributions, checks them with `twine`, verifies that the tag matches `__about__.py`, and then
publishes to PyPI. The documentation build is a separate workflow, so the release validation must
also run it locally.

The project is pre-1.0. The 0.9.0 release writes schema version 2 and snapshot version 2, and
refuses version 1 databases and snapshots. That compatibility break is already implemented and
documented; this release makes it available to users rather than changing it.

The current `Unreleased` entries are written for implementers: they name internal classes, SQL
details, tests, and file paths. The new project rule in `AGENTS.md` requires changelog entries to
be short, friendly, and useful to end users, so the release must rewrite them rather than move
them verbatim.

## Goals / Non-Goals

**Goals:**

- Publish a coherent 0.9.0 checkpoint with a version, changelog, and documentation that agree.
- Make the release notes honest about the breaking changes and the still-incomplete GQL profile.
- Make the 0.9.0 notes short, friendly, and readable by end users, not only by implementers.
- Validate the exact artifact that will be published, including the installed wheel and CLI.
- Keep the tag/publish step explicit and reversible up to the point of publishing.

**Non-Goals:**

- No parser, engine, storage, dependency, or public API change.
- No in-place migration from 0.8 or schema version 1.
- No claim of GQL profile completeness or ISO conformance.
- No new changelog categories or release automation.
- No spec delta: this is release hygiene, not a behavior requirement.

## Decisions

### D1: Release as 0.9.0, not 1.0.0 or 0.8.1

The accumulated work contains breaking API, query-semantics, and storage-format changes. A
pre-1.0 minor release is the honest SemVer signal. `1.0.0` would claim the profile-complete
milestone before the deferred path and expression work lands. `0.8.1` would imply a compatible
patch when the element model and default path mode have changed.

### D2: Rewrite the release notes for end users, not implementers

The git history and pull requests remain the detailed engineering record. The changelog should be
a friendly, scannable account of what users can now do. Move the entries into a dated `## [0.9.0]`
section, leave `## [Unreleased]` empty, and rewrite each user-visible change as one or two short
sentences that state the outcome. Preserve every feature, fix, removal, `**BREAKING**` marker, and
migration step, but remove internal class or function names, SQL details, test names, file paths,
and implementation mechanics.

A short summary above the categories records the milestone, the profile's incomplete status, and
the 0.8 export constraint. Encode the same style rule in `AGENTS.md` under Versioning and changelog
so every future change inherits it. Moving the entries verbatim would be faster, but it would make
the release notes a second engineering log and hide the user-facing changes.

### D3: Use `hatch version 0.9.0` as the only version edit

`pyproject.toml` reads the version dynamically from `src/pygrafito/__about__.py`. Editing that file
or `pyproject.toml` by hand risks a mismatch with the release workflow's tag check. `hatch version
0.9.0` updates the authoritative file and keeps the documentation build's metadata version in
sync.

### D4: Update only stale version examples in the documentation

`docs/conf.py` derives the documentation version from installed package metadata, so it needs no
source edit. The shell and CLI pages contain hand-written session banners from older releases:
`0.8.0` in one shell example and `0.6.0` in the read-only shell and CLI examples. Update those
banners to `0.9.0`, then run the Sphinx build. Do not edit generated files under `docs/_build/`;
they are build output.

Leave the 0.8 migration guidance intact. Statements such as "export an existing 0.8 graph with
0.8 first" remain correct for users crossing the schema version 2 break.

### D5: No spec delta; mark the change `skip_specs`

The release changes packaging, documentation, and release notes, not system behavior. A synthetic
"release" capability would create a requirement with no behavioral meaning. `.openspec.yaml`
therefore sets `skip_specs: true`, and the proposal records that no capabilities change.

### D6: Gate the tag and publish separately

Validation and artifact inspection happen on a clean commit. Creating the annotated tag is the
release action; pushing it is the publication action because the existing workflow publishes on
any `v*` tag. The tasks stop before the push so a maintainer can review the exact tag target. This
keeps an accidental push from publishing an unverified artifact.

### D7: Treat the 0.8 to 0.9 migration as an export, not an upgrade

The release does not add a migration. A 0.8 database or snapshot is refused. The release summary
and release notes point users to export with 0.8 before upgrading. This is a continuation of the
already-documented version 2 decision, not a new compatibility promise.

## Risks / Trade-offs

- **[Tag push publishes immediately]** → Create the tag only after the full validation and review;
  keep the push as a separate explicit step and verify the tag target first.
- **[Version and changelog drift]** → Use `hatch version`, assert `hatch version` reports `0.9.0`,
  inspect the built wheel metadata, and rely on the release workflow's tag/version check.
- **[Stale documentation banners]** → Search the source docs for `pygrafito 0.8.0` and `pygrafito
  0.6.0`, update the examples, and build with warnings as errors.
- **[Release notes read like an engineering log]** → Apply the concise end-user checklist in
  `AGENTS.md`; keep internals in git history and review the final 0.9.0 section as a user would.
- **[0.8 users cannot open their data]** → Make the breaking change prominent in the 0.9.0 summary
  and keep the export-with-0.8 guidance in the embedding and snapshot references.
- **[A published artifact cannot be replaced]** → Treat a bad release as a new patch release
  (0.9.1), not a re-tag; yank only if the artifact is unsafe.
- **[Release from a dirty tree or the wrong commit]** → Preflight checks the branch, the working
  tree, and the commit before tagging; tag only the reviewed release commit.

## Migration Plan

1. Confirm the release commit and clean working tree.
2. Run `hatch version 0.9.0`.
3. Move the `Unreleased` entries into `## [0.9.0] - <release date>`, rewrite them in concise
   end-user language, add the release summary, and leave `## [Unreleased]` empty.
4. Update the stale version banners in the shell and CLI documentation.
5. Run `hatch check --fix`, `hatch test`, `hatch run docs:build`, and whitespace checks.
6. Build `dist/`, run `twine check`, install the wheel in a clean environment, and smoke-test the
   package and CLI.
7. Commit the release changes and create the annotated `v0.9.0` tag.
8. After review, push the tag and verify the release workflow publishes the expected artifacts.

Rollback: before publication, delete the local tag and amend or revert the release commit. After
publication, do not re-tag the same version; publish a fixed patch and, if necessary, yank the
broken artifact. A 0.9 database cannot be opened by 0.8; preserve a 0.8 export or backup before
upgrading.
