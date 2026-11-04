# 小红书图文样例 —「质检全过，为什么还是被毙了」

一套 4 页、1080×1440 的小红书图文，用来证明「内容输入 → 卡片设计 → HTML/CSS 渲染 →
图片质量检查 → 图文审核包 → 本地预览」这条链在本机真实跑得通。

这不是新的图文引擎。渲染用 Easel 固定版本的 `render_card.py`，密度门禁用
`card_audit.py`，交付包用 ContentOps 的 `graphic_package.py`。

## 内容来源

卡片上的每个数字都来自本仓库已提交的回执与审计报告：

| 事实 | 来源 |
|---|---|
| 21 项自动 QC 全过、`REJECTED_FOUNDER`、62.0 秒、6/6 `static` | `projects/easel-review/receipts/human-review.json` |
| 近静止 60.1/62.0 秒（96.9%）、12 段冻结、最长一段 10.33 秒 | `reports/audits/video-quality-failure-audit-2026-11-01.md` |
| 真实素材秒数 ≥ 70% 的门禁、人审字段初始为 `null` | `docs/QUALITY-STANDARD.md`、`src/contentops/media/video_contract.py` |

卡片是**说明性视觉，不是证据**。它解释上面的回执，本身不能支撑任何事实主张。

## 怎么重跑

```bash
# 1. 渲染 + 密度门禁（写 receipts/card-render.json）
python scripts/render_cards.py projects/xhs-qc-gap

# 2. Bundle → GRAPHIC_TEXT handoff
python scripts/bundle_handoff.py projects/xhs-qc-gap/bundle.json \
  --account explorer --format GRAPHIC_TEXT --project-slug xhs-qc-gap \
  --source-map SRC-20261105-001=SRC-20261105-001 \
  --platform xiaohongshu_image --out-project projects/xhs-qc-gap

# 3. 交付包（停在 AWAITING_MANUAL_REVIEW）
python scripts/graphic_package.py --project projects/xhs-qc-gap \
  --handoff projects/xhs-qc-gap/receipts/bundle-handoff-graphic_text.json \
  --input projects/xhs-qc-gap/graphic-input.json
```

渲染需要 Playwright 与已安装的 Chromium。若默认解释器与浏览器构建不匹配，
用 `CONTENTOPS_CARD_PYTHON` 指向匹配的解释器，并设置 `PLAYWRIGHT_BROWSERS_PATH`。
安装浏览器是单独的、需要授权的动作。

## 产物与状态

| 产物 | 路径 | Git |
|---|---|---|
| 卡片 PNG（4 张） | `assets/cards/card_1..4.png` | 忽略（可确定性重建） |
| 渲染回执 | `receipts/card-render.json` | 提交 |
| Bundle handoff | `receipts/bundle-handoff-graphic_text.json` | 提交 |
| 交付包 | `receipts/graphic-package.json` | 提交 |
| 人工可读预览 | `receipts/graphic-preview.md` | 提交 |
| 运行时路径日志 | `receipts/workflow.json` | 提交 |

- `production_ready: false`、`publish_authorized: false`，状态 `AWAITING_MANUAL_REVIEW`。
- blocker 是真实的：`xiaohongshu_image` 在平台注册表里仍是 `PLANNED`，
  宿主能力是 `UNVERIFIED`。
- 权利记录写明「代理认定、待运营者会签」；会签前不得发布。

## 权利与许可

卡片由本仓自有 HTML 经本地脚本确定性渲染，无第三方素材、无 AI 生图，
许可类别为 `OWNED-GENERATED-LOCAL`。文字全部走 HTML/CSS 排版，
不存在「AI 生图画中文」的问题。
