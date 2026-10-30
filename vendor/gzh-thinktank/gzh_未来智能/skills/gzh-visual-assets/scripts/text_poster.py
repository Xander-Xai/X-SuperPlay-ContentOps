#!/usr/bin/env python3
"""
品牌封面确定性生成器 — 仅用于当前文章封面

当封面生图失败时，用确定性的本地渲染生成当前文章品牌封面。正文技术图不走本工具，
必须由当前主题语义合同驱动的 SVG/HTML/Mermaid/Excalidraw 后端生成或阻断。

用法（仓库根执行）：
    python {baseDir}/scripts/text_poster.py generate --title "文章标题" --subtitle "副标题" -o cover.png
退出码：
    0  成功
    1  失败
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.request
from pathlib import Path


def _info(msg: str):
    print(f"[INFO] {msg}", file=sys.stderr)


def _ok(msg: str):
    print(f"[OK] {msg}")


def _err(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


# ── 海报模板 ──

COVER_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{width}px; height:{height}px; display:flex; align-items:center; justify-content:center;
  background:linear-gradient(135deg, {bg1} 0%, {bg2} 100%); font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',sans-serif; overflow:hidden; }}
.card {{ width:88%; height:82%; display:flex; flex-direction:column; justify-content:center; align-items:center;
  background:rgba(255,255,255,0.08); border-radius:24px; padding:48px; backdrop-filter:blur(10px);
  border:1px solid rgba(255,255,255,0.15); }}
.brand {{ font-size:14px; color:rgba(255,255,255,0.5); letter-spacing:6px; text-transform:uppercase; margin-bottom:32px; }}
.title {{ font-size:{title_size}px; font-weight:800; color:#fff; text-align:center; line-height:1.35;
  margin-bottom:24px; text-shadow:0 2px 20px rgba(0,0,0,0.3); }}
.subtitle {{ font-size:18px; color:rgba(255,255,255,0.7); text-align:center; line-height:1.6; max-width:85%; }}
.divider {{ width:60px; height:3px; background:rgba(255,255,255,0.4); border-radius:2px; margin:28px 0; }}
.tag {{ display:inline-block; padding:6px 16px; border:1px solid rgba(255,255,255,0.3); border-radius:20px;
  font-size:13px; color:rgba(255,255,255,0.6); margin-top:20px; }}
</style></head><body>
<div class="card">
  <div class="brand">{brand}</div>
  <div class="title">{title}</div>
  <div class="divider"></div>
  <div class="subtitle">{subtitle}</div>
  {tag_html}
</div>
</body></html>"""

SECTION_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:{width}px; height:{height}px; display:flex; align-items:center; justify-content:center;
  background:{bg}; font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',sans-serif; overflow:hidden; }}
.card {{ width:90%; height:85%; display:flex; flex-direction:column; justify-content:center; align-items:center;
  background:{card_bg}; border-radius:20px; padding:40px; }}
.icon {{ font-size:64px; margin-bottom:24px; }}
.title {{ font-size:{title_size}px; font-weight:700; color:{text_color}; text-align:center; line-height:1.4;
  margin-bottom:16px; }}
.desc {{ font-size:16px; color:{desc_color}; text-align:center; line-height:1.7; max-width:85%; }}
</style></head><body>
<div class="card">
  <div class="icon">{icon}</div>
  <div class="title">{title}</div>
  <div class="desc">{description}</div>
</div>
</body></html>"""

# ── 配色方案 ──

THEMES = {
    "tech-blue": {"bg1": "#0f0c29", "bg2": "#302b63", "card_bg": "#1a1a2e", "text_color": "#e0e0e0", "desc_color": "#8888aa"},
    "warm-orange": {"bg1": "#f12711", "bg2": "#f5af19", "card_bg": "rgba(255,255,255,0.12)", "text_color": "#fff", "desc_color": "rgba(255,255,255,0.7)"},
    "green-forest": {"bg1": "#134e5e", "bg2": "#71b280", "card_bg": "rgba(0,0,0,0.2)", "text_color": "#fff", "desc_color": "rgba(255,255,255,0.7)"},
    "purple-dream": {"bg1": "#4a00e0", "bg2": "#8e2de2", "card_bg": "rgba(255,255,255,0.08)", "text_color": "#fff", "desc_color": "rgba(255,255,255,0.65)"},
    "minimal-light": {"bg1": "#f5f5f5", "bg2": "#e8e8e8", "card_bg": "#fff", "text_color": "#222", "desc_color": "#666"},
    "dark-red": {"bg1": "#1a1a2e", "bg2": "#16213e", "card_bg": "rgba(255,50,50,0.08)", "text_color": "#f0f0f0", "desc_color": "#aa6666"},
    "sentinel-radar": {
        "bg1": "#F7EFE5", "bg2": "#E6F3F2", "card_bg": "#FFFDF9",
        "text_color": "#252525", "desc_color": "#5C6268",
        "background": "#F7EFE5", "surface": "#FFFDF9", "ink": "#252525",
        "muted": "#5C6268", "accent": "#E05A2A", "secondary": "#1B6F8A",
    },
    "thinktank-atlas": {
        "bg1": "#F4F0E8", "bg2": "#E7EEF3", "card_bg": "#FFFCF7",
        "text_color": "#17324D", "desc_color": "#5E6872",
        "background": "#F4F0E8", "surface": "#FFFCF7", "ink": "#17324D",
        "muted": "#5E6872", "accent": "#B24A2B", "secondary": "#557A96",
    },
}


def _validate_account_theme(theme: str) -> None:
    """Reject the other split target's branded theme in this target."""
    if theme not in {"sentinel-radar", "thinktank-atlas"}:
        return
    try:
        import sys as _sys
        root = Path(__file__).resolve().parents[3]
        _sys.path.insert(0, str(root / "scripts"))
        from account_context import ACCOUNT_ID
        expected = "sentinel-radar" if ACCOUNT_ID == "sentinel" else "thinktank-atlas"
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc
    if theme != expected:
        raise ValueError(f"主题 {theme!r} 不属于本工作流（固定主题：{expected}）")


def _load_account_themes_from_tokens() -> None:
    """Single-source the two account themes from design_tokens (RC3/RC5).

    The generic themes (tech-blue, warm-orange, ...) stay hardcoded for
    callers that intentionally request a non-account look.  The account themes
    are overridden from ``profiles/visual-styles.yaml`` so a brand color change
    only needs one edit.
    """
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(
            (Path(__file__).resolve().parents[3] / "profiles" / "visual-styles.yaml").read_text(encoding="utf-8")
        )
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    theme_by_account = {"sentinel": "sentinel-radar", "thinktank": "thinktank-atlas"}
    for account, theme_name in theme_by_account.items():
        block = accounts.get(account, {})
        if not isinstance(block, dict):
            continue
        tokens = block.get("design_tokens") if isinstance(block.get("design_tokens"), dict) else {}
        if not tokens:
            continue
        THEMES[theme_name] = {
            "bg1": tokens.get("background", "#F4F0E8"),
            "bg2": tokens.get("surface", "#FFFCF7"),
            "card_bg": tokens.get("surface", "#FFFCF7"),
            "text_color": tokens.get("ink", "#17324D"),
            "desc_color": tokens.get("muted", "#5E6872"),
            "background": tokens.get("background", "#F4F0E8"),
            "surface": tokens.get("surface", "#FFFCF7"),
            "ink": tokens.get("ink", "#17324D"),
            "muted": tokens.get("muted", "#5E6872"),
            "accent": tokens.get("vermilion", "#B24A2B"),
            # 边框/分隔线/装饰线用暖朱砂而非信号蓝（用户反馈"图发蓝"）：
            # thinktank 是"纸白底+朱砂锚点"的暖调设计，细线用蓝会整卡发蓝。
            # sentinel 的"编辑部雷达"风格保留电蓝品牌色。
            "secondary": tokens.get("vermilion" if account == "thinktank" else "signal", "#B24A2B"),
        }


_load_account_themes_from_tokens()


def _html_to_png_via_chrome(html_content: str, width: int, height: int, output: Path) -> bool:
    """尝试用 Chrome/Puppeteer 截图；不可用时返回 False。"""
    try:
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html_content)
            html_path = f.name
        
        # 尝试找 Chrome
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        chrome = None
        for p in chrome_paths:
            if Path(p).exists():
                chrome = p
                break
        
        if not chrome:
            # 尝试用 where 找
            try:
                result = subprocess.run(
                    ["where", "chrome"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=5,
                )
                if result.returncode == 0:
                    chrome = result.stdout.strip().split("\n")[0]
            except Exception:
                pass
        
        if not chrome:
            return False
        
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # 用 Chrome headless 截图
        url = f"file:///{html_path.replace(chr(92), '/')}"
        cmd = [
            chrome, "--headless", "--disable-gpu", "--no-sandbox",
            f"--window-size={width},{height}",
            f"--screenshot={str(output)}",
            url
        ]
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
        
        # 清理临时文件
        try:
            Path(html_path).unlink()
        except Exception:
            pass
        
        return output.exists() and output.stat().st_size > 0
        
    except Exception as e:
        _info(f"Chrome 截图失败: {e}")
        return False


def _html_to_png_via_puppeteer(html_content: str, width: int, height: int, output: Path) -> bool:
    """尝试用 Node.js puppeteer 截图。"""
    try:
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html_content)
            html_path = f.name
        
        js_code = f"""
const puppeteer = require('puppeteer');
(async () => {{
    const browser = await puppeteer.launch({{ headless: true, args: ['--no-sandbox'] }});
    const page = await browser.newPage();
    await page.setViewport({{ width: {width}, height: {height} }});
    await page.goto('file:///' + '{html_path.replace(chr(92), "/")}' , {{ waitUntil: 'networkidle0' }});
    await page.screenshot({{ path: '{str(output).replace(chr(92), "/")}', type: 'png' }});
    await browser.close();
}})();
"""
        
        js_path = html_path.replace(".html", ".js")
        Path(js_path).write_text(js_code, encoding="utf-8")
        
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["node", js_path], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        
        # 清理
        for p in [html_path, js_path]:
            try:
                Path(p).unlink()
            except Exception:
                pass
        
        return output.exists() and output.stat().st_size > 0
        
    except Exception:
        return False


def _save_html_fallback(html_content: str, output: Path):
    """截图不可用时，保存为 HTML 文件作为降级。"""
    html_output = output.with_suffix(".html")
    html_output.write_text(html_content, encoding="utf-8")
    _info(f"截图工具不可用，已保存 HTML 降级文件: {html_output}")
    return html_output


def _pil_font(size: int, bold: bool = False):
    """Load a CJK-capable local font for the no-browser fallback."""
    try:
        from PIL import ImageFont
        candidates = [
            r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf" if bold else r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf",
            r"C:\Windows\Fonts\Dengb.ttf" if bold else r"C:\Windows\Fonts\Deng.ttf",
            r"C:\Windows\Fonts\simsunb.ttf" if bold else r"C:\Windows\Fonts\simsun.ttc",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()
    except Exception:
        return None


def _pil_wrap(text: str, max_chars: int) -> str:
    lines = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_chars and char in "，。！？：；、,.!? ":
            lines.append(current.strip())
            current = ""
    if current:
        lines.append(current.strip())
    return "\n".join(lines)


def _split_points(text: str, max_points: int = 4) -> list[str]:
    """把描述/正文拆成 3~4 条认知锚点要点（方案 C）。

    支持按换行、分号、句号拆分，过滤空项与过短碎片；拆不出时回退整句。
    返回值最多 max_points 条，每条 ≤60 字符（超出截断并加省略号）。
    """
    if not text:
        return []
    parts = re.split(r"[\n；;。]+", text)
    points = [p.strip().strip("，,、 ") for p in parts if p and len(p.strip()) >= 6]
    if len(points) < 2:
        return [text.strip()[:60]]
    return [p[:60] + ("…" if len(p) > 60 else "") for p in points[:max_points]]


def _pil_cover(title: str, subtitle: str, brand: str, tag: str, output: Path, width: int = 900, height: int = 383, palette: dict | None = None) -> bool:
    """Generate a real PNG when browser screenshot dependencies are absent."""
    try:
        from PIL import Image, ImageDraw
        p = palette or {
            "background": "#F4F0E8", "surface": "#FFFCF7", "ink": "#333333",
            "muted": "#6B6B6B", "accent": "#B24A2B", "secondary": "#B24A2B",
        }
        image = Image.new("RGB", (width, height), p["background"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((34, 30, width - 34, height - 30), radius=18, fill=p["surface"], outline=p["secondary"], width=2)
        draw.rectangle((34, 30, 48, height - 30), fill=p["accent"])
        draw.text((78, 60), brand or "AI CONTENT MATRIX", font=_pil_font(20, True), fill=p["accent"])
        title_font = _pil_font(36 if len(title) < 20 else 30, True)
        title_text = _pil_wrap(title, 18 if len(title) > 20 else 24)
        draw.multiline_text((78, 122), title_text, font=title_font, fill=p["ink"], spacing=10, align="left")
        draw.line((78, height - 86, 290, height - 86), fill=p["secondary"], width=4)
        draw.text((78, height - 64), subtitle or "可追溯、可复核、可回滚的内容工程", font=_pil_font(17), fill=p["muted"])
        if tag:
            draw.rounded_rectangle((width - 240, 60, width - 78, 100), radius=18, fill=p["background"])
            draw.text((width - 215, 70), tag, font=_pil_font(16, True), fill=p["accent"])
        image.save(output, format="PNG", optimize=True)
        return output.exists() and output.stat().st_size > 0
    except Exception as exc:
        _info(f"Pillow 封面兜底失败: {exc}")
        return False


def _pil_section(title: str, icon: str, description: str, output: Path, width: int = 800, height: int = 500, palette: dict | None = None, kind: str = "anchor", index: int = 1, brand: str = "") -> bool:
    try:
        from PIL import Image, ImageDraw
        p = palette or {
            "background": "#F4F0E8", "surface": "#FFFCF7", "ink": "#333333",
            "muted": "#6B6B6B", "accent": "#B24A2B", "secondary": "#B24A2B",
        }
        kind_zh = {
            "anchor": "认知锚点", "flow": "流程", "architecture": "架构",
            "comparison": "对比", "evidence-strip": "证据条", "checklist": "清单",
        }.get(kind, kind.upper())
        image = Image.new("RGB", (width, height), p["background"])
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((34, 34, width - 34, height - 34), radius=14, fill=p["surface"], outline=p["secondary"], width=2)
        draw.text((70, 62), f"{index:02d}  {kind_zh}", font=_pil_font(17, True), fill=p["accent"])
        draw.text((70, 115), title, font=_pil_font(30 if len(title) < 18 else 24, True), fill=p["ink"])
        draw.line((70, 180, width - 70, 180), fill=p["secondary"], width=3)

        # 方案 C：主体区承载真实内容——要点列表 / 左右双栏，替代孤立圆圈+短线。
        points = _split_points(description or "一张图只承担一个认知动作", max_points=4)
        y = 206
        if kind in {"comparison"} and len(points) >= 2:
            col_w = (width - 140 - 24) // 2
            # 左栏：现状 / 传统
            draw.rounded_rectangle((70, 206, 70 + col_w, 336), radius=10, fill=p["background"], outline=p["muted"], width=2)
            draw.text((84, 218), "传统 / 现状", font=_pil_font(15, True), fill=p["muted"])
            draw.multiline_text((84, 248), _pil_wrap(points[0], 12), font=_pil_font(16), fill=p["ink"], spacing=8)
            # 右栏：优化 / 结论
            rx = 70 + col_w + 24
            draw.rounded_rectangle((rx, 206, rx + col_w, 336), radius=10, fill=p["background"], outline=p["accent"], width=2)
            draw.text((rx + 14, 218), "优化 / 结论", font=_pil_font(15, True), fill=p["accent"])
            draw.multiline_text((rx + 14, 248), _pil_wrap(points[1], 12), font=_pil_font(16), fill=p["ink"], spacing=8)
            if len(points) >= 3:
                draw.text((70, 356), "→ " + points[2], font=_pil_font(15, True), fill=p["accent"])
        else:
            for i, pt in enumerate(points):
                if i > 0:
                    y += 40
                if kind == "checklist":
                    draw.rectangle((70, y + 1, 91, y + 22), outline=p["accent"], width=2)
                    draw.line((77, y + 12, 85, y + 19), fill=p["accent"], width=2)
                    draw.line((85, y + 19, 100, y + 4), fill=p["accent"], width=2)
                elif kind == "evidence-strip":
                    draw.rounded_rectangle((70, y, 104, y + 28), radius=6, fill=p["accent"])
                    draw.text((77, y + 5), f"{i + 1}", font=_pil_font(14, True), fill=p["surface"])
                else:
                    # 朱砂竖条（认知锚点视觉语法）
                    draw.rectangle((72, y + 7, 84, y + 19), fill=p["accent"])
                wrapped = _pil_wrap(pt, 30)
                draw.multiline_text((112, y), wrapped, font=_pil_font(16), fill=p["ink"], spacing=6)
                y += (wrapped.count("\n")) * 24

        # 底部装饰：flow/architecture 保留四节点流程；其余不再画孤立大圆。
        if kind in {"flow", "architecture"}:
            nodes = ["输入", "判断", "执行", "回读"]
            x0, gap = 80, 175
            ny = 378
            for n, label in enumerate(nodes):
                x = x0 + n * gap
                draw.rounded_rectangle((x, ny, x + 110, ny + 48), radius=8, fill=p["background"], outline=p["accent"], width=2)
                draw.text((x + 28, ny + 14), label, font=_pil_font(16, True), fill=p["ink"])
                if n < len(nodes) - 1:
                    draw.line((x + 112, ny + 24, x + gap - 8, ny + 24), fill=p["secondary"], width=3)
        else:
            # 轻量装饰线（不再渲染孤立圆点）
            for n in range(3):
                draw.line((70 + n * 12, height - 92, 70 + n * 12 + 8, height - 92), fill=p["secondary"], width=4)

        if brand:
            draw.text((70, height - 74), str(brand), font=_pil_font(14, True), fill=p["muted"])
        image.save(output, format="PNG", optimize=True)
        return output.exists() and output.stat().st_size > 0
    except Exception as exc:
        _info(f"Pillow 章节图兜底失败: {exc}")
        return False


def generate_cover(
    title: str,
    subtitle: str = "",
    brand: str = "",
    tag: str = "",
    theme: str = "tech-blue",
    width: int = 900,
    height: int = 383,
    output: Path = Path("cover.png"),
):
    """生成封面海报。"""
    _validate_account_theme(theme)
    t = THEMES.get(theme, THEMES["tech-blue"])
    
    title_size = 36 if len(title) <= 15 else (28 if len(title) <= 25 else 22)
    
    tag_html = f'<div class="tag">{tag}</div>' if tag else ""
    
    html = COVER_HTML.format(
        width=width, height=height,
        bg1=t["bg1"], bg2=t["bg2"],
        title_size=title_size,
        brand=brand, title=title, subtitle=subtitle,
        tag_html=tag_html,
    )
    
    output.parent.mkdir(parents=True, exist_ok=True)

    # The light editorial preset is intentionally deterministic and browser
    # independent: use the CJK-safe Pillow renderer first so a machine with a
    # different emoji font cannot silently produce tofu boxes.
    if theme in {"minimal-light", "sentinel-radar", "thinktank-atlas"} and _pil_cover(title, subtitle, brand, tag, output, width, height, palette=t):
        _ok(f"Pillow 封面已生成: {output} ({output.stat().st_size} bytes)")
        return str(output)
    
    ok = _html_to_png_via_chrome(html, width, height, output)
    if not ok:
        ok = _html_to_png_via_puppeteer(html, width, height, output)
    if not ok and _pil_cover(title, subtitle, brand, tag, output, width, height, palette=t):
        _ok(f"Pillow 封面兜底已生成: {output} ({output.stat().st_size} bytes)")
        return str(output)
    if not ok:
        html_path = _save_html_fallback(html, output)
        return str(html_path)
    
    _ok(f"封面海报已生成: {output} ({output.stat().st_size} bytes)")
    return str(output)


def generate_section_card(
    title: str,
    icon: str = "💡",
    description: str = "",
    theme: str = "tech-blue",
    kind: str = "anchor",
    index: int = 1,
    width: int = 800,
    height: int = 500,
    output: Path = Path("section.png"),
    brand: str = "",
):
    """生成章节配图卡片。"""
    raise RuntimeError("正文禁止使用 text_poster；请走当前主题语义确定性渲染器")
    _validate_account_theme(theme)
    t = THEMES.get(theme, THEMES["tech-blue"])
    
    title_size = 32 if len(title) <= 15 else (26 if len(title) <= 25 else 20)
    
    html = SECTION_HTML.format(
        width=width, height=height,
        bg=t["bg1"], card_bg=t["card_bg"],
        text_color=t["text_color"], desc_color=t["desc_color"],
        title_size=title_size,
        icon=icon, title=title, description=description,
    )
    
    output.parent.mkdir(parents=True, exist_ok=True)

    if theme in {"minimal-light", "sentinel-radar", "thinktank-atlas"} and _pil_section(title, icon, description, output, width, height, palette=t, kind=kind, index=index, brand=brand):
        _ok(f"Pillow 章节图已生成: {output} ({output.stat().st_size} bytes)")
        return str(output)
    
    ok = _html_to_png_via_chrome(html, width, height, output)
    if not ok:
        ok = _html_to_png_via_puppeteer(html, width, height, output)
    if not ok and _pil_section(title, icon, description, output, width, height, palette=t, kind=kind, index=index, brand=brand):
        _ok(f"Pillow 章节图兜底已生成: {output} ({output.stat().st_size} bytes)")
        return str(output)
    if not ok:
        html_path = _save_html_fallback(html, output)
        return str(html_path)
    
    _ok(f"章节卡片已生成: {output} ({output.stat().st_size} bytes)")
    return str(output)


def generate_article_posters(article_dir: Path, theme: str = "tech-blue"):
    """按视觉简报生成封面 + 认知锚点图。

    老文章没有 visual-brief.yaml 时保留兼容行为，但新文章会优先读取
    `body_visuals`，避免把每个章节都渲染成同一张文字卡片。
    """
    raise RuntimeError("整篇文章海报降级已禁用；仅允许生成当前文章品牌封面")
    _validate_account_theme(theme)
    md_path = article_dir / "article.md"
    if not md_path.exists():
        md_path = article_dir / "draft.md"
    if not md_path.exists():
        _err(f"找不到文章文件: {article_dir}")
    
    imgs_dir = article_dir / "imgs"
    imgs_dir.mkdir(parents=True, exist_ok=True)
    
    text = md_path.read_text(encoding="utf-8")
    
    # 提取标题
    title = "未命名文章"
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            break
    
    # 生成封面
    cover_path = imgs_dir / "cover.png"
    _info(f"生成封面海报: {title}")
    brand = "AI哨兵 · SIGNAL RADAR" if theme == "sentinel-radar" else "X超玩•未来智能 · ATLAS JOURNAL" if theme == "thinktank-atlas" else "AI CONTENT MATRIX"
    generate_cover(title=title, brand=brand, theme=theme, output=cover_path)
    
    # 提取二级标题作为章节
    sections = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("## ") and not line.startswith("### "):
            sec_title = line[3:].strip()
            # 跳过非内容标题
            if sec_title in ("总结", "参考", "References", "附录"):
                continue
            sections.append(sec_title)

    kinds = ["flow", "comparison", "evidence-strip", "checklist", "anchor", "architecture"]
    brief_path = article_dir / "visual-brief.yaml"
    if brief_path.is_file():
        try:
            import yaml  # type: ignore

            brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}
            planned = brief.get("body_visuals", [])
            if isinstance(planned, list) and planned:
                planned_sections = []
                for item in planned:
                    if not isinstance(item, dict):
                        continue
                    section = str(item.get("section", "")).strip()
                    if section:
                        planned_sections.append((section, str(item.get("kind", "anchor"))))
                if planned_sections:
                    sections = planned_sections
        except (ImportError, OSError, ValueError):
            _info("无法读取 visual-brief.yaml，使用兼容的章节提取模式")
    
    # 为每个章节生成配图
    # Use CJK-font-safe numeric badges in the Pillow fallback; many Windows
    # fonts render emoji as tofu boxes, which is unacceptable in a publishable
    # article image.
    icons = [f"{i:02d}" for i in range(1, 13)]
    for i, item in enumerate(sections):
        if isinstance(item, tuple):
            sec_title, planned_kind = item
        else:
            sec_title, planned_kind = item, kinds[i % len(kinds)]
        icon = icons[i % len(icons)]
        out_path = imgs_dir / f"section-{i+1:02d}.png"
        _info(f"生成章节配图 [{i+1}/{len(sections)}]: {sec_title}")
        generate_section_card(title=sec_title, icon=icon, kind=planned_kind, index=i + 1, theme=theme, output=out_path)
    
    _ok(f"文本海报生成完成：1 封面 + {len(sections)} 张章节配图")


# ── CLI ──

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="文本海报自动生成工具（配图降级方案）")
    sub = parser.add_subparsers(dest="command")
    
    p_cover = sub.add_parser("generate", help="生成封面海报")
    p_cover.add_argument("--title", required=True, help="标题")
    p_cover.add_argument("--subtitle", default="", help="副标题")
    p_cover.add_argument("--brand", default="", help="品牌名")
    p_cover.add_argument("--tag", default="", help="标签")
    p_cover.add_argument("--theme", default="tech-blue", choices=list(THEMES.keys()), help="配色主题")
    p_cover.add_argument("--width", type=int, default=900)
    p_cover.add_argument("--height", type=int, default=383)
    p_cover.add_argument("-o", "--output", default="cover.png", help="输出路径")
    
    p_section = sub.add_parser("section", help="生成章节配图")
    p_section.add_argument("--title", required=True, help="章节标题")
    p_section.add_argument("--icon", default="", help="兼容旧命令的标签；新流程优先使用 --kind")
    p_section.add_argument("--description", default="", help="描述文字")
    p_section.add_argument("--brand", default="", help="公开品牌署名")
    p_section.add_argument("--kind", default="anchor", choices=["anchor", "flow", "architecture", "comparison", "evidence-strip", "checklist"], help="认知锚点类型")
    p_section.add_argument("--index", type=int, default=1, help="视觉编号")
    p_section.add_argument("--theme", default="tech-blue", choices=list(THEMES.keys()))
    p_section.add_argument("--width", type=int, default=800)
    p_section.add_argument("--height", type=int, default=500)
    p_section.add_argument("-o", "--output", default="section.png")
    
    p_article = sub.add_parser("article", help="为整篇文章自动生成全部海报")
    p_article.add_argument("--dir", required=True, help="文章目录（含 article.md 或 draft.md）")
    p_article.add_argument("--theme", default="tech-blue", choices=list(THEMES.keys()))
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "generate":
        generate_cover(
            title=args.title, subtitle=args.subtitle,
            brand=args.brand, tag=args.tag,
            theme=args.theme, width=args.width, height=args.height,
            output=Path(args.output),
        )
    elif args.command == "section":
        generate_section_card(
            title=args.title, icon=args.icon, description=args.description,
            theme=args.theme, kind=args.kind, index=args.index, width=args.width, height=args.height,
            output=Path(args.output), brand=args.brand,
        )
    elif args.command == "article":
        generate_article_posters(Path(args.dir), theme=args.theme)


if __name__ == "__main__":
    main()
