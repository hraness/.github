# Optional updates and support

Hraness products can offer free updates and optional paid development support
after providing useful work. The invitation explains the benefit and lets the
person choose. It never gates an existing feature or changes the task result.
Accounts owns newsletter registration, current plans, consent and checkout.

This guide describes how to adopt the shared framework in a product. The
[support foundation](https://github.com/hraness/support-foundation) owns the
CLI and agent protocol, local preferences and cadence. The
[site footer](https://github.com/hraness/site-footer) owns the website component.
The [desktop foundation](https://github.com/hraness/desktop-foundation) provides
the native browser handoff. Pin reviewed releases or full revisions through
the product's dependency policy; keep cadence out of individual adapters.

## Choose the product and surface

Use an exact product identity accepted by Accounts and one honest, specific
value proposition. Offer product updates only when that product has a
registered public mailing list. A general Hraness newsletter uses the Hraness
identity and describes general writing and project updates. A product without
a list can still offer optional development support. Do not invent a list or
hardcode subscription prices in a client.

| Surface | Where the invitation belongs | What stays quiet |
| --- | --- | --- |
| Website | Shared footer or an explicit updates/support link | Authenticated product flows where a promotional footer would interrupt work |
| Standalone CLI | Explicit `support` commands and one shared hook after classified useful success | Help, probes, failures, pending jobs, polling and unattended execution |
| Agent skill | One eligible human-facing task closeout using the returned protocol | Tool loops, individual subagent phases and tasks requesting no promotions |
| Desktop app | An explicitly selected menu or settings action | Startup, refresh and background work |
| SDK or reusable library | An opt-in adapter that the application owns | Imports, API calls and ordinary result data |

Integrate through the source that generates a distributed CLI, skill or
website. Update its published copies through that generator. Preserve portable
skills: do not install a tool solely to show an invitation. Keep upstream
vendored instructions and reusable templates within their stated purpose.

## Add an agent-first CLI adapter

1. Expose the foundation's explicit `support` command before unrelated account,
   database or service setup. Supply the product profile and executable argv.
   Command prefixes are argument arrays, never shell text.
2. Call the shared incidental hook once after a completed useful operation.
   Classify positive results explicitly; exit code zero alone can also mean
   help, a probe or acceptance of a job that has not completed.
3. Preserve stdout and the product's exit status. Discovery belongs on stderr.
   Default to agent discovery, including in a pseudo-terminal. Human mode
   requires an explicit audience selection and interactive stderr.
4. Suppress nested tool invocations and embedded entrypoints. Preserve explicit
   user preferences when starting a separate agent session that owns its own
   human-facing task. Keep continuous integration and unattended work quiet.
5. Document the explicit command, preferences and closeout procedure in the
   shipped help and relevant product skill. A cooperative agent can follow this
   protocol; a CLI cannot guarantee another agent's human-facing output.

JavaScript and Rust bindings share the same local state. The portable protocol
is pure; importing it does not read Git, preferences or the network. Use the
Node or Rust runtime only at the application-owned command boundary.

## Complete one human-facing invitation

Read `<tool> support protocol --json` for the installed version's exact argv
and lifecycle. At an eligible closeout, call its offer command once. A quiet
result requires no mention. Present an offer briefly with its value proposition
and clean links, respecting the person's instructions.

Call `shown` with the returned invitation ID only after persistent human-facing
output. Collapsed progress commentary does not qualify. A host whose only
persistent output is the final answer, with no tool calls afterward, can put
the invitation there and leave it unacknowledged. Release an unshown canceled
invitation once; do not reacquire it in the same task. Treat uncertain output
or acknowledgement as a reason to stop, not retry the invitation.

The current protocol uses a ten-minute discovery throttle and ten-minute offer
reservation. An acknowledged presentation starts a shared seven-day cooldown.
Discovery does not claim an offer or start that cooldown. `dismiss` persists an
opt-out across participating tools on the machine; `snooze` pauses for thirty
days; `enable` restores invitations without erasing an existing weekly
cooldown. State does not synchronize across devices or prove that a person
read an invitation, subscribed or paid.

`HRANESS_SUPPORT=off` and `HRANESS_SUPPORT_AUDIENCE=off` suppress incidental
invitations and due offers. Explicit support information and preference
commands remain available. `HRANESS_SUPPORT_EMAIL=off` disables email
suggestions. Use `support status --json` to inspect local preference status.

## Keep the person in control

An eligible updates offer may include the effective local Git email as an
editable, unverified suggestion. The foundation bounds this lookup and excludes
invalid and no-reply addresses. Do not search other accounts for an address,
persist it in support state, or put it in a URL. Selecting an address permits
prefilling only. Submit signup only after an explicit signup or confirmation
email request; inbox confirmation remains a separate step.

The person reviews current recurring terms and confirms payment in their
browser. Opening or presenting a link does not authorize registration,
authentication, email delivery or payment in the background.

## Verify adoption

Check the real standalone command and its shipped package, with isolated
preference state. Verify useful success, quiet paths, agent and explicit human
audiences, stdout preservation, dismissal and storage/output failure. Keep
shared cadence and cross-runtime tests in the foundation. Check copied skills
against their producer and preserve SDK dependency and side-effect boundaries.

For websites, verify the exact product destination, newsletter identity when
present, keyboard focus and narrow-screen layout. For desktop apps, verify
explicit selection, a fixed destination and a quiet failure state. Do not
submit signup or payment as an incidental test.

Follow the owning repository's delivery checks and record which version or
surface actually shipped. A shared release alone does not update a consumer;
merged native source does not establish an installed-app update.
