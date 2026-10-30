---
name: wechat-svg-interactive
display_name: "微信纯 SVG/CSS 交互排版组件库"
display_name_en: "WeChat Interactive SVG & CSS Component Pack"
description: "为微信公众号文章提供免 JS 的 SVG/CSS 增强组件（折叠展开、多图滑动卡片、点击翻牌、答案揭晓），所有关键信息必须保留静态 HTML 降级。触发词：微信SVG排版、交互卡片、点击展开、滑动图组、SVG动画。"
category: formatting
version: 1.0.0
author: WeChat Matrix Team
visibility: "public"
---

# 微信纯 SVG/CSS 交互排版组件库 (wechat-svg-interactive)

微信公众号后台禁用了 `<script>` 脚本。SVG 动画在不同客户端、编辑器粘贴和深色模式下并不稳定，因此本 Skill 把交互定义为增强层：**答案、步骤和风险必须在静态 HTML 中直接可读**，不能把内容只放进 SVG 或只依赖 `<set>`、`hover`、`active`。

## 微信粘贴兼容合同（wechat-paste profile）

当 SVG 要直接粘贴到公众号编辑器，而不是只作为本地 HTML/PNG 的中间源时，额外启用
`wechat-paste` profile，并运行：

```powershell
python scripts/check_wechat_svg_compatibility.py --input <file.svg> --profile wechat-paste
```

该 profile 吸收了旧版 `wechat-svg` 的兼容性经验，但只约束“公众号粘贴交付物”，不约束
工作流内部用于语义 QA 的确定性 SVG 源。检查项包括：

- 禁止 `<script>`、事件处理器、`foreignObject`、外部 URL 和 `url(#...)` 依赖；
- 纯 SVG 交互组件不依赖 `id` / `class` / `defs` / `marker`，箭头应内联展开；确定性渲染器的
  几何合同可放在带 `id` 的 `<metadata>` 节点中，但该 `id` 不是渲染依赖，检查器只警告其可能被编辑器剥离；
- 写明像素 `width`、`height` 与 `viewBox`，不把尺寸交给外部 CSS 或 `width="100%"`；
- 文本必须在静态降级 HTML 中可读；SVG 动画只能增强，不承载唯一答案。

如果文章只交付 PNG/JPG 或工作流内部的 SVG/HTML 源，不要误用该严格 profile；仍应运行
`visual_artifact_qa.py`、`visual_semantic_qa.py` 和对应的几何/美学检查。这样可以同时保留
机器可读的语义元数据与微信粘贴端的保守兼容性，不把两种交付边界混为一谈。

---

## 🎨 示例组件：点击展开隐藏答案卡片

```html
<section style="margin: 15px 0; border: 1px solid #dbe4ee; border-radius: 8px; padding: 15px; background: #ffffff; font-family: sans-serif;">
  <section style="font-weight: bold; color: #2b6cb0; margin-bottom: 8px;"><span leaf="">❓ 思考题：AI Agent 与传统 Workflow 的区别？</span></section>
  <section style="margin: 10px 0; padding: 9px 12px; border-radius: 6px; background: #eaf3fb; text-align: center;"><span leaf="">点击查看参考答案（静态降级可直接阅读）</span></section>
  <section style="margin-top: 10px; font-size: 14px; color: #4a5568; line-height: 1.6;"><span leaf="">答案：Workflow 是预定义的固定路径，而 Agent 具备自主拆解目标、选择工具与自我修正的判断决策能力。</span></section>
</section>
```
