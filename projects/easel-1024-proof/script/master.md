# 1024 conflict cut — master

**Audience question:** Easel 能不能开箱即用？
**Format:** 1080×1920, 45 s
**Status:** EVIDENCE-DRAFT — waiting for assembly and human playback

## Evidence inventory

| Asset | Source | Class | What it shows |
|---|---|---|---|
| `A-REV` | `CAP-20261027-REV-H` | EXECUTED | the revision this run measured |
| `A-DOCTOR` | `CAP-20261027-DOCTOR-H` | EXECUTED | `doctor --json` returns 0 |
| `A-SUB` | `CAP-20261027-SUBTITLE-H` | EXECUTED | caption timing and overflow regressions pass |
| `A-SKILL` | `CAP-20261027-SKILLROUTE-H` | EXECUTED | `auto-subtitle` / `auto-short-video` own the caption step |
| `A-DOC-WEB` | `docs/CURRENT-STATE.md` | DOCUMENTED | Web workbench NOT VERIFIED, 6 doctor failures |

No generated visual appears in this cut. The two citation cards quote the
tracked document and carry its SHA in the Claim Map; they are citations, not
screenshots.

## Narration

| Time | Claim | Line |
|---|---|---|
| 0.0–3.0 | C-1024-OPEN | Easel 的 Web 工作台，仍未验证。 |
| 3.0–6.0 | C-1024-TRANS-1 | 先看它实际跑出来的东西。 |
| 6.0–11.0 | C-1024-REV | 这次验证的修订是 4efd5930。 |
| 11.0–18.0 | C-1024-DOCTOR | doctor 的七项核心检查，返回 0。 |
| 18.0–25.0 | C-1024-CAPTIONS | 字幕计时的回归，全部通过。 |
| 25.0–31.0 | C-1024-SKILL | 字幕工作由 auto-subtitle 接管。 |
| 31.0–38.0 | C-1024-WEB | 项目文档记录：Web 工作台 6 项失败。 |
| 38.0–42.0 | C-1024-BOUNDARY | 边界：工具链可用，Web 还不能算交付。 |
| 42.0–45.0 | C-1024-CTA | 先看证据，再决定接不接。 |

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
