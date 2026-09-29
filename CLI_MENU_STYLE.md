# CLI and control style

This guide sets how every Hraness command-line tool looks, reads, and behaves, so a person who learns one product can use the next. [`STYLE.md`](STYLE.md) governs every sentence; this guide adds the layout, symbols, budgets, shared commands, and exit codes that sentences sit in.

Hraness products have no menu bar. Since desktop-foundation 1.0 a person watches a product with `<product> tui`, a script or agent reads `<product> status --json`, and every action a menu used to offer is a command. The full specifications live in desktop-foundation: [headless control](https://github.com/hraness/desktop-foundation/blob/main/docs/control.md) (the envelope, error codes, verb registry, and owner process), [the human gate](https://github.com/hraness/desktop-foundation/blob/main/docs/human-gate.md), [permission notices](https://github.com/hraness/desktop-foundation/blob/main/docs/permissions.md), and [the 0.9 to 1.0 migration](https://github.com/hraness/desktop-foundation/blob/main/docs/migration-1.0.md). Use this page to write and review; use those pages to implement. For the envelope, error codes, exit codes, operation classes, and the human gate, desktop-foundation's contract files win and this page is fixed when they disagree. For text a person reads (help, errors, symbols, notices), this page is the standard, and output from the kits that misses it is a bug to fix in the kit. [Known gaps](#known-gaps-in-the-kits) lists the ones open today.

## Who is reading

Every tool decides who is reading before it prints anything, in this order:

1. `HRANESS_AUDIENCE` set to `human`, `agent`, or `quiet` (`off` means `quiet`).
2. `agent` when any of `AI_AGENT`, `CLAUDECODE`, `CODEX_SANDBOX`, `CODEX_SANDBOX_NETWORK_DISABLED`, `CURSOR_AGENT`, or `GEMINI_CLI` is set to a nonempty value. Only these exact names count: `CODEX_HOME` and `DEVIN_API_KEY` are a person's settings.
3. `human` when stderr is a terminal.
4. `quiet` otherwise.

`--json` always produces JSON. Tools built on `hraness-cli-kit` also print JSON to an agent that did not pass `--json`; the verb registry prints JSON only with `--json`, so an agent should always pass it. `quiet` prints plain text: no color, progress, hints, or invitations, and it never waits for input. Use `detectAudience()` from `@hraness/desktop-foundation` or `audience::detect` from the `hraness-cli-kit` crate instead of writing the rule again.

The audience chooses wording and format only. It never lets a command skip [the human gate](#c5-decisions-a-person-owns).

## Command-line tools

### D1. Streams and exit codes

- The result goes to stdout. Errors, notices, progress, prompts, and `Next:` hints go to stderr.
- `--json` writes exactly one JSON document to stdout, on one line (JSON Lines only for streaming commands), and nothing decorative to stderr.
- Every product uses the same exit codes. `contract/error-codes.json` in desktop-foundation is the list both kits check against.

| Exit | Meaning | Error codes |
| --- | --- | --- |
| 0 | Success | none |
| 1 | Failure | `not-found`, `permission-denied`, `unsupported-platform`, `internal`, and the product's own codes |
| 2 | Usage error: a malformed command line, an unknown command or option | `usage` |
| 3 | A person has to decide. Nothing changed. | `human-required`, `gate-failed`, `gate-expired` |
| 4 | The product's owner process is not running and could not be started | `owner-unavailable` |
| 5 | Conflict: a second owner, a stale revision, or a changed digest. Nothing changed. | `control-already-running`, `conflict`, `digest-mismatch` |
| 130 | Interrupted with Ctrl-C | none |

- A product adds error codes only under its own prefix, such as `ghostget.policy-locked`; they exit 1. Use no other exit code unless the product already documents it.

### D2. Running the tool with no arguments

At most 25 lines of at most 80 columns, on stdout, exit 0. Chat-first tools may open their interface on a terminal; without one they print this screen.

```text
Textbutler answers your Messages chats for you, only in chats you turn on.

Start here
  textbutler setup           Connect Messages and choose chats
  textbutler status          See what Textbutler is doing
  textbutler tui             Watch Textbutler in this terminal

Everyday
  textbutler chats           List chats and their reply settings
  textbutler pause           Pause automatic replies

All commands: textbutler --help · Topics: textbutler help <topic>
textbutler 1.4.0
```

- Line 1 is the product's `short` line from the portfolio registry ([`MESSAGING.md`](MESSAGING.md)).
- "Start here" lists 3 to 5 commands in the order a new person runs them. Add at most one more group.
- No support, credits, protocol, or maintainer lines. A banner counts toward the 25 lines.

### D3. Help

- `-h`, `--help`, and `help` print grouped help to stdout and exit 0. Root help is at most 60 lines: the `Usage:` line, "Start here", titled groups of one-line summaries (long synopses collapse to `[options]`), an Options block (`-h, --help`, `-V, --version`, `--json`), then at most one support line such as `Optional support: textbutler support · Turn off: HRANESS_SUPPORT=off`.
- Maintainer, agent-protocol, and advanced commands move to `help advanced`. They keep working; they leave root help. The shared commands in [C1](#c1-the-shared-commands) other than `status`, `tui`, and `doctor` usually belong there.
- `<cmd> --help`, `<cmd> -h`, and `help <cmd>` print the same text to stdout and exit 0 for every command, including commands that need arguments. Asking for help never runs the command and never asks for the human gate. With `--json`, help is a `hraness.help/1` envelope holding the same descriptors as `commands --json`.

```text
Usage: textbutler chats add <contact> [options]

Add a chat. Automatic replies stay off until you turn them on.

Options
  --auto        Turn on automatic replies now
  --json        Print machine-readable output

Example
  textbutler chats add "+1 555 0100"
```

- Write summaries in sentence case: capitalize the first word and proper nouns only.
- Keep delivery words out of help and errors: *admission*, *qualification*, *custody*, *receipt*, *lane*, *gate*, *surface*, *projection*, *habitat*, *organism*, *pin*. When one is the right word, explain it on the same line: `habitat (a folder of saved runs)`.

### D4. Version

`--version` and `-V` print the name and version, `textbutler 1.4.0`, to stdout and exit 0. `-v` means version only in a tool without a verbose flag. With `--json`: `{"name":"textbutler","version":"1.4.0"}`.

### D5. Errors

```text
✗ No chat matches "Mom".
→ textbutler chats list
```

- Line 1 is `✗` and one sentence saying what happened, then `: why` when known. Line 2 is `→` and exactly one next command. Nothing else by default.
- Never a stack trace, usage dump, error code, or JSON object in text mode. `--debug` or `HRANESS_DEBUG=1` adds the code and trace below.
- A usage error names the input and suggests the closest match, then exits 2: `✗ Unknown command "stauts". Did you mean "status"?` and `→ textbutler --help`. A missing argument points at that command's help: `→ textbutler chats add --help`. An unknown option is a usage error too, and the command does not run.
- With `--json`, the error goes to stdout as the error envelope in [C4](#c4-the-json-envelope), with the same exit code.
- Commands not yet on the verb registry may still print the older `hraness-cli-kit` shape, `{"ok":false,"error":{"code":"…","message":"…","next":"…"}}`, and `permissionErrorJson` still prints that shape. A command on the registry reports a macOS permission failure in the envelope instead, with the optional `error.permission` object `{"kind","settingsUrl"}` from desktop-foundation 1.1. A 1.0 reader rejects an envelope that carries it.

### D6. Symbols, color, and terminals

| Symbol | Meaning | Color | ASCII |
| --- | --- | --- | --- |
| ✓ | done, healthy | green | `OK` |
| ✗ | failed | red | `FAIL` |
| ⚠ | needs attention (no U+FE0F) | yellow | `WARN` |
| → | next step | dim | `->` |
| ● | running, on | green | `*` |
| ○ | idle, off | none | `o` |
| – | skipped | dim | `-` |
| ↻ | in progress | none | `...` |
| 🔐 | permission notice, only there | none | `NOTE` |

- Color the symbol, never the sentence.
- Color only when the stream is a terminal, `TERM` is not `dumb`, and `NO_COLOR` is unset or empty. `FORCE_COLOR=1` forces color. `NO_COLOR` removes color and keeps the symbols.
- Use the ASCII column when `TERM=dumb`, when none of `LC_ALL`, `LC_CTYPE`, or `LANG` names UTF-8, or when `HRANESS_ASCII=1`.
- When output is not a terminal: no color, no spinners or redrawn progress, and no prompts. Fail with the next command instead of waiting.
- Work that takes over 2 seconds shows one progress line on a terminal's stderr, such as `↻ Downloading the helper (1.8 MB)…`, replaced by the result.

### D7. Success and next steps

```text
✓ Added Mom. Automatic replies are off.
Next: textbutler chats on Mom
```

- A command that changes something ends with one `✓` line saying what changed.
- At most one `Next:` hint, on stderr, for a person. An agent gets it in the envelope's `next` list; `quiet` gets nothing.
- Status and doctor output use `●` and `○` for state and `✓`, `⚠`, `✗`, `–` per check, end with a one-line count, and give one `→` step when anything failed.

```text
✓ Background service is running
⚠ Messages access isn't set up yet
  Turn on Textbutler in System Settings › Privacy & Security › Full Disk Access.
– Contacts (skipped)

1 warning.
→ textbutler setup
```

### D8. Pipes and interrupts

- `<cli> --help | head -1` ends quietly: no panic, trace, or `EPIPE`. In Rust, restore `SIGPIPE` to its default at the top of `main` or treat a broken pipe as a quiet exit. In Node and Bun, exit 0 on `EPIPE` from stdout.
- Ctrl-C restores the terminal and exits 130, printing at most `✗ Stopped.` The interactive `tui` is the exception: there Ctrl-C, `q`, and Esc are keys that quit, restore the terminal, and exit 0.

### D9. Golden tests

Each tool keeps tests that capture: the no-argument screen, root `--help`, one `<cmd> --help` per command group, `--version`, output with `NO_COLOR=1`, output to a pipe, output with `TERM=dumb`, `--help | head -1`, one error per class (usage, not found, permission, network), the `--json` error, and every permission notice and recovery message the tool prints.

A product with the shared commands also keeps:

- `commands --json`, checked against `contract/envelope.schema.json`, with an operation class on every verb and a gate on every `decide` verb;
- `tui --snapshot` at widths 40, 80, and 120, and `tui --json`, for every state the product can show, including each state its retired menu bar had a fixture for;
- a check that `tui --json` equals `status --json` apart from `generatedAt`;
- every `decide` verb run with no terminal, a private `HOME`, and `--json`, exiting 3 with `human-required` and changing nothing.

## Shared commands

Every product offers the same few commands for health, discovery, watching, and decisions, built from the verb registry in desktop-foundation (`./registry` in TypeScript, `hraness-control-kit` in Rust). The product's own commands keep their names and sit beside them.

### C1. The shared commands

```text
<p> status            [--json]                          read     one screen of health; the same data as tui
<p> commands          --json                            read     every verb: path, class, schema, summary, gate
<p> tui               [--snapshot | --json] [--width N] read     a live view on a terminal; a snapshot otherwise
<p> doctor            [--json]                          read     platform, release, helper, owner, login items, retired items
<p> control serve     [--foreground]                    operate  owner products only; runs the owner
<p> control status    [--json]                          read     whether an owner answers; never signals
<p> control stop      [--json]                          operate  asks the owner to stop over its socket
<p> control install | uninstall [--json]                decide   an opt-in login item that starts the owner
<p> approvals list | show <id> [--json]                 read     products with approvals
<p> approvals decide <id> --digest <d> deny             operate
<p> approvals decide <id> --digest <d> allow-once       decide
<p> permissions list [--json]                           read     products with permissions
<p> permissions set <…> --expected-revision <n>         operate to tighten, decide to loosen
```

- Every product has `status`, `commands`, `tui`, and `doctor`. A product has `control` only when it runs an owner process, and `approvals` and `permissions` only when it holds those decisions.
- Every command takes `--json`, except `control serve` and the interactive `tui`, which own the terminal and print no envelope.
- `status` shows pending decisions, such as approvals waiting for a person, instead of a desktop notification.
- `control status` reads the owner's files and probes its socket; it never sends a signal. `control stop` asks over the owner's socket and never signals a process either. A second `control serve` exits 5 with `control-already-running`.
- `doctor` finds a login item an earlier menu bar release left behind and says how to set it aside. Setting it aside renames the exact item the product installed to `*.retired-<timestamp>`; nothing is deleted, and `doctor` prints how to rename it back.
- Each product keeps `docs/cli-parity.md`, a table from every former menu bar action and state to the command that replaces it. A test fails when an action or state has no command.

### C2. Operation classes

Every verb declares one class. `commands --json` lists it, and the registry refuses to build a verb without one.

| Class | What it may do | Gate |
| --- | --- | --- |
| `read` | Looks. Never changes anything. | none |
| `operate` | Changes state an agent may change on its own: deny, cancel, pause, stop, tighten. | none |
| `decide` | A decision a person owns: allow a request, loosen a permission, install a login item. | required |
| `decide-legacy` | A decision the product has always let any caller make. Listed so the gap is visible. | optional |

A verb whose class depends on its input, such as `approvals decide`, is registered as `decide` with a test for the input that runs as `operate` (`deny`). Every other input still needs a person.

### C3. `tui`

- On a terminal, `tui` opens a live view. Tab and Shift-Tab switch views, `r` reloads, and `q`, Esc, or Ctrl-C quit. The footer says so in one line: `Tab next · Shift-Tab back · r reload · q quit`.
- Without a terminal, or with `--snapshot`, it prints each view once as plain text, 80 columns wide unless `--width N` says otherwise, and exits. Each view starts with `== Title ==`.
- `tui --json` prints the same envelope as `status --json`.
- Put the product's state first, in the words a status line uses: "Running · 3 chats on", "Needs Full Disk Access", "Textbutler isn't running". Follow it with at most one next command.
- Keep IDs, paths, digests, and timestamps out of the first view. Show them in a detail view or in `--json`.
- Remove escape sequences and control characters from product data before drawing it (`clean` in `./tui`), and fit every line to the width in terminal columns, not characters.

### C4. The JSON envelope

Every command that takes `--json` prints exactly one JSON object, on one line, on stdout:

```json
{"ok":true,"schema":"textbutler.status/1","generatedAt":"2026-09-28T00:00:00.000Z","data":{}}
{"ok":false,"schema":"hraness.error/1","generatedAt":"2026-09-28T00:00:00.000Z","error":{"code":"not-found","message":"No approval a1."}}
```

- `schema` names the shape of `data` as `<product>.<noun>/<n>`. Raise `<n>` when the shape changes in a way a reader would notice.
- `generatedAt` is UTC with milliseconds.
- `next`, when present, lists follow-up commands as `{command, why, audience}`, where `audience` is `agent` or `human`. A step for a person keeps every argument, with flags written as `--flag=value`, so it runs back to the same input.
- `error.code` is one of the codes in [D1](#d1-streams-and-exit-codes) or a product code. `error.detail` holds extra text, such as the underlying message of an unexpected `internal` failure.
- The exit code matches `error.code`, as in the table in D1.

### C5. Decisions a person owns

A `decide` verb asks for a person through the human gate: the command needs a foreground terminal, shows what will change and its digest, prints a one-time code on `/dev/tty`, and reads it back from `/dev/tty` within 120 seconds. Piped input cannot answer it.

- With no terminal, or a terminal in the background, the verb exits 3 with `human-required`. A wrong code exits 3 with `gate-failed`; no answer in time exits 3 with `gate-expired`. In every case nothing changed.
- Run with `--json` by an agent or a quiet audience, a `decide` verb never prompts. It exits 3 with `human-required` and a `next` step whose audience is `human`, naming the exact command to run:

```json
{"ok":false,"schema":"hraness.error/1","generatedAt":"2026-09-28T00:00:00.000Z","error":{"code":"human-required","message":"`textbutler approvals decide` is a decision for a person. Nothing changed.","next":[{"command":"textbutler approvals decide a1 allow-once --digest=3f2a","why":"Run this in your own terminal to decide.","audience":"human"}]}}
```

- `HRANESS_AUDIENCE=human`, and `--confirm` on a verb that declares it, change wording only. They never satisfy the gate.
- The owner checks the digest again when it applies the decision. If the thing being decided changed in between, the verb exits 5 with `digest-mismatch`. A stale `--expected-revision` exits 5 with `conflict`.
- The gate stops an agent making a person's decision by accident or because a prompt told it to. It is not a boundary against a determined program running as the same user; [the human gate](https://github.com/hraness/desktop-foundation/blob/main/docs/human-gate.md#threat-model) says what it does and does not stop. Do not describe it as more.

## Permission notices

Before macOS shows a permission prompt, say what it will ask and why. After a denial, say it was a denial, name the pane, and give one next step. The permission kit in desktop-foundation (`hraness-cli-kit` in Rust) renders this copy from presets; products pass their name and, where a preset asks, the reason.

- Name the product, and name the requester as macOS will show it. Before the product has its own app, the requester is the terminal app or executable: `{forProduct}` becomes " for {product}" and `{thatsProduct}` becomes ". That's how {product} starts in the background". Once the requester is the product, both are empty.
- Ask for Enter only when macOS will show a dialog that needs a decision. A login-item notice needs no confirmation.
- Never wait for input unless stdin and stderr are both terminals.
- An agent gets one JSON line on stderr instead: `{"type":"permission-notice","product","kind","message"}`. `quiet` gets nothing.

### Before the prompt

When macOS asks:

```text
🔐 macOS will ask to let {requester} {ask}{forProduct}.
   {why} Change this any time in {path}.
   Press Enter to continue · s to skip
```

When the person must turn it on in System Settings (Full Disk Access):

```text
🔐 {product} needs {pane} to {ask}.
   macOS doesn't ask for this. Turn on {requester} in {path}. {why}
   Press Enter to open Settings · s to skip
```

When macOS only shows a notice (login items):

```text
🔐 macOS will show a notice that {requester} can open at login{thatsProduct}.
   {why} Turn it off any time in {path}.
```

For the keychain, the second line ends "Enter your Mac password if asked, then choose Always Allow so macOS doesn't ask again."

### After a denial

```text
✗ {product} can't {ask}: macOS access is off for {requester}.
  Turn on {requester} in {path}.
→ {next} · press o to open Settings
```

```text
✗ {product} couldn't {ask}. macOS may be blocking {requester}.
  Check {path}.
→ {next}
```

"press o to open Settings" appears only when stdin and stderr are terminals and the permission has a System Settings pane. A keychain denial says "the keychain request was denied" and asks the person to run the command again and choose Always Allow. Missing command line tools print `✗ {product} needs Apple's command line tools. Nothing was installed.` and `→ xcode-select --install`.

### Without a terminal

When a prompt is coming and there is no terminal, the helper shows one native dialog (`hraness-helper --notice`): the title `{product} needs access to {target}` (or `{product} needs {pane}`), the notice's first two lines as one paragraph, and "Continue" or "Open System Settings" beside "Not now". A login item shows no dialog: running the product's command that installs it, such as `control install`, is the consent.

In `status`, `tui`, and `doctor`, a missing permission is a `⚠` line naming the pane, with the command that fixes it as the next step. No kit renders these lines yet; products write them from this table:

| State | Line | Next step |
| --- | --- | --- |
| Not set up | ⚠ "Needs {pane} to {ask}" | the product's setup or doctor command |
| Denied | ⚠ "{pane} is off. Turn on {requester} to {ask}" | the product's setup or doctor command |
| Granted | none | none |

### Presets

| Preset | Example |
| --- | --- |
| `LOGIN_ITEM` | macOS will show a notice that Textbutler can open at login. It starts in the background when you log in and shows no window or icon. |
| `MESSAGES_FDA` | Textbutler needs Full Disk Access to read your Messages. Only the chats you pick are read. |
| `AUTOMATION` | macOS will ask to let Textbutler control Messages. |
| `CONTACTS` | macOS will ask to let PeopleBlade see your contacts. PeopleBlade reads names and numbers on this Mac. |
| `CHROME_SAFE_STORAGE` | macOS will ask to let security use "Chrome Safe Storage" from your keychain for Ghostget. |
| `LOCAL_NETWORK` | macOS will ask to let Valhalla find and connect to devices on your local network. |
| `INCOMING_CONNECTIONS` | macOS will ask to let vhalla accept incoming network connections for Valhalla. |
| `SCREEN_RECORDING` | macOS will ask to let Slopcamera record your screen. |
| `XCODE_TOOLS` | algal needs Apple's command line tools to build a small helper. macOS will offer to install them (about 1 GB). |
| `LOCAL_SIGNING` | macOS will ask to let codesign use your "Hraness Local Signing" key for Textbutler. |

The [permission notices page](https://github.com/hraness/desktop-foundation/blob/main/docs/permissions.md#presets) has each preset's full text and parameters.

## Check your product in CI

hraness/build-governance has two reusable workflows. Both start as advisory: findings appear as warnings on the pull request and in the job summary, and never fail the build.

```yaml
jobs:
  cli-golden:
    uses: hraness/build-governance/.github/workflows/cli-golden.yml@v0.3.0
    with:
      build: bun install --frozen-lockfile
      cli: bun src/cli.ts
      name: textbutler
      commands: setup,status,chats add

  ux-copy:
    uses: hraness/build-governance/.github/workflows/ux-copy.yml@v0.3.0
    with:
      bare-golden: test/golden/bare.txt
      help-golden: test/golden/help.txt
      command-goldens: test/golden/*.help.txt
```

- `cli-golden.yml` runs the built tool with no arguments, `--help`, each `<cmd> --help`, `--version`, an unknown command, `--json` and `AI_AGENT=1` errors, `NO_COLOR=1` on a terminal, `TERM=dumb`, a pipe, and `--help | head -1`, then checks D2 through D6 and the pipe rule in D8. Ctrl-C handling is not checked.
- `ux-copy.yml` checks captured help for sentence case, unexplained delivery words, and line budgets. Leave its `menu-fixtures` input unset: there are no menus to check.
- Neither workflow checks the shared commands yet, and `cli-golden.yml` v0.3.0 still expects the older error shape: it warns that a C4 envelope has no `error.next` command. Keep the goldens in D9 in the product's own tests, and treat that warning as known, until build-governance catches up.

To make a check required once its findings are fixed, pass `mode: required` and add the calling job to the `needs` list of the workflow's `Required` job.

## Known gaps in the kits

desktop-foundation 1.1.0 meets D3 and D5 in the verb registry's `runCli`: one `✗` sentence and one `→` line, `Did you mean` for a near miss, sentence-case `Usage:`, `help <cmd>`, no "gate" in text, and the JSON envelope for an agent without `--json`. A script (no terminal, no agent) still gets the error envelope on stdout and `FAIL <code>: <message>` on stderr, as in 1.0. Products on 1.0 keep their own handling of unknown commands and options until they move to 1.1. One gap is still open:

- Registry help has no `help advanced` form.
