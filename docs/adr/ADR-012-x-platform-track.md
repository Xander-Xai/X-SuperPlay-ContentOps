# ADR-012: The X track is vendored, gated, and manual-only

## Status

ACCEPTED 2026-10-30 — staged by importing the workflow, then adding the gate it
never had. Builds on [ADR-011](ADR-011-single-home-platform-tracks.md) and obeys
[ADR-005](ADR-005-human-approval.md).

## Context

[ADR-011](ADR-011-single-home-platform-tracks.md) made this repository the single
home for every platform it publishes to. Two tracks exist: video (producers and
gates in `src/contentops`) and 公众号 (vendored at `vendor/gzh-thinktank/`). The
third row of that decision — X — was empty, and `docs/CURRENT-STATE.md` said so
plainly: "not started: no account DNA and no publisher".

The source repository `Xander-Xai/X-SuperPlay-X-Growth-OS` is a working operating
manual for an English X account: positioning, prompts, seven post drafts, CSV
metric templates and one read-only analytics script. It has **no X API and no
publisher**. Every post in it is `draft`, and its own integrity check refuses to
call a post published without a real `x.com/<handle>/status/<id>` URL.

What it did not have is enforcement. "Three theses, each with evidence and a
counterexample", "1600×900 raster card", "ALT text", "a scored human review",
"never claim a first-person run on a source-analysis post" were prose. Prose
gates do not fail a build.

## Decision

**Vendor the X workflow verbatim behind a digest pin, declare a new account
schema for a text account, and ship a delivery gate whose publisher is
`MANUAL_ONLY`.**

### 1. Vendored, not re-implemented

`vendor/x-growth-os/` is a straight copy of 64 files (345,872 B) at commit
`3154db49ad2b070bf5dea2d8fb9a1fc4fdba6f44`, with nothing excluded — the tree is
entirely Markdown, Python, CSV and SVG, so no exclusion would have been
defensible. `scripts/x_growth_pin.py` recomputes the content digest and re-runs
the vendored suite behind `--suite`; a mismatch is a failure.

The tree is never edited. A change is a new import with a new digest, exactly as
with the 公众号 tree. This repository owns the copy, not the workflow.

### 2. A new account schema, not `contentops.account-dna/v2`

An English X account is not a film account. `contentops.account-dna/v2` asserts a
composition that sums to 100, `render.engine == "easel"`, a 1080×1920 canvas and a
generated `easel.yaml`. A text account has no such facts, and bending v2 around it
would make the validator assert things that are not true — the failure mode the
repository's own "FAIL is FAIL" rule exists to prevent.

So the X account declares `contentops.x-account/v1`, checked by its own rules.
`src/contentops/accounts.py` is the single place that decides which schema a file
in `config/accounts/*.json` is. That matters because the directory is globbed in
four places and three of them index video keys directly: without the shared
helper, `build_account_variants`, `check_retention` and `export_easel_yaml` would
raise `KeyError` on the new file or, worse, emit a bogus `easel.yaml` for an
account that will never render a frame. They now iterate video accounts only.

### 3. The pipeline is declared, not inferred

`evidence.mode` is a closed video vocabulary — `EVIDENCE_LED`, `EXPLANATORY` —
and its members describe how a film is assembled. An X post has no capture step
and no audio-first plan, so there is no honest value of `evidence.mode` for it and
the X account does not use one.

Instead the account declares `pipeline: "X_EDITORIAL"`, and
`scripts/account_route.py` resolves a declared pipeline before an evidence mode.
The chain is `research → editorial → visual → package → publish → measure`, where
`publish` is a person's action recorded as a URL and `measure` is the vendored
read-only report pointed at the project root.

An account that declares a pipeline the router does not know is refused with
`PIPELINE_UNMAPPED`. It is a separate refusal from `EVIDENCE_MODE_UNMAPPED` on
purpose: "you named a pipeline I have never heard of" and "your evidence mode
implies no chain" are different mistakes, and neither may silently fall back to a
video chain.

### 4. One gate, named refusals, and a publisher that cannot publish

`scripts/x_post.py` and `src/contentops/publish/` turn the vendored prose into
code. Every refusal has a name: `COPY_TOO_LONG` (280 weighted characters, URLs 23,
CJK and emoji 2), `IMAGE_ABSENT`, `IMAGE_NOT_RASTER` (an SVG alone is refused),
`IMAGE_WRONG_ASPECT`, `THESES_INSUFFICIENT`, `REVIEW_SCORE_LOW`,
`FIRSTHAND_CLAIM_UNSUPPORTED`, `PUBLISHED_WITHOUT_URL`, `METRIC_NOT_OBSERVED`, and
the rest. The verdict is derived from the same issue list in one place —
`DRAFT | IMAGE_MISSING | READY | PUBLISHED | BLOCKED` — so the CLI, the package and
the receipt cannot disagree.

`PublishMode.MANUAL_ONLY` writes a publish package and stops at
`AWAITING_MANUAL_PUBLISH`. `PublishMode.API` raises `PublisherUnavailable`. A test
asserts the package imports no `socket`, `ssl`, `http`, `urllib` or `requests`:
the boundary is executable, not a comment.

The gate is scoped to X posts. It is deliberately **not** a second copy gate in
front of the video producers, and it does not sit inside the script-quality gate
(SQ01–SQ07 describe silent gaps, layouts and presenter continuity, which an X post
does not have).

### 5. Image production is a renderer, not an image model

The card is HTML rendered to a 1600×900 PNG by the routed skill (`card-quote` under
the `card-design` system, `.runtime/easel/skills/shared/scripts/render_card.py`).
Typography and numbers are therefore exact and legible. The HTML is tracked; the
PNG is gitignored, so a fresh checkout re-renders it and sees `IMAGE_ABSENT` until
it does — which is the honest state, not a broken one.

## Consequences

- A project can be routed to `X_EDITORIAL`, a draft can be graded, a package can be
  produced, and a real URL can be recorded. No network call, no credential.
- The X account's handle is `null` with `handle_status: "UNKNOWN"`. It is not
  invented; the first real status URL teaches it, and is recorded.
- `projects/x-growth-en/` carries one real record whose terminal state today is
  `DRAFT` with a single `REVIEW_MISSING`. The review is a person's and has not
  happened. `--package` refuses it, correctly.
- The seven vendored drafts stay `draft`. Rendering them into packages is content
  work, not an import task, and this ADR does not claim it.
- Metrics that were never observed stay `null`. The vendored analytics already
  refuses to treat blanks as zeros and the gate does not undo that.
- Nothing here proves reach, demand or follower growth, and nothing in the X track
  is causal attribution.

## What a later API ADR must prove

`MANUAL_ONLY` is the current status, not a placeholder. An X API publisher is a
separate decision and needs, at minimum:

1. a capability spike against the real account (tier, app permissions, OAuth 1.0a
   media upload, rate limits) — no provider capability may be invented;
2. credentials outside both trees, never committed and never read by an agent;
3. a proven way to keep "automated post" honest in the record: a post becomes
   `published` when the platform returns a status URL, not when a request is sent;
4. a decision about what the gate does when an image upload fails after the text
   is accepted.

Until then the seam is a raised exception and a named refusal.

## Reversibility

Deleting `vendor/x-growth-os/`, the X account and its prompt, `PIPELINE["X_EDITORIAL"]`
in `scripts/account_route.py`, `src/contentops/publish/`, `scripts/x_post.py`,
`projects/x-growth-en/`, and the two pin/gate test suites restores the previous
state. The video and 公众号 tracks are untouched either way: the X account is the
only `contentops.x-account/v1` file, and removing it leaves the video globbers with
exactly the two accounts they had.

## Open questions

1. Who is the reviewer for the X track, and does the score floor of 24 (of 30) hold
   at three posts a week without becoming ritual?
2. Does the English account publish under this repository's identity or its own?
   The handle is unknown today, so the record keeps it unknown.
3. Should the seven vendored drafts be re-dated into `projects/x-growth-en/posts/`,
   and if so, does one of them still describe work that has not happened?
