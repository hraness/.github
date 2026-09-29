# Browser automation

For ordinary owned automation, use a versioned Chrome for Testing installation or the Chromium revision
provisioned for the repository's pinned Playwright version when tests or
verification scripts own the browser. Keep browser selection in the launcher
so shells, CI, and existing sessions all receive the same protection.

## Provision and verify

1. Install the repository's locked dependencies, then run its documented browser
   installation command. For a project with the pinned Playwright CLI installed,
   `bunx --no-install playwright install chromium` provisions its matching revision.
   CI should cache this installation by Playwright version.
2. Resolve the selected executable, including symlinks, before launching. Fail
   with provisioning instructions when it is absent. Reject installed
   auto-updating Chrome even when supplied through an environment variable or
   explicit override. Do not select the `chrome` channel or search application
   directories as a fallback.
3. Record the resolved executable and the running browser's version in the
   verification output. Use a throwaway profile. Preserve the existing host
   scheduling rules and browser ownership controls.
4. Pass `--mute-audio`. Merge `PaintHolding,MacAppCodeSignClone` into the existing
   `--disable-features` argument, retaining other feature names and using one
   switch. These flags supplement correct provisioning.
5. Close contexts and the owned browser in `finally`, including failed checks.
   Finish cleanup before releasing browser ownership. Use forced termination
   only as recovery for a browser that cannot close normally.

The [public-site browser template](templates/verify-public-site-browser.mjs)
uses Playwright's provisioned executable, resolves symlinks before launch,
rejects an installed Chrome app, and reports the executable and version. Its
self-test covers missing provisioning and a provisioned path resolving to the
system app. It intentionally has no executable override or system fallback.
Repositories that copy this template must adopt subsequent fixes explicitly.

An explicitly authorized attachment to a person's existing browser is a
separate operation. Preserve that browser's profile and lifetime; closing an
owned automation session must not terminate a browser owned by the user.

## Slopcamera native-runtime exception

Slopcamera's native runtime may use a signature-verified, version-bound,
immutable task-owned Chrome snapshot when its vendor identity requirement
excludes the provisioned testing browser. This exception applies only to that
native runtime. Ordinary automation and the public-site template continue to
require provisioned Chrome for Testing or Playwright browsers.

The native launcher must verify the expected vendor signature and exact browser
version, create and verify its immutable snapshot, and launch only that snapshot.
It must never launch the installed application directly or accept an arbitrary
executable override. Preserve all existing identity, snapshot integrity, browser
ownership, scheduling, and cleanup checks; a testing browser that fails identity
verification is not a reason to weaken them.

The current launch contract must include `MacAppCodeSignClone` in its merged
`--disable-features` value and bind that argument to the runtime's integrity
verification. Version the contract when changing it. Preserve the interpretation
of historical receipts without allowing an older contract to authorize a new
launch. Keep audio muting, other required feature flags, and graceful shutdown.

Before activating this exception, require native regression tests for the
contract and signature checks plus a live launch/shutdown test showing no new
code-signature clones and completed cleanup. This is a qualification requirement,
not a claim that any particular runtime version has passed. Candidates without
passing regression and live qualification evidence must not activate. At runtime,
identity or launch-contract verification failures must stop the launch; never
select installed Chrome as a fallback.

## Keep the rule enforced

Test missing installations, forbidden explicit selections and symlinks, and
successful provisioned selection in launcher tests. Run them through the
repository's existing required checks. A merge queue does not select browsers
and does not need an additional approval stage for this policy.

## Register the rule with agents

The organization `.github` repository's instructions are not automatically
inherited by other repositories. Register the rule in the global instruction
files that the agents load at session start to cover every repository on a
development machine, including future checkouts and directories without a
local agent guide.

| Agent | Global instruction file | Repository instruction file |
| --- | --- | --- |
| Codex | `~/.codex/AGENTS.md`; a nonempty `AGENTS.override.md` takes precedence | Root `AGENTS.md`, then instructions along the working-directory path |
| Claude Code | `~/.claude/CLAUDE.md` | Root `CLAUDE.md`; `@AGENTS.md` imports shared repository rules |
| Devin for Terminal | `~/.config/devin/AGENTS.md` | Root `AGENTS.md`; Devin also recognizes Claude instruction files |

From a reviewed checkout of this repository, preview the changes, install,
and verify:

```sh
python3 scripts/register-browser-policy.py --dry-run
python3 scripts/register-browser-policy.py --write --backup-dir /path/to/private-backup-directory
python3 scripts/register-browser-policy.py --check
```

The installer copies only the marked `browser-automation` rule from
[AGENTS.md](AGENTS.md), preserving all other instructions. It respects
`CODEX_HOME`, `CLAUDE_CONFIG_DIR`, and `XDG_CONFIG_HOME`; it also updates an
existing nonempty Codex global override so that override cannot hide the rule.
It backs up changed files before replacing them, rejects malformed managed
blocks and instruction-file symlinks, and makes no changes to agent permission settings,
authentication, provider settings, shell defaults, or running sessions.
Existing file modes are preserved; new instruction files and backups are private.
Empty environment overrides use the default paths; nonempty overrides must be
absolute. Directory aliases are resolved and overlapping targets are rejected.
Updates are atomic per file, not across all agents. If a later write fails, the
error report identifies completed updates and saved backups; inspect it before retrying.
Rerun `--check` after a policy update; a mismatch exits unsuccessfully.

Start a fresh agent session after installation. With Devin for Terminal,
`devin rules show AGENTS` identifies the exact loaded global file and its
always-on activation. For Claude Code, `/context` lists loaded memory files.
For Codex, ask a fresh session to report its loaded instructions. Check from
a repository with no local guide as well as an existing project. Do not put
the rule in the verification prompt: confirm the agent received it at startup.

Global files cover agents running under that home directory and configuration.
Hosted agents and another machine need the same registration in their own
environment, or the canonical delivery block in their repository's root
`AGENTS.md` and a `CLAUDE.md` containing `@AGENTS.md`. A local installation
does not change a hosted agent's organization knowledge or settings.

For new repositories, keep these root instruction files in the initial
commit and copy the delivery block as described below. Global registration
provides local coverage while repository instructions make the rule portable
to other machines. Use the existing drift checker to keep those copies current.

The loading paths follow the official [Codex instruction guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[Claude Code memory guide](https://code.claude.com/docs/en/memory), and Devin
for Terminal's installed `rules` help and always-on rule inspector.

The canonical rule lives in the `hraness-delivery` block in [AGENTS.md](AGENTS.md).
Copy the complete block into affected repositories, preserving their additions,
and run `python3 scripts/sync-agent-blocks.py --check --path /path/to/repository`
from this repository to detect drift. The block links back to this canonical runbook.

## Why the executable matters

On macOS, ordinary Chrome can create code-signature clones so an update does
not invalidate a running browser's signature. Abnormal shutdown can leave
those temporary clones behind. Repeated test launches can multiply them.
Chrome for Testing disables that clone feature; gracefully closing browsers
also prevents other abandoned process and profile resources. See the
[Chromium clone manager](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/mac/code_sign_clone_manager.mm).
