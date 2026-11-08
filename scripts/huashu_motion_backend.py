#!/usr/bin/env python3
"""Render a project-local huashu-motion film as one M5 visual asset.

The upstream CLI/runtime is installed separately and is never copied into the
repository. This adapter only runs its local, non-paid renderer; publication
and source evidence remain governed by the existing M5 stages.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "src", ROOT / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from process_utils import hidden_run, python_executable  # noqa: E402


class BackendError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackendError(f"invalid JSON input {path.name}: {type(exc).__name__}") from None
    if not isinstance(value, dict):
        raise BackendError(f"expected JSON object in {path.name}")
    return value


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_motion_project(project: Path, value: str) -> Path:
    """Only use film projects stored under this ContentOps project's motion tree."""
    candidate = (project / value).resolve()
    allowed = (project / "motion" / "huashu-motion").resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        raise BackendError("Huashu Motion project must stay under motion/huashu-motion/") from None
    if not (candidate / "index.html").is_file():
        raise BackendError("Huashu Motion project has no index.html")
    for relative in ("vendor/gsap.min.js",):
        if not (candidate / relative).is_file():
            raise BackendError(f"Huashu Motion project is missing {relative}")
    return candidate


def resolve_runtime() -> Path:
    configured = (os.environ.get("CONTENTOPS_HUASHU_MOTION_RUNTIME")
                  or os.environ.get("HUASHU_MOTION_RUNTIME"))
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([ROOT / ".runtime" / "huashu-motion", ROOT.parent / ".runtime" / "huashu-motion"])
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "cli" / "om.js").is_file() and (candidate / "package.json").is_file():
            return candidate
    raise BackendError("Huashu Motion runtime is not installed; set CONTENTOPS_HUASHU_MOTION_RUNTIME")


def _runtime_facts(runtime: Path) -> Dict[str, str]:
    package = _json(runtime / "package.json")
    node = hidden_run(["node", "--version"], cwd=str(runtime), timeout=30)
    if node.returncode != 0 or not re.fullmatch(r"v\d+\.\d+\.\d+\s*", node.stdout or ""):
        raise BackendError("Node.js is unavailable for Huashu Motion")
    major = int((node.stdout or "v0").strip()[1:].split(".", 1)[0])
    if major < 22:
        raise BackendError("Huashu Motion requires Node.js 22 or later")
    commit = hidden_run(["git", "rev-parse", "HEAD"], cwd=str(runtime), timeout=30)
    return {
        "version": str(package.get("version") or "unknown"),
        "node": (node.stdout or "").strip(),
        "commit": (commit.stdout or "").strip() if commit.returncode == 0 else "unversioned",
    }


def _film_hash(project_dir: Path) -> str:
    digest = hashlib.sha256()
    # The CLI appends render history under .om/ on every invocation; that log
    # is output metadata, not an input to the frames, so it must not defeat cache reuse.
    excluded = {"out", ".om", ".git", "node_modules", "cache", "tmp"}
    files = [p for p in project_dir.rglob("*") if p.is_file()
             and not any(part.casefold() in excluded for part in p.relative_to(project_dir).parts)]
    for path in sorted(files, key=lambda item: item.relative_to(project_dir).as_posix().casefold()):
        digest.update(path.relative_to(project_dir).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha(path)))
    return digest.hexdigest()


def author_auto_film(project: Path, shot: Dict[str, Any], line: Dict[str, Any],
                     account_dna: Dict[str, Any], duration_s: float) -> str:
    """Author an editable Huashu Motion scene for a planned M5 placement.

    Code shots show a readable excerpt taken from the registered source file,
    then animate the relevant lines. This avoids shrinking a whole source
    screenshot into a slide. Any diagram is labeled as explanatory and never
    claims to be a runtime result.
    """
    project = project.resolve()
    if not project.is_relative_to(ROOT.resolve()):
        raise BackendError("M5 project must be inside the repository")
    if not 0.5 <= float(duration_s) <= 8.0:
        raise BackendError(f"automatic Huashu Motion duration is unsupported: {duration_s}")
    runtime = resolve_runtime()
    placement = str(shot.get("placement_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,50}", placement):
        raise BackendError("automatic Huashu Motion placement id is invalid")
    profile = ((account_dna.get("visual") or {}).get("motion") or {}).get("motion_profile") or {}
    palette = profile.get("palette") or {}
    for key in ("bg", "surface", "ink", "sub", "accent", "accent2"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(palette.get(key) or "")):
            raise BackendError(f"account motion palette is missing a valid {key}")

    source = None
    source_id = str(shot.get("source_asset_id") or "")
    assets_doc = _json(project / "sources" / "assets.json")
    source = next((row for row in assets_doc.get("assets", [])
                   if str(row.get("id")) == source_id), None)
    source_path: Optional[Path] = None
    source_text_path: Optional[Path] = None
    source_type = str((source or {}).get("type") or "").upper()
    if source and source_type in {"CODE_SNAPSHOT", "USER_PROVIDED_IMAGE"}:
        candidate = (ROOT / str(source.get("repo_path") or "")).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            raise BackendError("automatic Huashu Motion source escapes the repository") from None
        if candidate.is_file():
            declared_sha = str(source.get("sha256") or "")
            if declared_sha and _sha(candidate) != declared_sha:
                raise BackendError("automatic Huashu Motion source image hash changed")
            source_path = candidate
        elif source_type == "USER_PROVIDED_IMAGE":
            raise BackendError("registered local screenshot is missing")
        if source_type == "CODE_SNAPSHOT":
            document = (project / str(source.get("source_document") or "")).resolve()
            try:
                document.relative_to(project)
            except ValueError:
                raise BackendError("automatic Huashu Motion source document escapes the project") from None
            if document.is_file():
                source_text_path = document

    fingerprint = hashlib.sha256(json.dumps({
        "shot": shot, "line": line, "duration_s": round(float(duration_s), 4),
        "palette": palette, "source_sha256": _sha(source_path) if source_path else None,
        "source_text_sha256": _sha(source_text_path) if source_text_path else None,
        "runtime_version": _json(runtime / "package.json").get("version"),
        "scene_template_version": "account-art-direction-v2",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    film = project / "motion" / "huashu-motion" / "auto" / f"{placement}-{fingerprint[:10]}"
    vendor = film / "vendor"
    assets_dir = film / "assets"
    (assets_dir / "fonts").mkdir(parents=True, exist_ok=True)
    vendor.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime / "templates" / "blank" / "vendor" / "gsap.min.js",
                 vendor / "gsap.min.js")
    shutil.copy2(runtime / "templates" / "blank" / "vendor" / "GSAP-LICENSE.html",
                 vendor / "GSAP-LICENSE.html")
    for font in ("NotoSansSC-500.woff", "NotoSansSC-700.woff", "OFL.txt"):
        shutil.copy2(runtime / "fonts" / font, assets_dir / "fonts" / font)
    image_markup = ""
    image_animation = ""
    material_lines = ["# Film materials", "", "- GSAP and Noto Sans SC are bundled local rendering dependencies."]
    if source_text_path:
        raw_lines = source_text_path.read_text(encoding="utf-8", errors="replace").splitlines()
        terms = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]{2,}",
                           f"{shot.get('content_point', '')} {line.get('caption', '')} {line.get('narration', '')}")
        ignored = {"the", "and", "with", "for", "from", "this", "that", "into", "code", "real"}
        terms = [term.casefold() for term in terms if term.casefold() not in ignored]
        scored = []
        for idx, raw in enumerate(raw_lines):
            lowered = raw.casefold()
            code_line = raw.strip()
            if (not code_line or code_line.startswith(("#", "\"\"\"", "'''", "import ", "from ", "class "))):
                continue
            score = sum(1 for term in terms if term in lowered)
            if raw.strip() and score:
                scored.append((score, idx))
        center = max(scored, default=(0, min(15, max(0, len(raw_lines) - 1))))[1]
        picked = sorted({idx for idx in range(max(0, center - 5), min(len(raw_lines), center + 6))
                         if raw_lines[idx].strip()})[:9]
        if not picked:
            picked = [idx for idx, raw in enumerate(raw_lines) if raw.strip()][:9]
        rows = []
        active = min(2, max(0, len(picked) - 1))
        for row_index, idx in enumerate(picked):
            excerpt = html.escape(raw_lines[idx].expandtabs(4).rstrip()[:96])
            rows.append(f'<div class="code-row row-{row_index}"><i>{idx + 1:04d}</i><code>{excerpt}</code></div>')
        filename = html.escape(Path(str(source.get("source_document") or "source.py")).name)
        semantic_class = str(shot.get("semantic_class") or "code")
        if semantic_class == "retrieval":
            point = f"{shot.get('content_point', '')} {line.get('caption', '')} {line.get('narration', '')}".casefold()
            relevant = [idx for _, idx in sorted(scored, key=lambda pair: (-pair[0], pair[1]))[:3]]
            relevant.sort()
            if not relevant:
                relevant = picked[:3]
            excerpt_rows = "".join(
                f'<span class="source-line"><i>{idx + 1:04d}</i><code>{html.escape(raw_lines[idx].expandtabs(4).rstrip()[:78])}</code></span>'
                for idx in relevant
            )
            if "cache" in point or "guardrail" in point:
                kind = "cache"
                stages = ("QUERY", "CACHE CHECK", "HIT / MISS", "GUARDRAILS")
                visual = (
                    '<div class="cache-query"><small>INCOMING QUERY</small><b>semantic key</b></div>'
                    '<div class="cache-gate"><small>DECISION</small><b>cache enabled?</b></div>'
                    '<div class="cache-branch branch-hit"><b>HIT</b><span>reuse response</span></div>'
                    '<div class="cache-branch branch-miss"><b>MISS</b><span>continue retrieval</span></div>'
                    '<div class="guardrail-bar">GUARDRAILS · validate before return</div>'
                )
                image_animation = (
                    f"tl.fromTo('.cache-query',{{x:-520,opacity:.75}},{{x:0,opacity:1,duration:.28}})"
                    f".fromTo('.cache-gate',{{scale:.72,opacity:.75}},{{scale:1,opacity:1,duration:.26}},{duration_s*.22:.3f})"
                    f".fromTo('.cache-branch',{{x:480,opacity:.75}},{{x:0,opacity:1,duration:.26,stagger:.16}},{duration_s*.43:.3f})"
                    f".fromTo('.guardrail-bar',{{y:100,opacity:.75}},{{y:0,opacity:1,duration:.24}},{duration_s*.70:.3f})"
                    f".to('.branch-hit',{{borderColor:'{palette['accent']}',duration:.18}},{duration_s*.86:.3f});"
                )
            elif "chunk" in point:
                kind = "chunk"
                stages = ("DOCUMENT", "CHUNKING", "HYBRID INDEX", "CANDIDATES")
                visual = (
                    '<div class="document-sheet"><small>SOURCE DOCUMENT</small>'
                    f'<div class="document-lines">{excerpt_rows}</div></div>'
                    '<div class="chunk-cut cut-one"></div><div class="chunk-cut cut-two"></div>'
                    '<div class="chunk-card chunk-one">CHUNK · SOURCE SPAN</div>'
                    '<div class="chunk-card chunk-two">CHUNK · SOURCE SPAN</div>'
                    '<div class="chunk-card chunk-three">BM25 + DENSE INDEX</div>'
                    '<div class="diagram-note">CHUNKING SCHEMATIC · SOURCE LINES SHOWN ABOVE</div>'
                )
                image_animation = (
                    f"tl.fromTo('.document-sheet',{{y:180,opacity:.75}},{{y:0,opacity:1,duration:.32}})"
                    f".fromTo('.document-lines .source-line',{{x:-80,opacity:.75}},{{x:0,opacity:1,duration:.22,stagger:.10}},{duration_s*.12:.3f})"
                    f".fromTo('.chunk-cut',{{scaleX:0}},{{scaleX:1,duration:.25,stagger:.12}},{duration_s*.40:.3f})"
                    f".fromTo('.chunk-card',{{y:240,opacity:.75}},{{y:0,opacity:1,duration:.25,stagger:.15}},{duration_s*.54:.3f})"
                    f".to('.chunk-three',{{x:110,scale:1.06,duration:.22}},{duration_s*.82:.3f});"
                )
            elif "rrf" in point or "fusion" in point:
                kind = "fusion"
                stages = ("BM25 ORDER", "DENSE ORDER", "RRF FUSION", "RERANK")
                visual = (
                    '<div class="rank-column rank-lex"><small>LEXICAL LIST</small><b>BM25</b>'
                    '<div class="rank-item r1">document order</div><div class="rank-item r2">rank positions</div></div>'
                    '<div class="rank-column rank-sem"><small>SEMANTIC LIST</small><b>DENSE</b>'
                    '<div class="rank-item r3">meaning order</div><div class="rank-item r4">rank positions</div></div>'
                    '<div class="rrf-equation"><small>RECIPROCAL RANK FUSION</small><b>Σ 1 / (k + rank)</b></div>'
                    '<div class="fusion-result">ONE FUSED ORDER</div>'
                    f'<div class="source-code"><small>{filename} · REAL SOURCE</small><div class="source-lines">{excerpt_rows}</div></div>'
                    '<div class="diagram-note">RANKING SCHEMATIC · NO MEASURED SCORES</div>'
                )
                image_animation = (
                    f"tl.fromTo('.rank-lex',{{x:-470,rotation:-5,opacity:.75}},{{x:0,rotation:0,opacity:1,duration:.28}})"
                    f".fromTo('.rank-sem',{{x:470,rotation:5,opacity:.75}},{{x:0,rotation:0,opacity:1,duration:.28}},{duration_s*.12:.3f})"
                    f".fromTo('.rank-item',{{x:-100,opacity:.75}},{{x:0,opacity:1,duration:.20,stagger:.09}},{duration_s*.30:.3f})"
                    f".fromTo('.rrf-equation',{{scale:.68,y:160,opacity:.75}},{{scale:1,y:0,opacity:1,duration:.28}},{duration_s*.55:.3f})"
                    f".fromTo('.fusion-result',{{scaleX:0,opacity:.75}},{{scaleX:1,opacity:1,duration:.22}},{duration_s*.82:.3f});"
                )
            elif "rerank" in point or "rank" in point or "benchmark" in point or "ir " in point:
                kind = "rerank"
                stages = ("RETRIEVED CANDIDATES", "CROSS-ENCODER", "RELEVANCE ORDER", "SOURCE CODE")
                visual = (
                    '<div class="rerank-stack"><small>RETRIEVED CANDIDATES</small>'
                    '<div class="candidate-card candidate-a">query + passage</div>'
                    '<div class="candidate-card candidate-b">query + passage</div>'
                    '<div class="candidate-card candidate-c">query + passage</div></div>'
                    '<div class="cross-encoder">CROSS-RERANKER<span>joint relevance scoring</span></div>'
                    '<div class="ordered-output"><span>REORDER</span><b>best-supported passage first</b></div>'
                    f'<div class="source-code"><small>{filename} · REAL SOURCE</small><div class="source-lines">{excerpt_rows}</div></div>'
                    '<div class="diagram-note">PROCESS SCHEMATIC · VALUES NOT MEASURED</div>'
                )
                image_animation = (
                    f"tl.fromTo('.rerank-stack',{{x:-500,opacity:.75}},{{x:0,opacity:1,duration:.28}})"
                    f".fromTo('.candidate-card',{{y:120,opacity:.75}},{{y:0,opacity:1,duration:.18,stagger:.12}},{duration_s*.14:.3f})"
                    f".fromTo('.cross-encoder',{{scale:.72,opacity:.75}},{{scale:1,opacity:1,duration:.28}},{duration_s*.40:.3f})"
                    f".fromTo('.ordered-output',{{x:490,opacity:.75}},{{x:0,opacity:1,duration:.28}},{duration_s*.62:.3f})"
                    f".fromTo('.source-code',{{y:100,opacity:.75}},{{y:0,opacity:1,duration:.24}},{duration_s*.80:.3f});"
                )
            elif "orchestrat" in point or "engine" in point or "end-to-end" in point:
                kind = "orchestrator"
                stages = ("QUERY", "RETRIEVER", "RERANKER", "RESPONSE")
                visual = (
                    '<div class="orchestrator-track"><i class="track-line"></i>'
                    '<div class="orbit-node orbit-query"><small>01</small><b>QUERY</b></div>'
                    '<div class="orbit-node orbit-retrieve"><small>02</small><b>RETRIEVER</b></div>'
                    '<div class="orbit-node orbit-rerank"><small>03</small><b>RERANKER</b></div>'
                    '<div class="orbit-node orbit-response"><small>04</small><b>RESPONSE</b></div></div>'
                    f'<div class="source-code"><small>{filename} · REAL SOURCE</small><div class="source-lines">{excerpt_rows}</div></div>'
                    '<div class="diagram-note">CONTROL FLOW SCHEMATIC · SOURCE EXCERPT BELOW</div>'
                )
                image_animation = (
                    f"tl.fromTo('.track-line',{{scaleX:0}},{'{'}scaleX:1,duration:{max(.25,duration_s*.62):.3f}{'}'})"
                    f".fromTo('.orbit-node',{{y:160,scale:.78,opacity:.75}},{{y:0,scale:1,opacity:1,duration:.23,stagger:.15}},.12)"
                    f".fromTo('.source-code',{{y:120,opacity:.75}},{{y:0,opacity:1,duration:.24}},{duration_s*.68:.3f})"
                    f".to('.orbit-response',{{borderColor:'{palette['accent2']}',scale:1.08,duration:.18}},{duration_s*.87:.3f});"
                )
            else:
                kind = "hybrid"
                stages = ("QUERY", "BM25 · TERMS", "DENSE · MEANING", "FUSION + RERANK")
                visual = (
                    '<div class="hybrid-query"><small>ONE QUERY</small><b>same input · two retrieval paths</b></div>'
                    '<div class="hybrid-lane lane-lex"><small>LEXICAL</small><b>BM25</b><span>term relevance</span></div>'
                    '<div class="hybrid-lane lane-dense"><small>SEMANTIC</small><b>DENSE</b><span>meaning similarity</span></div>'
                    '<svg class="hybrid-routes" viewBox="0 0 1080 1920" aria-hidden="true">'
                    '<path class="hybrid-route route-lex" d="M300 640 C300 780 250 850 260 1020"/>'
                    '<path class="hybrid-route route-dense" d="M780 640 C780 780 830 850 820 1020"/></svg>'
                    '<div class="hybrid-merge">FUSION<br>↓<br>RERANK</div>'
                    f'<div class="source-code"><small>{filename} · REAL SOURCE</small><div class="source-lines">{excerpt_rows}</div></div>'
                    '<div class="diagram-note">MECHANISM SCHEMATIC · NOT A RUNTIME RESULT</div>'
                )
                image_animation = (
                    f"tl.fromTo('.hybrid-query',{{y:-160,opacity:.75}},{{y:0,opacity:1,duration:.26}})"
                    f".fromTo('.hybrid-lane',{{x:-470,opacity:.75}},{{x:0,opacity:1,duration:.25,stagger:.18}},{duration_s*.15:.3f})"
                    f".fromTo('.hybrid-route',{{strokeDashoffset:700}},{{strokeDashoffset:0,duration:.35,stagger:.12}},{duration_s*.42:.3f})"
                    f".fromTo('.hybrid-merge',{{scale:.65,y:170,opacity:.75}},{{scale:1,y:0,opacity:1,duration:.28}},{duration_s*.66:.3f})"
                    f".fromTo('.source-code',{{y:100,opacity:.75}},{{y:0,opacity:1,duration:.24}},{duration_s*.82:.3f});"
                )
            image_markup = f'<section class="retrieval-scene kind-{kind}">{visual}</section>'
            material_lines.append(
                f"- `retrieval-scene/{kind}` is an explanatory schematic chosen from the line topic; any source-code rows are verbatim excerpts from `{source.get('source_document')}`. The diagram contains no measured retrieval result."
            )
        else:
            image_markup = (
                '<section class="editor"><div class="editor-bar"><b></b><b></b><b></b>'
                f'<span>{filename} · PINNED SOURCE</span></div><div class="code">{"".join(rows)}</div>'
                '<div class="editor-foot">SOURCE EXCERPT · NOT A LIVE EXECUTION</div></section>'
            )
            pan = -340 if center % 2 else 340
            image_animation = (
                "tl.fromTo('.editor',{y:55,opacity:.5},{y:0,opacity:1,duration:.28})"
                f".fromTo('.row-0',{{x:-90,opacity:.75}},{{x:0,opacity:1,duration:.28}},.12)"
                ".fromTo('.code-row:not(.row-0)',{x:90,opacity:.65},{x:0,opacity:1,duration:.25,stagger:.08},.22)"
                f".to('.code',{{y:{pan},duration:{max(.7,duration_s*.42):.3f},ease:'power3.inOut'}},.48)"
                f".to('.editor',{{y:-26,scale:1.018,duration:{min(.45,duration_s*.22):.3f},ease:'power2.inOut'}},.62)"
                f".to('.row-{active}',{{backgroundColor:'{palette['accent']}',borderColor:'{palette['accent']}',scale:1.025,duration:.30}},.78)"
                f".to('.row-{active} code,.row-{active} i',{{color:'{palette['bg']}',duration:.16}},.82)"
                f".to('.row-{active}',{{backgroundColor:'{palette['surface']}',scale:1,duration:.28}},{max(1.35,duration_s*.68):.3f})"
                f".to('.row-{active} code,.row-{active} i',{{color:'{palette['ink']}',duration:.16}},{max(1.38,duration_s*.70):.3f})"
                f".to('.editor',{{y:-4,scale:1,duration:{min(.45,duration_s*.20):.3f},ease:'power2.inOut'}},{max(1.15,duration_s*.59):.3f});"
            )
        material_lines.append(f"- Source excerpt comes from `{source.get('source_document')}`; source SHA-256 `{_sha(source_text_path)}`.")
        if source_path:
            material_lines.append(f"- The registered source screenshot is retained in `assets/source.png`; SHA-256 `{_sha(source_path)}`.")
            shutil.copy2(source_path, assets_dir / "source.png")
    elif source_path:
        shutil.copy2(source_path, assets_dir / "source.png")
        if source_type == "USER_PROVIDED_IMAGE":
            focus_markup = ""
            focus_animation = ""
            targets = shot.get("ocr_targets") or []
            rect = targets[0].get("rect") if targets and isinstance(targets[0], dict) else None
            if isinstance(rect, list) and len(rect) == 4:
                try:
                    from PIL import Image
                    with Image.open(source_path) as original:
                        image_w, image_h = original.size
                    scale = min(1000 / image_w, 1250 / image_h)
                    drawn_w, drawn_h = image_w * scale, image_h * scale
                    offset_x, offset_y = (1000 - drawn_w) / 2, (1250 - drawn_h) / 2
                    left, top, width, height = (float(value) for value in rect)
                    box = (offset_x + left * drawn_w, offset_y + top * drawn_h,
                           width * drawn_w, height * drawn_h)
                    focus_markup = (
                        '<div class="ocr-focus" style="left:%.1fpx;top:%.1fpx;'
                        'width:%.1fpx;height:%.1fpx"></div>' % box
                    )
                    focus_animation = (
                        "tl.fromTo('.ocr-focus',{scale:.92,opacity:0},{scale:1,opacity:1,duration:.32},.62);"
                    )
                except (OSError, TypeError, ValueError):
                    focus_markup = ""
                    focus_animation = ""
            image_markup = (
                '<div class="source-stage"><img class="source-evidence" src="assets/source.png" '
                'alt="user-provided source screenshot">' + focus_markup + '</div>'
            )
            image_animation = (
                "tl.fromTo('.source-stage',{x:45,opacity:.55},{x:0,opacity:1,duration:.36});"
                + focus_animation
            )
        else:
            image_markup = '<img class="source" src="assets/source.png" alt="pinned source screenshot">'
            image_animation = "tl.fromTo('.source',{scale:1.08,opacity:.45},{scale:1,opacity:1,duration:.52});"
        material_lines.append(f"- `assets/source.png`: registered source image; SHA-256 `{_sha(source_path)}`.")
        if source_type == "USER_PROVIDED_IMAGE":
            material_lines.append("- Screenshot remains fully visible; the cyan focus box comes from this placement's OCR target.")
    else:
        label = html.escape(str(line.get("caption") or line.get("narration") or
                                shot.get("content_point") or "").strip()[:62])
        image_markup = (
            f'<div class="hero-label">{label}</div>'
            '<div class="stage-rail"><span>01</span><b></b><span>02</span><b></b><span>03</span></div>'
            '<div class="flow"><div class="node first">INPUT</div>'
            '<div class="node second">TRANSFORM</div><div class="node third">OUTPUT</div></div>'
            '<div class="diagram-note">EXPLANATORY FLOW · NO MEASURED RESULT</div>'
        )
        image_animation = (
            "tl.fromTo('.hero-label',{x:-120,opacity:.75},{x:0,opacity:1,duration:.35})"
            ".fromTo('.node',{y:90,opacity:.75},{y:0,opacity:1,duration:.35,stagger:.3},.35)"
            ".fromTo('.stage-rail b',{scaleX:0},{scaleX:1,duration:.35,stagger:.28},.6)"
            ".fromTo('.diagram-note',{opacity:.75},{opacity:1,duration:.25},1.8);"
        )
    raw_title = str(shot.get("content_point") or line.get("caption") or "").strip()[:64]
    scene_title = html.escape(raw_title)
    title_px = 58 if len(raw_title) <= 14 else 49 if len(raw_title) <= 19 else 42
    evidence_label = html.escape(Path(str(source.get("source_document") or "source")).name
                                 if source else "EXPLANATORY MOTION")
    colors = {key: str(palette[key]) for key in ("bg", "surface", "ink", "sub", "accent", "accent2")}
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{placement}</title>
<script src="vendor/gsap.min.js"></script><style>
@font-face{{font-family:"Noto Sans SC";src:url("assets/fonts/NotoSansSC-500.woff");font-weight:400 600}}
@font-face{{font-family:"Noto Sans SC";src:url("assets/fonts/NotoSansSC-700.woff");font-weight:700 900}}
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;overflow:hidden}}
body{{font-family:"Noto Sans SC",sans-serif;background:{colors['bg']};color:{colors['ink']}}}
#film{{position:relative;width:1080px;height:1920px;overflow:hidden;background:{colors['bg']}}}
.eyebrow{{position:absolute;left:72px;top:112px;color:{colors['sub']};font:22px ui-monospace,monospace;letter-spacing:2px}}
h1{{position:absolute;left:68px;right:68px;top:230px;margin:0;font-size:{title_px}px;line-height:1.20;max-height:190px;overflow:hidden;letter-spacing:-.02em}}
.editor{{position:absolute;left:48px;right:48px;top:390px;height:1340px;background:{colors['bg']};border:2px solid {colors['surface']};border-radius:24px;overflow:hidden;box-shadow:0 34px 90px #0008}}
.editor-bar{{height:78px;background:{colors['surface']};display:flex;align-items:center;gap:10px;padding:0 28px;color:{colors['sub']};font:19px ui-monospace,monospace;letter-spacing:1px}}
.editor-bar b{{width:12px;height:12px;border-radius:50%;background:{colors['sub']};opacity:.6}}.editor-bar b:first-child{{background:{colors['accent']}}}.editor-bar b:nth-child(2){{background:{colors['sub']}}}.editor-bar b:nth-child(3){{background:{colors['sub']}}}.editor-bar span{{margin-left:18px}}
.code{{padding:30px 24px;will-change:transform}}.code-row{{display:flex;align-items:flex-start;min-height:104px;padding:20px 18px;border-left:6px solid transparent;border-bottom:1px solid {colors['bg']};background:{colors['surface']};margin-bottom:9px;border-radius:0 10px 10px 0}}
.code-row i{{font:24px ui-monospace,monospace;color:{colors['sub']};font-style:normal;min-width:84px}}.code-row code{{font:30px/1.35 ui-monospace,monospace;color:{colors['ink']};overflow:hidden;overflow-wrap:anywhere}}
.editor-foot{{position:absolute;left:28px;right:28px;bottom:22px;color:{colors['sub']};font:17px ui-monospace,monospace;letter-spacing:1px}}
.retrieval-scene{{position:absolute;inset:0}}
.query-node{{position:absolute;z-index:2;left:250px;right:250px;top:385px;height:210px;padding:28px 36px;background:{colors['surface']};border:1px solid {colors['sub']};border-top:6px solid {colors['accent']};display:flex;flex-direction:column;justify-content:center;gap:14px;text-align:center}}
.query-node small,.lane small,.source-code small{{font:18px ui-monospace,monospace;letter-spacing:2px;color:{colors['sub']}}}.query-node b{{font-size:42px}}
.routes{{position:absolute;z-index:0;inset:0;width:1080px;height:1920px;overflow:visible}}
.route{{fill:none;stroke:{colors['accent']};stroke-width:6;stroke-linecap:round;stroke-dasharray:900;stroke-dashoffset:0;opacity:.72}}
.route-b,.route-merge-b{{stroke:{colors['accent2']}}}
.lane{{position:absolute;z-index:1;top:680px;width:444px;height:405px;padding:28px;background:{colors['surface']};border:1px solid {colors['sub']}}}
.lane-a{{left:42px;border-top:7px solid {colors['accent']}}}.lane-b{{right:42px;border-top:7px solid {colors['accent2']}}}
.lane b{{display:block;margin-top:18px;font-size:34px;line-height:1.15;color:{colors['ink']}}}
.candidate{{position:absolute;left:26px;right:26px;height:62px;padding:16px 20px;background:{colors['bg']};border-left:5px solid {colors['accent']};color:{colors['ink']};font:20px ui-monospace,monospace}}
.lane-b .candidate{{border-color:{colors['accent2']}}}.c-a1,.c-b1{{top:195px}}.c-a2,.c-b2{{top:276px}}
.fusion-node{{position:absolute;z-index:2;left:108px;right:108px;top:1200px;height:150px;display:flex;align-items:center;justify-content:center;background:{colors['surface']};border:2px solid {colors['accent']};font-size:40px;font-weight:700;letter-spacing:1px}}
.source-code{{position:absolute;left:64px;right:64px;top:1455px;min-height:195px;padding:22px 26px;background:{colors['surface']};border-left:6px solid {colors['accent']};display:flex;flex-direction:column;gap:15px}}
.source-code code{{font:21px/1.35 ui-monospace,monospace;color:{colors['ink']};overflow-wrap:anywhere}}
.source-lines{{display:flex;flex-direction:column;gap:9px}}
.source-line{{display:flex;gap:18px;align-items:flex-start;padding:9px 12px;background:{colors['surface']};border-left:4px solid {colors['accent']}}}
.source-line i{{min-width:48px;color:{colors['sub']};font:17px ui-monospace,monospace;font-style:normal}}
.source-line code{{font:25px/1.25 ui-monospace,monospace;color:{colors['ink']};overflow-wrap:anywhere}}
.diagram-note{{position:absolute;left:72px;bottom:108px;color:{colors['sub']};font:17px ui-monospace,monospace;letter-spacing:1px}}
.retrieval-scene{{background:{colors['bg']}}}
.kind-chunk .document-sheet{{position:absolute;left:74px;right:74px;top:430px;height:450px;padding:30px 34px;background:{colors['surface']};color:{colors['ink']};box-shadow:0 28px 80px #0008;border-top:8px solid {colors['accent']}}}
.document-sheet>small{{font:700 18px ui-monospace,monospace;letter-spacing:2px;color:{colors['sub']}}}
.document-lines{{margin-top:24px;display:flex;flex-direction:column;gap:10px}}
.document-lines .source-line{{background:{colors['bg']};border-left:4px solid {colors['accent']};padding:10px 14px}}
.document-lines .source-line i{{color:{colors['sub']}}}
.document-lines .source-line code{{font:22px/1.2 ui-monospace,monospace;color:{colors['ink']}}}
.chunk-cut{{position:absolute;left:100px;right:100px;height:5px;background:{colors['accent']};transform-origin:left;box-shadow:0 0 22px {colors['accent']}}}.cut-one{{top:605px}}.cut-two{{top:765px;background:{colors['accent2']}}}
.chunk-card{{position:absolute;left:92px;right:92px;height:116px;padding:32px 34px;background:{colors['surface']};border-left:8px solid {colors['accent']};font:700 30px ui-monospace,monospace;letter-spacing:1px}}
.chunk-one{{top:970px}}.chunk-two{{top:1110px;border-color:{colors['accent2']}}}.chunk-three{{top:1280px;height:124px;background:{colors['surface']}}}
.kind-fusion .rank-column{{position:absolute;top:525px;width:420px;height:410px;padding:30px;background:{colors['surface']};box-shadow:0 24px 70px #0007}}
.kind-fusion .source-code{{top:1460px;min-height:250px}}
.rank-lex{{left:54px;border-top:9px solid {colors['accent']};transform:rotate(-2deg)}}.rank-sem{{right:54px;border-top:9px solid {colors['accent2']};transform:rotate(2deg)}}
.rank-column small,.rerank-stack small{{display:block;font:17px ui-monospace,monospace;letter-spacing:2px;color:{colors['sub']}}}.rank-column>b{{display:block;margin-top:14px;font-size:40px}}
.rank-item{{height:70px;margin-top:18px;padding:20px;background:{colors['surface']};border-left:5px solid {colors['accent']};font:22px ui-monospace,monospace}}
.rank-sem .rank-item{{border-color:{colors['accent2']}}}
.rrf-equation{{position:absolute;left:125px;right:125px;top:1015px;padding:30px;text-align:center;background:{colors['surface']};color:{colors['ink']};border-bottom:8px solid {colors['accent']};box-shadow:0 25px 80px #0008}}
.rrf-equation small{{display:block;font:700 17px ui-monospace,monospace;letter-spacing:2px;color:{colors['sub']}}}.rrf-equation b{{display:block;margin-top:12px;font:700 46px ui-monospace,monospace}}
.fusion-result{{position:absolute;left:220px;right:220px;top:1280px;padding:24px;text-align:center;background:{colors['accent']};color:{colors['bg']};font:800 29px ui-monospace,monospace;transform-origin:center}}
.kind-rerank .rerank-stack{{position:absolute;left:62px;top:510px;width:430px;height:475px;padding:27px;background:{colors['surface']};color:{colors['ink']};border-top:9px solid {colors['accent']};box-shadow:0 24px 70px #0008}}
.candidate-card{{position:absolute;left:24px;right:24px;height:88px;padding:26px 20px;background:{colors['bg']};border-left:6px solid {colors['accent2']};font:22px ui-monospace,monospace;color:{colors['ink']};box-shadow:0 12px 26px #0008}}
.candidate-a{{top:120px}}.candidate-b{{top:232px}}.candidate-c{{top:344px}}
.cross-encoder{{position:absolute;right:62px;top:590px;width:438px;height:210px;padding:38px 28px;background:{colors['surface']};border:2px solid {colors['accent2']};font:700 30px ui-monospace,monospace;box-shadow:0 25px 70px #0008}}
.cross-encoder span{{display:block;margin-top:18px;color:{colors['sub']};font:20px "Noto Sans SC",sans-serif}}
.ordered-output{{position:absolute;left:140px;right:140px;top:1085px;padding:30px;text-align:center;background:{colors['surface']};border-bottom:7px solid {colors['accent']}}}
.ordered-output span{{display:block;color:{colors['sub']};font:17px ui-monospace,monospace;letter-spacing:2px}}.ordered-output b{{display:block;margin-top:12px;font-size:31px}}
.kind-rerank .source-code{{top:1370px;min-height:285px}}
.kind-cache .cache-query,.kind-cache .cache-gate{{position:absolute;left:245px;right:245px;padding:26px 34px;text-align:center;background:{colors['surface']};box-shadow:0 20px 58px #0007}}
.cache-query{{top:445px;border-top:7px solid {colors['accent']}}}.cache-gate{{top:735px;border:2px solid {colors['accent2']}}}
.cache-query small,.cache-gate small{{display:block;color:{colors['sub']};font:17px ui-monospace,monospace;letter-spacing:2px}}.cache-query b,.cache-gate b{{display:block;margin-top:14px;font-size:35px}}
.cache-branch{{position:absolute;top:1030px;width:440px;height:168px;padding:30px;background:{colors['surface']};border-left:8px solid {colors['accent']};box-shadow:0 18px 50px #0006}}
.branch-hit{{left:58px}}.branch-miss{{right:58px;border-color:{colors['accent2']}}}.cache-branch b{{display:block;font:800 37px ui-monospace,monospace}}.cache-branch span{{display:block;margin-top:12px;color:{colors['sub']};font-size:22px}}
.guardrail-bar{{position:absolute;left:90px;right:90px;top:1300px;padding:24px;text-align:center;background:{colors['surface']};border-bottom:6px solid {colors['accent']};font:700 24px ui-monospace,monospace}}
.kind-orchestrator .orchestrator-track{{position:absolute;left:100px;right:100px;top:465px;height:760px;display:flex;flex-direction:column;justify-content:space-between}}
.track-line{{position:absolute;left:48px;top:52px;bottom:52px;width:6px;background:{colors['accent']};transform-origin:top}}
.orbit-node{{position:relative;z-index:1;margin-left:108px;padding:22px 28px;background:{colors['surface']};border-left:7px solid {colors['accent']};box-shadow:0 15px 42px #0006;display:flex;align-items:center;gap:22px}}
.orbit-node small{{font:18px ui-monospace,monospace;color:{colors['sub']}}}.orbit-node b{{font:700 29px ui-monospace,monospace}}.orbit-retrieve{{border-color:{colors['accent2']}}}.orbit-rerank{{border-color:{colors['accent']}}}.orbit-response{{border-color:{colors['accent2']}}}
.kind-orchestrator .source-code{{top:1315px;min-height:320px}}
.kind-hybrid .hybrid-query{{position:absolute;left:182px;right:182px;top:420px;padding:26px;background:{colors['surface']};color:{colors['ink']};text-align:center;border-bottom:7px solid {colors['accent']};box-shadow:0 20px 60px #0008}}
.hybrid-query small{{display:block;font:700 16px ui-monospace,monospace;letter-spacing:2px;color:{colors['sub']}}}.hybrid-query b{{display:block;margin-top:10px;font-size:28px}}
.hybrid-lane{{position:absolute;top:690px;width:440px;height:300px;padding:32px;background:{colors['surface']};box-shadow:0 22px 60px #0008}}
.lane-lex{{left:54px;border-top:9px solid {colors['accent']}}}.lane-dense{{right:54px;border-top:9px solid {colors['accent2']}}}
.hybrid-lane small{{font:17px ui-monospace,monospace;color:{colors['sub']};letter-spacing:2px}}.hybrid-lane b{{display:block;margin-top:20px;font:800 40px ui-monospace,monospace}}.hybrid-lane span{{display:block;margin-top:18px;font-size:23px;color:{colors['sub']}}}
.hybrid-routes{{position:absolute;inset:0;width:1080px;height:1920px;pointer-events:none}}.hybrid-route{{fill:none;stroke:{colors['accent']};stroke-width:8;stroke-dasharray:700;stroke-dashoffset:0}}.route-dense{{stroke:{colors['accent2']}}}
.hybrid-merge{{position:absolute;left:195px;right:195px;top:1090px;padding:24px;text-align:center;background:{colors['surface']};border:2px solid {colors['accent']};font:800 32px/1.35 ui-monospace,monospace;box-shadow:0 24px 70px #0008}}
.kind-hybrid .source-code{{top:1420px;min-height:280px}}
.source{{position:absolute;left:0;top:410px;width:100%;height:1250px;object-fit:cover;object-position:center;transform-origin:center}}
.source-stage{{position:absolute;left:40px;top:410px;width:1000px;height:1250px;overflow:hidden;background:{colors['surface']};border:2px solid {colors['surface']};display:flex;align-items:center;justify-content:center}}
.source-stage img{{width:100%;height:100%;object-fit:contain;transform-origin:center}}
.ocr-focus{{position:absolute;border:6px solid {colors['accent']};box-shadow:0 0 0 9999px #0F111766,0 0 26px {colors['accent']};border-radius:8px;pointer-events:none;transform-origin:center}}
.hero-label{{position:absolute;left:72px;right:72px;top:400px;font-size:54px;font-weight:700;line-height:1.2}}
.stage-rail{{position:absolute;left:160px;right:160px;top:690px;display:flex;align-items:center;justify-content:space-between;color:{colors['accent']};font:700 26px ui-monospace,monospace}}
.stage-rail b{{height:4px;flex:1;background:{colors['surface']};transform-origin:left;margin:0 20px}}
.flow{{position:absolute;left:0;right:0;top:800px;height:680px}}
.node{{position:absolute;left:90px;right:90px;height:170px;padding:34px 40px;background:{colors['surface']};border-left:8px solid {colors['accent']};font:700 42px ui-monospace,monospace;display:flex;align-items:center;letter-spacing:2px}}
.first{{top:0}}.second{{top:220px;border-color:{colors['accent2']}}}.third{{top:440px;border-color:{colors['accent']}}}
.diagram-note{{position:absolute;left:72px;bottom:130px;color:{colors['sub']};font:18px ui-monospace,monospace;letter-spacing:1px}}
.footer{{position:absolute;left:72px;bottom:118px;color:{colors['sub']};font:20px ui-monospace,monospace;letter-spacing:1px}}
/* Account-DNA art direction: ink-black canvas, quiet technical geometry,
   translucent charcoal surfaces and cyan only for the current focal event. */
#film{{isolation:isolate;background-color:{colors['bg']};background-image:
  linear-gradient(90deg,transparent 0,transparent 71px,rgba(139,149,165,.055) 72px,transparent 73px),
  linear-gradient(0deg,transparent 0,transparent 71px,rgba(139,149,165,.045) 72px,transparent 73px);
  background-size:72px 72px}}
#film::before{{content:"";position:absolute;z-index:-1;inset:0;pointer-events:none;
  background:radial-gradient(ellipse at 52% 46%,rgba(56,189,248,.055),transparent 58%);
  opacity:.62}}
.editor,.query-node,.lane,.document-sheet,.chunk-card,.rank-column,.rank-item,
.rrf-equation,.rerank-stack,.cross-encoder,.ordered-output,.cache-query,.cache-gate,
.cache-branch,.guardrail-bar,.orbit-node,.hybrid-query,.hybrid-lane,.hybrid-merge,
.node,.source-code{{background-color:rgba(16,18,22,.86);border-color:rgba(139,149,165,.24)}}
.editor{{left:72px;right:72px;width:auto;border-radius:10px 10px 18px 18px;box-shadow:0 28px 70px #0009}}
.editor-bar{{background:rgba(22,26,34,.58);border-bottom:1px solid rgba(139,149,165,.20)}}
.code-row{{background:rgba(22,26,34,.34);border-bottom:1px solid rgba(139,149,165,.08);border-radius:0;margin-bottom:5px}}
.code-row i{{font-size:20px;min-width:64px}}
.code-row code{{font-size:28px;line-height:1.32}}
.source-stage{{background:{colors['bg']};border:1px solid rgba(139,149,165,.35);border-radius:12px;box-shadow:0 24px 68px #0009}}
.source-stage img{{border-radius:10px}}
.lane,.hybrid-lane,.rank-column,.cache-branch,.orbit-node,.node{{box-shadow:none;border-radius:4px 12px 12px 4px}}
.query-node,.hybrid-query,.rrf-equation,.cross-encoder,.ordered-output,.cache-query,.cache-gate,.hybrid-merge{{border-radius:10px;background:rgba(16,18,22,.92)}}
.candidate,.candidate-card,.document-lines .source-line{{background:rgba(10,11,13,.72);border-radius:4px}}
.source-code,.guardrail-bar,.diagram-note{{background:rgba(16,18,22,.65)}}
.retrieval-scene::after{{content:"";position:absolute;left:72px;right:72px;top:355px;height:1px;background:linear-gradient(90deg,transparent,rgba(139,149,165,.28),transparent);pointer-events:none}}
.editor-foot,.diagram-note,.footer{{font-size:16px;letter-spacing:.08em}}
</style></head><body><main id="film" data-composition-id="film" data-width="1080" data-height="1920">
<div class="eyebrow">{evidence_label}　·　{placement}</div><h1>{scene_title}</h1>{image_markup}
<div class="footer">CONTENTOPS / MOTION</div></main>
<script>window.__timelines=window.__timelines||{{}};const tl=gsap.timeline({{paused:true,defaults:{{ease:"power2.out"}}}});
tl.fromTo('.eyebrow',{{x:-45,opacity:.75}},{{x:0,opacity:1,duration:.32}}).fromTo('h1',{{y:45,opacity:.75}},{{y:0,opacity:1,duration:.42}},.12);
{image_animation}tl.to({{}},{{duration:Math.max(0,{float(duration_s):.4f}-tl.duration())}},tl.duration());window.__timelines['film']=tl;</script></body></html>'''
    film.mkdir(parents=True, exist_ok=True)
    (film / "index.html").write_text(page, encoding="utf-8")
    if not source_text_path and not source_path:
        material_lines.append("- Diagram is explanatory motion based only on the source-backed narration; it contains no measured values.")
    (film / "materials.md").write_text("\n".join(material_lines) + "\n", encoding="utf-8")
    return film.relative_to(project).as_posix()


def _probe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ], timeout=60)
    if proc.returncode != 0:
        raise BackendError("ffprobe could not read Huashu Motion output")
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        raise BackendError("ffprobe returned invalid JSON") from None
    stream = next((row for row in data.get("streams", []) if row.get("codec_type") == "video"), None)
    if not stream:
        raise BackendError("Huashu Motion output has no video stream")
    result = {
        "codec": stream.get("codec_name"),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": stream.get("avg_frame_rate"),
        "duration_s": float((data.get("format") or {}).get("duration") or stream.get("duration") or 0),
        "has_audio": any(row.get("codec_type") == "audio" for row in data.get("streams", [])),
        "bytes": path.stat().st_size,
    }
    if result["codec"] != "h264" or (result["width"], result["height"]) != (1080, 1920):
        raise BackendError(
            f"Huashu Motion must render 1080x1920 H.264; got {result['width']}x{result['height']} {result['codec']}"
        )
    if result["duration_s"] <= 0 or result["bytes"] < 100_000:
        raise BackendError("Huashu Motion output is empty or has no duration")
    return result


def render(project: Path, film_arg: str, asset_id: str, placement_id: str,
           account_id: str = "", expected_duration_s: Optional[float] = None) -> Dict[str, Any]:
    project = project.resolve()
    if not project.is_relative_to((ROOT / "projects").resolve()):
        raise BackendError("M5 project must be inside projects/")
    film = resolve_motion_project(project, film_arg)
    runtime = resolve_runtime()
    facts = _runtime_facts(runtime)
    script = _json(project / "script" / "script.json")
    claims = _json(project / "script" / "claims.json")
    sources = _json(project / "sources" / "source-refs.json")
    line = next((row for row in script.get("lines", []) if str(row.get("id")) == placement_id), None)
    if not line:
        raise BackendError(f"placement {placement_id!r} is not present in script.json")
    inputs = {
        "script_sha256": _sha(project / "script" / "script.json"),
        "claims_sha256": _sha(project / "script" / "claims.json"),
        "source_refs_sha256": _sha(project / "sources" / "source-refs.json"),
        "film_sha256": _film_hash(film),
        "runtime_commit": facts["commit"],
    }
    fingerprint = hashlib.sha256(json.dumps(
        {"inputs": inputs, "asset_id": asset_id, "placement_id": placement_id},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    output = project / "assets" / "generated" / "huashu-motion" / f"{asset_id}.mp4"
    receipt_path = project / "receipts" / f"huashu-motion-{asset_id}.json"
    previous = None
    if output.is_file() and receipt_path.is_file():
        try:
            prior = _json(receipt_path)
            if (prior.get("fingerprint") == fingerprint
                    and prior.get("output_sha256") == _sha(output)):
                probe = _probe(output)
                if expected_duration_s is None or abs(probe["duration_s"] - expected_duration_s) <= 0.15:
                    previous = prior
        except (BackendError, OSError, ValueError):
            previous = None
    if previous:
        return {"state": "REUSED", "reused": True, "output": output,
                "receipt": receipt_path, "technical_qc": previous["technical_qc"],
                "fingerprint": fingerprint, "runtime": facts}

    check = hidden_run(["node", str(runtime / "cli" / "om.js"), "check", str(film), "--source", "--json"],
                       cwd=str(runtime), timeout=600)
    if check.returncode != 0:
        raise BackendError(f"Huashu Motion source/structure check failed: {(check.stderr or check.stdout)[-700:]}")
    started = time.monotonic()
    proc = hidden_run(["node", str(runtime / "cli" / "om.js"), "render", str(film),
                       "--format", "mp4", "--fps", "30", "--workers", "1", "--silent"],
                      cwd=str(runtime), timeout=3600)
    elapsed = round(time.monotonic() - started, 3)
    if proc.returncode != 0:
        raise BackendError(f"Huashu Motion render failed: {(proc.stderr or proc.stdout)[-900:]}")
    matches = re.findall(r"(?:[A-Za-z]:[\\/]|/)[^\r\n]*?\.mp4", proc.stdout or "", re.IGNORECASE)
    rendered = Path(matches[-1].strip().strip('"')) if matches else None
    if rendered is None or not rendered.is_file():
        raise BackendError("Huashu Motion CLI exited successfully but did not report an MP4 path")
    technical = _probe(rendered)
    if expected_duration_s is not None and abs(technical["duration_s"] - expected_duration_s) > 0.15:
        raise BackendError(
            f"render duration {technical['duration_s']:.3f}s does not match narration {expected_duration_s:.3f}s"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_suffix(".tmp.mp4")
    shutil.copy2(rendered, staged)
    staged.replace(output)
    digest = _sha(output)
    repo_path = output.relative_to(ROOT).as_posix()
    receipt = {
        "schema": "contentops.video-receipt/v1",
        "adapter": "contentops.huashu-motion-backend/v1",
        "created_at": _now(), "account_id": account_id,
        "engine": "huashu-motion", "runtime": facts,
        "placement_id": placement_id, "asset_id": asset_id,
        "script_sha256": inputs["script_sha256"],
        "claims_sha256": inputs["claims_sha256"],
        "source_refs_sha256": inputs["source_refs_sha256"],
        "film_sha256": inputs["film_sha256"],
        "fingerprint": fingerprint, "output_sha256": digest,
        "output": {"path": f"project://{output.relative_to(project).as_posix()}", "repo_path": repo_path},
        "technical_qc": technical, "elapsed_s": elapsed,
        "generated": True, "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT", "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False, "publish_authorized": False,
        "note": "Huashu Motion visuals are explanatory support, not execution evidence.",
    }
    _write_json(receipt_path, receipt)
    _write_json(output.with_suffix(".mp4.receipt.json"), receipt)

    assets_path = project / "sources" / "assets.json"
    asset_doc = _json(assets_path)
    entries = list(asset_doc.get("assets") or [])
    item = {"id": asset_id, "type": "GENERATED_VIDEO", "repo_path": repo_path,
            "sha256": digest, "permission": "CREATED_BY_OWNER",
            "usage_scope": "VISUAL_SUPPORT only", "origin": "huashu-motion local code render",
            "notes": "Generated visual; source claims remain separately registered."}
    old = next((row for row in entries if row.get("id") == asset_id), None)
    if old and old.get("repo_path") not in (repo_path, None):
        raise BackendError(f"asset id {asset_id} already points to a different file")
    if old:
        entries[entries.index(old)] = {**old, **item}
    else:
        entries.append(item)
    asset_doc["assets"] = entries
    _write_json(assets_path, asset_doc)
    script_assets_path = project / "script" / "assets.json"
    script_assets = _json(script_assets_path) if script_assets_path.is_file() else {"assets": {}}
    mapped = script_assets.get("assets")
    if not isinstance(mapped, dict):
        raise BackendError("script/assets.json does not contain an assets object")
    mapped[asset_id] = {"path": f"project://{output.relative_to(project).as_posix()}",
                        "sha256": digest, "evidence_use": "VISUAL_SUPPORT", "generated": True}
    script_assets["assets"] = mapped
    _write_json(script_assets_path, script_assets)
    return {"state": "EXECUTED", "reused": False, "output": output,
            "receipt": receipt_path, "technical_qc": technical,
            "fingerprint": fingerprint, "runtime": facts, "elapsed_s": elapsed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--film", required=True, help="project-relative Huashu Motion film directory")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--placement-id", required=True)
    parser.add_argument("--account-id", default="")
    parser.add_argument("--expected-duration", type=float)
    args = parser.parse_args(argv)
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    try:
        result = render(project, args.film, args.asset_id, args.placement_id,
                        args.account_id, args.expected_duration)
        public_result = {**result, "output": str(result["output"]),
                         "receipt": str(result["receipt"])}
        print(json.dumps({"execution": {"state": result["state"],
                                         "operation": "render", "reused": result["reused"],
                                         "adapter_receipt": public_result},
                          "receipt": f"project://{result['receipt'].relative_to(project).as_posix()}",
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False))
        return 0
    except (BackendError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"execution": {"state": "FAILED", "operation": "render",
                                         "external_effect": False, "error": str(exc)},
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
