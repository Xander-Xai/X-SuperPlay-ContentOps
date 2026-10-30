# beautiful-mermaid

Agent skill for rendering Mermaid diagrams as SVG or ASCII art.

## Installation

```bash
npx skills add AlexMikhalev/beautiful-mermaid
```

## Features

- Render Mermaid diagrams as SVG with theming support
- Render Mermaid diagrams as ASCII/Unicode for terminals and markdown
- 15 built-in themes (Tokyo Night, Dracula, GitHub, Nord, Catppuccin, etc.)
- Shiki VS Code theme integration
- Support for flowcharts, state diagrams, sequence diagrams, class diagrams, and ER diagrams

## Quick Start

```typescript
import { renderMermaid, renderMermaidAscii, THEMES } from 'beautiful-mermaid'

// SVG output with theme
const svg = await renderMermaid(`
  graph LR
    A[Start] --> B{Decision}
    B -->|Yes| C[Action]
    B -->|No| D[End]
`, THEMES['tokyo-night'])

// ASCII output for terminals
const ascii = renderMermaidAscii(`graph LR
    A --> B --> C`)
```

## Credits

This skill wraps the [beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) library by [lukilabs](https://github.com/lukilabs).

Original library documentation: https://agents.craft.do/mermaid

## License

MIT - See [LICENSE](LICENSE) for details.

The underlying `beautiful-mermaid` library is separately licensed by its authors.
