# X Post #006 — Build & Learn: prove causal masking in a CPU mini lab

**Content ID:** `20261025-006` | **Date:** 2026-10-25 | **Status:** `draft` — NOT published on X.  
**Type:** `TUTORIAL_BUILD_AND_LEARN` · **topic:** LLM learning through Github / verifiable code, not news from past 72h.  
**Research:** [Datawhale DIY-LLM](https://github.com/datawhalechina/diy-llm) [chapter4 pinned reference](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/docs/zh/chapter4), [upstream Assignment1](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/coursework/assignment1-basics); [official PyTorch attention API](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html).  
**X high-interaction signal:** no directly verified source for this specific learning claim; Github-primary fallback used; no invented engagement metrics.
**Technical trial:** [complete original lesson](../tutorials/llm-causal-mask-mini-lab/README.md) + [actual reproduction log](../tutorials/llm-causal-mask-mini-lab/REPRODUCTION-2026-10-25.md); PASS on Python 3.13.5 Linux CPU, 5 standard-library tests. **Not an upstream complete course run.**

## Three candidate editorial angles

| Angle | Mechanism and student decision | Counterexample / limitation | Subjective score |
|---|---|---|---|
| **Start with a falsifiable invariant (selected)** | Learn causal attention by changing a future token and confirming early output invariance. Reduces conceptual confusion and is a real local experiment. | Toy 1D Q=K=V example does not represent a trained LLM or benchmark. | **27/30** |
| Start with full training | Real end-to-end training shows models in action. | Unpinned tokenizer, weights and data create heavy dependencies; no run attempted here. | 18/30 |
| Read 10 curated repositories | Great survey of architecture patterns. | Passive curation alone doesn't prove learner understanding. | 18/30 |

Six rubric scores for chosen angle: novelty 4, primary evidence 5, mechanism 5, reader decision 5, reproducibility 5, expression 3 = 27/30. Editorial rating only; not engagement prediction.

## English publication copy — exactly one X post

```text
LLM tutorials should start with a claim you can test.

Change a future token. With causal masking, the first output stays 1.000. Without it, the output shifts from 2.575 to 30.000.

CPU-only toy lab; 5 tests pass.

Source curriculum: https://datawhalechina.github.io/diy-llm/
```

**Character check:** 275 Unicode code points including literal URL; X weighted estimate 257 using URL as 23 characters. Recheck in official X Composer.

## Image required for this post

- **Actual 1600×900 PNG:** `/mnt/data/x_llm_tutorial_pilot/llm_causal_mask_editorial.png` (rendered, inspected and delivered in the ChatGPT conversation; exact local artifact, not in GitHub).
- **Source SVG in GitHub:** [editable image source](../tutorials/llm-causal-mask-mini-lab/attention-mask-editorial.svg).
- **ALT:** `A minimal English infographic compares a CPU-only causal-attention mini lab: after a future token changes, the first output remains 1.000 with masking but shifts from 2.575 to 30.000 without masking. Five Python tests passed. This is a toy demonstration, not a trained LLM.`
- **Visual QA:** 10/10 for correctness/main text/hierarchy, subjective. Source-based numbers exactly match the tested script. Does not pretend a training run.

## 中文准确译文

LLM 教程应该从一条可以测试的结论开始。

修改一个未来 token。使用因果掩码时，第一个位置的输出保持 1.000 不变；不用掩码时，从 2.575 变成 30.000。

这是一个只需要 CPU 的玩具实验，5 个测试已通过。

公开的课程来源：Datawhale DIY-LLM。

## IMPORTANT — private repository reachability

The current X Growth OS repository is **private**. The **complete original mini-lab README and Python scripts here are NOT accessible to unapproved X readers**. Therefore the tweet links the **public original curriculum**, not a false "public complete guide". The public curriculum is genuine, but it is **not a public copy of our independent mini-lab**.

**Public tutorial publication state:** `BLOCKED_PUBLIC_MIRROR` — an isolated code/tutorial mirror or authorized public distribution is required before advertising a public link to the exact steps. Do NOT switch this private operations repo to public automatically.

**Post package:** copy + verified actual PNG + ALT are READY FOR HUMAN REVIEW. X publication itself is `draft`; no authenticated X publisher exists. The exact mini-lab code can be delivered as a local downloadable package to the author; external X users need separately approved access.

## Publish sequence

1. Review English claim, source curriculum and image; do not claim LLM training or that own GitHub code is public.
2. Open X Composer, paste exactly one post, attach the actual PNG, add ALT, confirm X weighted characters.
3. Publish once, record real `x.com/.../status/...` URL, and update [posts.csv](../templates/posts.csv) only after the URL is verified.
4. If making this a continuing series, publish a dedicated public tutorial mirror *after explicit repository scope and secret/license check*, then update the X thread with a link rather than inventing availability.
