"""Pixel/source integrity checks for article visuals.

Semantic labels and connector geometry cannot detect a renderer/parser defect
that changes a valid SVG into black opaque rectangles.  This gate therefore
checks both the editable source and the final raster delivered to WeChat.
It is deliberately conservative: a large near-black component on a light
technical canvas is a hard failure unless the visual is explicitly a code
surface.  The result is a small JSON-compatible record so semantic QA and
human review can cite the same evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:  # pragma: no cover - source checks still work
    Image = None
    ImageChops = None
    ImageStat = None


ROOT = Path(__file__).resolve().parents[1]
_SVG_TAG_RE = re.compile(r"<svg\b[^>]*>", re.I | re.S)
_ATTR_RE = re.compile(r"\s([:\w-]+)(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?", re.S)
_VAR_USE_RE = re.compile(r"var\(\s*(--[\w-]+)")
_VAR_DEF_RE = re.compile(r"(--[\w-]+)\s*:")
_UNSAFE_MARKUP_RE = re.compile(
    r"<\s*script\b|<\s*foreignObject\b|(?:^|\s)on[a-z]+\s*=|javascript\s*:|"
    r"(?:href|src)\s*=\s*['\"]https?://|@import\s+url\s*\(\s*['\"]?https?://",
    re.I,
)


def _chrome_path() -> Path | None:
    candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("chrome")
    return Path(found) if found else None


def _native_excalidraw_python() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    candidates = (
        root / "skills" / "excalidraw-skill-pack" / "packages" / "renderer-python" / ".venv" / "Scripts" / "python.exe",
        root / "skills" / "excalidraw-skill-pack" / "packages" / "renderer-python" / ".venv" / "bin" / "python",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _unsafe_markup_issues(text: str) -> list[str]:
    return ["unsafe markup or external reference detected"] if _UNSAFE_MARKUP_RE.search(text) else []


def _excalidraw_source_issues(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid Excalidraw JSON: {exc}"]
    errors: list[str] = []
    if value.get("type") != "excalidraw" or value.get("version") != 2:
        errors.append("invalid Excalidraw envelope")
    elements = value.get("elements")
    if not isinstance(elements, list) or not elements:
        errors.append("Excalidraw source has no elements")
    for element in elements if isinstance(elements, list) else []:
        if not isinstance(element, dict):
            errors.append("Excalidraw element is not an object")
            continue
        if element.get("link"):
            errors.append(f"Excalidraw element link is not allowed: {element.get('id')}")
        if element.get("type") == "text" and not str(element.get("text") or "").strip():
            errors.append(f"empty Excalidraw text: {element.get('id')}")
    return errors


def _resolve(article: Path, raw: str) -> Path:
    path = Path(str(raw or ""))
    return path if path.is_absolute() else article / path


def _source_path(article: Path, unit: dict[str, Any]) -> Path | None:
    for key in ("diagram_source", "source_file", "editable_source", "cover_overlay_source"):
        raw = str(unit.get(key) or "").strip()
        if raw:
            path = _resolve(article, raw)
            if path.is_file():
                return path
    return None


def _duplicate_svg_attributes(text: str) -> list[str]:
    errors: list[str] = []
    for index, tag in enumerate(_SVG_TAG_RE.findall(text), 1):
        names = [match.group(1).lower() for match in _ATTR_RE.finditer(tag)]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            errors.append(f"svg[{index}] duplicate attributes: {', '.join(duplicates)}")
    return errors


def _unresolved_css_vars(text: str) -> list[str]:
    uses = set(_VAR_USE_RE.findall(text))
    definitions = set(_VAR_DEF_RE.findall(text))
    return sorted(uses - definitions)


def _corner_is_light(image: Any) -> bool:
    w, h = image.size
    # Avoid browser scrollbars and crop borders at the outermost pixels.
    points = [
        (max(int(w * 0.05), 1), max(int(h * 0.05), 1)),
        (max(int(w * 0.95) - 1, 1), max(int(h * 0.05), 1)),
        (max(int(w * 0.05), 1), max(int(h * 0.90), 1)),
        (max(int(w * 0.95) - 1, 1), max(int(h * 0.90), 1)),
    ]
    values = []
    for x, y in points:
        pixel = image.getpixel((x, y))
        if isinstance(pixel, tuple):
            values.append(sum(pixel[:3]) / 3)
        else:
            values.append(float(pixel))
    return sum(values) / len(values) >= 150


def _dark_components(image: Any, threshold: int = 32) -> list[dict[str, Any]]:
    rgb = image.convert("RGB")
    w, h = rgb.size
    pixels = rgb.load()
    seen: set[tuple[int, int]] = set()
    components: list[dict[str, Any]] = []
    for y in range(h):
        for x in range(w):
            if (x, y) in seen:
                continue
            r, g, b = pixels[x, y]
            if max(r, g, b) > threshold:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            seen.add((x, y))
            points: list[tuple[int, int]] = []
            while queue:
                px, py = queue.popleft()
                points.append((px, py))
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen:
                        continue
                    rr, gg, bb = pixels[nx, ny]
                    if max(rr, gg, bb) <= threshold:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            if len(points) < 100:
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
            box_area = (right - left + 1) * (bottom - top + 1)
            fill_ratio = len(points) / max(box_area, 1)
            if right - left + 1 >= 10 and bottom - top + 1 >= 8 and fill_ratio >= 0.65:
                components.append({
                    "area": len(points),
                    "bbox": [left, top, right, bottom],
                    "fill_ratio": round(fill_ratio, 3),
                })
    return sorted(components, key=lambda item: item["area"], reverse=True)


def _source_raster_equivalence(article: Path, unit: dict[str, Any], source: Path | None, output: Path) -> dict[str, Any]:
    """Re-render the declared source and compare it to the delivered PNG.

    Hashes only prove that a file was recorded.  This check catches a swapped
    raster even when an attacker updates every manifest hash.  Excalidraw
    JSON uses the installed native renderer; SVG/HTML uses the same Chrome
    rasterization path as the article renderer.
    """
    result: dict[str, Any] = {"status": "skipped", "source": str(source or ""), "mean_abs_diff": None}
    if Image is None or ImageChops is None or ImageStat is None or source is None or not source.is_file() or not output.is_file():
        return result
    with tempfile.TemporaryDirectory(prefix="gzh-source-raster-") as temp:
        canonical = Path(temp) / "canonical.png"
        backend = str(unit.get("execution_backend") or unit.get("render_backend") or "").strip().lower()
        # The workflow currently executes Excalidraw as an editable JSON source
        # plus deterministic SVG/Chrome raster.  The optional native renderer is
        # not stable across environments, so it must be explicitly verified before
        # it can become the equivalence oracle; otherwise a visually valid SVG
        # would be rejected merely because a different native renderer produced a
        # different raster.
        native_attempt = (
            source.suffix.lower().endswith("json")
            and backend == "excalidraw"
            and bool(unit.get("native_renderer_verified"))
        )
        if native_attempt:
            renderer = _native_excalidraw_python()
            command = [str(renderer), "-c", "from excalidraw_render.cli import main; raise SystemExit(main())", str(source), "--theme", "default-sketchy", "--output", str(canonical), "--scale", "1", "--width", "1200"] if renderer else []
        else:
            command = []
        if not command:
            # Native renderer may be installed but unable to load its remote
            # module in an offline CI.  The SVG sidecar is the declared
            # deterministic fallback and remains a valid source of truth.
            sidecar_raw = str(unit.get("diagram_source") or "").strip()
            source = _resolve(article, sidecar_raw) if sidecar_raw else source
            chrome = _chrome_path()
            if not chrome:
                result.update({"status": "pending", "reason": "Chrome unavailable"})
                return result
            width, height = 1200, 760
            source_text = source.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'<svg\b[^>]*\bwidth=["\']([0-9.]+)', source_text, re.I)
            height_match = re.search(r'<svg\b[^>]*\bheight=["\']([0-9.]+)', source_text, re.I)
            if match:
                width = max(100, int(float(match.group(1))))
            if height_match:
                height = max(100, int(float(height_match.group(1))))
            if source.suffix.lower() in {".html", ".htm"}:
                # HTML/code cards are captured at their content height by
                # render_visual_anchor.  Reuse only the delivered viewport
                # dimensions (not its pixels) so the canonical rerender uses
                # the same crop and remains a meaningful source↔raster test.
                try:
                    with Image.open(output) as delivered:
                        width, height = delivered.size
                except (OSError, ValueError):
                    pass
            command = [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={width},{height}", f"--screenshot={canonical}", source.as_uri()]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8 if native_attempt else 90)
        except (OSError, subprocess.SubprocessError) as exc:
            if native_attempt:
                proc = subprocess.CompletedProcess(command, 1, "", str(exc))
            else:
                result.update({"status": "failed", "reason": str(exc)})
                return result
        if proc.returncode != 0 or not canonical.is_file():
            if native_attempt:
                sidecar_raw = str(unit.get("diagram_source") or "").strip()
                sidecar = _resolve(article, sidecar_raw) if sidecar_raw else None
                chrome = _chrome_path()
                if sidecar and sidecar.is_file() and chrome:
                    source = sidecar
                    source_text = source.read_text(encoding="utf-8", errors="replace")
                    width, height = 1200, 760
                    match = re.search(r'<svg\b[^>]*\bwidth=["\']([0-9.]+)', source_text, re.I)
                    height_match = re.search(r'<svg\b[^>]*\bheight=["\']([0-9.]+)', source_text, re.I)
                    if match:
                        width = max(100, int(float(match.group(1))))
                    if height_match:
                        height = max(100, int(float(height_match.group(1))))
                    fallback_command = [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={width},{height}", f"--screenshot={canonical}", source.as_uri()]
                    fallback = subprocess.run(fallback_command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
                    proc = fallback
            if proc.returncode != 0 or not canonical.is_file():
                result.update({"status": "failed", "reason": (proc.stderr or proc.stdout or "canonical render failed").strip()[-500:]})
                return result
        try:
            actual = Image.open(output).convert("RGB")
            expected = Image.open(canonical).convert("RGB")
            expected = expected.resize(actual.size)
            diff = ImageChops.difference(actual, expected)
            stat = ImageStat.Stat(diff)
            mean_abs = sum(stat.mean) / len(stat.mean)
            result.update({"status": "passed" if mean_abs <= 12.0 else "failed", "mean_abs_diff": round(mean_abs, 3), "actual_size": list(actual.size), "canonical_size": list(expected.size)})
            if mean_abs > 12.0:
                result["reason"] = "delivered raster differs materially from canonical source render"
        except (OSError, ValueError) as exc:
            result.update({"status": "failed", "reason": str(exc)})
    return result


def check_unit(article: Path, unit: dict[str, Any]) -> dict[str, Any]:
    unit_id = str(unit.get("id") or "unknown")
    visual_type = str(unit.get("visual_type") or unit.get("kind") or "").strip().lower()
    source = _source_path(article, unit)
    output = _resolve(article, str(unit.get("output") or unit.get("asset") or ""))
    source_text = source.read_text(encoding="utf-8", errors="replace") if source else ""
    source_errors = _duplicate_svg_attributes(source_text)
    source_errors.extend(_unsafe_markup_issues(source_text))
    native_source_raw = str(unit.get("excalidraw_source") or "").strip()
    native_source = _resolve(article, native_source_raw) if native_source_raw else None
    if native_source and native_source.is_file():
        source_errors.extend(_excalidraw_source_issues(native_source))
    elif native_source_raw:
        source_errors.append(f"Excalidraw source missing: {native_source_raw}")
    unresolved = _unresolved_css_vars(source_text)
    if unresolved:
        source_errors.append("unresolved CSS variables: " + ", ".join(unresolved))
    # Mermaid also emits a browser screenshot wrapper beside the SVG.  The
    # wrapper is part of the delivery path and must be checked even when the
    # contract points at the editable SVG only.
    wrapper = source.with_suffix(".html") if source and source.suffix.lower() == ".svg" else None
    if wrapper and wrapper.is_file():
        wrapper_text = wrapper.read_text(encoding="utf-8", errors="replace")
        source_errors.extend(f"wrapper: {issue}" for issue in _duplicate_svg_attributes(wrapper_text))
        source_errors.extend(f"wrapper: {issue}" for issue in _unsafe_markup_issues(wrapper_text))
        wrapper_unresolved = _unresolved_css_vars(wrapper_text)
        if wrapper_unresolved:
            source_errors.append("wrapper unresolved CSS variables: " + ", ".join(wrapper_unresolved))
    raster_errors: list[str] = []
    components: list[dict[str, Any]] = []
    # Code cards are no longer exempt from the black-component guard.  A dark
    # code surface is allowed only when the visual contract explicitly opts in
    # with allow_dark_surface=true; the account default is light and should
    # fail closed on opaque black rectangles.
    allow_dark_surface = str(unit.get("allow_dark_surface", "")).strip().lower() == "true"
    inspect_code_surface = visual_type in {"code", "code-block", "code_card"} and not allow_dark_surface
    if Image is not None and output.is_file() and (visual_type not in {"cover"} or inspect_code_surface):
        try:
            image = Image.open(output)
            if _corner_is_light(image):
                components = _dark_components(image, threshold=96 if inspect_code_surface else 32)
                if components:
                    raster_errors.append(
                        "large near-black component(s) on light canvas: "
                        + ", ".join(str(item["bbox"]) for item in components[:5])
                    )
        except (OSError, ValueError) as exc:
            raster_errors.append(f"cannot inspect raster: {exc}")
    elif not output.is_file():
        raster_errors.append("raster output missing")
    native_verified = bool(unit.get("native_renderer_verified"))
    canonical_source = native_source if native_source and native_source.is_file() and native_verified else source
    enforce_equivalence = bool(unit.get("source_raster_required")) or bool(native_source_raw) or (
        unit_id == "cover" and bool(str(unit.get("cover_overlay_source") or "").strip())
    )
    equivalence = _source_raster_equivalence(article, unit, canonical_source, output) if enforce_equivalence else {"status": "skipped", "source": str(canonical_source or ""), "mean_abs_diff": None, "reason": "contract did not opt into source-raster gate"}
    if equivalence.get("status") == "failed":
        raster_errors.append(f"source-to-raster equivalence failed: {equivalence.get('reason') or equivalence.get('mean_abs_diff')}")
    return {
        "id": unit_id,
        "source": str(source.relative_to(article)).replace("\\", "/") if source else "",
        "output": str(output.relative_to(article)).replace("\\", "/") if output.is_absolute() and output.is_relative_to(article) else str(output),
        "source_errors": source_errors,
        "raster_errors": raster_errors,
        "detected_regions": components,
        "source_raster_equivalence": equivalence,
        "status": "failed" if source_errors or raster_errors else "passed",
    }


def check_article(article: Path, units: list[dict[str, Any]]) -> dict[str, Any]:
    article = article.resolve()
    records = [check_unit(article, unit) for unit in units]
    errors = [f"{record['id']}: {issue}" for record in records for issue in (record["source_errors"] + record["raster_errors"])]
    return {"status": "failed" if errors else "passed", "errors": errors, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SVG source and raster artifact integrity")
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    contract_path = args.article / "visual-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.is_file() else {}
    units = contract.get("units", []) if isinstance(contract, dict) else []
    result = check_article(args.article, units if isinstance(units, list) else [])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
