# 解除阻断步骤

当前没有生成有效运行回执。本文件不是一次运行产生的审核回执，而是阻断状态说明；不要签署或沿用其中的 `NOT_RUN`。

要完成 PR-2 示例，请按序：

1. 通过仓库精确路径媒体例外审批，提供有明确权利来源且可纳入版本控制的封面素材；同步为 `tests/test_gitignore_evidence_policy.py` 新增窄范围断言，不允许放宽全局 `*.png` 规则。
2. 在有权限的环境中显式设置 `CONTENTOPS_PYTHON`，运行 `python scripts/render_article.py projects/gzh-qc-gap`。不得自动扫描解释器或安装依赖。
3. 确认 `validate_gzh_html.py` 无 ERROR、无 WARNING，且预览生成并带有校验后的图片。
4. 浏览器打开完整预览，在手机宽度目检标题、摘要、各级正文、图片/图注/来源和整篇节奏；人工结论单独记录。
5. 保持 `production_ready: false` 和 `publish_authorized: false`，除非另有人的明确批准；这条 CLI 不提供平台发布或模拟已发布功能。

复核 `article-input.json` 中的来源引用及 PNG 许可证例外后，再将此状态说明替换为实际生成的 `gzh-article.json` 回执。
