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
