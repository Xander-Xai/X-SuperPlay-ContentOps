#!/usr/bin/env npx ts-node
/**
 * Render Mermaid diagrams from CLI
 *
 * Usage:
 *   npx ts-node render-diagram.ts <input-file> [options]
 *   npx ts-node render-diagram.ts diagram.mmd --output diagram.svg --theme tokyo-night
 *   npx ts-node render-diagram.ts diagram.mmd --ascii
 *
 * Options:
 *   --output, -o    Output file path (default: stdout)
 *   --theme, -t     Theme name (default: zinc-light)
 *   --ascii, -a     Output ASCII instead of SVG
 *   --unicode       Use Unicode characters for ASCII output (default)
 *   --bg            Background color (overrides theme)
 *   --fg            Foreground color (overrides theme)
 */

import { readFileSync, writeFileSync } from 'fs'
import { renderMermaid, renderMermaidAscii, THEMES } from 'beautiful-mermaid'

interface Options {
  input?: string
  output?: string
  theme: string
  ascii: boolean
  unicode: boolean
  bg?: string
  fg?: string
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    theme: 'zinc-light',
    ascii: false,
    unicode: true
  }

  for (let i = 0; i < args.length; i++) {
    const arg = args[i]

    if (arg === '--output' || arg === '-o') {
      options.output = args[++i]
    } else if (arg === '--theme' || arg === '-t') {
      options.theme = args[++i]
    } else if (arg === '--ascii' || arg === '-a') {
      options.ascii = true
    } else if (arg === '--unicode') {
      options.unicode = true
    } else if (arg === '--no-unicode') {
      options.unicode = false
    } else if (arg === '--bg') {
      options.bg = args[++i]
    } else if (arg === '--fg') {
      options.fg = args[++i]
    } else if (!arg.startsWith('-')) {
      options.input = arg
    }
  }

  return options
}

async function main() {
  const args = process.argv.slice(2)

  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
Usage: npx ts-node render-diagram.ts <input-file> [options]

Options:
  --output, -o    Output file path (default: stdout)
  --theme, -t     Theme name (default: zinc-light)
  --ascii, -a     Output ASCII instead of SVG
  --unicode       Use Unicode characters for ASCII (default)
  --no-unicode    Use ASCII characters only
  --bg            Background color (overrides theme)
  --fg            Foreground color (overrides theme)

Available themes:
  zinc-light, zinc-dark, tokyo-night, tokyo-night-storm, tokyo-night-light,
  catppuccin-mocha, catppuccin-latte, nord, nord-light, dracula,
  github-light, github-dark, solarized-light, solarized-dark, one-dark

Examples:
  npx ts-node render-diagram.ts diagram.mmd
  npx ts-node render-diagram.ts diagram.mmd -o output.svg -t tokyo-night
  npx ts-node render-diagram.ts diagram.mmd --ascii
  npx ts-node render-diagram.ts diagram.mmd --bg "#1a1b26" --fg "#a9b1d6"
`)
    process.exit(0)
  }

  const options = parseArgs(args)

  if (!options.input) {
    console.error('Error: No input file specified')
    process.exit(1)
  }

  // Read input
  const diagram = readFileSync(options.input, 'utf-8')

  let result: string

  if (options.ascii) {
    // ASCII rendering
    result = renderMermaidAscii(diagram, {
      useAscii: !options.unicode
    })
  } else {
    // SVG rendering
    const themeColors = THEMES[options.theme] || THEMES['zinc-light']
    const colors = {
      ...themeColors,
      ...(options.bg && { bg: options.bg }),
      ...(options.fg && { fg: options.fg })
    }
    result = await renderMermaid(diagram, colors)
  }

  // Output
  if (options.output) {
    writeFileSync(options.output, result)
    console.log(`Written to ${options.output}`)
  } else {
    console.log(result)
  }
}

main().catch(err => {
  console.error('Error:', err.message)
  process.exit(1)
})
