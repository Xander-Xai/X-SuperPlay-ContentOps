#!/bin/bash
# Setup script for beautiful-mermaid skill
# Installs all necessary dependencies

set -e

echo "Installing beautiful-mermaid..."

# Check if package.json exists, create if not
if [ ! -f package.json ]; then
    echo "No package.json found. Initializing..."
    npm init -y
fi

# Install beautiful-mermaid
npm install beautiful-mermaid

# Optional: Install shiki for VS Code theme integration
read -p "Install shiki for VS Code theme integration? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    npm install shiki
    echo "Shiki installed. Use fromShikiTheme() for VS Code themes."
fi

echo ""
echo "Setup complete. Usage:"
echo ""
echo "  import { renderMermaid, renderMermaidAscii, THEMES } from 'beautiful-mermaid'"
echo ""
echo "  // SVG output"
echo "  const svg = await renderMermaid('graph LR; A --> B')"
echo ""
echo "  // ASCII output"
echo "  const ascii = renderMermaidAscii('graph LR; A --> B')"
echo ""
