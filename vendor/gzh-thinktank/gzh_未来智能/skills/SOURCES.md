# Skill 来源与本地改造记录

本目录是当前独立公众号工作流的本地发行包。公开触发名和目录名已经统一为本地语义；兼容旧 slug 只在 `skill-registry.yaml` 中保留，不作为内部路径依赖。

## 处理规则

1. 外部 skill 的许可证、版权和 NOTICE 不删除；
2. 只保留对本项目有用的流程、规则和适配接口；
3. 上游的品牌文案、安装指引和运行时命名不进入本地工作流；
4. 原项目的外部 API 不会被默认调用，凭证不会写入 profile；
5. 需要升级时，先记录来源版本，再在本地工作流中运行回归测试。

## 当前发行层

| 本地能力 | 用途 | 处理方式 |
|---|---|---|
| `ai-sentinel-workflow` | AI哨兵账号编排 | 本地账号规则与 9 门禁 |
| `ai-thinktank-workflow` | X超玩•未来智能账号编排 | 本地账号规则与 9 门禁 |
| `gzh-*` + `wechat-seo-optimizer` | 选题、写作、审稿、排版、配图、草稿 | 核心目录使用 source-neutral 命名；旧 slug 只在注册表作为兼容别名 |
| `content-*` | 内容简报、生产、人性化审校 | 本地重写的支撑规范 |
| `visual_qa.py` + `visual_semantic_qa.py` | 视觉简报、章节语义合同、图片质量 | 本地确定性检查器；技术图缺少正文映射时阻断 |
| `formula-rendering` + `formula_pipeline.py` | LaTeX 源、KaTeX/Chrome PNG、微信 HTML 公式审计 | 本地编排层；KaTeX 版本锁定，许可证见 `THIRD_PARTY_NOTICES.md` |

具体第三方来源、许可证和未内置的 GitHub 参考项目见仓库根目录的
`THIRD_PARTY_NOTICES.md` 与 `integrations/`。
