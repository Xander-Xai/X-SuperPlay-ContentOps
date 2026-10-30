# GitHub/Skill Relevance Audit — AI Work Efficiency and Monetization (2026-10-25)

**Audit is stricter than GitHub stars, official authorship, or an existing Skill title.** The previous [12-skill list](100-SKILLS-SERIES.md) mixed immediately useful automation/validation Skills with broad design and deployment helpers. All 12 can have a legitimate use, but several lacked a **specific value case** and should **not** be automatically selected for X production.

## Mandatory GitHub content gate

A GitHub project / Skill is **eligible** only if the research card records all six items:

1. **Buyer/user/job:** concrete role and repeated task (e.g. finance ops matching invoices; developer confirming AI code fix), not just "everyone using AI".
2. **Mechanism:** actual AI-assisted or AI-enabling workflow from **named SKILL.md/README/Release/code**: inputs→process→outputs; do not assume the project performed an experiment.
3. **Productivity/business value:** time, error, rework, software cost, lead/revenue path **with a testable measure**. A plausible mechanism is **not** verified gain.
4. **Costs and boundaries:** setup, inference/API, hosting, human review, security, licence and ongoing maintenance. If a source lacks pricing, explicitly say so.
5. **Evidence:** primary GitHub source, commit/release when claiming 72h novelty, independent test/benchmark when quoting a number. **Repo last-updated date ≠ important technical release.**
6. **Original editorial thesis:** specific bottleneck, tradeoff and decision/action; commercial buyer + deliverable + proposed willingness-to-pay test if claiming a monetization angle.

**Fail any element → HOLD**, not automatic posting. Missing measured gain does not ban a technically valuable Skill, but the proposed test and uncertainty must be explicit. **No "10x faster" or "this SaaS makes money" without primary evidence.**

## Reassessment of 12 prior Skill candidates

| ID | Status | Use case and why |
|---|---|---|
| S001 Anthropic mcp-builder | **eligible_for_research** | Developer integrator: task-based evaluation and error handling for usable MCP tools; verify 10 real tasks / costs; no benchmark asserted |
| S002 Anthropic skill-creator | **hold_until_case** | Repeated prompt-to-Skill conversion has plausible time value; need one concrete weekly task and maintenance/evaluation evidence before posting |
| S003 Anthropic webapp-testing | **eligible_for_research** | Product QA: automated real UI regression, measure missed failures/review time vs manual testing, Playwright environment costs |
| S004 Anthropic frontend-design | **hold_until_case** | Design quality claim ≠ productivity. Need actual design iteration/rework case and human evaluation |
| S005 Anthropic xlsx | **eligible_for_research** | Finance/ops spreadsheet processing: compare formulas/errors/time on a safe sample; licence/data privacy/cross-model limits |
| S006 Anthropic docx | **hold_until_case** | Generic document generation alone is not a business insight; require specific repetitive template workflow, review error count and who pays |
| S007 Vercel react-best-practices | **hold_until_case** | Frontend performance is relevant but no measured AI-specific impact; need repository commit, profiling comparison and deployment constraints |
| S008 Vercel web-design-guidelines | **hold_until_case** | Checklist without tested reduction in UX fixes or conversion relevance is broad design commentary |
| S009 Vercel deploy-to-vercel | **hold_until_case** | Deployment helper may lower shipping friction; require realistic end-to-end MVP deliverable, hosting/cost, actual customer test |
| S010 Superpowers systematic-debugging | **eligible_for_research** | AI coding failure triage, show reproducible root cause and command before/after; no saved-hours estimate invented |
| S011 Superpowers test-driven-development | **hold_until_case** | Sound dev practice but not automatically new AI productivity. Need specific agent test/commit and rework outcome |
| S012 Superpowers verification-before-completion | **eligible_for_research** | Evidence-bound AI fix verification; already drafted as X #001, **avoid repetitive post** unless new primary evidence or original angle |

**Total: 5 eligible for research, 7 held pending a concrete productivity/commercial case.** `eligible_for_research` does **not** mean hands-on verified or necessarily publishable. All 12 remain source references; none is a verified income stream. This editorial classification is a new review, not a claim the previous sources were technically invalid.

## Stronger AI productivity/business candidate GitHub repos (new discovery, NOT verified as money-makers)

| GitHub repository | Specific work scenario | Test to pass before publishing | Status |
|---|---|---|---|
| [activepieces/activepieces](https://github.com/activepieces/activepieces) | Operations teams: capture forms/invoices, route exceptions for human approval, notify assignee. README supports automations and human-in-loop; commercial value requires test | Count processed cases, exceptions, manual minutes, API/hosting costs, operational owner | `research_candidate` |
| [docling-project/docling](https://github.com/docling-project/docling) | Reconcile unstructured PDF invoices/contracts into structured review inputs; README documents multi-format parsing | Check extraction accuracy with a consented sample, costs, PII/data safeguards and actual finance steps | `research_candidate` |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | Permitted browser-based repetitive business tasks where API is unavailable | Test reliability, manual approval, target-site terms, security and maintenance. **Do not use this to bypass X automation restrictions.** | `conditional_candidate` |

**X + GitHub bridge:** a popular X discussion about "software is dead" is demand/sentiment evidence only; it does not validate the app replacements' operating cost or business margins. The October 2026 [NBER survey](https://www.nber.org/papers/w34836) supplies more grounded evidence about firm-wide value realization, but it is not a customer interview about automation services.

## Enforcement and changes

- The [daily prompt](../prompts/DAILY-POST.md) must run both **X signal** and **GitHub value gate** before drafting.
- The [GitHub URL prompt](../prompts/GITHUB-URL-TO-X.md) cannot promote items held without a scoped work case and proof plan.
- Skills older than 72h remain clearly `evergreen`.
- Never mark a Skill `tested` merely because its README or SKILL.md was read. Link actual runs and traceability first.
- Continue maintaining project selection separately from publication state `draft/scheduled/published`.
