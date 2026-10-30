# Mandatory Text + Image Delivery Gate (V0.9)

**Effective 2026-10-25. Owner decision: EVERY X post produced by this workflow must be paired with an actual, topic-matched image.** This supersedes every historical "text-only is acceptable", "no image" or "optional picture" exception in this repository. It applies to `DAILY-POST`, `GITHUB-URL-TO-X`, `X-HIGH-SIGNAL-TO-POST`, **`TUTORIAL-TO-X`**, scheduled drafts and revisions. No post-only delivery.

## Definition of a publish-ready unit

A **post package** MUST include:
1. **English publication copy**: one X post by default; up to 3 only when necessary. Original insight, first-party source links, fact-vs-analysis boundaries, X weighted-length estimate and composer check.
2. **Actual 16:9 image**: a legible, correctly named, source-aligned 1600×900 PNG or JPEG that the user can attach to X; an editable SVG source may accompany it **but an SVG alone is NOT sufficient for X upload**.
3. **ALT text**: 1–2 English sentences describing what is actually visible, avoiding unverified numbers and invented UI.
4. **Research and approval record**: source URL(s), original X signal (when available), 3 competing insights, rebuttal, content and visual QA, release status, and the actual asset filename/path.
5. **GitHub archival link to the image** when upload is possible; otherwise an exact VERIFIED generated conversation attachment link must be delivered and the post record must note `external_image_pending_archive`. Do not invent a GitHub PNG link.

## Mandatory execution order

`Discover X/GitHub → Evidence & value gate → 3 theses / red-team → final English post → image-specific art direction → CREATE actual image → inspect/render & match copy → ALT → package and archive → human approval → X publication → actual status URL.`

**Image art direction precedes generation**. The image's claim must be directly justified by the actual post. Read [visual standard](VISUAL-EDITORIAL-STANDARD.md) and [visual brief](../prompts/VISUAL-BRIEF.md). Prefer a source-backed screenshot/diagram or restrained editorial illustration, never generic robot/neon/cyber stock style. All factual numbers/text must be legible and checked. For exact labels or quantitative graphics, deterministic SVG/vector typesetting → PNG export is preferred; image models may provide an illustrative element, not fabricated technical evidence.

### Image hard stop

- If image is absent, wrong project, misspelled, fabricated, unreadable on mobile, inconsistent with text, or not an actual image file, **do NOT call it a completed post, do NOT recommend publishing it**.
- Record as `draft` with `image_status=missing|failed_qa|pending_export|external_image_pending_archive`; don't mark `ready_to_publish`.
- Fix with targeted re-generation, controllable SVG+PNG export, or select a different suitable visual. If all attempts fail, **stop, report blocker and keep as draft**. Never "fall back to text-only" under the current user requirement.
- An abstract illustration is allowed; it must still visibly convey this post's specific idea. It must not masquerade as benchmark, real screenshot or verified business effect.
- Prior drafts #001–#004 are legacy artifacts. They remain `draft`; revalidate that *each* has an actual appropriate X-uploadable PNG/JPG and record its path before publication. Previous text-only recommendation for #004 is **withdrawn**. Do not silently claim prior image files were uploaded.

## Validation checklist (all pass)

- [ ] Post is relevant to AI work efficiency or evidence-bounded commercialization, not merely a popular project.
- [ ] Source date and claims verified; X discussion's metric provenance stated, no invented hype.
- [ ] English post final, ≤280 X weighted chars each; original, specific, defensible.
- [ ] An actual image file (PNG/JPG) is accessible, paired to this exact post; 16:9 and readable around 400px width.
- [ ] Image and post share one core claim; no wrong logo, fake screenshot, fabricated chart or unreadable typography.
- [ ] ALT text matches actual image; image score ≥8/10 with factual accuracy 2/2.
- [ ] Actual image link or verified local attachment, asset status and original source(s) saved.
- [ ] Publishing remains human-approved; never label `published` without actual `x.com/.../status/...` URL.

**Independent state concepts**: `image_status` is not `post_status`. Valid `post_status` is `draft` / `scheduled` / `published` / `failed`. A post can be draft with image complete. `image_status=generated` must refer to a real checked image, not just an SVG idea, placeholder or an image prompt.

## Non-negotiable acceptance

The response to an X content request must visibly deliver the final English copy **and the real image together in the same answer**. Never deliver only a research summary, only an image, or only a prompt. If any mandatory component cannot be produced, say which one is blocked and keep the package in draft state. This is a **workflow delivery requirement**, not permission to circumvent X authentication, licensing or platform rules.
