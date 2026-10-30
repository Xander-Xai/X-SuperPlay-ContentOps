#!/usr/bin/env node
/**
 * Single source of truth for deterministic visual color tokens (RC3).
 *
 * Every renderer that paints an account-themed diagram must pull its palette
 * from profiles/visual-styles.yaml via loadDesignTokens(); never hardcode a
 * second copy of the colors (the old THEMES_BY_ACCOUNT duplication in
 * render_mermaid_visual.mjs is exactly the drift RC3 forbids).
 *
 * The bundled YAML subset parser supports the two-level nesting used by the
 * profile (accounts.<name>.design_tokens.<token>) plus inline flow lists
 * [a, b]. We avoid a third-party YAML dependency so the renderers stay
 * launchable from a bare Node process.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const YAML_PATH = path.resolve(here, "../profiles/visual-styles.yaml");

/** Minimal indentation-based YAML reader (mappings + inline flow lists). */
function parseYaml(text) {
  const root = {};
  const stack = [{ indent: -1, node: root }];
  let listKey = null; // key that owns the most recent block list, if any
  for (const raw of String(text).split(/\r?\n/)) {
    if (!raw.trim() || raw.trimStart().startsWith("#")) continue;
    const indent = raw.length - raw.trimStart().length;
    const trimmed = raw.trim();

    // Block list item: "- value"
    const listItem = trimmed.match(/^-\s*(.*)$/);
    if (listItem) {
      const parent = stack[stack.length - 1].node;
      if (listKey && !Array.isArray(parent[listKey])) parent[listKey] = [];
      if (Array.isArray(parent[listKey])) {
        parent[listKey].push(listItem[1].replace(/^["']|["']$/g, ""));
      }
      continue;
    }

    const m = trimmed.match(/^([A-Za-z0-9_\-]+):\s*(.*)$/);
    if (!m) continue;
    const key = m[1];
    const rawValue = m[2].replace(/^["']|["']$/g, "");
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const parent = stack[stack.length - 1].node;

    if (rawValue === "") {
      const child = {};
      parent[key] = child;
      stack.push({ indent, node: child });
      listKey = key;
    } else {
      const flow = rawValue.match(/^\[(.*)\]$/);
      if (flow) {
        parent[key] = flow[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
      } else {
        parent[key] = rawValue;
      }
      listKey = key;
    }
  }
  return root;
}

let cached = undefined;
function loadYaml() {
  if (cached !== undefined) return cached;
  try {
    cached = parseYaml(fs.readFileSync(YAML_PATH, "utf8"));
  } catch {
    cached = {};
  }
  return cached;
}

/**
 * Resolve the palette for an account.
 * @param {string} account "sentinel" | "thinktank"
 * @returns {{paper:string,surface:string,ink:string,muted:string,accent:string,line:string,font_stack:string,mono_stack:string}}
 */
/**
 * Read the fixed account id from workflow-identity.yaml (split targets).
 * Missing or malformed identity is a hard error in a split target.
 */
export function defaultAccount() {
  try {
    const idPath = path.resolve(here, "../workflow-identity.yaml");
    const text = fs.readFileSync(idPath, "utf8");
    const m = String(text).match(/^account_id:\s*([A-Za-z0-9_-]+)\s*$/m);
    if (m) return m[1];
  } catch (err) {
    throw new Error(`workflow identity unavailable: ${err.message}`);
  }
  throw new Error("workflow-identity.yaml missing account_id");
}

export function loadDesignTokens(account = defaultAccount()) {
  const fixed = defaultAccount();
  if (String(account).trim().toLowerCase() !== String(fixed).trim().toLowerCase()) {
    throw new Error(`account ${account} is not allowed in this split target (fixed: ${fixed})`);
  }
  const data = loadYaml();
  const defaults = (data.design_tokens_default && typeof data.design_tokens_default === "object") ? data.design_tokens_default : {};
  const accounts = (data.accounts && typeof data.accounts === "object") ? data.accounts : {};
  const acct = (accounts[account] && typeof accounts[account] === "object") ? accounts[account] : {};
  const tokens = (acct.design_tokens && typeof acct.design_tokens === "object") ? acct.design_tokens : {};
  const t = { ...defaults, ...tokens };
  return {
    paper: t.background || (account === "sentinel" ? "#F7EFE5" : "#F4F0E8"),
    surface: t.surface || "#FFFCF7",
    ink: t.ink || (account === "sentinel" ? "#252525" : "#17324D"),
    muted: t.muted || "#5E6872",
    accent: t.vermilion || (account === "sentinel" ? "#E05A2A" : "#B24A2B"),
    line: t.signal || (account === "sentinel" ? "#1B6F8A" : "#557A96"),
    font_stack: t.font_stack || "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif",
    mono_stack: t.mono_stack || "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace",
  };
}

// Allow `node scripts/read_design_tokens.mjs [account]` for ad-hoc checks.
// Compare normalized filesystem paths; the old file:// string comparison was
// false on Windows and silently skipped this CLI (including its fail-closed
// account check).
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
const modulePath = path.resolve(fileURLToPath(import.meta.url));
if (invokedPath && invokedPath === modulePath) {
  const account = process.argv[2] || defaultAccount();
  console.log(JSON.stringify(loadDesignTokens(account), null, 2));
}
