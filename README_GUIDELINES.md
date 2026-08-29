# README guidelines

A Hraness README is the public contract for a repository. It should let a new
reader decide what the project is, reach one verified result, understand the
important boundaries, and find deeper documentation without knowing the
project's history.

These guidelines define an information architecture, not a fixed template.
Use the smallest shape that answers the real questions for the project.

## Build a trust path

Order the README around the reader's decisions:

1. **What is this?** Name the product, its stable category, the problem
   boundary, the mechanism that distinguishes it, and the outcome it enables.
2. **Why does it exist?** Explain the few design choices that determine when
   someone should use it. Pair each benefit with its mechanism and nearest
   limit.
3. **How do I reach first value?** Give the shortest supported install and one
   complete, copyable task. Show the result or say exactly what changes.
4. **How does it behave?** Describe the normal workflow with observable verbs,
   stable terms, and representative commands or code.
5. **What should I not infer?** Put compatibility, privacy, security, failure,
   and product-scope boundaries where the corresponding misunderstanding first
   becomes likely.
6. **How are the claims checked?** Name the deterministic gate, meaningful
   external checks, and any skipped or credential-gated evidence.
7. **Where is the rest?** Link to deeper documentation by reader task.

Complex, trust-sensitive tools often need every step. A small library may need
only the definition, install, example, API boundary, compatibility, and
verification.

## Open with the durable product

The first paragraph should survive a change in interface or implementation.
Use one compact paragraph, with as many sentences as needed, to establish:

- the product category and intended reader;
- the concrete problem boundary;
- the mechanism or invariant that differentiates the project; and
- the result a user can obtain.

Describe the stable identity before today's interface. A tool can be a durable
runtime even if the terminal is its current client. A package can own a data
contract even if one CLI is its most visible entry point.

Keep the first paragraph consistent with the package description, GitHub About
description, social metadata, and website. Those surfaces may shorten the
language, but they must not make a different claim.

## Make “why” claims earn their space

A useful “Why” item has four parts when the product supports them:

- a short name for the value;
- the mechanism that produces it;
- behavior under failure or pressure; and
- the nearest boundary or non-claim.

Write “the importer validates every manifest before it opens the database,”
then name what remains outside that guarantee. Avoid claims such as “powerful,”
“seamless,” or “production-ready” unless the following text supplies observable
evidence.

Use the project's real vocabulary. Repeat a term when it names an invariant.
Do not import words such as “bounded,” “canonical,” or “durable” merely because
they sound technical.

## Show one finished task

Installation alone is not first value. Follow it with one complete task that
fits the main audience:

- a CLI command and representative result;
- an input-to-output media job;
- a small library program and its returned value;
- a local data import followed by a useful query; or
- a UI action with restrained visual evidence.

Keep the example runnable against the documented release. State prerequisites
before the command. Explain material filesystem, network, account, cost, or
provider effects beside the step that causes them.

Do not make the reader assemble a first task from a command reference. Move
provider matrices, migration history, configuration catalogs, and exhaustive
examples below the first successful journey or into focused documentation.

## Explain behavior through evidence

Use concrete verbs and named objects. Say what the command reads, validates,
writes, returns, or refuses. Include enough detail to make a claim credible,
then link to the contract, architecture, or reference page that owns the full
mechanism.

Treat limitations as product information:

- correct a likely misreading beside the related feature;
- keep a dedicated limitations section for important scope exclusions;
- keep a distinct security or trust boundary when generated code, credentials,
  private data, external effects, or untrusted input are involved; and
- report a skipped external check as unverified, not passed.

The README must describe shipped behavior. Keep internal phases, ticket names,
private paths, migration chronology, and assumed repository history out of the
public narrative.

## Move depth into task-oriented docs

The README is a front door and working contract. It is not the only manual.
Move detail when it interrupts the trust path or serves a narrower reader.

Organize deeper documentation around tasks such as:

- getting started;
- using the CLI, SDK, or application;
- operating providers or deployments;
- integrating and extending;
- understanding architecture and data contracts;
- security, privacy, and recovery; and
- contributing and release verification.

Link at the point where the README stops. A final documentation map may group
these destinations by reader intent. Do not expose the repository directory
tree as if it were an information architecture.

## Adapt the shape to the project

| Project shape | Early path | Depth to retain | Depth to move |
| --- | --- | --- | --- |
| CLI or Agent Skill | Definition, why, install, one finished task | Core workflow, effects, trust, limits, verification | Provider and command reference, migrations, advanced operations |
| Library or SDK | Definition, install, smallest useful program | Public surface, compatibility, errors, verification | Exhaustive API and architecture reference |
| Visual or media tool | Definition, install or try path, one finished artifact | Supported inputs and outputs, provenance, safety, restrained visual proof | Effect catalogs, renderer internals, provider setup |
| Local-data product | Definition, privacy boundary, local quick start | Data ownership, read/write effects, recovery, limits | Source-specific ingestion and operator runbooks |
| Hosted product | Definition, try path, current capability | Account, data, cost, privacy, and availability boundaries | Deployment and provider operations |
| Research or knowledge product | Definition, current use, evidence model | Provenance, review, uncertainty, withdrawal, limits | Schema, editorial, and provider reference |

These shapes can combine. Keep the resulting reader path coherent instead of
copying every section from every row.

## Keep the README and website one system

Choose one explicit relationship for every product site:

### Render the complete README

Use this for a quiet technical project page. Render repository-owned Markdown
at build time. Preserve headings, code, tables, relative links, and images;
reject unsafe HTML and URL schemes, and test source equality.

### Render a marked README selection

Use this when the website needs a compact overview. Put unique, own-line markers
around the selected Markdown. Parse them strictly, reject duplicates, reversed
ranges, and empty selections, and prove that surrounding README text cannot
change the result. Keep the marker block useful on GitHub without the website.

### Author a separate product landing page

Use this when the website must support a different reader journey, such as a
visual product or hosted application. Share or derive stable facts including
the name, definition, install command, repository URL, release, and trust
boundary. Test those facts across the README and site. Keep the operating
manual in the README or docs instead of copying it into landing-page prose.

Whichever relationship applies, update the README, site source, metadata, and
their alignment tests in the same behavior change. Treat stale documentation
and unsupported site claims as defects. Review the changed surface at mobile
width and 200% text, traverse its interactive controls by keyboard, and inspect
every color mode it supports. Automate those checks when an existing browser
harness or the regression risk makes the evidence worth maintaining.

## Keep the page quiet

- Use one descriptive H1 and literal, sentence-case headings.
- Put runnable commands before comprehensive explanation.
- Prefer paragraphs for connected reasoning and lists for parallel facts.
- Add one restrained screenshot, diagram, or output sample only when it proves
  something text cannot show as clearly.
- Keep badges to facts that materially help a user decide or verify.
- Omit a table of contents when the heading outline already provides a short,
  useful path.
- Do not repeat the title, tagline, and summary in several decorative forms.
- Keep contribution, security, license, and support paths easy to find.

## Verify before merging

Review the README as a user-facing change:

- The opening names a category, boundary, differentiating mechanism, and
  outcome without praise.
- A new reader can reach one supported result without consulting the command
  reference.
- Commands, versions, package names, links, and outputs match executable or
  generated evidence.
- Capability claims name their important limits and external dependencies.
- Security and private-data boundaries are explicit where relevant.
- Deep reference material follows the first-value path or lives in linked docs.
- Public prose contains no private provenance, internal workflow, or assumed
  history.
- Website copy and README-derived surfaces pass their alignment tests.
- The repository's required check passes, and skipped external checks are
  reported as unverified.

Read the page at speaking pace. Remove mechanical repetition, staged contrasts,
filler, decorative claims, and details that do not help the next decision.

## Source and adaptation

This framework was prompted by the information architecture and documentation
discipline in [Agencity](https://github.com/kousun12/agencity/tree/4beeb6fef202a491959ceef9b1f74d1567349b4c).
Its README moves from durable identity through first use, core behavior,
recovery, limitations, trust, and verification. Its repository guidance also
requires public documentation to stand alone and remain within executable
reality. Hraness keeps that trust architecture while adding public install,
distribution, contribution, release, website, and visual-product needs.
