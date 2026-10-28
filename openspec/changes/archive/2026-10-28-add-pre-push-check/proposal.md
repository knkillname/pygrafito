# Proposal

## Why

A local `hatch test` run and the CI test job can use different SQLite libraries. Local Python often
bundles a recent SQLite, while the CI runner uses the system library. That difference let a change
pass locally on SQLite 3.53 and fail in CI on SQLite 3.45.1. There is no local gate before
`git push`, so CI remains the first place a version-specific or documentation regression appears.

## What Changes

- Add a versioned `pre-push` hook under `.githooks/` and document the one-time
  `git config core.hooksPath .githooks` setup.
- Make the hook refuse to run when tracked files differ from `HEAD` or when the pushed ref is not
  `HEAD`, so it checks the commit being pushed rather than an unrelated working tree.
- Run `hatch check` without `--fix`, `hatch test` for both Python 3.13 and 3.14, and
  `docker compose run --rm test-sqlite`, which pins the SQLite release used by CI.
- Fail with a clear message when Docker or Compose is unavailable, unless
  `PREGRAFITO_SKIP_SQLITE=1` is set. `git push --no-verify` remains the full bypass.
- Build the documentation with `hatch run docs:build` only when the pushed range changes
  `docs/**` or `README.md`; new branches and tags build it conservatively.
- Expose the same checks as a documented manual command so a contributor can run them without
  pushing.
- Document the hook in the testing guide and README, and add a changelog entry.

## Capabilities

None. This change affects local development tooling only. It does not change library behavior, the
public API, the CLI, the stored format, or the GQL profile, so no capability spec is created or
modified. The change declares `skip_specs: true`.

### New Capabilities

- None.

### Modified Capabilities

- None.

## Impact

- New `.githooks/pre-push` hook and `scripts/verify` command.
- New pytest coverage for the hook and verification command under `tests/`.
- Documentation updates in `docs/contributing/testing.md`, `README.md`, `AGENTS.md`, and
  `CHANGELOG.md`.
- Reuses `compose.yaml` and `docker/Dockerfile`; no runtime dependency is added.
- No changes to `src/`, package dependencies, or the public API.
