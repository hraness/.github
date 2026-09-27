# CLI and menu bar style

This guide sets how every Hraness command-line tool and menu bar menu looks, reads, and behaves, so a person who learns one product can use the next. [`STYLE.md`](STYLE.md) governs every sentence; this guide adds the layout, symbols, budgets, and exit codes that sentences sit in.

The full specifications live in desktop-foundation: [menu kit v2](https://github.com/hraness/desktop-foundation/blob/main/docs/protocol-v2.md) and [permission notices](https://github.com/hraness/desktop-foundation/blob/main/docs/permissions.md). Use this page to write and review; use those pages to implement. When they disagree, desktop-foundation wins and this page is fixed.

## Who is reading

Every tool decides who is reading before it prints anything, in this order:

1. `HRANESS_AUDIENCE` set to `human`, `agent`, or `quiet` (`off` means `quiet`).
2. `agent` when any of `AI_AGENT`, `CLAUDECODE`, `CODEX_SANDBOX`, `CODEX_SANDBOX_NETWORK_DISABLED`, `CURSOR_AGENT`, or `GEMINI_CLI` is set to a nonempty value. Only these exact names count: `CODEX_HOME` and `DEVIN_API_KEY` are a person's settings.
3. `human` when stderr is a terminal.
4. `quiet` otherwise.

`--json` always produces JSON. An agent gets JSON by default from commands that have a `--json` form. `quiet` prints plain text: no color, progress, hints, or invitations, and it never waits for input. Use `detectAudience()` from `@hraness/desktop-foundation` or `audience::detect` from the `hraness-cli-kit` crate instead of writing the rule again.

## Command-line tools

### D1. Streams and exit codes

- The result goes to stdout. Errors, notices, progress, prompts, and `Next:` hints go to stderr.
- Exit 0 for success, 1 for failure, 2 for a usage error, 130 when interrupted. Use another code only if the product already documents it.
- `--json` writes exactly one JSON document to stdout (JSON Lines only for streaming commands) and nothing decorative to stderr.

### D2. Running the tool with no arguments

At most 25 lines of at most 80 columns, on stdout, exit 0. Chat-first tools may open their interface on a terminal; without one they print this screen.

```text
Textbutler answers your Messages chats for you, only in chats you turn on.

Start here
  textbutler setup           Connect Messages and choose chats
  textbutler status          See what Textbutler is doing
  textbutler menubar         Show Textbutler in the menu bar

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
- Maintainer, agent-protocol, and advanced commands move to `help advanced`. They keep working; they leave root help.
- `<cmd> --help`, `<cmd> -h`, and `help <cmd>` print the same text to stdout and exit 0 for every command, including commands that need arguments.

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
- A usage error names the input and suggests the closest match, then exits 2: `✗ Unknown command "stauts". Did you mean "status"?` and `→ textbutler --help`. A missing argument points at that command's help: `→ textbutler chats add --help`.
- With `--json` or an agent reading, the error goes to stdout as `{"ok":false,"error":{"code":"…","message":"…","next":"…"}}` with the same exit code. A permission failure adds `"permission":{"kind","settingsUrl"}`.

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
- Work that takes over 2 seconds shows one progress line on a terminal's stderr, such as `↻ Downloading the menu bar helper (1.8 MB)…`, replaced by the result.

### D7. Success and next steps

```text
✓ Added Mom. Automatic replies are off.
Next: textbutler chats on Mom
```

- A command that changes something ends with one `✓` line saying what changed.
- At most one `Next:` hint, on stderr, for a person. An agent gets it as the `next` field in JSON; `quiet` gets nothing.
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
- Ctrl-C restores the terminal and exits 130, printing at most `✗ Stopped.`

### D9. Golden tests

Each tool keeps tests that capture: the no-argument screen, root `--help`, one `<cmd> --help` per command group, `--version`, output with `NO_COLOR=1`, output to a pipe, output with `TERM=dumb`, `--help | head -1`, one error per class (usage, not found, permission, network), the `--json` error, and every permission notice and recovery message the tool prints.

## Menu bar menus

Every menu bar product builds its menu with menu kit v2 from `@hraness/desktop-foundation` (`menuKit.layout()` in TypeScript, the builder in Rust). The kit produces this order; rows in parentheses are optional.

```text
[mark ● 3]                          template glyph, dot and count only when needed
Textbutler                          the product name, once
● Running · 3 chats on              1 or 2 status rows
(⚠︎ Couldn't pause replies)          an action error, until the next refresh
─────────
↗ Open dashboard            ⌘O      exactly one primary action
─────────
  (up to 5 recent rows)             detail in the subtitle; ⌥ shows Copy ID or Reveal
  (Show all (23) ↗)                 more rows open the browser or Finder, never a deep submenu
─────────
  (up to 3 toggles)
✓ Open at login
─────────
♡ Help & support ↗                  ⌥ Copy diagnostics
  Quit Textbutler           ⌘Q      always last
```

- Start with a status row: a symbol and a plain state, such as "Running" or "Needs Full Disk Access".
- Keep 10 top-level rows or fewer, not counting separators and the header. Nothing done daily goes in a submenu.
- Put IDs, timestamps, versions, and capability lists behind the ⌥ key as alternates, not in visible rows.
- Show a failed action as a ⚠︎ row with one sentence until the next refresh.
- The menu bar mark is a monochrome template SF Symbol. Add the status dot only when the person needs to act.
- Give each product one "Help & support" row. Updates, docs, and support links go there.
- Write every label in sentence case in words anyone can follow. No paths, URLs, flags, commands, or IDs in labels.

### First rows by state

| State | Status row | Primary action |
| --- | --- | --- |
| Starting | ↻ "Starting Textbutler" | none until ready (the only menu without one) |
| Signed out | "Signed out" | "Sign in", opens the browser |
| Needs a permission | 🔒︎ "Needs Full Disk Access" | "Open Full Disk Access settings" |
| Service down | ⊘ "Textbutler isn't running" | "Start Textbutler" |
| Can't reach the service | ⚠︎ "Can't reach Textbutler", detail "Retrying…" | "Open dashboard" if it still works, else "Help & support" |

### Symbols

Products name a symbol; desktop-foundation maps it to the SF Symbol on macOS and to the text glyph elsewhere and in fixtures. Never send raw SF Symbol names or emoji. Adding a name is a reviewed change to the vocabulary in desktop-foundation.

| Group | Names |
| --- | --- |
| Status rows | `status.ok` ✓, `status.running` ●, `status.idle` ○, `status.partial` ◐, `status.syncing` ↻, `status.paused` ⏸︎, `status.attention` ⚠︎, `status.error` ✕, `status.offline` ⊘, `status.signedOut` ?, `status.locked` 🔒︎ |
| Actions | `action.open` ↗, `action.add` +, `action.pause` ⏸︎, `action.resume` ▶︎, `action.refresh` ↻, `action.folder`, `action.copy`, `action.settings` ⚙︎, `action.permission`, `action.signIn`, `action.signOut`, `action.update` ⤓, `action.help`, `action.support` ♡ |
| Content rows | `item.file`, `item.image`, `item.chat`, `item.contact`, `item.room`, `item.job`, `item.camera`, `item.chart`, `item.agent` ✦, `item.approval`, `item.key` |
| Menu bar marks | `mark.chat` Textbutler, `mark.masks` Ghostget, `mark.drop` Sponge, `mark.dropHalf` Sponge v2, `mark.people` PeopleBlade, `mark.chart` AI Charts, `mark.camera` Slopcamera, `mark.shield` Valhalla, `mark.agent` demos and new products |

In menus, ⚠︎ carries U+FE0E. On the command line, ⚠ carries no selector.

### Menu checks

`lintMenu` in desktop-foundation checks a menu snapshot, and `companion lint-menu --strict <fixture.json>` runs it from the command line. Keep one fixture per state (first run, signed out, running, error, empty, most accounts) and its `renderMenuTree` text in the product's tests.

| Rule | Fails when |
| --- | --- |
| `top-level-count` | More than 10 top-level rows, not counting separators and the header |
| `depth` | An action sits two submenus deep, or a submenu holds the primary action |
| `primary-count` | Not exactly one primary action, except in the Starting state |
| `status-count` | More than 2 status rows, or a status row below the first separator |
| `status-repeat` | Two status rows, or a status row and its detail, repeat the same text |
| `quit` | The last item is not `Quit {name}` |
| `header` | More than one header, or a header that is not the product name |
| `raw-text` | A label, subtitle, detail, or tooltip holds a path, URL, UUID, 8 or more hex characters, a `--flag`, or a command |
| `sentence-case` | A label capitalizes a later word that is not a proper noun: the product name, macOS, Messages, Chrome, Safari, Finder, System Settings, Keychain Access, a permission pane name, or a name the product passes in. All-capital words and words with digits pass. |
| `length` | A label over 48 characters, a subtitle over 80, or a tooltip over 160 |
| `glyph-in-label` | A label holds an emoji or a vocabulary glyph, or ends with `↗`, `…`, or `...` |
| `mark-text` | The mark shows text while its tone is normal, paused, or offline |
| `shortcut-repeat` | Two items share a shortcut |
| `empty-submenu` | A submenu has no items |

## Permission notices

Before macOS shows a permission prompt, say what it will ask and why. After a denial, say it was a denial, name the pane, and give one next step. The permission kit in desktop-foundation (`hraness-cli-kit` in Rust) renders this copy from presets; products pass their name and, where a preset asks, the reason.

- Name the product, and name the requester as macOS will show it. Before the product has its own app, the requester is the terminal app or executable: `{forProduct}` becomes " for {product}" and `{thatsProduct}` becomes ". That's {product}'s menu bar". Once the requester is the product, both are empty.
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

### In menus and dialogs

| State | Status row | Action |
| --- | --- | --- |
| Not set up | 🔒︎ "Needs {pane}", detail "To {ask}" | "Open {pane} settings" |
| Denied | 🔒︎ "{pane} is off", detail "Turn on {requester} to {ask}" | "Open {pane} settings" |
| Granted | none | none |

A menu action that is about to cause a prompt shows a dialog first: the title `{product} needs access to {target}` (or `{product} needs {pane}`), the notice's first two lines as one paragraph, and "Continue" or "Open System Settings" beside "Not now". Turning on "Open at login" is itself the consent, so its subtitle reads "macOS shows a notice when you turn this on".

### Presets

| Preset | Example |
| --- | --- |
| `LOGIN_ITEM` | macOS will show a notice that Textbutler can open at login. Its menu bar icon opens when you log in. Nothing else runs in the background. |
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
      menu-fixtures: test/menus/*.json
      bare-golden: test/golden/bare.txt
      help-golden: test/golden/help.txt
      command-goldens: test/golden/*.help.txt
```

- `cli-golden.yml` runs the built tool with no arguments, `--help`, each `<cmd> --help`, `--version`, an unknown command, `--json` and `AI_AGENT=1` errors, `NO_COLOR=1` on a terminal, `TERM=dumb`, a pipe, and `--help | head -1`, then checks D2 through D6 and the pipe rule in D8. Ctrl-C handling is not checked.
- `ux-copy.yml` checks captured help for sentence case, unexplained delivery words, and line budgets, and runs desktop-foundation's `lint-menu --strict` over the menu fixtures.

To make a check required once its findings are fixed, pass `mode: required` and add the calling job to the `needs` list of the workflow's `Required` job.
