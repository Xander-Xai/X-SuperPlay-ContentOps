# 质检全过，为什么还是被毙了

> 一条 62 秒、21 项自动检查全绿的成片，被创始人当场否掉。
> 这不是工具坏了，是"自动 QC 能测什么"和"人要不要发"之间有一道缝。

## 账本一：那次到底发生了什么

- **自动 QC**：21 项检查，0 FAIL，0 WARN，整体 PASS
- **人审结论**：`REJECTED_FOUNDER`
- **成片**：62.0 秒，1080×1920，6 个镜头
- **镜头运动**：6/6 全部 `static`
- **近静止时长**：60.1 / 62.0 秒，约 96.9%，分 12 段冻结

来源：`projects/easel-review/receipts/human-review.json`、
`reports/audits/video-quality-failure-audit-2026-11-01.md`

## 账本二：自动 QC 能测什么、测不了什么

能测：

- 容器、分辨率、时长、编码、音轨
- 字幕是否烧录、音量是否静音
- 真实素材秒数占比是否 ≥ 70%

测不了：

- 声音像不像人、音质能不能接受
- 画面像不像"成熟作品"——这是审美判断
- 这条结论值不值得发

来源：`docs/QUALITY-STANDARD.md`、`src/contentops/media/video_contract.py`

## 收尾：把"测不了的"变成人审清单

1. **先看片，再看回执。** 分数由人填，缺省是 `null`，不是自动生成。
2. **只问三个问题。** 手机上读得清吗、画面有变化吗、我愿意发吗。
3. **技术 PASS ≠ 可发布。** `production_ready` 在有人签字前恒为 `false`。

## 说明

- 本图文由 ContentOps 用 Easel `card-design` / `card-xiaohongshu` 的确定性规则本地渲染，
  文字全部走 HTML/CSS 排版，未使用任何 AI 生图。
- 卡片是说明性视觉，**不是事实证据**；文中的数字来自上面列出的回执与审计报告。
- 状态：人工审核前，`production_ready: false`、`publish_authorized: false`。

## Images

- `card_01_cover` — 1080x1440 png
  ![封面卡：大字标题『质检全过，为什么还是被毙了』，下方标注 96.9% 的近静止占比，以及并排的六个镜头方块 S1 到 S6。](assets/cards/card_1.png)
- `card_02_facts` — 1080x1440 png
  ![事实卡：六行账本，逐条列出自动 QC 全过、人审结论被拒、成片 62 秒、六个镜头全为 static、近静止 96.9%、冻结 12 段。](assets/cards/card_2.png)
- `card_03_boundary` — 1080x1440 png
  ![拆解卡：左侧列出自动 QC 能测的三项（容器规格、字幕音量、真实素材占比），右侧三条蓝色强调的是测不了的三项（声音是否像人、画面是否像成品、值不值得发）。](assets/cards/card_3.png)
- `card_04_checklist` — 1080x1440 png
  ![收尾卡：四条人审清单（先看片再看回执、只问三个问题、技术通过不等于可发布、发布授权要人签），底部一行行动号召。](assets/cards/card_4.png)

## Review state

- status: `AWAITING_MANUAL_REVIEW`
- publish authorized: **no**
- blockers: HOST_CAPABILITY_UNVERIFIED, PLATFORM_PLACEHOLDER
