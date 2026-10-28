# Design

## Context

See `proposal.md` - Why. The version is `0.9.0`, read dynamically from
`src/pygrafito/__about__.py` by Hatch and by `docs/conf.py`. The `[Unreleased]` changelog block
holds 25 entries covering the query surface, the path engine, the frozen profile, and the
hardening work. The 1.0 gate in `docs/reference/gql-profile.md` is written as a future blocker,
and several pages still call Linux "the supported 1.0 platform".

The release workflow is tag-driven: pushing a `v*` tag runs `hatch check`, `hatch test`, verifies
the tag matches `__about__.py`, builds, runs `twine check`, and publishes to PyPI. The docs are
built by a separate CI job on every push, so the release validation must also run the docs build
locally.

`release-0-9` is the direct precedent. It used `skip_specs: true`, updated the version, moved the
changelog, fixed stale version banners, ran the full gate, and left the tag push as a separate
explicit step.

## Goals / Non-Goals

**Goals:**

- Publish `1.0.0` with a version, changelog, classifier, and documentation that agree.
- Leave no documentation that presents 1.0 as a future release.
- Keep the release mechanical: no new page, no new behavior, no new dependency.
- Validate the exact artifact that will be published, including the installed wheel and CLI.
- Keep the tag and publish steps explicit and reversible until the tag is pushed.

**Non-Goals:**

- No parser, engine, storage, dependency, or public API change.
- No migration page, no separate release-notes page, and no GitHub Release automation.
- No spec delta; the change declares `skip_specs: true`.
- No in-place migration and no claim of ISO conformance.
- No ingestion fast path or other optional follow-up promoted into 1.0.

## Decisions

### D1: Release as 1.0.0, not a release candidate or 0.10

The profile gate is met, the hardening work is archived, and no `deferred` or `gated` row remains.
A release candidate would add a version without changing the evidence. `0.10.0` would contradict
the profile-complete milestone and the API stability policy that already promises 1.x. The
remaining work is release hygiene, so `1.0.0` is the honest SemVer signal.

### D2: Use `hatch version 1.0.0` as the only version edit

`pyproject.toml` reads the version dynamically, and the release workflow compares the tag with
`__about__.py`. Editing either file by hand risks a mismatch. `docs/conf.py` reads the installed
metadata, so it follows automatically.

### D3: The changelog is the release record; add no separate release-notes artifact

The user chose a mechanical release. The `1.0.0` section carries the 25 existing end-user entries
and the **BREAKING** markers. A separate docs page, a GitHub Release, and a migration section in
the changelog would each be a new artifact with its own review surface.

Gate item 8 in the profile requires a changelog section, migration notes, and an out-of-profile
list. The latter two already exist in the profile page. The gate prose will point at those
sections instead of implying that the changelog must duplicate them.

Alternative considered: a `reference/release-notes.md` or `guides/migrating.md` page. Rejected for
this release because it expands a mechanical change into a documentation project and duplicates
material the profile already owns.

### D4: Rewrite the release gate in place; do not delete it

The `gql-profile` spec requires the profile to define a 1.0 release gate, and
`tests/test_gql_profile.py` enforces the profile-side checks. Removing the section would create
spec drift. The rewrite changes tense and framing:

- "The gate blocks 1.0 until every item is checked" becomes a statement of what 1.0 was gated on.
- The hardening item records that the work shipped, without naming the OpenSpec change.
- The release-notes item records that the changelog, migration guidance, and out-of-profile list
  exist, and points at them.
- The version item records `1.0.0`.
- "frozen at release" becomes "frozen at 1.0".

The heading `## 1.0 release gate` stays: it names the gate that was met, not a future event.

### D5: Remove future framing, keep 1.x compatibility claims

The cleanup targets sentences that present 1.0 as pending. It does not launder true statements.
The distinction:

| Rewrite | Keep |
| --- | --- |
| "the 1.0 target" and "changes that lead to 1.0" | "frozen for 1.x" |
| "Current release / 1.0 target" table columns | "a version 2 database written by 0.9 or 1.0 opens" |
| "the gate adds a test before it can pass" | "after 1.0, a construct may be added in a minor release" |
| "pre-1.0 target" in the migration guidance | "post-1.0 language direction" in the status vocabulary |
| "supported 1.0 platform" | numeric values such as `1.0` in constraints and benchmark ratios |

Platform-facing pages move from "1.0 platform" to "1.x platform", because the support promise
outlives the 1.0 release. The durable specs keep their existing 1.0 wording: 1.0 is the release
that established the platform, and this change deliberately does not open a spec delta to restyle
it.

### D6: Replace the stale rejected-forms cell with the real corpus case

`docs/reference/gql-profile.md` still says
`1.0 gate: add a focused parser test in complete-gql-profile` for catalog operations. That work is
done: `tests/conformance/cases.json` contains `catalog-insert-graph-is-rejected`. The cell becomes
that corpus case, which also satisfies the evidence-resolution check in the profile test. This is
the clearest example of the planning residue the cleanup removes.

### D7: Put Bit in the quickstart node example, not the landing page

`Bit` already exists in `examples/data/grid.json` as a `Program` with `cycles=1` and `active=true`,
and `examples/tours/01-match.gql` matches it. The docs never mention it. The quickstart section 3
example is the right home:

- It already introduces the strict value model in prose but never shows a boolean.
- Bit's yes/no character makes `active=True` memorable.
- The section opens its own in-memory graph and introduces no relationship, so the existing
  relationship diagram in section 4 stays correct and no new Mermaid block is required.
- The `find_nodes("Program", active=True)` call demonstrates a boolean predicate and returns
  `['Bit']`.

Alternative considered: the README landing snippet. Rejected because it changes the first example
every reader sees and its printed output, for no additional teaching value.

### D8: Update the classifier with the release

`Development Status :: 4 - Beta` contradicts a 1.0 release and the frozen public API policy. It
becomes `5 - Production/Stable` in the same change. This is metadata only; no dependency or
build change.

### D9: Keep the tag and the publish separate

The full gate runs and the wheel is smoke-tested on a clean commit. The annotated `v1.0.0` tag is
created locally after review; pushing it is the publication action because the workflow publishes
on any `v*` tag. A failed release is fixed with a new patch version, never a re-tag.

### D10: No spec delta

This change packages and documents behavior that already shipped. `.openspec.yaml` sets
`skip_specs: true`, following `release-0-9`. A synthetic "release" capability would create a
requirement with no behavioral meaning.

## Risks / Trade-offs

- **[The tag push publishes immediately]** -> Run the full gate first, create the tag on the
  reviewed commit, and keep the push as a separate explicit step.
- **[Version and changelog drift]** -> Use `hatch version`, assert `hatch version` reports
  `1.0.0`, inspect the wheel metadata, and rely on the workflow's tag/version check.
- **[Stale future-1.0 wording is missed]** -> Search the source docs for `1.0`, `pre-1.0`,
  `target`, and `pygrafito 0.9.0` before the build, and review every hit against the keep/rewrite
  table. Exclude `docs/_build`.
- **[The docs rewrite breaks the profile test]** -> The test parses the conformance matrix and the
  construct inventory, not the status table or the gate prose. Keep both parsed tables unchanged
  and run `tests/test_gql_profile.py` after the edit.
- **[The Bit snippet breaks the executable-docs test]** -> `tests/test_docs_examples.py` runs every
  quickstart Python fence. The snippet is deterministic and uses only supported values.
- **[Classifier and package metadata diverge]** -> Update the classifier in the same commit as the
  version, and inspect the built wheel metadata before tagging.
- **[Specs and docs use different 1.0/1.x wording]** -> Accept for this release. The specs describe
  the 1.0 contract; the docs describe the 1.x support promise. A wording sync would be a separate
  spec change, not release hygiene.
- **[A published artifact cannot be replaced]** -> Treat a bad release as `1.0.1`, not a re-tag;
  yank only if the artifact is unsafe.

## Migration Plan

1. Confirm a clean tree, the intended branch, and no other active change; record the commit and the
   release date.
2. Run `hatch version 1.0.0` and update the classifier.
3. Move the `[Unreleased]` entries into `## [1.0.0] - 2026-10-28`, leave `[Unreleased]` empty, and
   review the section as an end user.
4. Apply the future-1.0 documentation pass and the Bit cameo; run the profile and docs tests.
5. Run `hatch check --fix`, `hatch test`, `hatch run docs:build`, and `scripts/verify --docs`.
6. Build `dist/`, run `twine check`, install the wheel in a clean environment, and smoke-test the
   package and CLI.
7. Commit the release, create the annotated `v1.0.0` tag, then push the tag after approval and
   verify the workflow publishes the expected artifacts.

Rollback: before publication, delete the local tag and revert the release commit. After
publication, do not re-tag; publish `1.0.1`.
