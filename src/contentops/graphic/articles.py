"""WeChat Official Account (GZH) article orchestrator.

What this module owns
---------------------
It binds article inputs, HTML validation, image verification, and local preview
wrapping into one verifiable step. It writes ``receipts/gzh-article.json``, which
binds the article HTML SHA-256, referenced images, source references, upstream
validation results, and operational blockers.

What it does NOT do
-------------------
It contains no browser automation, no HTML rendering engine, no agent loop,
and no platform publisher. It never contacts WeChat API endpoints, stores no
account credentials, and records measurements and gates only — never approval.
A validation PASS leaves ``production_ready: false`` and
``publish_authorized: false``; human editorial and founder review remain mandatory.

Upstream reuse
--------------
Reuses ``gzh-design`` tools from the pinned Easel runtime (.runtime/easel/skills/openclaw/gzh-design):
- ``validate_gzh_html.py``: checks forbidden tags, inline styles, and <span leaf=""> wrapping
- ``wrap_preview.py``: wraps verified section HTML into browser preview with copy button
- ``component_lint.py``: scans component source references for anti-patterns

License note: ``gzh-design`` is licensed under GNU AGPL-3.0 (Copyright 2026 甲木 × 摸鱼小李).
This module invokes the upstream tools via process execution and does not redistribute
derivative code within contentops.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import unquote

INPUT_SCHEMA = "contentops.gzh-article-input/v1"
RECEIPT_SCHEMA = "contentops.gzh-article/v1"

_IMG_SRC_PATTERN = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\'](.*?)["\']', re.IGNORECASE)
_SPAN_LEAF_PATTERN = re.compile(r"span leaf 包裹:\s*(\d+)\s*处")
_ERROR_BLOCK_PATTERN = re.compile(r"❌ ERROR[^\n]*:\n((?:\s+•[^\n]+\n?)+)")
_WARN_BLOCK_PATTERN = re.compile(r"⚠️\s+WARNING[^\n]*:\n((?:\s+•[^\n]+\n?)+)")


class ArticleError(ValueError):
    """Raised when an article plan, validation, or tool execution fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ArticleTools:
    """Paths to the upstream gzh-design helper scripts."""

    validator: Path
    wrapper: Path
    linter: Path
    upstream_root: Path

    @classmethod
    def resolve(cls, runtime_root: Optional[Path] = None) -> "ArticleTools":
        base = runtime_root or (Path(__file__).resolve().parents[3] / ".runtime" / "easel")
        gzh_dir = base / "skills" / "openclaw" / "gzh-design"
        scripts_dir = gzh_dir / "scripts"

        validator = scripts_dir / "validate_gzh_html.py"
        wrapper = scripts_dir / "wrap_preview.py"
        linter = scripts_dir / "component_lint.py"

        missing = [p.name for p in (validator, wrapper, linter) if not p.is_file()]
        if missing:
            raise ArticleError(
                "ARTICLE_UPSTREAM_TOOL_MISSING",
                f"missing upstream tools under {scripts_dir}: {', '.join(missing)}; "
                "verify runtime/easel.lock.json and .runtime/easel checkout",
            )
        return cls(
            validator=validator,
            wrapper=wrapper,
            linter=linter,
            upstream_root=gzh_dir,
        )


@dataclass
class ArticlePlan:
    """Resolved inputs for article validation and preview."""

    project: Path
    html: Path
    preview_out: Path
    tools: ArticleTools
    title: str = "未命名文章"
    digest: str = ""
    theme: str = "graphite-minimal"
    sources: List[str] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    cover: Optional[Dict[str, Any]] = None
    input_file: Optional[Path] = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def parse_validator_output(text: str) -> Dict[str, Any]:
    """Parse text emitted by validate_gzh_html.py into structured metrics."""
    errors: List[str] = []
    warnings: List[str] = []
    leaf_count = 0

    leaf_match = _SPAN_LEAF_PATTERN.search(text)
    if leaf_match:
        try:
            leaf_count = int(leaf_match.group(1))
        except ValueError:
            leaf_count = 0

    err_match = _ERROR_BLOCK_PATTERN.search(text)
    if err_match:
        for line in err_match.group(1).splitlines():
            line = line.strip()
            if line.startswith("•"):
                errors.append(line.lstrip("•").strip())

    warn_match = _WARN_BLOCK_PATTERN.search(text)
    if warn_match:
        for line in warn_match.group(1).splitlines():
            line = line.strip()
            if line.startswith("•"):
                warnings.append(line.lstrip("•").strip())

    return {
        "span_leaf_count": leaf_count,
        "errors": errors,
        "warnings": warnings,
        "raw_output": text.strip(),
    }


def plan(
    project_dir: Path | str,
    *,
    html_path: Optional[Path | str] = None,
    preview_path: Optional[Path | str] = None,
    input_file: Optional[Path | str] = None,
    runtime_root: Optional[Path] = None,
    title: Optional[str] = None,
    digest: Optional[str] = None,
    theme: Optional[str] = None,
    sources: Optional[Sequence[str]] = None,
) -> ArticlePlan:
    """Validate project layout, verify HTML & referenced images, and assemble plan."""
    project = Path(project_dir).resolve()
    if not project.is_dir():
        raise ArticleError("PROJECT_MISSING", f"project directory does not exist: {project}")

    tools = ArticleTools.resolve(runtime_root)

    # Resolve input JSON if present or specified
    candidate_input = Path(input_file).resolve() if input_file else (project / "article-input.json")
    input_data: Dict[str, Any] = {}
    if candidate_input.exists() and not candidate_input.is_file():
        raise ArticleError("ARTICLE_INPUT_INVALID", f"input path is not a file: {candidate_input}")
    if candidate_input.is_file():
        if not _is_relative_to(candidate_input, project):
            raise ArticleError(
                "PATH_TRAVERSAL",
                f"input file {candidate_input} is outside project {project}",
            )
        try:
            input_data = json.loads(candidate_input.read_text(encoding="utf-8"))
        except Exception as e:
            raise ArticleError("ARTICLE_INPUT_INVALID", f"failed to parse JSON from {candidate_input}: {e}")
        if not isinstance(input_data, dict):
            raise ArticleError("ARTICLE_INPUT_INVALID", "input JSON root must be an object")
        input_schema = input_data.get("schema")
        if input_schema != INPUT_SCHEMA:
            raise ArticleError(
                "ARTICLE_INPUT_SCHEMA_MISMATCH",
                f"expected {INPUT_SCHEMA}, got {input_schema!r}; legacy card receipts cannot be used as article input",
            )

    # Determine HTML target
    if html_path:
        html = Path(html_path)
        if not html.is_absolute():
            html = (project / html).resolve()
    elif input_data.get("html"):
        html = (project / input_data["html"]).resolve()
    else:
        html = (project / "assets" / "article" / "article.html").resolve()

    if not _is_relative_to(html, project):
        raise ArticleError(
            "ARTICLE_HTML_OUTSIDE_PROJECT",
            f"HTML file {html} is outside project boundary {project}",
        )
    if not html.is_file():
        raise ArticleError("ARTICLE_HTML_MISSING", f"article HTML does not exist: {html}")

    html_bytes = html.read_bytes()
    if not html_bytes.strip():
        raise ArticleError("ARTICLE_EMPTY", f"article HTML file is empty: {html}")

    html_text = html_bytes.decode("utf-8", errors="replace")
    if not re.search(r"<section\b", html_text, re.IGNORECASE):
        raise ArticleError("ARTICLE_COMPONENT_INVALID", "article must contain at least one section component")
    if re.search(r"<\s*(script|iframe|object|embed)\b", html_text, re.IGNORECASE):
        raise ArticleError("ARTICLE_COMPONENT_INVALID", "active or embedded content is not allowed")

    # Determine preview output target
    if preview_path:
        preview = Path(preview_path)
        if not preview.is_absolute():
            preview = (project / preview).resolve()
    else:
        preview = html.with_name(f"{html.stem}_preview.html")

    if not _is_relative_to(preview, project):
        raise ArticleError(
            "PATH_TRAVERSAL",
            f"preview output {preview} is outside project boundary {project}",
        )
    if preview.resolve() == html.resolve():
        raise ArticleError("ARTICLE_PREVIEW_OVERWRITES_HTML", "preview output cannot overwrite the article HTML")

    # Scan and verify referenced images
    found_images: List[Dict[str, Any]] = []
    seen_paths = set()
    for m in _IMG_SRC_PATTERN.finditer(html_text):
        src = m.group(1).strip()
        if src.startswith(("http://", "https://", "//")):
            raise ArticleError(
                "ARTICLE_IMAGE_UNAUTHORIZED",
                f"remote image source requires separate rights review: {src[:120]}",
            )
        if src.startswith("data:"):
            # The upstream preview wrapper inlines local images. Permit only a
            # data URI whose digest exactly matches an already verified local
            # image; arbitrary embedded payloads remain blocked.
            if not re.match(r"^data:image/(png|jpeg|gif|webp);base64,", src, re.IGNORECASE):
                raise ArticleError("ARTICLE_IMAGE_UNAUTHORIZED", "unsupported or non-image data URI")
            encoded = src.split(",", 1)[1]
            try:
                embedded = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ArticleError("ARTICLE_IMAGE_UNAUTHORIZED", "malformed image data URI") from exc
            embedded_hash = hashlib.sha256(embedded).hexdigest()
            # Compare against the images verified so far in THIS scan
            # (found_images), not a plan attribute: `plan()` has not built the
            # ArticlePlan yet, so referencing `p.images` here was a guaranteed
            # NameError on any HTML containing a data-URI image.
            if not any(item["sha256"] == embedded_hash for item in found_images):
                raise ArticleError("ARTICLE_IMAGE_UNAUTHORIZED", "embedded image bytes do not match a verified local image")
            continue
        clean_src = unquote(src.split("?", 1)[0].split("#", 1)[0])
        img_path = Path(clean_src) if os.path.isabs(clean_src) else (html.parent / clean_src).resolve()

        if not _is_relative_to(img_path, project):
            raise ArticleError(
                "ARTICLE_IMAGE_OUTSIDE_PROJECT",
                f"image {src} resolves to {img_path} which is outside project boundary {project}",
            )
        if not img_path.is_file():
            raise ArticleError(
                "ARTICLE_IMAGE_MISSING",
                f"referenced image file is missing: {img_path} (from src '{src}')",
            )

        if img_path not in seen_paths:
            seen_paths.add(img_path)
            found_images.append({
                "path": "project://" + img_path.relative_to(project).as_posix(),
                "sha256": _sha256(img_path),
                "bytes": img_path.stat().st_size,
            })

    # Merge metadata
    article_title = title or input_data.get("title") or "未命名文章"
    article_digest = digest or input_data.get("digest") or input_data.get("summary") or ""
    article_theme = theme or input_data.get("theme") or "graphite-minimal"
    if len(article_title.strip()) > 64:
        raise ArticleError("ARTICLE_TITLE_INVALID", "title must be 64 characters or fewer")
    if len(article_digest.strip()) > 200:
        raise ArticleError("ARTICLE_DIGEST_INVALID", "digest must be 200 characters or fewer")
    if not isinstance(article_theme, str) or not article_theme.strip():
        raise ArticleError("ARTICLE_THEME_INVALID", "theme must be a non-empty string")
    raw_sources = sources if sources is not None else input_data.get("sources", [])
    if not isinstance(raw_sources, list) or not all(isinstance(s, str) and s.strip() for s in raw_sources):
        raise ArticleError("ARTICLE_SOURCES_INVALID", "sources must be a list of non-empty strings")
    article_sources = list(raw_sources)

    cover_data = input_data.get("cover")
    if cover_data:
        if not isinstance(cover_data, dict) or not isinstance(cover_data.get("path"), str):
            raise ArticleError("ARTICLE_COVER_INVALID", "cover must have a string path")
        cover_path = Path(cover_data["path"])
        cover_path = cover_path if cover_path.is_absolute() else (project / cover_path).resolve()
        if not _is_relative_to(cover_path, project):
            raise ArticleError("ARTICLE_COVER_OUTSIDE_PROJECT", f"cover resolves outside project: {cover_path}")
        if not cover_path.is_file():
            raise ArticleError("ARTICLE_COVER_MISSING", f"cover image missing: {cover_path}")
        cover_data = {
            **cover_data,
            "path": "project://" + cover_path.relative_to(project).as_posix(),
            "sha256": _sha256(cover_path),
            "bytes": cover_path.stat().st_size,
        }

    return ArticlePlan(
        project=project,
        html=html,
        preview_out=preview,
        tools=tools,
        title=article_title,
        digest=article_digest,
        theme=article_theme,
        sources=article_sources,
        images=found_images,
        cover=cover_data,
        input_file=candidate_input if candidate_input.is_file() else None,
    )


def run(
    p: ArticlePlan,
    *,
    runner: Callable[..., Any],
    article_python: str = sys.executable,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Execute upstream validate_gzh_html and wrap_preview, then build receipt."""
    # 1. Run validator
    validator_argv = [article_python, str(p.tools.validator), str(p.html)]
    try:
        val_res = runner(validator_argv, timeout=timeout)
    except OSError as exc:
        raise ArticleError(
            "ARTICLE_PYTHON_UNAVAILABLE",
            f"could not launch the explicitly selected interpreter {article_python!r}: {exc}; "
            "set CONTENTOPS_PYTHON to an existing Python executable; no automatic interpreter scan or installation is performed",
        ) from exc
    val_text = (val_res.stdout or "") + (val_res.stderr or "")

    metrics = parse_validator_output(val_text)
    if val_res.returncode != 0 or metrics["errors"] or metrics["warnings"]:
        details = metrics["errors"] + metrics["warnings"]
        error_msg = "; ".join(details) if details else val_text.strip()
        raise ArticleError("ARTICLE_VALIDATION_FAILED", f"HTML validation failed: {error_msg}")

    # 2. Run preview wrapper
    p.preview_out.parent.mkdir(parents=True, exist_ok=True)
    wrapper_argv = [article_python, str(p.tools.wrapper), str(p.html), str(p.preview_out)]
    try:
        wrap_res = runner(wrapper_argv, timeout=timeout)
    except OSError as exc:
        raise ArticleError(
            "ARTICLE_PYTHON_UNAVAILABLE",
            f"could not launch the explicitly selected interpreter {article_python!r}: {exc}; "
            "set CONTENTOPS_PYTHON to an existing Python executable; no automatic interpreter scan or installation is performed",
        ) from exc
    if wrap_res.returncode != 0:
        wrap_text = (wrap_res.stdout or "") + (wrap_res.stderr or "")
        raise ArticleError("ARTICLE_PREVIEW_FAILED", f"Preview wrap failed: {wrap_text.strip()}")

    if not p.preview_out.is_file() or p.preview_out.stat().st_size == 0:
        raise ArticleError("ARTICLE_PREVIEW_MISSING", f"Preview file was not created: {p.preview_out}")

    return build_receipt(p, validation_metrics=metrics, article_python=article_python)


def build_receipt(
    p: ArticlePlan,
    *,
    validation_metrics: Dict[str, Any],
    article_python: str,
) -> Dict[str, Any]:
    """Assemble the canonical contentops.gzh-article/v1 receipt."""
    has_errors = bool(validation_metrics.get("errors"))
    has_warnings = bool(validation_metrics.get("warnings"))
    all_pass = not has_errors and not has_warnings

    html_rel = "project://" + p.html.relative_to(p.project).as_posix()
    preview_rel = "project://" + p.preview_out.relative_to(p.project).as_posix()

    receipt: Dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "project": p.project.name,
        "title": p.title,
        "digest": p.digest,
        "theme": p.theme,
        "html": {
            "path": html_rel,
            "sha256": _sha256(p.html),
            "bytes": p.html.stat().st_size,
        },
        "preview": {
            "path": preview_rel,
            "sha256": _sha256(p.preview_out),
            "bytes": p.preview_out.stat().st_size,
        },
        "cover": p.cover,
        "images": list(p.images),
        "image_count": len(p.images),
        "sources": list(p.sources),
        "tools": {
            "validator": p.tools.validator.name,
            "wrapper": p.tools.wrapper.name,
            "upstream_skill": "gzh-design",
            "upstream_license": "AGPL-3.0",
            "easel_runtime_commit": "3fe2d9904c1619281ef57f81d9ee0b7854998399",
            "theme_component_file": "references/theme-graphite-minimal.md",
            "common_components_file": "references/common-components.md",
            "interpreter": Path(article_python).name,
        },
        "validation": {
            "status": "PASS" if all_pass else "FAIL",
            "span_leaf_count": validation_metrics.get("span_leaf_count", 0),
            "errors": list(validation_metrics.get("errors", [])),
            "warnings": list(validation_metrics.get("warnings", [])),
            "component_rules": "SOURCE_LINT_NOT_ARTICLE_VALIDATOR",
        },
        "audit_status": "PASS" if all_pass else "FAIL",
        "status": "AWAITING_MANUAL_REVIEW" if all_pass else "BLOCKED",
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "NOT_STARTED",
        "cannot": [
            "an automated HTML check is not a readability judgement, editorial approval, or fact check",
            "the generated HTML is formatted for the WeChat Official Account editor and requires human copy-paste verification",
            "this receipt grants no publication authority for any platform",
            "WeChat Official Accounts API publication is not authorized and not implemented",
        ],
        "blockers": [
            "AWAITING_FOUNDER_REVIEW",
            "WECHAT_PUBLISH_UNAUTHORIZED",
            "PLATFORM_PLACEHOLDER",
        ] + (["HTML_VALIDATION_WARNINGS"] if has_warnings else []),
    }

    # Deterministic fingerprint over canonical payload
    fingerprint_payload = {
        "html": receipt["html"],
        "title": receipt["title"],
        "theme": receipt["theme"],
        "images": sorted(receipt["images"], key=lambda x: x["path"]),
        "sources": sorted(receipt["sources"]),
        "validation_status": receipt["validation"]["status"],
        "blockers": receipt["blockers"],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    receipt["article_fingerprint"] = fingerprint
    return receipt


def write_receipt(receipt: Dict[str, Any], project_dir: Path | str, out_path: Optional[Path | str] = None) -> Path:
    """Save receipt to project receipts directory, refusing to overwrite a legacy receipt."""
    project = Path(project_dir).resolve()
    target = Path(out_path).resolve() if out_path else (project / "receipts" / "gzh-article.json")
    if not _is_relative_to(target, project):
        raise ArticleError("RECEIPT_PATH_OUTSIDE_PROJECT", f"receipt path is outside project: {target}")
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ArticleError("RECEIPT_SCHEMA_MISMATCH", f"existing receipt is not valid JSON: {target}") from exc
        if existing.get("schema") != RECEIPT_SCHEMA:
            raise ArticleError(
                "RECEIPT_SCHEMA_MISMATCH",
                f"refusing to mix {existing.get('schema')!r} with {RECEIPT_SCHEMA}; move the legacy receipt explicitly",
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def verify_receipt(receipt: Dict[str, Any], project_dir: Path | str) -> bool:
    """Verify the article receipt schema, input, outputs, hashes, and fingerprint."""
    if receipt.get("schema") != RECEIPT_SCHEMA:
        return False
    project = Path(project_dir).resolve()
    input_file = project / "article-input.json"
    if input_file.is_file():
        try:
            input_data = json.loads(input_file.read_text(encoding="utf-8"))
        except Exception:
            return False
        if input_data.get("schema") != INPUT_SCHEMA:
            return False
        if receipt.get("sources") != input_data.get("sources", []):
            return False
    html_entry = receipt.get("html", {})
    raw_path = html_entry.get("path", "")
    if not raw_path.startswith("project://"):
        return False
    rel = raw_path[len("project://") :]
    html_file = (project / rel).resolve()
    if not _is_relative_to(html_file, project) or not html_file.is_file():
        return False

    if _sha256(html_file) != html_entry.get("sha256"):
        return False

    preview_entry = receipt.get("preview", {})
    preview_path = preview_entry.get("path", "")
    if not preview_path.startswith("project://"):
        return False
    preview_file = (project / preview_path[len("project://"):]).resolve()
    if not _is_relative_to(preview_file, project) or not preview_file.is_file():
        return False
    if _sha256(preview_file) != preview_entry.get("sha256"):
        return False

    image_entries = list(receipt.get("images", []))
    if receipt.get("cover"):
        image_entries.append(receipt["cover"])
    for image in image_entries:
        raw_path = image.get("path", "")
        if not raw_path.startswith("project://"):
            return False
        image_file = (project / raw_path[len("project://"):]).resolve()
        if not _is_relative_to(image_file, project) or not image_file.is_file():
            return False
        if _sha256(image_file) != image.get("sha256"):
            return False

    fingerprint_payload = {
        "html": receipt["html"],
        "title": receipt["title"],
        "theme": receipt["theme"],
        "images": sorted(receipt.get("images", []), key=lambda x: x["path"]),
        "sources": sorted(receipt.get("sources", [])),
        "validation_status": receipt.get("validation", {}).get("status"),
        "blockers": receipt.get("blockers", []),
    }
    expected = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return expected == receipt.get("article_fingerprint")
