# Spec Delta

## ADDED Requirements

### Requirement: Windows signal and POSIX-only tooling

The nightly Windows job SHALL run the library, CLI, import, interop, and constraint test
suites on every supported Python version. Tests for developer tooling that requires a
POSIX shell SHALL run through an available POSIX shell or skip with a clear platform
marker; they SHALL NOT fail solely because Windows cannot execute a shell script
directly. The documentation SHALL identify which local scripts require a POSIX shell.

#### Scenario: Windows library signal

- **WHEN** the nightly Windows job runs on Python 3.13 or 3.14
- **THEN** the library, CLI, import, interop, and constraint suites run normally

#### Scenario: POSIX-only tooling on Windows

- **WHEN** a test targets the pre-push hook or the verification shell script on Windows
- **THEN** it runs through a POSIX shell when one is available, or skips with an explicit
  platform reason

#### Scenario: Tooling documentation

- **WHEN** a Windows user reads the verification guide
- **THEN** the page states that `scripts/verify` and the Git hook require a POSIX shell or
  Git Bash
