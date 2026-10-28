# Tasks

## 1. Verification command and hook

- [x] 1.1 Add `scripts/verify` with `set -eu`, repository-root resolution, `--skip-sqlite` and
  `--docs` flags, and a clear failure when Docker, Compose, or the daemon is unavailable. Verify
  `sh -n scripts/verify`, `test -x scripts/verify`, and `scripts/verify --skip-sqlite` exit 0.
- [x] 1.2 Add tests for the verification command using PATH stubs for `hatch` and `docker`,
  covering the default command sequence, `--skip-sqlite`, `--docs`, a missing Docker environment,
  and a failing stage short-circuiting later stages. Verify
  `hatch test tests/test_pre_push.py::TestVerifyScript` passes.
- [x] 1.3 Add the executable `.githooks/pre-push` script. It must skip pure deletions, abort on a
  dirty tracked tree or a pushed ref that is not `HEAD`, map `PREGRAFITO_SKIP_SQLITE=1` to
  `--skip-sqlite`, detect docs changes from the pushed range, and call `scripts/verify` once.
  Verify `sh -n .githooks/pre-push` and `test -x .githooks/pre-push`.
- [x] 1.4 Add tests for the hook using a temporary git repository and a local bare remote, covering
  a clean code push, a docs-only push, a new branch, a pure deletion, a dirty tracked tree, a
  mismatched `HEAD`, and the `PREGRAFITO_SKIP_SQLITE=1` path. Verify
  `hatch test tests/test_pre_push.py::TestPrePushHook` passes.

## 2. Documentation and validation

- [x] 2.1 Update `docs/contributing/testing.md` with the one-time `git config core.hooksPath
  .githooks` setup, what the hook runs, the clean-tree and HEAD rules, the Docker opt-out, the docs
  trigger, and the manual `scripts/verify` command. Verify `hatch run docs:build` succeeds with no
  warnings.
- [x] 2.2 Update the Development section in `README.md` and the Commands section in `AGENTS.md`
  with `scripts/verify` and the hook setup. Verify the documented commands match the implemented
  flags and run `scripts/verify --skip-sqlite` as written.
- [x] 2.3 Add an entry under `## [Unreleased]` in `CHANGELOG.md` describing the new pre-push check
  and manual verification command. Verify the entry uses the Keep a Changelog categories and is
  written for contributors rather than internal class names.
- [x] 2.4 Run `openspec validate add-pre-push-check --strict` and
  `openspec validate --specs --strict`; verify both pass. The change sets `skip_specs: true`
  because it changes development tooling only.

## 3. Integration verification

- [x] 3.1 Run `hatch check` and `hatch test`; verify the full suite and coverage gate pass.
- [x] 3.2 Run `scripts/verify --skip-sqlite` and then `scripts/verify` with Docker available; verify
  both succeed and print one labeled result per stage.
- [x] 3.3 Run `hatch run docs:build`; verify the site builds with warnings treated as errors.
- [x] 3.4 In a scratch clone, enable `core.hooksPath`, push a clean commit to a local bare remote,
  and verify the hook runs and the push succeeds. Make a tracked file dirty and verify the next
  push aborts.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Consider extending the hook to the package/wheel smoke job and `src/**` docs triggers in a later
  change; both are deliberately out of scope here.
