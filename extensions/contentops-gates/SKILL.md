---
name: contentops-production-gates
description: >
  X-SuperPlay ContentOps 的生产门控技能声明：把 7 个 VIDEO 门控与 5 个
  GRAPHIC_TEXT 门控以技能形态暴露给底座发现。本声明是「指路牌」，不是执行授权；
  门控的判定权永远在 scripts/production_gates.py 与人工复核。
version: 1.0.0
owner: contentops
language: zh-CN
upstream: none
---

# contentops-production-gates

## 这是什么

把本仓库自有的生产门控声明为一个可被发现的技能，使底座（Easel workbench / skill
路由）能够**指向**它们。声明 ≠ 授权：本文件不授权任何执行，只描述能力边界与契约。

## 门控清单

VIDEO 线（7 个，全部失败即拒绝）：

| 门控 | 判定内容 |
|---|---|
| `account` | 项目绑定的账号与 DNA 一致 |
| `copy_review` | 文案复核通过 |
| `evidence_links` | 证据引用可解析且未被篡改 |
| `asset_sufficiency` | 素材充分性（视频线） |
| `avatar_bookends` | 片头片尾形象一致 |
| `style_audio` | 风格与音频符合账号 DNA |
| `runtime_readiness` | 运行时就绪（引擎可解析、依赖在场） |

GRAPHIC_TEXT 线（5 个）：`account`、`copy_review`、`evidence_links`、`asset_rights`、
`runtime_readiness`。

## 契约

- 入口：`scripts/make_content.py`（唯一稳定生产入口），实现于
  `scripts/production_gates.py`。
- 输入：`project.yaml`、`sources/source-refs.json`、`sources/assets.json` 与
  账号 DNA。
- 输出：`receipts/production-gates*.json`，`production_ready` 恒由人工复核决定，
  自动门控 PASS ≠ production ready。
- 边界：不发布、不付费、不联网、不跨项目；底座无论渲染出什么，门控不过即不得
  进入交付。

## 与底座的关系

底座（Easel v0.3.0 workbench）可以**读取**门控结论（经治理扩展的只读 API），
但不能修改门控判定，也不能绕过门控直接进入交付。任何「门控通过」的断言必须
能由一份回执文件证明。
