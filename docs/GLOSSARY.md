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
| dev_check | The unified developer gate: `python scripts/dev_check.py` — runs repo policy, docs, i18n, tests, whitespace |