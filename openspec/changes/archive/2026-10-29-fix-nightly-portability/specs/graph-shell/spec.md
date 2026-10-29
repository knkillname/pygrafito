# Spec Delta

## ADDED Requirements

### Requirement: Native path arguments

Shell dot-command path arguments SHALL preserve the host platform's path separators.
On Windows, an unquoted path containing backslashes or a drive letter SHALL be treated
as one path value, and quoted paths SHALL remain the way to include spaces. Export,
restore, backup, and import SHALL use the same path parsing rules.

#### Scenario: Export to a Windows path

- **WHEN** a caller submits `.export C:\grid\snapshot.jsonl` on Windows
- **THEN** the snapshot is written to that exact path and the backslashes are not treated
  as escapes

#### Scenario: Import from a Windows path

- **WHEN** a caller submits `.import C:\grid\programs.csv --statement "..."` on Windows
- **THEN** the file at that path is read

#### Scenario: Quoted Windows path with spaces

- **WHEN** a caller submits `.backup "C:\Grid Files\backup.db"` on Windows
- **THEN** the quoted path with spaces is accepted as one argument

#### Scenario: POSIX paths keep their behavior

- **WHEN** a caller submits an export, restore, backup, or import path on Linux or macOS
- **THEN** the path is parsed exactly as before

### Requirement: Deterministic redirected output

Output written through `.output` or `.once` SHALL use `\n` line endings on every
platform, independent of the host text-mode newline default.

#### Scenario: Redirected output on Windows

- **WHEN** a caller redirects a result to a file on Windows
- **THEN** the file contains `\n` line endings and the same text as a redirect on Linux or
  macOS

#### Scenario: One-shot output on Windows

- **WHEN** a caller redirects one result with `.once` on Windows
- **THEN** that file also uses `\n` line endings
