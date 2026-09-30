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
A local global file does not configure another machine or a hosted service.
Use portable repository registration for source-based coverage and the Devin
personal-cloud plugin for account-wide Devin coverage.

### Portable repository registration

The independent `browser-automation` block at the start of [AGENTS.md](AGENTS.md)
is the canonical rule. Keep it first in each repository's root `AGENTS.md`.
Devin automatically includes at most the first 16 KiB from each always-on
instruction file ([hosted onboarding](https://docs.devin.ai/onboard-devin/agents-md)),
so an otherwise correct block at the end of a long guide
may be incomplete. A nonempty root `AGENTS.override.md` must carry the rule too.
Claude Code needs a root `CLAUDE.md` that imports `@AGENTS.md` or carries the
same rule itself.

Preview, update, and check a selected repository from a reviewed checkout of
this policy repository:

```sh
python3 scripts/register-browser-policy.py --repo /path/to/repository --dry-run
python3 scripts/register-browser-policy.py --repo /path/to/repository --write --backup-dir /path/to/private-repository-backup
python3 scripts/register-browser-policy.py --repo /path/to/repository --check
python3 scripts/sync-agent-blocks.py --check --block browser-automation --path /path/to/repository
```

Repeat `--repo` to select several Git roots. Repository mode cannot be combined
with `--home`; it never changes the global agent files. It inserts or moves only
the managed browser block to the beginning and preserves other instructions.
Existing Claude imports are retained; a missing `CLAUDE.md` receives a minimal
`@AGENTS.md` import. Safe aliases between root instruction files are preserved;
external, dangling, cyclic, non-regular, and hard-linked targets are rejected.
All selected targets are checked before any write. Backups and per-file atomic
updates use the same recovery reporting as global registration.

Deliver the changed files through each repository's existing validation,
review, and integration workflow. Do not replace its delivery policy or copy
unrelated shared blocks just to register this rule. For new repositories, copy
[the AGENTS template](templates/AGENTS.md) and
[the Claude import](templates/CLAUDE.md) in the initial commit, then add the
repository's own setup, validation, and delivery instructions.

To report browser-rule drift on accessible active repositories, including
owner-controlled forks and this policy repository:

```sh
python3 scripts/sync-agent-blocks.py --check --block browser-automation --org hraness --visibility all --include-forks --include-self
```

The checker reports missing, different, duplicate, malformed, or too-late
blocks. It never writes to another repository. Organization discovery leaves
archived repositories read-only. The existing weekly public drift report also
checks this independent browser rule; private repositories require a signed-in
machine with access. Use the repository installer to verify the actual Claude
import and Codex override paths as well as the canonical `AGENTS.md` block.

### Devin personal-cloud registration

Devin supports personal plugins that sync to future cloud, CLI, and Desktop
sessions across devices. The [browser policy plugin](plugins/browser-automation/AGENTS.md)
contains the exact public canonical rule and a manifest with skill and MCP
loading disabled. It has no hooks, executables, tools, dependencies, or
permission changes.

After reviewing the merged source, install it with the installed Devin CLI:

```sh
devin plugins install --yes 'hraness/.github#plugins/browser-automation'
devin plugins list
devin plugins info hraness-browser-automation
devin rules list
```

The default install scope is personal cloud. Do not pass `--local` when cloud
coverage is required. `--yes` accepts the plugin trust prompt for the reviewed
source; this operation registers instructions and does not start a model or
cloud session. Inspect the installed source, version, unblocked status, and
rule count. Use `devin rules show` with the exact new rule name listed by the
inspector to confirm always-on activation and the canonical content.

The source tracks the repository's default branch. Check its current reviewed
contents before installation; `devin plugins update` refreshes installed
contents after a delivered policy update. Existing organization and enterprise
plugin controls remain binding. Running sessions retain their startup context;
start a fresh session after registration. Portable repository files also cover
other authorized accounts that do not have this personal plugin.

These loading paths follow the official
[Codex instruction guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[Claude Code memory guide](https://code.claude.com/docs/en/memory),
[Devin rules reference](https://docs.devin.ai/cli/extensibility/rules), and
[Devin cloud plugin guide](https://docs.devin.ai/product-guides/plugins#how-plugins-reach-sessions-cloud--local-sync).

## Why the executable matters

On macOS, ordinary Chrome can create code-signature clones so an update does
not invalidate a running browser's signature. Abnormal shutdown can leave
those temporary clones behind. Repeated test launches can multiply them.
Chrome for Testing disables that clone feature; gracefully closing browsers
also prevents other abandoned process and profile resources. See the
[Chromium clone manager](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/mac/code_sign_clone_manager.mm).
