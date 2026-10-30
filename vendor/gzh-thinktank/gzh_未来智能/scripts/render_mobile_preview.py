#!/usr/bin/env python3
"""Render a real mobile screenshot of article_预览.html with headless Chrome/Edge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_url(raw: str) -> str:
    """Keep host/path for diagnostics while dropping query/fragment secrets."""
    parsed = urlsplit(raw)
    if parsed.scheme in {"http", "https", "file"}:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return raw.split("?", 1)[0].split("#", 1)[0]


def _dom_checks(dom: str) -> dict[str, object]:
    text = re.sub(r"<script\b[^>]*>.*?</script\s*>", " ", dom, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style\s*>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    title_match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", dom, flags=re.I | re.S)
    title_present = bool(title_match and re.sub(r"<[^>]+>", "", title_match.group(1)).strip())
    image_count = len(re.findall(r"<img\b", dom, flags=re.I))
    # A prose explanation may legitimately mention the word “placeholder”;
    # only unresolved image sources are blocking.
    placeholder_count = len(re.findall(r"(?:src|data-src)\s*=\s*[\"']?placeholder(?:[\"'\s>]|$)", dom, flags=re.I))
    heading_count = len(re.findall(r"<h[1-3]\b", dom, flags=re.I))
    horizontal_overflow = re.search(r'data-gzh-horizontal-overflow=["\']1["\']', dom, flags=re.I) is not None
    image_overflow = re.search(r'data-gzh-image-overflow=["\']1["\']', dom, flags=re.I) is not None
    checks: dict[str, object] = {
        "status": "passed" if title_present and len(text) >= 80 and image_count >= 1 and placeholder_count == 0 and not horizontal_overflow and not image_overflow else "blocked",
        "title_present": title_present,
        "body_text_chars": len(text),
        "image_count": image_count,
        "heading_count": heading_count,
        "placeholder_count": placeholder_count,
        "horizontal_overflow": horizontal_overflow,
        "image_overflow": image_overflow,
    }
    return checks


def _dump_dom(executable: Path, target_url: str) -> tuple[str, str]:
    common = [
        str(executable),
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--allow-file-access-from-files",
        "--virtual-time-budget=1500",
        "--dump-dom",
        target_url,
    ]
    attempts = [common, [str(executable), *common[1:-1], target_url]]
    last_error = ""
    for command in attempts:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout, ""
        last_error = (result.stderr or result.stdout or "浏览器没有返回 DOM").strip()[-1000:]
    return "", last_error


def find_browser(explicit: str | None = None) -> Path | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("CHROME_BIN"):
        candidates.append(os.environ["CHROME_BIN"])
    candidates.extend(
        [
            "chrome",
            "msedge",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    )
    for candidate in candidates:
        resolved = shutil.which(candidate) or candidate
        path = Path(resolved)
        if path.is_file():
            return path.resolve()
    return None


def render(article_dir: Path, width: int, height: int, browser: str | None, editor_url: str | None = None) -> int:
    preview = article_dir / "article_预览.html"
    screenshot = article_dir / "preview_screenshot.png"
    fullpage = article_dir / "preview-fullpage.png"
    slices_dir = article_dir / "preview-slices"
    capture = article_dir / "preview-capture.json"
    if not preview.is_file() or preview.stat().st_size < 500:
        print("MOBILE PREVIEW BLOCKED: 缺少 article_预览.html 或文件过短", file=sys.stderr)
        return 1
    if width != 390:
        print("MOBILE PREVIEW BLOCKED: width 必须固定为 390", file=sys.stderr)
        return 1
    executable = find_browser(browser)
    if executable is None:
        print(
            "MOBILE PREVIEW BLOCKED: 未找到 Chrome/Edge；禁止用合成图片冒充浏览器截图。",
            file=sys.stderr,
        )
        return 1
    url = editor_url.strip() if editor_url and editor_url.strip() else preview.resolve().as_uri()
    common = [
        str(executable),
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--disable-extensions",
        "--disable-background-networking",
        "--allow-file-access-from-files",
        f"--window-size={width},{height}",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1500",
        f"--screenshot={screenshot}",
        url,
    ]
    attempts = [common[:1] + ["--headless=new"] + common[2:], common]
    last_error = ""
    for command in attempts:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
            continue
        if result.returncode == 0 and screenshot.is_file() and screenshot.stat().st_size > 1024:
            break
        last_error = (result.stderr or result.stdout or "浏览器没有生成截图").strip()[-1000:]
    else:
        print(f"MOBILE PREVIEW BLOCKED: 浏览器截图失败：{last_error}", file=sys.stderr)
        return 1

    # Chrome/Edge headless has no Playwright dependency in this workspace.  A
    # second, tall viewport captures the rendered document in one image when
    # the page is shorter than the safety cap; the image is then split into
    # 390×844 scroll slices so below-fold defects cannot hide behind a first
    # viewport-only receipt.
    full_height = 12000
    full_common = [
        str(executable),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--disable-extensions",
        "--disable-background-networking",
        "--allow-file-access-from-files",
        f"--window-size={width},{full_height}",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1500",
        f"--screenshot={fullpage}",
        url,
    ]
    full_attempts = [full_common, [str(executable), "--headless", *full_common[2:]]]
    full_error = ""
    for command in full_attempts:
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            full_error = str(exc)
            continue
        if result.returncode == 0 and fullpage.is_file() and fullpage.stat().st_size > 1024:
            break
        full_error = (result.stderr or result.stdout or "浏览器没有生成 full-page 截图").strip()[-1000:]
    else:
        print(f"MOBILE PREVIEW BLOCKED: full-page 截图失败：{full_error}", file=sys.stderr)
        return 1

    try:
        from PIL import Image

        with Image.open(screenshot) as image:
            actual_width, actual_height = image.size
        with Image.open(fullpage) as image:
            full_width, full_height_actual = image.size
            if full_width != width or full_height_actual < actual_height:
                raise ValueError(f"full-page 尺寸为 {full_width}x{full_height_actual}")
            # Trim the tall viewport's trailing blank area.  Chrome cannot
            # query scrollHeight without a driver, but the rendered tail is
            # visually uniform; keeping only rows with foreground variation
            # prevents dozens of meaningless blank slices.
            bg = image.getpixel((0, full_height_actual - 1))
            content_bottom = full_height_actual
            for y in range(full_height_actual - 1, actual_height - 1, -1):
                row = [image.getpixel((x, y)) for x in range(0, width, max(1, width // 40))]
                changed = sum(1 for pixel in row if sum(abs(int(pixel[i]) - int(bg[i])) for i in range(3)) > 18)
                if changed >= max(2, len(row) // 20):
                    content_bottom = min(full_height_actual, y + 2)
                    break
            if content_bottom < full_height_actual:
                trimmed = image.crop((0, 0, width, content_bottom))
                trimmed.save(fullpage, format="PNG")
                image = trimmed
                full_height_actual = content_bottom
            slices_dir.mkdir(parents=True, exist_ok=True)
            # Remove stale slices only inside this article-owned directory.
            for old in slices_dir.glob("segment-*.png"):
                old.unlink()
            slice_records = []
            segment_height = height
            for index, top in enumerate(range(0, full_height_actual, segment_height), 1):
                bottom = min(top + segment_height, full_height_actual)
                crop = image.crop((0, top, width, bottom))
                target = slices_dir / f"segment-{index:03d}.png"
                crop.save(target, format="PNG")
                slice_records.append({"path": f"preview-slices/{target.name}", "top": top, "bottom": bottom, "sha256": sha256_file(target)})
    except (ImportError, OSError) as exc:
        print(f"MOBILE PREVIEW BLOCKED: 无法读取截图尺寸：{exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"MOBILE PREVIEW BLOCKED: {exc}", file=sys.stderr)
        return 1
    if actual_width != width or actual_height < 300:
        print(f"MOBILE PREVIEW BLOCKED: 截图尺寸为 {actual_width}x{actual_height}", file=sys.stderr)
        return 1
    dom, dom_error = _dump_dom(executable, url)
    if not dom:
        print(f"MOBILE PREVIEW BLOCKED: 浏览器 DOM 检查失败：{dom_error}", file=sys.stderr)
        return 1
    dom_check = _dom_checks(dom)
    if dom_check.get("status") != "passed":
        print(f"MOBILE PREVIEW BLOCKED: DOM 运行时检查未通过：{dom_check}", file=sys.stderr)
        return 1
    payload = {
        "schema_version": 1,
        "status": "passed",
        "renderer": "chrome-headless" if "chrome" in executable.name.lower() else "edge-headless",
        "browser": executable.name,
        "target_kind": "wechat_editor" if editor_url and editor_url.strip() else "local_preview",
        # A9（对抗审查）：回执不得保存本机绝对路径/完整 URL（file:///D:/... 会
        # 泄漏工作区结构）。只保留相对资源标识与内容哈希；本机路径仅在终端日志。
        "target_url": "",
        "target_uri_id": "local_preview:article_预览.html",
        "source": "article_预览.html",
        "source_sha256": sha256_file(preview),
        "viewport": {"width": width, "height": height},
        "screenshot": "preview_screenshot.png",
        "screenshot_sha256": sha256_file(screenshot),
        "fullpage_screenshot": "preview-fullpage.png",
        "fullpage_screenshot_sha256": sha256_file(fullpage),
        "fullpage_capture_mode": "tall-browser-viewport",
        "scroll_slices": slice_records,
        "scroll_slice_height": height,
        "scroll_slice_count": len(slice_records),
        "dom_sha256": hashlib.sha256(dom.encode("utf-8", errors="replace")).hexdigest(),
        "dom_check": dom_check,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    capture.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MOBILE PREVIEW CAPTURED: {screenshot} ({actual_width}x{actual_height})")
    print(f"CAPTURE RECEIPT: {capture}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--width", type=int, default=390)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--browser")
    parser.add_argument("--editor-url", help="可选：已登录的公众号编辑器预览地址；回执会移除查询参数")
    args = parser.parse_args()
    article_dir = args.article.expanduser()
    if not article_dir.is_absolute():
        article_dir = ROOT / article_dir
    return render(article_dir.resolve(), args.width, args.height, args.browser, args.editor_url)


if __name__ == "__main__":
    raise SystemExit(main())
