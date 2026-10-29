# Spec Delta

## ADDED Requirements

### Requirement: Embedded CSV newline preservation

The CSV reader SHALL preserve newline characters inside quoted fields exactly as they
are encoded in the file and SHALL NOT apply the host platform's text-mode newline
translation to field contents.

#### Scenario: LF inside a quoted field

- **WHEN** a quoted CSV field contains `line one\nline two`
- **THEN** the imported value contains `line one\nline two`

#### Scenario: CRLF inside a quoted field

- **WHEN** a quoted CSV field contains `line one\r\nline two`
- **THEN** the imported value contains `line one\r\nline two`

#### Scenario: Windows host

- **WHEN** the same CSV bytes are imported on Windows and on Linux
- **THEN** the field content is identical on both platforms
