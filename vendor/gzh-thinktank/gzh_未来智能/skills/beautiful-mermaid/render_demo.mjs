import { renderMermaid } from 'beautiful-mermaid';
import { writeFileSync, mkdirSync } from 'fs';

const diagram = `graph TD
  X[输入 X]
  X --> Q["Q = X·W_Q"]
  X --> K["K = X·W_K"]
  X --> V["V = X·W_V"]
  Q --> S["Score = QK^T / sqrt(d_k)"]
  K --> S
  S --> A["Softmax 得权重 A"]
  A --> O["O = A·V"]
  V --> O
  O --> Y[输出表示]`;

const themes = {
  sentinel: {
    bg: '#F7EFE5', fg: '#252525', line: '#1B6F8A', accent: '#E05A2A',
    muted: '#5C6268', surface: '#FFFDF9', border: '#E05A2A',
  },
  thinktank: {
    bg: '#F4F0E8', fg: '#17324D', line: '#557A96', accent: '#B24A2B',
    muted: '#5E6872', surface: '#FFFCF7', border: '#B24A2B',
  },
};

const outDir = 'D:/Projects/test_workspace/gzh_image_optimization';
mkdirSync(outDir, { recursive: true });

for (const [name, t] of Object.entries(themes)) {
  const svg = await renderMermaid(diagram, t);
  const w = Number((svg.match(/width="([\d.]+)"/) || [0, 900])[1]);
  const h = Number((svg.match(/height="([\d.]+)"/) || [0, 600])[1]);
  writeFileSync(`${outDir}/AFTER_mermaid_${name}.svg`, svg, 'utf-8');
  const html = `<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:${t.bg};display:flex;align-items:center;justify-content:center;width:${w+40}px;height:${h+40}px">
${svg.replace('<svg ', `<svg style="max-width:100%" `)}
</body></html>`;
  writeFileSync(`${outDir}/AFTER_mermaid_${name}.html`, html, 'utf-8');
  console.log(`OK ${name}: ${w}x${h}`);
}
