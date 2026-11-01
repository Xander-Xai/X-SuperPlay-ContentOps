# Glossary

> High-frequency terminology for X-SuperPlay-ContentOps. One canonical definition per term.

[English](GLOSSARY.md) | [简体中文](GLOSSARY.zh-CN.md)

| Term | Definition |
|---|---|
| ContentOps | X-SuperPlay executable ContentOps runtime — converts real business artifacts into traceable video workflows |
| Easel Runtime | UPSTREAM RUNTIME / SKILL ENGINE — the pinned Easel release that provides TTS, video assembly, and provider capabilities |
| Upstream | The Easel repository (ZJU-REAL/Easel) that ContentOps tracks and adapts from |
| Pinned Release | A specific stable Easel version locked in `runtime/easel.lock.json` — the production runtime |
| Capability Spike | A verification phase that tests whether a subscription or plan can actually perform an operation before implementation |
| Receipt | Machine-generated evidence file proving a specific action was taken (e.g., render, QC, test) |
| Golden Sample | A reference project with known-good output used for regression testing |
| Human Review | The final gate before publication — a human must approve the output |
| Production Ready | Status indicating output has passed all automated gates and is awaiting human review |
| Subscription Key | MiniMax credential tied to a subscription plan (not PAYG) |
| PAYG | Pay-As-You-Go API billing — explicitly disabled in ContentOps (`allow_payg: false`) |
| SourceArtifact | A structured input from a real business source (repo, experiment, research) |
| ContentRun | A single execution of the video production pipeline for a project |
| Adapter | A pattern that wraps upstream Easel behavior without modifying upstream code |
| dev_check | The unified developer gate: `python scripts/dev_check.py` — runs repo policy, subprocess policy, skill references, docs, i18n, tests, whitespace |
| Branch layer | A body of work that exists on one branch only. Named in the docs so a feature on a draft branch is never described as available |
| Integration branch | The branch that carries the merged stack. While `main` is behind it, `main` is not the truth about what runs |
| Content-router slice | One reviewable slice (S1–S4) of the account-aware content router, merged separately with its own tests |
| Skill reference integrity | The rule that an installed skill may only name code this branch has. Enforced by `scripts/check_skill_references.py` against `runtime/content-skill-status.json` |
| RECORD_STALE | The check's failure code for a recorded skill reference that now exists: the layer landed and the record was not updated |
| Declared capability | An entry in `runtime/skill-registry.json` pointing at code on the integration branch. A declaration never grants execution |
| Content-skill status record | `runtime/content-skill-status.json` — the list of paths the installed content skills name that this branch does not have |