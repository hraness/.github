# Dependency audit

`actions/dependency-audit` checks every lockfile in a repository against known
vulnerabilities with a pinned [OSV-Scanner](https://google.github.io/osv-scanner/)
build. One scanner covers Bun, npm, pnpm, Yarn, Cargo, Go, Python, Ruby, PHP,
and the other formats in [`lockfiles.json`](lockfiles.json), including `bun.lock`,
which GitHub's dependency graph does not read.

## Install

Every Hraness repository uses the same workflow, rendered from
[`templates/dependency-audit.yml`](../../templates/dependency-audit.yml) with the
action pinned to a full commit of this repository. Install or update it with:

```sh
scripts/sync-dependency-audit.py --apply --repo hraness/<name>
```

The script opens a pull request with the rendered workflow and enables auto-merge.
Change the template here rather than a repository's copy: the coverage check below
reports any difference.

## What it checks

The workflow checks out the repository and runs the action on `ubuntu-slim`.

| Event | Scope | Fails when | Tracking issue |
| --- | --- | --- | --- |
| Pull request that changes a lockfile | Every lockfile, compared with the same lockfiles on the base commit | The pull request adds a known vulnerability | Not changed |
| Push to `main` that changes a lockfile, daily schedule, manual run | Every lockfile on `main` | Any known vulnerability is present | Opened or updated while vulnerabilities remain; closed with a comment when none remain |

The run summary lists the scanned lockfiles and one row per vulnerable package
version and advisory: severity, the advisory link on osv.dev, fixed versions above
the installed one, and the lockfiles that pin it. RustSec advisories that report an
unmaintained or unsound crate are listed separately and never fail the audit.

The audit is advisory. Never add it to a repository's required checks; the
`Required` job stays the only merge gate.

## Resolving findings

Update the package, or the dependency that pins it, to a fixed version. When no
fixed release exists, replace the dependency, or record a reviewed exception in an
`osv-scanner.toml` next to the lockfile:

```toml
[[IgnoredVulns]]
id = "GHSA-xxxx-xxxx-xxxx"
ignoreUntil = 2026-12-31
reason = "Reached only through lint tooling with trusted input; no fixed release."
```

Keep the date close and the reason specific; the exception lapses on that date.

## Inputs and outputs

| Name | Kind | Meaning |
| --- | --- | --- |
| `github-token` | Input, default `github.token` | Reads the base lockfiles of a pull request and, on `main`, updates the issue labelled `dependency-audit`. The job needs `contents: read` and `issues: write`. |
| `vulnerabilities` | Output | Known vulnerabilities found, counted once per package version and advisory. |
| `introduced` | Output | Vulnerabilities a pull request adds; 0 outside pull requests. |

The action runs on the runner's Node 24 runtime on Linux x64. It downloads
OSV-Scanner 2.6.0 from its GitHub release and refuses a binary whose SHA-256
differs from the pinned digest. Scanning sends package names and versions to
[api.osv.dev](https://osv.dev); private GitHub dependencies pinned by an
abbreviated commit are skipped.

## Coverage

`scripts/sync-dependency-audit.py --check` reports, for each repository, whether
the workflow is current, outdated, drifted, or missing, with its latest run on
`main` and the open tracking issue. `.github/workflows/dependency-audit-coverage.yml`
runs it weekly over public repositories. Check private repositories from a
signed-in machine:

```sh
scripts/sync-dependency-audit.py --check --org hraness --visibility private
```
