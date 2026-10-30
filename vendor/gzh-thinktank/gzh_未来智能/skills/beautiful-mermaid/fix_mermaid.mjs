import { renderMermaid, THEMES } from 'beautiful-mermaid';
import { writeFileSync } from 'fs';

const diagram = `graph LR
    A[ChatGPT - 全能助手] --> A1[写作/翻译/分析]
    B[Notion AI - 知识管理] --> B1[会议/周报/笔记]
    C[Copilot - Office 自动化] --> C1[文档/数据/PPT]
    D[Canva AI - 设计外挂] --> D1[海报/配图/排版]
    E[Otter.ai - 会议记录] --> E1[转录/摘要/待办]
    style A fill:#10a37f,stroke:#333,color:#fff
    style B fill:#2d2d2d,stroke:#333,color:#fff
    style C fill:#0078d4,stroke:#333,color:#fff
    style D fill:#00c4cc,stroke:#333,color:#fff
    style E fill:#7c3aed,stroke:#333,color:#fff
    style A1 fill:#e8f5e9,stroke:#ccc,color:#333
    style B1 fill:#f5f5f5,stroke:#ccc,color:#333
    style C1 fill:#e3f2fd,stroke:#ccc,color:#333
    style D1 fill:#e0f7fa,stroke:#ccc,color:#333
    style E1 fill:#f3e5f5,stroke:#ccc,color:#333`;

const svg = await renderMermaid(diagram, THEMES['github-light']);
const outPath = 'D:/Projects/codex/skills/wechat-article-skills/test_article/imgs/tool-comparison.svg';
writeFileSync(outPath, svg, 'utf-8');
console.log('OK: ' + outPath + ' (' + svg.length + ' bytes)');
