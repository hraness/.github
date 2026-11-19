# Writing articles

Every Hraness host renders articles with the same shape, using components and checks that live in the host's own source. This guide says what goes in each part and which posts a host may publish. [`STYLE.md`](STYLE.md) still owns voice and conventions, [`GENERATION_STYLE.md`](GENERATION_STYLE.md) owns the instructions for models that draft posts, and [`MESSAGING.md`](MESSAGING.md) owns product names, messaging records, and social channel limits.

The names below (`heading`, `dek`, `ArticleSources`, `LaunchBeat`, `assertArticleAdmissions()`, and the rest) name the parts and checks a host implements. They are not imports from a shared package. `@hraness/design-kit`, which once shipped them, is frozen: do not add new dependencies on it, and copy what a site still uses into that site.

Article and index pages use the host's product header, with the same brand mark, home link, navigation, and final appearance control as its homepage. Place that header before and outside the main landmark; the article's own title header remains inside the article. Breadcrumbs and feed links belong in the reading column. Check every rendered public route for that header in the host's browser checks, so a missing header cannot pass a layout check.

A reader arrives with one question. The title names it, the dek answers it in one sentence, and the body shows the evidence.

## Parts of an article

Limits are maximums. Count characters in the rendered text.

| Part | Write | Limit | Avoid |
| --- | --- | --- | --- |
| `heading` | The question or the result, in sentence case with no period. | 70 characters | Clickbait, a question the article does not answer, and a colon followed by a second title. |
| `dek` | One concrete claim, as a complete sentence, that a reader could check. | 200 characters | A summary of the article's sections, "In this post", and claims with no source in the body. |
| `eyebrow` | The series or post type: "Technique", "Release", "Integration". | Three words | A tagline. |
| `author` | The organization byline on every host: `{ kind: "organization", name: "Hraness" }`. | | A person's name on a post that person did not adopt. |
| `provenance` | The drafting kind and the review on record. | | Omitting it on an AI-drafted post. |
| `toc` | One entry per `h2`, only when the article has four or more. | Eight entries | Entries for `h3` headings. |
| Body headings | Sentence case, each naming what the section shows. | 70 characters | Signpost headings such as "Overview", "Conclusion", or "Key takeaways". |
| `ArticleSources` | Primary sources a reader can open, retaining the date someone last checked the cited claim in each record. | | Secondary summaries when the primary source is public. |
| `ArticleRelatedProducts` | Siblings from the registered relations for this article, each shown with its mark, name, and one-line description. | Three items | Every product in the portfolio. |
| `ArticleCallout` | A limit or warning the reader must see before acting. | One short paragraph | Decorative asides and restated body text. |

### Date presentation

For evergreen explanations, hide dates in the article, the article index, and the sources list. Each of them controls its own date presentation. Dates remain visible by default for release notes and other chronological writing.

This option hides publication, update, or source-check dates from the rendered text. It keeps authors, review credits, source links, and publishers visible, and removes rows that would otherwise be empty. The `published`, `updated`, and `checkedOn` fields retain their existing types and validation. Keep their true values in article records and use them for feeds and structured metadata; hiding a date never changes it.

## Post shapes

### Introducing a product

Title: "Introducing <product>". It lives on the product's own host, and each active product gets one. The reader's job is to decide whether to try it, so the admission record says `readerJob: "decide whether to try it"`.

Publish it at a permanent URL, mark it evergreen, and pin it as the product guide above recent changes on `/blog`. Keep its original publication date. Update the guide and its modification date as the product changes.

Open with one situation a reader will recognize. Walk through a real task using the names they will see in the product. Tell them what they start with, what they do, and what they get. Include enough detail to help them decide whether to try it. Mention availability, cost, platform requirements, or limits where they affect that decision. A paused product says so. Retired and legacy products get no introduction.

Show one or two captioned examples of shipped behavior. Reuse a working homepage control or an actual product capture where it helps. A second example should teach a different part of the workflow. Give images descriptive alt text and interactive examples a keyboard path. Keep the steps understandable on a narrow screen, with reduced motion, and in the text alone.

Put further reading, source credits, and the review note before the closing action. End with the product journal's shared call to action. Its label names the next step the reader can take today. Use the site's existing analytics consent settings to measure when the action comes into view and when a reader follows it. Use the shared layout check in the site's browser tests and check where the link goes.

#### Beats

Beats are the source material for launch films and social posts. Build the campaign from the same verified product facts as the evergreen guide. The guide chooses the examples that explain its task. A campaign can cover more surfaces and point readers to that guide.

For the campaign, write 7 to 10 beats, about 40 to 60 words each, in this order:

| Part | Beats | Write |
| --- | --- | --- |
| `what` | 1 | What the product does, stated plainly. No question, teaser, or "here's why". |
| `does` | 1 or more | One surface or mode each, tied to one mockup state or clip. |
| `how` | 1 | How it works, in the reader's terms. |
| `who` | 1 | Who it is for, and who should use something else. |
| `vision` | 1 | Where it is going, as intent. |
| `limits` | 1 | What it does not do yet, once, at its true scope. |
| `status` | 1 | The status label and how to get it. |

- Each beat has a headline of 70 characters or fewer, in sentence case with no period, and a post of 250 characters or fewer that works on its own as one social post.
- Social posts carry claims only. The `limits` beat, and any caveat, known gap, negative finding, audit or review line, or legally required disclaimer, stay in the launch post, the docs, and the site, and never reach a social post, the Show HN facts, or the Product Hunt fields. Every social post must still be true on its own: when a caveat is what keeps a beat's claim accurate, give the beat a `socialPost` that states a narrower claim accurately without it, or mark the beat `social: false`.
- Each beat has exactly one visual, and no two beats share one. Alt text is 125 characters or fewer and describes the visual accurately. Visible captions are optional and add context; never repeat alt text or require a generic illustration disclaimer.
- Keep beat IDs stable for campaign assets. Preserve existing public links when revising a guide.
- Technical depth, comparisons with other products, and tables go in companion posts or `/compare` pages. Link them from the beat with `detailHref`.

#### Launch data

Keep these shapes and the checks below in the product's site source, outside any rendering framework, so the guide and campaign assets can draw on the same source facts.

```ts
type LaunchBeat = {
  id: string;              // stable lowercase slug for the campaign asset
  part: "what" | "does" | "how" | "who" | "vision" | "limits" | "status";
  headline: string;        // may hold {fact} placeholders
  post: string;            // may hold {fact} placeholders
  visual:
    | { kind: "mockup"; id: string; state: Record<string, string> }
    | { kind: "clip"; scene: string }
    | { kind: "diagram"; src: string };
  alt: string;
  facts?: string[];        // every placeholder key the beat uses
  detailHref?: string;     // a companion post
  socialPost?: string;     // social wording when `post` keeps a caveat; accurate on its own
  social?: boolean;        // false excludes the beat from social posts
};

type LaunchFacts = Record<string, { value: string; source: string }>;

type SocialKit = {
  x: string[];
  bluesky: string[];
  threads: string[];
  linkedin: string;
  productHunt: { tagline: string; description: string; tags: string[] };
  showHnFacts: string[];   // facts for a person to write from
  sources: Record<string, string>;
};
```

- **Facts.** Type every number once, in the product's `LaunchFacts` module, with its source: versions, sizes, rates, counts, and prices. The post, the social kit, film captions, and store listings all import it. Fill `{key}` placeholders from it, and reject a beat that types a digit by hand.
- **Checks.** Check the beats' order, counts, limits, and wording rules in tests. Build each channel's posts from the social beats (every beat except `limits` and beats marked `social: false`, using `socialPost` when a beat has one), the Product Hunt fields from the product's messaging record, and the status from the release record. Check each channel's length. Also check that only the last post links, that the last post carries the status and the canonical URL without tracking parameters, that nothing asks the reader to install before a public install exists, that no other product is named, and that no post or fact carries the text of a `limits` beat or a `social: false` beat.
- **Social kit.** Build it only from an `indexable` post. A quarantined post has no social kit. When a press or campaign page offers the kit, render it as a closed `<details>` with a copy button and a character count per post. A person writes the Show HN post and the first Product Hunt comment; the kit gives them the facts.
- **Words.** Social posts follow the rules below, plus: no hashtags, no emoji, and no thread markers such as "1/n".
- **Admission.** A launch post passes the same admission gate as every other article. The launch helpers do not change it.

### How one product uses another

Title: "How <consumer> uses <provider>". It lives on the consumer's host.

1. **The reader's problem.** The job the consumer's user is trying to get done.
2. **What the provider does.** In plain words, for a reader who has never used it.
3. **How the consumer uses it.** The code path, configuration, or data flow, from the consumer's side.
4. **What that buys the user.** The concrete result a user of the consumer sees.
5. **Limits.** What the integration does not cover, once, at its true scope.
6. **Links.** The provider's home page and hub page, and the consumer's introduction.

- Write one only for a relation recorded in the portfolio registry that has a reviewed `detail` sentence. The post expands that sentence; it does not claim more.
- Outside its hub page, the provider's host adds at most one descriptive link to the post, and only after both pages are live.
- When the relation changes or is removed, update or archive the post in the same change.

### Provider hub page

A provider may keep one page, such as "Built on <provider>", that lists the products using it. Each entry is the registered relation's own sentence and a link to the consumer's "How <consumer> uses <provider>" post when one exists. The hub is an index. It does not restate each post.

### Technique posts

A technique post teaches one method, such as property tests, model checking, or proofs. It lives on hraness.com, and a product host may carry a product-specific version that shows the technique inside that product.

- Answer one useful question. Explain the reasoning with a concrete example the reader can follow, using code or notation where it helps.
- Use public references when they clarify the method or support a claim. A product example belongs only when it helps answer the question; neither Hraness code nor a product recommendation is required.
- Keep internal build diaries, verification logs, and implementation chronology out of the article. Teach the method in the order the reader needs it.
- End on the last supported fact. State a material limitation where it changes the reader’s decision; do not append a generic disclaimer.

### Illustrations

Follow the [shared illustration guidance](https://github.com/hraness/.github/blob/main/STYLE.md). Use SlopCamera to create an illustration when it helps explain the article, with a limited brand palette and a reference that establishes the intended visual style. Record the tools, model, references, and actual asset source used; do not substitute a generic provenance claim. Keep captions useful and optional.

## Titles and formulas

- Keep titles to 70 characters or fewer. Most search results cut longer ones.
- The fixed formulas "Introducing <product>" and "How <consumer> uses <provider>" are allowed. Every other title in a series needs its own wording.
- Vary openings, closing sections, and headings across a series. Check the other posts before publishing: no repeated first sentence pattern, closing heading, closing checklist, or disclaimer paragraph.

## Words and numbers

- Follow `STYLE.md`. Do not use em dashes anywhere in the article, including the title, dek, captions, and alt text.
- Do not use these words: delve, tapestry, testament, landscape (for a market), realm, seamless, seamlessly, robust (without the specific property), leverage (as a verb), unlock, empower, elevate, supercharge, game-changer, cutting-edge, revolutionize, harness (as a verb), journey (for a process), and "in today's world".
- Keep internal vocabulary out of articles: admission, admitted, qualification, qualified, custody, settlement, receipt, attest, bounded, boundary, gate, lane, surface, projection, manifest, lease, and the other words `STYLE.md` lists under "Write for the reader, not the build". A technique post may define one of these once when it is the subject.
- Do not invent numbers, benchmarks, quotes, customers, or dates. Every number has a source or a date in the text. Every quote has a named person who agreed to it.
- Type each number once. Versions, sizes, rates, counts, and prices in a launch post come from the product's launch facts, not from the article text.
- State product status once with one of the `STYLE.md` labels: In development, Preview, Beta, Latest release: vX.Y.Z, Paused, or Retired.

## Dual-use products

Some products can be pointed at other people's accounts or data: authenticated browser adapters, automated messaging, exposure scans, clipping tools, and media import. Articles about them:

- describe the owner's own accounts and data, used with the owner's authorization;
- show previews, confirmation steps, and consent before anything is sent or changed;
- say what the product will not do;
- never frame the product as scraping, impersonation, or outreach at scale.

## Drafting and review note

Every article states who drafted it and who reviewed it, visibly, on every host. This applies to articles only; other pages follow `STYLE.md`.

- Render the note from the admission record. Do not type the sentence by hand.
- The default AI drafting kind is `ai`: "Drafted with AI and reviewed by <reviewer>." Use `ai-from-source` and its "from the source code" wording only when the article was drafted from source code.
- Name the reviewer as it is. An AI reviewer has `reviewerType: "ai"` and a name that says it is AI, for example "Claude Opus 5.5 (claude-opus-5-5) editorial review". The sentence says "human" only when `reviewerType` is `human-editor`.
- Keep `humanReview` null unless a person reviewed the article. Never describe AI review as human review.
- The byline is "Hraness" on every host. Do not credit a person, including the owner, for an AI-drafted post. A person who later adopts a post may switch the byline to their own name; the drafting and review note stays.
- A post with no review on record renders "It has not been reviewed yet." and stays quarantined.

## Admission and indexing

Every article URL has an `ArticleAdmission` record in its host's registry, checked by `assertArticleAdmissions()` in tests.

- A new post starts `quarantined`: readable, `noindex`, and absent from the sitemap, feeds, `llms.txt`, and index lists.
- It becomes `indexable` only when the record passes: six scores of 0 to 2 totalling at least 9 with no zero, a review with reviewer and `reviewerType`, at least one source with a check date, two observations that are not paraphrases of the sources, and at least one refresh trigger.
- An independent, disclosed AI review can admit a post. Record it as `reviewerType: "ai"`. The validator rejects an AI reviewer name that does not say it is AI (for example by naming the model), and it rejects `reviewerType: "author"` for an indexable post, because the author cannot admit their own post.
- `archived` keeps an old URL working without listing it.

## Freshness

- Keep review, publication, and update metadata truthful. Educational bodies do not need repeated "as of" dates, build identifiers, or freshness labels; include a date or version in the prose only when the explanation depends on it.
- Every record has `reassessOn`, 28 to 56 days after `review.reviewedOn`. `articleAdmissionsDue(registry, today)` lists the records to look at again.
- Render versions, release dates, and status labels from release data (`package.json`, a published release file, or the portfolio registry). Never type a version into an article body.
- Each record names its refresh triggers: a release tag bump, a change to a relation's `detail`, a rename, or a change to the feature the post describes.
- When a product is renamed, update article bodies, titles, and slugs (with redirects) in the same change as the rename.
- When a feature an article describes changes, refresh the article or archive it. Update the `updated` date only when the content changed.

## Interlinking

- Add a link only when it is the reader's next useful action. Use a descriptive anchor.
- Follow registered relations. Do not link every product to every other product.
- No minimum link counts, reciprocal link swaps, or footer link farms.
- Every article stands on its own. A reader who follows no link still gets the answer.
- Link to another host only after both URLs are live.

## Check before publishing

Read the title, dek, and first paragraph aloud. Open every source and confirm the cited claim on the check date. Render the article at 1280px and 375px wide; code blocks scroll sideways and tables stay readable on a phone. Run `assertArticleAdmissions()` on the registry.

## Block for product repositories

The `hraness-articles` block in [`AGENTS.md`](AGENTS.md) is the block product repositories carry. Copy it from there, not from this guide.
