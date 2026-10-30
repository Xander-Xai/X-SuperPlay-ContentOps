import { renderMermaid, THEMES } from 'beautiful-mermaid';
import { writeFileSync, mkdirSync } from 'fs';

const diagram = `graph LR
    A["ChatGPT<br/>全能写作助手"] --- D["写作/翻译"]
    B["Notion AI<br/>知识管理"] --- E["会议/周报"]
    C["Microsoft Copilot<br/>Office 自动化"] --- F["文档/数据"]
    G["Canva AI<br/>设计小白"] --- H["海报/配图"]
    I["Otter.ai<br/>会议记录"] --- J["转录/摘要"]
    style A fill:#10a37f,stroke:#333,color:#fff
    style B fill:#000,stroke:#333,color:#fff
    style C fill:#0078d4,stroke:#333,color:#fff
    style G fill:#00c4cc,stroke:#333,color:#fff
    style I fill:#7c3aed,stroke:#333,color:#fff
    style D fill:#e8f5e9,stroke:#333,color:#333
    style E fill:#e8f5e9,stroke:#333,color:#333
    style F fill:#e8f5e9,stroke:#333,color:#333
    style H fill:#e8f5e9,stroke:#333,color:#333
    style J fill:#e8f5e9,stroke:#333,color:#333`;

const svg = await renderMermaid(diagram, THEMES['github-light']);
const outPath = 'D:/Projects/codex/skills/wechat-article-skills/test_article/imgs/tool-comparison.svg';
mkdirSync('D:/Projects/codex/skills/wechat-article-skills/test_article/imgs', { recursive: true });
writeFileSync(outPath, svg, 'utf-8');
console.log('OK: ' + outPath + ' (' + svg.length + ' bytes)');
