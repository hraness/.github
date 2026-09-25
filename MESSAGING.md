# Messaging

This guide decides what Hraness says about itself and its products, and where each line goes. [`STYLE.md`](STYLE.md) governs how every sentence is written. This guide governs the story, the names, and the tiers of copy each product carries. The [README guidelines](README_GUIDELINES.md) and [documentation guidelines](DOCUMENTATION_GUIDELINES.md) govern the pages built around them.

Each product's messaging lives in one record in the portfolio registry, published at [hraness.com/portfolio.json](https://hraness.com/portfolio.json). Sites, READMEs, package manifests, CLI help, and listing submissions take their words from that record. To change a line, change the record and let every surface follow it.

## Who is speaking

Hraness is a software studio. It makes tools for AI agents and for people, and it publishes what it learns building them.

- The studio is the maker on every product surface. Write “Hraness” or “we”.
- Name Ben Guo, the founder, on the about page and on his own essays. Do not present a product as one person's project.
- Do not claim a large team or hand-made work. Hraness builds with AI agents; let the work show the care.
- Product sites carry the attribution “by Hraness”, linked to hraness.com. The studio describes itself with its own record in the registry, like any product.

## Voice

Hraness writes like a small, exacting studio that is excited about what people can build now. The voice is precise, warm, and a little intellectual: curious about the history of computing, the internet, and online business, and optimistic about where they go next. Aim for the care of the best product writing you know, and earn it with evidence instead of adjectives.

1. **Lead with the category and the outcome.** Nobody knows a Hraness product name yet, so no hero can rest on the name. The eyebrow names the kind of thing in words a buyer would search for; the heading says what the reader gets.
2. **Show one real thing.** Put the most real object the product can show above the fold: its interface on sample data, real command output, a file it made, or a recorded run. Generate it from the product when you can, label it once, and link to something the reader can inspect.
3. **Use numbers instead of adjectives.** When a sentence wants an adjective, give it a number, a limit, or a date. Take every number from the product's build, release record, or source.
4. **Name the job.** Many software companies now put “agents” or “AI” in their hero, so the word no longer tells a reader which product this is. Say what the agent does with this product that it could not do without it.
5. **Explain through one familiar model.** When a new idea needs a comparison, use something the reader already understands, introduce it once, and keep it. Do not borrow a sibling's comparison or metaphor.
6. **Use one noun per thing.** Choose the word for each concept and use it on every surface. Define a necessary term at first use.
7. **Practice confident restraint.** Say less. State each limit once, beside the claim it limits. Tell the reader when the product is the wrong choice; that sentence costs nothing and earns trust.
8. **Argue optimism from a mechanism.** State what a reader can now build or learn and what makes it possible. Present open questions as the interesting part of the work, never as disclaimers.
9. **Credit the ideas you extend.** Name at most one precedent per product, one it extends, with its primary source. Put it in the idea section or an essay, never in a heading.
10. **Show craft through artifacts.** A dated release line, docs whose commands run on the current release, a changelog, a Markdown twin for agent readers, an essay on how it was built. Never call the work crafted, careful, or beautiful.

### Precedents worth knowing

Use one only when the product extends it, and verify the citation at the source before publishing.

| Idea | Primary work | Fits a product that |
| --- | --- | --- |
| Memex and associative trails | Vannevar Bush, “As We May Think,” *The Atlantic Monthly*, July 1945 | keeps a personal library, links, or research trails |
| Man-computer symbiosis | J. C. R. Licklider, “Man-Computer Symbiosis,” *IRE Transactions on Human Factors in Electronics*, March 1960 | pairs a person and a machine on one task |
| Augmenting human intellect | Douglas Engelbart, “Augmenting Human Intellect: A Conceptual Framework,” Stanford Research Institute, October 1962 | amplifies a person's thinking or knowledge work |
| Personal dynamic media | Alan Kay and Adele Goldberg, “Personal Dynamic Media,” *Computer*, March 1977 | makes the computer a medium people shape |
| Small tools that compose | M. D. McIlroy, E. N. Pinson, and B. A. Tague, “UNIX Time-Sharing System: Foreword,” *Bell System Technical Journal*, July–August 1978 | is a command-line tool meant to combine with others |
| The web | Tim Berners-Lee, “Information Management: A Proposal,” CERN, March 1989 | publishes, links, or addresses things by URL |
| Working in public | Nadia Eghbal, *Working in Public*, Stripe Press, 2020 | is open source or maintained in public |

## Names

- Each messaging record holds the product's names: `names.name`, the prose name with its exact case; `names.catalog`, the all-capitals display form that hraness.com lists and the organization profile use; `names.command`, the command or package name; and `names.formerly`, its retired names.
- Use `names.name` in every sentence, title, heading, and metadata field, on the product's own site and on its siblings'. Use `names.catalog` only where a design sets every name in capitals, and `names.command` only in code.
- On a page that stands alone, say what kind of thing the product is at its first mention, using its category.
- Do not use a domain or a repository slug as a name in prose, and do not use a product name as a common noun.
- Mention a retired name only in a redirect, a changelog, or a “formerly” note.

## The messaging record

Each product has one record with these fields. Limits are maximums; write less when less is true.

| Field | Limit | Form | Job |
| --- | --- | --- | --- |
| `category` | 30 characters, 4 words | A noun phrase in sentence case, singular where possible, without a period: the words a buyer would search for. | Hero eyebrow, listing category, App Store subtitle |
| `tagline` | 60 | One sentence with a verb and one claim a reader could check. No product name. It is a promise the page proves, not a slogan. | Default hero heading, share card, home page title, Product Hunt tagline, footer |
| `short` | 80 | A phrase with no leading article, no product name, and no final period. It reads after the name: “{name}: {short}”. | hraness.com cards, sibling cards, CLI about, Homebrew, organization profile, LinkedIn tagline |
| `meta` | 110 to 160 | One or two sentences that name the product and give one concrete fact. | Home page meta and share description, JSON-LD, GitHub About, package and crate descriptions, `llms.txt` summary |
| `medium` | 240 | Two sentences. The first starts with the name and stands alone. | README first paragraph, default hero summary, Product Hunt and directory descriptions |
| `long` | 1,000 | One paragraph of about 100 to 160 words: the reader's problem, what the product does, how it does it, and one proof. | Long listing descriptions, App Store and LinkedIn descriptions, press, `llms.txt` introduction |
| `hero` | heading 60, summary 240, each action 32 | Optional. The heading and summary default to `tagline` and `medium`. | The product home page hero and closing call to action |
| `channels` | per channel | Optional overrides for a channel whose rules make the default unfit. | See [Listing sites](#listing-sites) |

- Write `long` first, then cut. Each shorter field keeps the longer field's nouns. Shorten by cutting words, never by swapping in house nouns.
- Every field follows `STYLE.md`: no em dashes, hype words, internal vocabulary, verbless slogans, reflexive threes, or unsupported superlatives.
- Each `tagline` and `short` is unique across the portfolio, and no two fields of the same product are identical.
- Status, version, price, and platforms are facts, not messaging. Render them from the release record beside the copy. A field may state a stable fact such as “free and open source”.
- Store sentence case with proper nouns and acronyms intact. hraness.com lowercases lines at its own display boundary; every other surface uses the stored case.
- Each field records its author: `authored` when the owner wrote or approved it, `proposed` when an agent drafted it. Replace an authored line only when a reviewer who did not write the new line agrees it is better, and keep the old line in the record as `superseded` so every replacement can be listed and reversed.

## Where each field goes

| Surface | Field |
| --- | --- |
| hraness.com cards and project list | `names.catalog` and `short` |
| Product home page `<title>` | `names.name` and `tagline`, joined with the site's separator |
| Home page meta, share description, and JSON-LD | `meta` |
| Share card | `names.name` over `tagline` |
| Hero | eyebrow `category`; heading `hero.heading` or `tagline`; summary `hero.summary` or `medium`; action labels from `hero` |
| Sibling cards | the sibling's `names.name` and `short`; a relationship sentence only for a registered relation |
| “Who made it?” | the Hraness record's `medium` |
| README | H1 `names.name`; first paragraph `medium`; status from the release record |
| `llms.txt` | summary `meta`; introduction `long` |
| GitHub About, npm, crates.io | `meta`, or its channel override |
| Homebrew `desc` and CLI about | `short` |
| Organization profile | emoji, `names.catalog`, and `short` |
| Interior pages | written for each page under the description rules in `STYLE.md` |

Import these fields from the published record instead of typing them. When a repository cannot import, sync them into the file with a check that fails when the file and the record differ.

## Listing sites

| Channel | Field | Take | Limit |
| --- | --- | --- | --- |
| Product Hunt | Tagline | `tagline` | 60 |
| Product Hunt | Description | `medium` | 260 |
| Product Hunt | Launch tags | `category` words | 3 tags |
| Homebrew | `desc` | `short`, starting with a capital letter | 79 |
| Chrome Web Store | Summary | `meta`, cut to fit | 132 |
| Chrome Web Store | Description | `long`, then a feature list | none published |
| App Store | Subtitle | `category` | 30 |
| App Store | Promotional text | `meta` | 170 |
| App Store | Description | `long`, then features | 4,000 |
| AlternativeTo, SaaSHub, BetaList, Indie Hackers | Description | `medium` or `long`; tagline fields take `tagline` | not published |
| X profile | Bio | `meta` | 160 |
| LinkedIn page | Tagline | `short` | 120 |

- The X and LinkedIn limits come from secondary sources. Check the field's own counter when you submit.
- A person writes the Show HN title and text and the Product Hunt first comment. Agents supply checked facts for them, not prose.
- Submit the canonical URL without tracking parameters.
- Record the exact text submitted to each field and the record field it came from, so a later audit can find listings that no longer match.

## Page anatomy

The product home page follows one pattern, so a reader who learns one Hraness site can read the next.

**Hero.** Eyebrow (`category`); heading (a full sentence, which may break at a phrase boundary onto two lines); a summary of two sentences, the first saying what the reader does and gets, the second giving the one mechanism or proof; a primary action that reaches first value on the site; a secondary action that opens the proof; one status line (label, version, platforms, license); and the proof object with a one-sentence caption. The first 12 words say what the product is or what the reader gets. Allow at most one coined term above the fold, and define it. Keep version strings, digests, and schema names out of the heading and summary.

**Sections, in order.** Who it is for; the idea (the belief, one precedent if one applies, and the open question); what it does; how it works, shown with one real example; get started; how it compares, when real alternatives exist; limits, including when the product is the wrong choice; and the footer, with the tagline and one label per destination. The status label lives in the hero status line only. Each section has a short eyebrow, a heading that is a sentence, an introduction of no more than two sentences, and one object.

**What not to copy between products.** A programming language may put code, spec identifiers, and a spec sheet above the fold; an app shows its interface instead. Do not borrow another product's metaphor, lineage, or proof device. Do not put caveats in every section, a terminal as the get-started object for an app, a founder letter on a product page, anonymous testimonials, or puns in display lines.

## Before you ship

- Every claim is true of the current release, and every number traces to a source.
- No other product could publish the line unchanged.
- The hero's first 12 words say what the product is or what the reader gets.
- Names match the record's `names`, and each concept has one noun.
- Shorter fields are cut from longer ones and make no different claim.
- The status appears once.
- The copy passes `STYLE.md`, including the internal vocabulary list.
- Someone read the hero and the first two sections aloud.
- A reviewer who did not write the copy rechecked every absolute word (*any*, *every*, *never*, *always*) against the source.
