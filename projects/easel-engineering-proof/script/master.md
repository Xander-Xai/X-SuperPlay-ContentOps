# Engineering evidence cut — master

**Audience question:** 到底验证了什么，什么还没验证？
**Format:** 1920×1080, 52 s
**Status:** EVIDENCE-DRAFT — waiting for assembly and human playback

## Evidence inventory

| Asset | Source | Class | What it shows |
|---|---|---|---|
| `A-REV` | `CAP-20261027-REV-H` | EXECUTED | revision `4efd5930` |
| `A-DOCTOR` | `CAP-20261027-DOCTOR-H` | EXECUTED | seven core checks, exit 0 |
| `A-SKILL` | `CAP-20261027-SKILLROUTE-H` | EXECUTED | caption route |
| `A-SUB` | `CAP-20261027-SUBTITLE-H` | EXECUTED | centisecond, overflow and truncation regressions |
| `A-MATRIX` | `docs/CURRENT-STATE.md` | DOCUMENTED | verified/unverified matrix, Web NOT VERIFIED |
| `A-LOCK` | `runtime/easel.lock.json` | DOCUMENTED | v0.2.1 / `3fe2d99` |

The two matrix cards quote tracked files and carry their SHA in the Claim Map.
No generated image or video appears.

## Narration

| Time | Claim | Line |
|---|---|---|
| 0–4 | E-OPEN | 已验证的是命令行；没验证的是 Web。 |
| 4–7 | E-REV | 验证修订：4efd5930。 |
| 7–10 | E-PIN | 运行时固定在 v0.2.1，提交 3fe2d99。 |
| 10–17 | E-DOCTOR | doctor 七项，全部返回 OK。 |
| 17–24 | E-SKILL | 字幕这一步，路由到 auto-subtitle 和 auto-short-video。 |
| 24–32 | E-SUB | 字幕回归覆盖厘秒时间戳、截断阻断和超长 cue。 |
| 32–40 | E-TRANS-PROOF | 已经看到的每一项，都能回溯到回执。 |
| 40–47 | E-TRANS-SCOPE | 这就是我们说的“验证过”。 |
| 47–50 | E-MATRIX | 已验证：依赖、运行时、技能路由、字幕回归。未验证：Web。 |
| 50–52 | E-CTA | 要复核，就从这些回执开始。 |

## Deliberate omissions

- the 1024 conflict hook and its platform framing;
- generalized product promises;
- any date for Web repair.

## Duration deviation

The design proposed 78–90 s. Approved evidence currently totals 23 s of real
terminal footage, and repeating it to reach 90 s would be the static padding
this rebuild exists to remove. The engineering cut is therefore 52 s, and the
deviation is recorded in the package receipt for Founder review.

## Packaging

- Bilibili cover title (1600×900): `验证到哪一步`
- Platform title: `Easel 验证边界：CLI 通过，Web 未验证`
- CTA: `要复核，就从这些回执开始。`
