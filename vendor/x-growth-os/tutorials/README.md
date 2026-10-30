# Reproducible Tutorials — Build & Learn

This directory stores complete **original** step-by-step guides only when the guide can be sourced and the steps can be stated truthfully. A list of links or generated prose is NOT a validated course.

**Start:** [Tutorial editorial SOP](../docs/TUTORIAL-CONTENT-WORKFLOW.md) · [Source register](../docs/TUTORIAL-SOURCES-2026-10-25.md) · [Candidate CSV](../templates/tutorial-candidates.csv) · [Runbook skeleton](../templates/TUTORIAL-RUNBOOK.md) · [Tutorial card](../templates/TUTORIAL-CARD.md).

## Lifecycle

`source_only → lesson_draft → REPRO_PENDING → repro_verified → x_media_ready → human_approved → published`.

- Maintain a folder only when implementing an actual lesson: `tutorials/<slug>/README.md`, `TUTORIAL-CARD.md`, `examples/`, `assets/`, and `CHANGELOG.md` when needed.
- Every runbook includes learner objective, environment, **copyable numbered actions**, expected outputs, verification, troubleshooting, safe rollback, known costs, source attribution/versions and dated evidence.
- `REPRO_PENDING` means **NOT tested**. Never represent examples below or the candidates CSV as completed runnable tutorials.
- For X: derive one English hook with a real *paired PNG/JPG*, ALT and full GitHub lesson URL. The image requirement is mandatory on **every X post**; do not ship a text-only excerpt.
- Archive without hardcoding secrets, personal account identifiers or third-party copyrighted transcripts/screenshots; use own screenshots or obtain permissions.

## First longform flagship (2026-10-25)

- [13-section GitHub LLM learning guide](github-llm-complete-guide/README.md): from repo search, prerequisites and sources to a personal learning repo, tested narrow lab, issues/PR and future curriculum. **Not all web UI steps were independently executed.**
- [English X draft #007 + real matched image/ALT](../posts/2026-10-25-007-github-llm-longform.md). Full original guide is internal Private, not publicly accessible until separately published.
- The original Causal Mask lab remains a valid tested exercise within this broader educational course, not the entire course.

## First produced and tested lesson (2026-10-25)

- **[Lab 01 — Prove causal masking with a CPU mini-experiment](llm-causal-mask-mini-lab/README.md)**. Original Python standard-library code, five passing tests, exact stdout, beginner runbook, troubleshooting and restrained editorial image source are saved in the private repo. [Reproduction evidence](llm-causal-mask-mini-lab/REPRODUCTION-2026-10-25.md).
- **Scope is narrow**: this is our own attention demo **inspired by** DIY-LLM chapter 4, not execution of Datawhale's official Assignment1 model training. The full source text remains PRIVATE; don't link private GitHub to unapproved X readers. An independent downloadable ZIP is available to the author in the ChatGPT conversation.
- [Corresponding original X copy + image package](../posts/2026-10-25-006-llm-causal-mask-tutorial.md) is `draft`, not actually posted.

## First pilot candidate

**T001 — “How to learn LLMs from GitHub without getting stuck in setup.”** Start with [datawhalechina/diy-llm](https://github.com/datawhalechina/diy-llm) and its [online book](https://datawhalechina.github.io/diy-llm/). A useful first **test to perform later** is selecting one lesson and capturing (1) exact prerequisite versions, (2) commands that really run on the chosen environment, (3) a checked output, (4) one failure diagnosis and fix. **Not yet executed**, so do not tweet “I tested this whole curriculum” or invent timings.

## Future online reading

Markdown and exact GitHub permalinks first. Once there are >=10 actually verified tutorials and user demand, compare [Docusaurus](https://github.com/facebook/docusaurus) vs [Quarto](https://github.com/quarto-dev/quarto-cli) vs [Zensical](https://github.com/zensical/zensical). No extra hosting or CI setup is needed for this V0 editorial addition.
