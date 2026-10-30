#!/usr/bin/env python3
"""Normalize and render LaTeX formulas for WeChat-compatible HTML.

Canonical ``article.md`` keeps the LaTeX source.  ``article.render.md`` is a
derived formatter input where block formulas become image references and
inline formulas become ``{{formula:id}}`` markers.  KaTeX renders each source
to an HTML page and Chrome rasterizes it to a high-resolution PNG under
``imgs/formulas``; the publisher can therefore upload formulas like any other
WeChat content image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import html as html_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops
except ImportError:  # pragma: no cover - surfaced as a runtime block below
    Image = None  # type: ignore[assignment]
    ImageChops = None  # type: ignore[assignment]

try:
    from excerpt_utils import section_excerpt_sha256 as _shared_excerpt_sha256
except ImportError:
    _shared_excerpt_sha256 = None

from workspace_paths import resolve_article_workspace


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "skills" / "formula-rendering" / "render_formula.mjs"
FORMULA_DIR = ROOT / "skills" / "formula-rendering"
FORMULA_MANIFEST = "formula-manifest.json"
RENDER_SOURCE = "article.render.md"
# Block formulas first, then inline.  The previous single-regex backreference
# trick ``(?<!\\)\$(\$?)(.+?)\1\$`` mishandled escaped ``\$`` and, under
# ``re.S``, could over-match across newlines.  Splitting into two explicit
# passes is simpler and robust.
BLOCK_RE = re.compile(r"\$\$(.+?)\$\$", flags=re.S)
INLINE_RE = re.compile(r"(?<!\\)\$(?!\$)([^\n]+?)(?<!\\)\$(?!\$)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
MATH_CODE_PATTERNS = (
    re.compile(r"[×·√∈≈→←⊤²³⁴]"),
    # Only flag conventional math/shape variable forms.  Generic audit and
    # API identifiers such as ``principal_id`` or ``trace_id`` are ordinary
    # code and must not be forced into a LaTeX asset ledger.
    re.compile(r"\b(?:d|n|q|k|v|W|H|L|T)_[A-Za-z0-9]+\b"),
    re.compile(r"\b[A-Za-z]\s*[+*/-]\s*\d\b"),
    re.compile(r"\bO\([^`]+\)"),
    re.compile(r"\[[A-Za-z][^\]]*\]"),
)
MATH_CODE_ALLOWLIST = {
    "dim=-1",
    "attention_weights",
    "torch.softmax",
    "scores",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def article_path(raw: str | Path) -> Path:
    return resolve_article_workspace(raw, allow_test_fixture=True)


def _skip_code_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    cursor = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if start is None:
                start = cursor
            else:
                ranges.append((start, cursor + len(line)))
                start = None
        cursor += len(line)
    if start is not None:
        ranges.append((start, len(text)))
    return ranges


def _in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def extract_formulas(text: str) -> list[dict[str, Any]]:
    """Extract block and inline formulas while ignoring fenced code blocks.

    Block ``$$...$$`` formulas are detected first; their spans are then added
    to the skip set so the inline pass never matches a ``$`` that lives inside
    a block formula.  Results are returned in document order.
    """
    code_ranges = _skip_code_ranges(text)
    block_ranges = [(m.start(), m.end()) for m in BLOCK_RE.finditer(text)]
    found: list[dict] = []
    for match in BLOCK_RE.finditer(text):
        # Block pass: only skip fenced code blocks, never skip block spans.
        if _in_ranges(match.start(), code_ranges):
            continue
        source = canonical_text(match.group(1))
        if not source:
            continue
        found.append({
            "source": source,
            "display_mode": "block",
            "start": match.start(),
            "end": match.end(),
        })
    # Inline pass: skip both fenced code blocks and already-matched block spans.
    skip = code_ranges + block_ranges
    for match in INLINE_RE.finditer(text):
        if _in_ranges(match.start(), skip):
            continue
        source = canonical_text(match.group(1))
        if not source:
            continue
        found.append({
            "source": source,
            "display_mode": "inline",
            "start": match.start(),
            "end": match.end(),
        })
    found.sort(key=lambda item: item["start"])
    return found


def find_unrendered_math_literals(text: str) -> list[dict[str, Any]]:
    """Find math-like inline code that should have been written as LaTeX.

    Backticks are reserved for executable identifiers and code. Dimensions,
    subscripts, matrix shapes and asymptotic expressions inside backticks are
    visually inconsistent in WeChat and bypass the formula asset ledger, so
    they are blocked before formatting. Fenced code blocks are intentionally
    ignored; ``dim=-1`` and other explicitly allowlisted implementation tokens
    remain valid code.
    """
    ranges = _skip_code_ranges(text)
    findings: list[dict[str, Any]] = []
    for match in INLINE_CODE_RE.finditer(text):
        if _in_ranges(match.start(), ranges):
            continue
        value = canonical_text(match.group(1))
        if value in MATH_CODE_ALLOWLIST:
            continue
        if any(pattern.search(value) for pattern in MATH_CODE_PATTERNS):
            findings.append({"value": value, "start": match.start(), "end": match.end()})
    return findings


def _formula_id(index: int) -> str:
    return f"f-{index:03d}"


def _section_for_position(text: str, position: int) -> tuple[str, str]:
    """Return the nearest level-2 section and its body for an occurrence."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M))
    if not matches:
        return "", text
    selected = matches[0]
    for match in matches:
        if match.start() <= position:
            selected = match
        else:
            break
    end = len(text)
    for match in matches:
        if match.start() > selected.start():
            end = match.start()
            break
    heading = selected.group(1).strip()
    body = text[selected.end():end].strip()
    return heading, body


def _claim_ids_for_heading(heading: str) -> list[str]:
    """Map formula context to the article's stable claim groups."""
    value = heading.lower()
    claims: list[str] = []
    if any(token in value for token in ("q", "k", "v", "投影")):
        claims.append("c1")
    if any(token in value for token in ("shape", "score", "矩阵")):
        claims.append("c2")
    if any(token in value for token in ("attention", "softmax", "mask", "手算")):
        claims.extend(["c3", "c4"])
    if any(token in value for token in ("self", "cross", "multi-head", "多头")):
        claims.append("c5")
    if "kv cache" in value or "prefill" in value or "decode" in value:
        claims.extend(["c6", "c7"])
    if "验收" in heading or "清单" in heading:
        claims = [f"c{i}" for i in range(1, 8)]
    return list(dict.fromkeys(claims))


def _replace_source(text: str, occurrence_map: list[dict[str, Any]]) -> str:
    """Replace each detected formula occurrence with its render marker.

    ``occurrence_map`` is parallel to the occurrences returned by
    :func:`extract_formulas`, so the same canonical source (which may repeat in
    the document) maps to the same reused ``formula_id`` / PNG.
    """
    replacements: list[tuple[int, int, str]] = []
    found = extract_formulas(text)
    for occurrence, raw in enumerate(found):
        item = occurrence_map[occurrence]
        formula_id = item["formula_id"]
        output = item["output"]
        if item["display_mode"] == "block":
            replacement = f"![公式 {formula_id}]({output})"
        else:
            replacement = f"{{{{formula:{formula_id}}}}}"
        replacements.append((raw["start"], raw["end"], replacement))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _chrome_path() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    chrome = next((path for path in candidates if path.is_file()), None)
    if chrome is None:
        chrome_name = shutil.which("chrome")
        chrome = Path(chrome_name) if chrome_name else None
    if chrome is None:
        raise RuntimeError("未找到 Chrome，无法将 KaTeX 结果栅格化为 PNG")
    return chrome


FORMULA_DPR = 2


def _crop_formula(
    raw_path: Path,
    png_path: Path,
    display_mode: str,
    *,
    dpr: int = FORMULA_DPR,
    baseline_y_css: float | None = None,
) -> dict[str, Any]:
    """Trim the browser canvas so formulas cannot become giant blank panels."""
    if Image is None or ImageChops is None:
        raise RuntimeError("公式紧致裁剪需要 Pillow；请先安装 Pillow")
    image = Image.open(raw_path).convert("RGBA")
    # The Chrome screenshot is intentionally transparent so the tight crop
    # can use the alpha channel.  ``raw_was_transparent`` records that state
    # for the clip check below; the final PNG is always composited onto solid
    # white so it stays readable in WeChat (including dark mode and after the
    # platform's image re-encoding), instead of disappearing like a transparent
    # glyph-on-nothing PNG would.
    alpha = image.getchannel("A")
    alpha_min, alpha_max = alpha.getextrema()
    raw_was_transparent = alpha_min < 250
    if raw_was_transparent:
        mask = alpha.point(lambda value: 255 if value > 12 else 0)
    else:
        background = Image.new("RGBA", image.size, (255, 253, 249, 255))
        diff = ImageChops.difference(image, background).convert("L")
        mask = diff.point(lambda value: 255 if value > 12 else 0)
    bbox = mask.getbbox()
    if not bbox:
        raise RuntimeError(f"公式没有可见内容：{png_path.name}")
    margin = 2 if display_mode == "inline" else 5
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(image.width, bbox[2] + margin)
    bottom = min(image.height, bbox[3] + margin)
    cropped = image.crop((left, top, right, bottom))
    # Composite the tight-cropped glyphs onto solid white before saving.
    white_bg = Image.new("RGBA", cropped.size, (255, 255, 255, 255))
    white_bg.paste(cropped, (0, 0), cropped)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    white_bg.convert("RGB").save(png_path, "PNG", optimize=True)
    content_area = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    cropped_area = max(1, cropped.width * cropped.height)
    blank_ratio = round(1 - content_area / cropped_area, 4)
    limit = 0.70 if display_mode == "inline" else 0.55
    metrics = {
        "width": cropped.width,
        "height": cropped.height,
        "pixel_ratio": dpr,
        "css_width": round(cropped.width / max(1, dpr)),
        "css_height": round(cropped.height / max(1, dpr)),
        "bbox": [left, top, right, bottom],
        "blank_ratio": blank_ratio,
        "blank_ratio_limit": limit,
        "mobile_readable": cropped.height >= (16 if display_mode == "inline" else 24),
        # KaTeX glyphs can legitimately reach the top of a zero-margin
        # browser canvas; horizontal/right/bottom contact is the meaningful
        # truncation signal for this renderer.
        # Chrome's transparent headless screenshot may auto-trim the
        # viewport to the content box.  Edge contact is therefore only a
        # clipping signal for opaque canvases; KaTeX itself has already
        # completed layout before this crop runs.
        "transparent_background": False,
        "raw_was_transparent": raw_was_transparent,
        "clipped": (not raw_was_transparent) and (bbox[0] <= 0 or bbox[2] >= image.width - 1 or bbox[3] >= image.height - 1),
    }
    # The PNG is tight-cropped around the glyphs, so its CSS baseline is no
    # longer the image bottom.  Persist the exact descender depth measured
    # from KaTeX's zero-width baseline marker; the WeChat HTML formatter uses
    # this value as a per-formula vertical-align offset instead of guessing a
    # single -0.14em for every expression.
    if display_mode == "inline" and baseline_y_css is not None:
        baseline_y_px = float(baseline_y_css) * float(dpr)
        descent_px = float(bottom) - baseline_y_px
        metrics["baseline_y_css"] = round(float(baseline_y_css), 4)
        metrics["baseline_shift_px"] = round(-descent_px / float(dpr), 4)
        metrics["baseline_method"] = "katex-zero-width-baseline-marker"
    return metrics


def _measure_formula_baseline(html_path: Path) -> float | None:
    """Read the KaTeX baseline marker emitted by render_formula.mjs."""
    chrome = _chrome_path()
    result = subprocess.run(
        [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", "--dump-dom", html_path.resolve().as_uri()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        return None
    match = re.search(r'data-baseline-y="?([^"\s>]+)', result.stdout)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _write_formula_svg(article: Path, item: dict[str, Any], html_path: Path) -> Path:
    """Keep an editable KaTeX-backed SVG intermediate beside the TeX source."""
    svg_path = article / str(item["svg_output"])
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_text, flags=re.I | re.S)
    body = body_match.group(1).strip() if body_match else html_text
    tex = html_mod.escape(str(item.get("source_tex", "")), quote=True)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xhtml="http://www.w3.org/1999/xhtml" width="2400" height="500" viewBox="0 0 2400 500" data-tex="{tex}" data-display-mode="{html_mod.escape(str(item.get("display_mode", "block")), quote=True)}">
  <title>{tex}</title>
  <foreignObject x="0" y="0" width="2400" height="500">
    <xhtml:div style="margin:0;padding:0;width:max-content;min-width:12px;min-height:20px;background:#fffdf9;color:#17324D;font-family:serif;font-size:24px;">
      {body}
    </xhtml:div>
  </foreignObject>
</svg>
'''
    svg_path.write_text(svg, encoding="utf-8")
    return svg_path


def _render_one(article: Path, item: dict[str, Any]) -> None:
    tex_path = article / item["source_file"]
    html_path = article / ".tmp-formulas" / f"{item['formula_id']}.html"
    png_path = article / item["output"]
    raw_path = article / ".tmp-formulas" / f"{item['formula_id']}.raw.png"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["node", str(RENDERER), "--input", str(tex_path), "--output", str(html_path), "--mode", str(item["display_mode"])],
        cwd=FORMULA_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"KaTeX failed: {item['formula_id']}")
    chrome = _chrome_path()
    # Use a tall viewport (2400x2000) to prevent Chrome from clipping or
    # rotating content when KaTeX layouts exceed the old 500px height limit.
    # The tight-crop step (_crop_formula) will trim the final PNG regardless.
    shot = subprocess.run(
        [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", f"--force-device-scale-factor={FORMULA_DPR}", "--default-background-color=00000000",
         "--window-size=2400,2000", f"--screenshot={raw_path}", html_path.as_uri()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if shot.returncode or not raw_path.is_file() or raw_path.stat().st_size < 1024:
        raise RuntimeError(shot.stderr.strip() or shot.stdout.strip() or f"公式原始 PNG 输出无效：{raw_path}")
    # Rotation guard: if the raw screenshot is taller than wide for an inline
    # formula, Chrome likely rotated the content.  Re-render with an even
    # larger viewport as a fallback.
    if Image is not None:
        _probe = Image.open(raw_path)
        if str(item["display_mode"]) == "inline" and _probe.height > _probe.width:
            shot = subprocess.run(
                [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", f"--force-device-scale-factor={FORMULA_DPR}", "--default-background-color=00000000",
                 "--window-size=3000,3000", f"--screenshot={raw_path}", html_path.as_uri()],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if shot.returncode or not raw_path.is_file() or raw_path.stat().st_size < 1024:
                raise RuntimeError(shot.stderr.strip() or shot.stdout.strip() or f"公式原始 PNG 输出无效（重试）：{raw_path}")
    baseline_y_css = _measure_formula_baseline(html_path) if str(item["display_mode"]) == "inline" else None
    item["visual_metrics"] = _crop_formula(
        raw_path,
        png_path,
        str(item["display_mode"]),
        dpr=FORMULA_DPR,
        baseline_y_css=baseline_y_css,
    )
    try:
        raw_path.unlink()
    except OSError:
        pass
    if item["visual_metrics"]["blank_ratio"] > item["visual_metrics"]["blank_ratio_limit"]:
        raise RuntimeError(f"公式空白比例过高：{item['formula_id']}")
    if not item["visual_metrics"]["mobile_readable"]:
        raise RuntimeError(f"公式移动端高度不足：{item['formula_id']}")
    item["output_sha256"] = sha256(png_path)
    item["source_sha256"] = sha256(tex_path)
    persisted_html = article / "formula-src" / f"{item['formula_id']}.html"
    persisted_html.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, persisted_html)
    item["html_output"] = str(persisted_html.relative_to(article)).replace("\\", "/")
    item["html_sha256"] = sha256(persisted_html)
    item["clipped"] = bool(item["visual_metrics"].get("clipped"))
    _write_formula_svg(article, item, html_path)
    item["svg_sha256"] = sha256(article / str(item["svg_output"]))
    item["unresolved_placeholder"] = bool(re.search(r"\{\{formula:|(?<!\\)\$\$?[^$]+\$\$?", html_path.read_text(encoding="utf-8", errors="replace")))
    item["renderer"] = "katex-html-chrome-tight-v3"


def prepare(article: Path) -> int:
    source = article / "article.md"
    if not source.is_file():
        print(f"FORMULA BLOCKED: 缺少 {source}", file=sys.stderr)
        return 1
    text = source.read_text(encoding="utf-8")
    found = extract_formulas(text)
    formula_dir = article / "formula-src"
    image_dir = article / "imgs" / "formulas"
    formula_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []            # unique formulas -> manifest
    occurrence_map: list[dict[str, Any]] = []    # parallel to `found`
    seen: dict[str, dict[str, Any]] = {}
    for raw in found:
        src = raw["source"]
        if src in seen:
            # Same canonical source already rendered: reuse its PNG and only
            # bump the occurrence count instead of re-running KaTeX + Chrome.
            seen[src]["occurrence_count"] = seen[src].get("occurrence_count", 1) + 1
            occurrence_map.append(seen[src])
            continue
        formula_id = _formula_id(len(items) + 1)
        source_file = formula_dir / f"{formula_id}.tex"
        source_file.write_text(src + "\n", encoding="utf-8")
        section_heading, section_body = _section_for_position(text, int(raw.get("start", 0)))
        excerpt = canonical_text(section_body)[:1200]
        # Use the shared excerpt_utils module for SHA-256 computation to
        # ensure consistency with visual_semantic_qa.py (single source of truth).
        if _shared_excerpt_sha256 is not None:
            excerpt_digest = _shared_excerpt_sha256(article, section_heading)
        else:
            excerpt_digest = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        item = {
            "formula_id": formula_id,
            "display_mode": raw["display_mode"],
            "source_tex": src,
            "source_file": str(source_file.relative_to(article)).replace("\\", "/"),
            "output": f"imgs/formulas/{formula_id}.png",
            "svg_output": f"formula-src/{formula_id}.svg",
            "alt": f"公式 {formula_id}",
            "renderer": "katex-html-chrome-tight-v3",
            "claim_ids": _claim_ids_for_heading(section_heading),
            "section_heading": section_heading,
            "source_excerpt_sha256": excerpt_digest,
            "occurrence_count": 1,
        }
        _render_one(article, item)
        seen[src] = item
        items.append(item)
        occurrence_map.append(item)
    render_text = _replace_source(text, occurrence_map)
    (article / RENDER_SOURCE).write_text(render_text, encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "contract": "formula-render-v2",
        "status": "passed",
        "source": "article.md",
        "render_source": RENDER_SOURCE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formulas": items,
    }
    (article / FORMULA_MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "count": len(items), "manifest": str(article / FORMULA_MANIFEST)}, ensure_ascii=False, indent=2))
    return 0


def check(article: Path) -> int:
    manifest_path = article / FORMULA_MANIFEST
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
        errors.append("缺少或无法读取 formula-manifest.json")
    if manifest.get("contract") not in {"formula-render-v1", "formula-render-v2"}:
        errors.append("formula-manifest.json contract 必须为 formula-render-v1 或 formula-render-v2")
    source = article / str(manifest.get("source") or "article.md")
    formulas = manifest.get("formulas") if isinstance(manifest.get("formulas"), list) else []
    if not source.is_file():
        errors.append("公式 canonical source 不存在")
    else:
        source_text = source.read_text(encoding="utf-8")
        strict_literals = find_unrendered_math_literals(source_text)
        for finding in strict_literals:
            errors.append(f"数学表达仍以行内代码存在：{finding['value']}；请改为 $...$ LaTeX")
        detected = extract_formulas(source_text)
        unique_sources = {f["source"] for f in detected}
        if len(unique_sources) != len(formulas):
            errors.append(f"公式数量不一致：source唯一数={len(unique_sources)} manifest={len(formulas)}")
    section_cache: dict[str, str] = {}
    if source.is_file():
        source_text = source.read_text(encoding="utf-8")
        for match in re.finditer(r"^##\s+(.+?)\s*$", source_text, flags=re.M):
            heading, body = _section_for_position(source_text, match.start())
            section_cache[heading] = canonical_text(body)[:1200]
    for item in formulas:
        if not isinstance(item, dict):
            errors.append("formula-manifest.json 含有非法记录")
            continue
        formula_id = str(item.get("formula_id", ""))
        tex = article / str(item.get("source_file", ""))
        png = article / str(item.get("output", ""))
        svg = article / str(item.get("svg_output", "")) if item.get("svg_output") else None
        html_asset = article / str(item.get("html_output", "")) if item.get("html_output") else None
        if not tex.is_file() or not png.is_file():
            errors.append(f"公式资产缺失：{formula_id}")
            continue
        if manifest.get("contract") == "formula-render-v2" and (svg is None or not svg.is_file()):
            errors.append(f"公式 SVG 中间资产缺失：{formula_id}")
        if str(item.get("source_sha256", "")) != sha256(tex):
            errors.append(f"公式源哈希不匹配：{formula_id}")
        if str(item.get("output_sha256", "")) != sha256(png):
            errors.append(f"公式 PNG 哈希不匹配：{formula_id}")
        if svg is not None and svg.is_file() and str(item.get("svg_sha256", "")) != sha256(svg):
            errors.append(f"公式 SVG 哈希不匹配：{formula_id}")
        metrics = item.get("visual_metrics") if isinstance(item.get("visual_metrics"), dict) else {}
        if manifest.get("contract") == "formula-render-v2":
            if html_asset is None or not html_asset.is_file() or not str(item.get("html_sha256", "")).strip():
                errors.append(f"公式缺少 HTML 中间资产：{formula_id}")
            elif str(item.get("html_sha256", "")) != sha256(html_asset):
                errors.append(f"公式 HTML 哈希不匹配：{formula_id}")
            if item.get("clipped") is True or item.get("unresolved_placeholder") is True:
                errors.append(f"公式存在裁切或未解析占位符：{formula_id}")
            if str(item.get("display_mode", "block")) == "inline":
                baseline_shift = metrics.get("baseline_shift_px")
                if not isinstance(baseline_shift, (int, float)):
                    errors.append(f"行内公式缺少 KaTeX 基线偏移：{formula_id}")
        try:
            blank_ratio = float(metrics.get("blank_ratio", 1.0))
            blank_limit = float(metrics.get("blank_ratio_limit", 0.0))
            if blank_ratio > blank_limit:
                errors.append(f"公式空白比例超限：{formula_id}")
        except (TypeError, ValueError):
            errors.append(f"公式缺少有效视觉指标：{formula_id}")
        try:
            pixel_ratio = int(metrics.get("pixel_ratio", 0) or 0)
            css_width = int(metrics.get("css_width", 0) or 0)
            css_height = int(metrics.get("css_height", 0) or 0)
            if pixel_ratio < 2 or css_width < 1 or css_height < 1:
                errors.append(f"公式未使用高 DPI 栅格或缺少 CSS 尺寸：{formula_id}")
        except (TypeError, ValueError):
            errors.append(f"公式视觉指标缺少 pixel_ratio/css_width/css_height：{formula_id}")
        if metrics.get("mobile_readable") is not True:
            errors.append(f"公式移动端不可读：{formula_id}")
        heading = str(item.get("section_heading", ""))
        excerpt_hash = str(item.get("source_excerpt_sha256", ""))
        if heading and heading in section_cache:
            expected_excerpt_hash = hashlib.sha256(section_cache[heading].encode("utf-8")).hexdigest()
            if excerpt_hash != expected_excerpt_hash:
                errors.append(f"公式正文片段哈希不匹配：{formula_id}")
        elif heading or excerpt_hash:
            errors.append(f"公式缺少可复核的正文片段：{formula_id}")
    html = article / "article.html"
    if html.is_file():
        html_text = html.read_text(encoding="utf-8", errors="replace")
        if "$" in html_text:
            errors.append("article.html 残留未渲染的公式文本")
        for item in formulas:
            output = str(item.get("output", ""))
            if output and output not in html_text:
                # A published/remote HTML may already contain a CDN URL; the
                # local pre-publish HTML must contain the relative reference.
                errors.append(f"article.html 未引用公式图片：{output}")
    report = {
        "schema_version": 2,
        "contract": manifest.get("contract", "formula-render-v2"),
        "render_profile": "katex-html-chrome-tight-v3",
        "status": "passed" if not errors else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "formula_count": len(formulas),
    }
    (article / FORMULA_MANIFEST).write_text(json.dumps({**manifest, "check": report}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("FORMULA QA BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"FORMULA QA PASSED: {len(formulas)} formulas")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "check"):
        command = sub.add_parser(name)
        command.add_argument("--article", required=True)
    args = parser.parse_args()
    article = article_path(args.article)
    return prepare(article) if args.command == "prepare" else check(article)


if __name__ == "__main__":
    raise SystemExit(main())
