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
    if source and str(source.get("type") or "").upper() == "CODE_SNAPSHOT":
        candidate = (ROOT / str(source.get("repo_path") or "")).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            raise BackendError("automatic Huashu Motion source escapes the repository") from None
        if candidate.is_file():
            source_path = candidate
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
        ribbon_by_kind = {
            "retrieval": ("QUERY", "RECALL", "FUSION", "RERANK"),
            "agent": ("INPUT", "STATE", "ACTION", "OUTPUT"),
            "protocol": ("CALL", "SERVER", "RESPONSE"),
            "code": ("SOURCE", "LOGIC", "RESULT"),
        }
        ribbon_labels = ribbon_by_kind.get(str(shot.get("semantic_class") or "code"),
                                           ("SOURCE", "DETAIL", "RESULT"))
        ribbon_markup = "<i>→</i>".join(f"<span>{html.escape(value)}</span>"
                                           for value in ribbon_labels)
        image_markup = (
            '<section class="editor"><div class="editor-bar"><b></b><b></b><b></b>'
            f'<span>{filename} · PINNED SOURCE</span></div><div class="code">{"".join(rows)}</div>'
            '<div class="editor-foot">SOURCE EXCERPT · NOT A LIVE EXECUTION</div></section>'
            f'<div class="stage-ribbon">{ribbon_markup}</div>'
        )
        image_animation = (
            "tl.fromTo('.editor',{y:90,opacity:0},{y:0,opacity:1,duration:.42})"
            f".fromTo('.row-0',{{x:-90,opacity:0}},{{x:0,opacity:1,duration:.3}},.4)"
            ".fromTo('.code-row:not(.row-0)',{x:90,opacity:0},{x:0,opacity:1,duration:.26,stagger:.14},.55)"
            f".to('.row-{active}',{{backgroundColor:'#182B38',borderColor:'{palette['accent']}',duration:.25}},1.1)"
            ".fromTo('.stage-ribbon span,.stage-ribbon i',{y:30,opacity:0},{y:0,opacity:1,duration:.22,stagger:.1},1.45);"
        )
        material_lines.append(f"- Source excerpt comes from `{source.get('source_document')}`; source SHA-256 `{_sha(source_text_path)}`.")
        if source_path:
            material_lines.append(f"- The registered source screenshot is retained in `assets/source.png`; SHA-256 `{_sha(source_path)}`.")
            shutil.copy2(source_path, assets_dir / "source.png")
    elif source_path:
        shutil.copy2(source_path, assets_dir / "source.png")
        image_markup = '<img class="source" src="assets/source.png" alt="pinned source screenshot">'
        image_animation = "tl.fromTo('.source',{scale:1.08,opacity:.45},{scale:1,opacity:1,duration:.52});"
        material_lines.append(f"- `assets/source.png`: registered source image; SHA-256 `{_sha(source_path)}`.")
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
            "tl.fromTo('.hero-label',{x:-120,opacity:0},{x:0,opacity:1,duration:.35})"
            ".fromTo('.node',{y:90,opacity:0},{y:0,opacity:1,duration:.35,stagger:.3},.35)"
            ".fromTo('.stage-rail b',{scaleX:0},{scaleX:1,duration:.35,stagger:.28},.6)"
            ".fromTo('.diagram-note',{opacity:0},{opacity:1,duration:.25},1.8);"
        )
    scene_title = html.escape(str(shot.get("content_point") or line.get("caption") or "").strip()[:64])
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
h1{{position:absolute;left:68px;right:68px;top:230px;margin:0;font-size:58px;line-height:1.16}}
.editor{{position:absolute;left:30px;right:30px;top:410px;height:1250px;background:#11161E;border:1px solid {colors['surface']};overflow:hidden}}
.editor-bar{{height:78px;background:{colors['surface']};display:flex;align-items:center;gap:10px;padding:0 28px;color:{colors['sub']};font:19px ui-monospace,monospace;letter-spacing:1px}}
.editor-bar b{{width:12px;height:12px;border-radius:50%;background:{colors['sub']};opacity:.6}}.editor-bar b:first-child{{background:#F07167}}.editor-bar b:nth-child(2){{background:#F2A93B}}.editor-bar b:nth-child(3){{background:{colors['accent']}}}.editor-bar span{{margin-left:18px}}
.code{{padding:34px 28px}}.code-row{{display:flex;align-items:flex-start;min-height:88px;padding:18px 16px;border-left:5px solid transparent;border-bottom:1px solid #242B35;background:#141A23;margin-bottom:7px}}
.code-row i{{font:22px ui-monospace,monospace;color:{colors['sub']};font-style:normal;min-width:80px}}.code-row code{{font:24px/1.4 ui-monospace,monospace;color:#E8EDF3;overflow:hidden;overflow-wrap:anywhere}}
.editor-foot{{position:absolute;left:28px;right:28px;bottom:22px;color:{colors['sub']};font:17px ui-monospace,monospace;letter-spacing:1px}}
.source{{position:absolute;left:0;top:410px;width:100%;height:1250px;object-fit:cover;object-position:center;transform-origin:center}}
.hero-label{{position:absolute;left:72px;right:72px;top:400px;font-size:54px;font-weight:700;line-height:1.2}}
.stage-rail{{position:absolute;left:160px;right:160px;top:690px;display:flex;align-items:center;justify-content:space-between;color:{colors['accent']};font:700 26px ui-monospace,monospace}}
.stage-rail b{{height:4px;flex:1;background:{colors['surface']};transform-origin:left;margin:0 20px}}
.flow{{position:absolute;left:0;right:0;top:800px;height:680px}}
.node{{position:absolute;left:90px;right:90px;height:170px;padding:34px 40px;background:{colors['surface']};border-left:8px solid {colors['accent']};font:700 42px ui-monospace,monospace;display:flex;align-items:center;letter-spacing:2px}}
.first{{top:0}}.second{{top:220px;border-color:{colors['accent2']}}}.third{{top:440px;border-color:{colors['accent']}}}
.diagram-note{{position:absolute;left:72px;bottom:130px;color:{colors['sub']};font:18px ui-monospace,monospace;letter-spacing:1px}}
.footer{{position:absolute;left:72px;bottom:118px;color:{colors['sub']};font:20px ui-monospace,monospace;letter-spacing:1px}}
</style></head><body><main id="film" data-composition-id="film" data-width="1080" data-height="1920">
<div class="eyebrow">{evidence_label}　·　{placement}</div><h1>{scene_title}</h1>{image_markup}
<div class="footer">CONTENTOPS / MOTION</div></main>
<script>window.__timelines=window.__timelines||{{}};const tl=gsap.timeline({{paused:true,defaults:{{ease:"power2.out"}}}});
tl.fromTo('.eyebrow',{{x:-45,opacity:0}},{{x:0,opacity:1,duration:.32}}).fromTo('h1',{{y:45,opacity:0}},{{y:0,opacity:1,duration:.42}},.12);
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
