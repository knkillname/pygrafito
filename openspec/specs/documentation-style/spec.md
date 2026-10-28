# documentation-style Specification

## Purpose

The documentation site teaches `pygrafito` through a warm, consistent visual language while keeping
the reference precise and authoritative.

## Requirements

### Requirement: Zone-appropriate documentation voice

The documentation SHALL use a warm, instructional voice on the landing page, the quickstart, and
the guides, and a precise reference voice in the reference pages. Generated API pages SHALL keep
their generated structure. A guide SHALL lead with the outcome the reader can achieve.

#### Scenario: Guide opens with an outcome

- **WHEN** a reader opens a guide
- **THEN** the opening paragraph states the task the page completes in the second person

#### Scenario: Reference stays precise

- **WHEN** a reader opens a query-language or profile reference page
- **THEN** the page states rules and edge cases without instructional asides

### Requirement: Page summary

Every reader-facing page except generated API reference pages SHALL open with a `tl;dr` callout
immediately after the page title. The callout SHALL summarize the page's outcome in at most three
sentences and SHALL NOT claim behavior the page does not describe.

#### Scenario: Guide has a summary

- **WHEN** a reader opens a landing, quickstart, guide, or reference page
- **THEN** the first content block after the title is a `tl;dr` callout

#### Scenario: API page has no summary

- **WHEN** a reader opens a generated API page
- **THEN** no `tl;dr` callout is required

### Requirement: Fixed callout vocabulary

Documentation SHALL use exactly five callout types: `tl;dr` for the page summary, `Tip` for an
optional shortcut, `Warning` for a risk of data loss or a wrong result, `Remember` for the one rule
to carry away, and `In detail` for optional technical depth. Each type SHALL keep its fixed title.
Callouts SHALL NOT be nested, and a callout SHALL replace prose rather than repeat it.

#### Scenario: Tip marks a shortcut

- **WHEN** a page offers a faster or nicer optional way to do something
- **THEN** the page uses a `Tip` callout

#### Scenario: Warning marks a risk

- **WHEN** an action can lose data or produce a wrong result
- **THEN** the page uses a `Warning` callout before the action

#### Scenario: Remember marks a key rule

- **WHEN** a page states one rule the reader should carry away
- **THEN** the page uses a `Remember` callout

#### Scenario: In detail marks optional depth

- **WHEN** a page offers technical depth the reader can safely skip
- **THEN** the page uses an `In detail` callout

#### Scenario: No nested callouts

- **WHEN** a page needs both optional depth and a warning
- **THEN** the callouts appear as separate blocks, not one inside the other

### Requirement: Consistent emoji and badges

Emoji SHALL appear only in card titles and badges. Emoji SHALL NOT appear in headings, body prose,
callout titles, or diagrams. Within a card grid or badge collection, every item SHALL carry an
emoji or none SHALL.

#### Scenario: Card grid is all-or-nothing

- **WHEN** a page shows a grid of cards
- **THEN** every card title has an emoji or no card title does

#### Scenario: Heading anchors stay predictable

- **WHEN** a heading is added to a page
- **THEN** it contains no emoji, so its anchor is derived from words alone

### Requirement: Graph examples begin with a diagram

Every example that introduces a graph shape SHALL present a diagram of that graph before the first
code snippet. The diagram SHALL use the same node names, labels, property names, and relationship
types as the example. Later variations of the same shape SHALL reuse the diagram by reference
rather than redraw it.

#### Scenario: Quickstart shows the graph

- **WHEN** a reader reaches the first node-and-relationship example
- **THEN** a diagram of those nodes and that relationship appears before the code

#### Scenario: Variation reuses the shape

- **WHEN** a later snippet changes only a property or filter on the same graph
- **THEN** the page refers to the earlier diagram instead of adding a second one

### Requirement: Accessible diagrams and build failure

Every diagram SHALL include an accessible title and description and SHALL NOT rely on colour alone.
The built documentation SHALL display diagrams as static images without requiring a client-side
runtime or network access. A diagram that cannot be rendered SHALL fail the documentation build.

#### Scenario: Screen reader gets a description

- **WHEN** a diagram is rendered in the documentation
- **THEN** its image exposes a title and a description of the graph

#### Scenario: Malformed diagram fails the build

- **WHEN** a diagram source cannot be parsed
- **THEN** the documentation build fails with the page and diagram identified

#### Scenario: Offline reading

- **WHEN** a reader opens a documentation page without network access
- **THEN** every diagram is still visible

### Requirement: Published style guide

The documentation site SHALL publish a style guide reachable from its navigation. The guide SHALL
define the zone voices, show each of the five callout types rendered, state the emoji and badge
rules, and describe the graph-diagram convention.

#### Scenario: Contributor finds the rules

- **WHEN** a contributor opens the documentation navigation
- **THEN** a documentation style guide entry is available

#### Scenario: Callouts are demonstrated

- **WHEN** a reader opens the style guide
- **THEN** each of the five callout types appears with a rendered example
