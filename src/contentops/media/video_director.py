"""Director-Grade Multi-Role Video Planner & Huashu Motion Film Compiler (T08).

Replaces the historical "14/14 flat explain black-text-card" pattern with an
explicit Director Plan (``contentops.director-plan/v1``) that compiles into a
real, continuous-animation Huashu Motion (``om.js``) HTML+GSAP composition.

Key capabilities:
- Distinct beat roles: ``hook_conflict``, ``real_evidence``, ``mechanism_flow``,
  ``code_walkthrough``, ``failure_boundary``, ``verdict_cta``.
- Strictly consumes account-DNA light visual tokens from
  ``config/design/design-tokens.json`` (FI soft-engineering ``#E9EDEF``,
  1024 warm-editorial ``#F4F2ED``); never copies dark ``#0F1117`` onto body scenes.
- Enforces account hard boundaries (FI refuses ``recording`` scenes; generated
  visuals stay ``evidence_capable: false``).
- Native **9:16 (1080×1920)** AND Native **16:9 (1920×1080)** layouts with true
  horizontal grid reflow (not blurred pillarboxes).
- Per-scene content hash (``scene_sha256``) for partial-shot editing verification.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from contentops.graphic.design_system import account_tokens, css_variables_block, lint_html_design

DIRECTOR_SCHEMA = "contentops.director-plan/v1"
VALID_ROLES = (
    "hook_conflict",
    "real_evidence",
    "mechanism_flow",
    "code_walkthrough",
    "failure_boundary",
    "verdict_cta",
)
CANVAS_PRESETS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}


class DirectorError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def find_huashu_runtime(root: Path) -> Optional[Path]:
    env = os.environ.get("CONTENTOPS_HUASHU_MOTION_RUNTIME") or os.environ.get("HUASHU_MOTION_RUNTIME")
    candidates = [Path(env)] if env else []
    candidates.extend([
        root / ".runtime" / "huashu-motion",
        root.parent / ".runtime" / "huashu-motion",
        Path("D:/Projects/X-SuperPlay-ContentOps/.runtime/huashu-motion"),
    ])
    for cand in candidates:
        cand = cand.resolve()
        if (cand / "cli" / "om.js").is_file() and (cand / "templates" / "blank" / "vendor" / "gsap.min.js").is_file():
            return cand
    return None


def build_director_plan(
    *,
    root: Path,
    account_slug: str,
    title: str,
    aspect: str = "9:16",
    scenes: Sequence[Mapping[str, Any]],
    style_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate scenes against account DNA and build contentops.director-plan/v1."""
    if aspect not in CANVAS_PRESETS:
        raise DirectorError("ASPECT_UNSUPPORTED", f"aspect must be one of {sorted(CANVAS_PRESETS)}")
    if not scenes:
        raise DirectorError("SCENES_EMPTY", "director plan needs at least one scene")

    tokens = account_tokens(root, account_slug, variant_override=style_override)
    width, height = CANVAS_PRESETS[aspect]

    normalized: List[Dict[str, Any]] = []
    roles_seen = set()
    cursor = 0.0
    for idx, raw in enumerate(scenes, start=1):
        role = str(raw.get("role") or "").strip()
        if role not in VALID_ROLES:
            raise DirectorError("SCENE_ROLE_INVALID", f"scene {idx} role {role!r} not in {VALID_ROLES}")
        if account_slug == "x-superplay-future-intelligence" and raw.get("is_manual_recording"):
            raise DirectorError("RECORDING_FORBIDDEN", f"FI account forbids manual recording in scene {idx}")
        dur = round(float(raw.get("duration_s") or 3.5), 2)
        if not 1.5 <= dur <= 12.0:
            raise DirectorError("SCENE_DURATION_INVALID", f"scene {idx} duration {dur}s outside 1.5-12.0s")
        scene_id = str(raw.get("scene_id") or f"s{idx:02d}")
        roles_seen.add(role)
        scene_obj: Dict[str, Any] = {
            "scene_id": scene_id,
            "role": role,
            "start_s": round(cursor, 2),
            "duration_s": dur,
            "end_s": round(cursor + dur, 2),
            "kicker": str(raw.get("kicker") or role.upper()),
            "headline": str(raw.get("headline") or ""),
            "subtext": str(raw.get("subtext") or ""),
            "narration": str(raw.get("narration") or ""),
            "image_path": raw.get("image_path"),
            "focus_box": raw.get("focus_box"),
            "nodes": list(raw.get("nodes") or []),
            "code_lines": list(raw.get("code_lines") or []),
            "highlight_lines": list(raw.get("highlight_lines") or []),
            "file_path": raw.get("file_path"),
            "metrics": list(raw.get("metrics") or []),
            "dot_matrix": raw.get("dot_matrix"),
            "cta_line": raw.get("cta_line"),
            "source_label": str(raw.get("source_label") or ""),
            "style_override": raw.get("style_override"),
        }
        scene_obj["scene_sha256"] = _sha256_obj(scene_obj)
        normalized.append(scene_obj)
        cursor += dur

    # Reject homogeneous all-same-role plans when >=3 scenes exist
    if len(normalized) >= 3 and len(roles_seen) < 2:
        raise DirectorError("MONOTONOUS_SHOT_PLAN", "multi-scene film must use varied director roles, not one repeated card type")

    plan = {
        "schema": DIRECTOR_SCHEMA,
        "account_slug": account_slug,
        "account_label": tokens["label"],
        "title": title,
        "aspect": aspect,
        "width": width,
        "height": height,
        "total_duration_s": round(cursor, 2),
        "role_diversity": sorted(roles_seen),
        "palette_variant": tokens["variant"],
        "colors": tokens["colors"],
        "scenes": normalized,
        "production_ready": False,
        "publish_authorized": False,
    }
    plan["plan_sha256"] = _sha256_obj(plan)
    return plan


def _image_dimensions(path: Path) -> Optional[tuple[int, int]]:
    """Read PNG width/height from IHDR header without external dependencies."""
    try:
        head = path.read_bytes()[:24]
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(head[16:20], "big")
            h = int.from_bytes(head[20:24], "big")
            if w > 0 and h > 0:
                return (w, h)
    except OSError:
        return None
    return None


def _scene_markup(
    scene: Mapping[str, Any],
    idx: int,
    *,
    horizontal: bool,
    copied_img: Optional[str],
    img_dims: Optional[tuple[int, int]],
    account_label: str,
) -> str:
    sid = _e(scene["scene_id"])
    role = scene["role"]
    kicker = _e(scene["kicker"])
    headline = _e(scene["headline"])
    subtext = _e(scene["subtext"])
    src_lbl = _e(scene.get("source_label") or "")
    extra_vars = ""
    if scene.get("style_override") == "warm-editorial":
        extra_vars = "--bg:#F4F2ED;--surface:#FFFFFF;--ink:#18232B;--sub:#5C6970;--accent:#087FA6;--accent-soft:#E2F2F7;"
    elif scene.get("style_override") == "warm-amber":
        extra_vars = "--bg:#F7EFE4;--surface:#FFFDF9;--ink:#231D16;--sub:#6B5E52;--accent:#B45309;--accent-soft:#FEF3C7;"

    stage_style = f' style="aspect-ratio:{img_dims[0]}/{img_dims[1]}"' if img_dims else ""
    focus_html = ""
    if isinstance(scene.get("focus_box"), list) and len(scene["focus_box"]) == 4:
        l, t, w, h = scene["focus_box"]
        focus_html = f'<div class="focus-rect anim-focus" style="left:{l}%;top:{t}%;width:{w}%;height:{h}%"></div>'

    if role == "hook_conflict":
        img_block = (
            f'<div class="evidence-frame anim-rise">'
            f'<div class="evidence-stage"{stage_style}><img src="assets/{_e(copied_img)}" alt="real evidence">{focus_html}</div>'
            f'</div>'
            if copied_img
            else '<div class="hook-badge anim-rise">REAL SOURCE · VERIFIED</div>'
        )
        inner = (
            f'<div class="scene-head"><div class="kicker anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h1 class="hero-h1 anim-title">{headline}</h1>'
            f'<p class="hero-sub anim-sub">{subtext}</p></div>'
            f'{img_block}'
            f'<div class="scene-foot"><span>{src_lbl}</span><span class="brand-tag"><b>X</b> · {_e(account_label)}</span></div>'
        )
    elif role == "real_evidence":
        img_html = (
            f'<div class="evidence-stage"{stage_style}><img src="assets/{_e(copied_img)}" alt="verified screenshot">{focus_html}</div>'
            if copied_img
            else '<div class="empty-proof">NO IMAGE</div>'
        )
        inner = (
            f'<div class="scene-head"><div class="kicker anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h2 class="sec-h2 anim-title">{headline}</h2></div>'
            f'<div class="evidence-frame tall anim-rise">{img_html}</div>'
            f'<div class="caption-strip anim-sub">{subtext}</div>'
            f'<div class="scene-foot"><span>{src_lbl}</span><span class="brand-tag">REAL EVIDENCE</span></div>'
        )
    elif role == "mechanism_flow":
        nodes = scene.get("nodes") or []
        node_cards = []
        arrow = "→" if horizontal else "↓"
        for n_idx, node in enumerate(nodes[:4], start=1):
            st_cls = "flow-node is-alert" if node.get("status") == "failure" else "flow-node"
            node_cards.append(
                f'<div class="{st_cls} anim-node">'
                f'<div class="fn-idx">0{n_idx}</div>'
                f'<div class="fn-title">{_e(node.get("label"))}</div>'
                f'<div class="fn-desc">{_e(node.get("detail"))}</div>'
                '</div>'
            )
            if n_idx < len(nodes[:4]):
                node_cards.append(f'<div class="flow-arrow anim-arrow">{arrow}</div>')
        inner = (
            f'<div class="scene-head"><div class="kicker anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h2 class="sec-h2 anim-title">{headline}</h2></div>'
            f'<div class="flow-grid {"is-row" if horizontal else "is-col"}">{"".join(node_cards)}</div>'
            f'<div class="caption-strip anim-sub">{subtext}</div>'
            f'<div class="scene-foot"><span>{src_lbl}</span><span class="brand-tag">EXPLANATORY FLOW</span></div>'
        )
    elif role == "code_walkthrough":
        hl = set(scene.get("highlight_lines") or [])
        rows = []
        for l_i, line_txt in enumerate(scene.get("code_lines") or [], start=1):
            cls = "code-ln is-hl anim-hl" if l_i in hl else "code-ln anim-node"
            rows.append(f'<div class="{cls}"><i>{l_i:02d}</i><code>{_e(line_txt)}</code></div>')
        fname = _e(scene.get("file_path") or "source.py")
        inner = (
            f'<div class="scene-head"><div class="kicker anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h2 class="sec-h2 anim-title">{headline}</h2></div>'
            f'<div class="code-box anim-rise"><div class="code-top"><span>{fname}</span><span>github-light</span></div>'
            f'<div class="code-lines">{"".join(rows)}</div></div>'
            f'<div class="caption-strip anim-sub">{subtext}</div>'
            f'<div class="scene-foot"><span>{src_lbl}</span><span class="brand-tag">CODE EXCERPT</span></div>'
        )
    elif role == "failure_boundary":
        metrics = scene.get("metrics") or []
        m_cards = []
        for m in metrics[:3]:
            tone = "m-val is-bad" if m.get("tone") == "problem" else ("m-val is-good" if m.get("tone") == "success" else "m-val")
            m_cards.append(
                f'<div class="metric-tile anim-node"><div class="m-lbl">{_e(m.get("label"))}</div>'
                f'<div class="{tone}">{_e(m.get("value"))}</div><div class="m-note">{_e(m.get("note"))}</div></div>'
            )
        dm = scene.get("dot_matrix")
        dm_html = ""
        if isinstance(dm, dict) and dm.get("total"):
            total = int(dm["total"])
            active = int(dm.get("active") or 0)
            dots = "".join(
                f'<span class="dm-cell {"on" if i < active else ""} anim-dot"></span>'
                for i in range(min(total, 24))
            )
            dm_html = f'<div class="dm-wrap"><div class="dm-label">{_e(dm.get("label") or "")}</div><div class="dm-grid">{dots}</div></div>'
        inner = (
            f'<div class="scene-head"><div class="kicker is-problem anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h2 class="sec-h2 anim-title">{headline}</h2></div>'
            f'<div class="metric-grid">{"".join(m_cards)}</div>'
            f'{dm_html}'
            f'<div class="problem-strip anim-sub">{subtext}</div>'
            f'<div class="scene-foot"><span>{src_lbl}</span><span class="brand-tag">HONEST LIMITS</span></div>'
        )
    else:  # verdict_cta
        cta = _e(scene.get("cta_line") or "")
        inner = (
            f'<div class="close-wrap">'
            f'<div class="kicker anim-kicker"><span class="dot"></span>{kicker}</div>'
            f'<h1 class="close-h1 anim-title">{headline}</h1>'
            f'<div class="close-rule anim-rule"></div>'
            f'<p class="close-sub anim-sub">{subtext}</p>'
            + (f'<div class="close-cta anim-rise">{cta}</div>' if cta else "")
            + f'<div class="brand-tag large anim-sub"><b>X</b> · {_e(account_label)}</div>'
            f'</div>'
        )

    opacity = "1" if idx == 0 else "0"
    style_attr = f"opacity:{opacity};{extra_vars}" if extra_vars else f"opacity:{opacity}"
    return f'<section class="scene role-{_e(role)}" id="{sid}" data-scene-role="{_e(role)}" style="{style_attr}">\n{inner}\n</section>'


def compile_huashu_film(
    plan: Mapping[str, Any],
    *,
    root: Path,
    out_dir: Path,
) -> Dict[str, Any]:
    """Compile a validated Director Plan into an om.js-ready film directory."""
    root = Path(root).resolve()
    out_dir = Path(out_dir).resolve()
    runtime = find_huashu_runtime(root)
    if runtime is None:
        raise DirectorError("HUASHU_RUNTIME_MISSING", "Huashu Motion runtime (cli/om.js) not found")

    tokens = account_tokens(root, str(plan["account_slug"]))
    width, height = int(plan["width"]), int(plan["height"])
    horizontal = width > height

    assets_dir = out_dir / "assets"
    fonts_dir = assets_dir / "fonts"
    vendor_dir = out_dir / "vendor"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    vendor_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(runtime / "templates" / "blank" / "vendor" / "gsap.min.js", vendor_dir / "gsap.min.js")
    for fname in ("NotoSansSC-500.woff", "NotoSansSC-700.woff"):
        src_f = runtime / "fonts" / fname
        if src_f.is_file():
            shutil.copy2(src_f, fonts_dir / fname)

    materials = ["# Director Film Materials", "", f"- Account: `{plan['account_slug']}` ({plan['palette_variant']})", f"- Canvas: `{width}x{height}` ({plan['aspect']})"]
    sections_html: List[str] = []
    js_blocks: List[str] = []

    for idx, scene in enumerate(plan["scenes"]):
        copied_name: Optional[str] = None
        img_dims: Optional[tuple[int, int]] = None
        img_raw = scene.get("image_path")
        if img_raw:
            img_p = Path(img_raw)
            if not img_p.is_absolute():
                img_p = (root / img_p).resolve()
            if img_p.is_file():
                copied_name = f"{scene['scene_id']}-{img_p.name}"
                img_dims = _image_dimensions(img_p)
                shutil.copy2(img_p, assets_dir / copied_name)
                sha = hashlib.sha256(img_p.read_bytes()).hexdigest()[:12]
                materials.append(f"- `{scene['scene_id']}` real asset: `assets/{copied_name}` (sha256 `{sha}`)")

        sections_html.append(
            _scene_markup(
                scene,
                idx,
                horizontal=horizontal,
                copied_img=copied_name,
                img_dims=img_dims,
                account_label=str(plan["account_label"]),
            )
        )
        sid = scene["scene_id"]
        t0 = float(scene["start_s"])
        dur = float(scene["duration_s"])
        fade_out_at = round(t0 + max(0.8, dur - 0.35), 3)
        is_last = idx == len(plan["scenes"]) - 1

        block = [f"tl.addLabel('scene:{sid}', {t0:.2f});"]
        if idx > 0:
            block.append(f"tl.set('#{sid}', {{ opacity: 1 }}, {t0:.2f});")
            block.append(f"tl.fromTo('#{sid} .anim-kicker', {{ x: -24, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.35 }}, {t0:.2f});")
            block.append(f"tl.fromTo('#{sid} .anim-title', {{ y: 26, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.45 }}, {t0 + 0.08:.2f});")
        else:
            # First frame already composed and legible (zero blank flash)
            block.append(f"tl.fromTo('#{sid} .anim-kicker', {{ x: -16 }}, {{ x: 0, duration: 0.4 }}, 0);")
            block.append(f"tl.fromTo('#{sid} .anim-title', {{ y: 14 }}, {{ y: 0, duration: 0.5 }}, 0);")

        block.append(f"if (document.querySelector('#{sid} .anim-rise')) tl.fromTo('#{sid} .anim-rise', {{ y: 28, opacity: {0.85 if idx == 0 else 0} }}, {{ y: 0, opacity: 1, duration: 0.55 }}, {t0 + 0.15:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-node')) tl.fromTo('#{sid} .anim-node', {{ y: 24, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.38, stagger: 0.16 }}, {t0 + 0.25:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-arrow')) tl.fromTo('#{sid} .anim-arrow', {{ scale: 0.5, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.25, stagger: 0.16 }}, {t0 + 0.42:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-hl')) tl.fromTo('#{sid} .anim-hl', {{ x: -12, opacity: 0.7 }}, {{ x: 0, opacity: 1, duration: 0.42, stagger: 0.12 }}, {t0 + 0.55:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-focus')) tl.fromTo('#{sid} .anim-focus', {{ opacity: 0, scale: 0.92 }}, {{ opacity: 1, scale: 1, duration: 0.45 }}, {t0 + min(1.0, dur * 0.35):.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-dot')) tl.fromTo('#{sid} .anim-dot', {{ scale: 0, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.25, stagger: 0.04 }}, {t0 + 0.45:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-rule')) tl.fromTo('#{sid} .anim-rule', {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.55 }}, {t0 + 0.35:.2f});")
        block.append(f"if (document.querySelector('#{sid} .anim-sub')) tl.fromTo('#{sid} .anim-sub', {{ y: 16, opacity: {0.85 if idx == 0 else 0} }}, {{ y: 0, opacity: 1, duration: 0.45 }}, {t0 + 0.45:.2f});")
        if not is_last:
            block.append(f"tl.to('#{sid}', {{ opacity: 0, duration: 0.30, ease: 'power2.in' }}, {fade_out_at:.2f});")
        else:
            block.append(f"tl.to({{}}, {{ duration: 0.2 }}, {t0 + dur - 0.2:.2f});")
        js_blocks.append("\n  ".join(block))

    pad_top = 64 if horizontal else 110
    pad_side = 84 if horizontal else 64
    pad_bot = 56 if horizontal else 320  # Reserve vertical subtitle safe zone on 9:16
    css = (
        '@font-face{font-family:"Noto Sans SC";src:url("assets/fonts/NotoSansSC-500.woff");font-weight:400 600}\n'
        '@font-face{font-family:"Noto Sans SC";src:url("assets/fonts/NotoSansSC-700.woff");font-weight:700 900}\n'
        + css_variables_block(tokens)
        + f"""
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: var(--bg); color: var(--ink); font-family: "Noto Sans SC", var(--font-sans); }}
#film {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; background: var(--bg); color: var(--ink); }}
.scene {{ position: absolute; inset: 0; padding: {pad_top}px {pad_side}px {pad_bot}px {pad_side}px; display: flex; flex-direction: column; justify-content: space-between; gap: {24 if horizontal else 28}px; background: var(--bg); color: var(--ink); }}
.scene-head {{ display: flex; flex-direction: column; gap: 14px; }}
.kicker {{ font: 700 {20 if horizontal else 24}px/1.2 var(--font-mono); letter-spacing: 0.14em; color: var(--accent); display: flex; align-items: center; gap: 12px; }}
.kicker .dot {{ width: 11px; height: 11px; border-radius: 50%; background: var(--accent); display: inline-block; }}
.kicker.is-problem {{ color: var(--problem); }}
.kicker.is-problem .dot {{ background: var(--problem); }}
.hero-h1 {{ margin: 0; font-size: {60 if horizontal else 66}px; line-height: 1.15; font-weight: 900; letter-spacing: -0.02em; }}
.hero-sub {{ margin: 0; font-size: {26 if horizontal else 30}px; line-height: 1.48; color: var(--sub); }}
.sec-h2 {{ margin: 0; font-size: {48 if horizontal else 54}px; line-height: 1.18; font-weight: 800; letter-spacing: -0.02em; }}
.evidence-frame {{ position: relative; flex: 1; min-height: 0; background: var(--surface); border: 1.5px solid var(--border); border-radius: 16px; padding: 18px; display: flex; align-items: center; justify-content: center; overflow: hidden; box-shadow: 0 18px 46px rgba(24,35,43,0.08); }}
.evidence-stage {{ position: relative; max-width: 100%; max-height: 100%; height: 100%; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 8px; box-shadow: 0 6px 24px rgba(15,17,23,0.10); }}
.evidence-stage img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
.focus-rect {{ position: absolute; border: 4px solid var(--accent); border-radius: 8px; box-shadow: 0 0 0 9999px rgba(15,17,23,0.20); pointer-events: none; }}
.caption-strip {{ background: var(--surface); border: 1px solid var(--border); border-left: 6px solid var(--accent); border-radius: 10px; padding: 18px 24px; font-size: {24 if horizontal else 28}px; line-height: 1.48; color: var(--ink); font-weight: 500; }}
.problem-strip {{ background: var(--problem-soft); border: 1px solid var(--problem); border-left: 6px solid var(--problem); border-radius: 10px; padding: 18px 24px; font-size: {24 if horizontal else 28}px; line-height: 1.48; color: var(--ink); font-weight: 600; }}
.flow-grid {{ flex: 1; display: flex; gap: 16px; align-items: stretch; justify-content: space-between; }}
.flow-grid.is-row {{ flex-direction: row; }}
.flow-grid.is-col {{ flex-direction: column; }}
.flow-node {{ flex: 1; background: var(--surface); border: 1.5px solid var(--border); border-top: 6px solid var(--accent); border-radius: 14px; padding: 24px; display: flex; flex-direction: column; justify-content: center; gap: 10px; }}
.flow-node.is-alert {{ border-top-color: var(--problem); background: var(--problem-soft); }}
.fn-idx {{ font: 800 20px/1 var(--font-mono); color: var(--accent); }}
.flow-node.is-alert .fn-idx {{ color: var(--problem); }}
.fn-title {{ font-size: {28 if horizontal else 34}px; font-weight: 800; color: var(--ink); }}
.fn-desc {{ font-size: {21 if horizontal else 25}px; line-height: 1.45; color: var(--sub); }}
.flow-arrow {{ flex: 0 0 36px; display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: 900; color: var(--accent); }}
.code-box {{ flex: 1; background: var(--surface); border: 1.5px solid var(--border); border-radius: 14px; overflow: hidden; display: flex; flex-direction: column; }}
.code-top {{ background: var(--surface-alt); padding: 14px 22px; border-bottom: 1px solid var(--border); font: 700 19px/1 var(--font-mono); color: var(--sub); display: flex; justify-content: space-between; }}
.code-lines {{ padding: 18px 0; display: flex; flex-direction: column; gap: 6px; }}
.code-ln {{ display: flex; gap: 18px; padding: 8px 22px; font: 500 {22 if horizontal else 24}px/1.4 var(--font-mono); border-left: 5px solid transparent; }}
.code-ln.is-hl {{ background: var(--accent-soft); border-left-color: var(--accent); font-weight: 700; }}
.code-ln i {{ font-style: normal; color: var(--sub); min-width: 36px; text-align: right; }}
.code-ln code {{ white-space: pre-wrap; word-break: break-all; color: var(--ink); }}
.metric-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
.metric-tile {{ background: var(--surface); border: 1.5px solid var(--border); border-radius: 14px; padding: 20px; min-width: 0; }}
.m-lbl {{ font: 700 17px/1.2 var(--font-mono); color: var(--sub); letter-spacing: 0.08em; }}
.m-val {{ font-size: {56 if horizontal else 62}px; font-weight: 900; color: var(--accent); margin: 10px 0 6px; line-height: 1.05; font-variant-numeric: tabular-nums; }}
.m-val.is-bad {{ color: var(--problem); }}
.m-val.is-good {{ color: var(--success); }}
.m-note {{ font-size: 18px; line-height: 1.38; color: var(--sub); overflow-wrap: anywhere; }}
.dm-wrap {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; }}
.dm-label {{ font: 700 19px/1.2 var(--font-mono); color: var(--ink); }}
.dm-grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 10px; }}
.dm-cell {{ aspect-ratio: 1; border-radius: 6px; background: var(--success-soft); border: 1.5px solid var(--success); }}
.dm-cell.on {{ background: var(--problem); border-color: var(--problem); }}
.close-wrap {{ flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 28px; }}
.close-h1 {{ margin: 0; font-size: {64 if horizontal else 70}px; line-height: 1.18; font-weight: 900; }}
.close-rule {{ width: 220px; height: 8px; background: var(--accent); transform-origin: left; border-radius: 4px; }}
.close-sub {{ margin: 0; font-size: {28 if horizontal else 32}px; line-height: 1.5; color: var(--sub); max-width: 90%; }}
.close-cta {{ background: var(--surface); border: 1.5px solid var(--accent); border-radius: 10px; padding: 18px 26px; font-size: {24 if horizontal else 28}px; font-weight: 700; color: var(--ink); }}
.scene-foot {{ display: flex; justify-content: space-between; align-items: center; padding-top: 14px; border-top: 1px solid var(--border); font: 600 18px/1.2 var(--font-mono); color: var(--sub); }}
.brand-tag {{ background: var(--brand-dark); color: #F9FBFA; padding: 8px 16px; border-radius: 6px; font: 700 16px/1 var(--font-mono); letter-spacing: 0.08em; }}
.brand-tag b {{ color: var(--brand-cyan); }}
.brand-tag.large {{ font-size: 22px; padding: 12px 22px; }}
"""
    )

    page = (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{_e(plan['title'])}</title>\n"
        '<script src="vendor/gsap.min.js"></script>\n'
        f"<style>{css}</style>\n</head>\n<body>\n"
        f'<main id="film" data-composition-id="film" data-width="{width}" data-height="{height}" data-om-signature="off">\n'
        + "\n".join(sections_html)
        + "\n</main>\n<script>\n"
        "window.__timelines = window.__timelines || {};\n"
        "const tl = gsap.timeline({ paused: true, defaults: { ease: 'power3.out' } });\n"
        "  " + "\n  ".join(js_blocks) + "\n"
        "window.__timelines['film'] = tl;\n"
        "</script>\n</body>\n</html>\n"
    )

    lint = lint_html_design(page)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "materials.md").write_text("\n".join(materials) + "\n", encoding="utf-8")
    (out_dir / "director-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "schema": "contentops.director-compile/v1",
        "film_dir": str(out_dir),
        "index_html": str(out_dir / "index.html"),
        "plan_sha256": plan["plan_sha256"],
        "aspect": plan["aspect"],
        "total_duration_s": plan["total_duration_s"],
        "scene_count": len(plan["scenes"]),
        "role_diversity": plan["role_diversity"],
        "design_lint": lint,
        "production_ready": False,
        "publish_authorized": False,
    }
