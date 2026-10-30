# Mermaid 图形适配器说明

## 目的

为 X超玩•未来智能提供确定性的流程图、架构图和对比图出口。默认调用本仓库的
`integrations/diagram_mermaid.py`，由本地 `beautiful-mermaid` 运行时输出 SVG；
`excalidraw-diagram` 仍可作为手绘风格备选，外部 MCP 不进入默认发布链。

## 参考项目

- 项目：[hustcc/mcp-mermaid](https://github.com/hustcc/mcp-mermaid)
- 参考能力：Timeline、Comparison、List、Process 等图形类型，导出 Mermaid/SVG/PNG；
- 许可证：以外部仓库当前 LICENSE 为准，接入前重新核对版本；
- 接入状态：enabled-local；仅实现本项目自己的适配器，不复制上游代码。

## 本项目接口约束

1. 输入必须来自 `visual-brief.yaml` 中的图形类型；
2. 输出至少包含 PNG 或可转换为 PNG 的 SVG；
3. 文章中所有关键结论必须在静态 HTML 中可见，不能只存在于交互动画；
4. 生成后运行 `visual_qa.py check` 和公众号 HTML 严格校验；
5. 失败时回退到本地确定性图形，不得伪造“已生成”。

## 调用

```powershell
python integrations/diagram_mermaid.py `
  --input <外部active/THK-...>/imgs/prompts/workflow.mmd `
  --output <外部active/THK-...>/imgs/workflow.svg `
  --theme github-light
```

适配器只在本机依赖可用时运行，使用 `npx --no-install`，不会联网安装依赖。
输出为可审计的 SVG；若需要 PNG，再由本地截图/转换步骤处理，不能把未生成的
文件标记为完成。
