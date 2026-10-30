# X daily post trial — 2026-10-25 — verification-before-completion

**Workflow:** X-SuperPlay-X-Growth-OS / V0
**Content ID:** `20261025-001`
**Publication state:** `draft` — **not posted to X**; no X post URL or confirmed schedule.
**Category:** `SKILL_EVERGREEN` (not a breaking event from the past 72h).
**Research source:** https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md
**Evidence inspected:** the upstream SKILL.md explicitly requires proof of completed work from a fresh verification command and actual output, including checking exit status, and verifying the original symptom when claiming a fix.
**Review date:** 2026-10-25. The Skill is used as evergreen advice, not claimed as a newly released feature.
**Reader:** AI coding agent users and developers.
**Angle:** An AI-generated "fixed" claim is not proof. Show the evidence checklist.
**Competing angle (not selected):** Sell an AI QA report service. Deferred because no validated paying customer or pricing evidence.
**Format:** 1 post + 1 image (16:9 English infographic).
**Actual code-point count:** 255 (including the full URL). Verify in the X Composer before publishing due to weighted URL and Unicode rules.

## English post — copy exactly

```text
AI coding agent: "Fixed."
Proof?

Before merging, check:
1) exact test command
2) fresh output + exit code
3) original failure now passes

No run = unverified fix.

Skill: https://github.com/obra/superpowers/tree/main/skills/verification-before-completion
```

## 中文翻译

AI 编程助手说“修好了”。证据呢？

合并代码前确认：
1. 具体执行了哪条测试命令
2. 本次运行的最新输出与退出状态
3. 最初的故障现在是否通过验证

没有实际运行，就不能声称修复已经验证。

Skill 来源见英文原帖 GitHub 链接。

## Image

- Vector source committed to this repository: [verification-card.svg](../assets/2026-10-25-verification-card.svg) (16:9 conceptual explanatory card).
- A matching 1600×900 PNG was prepared in the authoring session for direct upload; **PNG is not embedded in this repo in this trial**. If you plan to publish later, export/render the SVG as PNG or save the delivered PNG from the conversation.
- ALT text: A dark blue infographic titled 'FIXED IS NOT PROOF'. Three steps: Test Command, Fresh Output, Exit Status. Footer: No fresh run means unverified.
- No numbers/benchmarks are asserted in this diagram.

## Two-minute actual publish test — pending

1. Open https://x.com/compose/post (sign in on your own device); paste the English text above.
2. Check the **official weighted character counter**, then attach the prepared PNG and set ALT text.
3. Visually verify and click Post once. Do not claim posted based on a draft or an unsent composer.
4. Record the actual `https://x.com/.../status/...` link, then change the post state to `published` and append the real URL to `templates/posts.csv`.

## Trial observations

| Checkpoint | Result |
|---|---|
| GitHub V0 prompt read | verified |
| Upstream SKILL.md retrieved | verified |
| Credible evergreen technical claim | verified against source |
| Single post, fewer than 280 raw characters | verified (255 code points) |
| Correct English 16:9 illustration | generated / visually inspected; SVG source committed |
| Logged in and authorized X publishing tool | **not available in this chat** |
| Actual X post URL | **none** |
| X live publishing | **not completed** |
| Live impression/follower impact | **not measurable yet** |

**Safety/limitations:** No third-party publishing OAuth integration is configured. Browser UI scripting is not used as a workaround because X's automation rules restrict non-API website scripting. See https://help.x.com/en/rules-and-policies/x-automation . Do not treat a GitHub commit as a successful X publication.
