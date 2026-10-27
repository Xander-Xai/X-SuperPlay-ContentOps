# 1024 conflict cut — master

**Audience question:** Easel 能不能开箱即用？
**Format:** 1080×1920, 44 s
**Status:** EVIDENCE-DRAFT — assembled, awaiting human playback

## Evidence inventory

| Asset | Source | Class | What it shows |
|---|---|---|---|
| `A-REV` | `CAP-20261027-REV-H` | EXECUTED | the revision this run measured |
| `A-DOCTOR` | `CAP-20261027-DOCTOR-H` | EXECUTED | `doctor --json` returns 0 |
| `A-SUB` | `CAP-20261027-SUBTITLE-H` | EXECUTED | caption timing and overflow regressions pass |
| `A-SKILL` | `CAP-20261028-SKILLROUTE-AUTO` | EXECUTED | `skill_route --match auto-subtitle` returns `auto-subtitle` first |
| `A-DOC-WEB` | `docs/CURRENT-STATE.md` | DOCUMENTED | Web workbench NOT VERIFIED |
| `A-DOC-CTA` | claim `C-1024-CTA` | — | the closing invitation |

No generated visual appears in this cut. The two cards are citations and an
invitation, not screenshots; the Web card quotes the tracked document and
carries its SHA in the Claim Map.

Two recording notes:

- the skill-route beat uses `CAP-20261028-SKILLROUTE-AUTO`; the 2026-10-27
  capture asked `final cut subtitles burn` and did not return `auto-subtitle`,
  so it could not support the line.
- `doctor --json` reports seven checks, but the capture window scrolls the
  `python` and `node` entries above the frame. The visible crop shows five
  entries and the exit code; the count comes from the command's own output.

## Narration

| Time | Claim | Line |
|---|---|---|
| 0–2 | C-1024-OPEN | Web 工作台仍未验证。 |
| 2–8 | C-1024-REV | 这次验证的修订是 4efd5930。 |
| 8–16 | C-1024-DOCTOR | doctor 的七项核心检查，返回 0。 |
| 16–22 | C-1024-CAPTIONS | 字幕计时的回归，全部通过。 |
| 22–28 | C-1024-SKILL | 字幕工作由 auto-subtitle 接管。 |
| 28–34 | C-1024-WEB | 项目文档记录：Web 工作台 6 项失败。 |
| 34–40 | C-1024-BOUNDARY | 边界：工具链可用，Web 还不能算交付。 |
| 40–44 | C-1024-CTA | 先看证据，再决定接不接。 |

## Views

A placement runs for as long as its narration. Its *views* do not: every view is
2.0 s, so no static frame is held past the V2 `max_visual_hold_ms`. Each result
appears once in context, then the crop is enlarged onto the line the narration
names. The enlargement is validated as contained by its context crop.

## Deliberate omissions

- full skill taxonomy;
- hash mechanics beyond the revision line;
- any claim that the Web workbench will be fixed by a date.

## Why the opening is a citation

There is no approved browser capture, so the Web boundary is shown as a quoted
line from the tracked document. Rendering that quote as a designed screenshot
would imply a UI state nobody filmed. The card cites the file; the file is the
evidence.

## Packaging

- Xiaohongshu cover title (1080×1440): `Web 仍未验证`
- Platform title: `Easel 实测：工具链通了，Web 还没`
- CTA: `先看证据，再决定接不接。`
