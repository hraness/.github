# npm package visibility

`actions/npm-visible` waits for a public npm package version to become readable
with the expected archive integrity, distribution tag, and provenance subject.
Use it after publishing a package, before an installation or release step that
needs the registry to serve that exact version.

The expected integrity comes from the retained package archive. For example,
`npm pack --json` reports it in the archive's `integrity` field. Supply that
value as the action input. Pin the action to a reviewed commit of this repository.

## Inputs

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `package` | Yes | | Lowercase npm package name, such as `@example/tool`. |
| `version` | Yes | | Exact semantic version, such as `1.2.3`. |
| `integrity` | Yes | | One canonical `sha512-` Subresource Integrity (SRI) value for the retained archive. |
| `tag` | No | `latest` | Distribution tag that must point to the version. |
| `timeout-seconds` | No | `1200` | Total deadline, including requests; integer from 1 through 1200. |
| `poll-interval-seconds` | No | `5` | Delay between attempts; integer from 1 through 60. |

The action runs on the GitHub runner's Node 24 runtime and requires public
HTTPS access to `registry.npmjs.org`. It uses no npm or GitHub credentials.

## Results and failures

Success sets `version`, `integrity`, and `attestation-url` outputs. It requires
matching version metadata and tag data, a SLSA v1 provenance statement with
signature data, and a single subject with the expected package name, version,
and archive SHA-512. Pair this visibility check with the release workflow's cryptographic
signature and source-authority verification.

Missing metadata, an old tag, temporary HTTP failures, and network failures
retry within the deadline. The action respects `Retry-After` up to that deadline.
A different archive integrity, unexpected package identity, wrong provenance
subject, malformed response, redirect, or authentication failure stops the
action immediately. A failure produces no new outputs.

Requests bypass caches, have a maximum duration of 20 seconds, and accept at
most 1 MiB of JSON per response. Attestation URLs must identify the exact
package version at the canonical registry. The action checks existing public
data and performs no registry writes.

## Development

Run the deterministic request, deadline, and adverse-response tests with Node:

```sh
node --test actions/npm-visible/index.test.mjs
```
