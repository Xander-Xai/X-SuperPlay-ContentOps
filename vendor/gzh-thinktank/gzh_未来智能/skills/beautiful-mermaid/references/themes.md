# Beautiful Mermaid Theming Guide

Complete reference for theming Mermaid diagrams with beautiful-mermaid.

## Theming Philosophy

Beautiful-mermaid uses a **two-color foundation** (Mono Mode) where all diagram colors are derived from just `bg` (background) and `fg` (foreground). This ensures visual harmony with minimal configuration.

---

## Mono Mode (Recommended)

Provide only two colors. Everything else is calculated:

```typescript
const svg = await renderMermaid(diagram, {
  bg: '#1a1b26',  // Background
  fg: '#a9b1d6'   // Foreground
})
```

### Color Derivation Rules

From `bg` and `fg`, the system derives:

| Element | Calculation |
|---------|-------------|
| Text (primary) | `--fg` at 100% |
| Text (secondary) | `--fg` at 60% into `--bg` |
| Edge labels | `--fg` at 40% into `--bg` |
| Connectors | `--fg` at 30% into `--bg` |
| Arrow heads | `--fg` at 50% into `--bg` |
| Node fill | `--fg` at 3% into `--bg` |
| Node stroke | `--fg` at 20% into `--bg` |

The `color-mix()` CSS function handles blending:

```css
/* Example: Secondary text */
color: color-mix(in srgb, var(--fg) 60%, var(--bg));
```

---

## Enriched Mode

Override specific derived colors for finer control:

```typescript
const svg = await renderMermaid(diagram, {
  bg: '#1a1b26',
  fg: '#a9b1d6',
  line: '#565f89',      // Edge/connector color
  accent: '#7aa2f7',    // Arrow heads, highlights
  muted: '#565f89',     // Secondary text, labels
  surface: '#24283b',   // Node fill tint
  border: '#414868'     // Node stroke
})
```

Unprovided colors fall back to Mono Mode derivation.

---

## Built-in Themes

### Light Themes

```typescript
import { THEMES } from 'beautiful-mermaid'

THEMES['zinc-light']       // Clean grayscale
THEMES['tokyo-night-light']
THEMES['catppuccin-latte']
THEMES['nord-light']
THEMES['github-light']
THEMES['solarized-light']
```

### Dark Themes

```typescript
THEMES['zinc-dark']
THEMES['tokyo-night']      // Popular dark theme
THEMES['tokyo-night-storm']
THEMES['catppuccin-mocha']
THEMES['nord']
THEMES['dracula']
THEMES['github-dark']
THEMES['solarized-dark']
THEMES['one-dark']
```

### Using Built-in Themes

```typescript
import { renderMermaid, THEMES } from 'beautiful-mermaid'

const svg = await renderMermaid(diagram, THEMES['tokyo-night'])
```

---

## Custom Themes

### Creating a Custom Theme

```typescript
const customTheme = {
  bg: '#0d1117',
  fg: '#c9d1d9',
  line: '#30363d',
  accent: '#58a6ff',
  muted: '#8b949e',
  surface: '#161b22',
  border: '#30363d'
}

const svg = await renderMermaid(diagram, customTheme)
```

### Theme Type Definition

```typescript
interface DiagramColors {
  bg: string        // Required: Background color
  fg: string        // Required: Foreground color
  line?: string     // Optional: Edge/connector color
  accent?: string   // Optional: Arrow heads, highlights
  muted?: string    // Optional: Secondary text, labels
  surface?: string  // Optional: Node fill tint
  border?: string   // Optional: Node stroke
}
```

---

## Shiki Integration

Use any VS Code theme with `fromShikiTheme()`:

```typescript
import { getSingletonHighlighter } from 'shiki'
import { renderMermaid, fromShikiTheme } from 'beautiful-mermaid'

const highlighter = await getSingletonHighlighter({
  themes: ['vitesse-dark', 'rose-pine', 'material-theme-darker']
})

// Extract colors from Shiki theme
const colors = fromShikiTheme(highlighter.getTheme('vitesse-dark'))
const svg = await renderMermaid(diagram, colors)
```

### Shiki Color Mapping

`fromShikiTheme()` maps VS Code theme colors to diagram roles:

| VS Code Token | Diagram Role |
|---------------|--------------|
| `editor.background` | `bg` |
| `editor.foreground` | `fg` |
| `editorLineNumber.foreground` | `muted` |
| `focusBorder` | `accent` |
| `editorWidget.background` | `surface` |
| `editorWidget.border` | `border` |

---

## Live Theme Switching (Browser)

SVG output uses CSS custom properties. Change themes without re-rendering:

```javascript
const svgElement = document.querySelector('svg')

// Switch to dark theme
svgElement.style.setProperty('--bg', '#1a1b26')
svgElement.style.setProperty('--fg', '#a9b1d6')

// Switch to light theme
svgElement.style.setProperty('--bg', '#ffffff')
svgElement.style.setProperty('--fg', '#27272a')
```

### CSS Custom Properties

The SVG contains these properties:

```css
svg {
  --bg: #ffffff;
  --fg: #27272a;
  --line: /* derived */;
  --accent: /* derived */;
  --muted: /* derived */;
  --surface: /* derived */;
  --border: /* derived */;
}
```

---

## Theme Selection Guide

| Context | Recommended Theme |
|---------|-------------------|
| Light documentation | `zinc-light`, `github-light` |
| Dark documentation | `github-dark`, `zinc-dark` |
| Terminal output | `tokyo-night`, `dracula` |
| Print-friendly | `zinc-light`, `solarized-light` |
| High contrast | Custom with increased `fg`/`bg` difference |
| Brand matching | Custom theme with brand colors |

---

## Best Practices

1. **Start with Mono Mode**: Two colors usually suffice
2. **Match editor theme**: Use `fromShikiTheme()` for consistency
3. **Test contrast**: Ensure text remains readable
4. **Consider output format**: Dark themes for screens, light for print
5. **Use CSS variables**: Enable user preference adaptation
