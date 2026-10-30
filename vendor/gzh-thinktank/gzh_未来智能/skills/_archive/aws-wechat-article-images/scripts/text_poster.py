#!/usr/bin/env python3
"""
文本海报自动生成工具 — 配图失败时的降级方案

当 image_create.py 和 Agent 生图都失败时，用纯 HTML+CSS 生成简洁的文字卡片，
确保文章始终有封面和配图可用。

用法（仓库根执行）：
    python {baseDir}/scripts/text_poster.py generate --title "文章标题" --subtitle "副标题" -o cover.png
    python {baseDir}/scripts/text_poster.py article --dir drafts/20260609-slug/
    python {baseDir}/scripts/text_poster.py section --title "章节标题" --icon "💡" -o imgs/section-01.png

退出码：
    0  成功
    1  失败
"""

from __future__ import annotations

import argparse
import base64
import json
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
}


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
                result = subprocess.run(["where", "chrome"], capture_output=True, text=True, timeout=5)
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
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
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
        result = subprocess.run(["node", js_path], capture_output=True, text=True, timeout=30)
        
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


def generate_cover(
    title: str,
    subtitle: str = "",
    brand: str = "",
    tag: str = "",
    theme: str = "tech-blue",
    width: int = 900,
    height: int = 500,
    output: Path = Path("cover.png"),
):
    """生成封面海报。"""
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
    
    ok = _html_to_png_via_chrome(html, width, height, output)
    if not ok:
        ok = _html_to_png_via_puppeteer(html, width, height, output)
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
    width: int = 800,
    height: int = 500,
    output: Path = Path("section.png"),
):
    """生成章节配图卡片。"""
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
    
    ok = _html_to_png_via_chrome(html, width, height, output)
    if not ok:
        ok = _html_to_png_via_puppeteer(html, width, height, output)
    if not ok:
        html_path = _save_html_fallback(html, output)
        return str(html_path)
    
    _ok(f"章节卡片已生成: {output} ({output.stat().st_size} bytes)")
    return str(output)


def generate_article_posters(article_dir: Path, theme: str = "tech-blue"):
    """为整篇文章生成封面 + 所有章节配图（从 article.md 中提取章节标题）。"""
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
    generate_cover(title=title, theme=theme, output=cover_path)
    
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
    
    # 为每个章节生成配图
    icons = ["📌", "💡", "🔑", "⚡", "🎯", "🚀", "🔧", "📊", "🌟", "💬", "🎨", "📱"]
    for i, sec_title in enumerate(sections):
        icon = icons[i % len(icons)]
        out_path = imgs_dir / f"section-{i+1:02d}.png"
        _info(f"生成章节配图 [{i+1}/{len(sections)}]: {sec_title}")
        generate_section_card(title=sec_title, icon=icon, theme=theme, output=out_path)
    
    _ok(f"文本海报生成完成：1 封面 + {len(sections)} 张章节配图")


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="文本海报自动生成工具（配图降级方案）")
    sub = parser.add_subparsers(dest="command")
    
    p_cover = sub.add_parser("generate", help="生成封面海报")
    p_cover.add_argument("--title", required=True, help="标题")
    p_cover.add_argument("--subtitle", default="", help="副标题")
    p_cover.add_argument("--brand", default="", help="品牌名")
    p_cover.add_argument("--tag", default="", help="标签")
    p_cover.add_argument("--theme", default="tech-blue", choices=list(THEMES.keys()), help="配色主题")
    p_cover.add_argument("--width", type=int, default=900)
    p_cover.add_argument("--height", type=int, default=500)
    p_cover.add_argument("-o", "--output", default="cover.png", help="输出路径")
    
    p_section = sub.add_parser("section", help="生成章节配图")
    p_section.add_argument("--title", required=True, help="章节标题")
    p_section.add_argument("--icon", default="💡", help="图标 emoji")
    p_section.add_argument("--description", default="", help="描述文字")
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
            theme=args.theme, width=args.width, height=args.height,
            output=Path(args.output),
        )
    elif args.command == "article":
        generate_article_posters(Path(args.dir), theme=args.theme)


if __name__ == "__main__":
    main()