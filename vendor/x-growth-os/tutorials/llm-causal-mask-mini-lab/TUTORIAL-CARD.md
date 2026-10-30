# Tutorial Production Card — LLM Causal Mask Mini Lab

- **ID**: T001 / `20261025-006`
- **Primary category**: `TUTORIAL_BUILD_AND_LEARN`
- **Audience**: Python-capable beginner learning LLMs from GitHub
- **Outcome**: independently verify causal mask prevents future-token leakage in a small scalar attention example
- **Source**: [Datawhale DIY-LLM](https://github.com/datawhalechina/diy-llm), chapter 4 and Assignment1, pinned upstream `95a3b81d`; [official PyTorch SDPA](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)
- **Reproduction**: **PASS** on Linux / Python 3.13.5 / standard library CPU, run date 2026-10-25; [real stdout and five tests](REPRODUCTION-2026-10-25.md)
- **Boundaries**: not a trained LLM, not full upstream Assignment1; other OS unverified; no claimed productivity improvement or revenue
- **Full runbook**: [README](README.md) and two original Python files
- **Rights and security**: cite original CC BY-NC-SA source; do not paste API tokens; no external services needed
- **Tutorial availability**: **PRIVATE_REPO**; not available to public X readers! Do not put this repo's private tutorial URL in a public promise. X copy links to accessible original Datawhale curriculum as learning reference.
- **Artwork**: 1600×900 PNG actually rendered and displayed in ChatGPT, `/mnt/data/x_llm_tutorial_pilot/llm_causal_mask_editorial.png`; GitHub versioned vector [SVG](attention-mask-editorial.svg). PNG binary not in GitHub.
- **ALT**: `Editorial test comparison for a CPU-only causal-attention mini lab: changing a future token leaves the first output at 1.000 with causal masking, while without the mask it shifts from 2.575 to 30.000. Five Python unit tests passed. This is a toy lab, not a trained language model.`
- **Visual QA** (subjective): point 2/2, topic 2/2, visual hierarchy 2/2, mobile main result 2/2, data/accuracy 2/2 = **10/10**. Small footer is informational, not essential on thumbnails.
- **English post status**: `draft, text+image_ready`, no actual X URL; see [post package](../../posts/2026-10-25-006-llm-causal-mask-tutorial.md).
- **Full tutorial public distribution gate**: **BLOCKED_PUBLIC_MIRROR** until the isolated tutorial package is intentionally copied to an approved public location. Never make the private operations repo public to satisfy this condition.
- **Next review**: before making a public "full guide" claim or when code/prerequisites change.
