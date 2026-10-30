import { renderMermaid, THEMES } from 'beautiful-mermaid';
import { writeFileSync, mkdirSync } from 'fs';

const diagram = `graph TD
    A[选题] --> B[写稿]
    B --> C[审稿]
    C --> D[排版]
    D --> E[配图]
    E --> F[发布]`;

const theme = 'tokyo-night';
const svg = await renderMermaid(diagram, THEMES[theme]);
mkdirSync('D:/Projects/codex/skills/wechat-article-skills/test_article/imgs', { recursive: true });
const filename = 'D:/Projects/codex/skills/wechat-article-skills/test_article/imgs/test-mermaid.svg';
writeFileSync(filename, svg, 'utf-8');
console.log('OK: ' + filename + ' (' + svg.length + ' bytes)');
