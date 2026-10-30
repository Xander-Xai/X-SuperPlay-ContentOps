#!/usr/bin/env python3
"""Check an SVG against the conservative WeChat paste profile.

The main visual contracts intentionally allow machine-readable metadata and
editable SVG sources.  A direct paste into the WeChat editor is stricter: the
editor may discard IDs, CSS classes, defs/markers, scripts, event handlers,
foreignObject, external URLs, and percentage sizing.  This checker is an
optional delivery-profile gate for that boundary; it is not a replacement for
visual semantic, geometry, aesthetic, or source-to-raster QA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_URL_RE = re.compile(r"(?:https?:|//)", re.I)
EVENT_ATTR_RE = re.compile(r"^on[a-z]+$", re.I)
URL_FRAGMENT_RE = re.compile(r"url\(\s*#", re.I)
PERCENT_RE = re.compile(r"%")
ANIMATION_TAGS = {"animate", "set", "animateTransform", "animateMotion"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_has_static_fallback(path: Path) -> bool:
    """A conservative fallback check for an accompanying HTML file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    visible = re.sub(r"<[^>]+>", " ", text)
    return bool(re.search(r"\S", visible))


def check(path: Path, *, profile: str = "wechat-paste", fallback: Path | None = None,
          require_static_fallback: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    path = path.resolve()
    result: dict[str, Any] = {
        "contract": "wechat-svg-compatibility-v1",
        "profile": profile,
        "input": str(path),
        "input_sha256": _sha256(path) if path.is_file() else "",
        "status": "failed",
        "errors": errors,
        "warnings": warnings,
    }
    if profile != "wechat-paste":
        errors.append(f"unsupported profile: {profile}")
        return result
    if not path.is_file():
        errors.append("input SVG not found")
        return result
    if path.suffix.lower() != ".svg":
        errors.append("input must be an .svg file")
        return result
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
        root = ET.fromstring(text)
    except (OSError, UnicodeError, ET.ParseError) as exc:
        errors.append(f"invalid SVG/XML: {exc}")
        return result

    if _local(root.tag) != "svg":
        errors.append("root element must be <svg>")
    attrs = {str(k).rsplit("}", 1)[-1]: str(v) for k, v in root.attrib.items()}
    for attr in ("width", "height", "viewBox"):
        if not attrs.get(attr):
            errors.append(f"root svg missing {attr}")
    for attr in ("width", "height"):
        value = attrs.get(attr, "")
        if PERCENT_RE.search(value) or value.strip().lower() in {"auto", "100%"}:
            errors.append(f"root svg {attr} must use explicit pixels, got {value!r}")
    if attrs.get("viewBox"):
        try:
            parts = [float(x) for x in re.split(r"[ ,]+", attrs["viewBox"].strip())]
            if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
                raise ValueError
        except ValueError:
            errors.append("root svg viewBox must contain four positive numeric values")

    tags: dict[str, int] = {}
    for element in root.iter():
        tag = _local(element.tag)
        tags[tag] = tags.get(tag, 0) + 1
        if tag in {"script", "foreignObject", "embed", "object", "iframe"}:
            errors.append(f"forbidden element <{tag}>")
        if tag == "defs":
            errors.append("<defs> is not allowed in wechat-paste profile")
        if tag in {"marker", "pattern", "filter", "linearGradient", "radialGradient", "clipPath", "mask"}:
            warnings.append(f"advanced SVG element <{tag}> may be stripped by the editor")
        if tag not in {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "image", "title", "desc", "metadata", *ANIMATION_TAGS}:
            warnings.append(f"unrecognized SVG element <{tag}>")
        for raw_name, raw_value in element.attrib.items():
            name = raw_name.rsplit("}", 1)[-1]
            value = str(raw_value)
            # The deterministic renderer stores a machine-readable geometry
            # contract in one metadata node.  Its id is not referenced by any
            # drawing element and may safely be stripped by the editor; treat
            # it as a compatibility warning rather than blocking the source.
            if name.lower() == "id" and tag == "metadata":
                warnings.append("metadata id may be stripped by the editor; it is not a rendering dependency")
                continue
            if name.lower() in {"id", "class"}:
                errors.append(f"attribute {name!r} is not allowed on <{tag}>")
            if EVENT_ATTR_RE.match(name):
                errors.append(f"event handler {name!r} is not allowed")
            if name in {"href", "xlink:href", "src"}:
                errors.append(f"external/resource reference attribute {name!r} is not allowed")
            if EXTERNAL_URL_RE.search(value) or URL_FRAGMENT_RE.search(value):
                errors.append(f"external or fragment URL reference is not allowed: {value[:120]!r}")
            if name in {"width", "height", "x", "y"} and PERCENT_RE.search(value):
                errors.append(f"percentage geometry is not allowed: {name}={value!r}")
            if name in {"marker-start", "marker-mid", "marker-end"}:
                errors.append(f"marker dependency is not allowed: {name}")
        if tag in {"animate", "set", "animateTransform", "animateMotion"}:
            attribute_name = element.attrib.get("attributeName", "")
            if not attribute_name:
                errors.append(f"animation <{tag}> missing attributeName")
            if tag == "set" and attribute_name not in {"visibility", "opacity"}:
                warnings.append(f"set animation targets {attribute_name!r}; verify editor support")

    if not any(_local(child.tag) == "text" for child in root.iter()):
        warnings.append("SVG contains no <text>; verify that the HTML fallback carries all labels")
    if fallback:
        result["static_fallback"] = str(fallback.resolve())
        if not fallback.is_file() or not _text_has_static_fallback(fallback):
            errors.append("static fallback HTML is missing or has no visible text")
    elif require_static_fallback:
        errors.append("--require-static-fallback needs --fallback-html")
    else:
        warnings.append("no static fallback HTML supplied; profile check covers SVG only")

    result["tag_counts"] = tags
    result["status"] = "passed" if not errors else "failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--profile", choices=("wechat-paste",), default="wechat-paste")
    parser.add_argument("--fallback-html", type=Path)
    parser.add_argument("--require-static-fallback", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.input, profile=args.profile, fallback=args.fallback_html,
                   require_static_fallback=args.require_static_fallback)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
