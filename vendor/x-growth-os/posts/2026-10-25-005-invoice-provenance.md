# X Post #005 — Parsing is not approval

**Content ID:** `20261025-005` · **Date:** 2026-10-25 (Asia/Shanghai)  
**Workflow:** mandatory [text + image delivery gate](../docs/POST-IMAGE-DELIVERY-GATE.md) (V0.9).  
**Status:** `draft` (publishable copy and image supplied, but **no X account connection or live post URL**). Human must approve and publish.  
**Mode:** `TOOL_EVERGREEN` — no verified material change in the last 72 hours was claimed.  
**Editorial scope:** AI efficiency and a **commercialization hypothesis**, not a product launch or verified customer story.

## Research facts and source status

1. **[Docling official GitHub](https://github.com/docling-project/docling)** and [DoclingDocument documentation](https://docling-project.github.io/docling/concepts/docling_document/) describe PDF/table parsing, structured output, provenance and bounding boxes when available. They do **not** establish flawless invoice extraction.
2. **[Activepieces official GitHub](https://github.com/activepieces/activepieces)** documents workflow automation and human-in-the-loop approval steps. This does **not** demonstrate a ready-made Docling ↔ Activepieces invoice integration.
3. **X research:** no current original X post with sufficiently verified post-level high engagement was found for this exact invoicing claim in this run; this draft uses the explicit *GitHub/first-party fallback* of the [dual-source SOP](../docs/X-SIGNAL-RESEARCH.md). Do not invent a viral X signal or engagement counts.
4. **Costs/conditions:** deployment, invoices' private data and consent, parser mistakes, review labor, approval delegation, product license and maintenance must be examined before a paid offer; no price, customer revenue, ROI or benchmark was independently verified.

## Three independent editorial theses

| Angle | Judgment | Evidence and causal mechanism | Strongest limitation | Subjective editor score |
|---|---|---|---|---:|
| **A — Extraction ≠ approval (chosen)** | Financial process value depends on traceable source evidence plus an explicit exception/approval step | Docling structured document provenance; Activepieces approval workflow; proposed process connects them | No actual integration or invoice accuracy test has been done | **26/30** |
| B — Accuracy needs field-level proof | A perfect-looking JSON response may hide a false amount unless it is linked to its PDF position | DoclingDocument provenance/geometry can support traceability | Source coordinates alone do not verify the amount or payment authority | 24/30 |
| C — Sell the exception queue | A buyer might prefer paying for fewer unresolved invoice disputes rather than just PDF conversion | Possible delivery: reviewed queue with audit logs, not a proven commercial product | No customer commitment, cost model or willingness-to-pay validation yet | 23/30 |

Chosen six scores: novelty 4; evidence 5; mechanism 5; decision value 5; testability 4; expressive tension 3 = **26/30**. This is an editing score, not an X ranking score.

**Red-team objection:** approval stages can slow straightforward invoices, provenance links can be wrong or coarse, and expensive manual review can eliminate savings. The solution is not "AI everywhere" but **sample-based evaluation and only reviewing exceptions**. Proposed test on consented sample: tag 20 diverse invoices, compare extraction fields to source, create a mismatch queue and review ledger, count manual minutes per exception and errors. *No test conducted here*.

## Final English X copy (paste verbatim)

```text
An invoice-to-JSON demo isn't an accounts-payable product.

Docling parses PDF tables with provenance. Activepieces supports approvals.

The service to test: link each amount to its source, flag mismatches, and leave a review trail.

https://github.com/docling-project/docling
```

Raw Unicode code-point length: **276**. X URL-weighted estimate (URLs treated as 23 characters): **257**. Verify the post's actual count in X Composer. Images do not consume body characters in standard X composer.

## Required paired image (real asset)

- **PNG (1600×900, actually rendered and visually reviewed):** `/mnt/data/x_post_005_provenance.png` in the associated ChatGPT response, user-downloadable attachment. This conversation-local file is **not** claimed to have been uploaded to GitHub; `image_status=generated_png_in_chat_svg_in_repo`.
- **Editable GitHub SVG of the same diagram:** [2026-10-25-invoice-provenance.svg](../assets/2026-10-25-invoice-provenance.svg) (SVG is a source, not a substitute for the required X-uploadable PNG).
- **Conceptual claim:** SOURCE → EVIDENCE → REVIEW. It is a proposal, not a fabricated UI or a production result.
- **English ALT:** "Minimal editorial diagram titled ‘Parsing is not approval.’ An original invoice flows into traceable source-linked fields and then human review of exceptions. This is a proposed Docling and Activepieces workflow, not a tested integration."
- **Visual gate:** message 2/2, topic 2/2, hierarchy 2/2, mobile readability 1/2 (small footer is not intended for thumbnail reading), factual legibility/accuracy 2/2 = **9/10**, subjective editorial QA. No fictional invoice values, fake benchmark or invented product screen.

## Chinese translation

把发票转换成 JSON 的演示，还不等于一套真正的应付账款产品。

Docling 能解析 PDF 表格并保留来源信息。Activepieces 支持人工审批步骤。

值得验证的服务是：把金额关联回原始来源，标记不一致的内容，保留复核记录。

GitHub 链接见英文原帖。

## Publication gate

1. **Must bring both** the final English post above **and the actual PNG** to X. Do not publish text-only.
2. Check counted characters, image readability/crop, source URLs and the provided ALT in X composer.
3. Human approves and publishes the single X post. **Only** after the live `https://x.com/.../status/...` URL can `status=published` be recorded in [posts.csv](../templates/posts.csv).
4. PNG is currently available through the conversation attachment and as a render of the archived SVG. Archive binary PNG separately when a supported attachment-to-GitHub uploader is available; do not fabricate a GitHub binary path.

**Status after generating this artifact:** draft with complete text+visual, external image attachment ready, not yet published.
