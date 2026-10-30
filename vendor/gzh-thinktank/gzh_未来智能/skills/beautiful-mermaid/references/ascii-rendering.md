# ASCII Rendering Guide

Complete reference for rendering Mermaid diagrams as ASCII/Unicode text.

## Overview

ASCII rendering produces plain text diagrams suitable for:
- Terminal output
- Markdown documentation
- Plain text files
- Environments without graphics support
- Accessibility contexts

---

## Basic Usage

```typescript
import { renderMermaidAscii } from 'beautiful-mermaid'

const ascii = renderMermaidAscii(`graph LR; A --> B --> C`)
```

Output (Unicode mode):
```
+-----+     +-----+     +-----+
|  A  |---->|  B  |---->|  C  |
+-----+     +-----+     +-----+
```

---

## Options

### `useAscii: boolean`

**Default**: `false` (Unicode mode)

Controls character set for box drawing:

```typescript
// Unicode mode (default) - cleaner appearance
const unicode = renderMermaidAscii(diagram, { useAscii: false })

// ASCII mode - maximum compatibility
const ascii = renderMermaidAscii(diagram, { useAscii: true })
```

Unicode output:
```
+---+     +---+
| A |---->| B |
+---+     +---+
```

ASCII output:
```
+---+     +---+
| A |---->| B |
+---+     +---+
```

### `paddingX: number`

**Default**: `5`

Horizontal spacing between nodes:

```typescript
// Compact
renderMermaidAscii(diagram, { paddingX: 2 })

// Spacious
renderMermaidAscii(diagram, { paddingX: 10 })
```

### `paddingY: number`

**Default**: `5`

Vertical spacing between nodes:

```typescript
// Compact vertical
renderMermaidAscii(diagram, { paddingY: 2 })

// Spacious vertical
renderMermaidAscii(diagram, { paddingY: 8 })
```

### `boxBorderPadding: number`

**Default**: `1`

Inner padding within node boxes:

```typescript
// Tight
renderMermaidAscii(diagram, { boxBorderPadding: 0 })
// Result: |A|

// Normal (default)
renderMermaidAscii(diagram, { boxBorderPadding: 1 })
// Result: | A |

// Spacious
renderMermaidAscii(diagram, { boxBorderPadding: 2 })
// Result: |  A  |
```

---

## Complete Options Example

```typescript
const ascii = renderMermaidAscii(diagram, {
  useAscii: true,        // ASCII-only characters
  paddingX: 3,           // Horizontal spacing
  paddingY: 2,           // Vertical spacing
  boxBorderPadding: 1    // Inner box padding
})
```

---

## Supported Diagram Types

### Flowcharts

```typescript
const diagram = `
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action]
    B -->|No| D[End]
`
const ascii = renderMermaidAscii(diagram)
```

### State Diagrams

```typescript
const diagram = `
stateDiagram-v2
    [*] --> Active
    Active --> Inactive
    Inactive --> Active
    Inactive --> [*]
`
const ascii = renderMermaidAscii(diagram)
```

### Sequence Diagrams

```typescript
const diagram = `
sequenceDiagram
    Alice->>Bob: Hello
    Bob->>Alice: Hi back
`
const ascii = renderMermaidAscii(diagram)
```

### Class Diagrams

```typescript
const diagram = `
classDiagram
    Animal <|-- Dog
    Animal <|-- Cat
`
const ascii = renderMermaidAscii(diagram)
```

### ER Diagrams

```typescript
const diagram = `
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains
`
const ascii = renderMermaidAscii(diagram)
```

---

## Markdown Integration

### Code Blocks

```typescript
const ascii = renderMermaidAscii(diagram)
const markdown = `## System Architecture

\`\`\`
${ascii}
\`\`\`
`
```

### Inline Diagrams

For simple diagrams, embed directly:

```typescript
const simple = renderMermaidAscii('graph LR; A --> B', {
  paddingX: 2,
  boxBorderPadding: 0
})
// Compact output suitable for inline use
```

---

## Terminal Output

### Direct Print

```typescript
console.log(renderMermaidAscii(diagram))
```

### With Colors (ANSI)

ASCII output is plain text. Add ANSI colors manually if needed:

```typescript
const ascii = renderMermaidAscii(diagram)

// Example: Highlight node names
const colored = ascii.replace(/\|([^|]+)\|/g, '|\x1b[36m$1\x1b[0m|')
console.log(colored)
```

---

## File Output

```typescript
import { writeFileSync } from 'fs'

const ascii = renderMermaidAscii(diagram, { useAscii: true })
writeFileSync('diagram.txt', ascii)
```

---

## Character Reference

### Unicode Mode Characters

| Element | Character |
|---------|-----------|
| Horizontal line | `-` |
| Vertical line | `|` |
| Corner (top-left) | `+` |
| Corner (top-right) | `+` |
| Corner (bottom-left) | `+` |
| Corner (bottom-right) | `+` |
| Arrow right | `>` |
| Arrow left | `<` |
| Arrow up | `^` |
| Arrow down | `v` |

### ASCII Mode Characters

Same as Unicode mode - the library uses ASCII-compatible characters by default.

---

## Best Practices

1. **Use ASCII mode for email**: Maximum compatibility
2. **Use Unicode mode for terminals**: Better appearance
3. **Adjust padding for context**: Tighter for inline, looser for standalone
4. **Test rendering**: Preview output before committing to documentation
5. **Consider width limits**: Terminal windows and markdown renderers have width limits

---

## Troubleshooting

### Diagram too wide

Reduce padding or simplify diagram:

```typescript
renderMermaidAscii(diagram, {
  paddingX: 1,
  boxBorderPadding: 0
})
```

### Garbled output

Use ASCII mode for maximum compatibility:

```typescript
renderMermaidAscii(diagram, { useAscii: true })
```

### Empty output

Verify Mermaid syntax is valid. Test at mermaid.live first.
