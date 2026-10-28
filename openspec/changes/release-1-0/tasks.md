# Tasks

## 1. Preflight and version

- [x] 1.1 Run `openspec validate "release-1-0" --strict` and `openspec status --change "release-1-0" --json`; verify the change validates, `specs` reports `skipped`, and no other change is active.
- [x] 1.2 Confirm the intended release point with `git status --short`, `git branch --show-current`, and `git rev-parse HEAD`; verify the tree is clean and record the commit SHA and the release date (2026-10-28).
- [x] 1.3 Confirm `hatch version` reports `0.9.0` and `pyproject.toml` still reads the version dynamically from `src/pygrafito/__about__.py`; verify with `hatch version` and `grep -n "dynamic\|hatch.version" pyproject.toml`.
- [x] 1.4 Run `hatch version 1.0.0`; verify `hatch version` reports `1.0.0` and `src/pygrafito/__about__.py` contains `__version__ = "1.0.0"`. Do not edit the version file or `pyproject.toml` by hand.
- [x] 1.5 Change the `Development Status` classifier in `pyproject.toml` from `4 - Beta` to `5 - Production/Stable`; verify with `grep -n "Development Status" pyproject.toml` and confirm no other classifier changed.

## 2. Changelog 1.0.0

- [x] 2.1 Move every entry under `## [Unreleased]` into `## [1.0.0] - 2026-10-28` and leave an empty `## [Unreleased]` section at the top; verify with `grep -n "^## " CHANGELOG.md | head -4` that the order is Unreleased, 1.0.0, 0.9.0.
- [x] 2.2 Review the 1.0.0 section as an end user: keep one or two outcome-focused sentences per entry, preserve every **BREAKING** marker and its migration step, and keep the Added, Changed, and Fixed categories without empty headings; verify a focused read of the section and `git diff CHANGELOG.md`.
- [x] 2.3 Verify the release record is complete without new artifacts: the changelog names the 1.0.0 section, and the profile still owns the migration guidance and the out-of-profile list; confirm no migration or release-notes page was added with `git status --short`.

## 3. Documentation future-1.0 pass

- [x] 3.1 Rewrite `docs/reference/gql-profile.md` so 1.0 is the shipped release: replace "target language profile" and "changes that lead to 1.0" in the introduction, and collapse the `| Area | Current release | 1.0 target |` table into one supported-surface column; verify with `grep -n "1.0 target\|lead to 1.0" docs/reference/gql-profile.md` returning nothing and `hatch test tests/test_gql_profile.py` passing.
- [x] 3.2 Put the release gate, profile-freeze policy, rejected-forms table, and migration guidance in the present or past tense: state what 1.0 was gated on, record the hardening as shipped, point gate item 8 at the existing migration guidance and out-of-profile list, record the version as `1.0.0`, change "frozen at release" to "frozen at 1.0", and replace `1.0 gate: add a focused parser test in complete-gql-profile` with the `catalog-insert-graph-is-rejected` corpus case; verify with `grep -n "1.0 gate: add\|pre-1.0 target\|blocks 1.0" docs/reference/gql-profile.md` returning nothing and `hatch test tests/test_gql_profile.py` passing.
- [x] 3.3 Change the platform label from "supported 1.0 platform" to "supported 1.x platform" in `README.md`, `docs/index.md`, `docs/getting-started/quickstart.md`, and `docs/reference/platform-support.md`, and change "the 1.0 contract" to "the 1.x contract" in `docs/reference/query-language.md`; verify `grep -rn "supported 1.0 platform" README.md docs --exclude-dir=_build` returns nothing and `grep -rn "1.x platform\|1.x contract" README.md docs --exclude-dir=_build` shows the updated pages.
- [x] 3.4 Update the shell and CLI session banners from `0.9.0` to `1.0.0` in `docs/guides/shell.md` and `docs/reference/cli.md`; verify `grep -rn "pygrafito 0.9.0" docs --exclude-dir=_build` returns nothing and `grep -rn "pygrafito 1.0.0" docs --exclude-dir=_build` lists the two pages.
- [x] 3.5 Add the Bit cameo to the quickstart section 3 node example: add `bit = graph.add_node("Program", designation="Bit", cycles=1, active=True)`, print `bit["designation"]` and `bit["active"]`, and add `graph.find_nodes("Program", active=True)` returning `['Bit']` in the `find_nodes` example; verify `hatch test tests/test_docs_examples.py` passes and the relationship diagram in section 4 still matches its snippet.
- [x] 3.6 Run `hatch run docs:build` with warnings as errors; verify it succeeds, the rendered site reports version 1.0.0, and `hatch test tests/test_docs_style.py` passes.

## 4. Full validation and distribution artifacts

- [x] 4.1 Run `hatch check --fix`; verify Ruff and Pyrefly pass and the formatter changed no unexpected files with `git diff --check` and `git status --short`.
- [x] 4.2 Run `hatch test`; verify the full suite passes and coverage is at least 80%.
- [x] 4.3 Run `hatch run docs:build`; verify it exits successfully with warnings treated as errors.
- [x] 4.4 Run `scripts/verify --docs`; verify `hatch check`, both supported Python test environments, the pinned SQLite container, and the docs build all pass.
- [x] 4.5 Run `uv build`, then `uvx twine check dist/*`; verify the distribution filenames contain `1.0.0` and both commands accept every artifact.
- [x] 4.6 Install the built wheel in a clean environment on Python 3.13 and 3.14; verify `importlib.metadata.version("pygrafito") == "1.0.0"`, an in-memory graph opens, the installed `pygrafito --help` and `python -m pygrafito --help` commands work, the wheel contains `py.typed` and `LICENSE.txt`, and the metadata reports `5 - Production/Stable`.
- [x] 4.7 Verify the release contract the tag will use: `v$(hatch version)` equals `v1.0.0`, the wheel metadata reports `1.0.0`, and `grep -nF "## [1.0.0]" CHANGELOG.md` matches the release date.

## 5. Release commit and tag

- [x] 5.1 Review `git status` and `git diff`; verify the release commit contains only the version, classifier, changelog, documentation, and this OpenSpec change, with no build output or local artifacts. Commit as `chore: release 1.0.0` and verify with `git show --stat HEAD`.
- [x] 5.2 Create an annotated `v1.0.0` tag on the release commit; verify `git tag -n v1.0.0` shows the annotation and `git rev-parse v1.0.0^{}` matches `git rev-parse HEAD`. Do not push the tag in this task.
- [ ] 5.3 After explicit maintainer approval, push the release commit and the `v1.0.0` tag; verify the release workflow's check, test, tag/version, build, twine, and publish steps succeed and PyPI serves `pygrafito 1.0.0`.

## 6. Post-release verification

- [ ] 6.1 Install `pygrafito==1.0.0` from PyPI in a clean environment; verify the version, an in-memory graph round trip, and the `pygrafito --help` command.
- [ ] 6.2 Verify the documentation site built from the release commit reports version 1.0.0 and the GQL profile no longer describes 1.0 as a future release.

## Workflow follow-up

- Archive the change after the release is published and the project's review requirements are satisfied.
- Create the Git commit required after archive, and confirm the archived change validates.
- Update the roadmap status in `tmp/planning.md` only after the archive cycle is complete; it is a scratch roadmap, not a durable spec.
- If a published 1.0.0 artifact is broken, do not re-tag the same version; publish a fixed 1.0.1 and yank only if the artifact is unsafe.
