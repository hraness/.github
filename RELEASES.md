# Release pages

This guide decides what a Hraness GitHub Release page says and how the release workflow builds it. [`STYLE.md`](STYLE.md) governs every sentence on the page, and [`MESSAGING.md`](MESSAGING.md) supplies the product name.

A release page is the first thing many people read about a version: someone deciding whether to upgrade, an agent checking what changed, a security reviewer checking what they installed. It answers three questions, in this order: what changed, how to install this exact version, and how to check that the files are the ones the workflow built.

## The page

**Title:** the product name from the portfolio registry, a space, and the tag, such as `Oh v0.12.1` or `Ghostget v0.18.38`. Use the name, not the package name or the repository name.

**Body,** in this order:

1. **Summary.** One or two sentences that say what this version changes for someone using it. Lead with the change a reader would notice first. A release that only fixes a bug says which behavior was wrong and what it does now.
2. **`## Changes`.** One bullet per change a user, integrator, or operator would notice, most important first. Start each bullet with what now happens, not with the file or module that changed. Name commands, options, and limits exactly. Leave out internal refactors, dependency bumps with no visible effect, and CI changes. Link a pull request only when it explains more than the bullet.
3. **`## Install`.** The exact command that installs this version from its GitHub Release asset, then the npm or other mirror command when one exists. The command names the version; never write `latest` here.
4. **`## Verify`.** Where the checksums are (usually the `SHA256SUMS` asset), the full source commit, and a link to the repository's guide for checking provenance or signatures, pinned to the tag.
5. **The identity record.** The repository's machine-readable release identity, as an HTML comment, as the final bytes of the body. It is invisible on the rendered page. Keep each repository's existing identity format; this guide only fixes where it goes.

A page with nothing to say under `## Changes` does not ship. Make the version bump carry at least one real change, or do not cut the release.

Example, from Oh v0.12.1:

> Installed copies of Oh now run the Rust text engine. Releases v0.10.3 through v0.12.0 looked for its WebAssembly files in the wrong folder and fell back to the TypeScript reference, which gives the same results more slowly.
>
> **Changes**
> - The packaged loader finds its WebAssembly files, so an installed copy reports `rust-wasm` as its engine.
> - The release check installs the packed package and fails unless the loader reports the Rust engine.
>
> **Install** … **Verify** …

## Where the words come from

The summary and changes come from `CHANGELOG.md` in the tagged commit. The section whose heading is the version (`## 0.12.1` or `## v0.12.1`, with an optional ` - 2026-09-26` date) holds a summary paragraph and a bulleted list. The release workflow copies that section onto the page. It does not write notes of its own, and it never uses GitHub's generated notes.

- Write the changelog section in the version bump pull request, so the notes are reviewed with the release that carries them.
- The release workflow fails before creating the release when the section is missing, empty, or still says `Unreleased`.
- The workflow generates `## Install` and `## Verify` from the release record, so their commands and digests always match the attached files.
- Keep old changelog sections as they shipped. Correct a published page by editing the page and the changelog in the same change, never by rewriting history.

## Identity checks

Release workflows that verify their own release, for retries or for downstream admission, read the identity record from the end of the body. Parse from the last `<!-- ` marker that opens the repository's identity comment, and require the body to end with `-->`. Check that the notes above it are byte-identical to the rendered changelog section plus the generated install and verify sections, so a hand edit to a published page is detected like any other change.

## Do not put on a release page

- “What’s Changed” lists, “Full Changelog” compare links, contributor lists, or “Generated with” lines. The compare link and the commit are in the Verify section when they help.
- Text about the release process itself, such as “Automated release” or “Canonical GitHub release for”.
- A human-visible copy of the identity record. The Verify section carries what a person needs.
- Version numbers typed by hand anywhere except the changelog heading.
