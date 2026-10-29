# platform-support Specification

## Purpose

Defines the Python versions, operating systems, SQLite minimum, and installation guarantees a
pygrafito user can rely on.

## Requirements

### Requirement: Supported Python versions

The package SHALL install and run on CPython 3.13 and 3.14. The declared `requires-python` SHALL be
`>=3.13`. The runtime SHALL depend only on the Python standard library.

#### Scenario: Install on the floor

- **WHEN** a user installs the wheel in a clean Python 3.13 environment
- **THEN** installation succeeds and the graph opens

#### Scenario: Install on the newest supported version

- **WHEN** a user installs the wheel in a clean Python 3.14 environment
- **THEN** installation succeeds and the graph opens

#### Scenario: Older interpreter is refused by the installer

- **WHEN** a user attempts to install on Python 3.12
- **THEN** the installer refuses because the package requires 3.13 or newer

#### Scenario: No third-party runtime dependency

- **WHEN** the package is imported in an environment with no third-party packages
- **THEN** every graph, query, and CLI feature works

### Requirement: Linux support and portability signal

Linux with glibc and SQLite 3.38 or newer SHALL be the supported 1.0 platform. macOS and Windows
SHALL run the same test suite nightly as a non-blocking signal and SHALL NOT be claimed as
supported until that signal is green.

#### Scenario: Linux is the gate

- **WHEN** the Linux test suite fails on a supported Python version
- **THEN** the release is blocked

#### Scenario: Nightly portability report

- **WHEN** the nightly macOS or Windows suite fails
- **THEN** the failure is reported but does not block a release

#### Scenario: Supported SQLite floor

- **WHEN** the graph opens on SQLite 3.38 or newer
- **THEN** all documented operations work

#### Scenario: Older SQLite is refused

- **WHEN** the graph opens on a SQLite runtime older than 3.38
- **THEN** it reports an unsupported runtime error

#### Scenario: Untested Linux variants are not claimed

- **WHEN** a user runs on musl or a distribution without the required SQLite functions
- **THEN** the documentation does not claim support

### Requirement: Pure-Python distribution

The project SHALL publish a pure-Python wheel that installs without a compiler or a system SQLite
build step and SHALL include the `py.typed` marker and license file.

#### Scenario: Wheel tag

- **WHEN** the distribution is built
- **THEN** the wheel is platform-independent and contains no compiled extension

#### Scenario: Typed package

- **WHEN** the wheel is inspected
- **THEN** `py.typed` and `LICENSE.txt` are present

#### Scenario: Clean install

- **WHEN** the wheel is installed on a supported platform without build tools
- **THEN** installation succeeds

### Requirement: Blocking gate and nightly evidence

The project SHALL run the full suite on every supported Python version on Linux for each change,
and SHALL run the suite on macOS and Windows on a nightly schedule.

#### Scenario: Pull request gate

- **WHEN** a change is proposed
- **THEN** the Linux suite runs on 3.13 and 3.14 before merge

#### Scenario: Nightly schedule

- **WHEN** the nightly schedule fires
- **THEN** the suite runs on macOS and Windows for 3.13 and 3.14

#### Scenario: Nightly failure is visible

- **WHEN** a nightly job fails
- **THEN** the failure is reported to the maintainer without blocking the next release

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
