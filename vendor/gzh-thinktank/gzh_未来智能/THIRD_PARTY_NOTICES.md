# Third-party notices

本项目包含或引用多个独立的 Agent Skill、脚本、字体和开源项目。它们的
许可证不因本仓库的编排、重命名或文档整理而改变。

## 当前仓库内的主要来源

| 组件 | 本地路径 | 许可证/处理方式 |
|---|---|---|
| 公众号图文子技能 | `skills/gzh-*` + `skills/wechat-seo-optimizer` | 核心目录使用本项目的 source-neutral 命名；旧触发名仅作为 `skills/skill-registry.yaml` 兼容别名，许可证与来源声明保持不变 |
| Z5-WeChat-SOP 包装入口 | `skills/z5-wechat-sop` | MIT；仅作为可选外部适配器，不内置其源码 |
| wemp-operator 包装入口 | `skills/wemp-operator` | MIT；仅作为可选外部适配器，不内置其源码 |
| AiToEarn 包装入口 | `skills/aitoearn` | MIT；仅作为可选外部适配器，不内置其源码 |
| beautiful-mermaid | `skills/beautiful-mermaid` | 以该目录内的 LICENSE 为准 |
| KaTeX | `skills/formula-rendering`（npm 依赖） | MIT；仅用于把 canonical LaTeX 渲染为本地 PNG，不在公众号 HTML 注入运行时 |
| gzh-design-skill | `skills/gzh-design-skill` | 以该目录内的 LICENSE 为准 |
| Agnes Image 2.1 Flash 个人 skill 适配 | `skills/agnes-image-21-flash` + `skills/gzh-visual-assets/scripts/image_create.py` | 仅复用公开 API 契约；API Key 只从仓库外环境读取，生成图必须标记 illustrative；本项目保留安全下载与本地 Data URI 适配 |
| 本地内容策略/生产/人性化模块 | `skills/content-*` | 本仓库重写的流程规范，不复制外部实现 |
| GitHub 图形项目参考 | `integrations/diagram-mermaid.md` + `integrations/diagram_mermaid.py` | 仅参考 mcp-mermaid 契约；本地实现适配器，不内置上游代码 |
| 字体与 Office/PDF 工具 | 历史版本曾包含 | 已从核心发行包移除；如需恢复，应单独核对其许可证 |

## 本次核心发行包瘦身

未参与双账号公众号链路的通用文档、演示、学术和大体积字体 skill 已从当前工作树移除，
包括 `docx`、`pptx`、`pdf`、`canvas-design`、`figure-generation`、`visualization-expert`、
`ecom-details-image`、`brand-kit`、`notebooklm-skill`、`parallel-deep-research` 和 OPC 定位类 skill。
这些文件仍可从 Git 历史恢复，公众号核心流程不依赖它们。

## 发行规则

1. 不删除第三方代码要求保留的版权、许可证或 NOTICE 文本。
2. 新增外部项目时先记录来源 URL、版本/commit、许可证和是否允许商业再分发。
3. 仅复制方法论时重新编写本项目的流程和实现，不复制上游的整段实现或品牌文案。
4. 商业部署前对 Source Available、AGPL、Proprietary 组件单独复核。

## 外部调研来源（未内置代码）

| 项目 | 用途 | 处理 |
|---|---|---|
| [doocs/md](https://github.com/doocs/md) | 微信 Markdown 排版产品对标 | 仅参考交互与主题能力 |
| [hustcc/mcp-mermaid](https://github.com/hustcc/mcp-mermaid) | 图形类型和导出接口参考 | 本地适配器已启用，未复制代码 |
| [langchain-ai/social-media-agent](https://github.com/langchain-ai/social-media-agent) | 人工审核和可恢复流程参考 | 重新实现门禁，不复制代码 |
| [microsoft/lida](https://github.com/microsoft/lida) | 数据可视化候选 | 默认不启用，需沙箱 |
| [llmsresearch/paperbanana](https://github.com/llmsresearch/paperbanana) | 高级技术图候选 | 第二阶段评估 |
| [trypostit/trypost](https://github.com/trypostit/trypost) | 运营日历参考 | AGPL，不进入核心仓库 |
| 外部双账号视觉工作流（原始工作区） | `docs/visual-generation-runbook.md` | 仅吸收导演计划、证据优先、连续性、fallback 与渲染复核方法，未复制视频生产源码 |
