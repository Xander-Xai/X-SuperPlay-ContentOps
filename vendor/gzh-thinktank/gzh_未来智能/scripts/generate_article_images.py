#!/usr/bin/env python3
"""Execute the reviewed article visual plan through the shared provider.

The executor is intentionally boring: it only calls Agnes for records whose
director plan says ``generation_mode=agnes``.  Architecture/flow/code assets
stay on a deterministic renderer, while every output is written back with a
prompt, request, model, rights and SHA-256 provenance record.
"""

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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_image_prompt_plan import article_path, compile_plan, load_yaml  # noqa: E402
from visual_run_manifest import record as record_visual_run  # noqa: E402


IMAGE_CREATE = ROOT / "skills" / "gzh-visual-assets" / "scripts" / "image_create.py"
VISUAL_ANCHOR = ROOT / "scripts" / "render_visual_anchor.py"
COVER_COMPOSITOR = ROOT / "scripts" / "compose_editorial_cover.py"



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read rendered dimensions so provenance records actual, not requested, size."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except (ImportError, OSError, ValueError):
        return None


def request_sha256(item: dict, plan: dict) -> str:
    payload = {
        "provider": plan.get("provider"),
        "model": plan.get("model"),
        "kind": item.get("kind"),
        "generation_mode": item.get("generation_mode"),
        "size": item.get("size"),
        "ratio": item.get("ratio"),
        "prompt_sha256": item.get("sha256"),
        "code_style": item.get("code_style", ""),
        "reference_images": item.get("reference_images", []),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def clean_provider_error(value: str) -> str:
    """Keep an actionable, UTF-8-safe provider error in the audit trail."""
    text = str(value or "").strip()
    win_error = re.search(r"WinError\s+(\d+)", text, flags=re.I)
    if win_error:
        code = win_error.group(1)
        hint = "network timeout or unreachable endpoint" if code == "10060" else "Windows network error"
        return f"Agnes request failed: WinError {code} ({hint}); see command stderr for the provider response"
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "Agnes request failed: network timeout; see command stderr for the provider response"
    # Avoid persisting undecodable console bytes as a wall of U+FFFD.
    if "\ufffd" in text:
        return "Agnes request failed: provider output could not be decoded; see command stderr"
    return text[-1000:]


def section_body(article: Path, heading: str, limit: int = 240) -> str:
    """提取章节正文前 limit 字符，供封面/概念候选的可审计描述使用。

    去掉图片 marker 与 fenced code 块，避免把代码/占位当认知锚点文案。
    """
    source = article / "article.md"
    if not source.is_file():
        source = article / "draft.md"
    if not source.is_file():
        return ""
    text = source.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)", text, flags=re.M | re.S)
    if not match:
        return ""
    body = match.group(1)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)          # 图片 marker
    body = re.sub(r"```[\s\S]*?```", " ", body)                 # fenced code
    body = re.sub(r"`[^`]+`", " ", body)                        # inline code
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit]


def ensure_visual_plan_ready(article: Path) -> None:
    brief = load_yaml(article / "visual-brief.yaml")
    approval = brief.get("approval") if isinstance(brief, dict) else {}
    if not isinstance(approval, dict) or approval.get("cover_selection") != "approved":
        raise SystemExit("视觉计划尚未批准：先运行 visual_qa.py approve，再执行生图")
    if str(approval.get("reviewer_type", "")).strip() not in {"agent", "human"}:
        raise SystemExit("视觉计划缺少 reviewer_type=agent/human")
    director_path = article / "visual-director-plan.json"
    if not director_path.is_file():
        raise SystemExit("缺少 visual-director-plan.json：先运行 build_image_prompt_plan.py")
    try:
        director = json.loads(director_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"视觉导演计划不是有效 JSON：{exc}") from exc
    if director.get("contract") != "visual-director-v1" or director.get("status") not in {"ready", "approved", "generated"}:
        raise SystemExit("visual-director-plan.json 尚未达到 ready/approved 状态")


def update_sources(article: Path, plan: dict, *, executed: bool) -> None:
    source_path = article / "image-sources.json"
    data = {}
    if source_path.is_file():
        try:
            value = json.loads(source_path.read_text(encoding="utf-8"))
            data = value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            data = {}
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    by_path = {str(item.get("path")): item for item in assets if isinstance(item, dict)}
    prompt_records = plan.get("prompt_files", []) if isinstance(plan.get("prompt_files"), list) else []
    completed_statuses = {"generated", "fallback", "deterministic"}
    all_generated = executed and bool(prompt_records) and all(
        str(prompt.get("status", "")) in completed_statuses for prompt in prompt_records if isinstance(prompt, dict)
    )
    for prompt in prompt_records:
        if not isinstance(prompt, dict):
            continue
        asset_path = str(prompt.get("asset", ""))
        item = by_path.setdefault(asset_path, {"path": asset_path})
        status = str(prompt.get("status", "planned"))
        execution_provider = str(prompt.get("execution_provider") or plan.get("provider") or "").strip()
        execution_model = str(prompt.get("execution_model") or plan.get("model") or "").strip()
        execution_method = str(prompt.get("execution_method") or "text-to-image").strip()
        if execution_provider == "agnes":
            source = "Agnes Image 2.1 Flash"
            license_text = "AI-generated illustrative asset; human review required"
        elif execution_provider == "local-deterministic":
            source = "本地 SVG 视觉锚点渲染器（可编辑源文件）"
            license_text = "Deterministic local illustrative asset; human review required"
        elif execution_provider == "local-fallback" and str(prompt.get("id")) == "cover":
            source = "本地当前品牌主题封面生成器"
            license_text = "Deterministic local cover asset; human review required"
        else:
            source = "本地主题语义渲染器（可编辑源文件）"
            license_text = "Deterministic local illustrative asset; human review required"
        item.update({
            "origin": "generated",
            "source": source,
            "license": license_text,
            "reuse_approved": False,
            "generation": {
                "provider": execution_provider,
                "requested_provider": str(prompt.get("requested_provider") or plan.get("requested_provider") or plan.get("provider") or "").strip(),
                "model": execution_model,
                "method": execution_method,
                "prompt_file": prompt.get("path"),
                "prompt_sha256": prompt.get("sha256"),
                "visual_owner": prompt.get("visual_owner"),
                "viewer_job": prompt.get("viewer_job"),
                "claim_ids": prompt.get("claim_ids", []),
                "fallback": prompt.get("fallback"),
                "kind": prompt.get("kind"),
                "generation_mode": prompt.get("generation_mode"),
                "requested_backend": prompt.get("requested_backend") or prompt.get("render_backend"),
                "execution_backend": prompt.get("execution_backend") or prompt.get("render_backend"),
                "fallback_reason": prompt.get("fallback_reason", ""),
                "size": prompt.get("size"),
                "ratio": prompt.get("ratio"),
                "source_strategy": prompt.get("source_strategy"),
                "rights_status": prompt.get("rights_status"),
                "continuity_group": prompt.get("continuity_group"),
                "safe_area": prompt.get("safe_area"),
                "reference_images": prompt.get("reference_images", []),
                "cover_copy": prompt.get("cover_copy", {}),
                "cover_background": prompt.get("cover_background", ""),
                "cover_background_sha256": prompt.get("cover_background_sha256", ""),
                "cover_overlay_source": prompt.get("cover_overlay_source", ""),
                "cover_motif": prompt.get("cover_motif", ""),
                "skill_evaluation": prompt.get("skill_evaluation", []),
                "diagram_source": prompt.get("diagram_source"),
                "request_sha256": prompt.get("request_sha256"),
                "execution_mode": "real" if status == "generated" else ("deterministic" if status == "deterministic" else ("fallback" if status == "fallback" else "planned")),
                "status": status,
            },
        })
        output_raw = str(prompt.get("output") or asset_path).replace("\\", "/")
        rendered = (article / output_raw).resolve()
        dimensions = image_dimensions(rendered) if rendered.is_file() else None
        if dimensions:
            item["generation"]["requested_size"] = item["generation"].get("size")
            item["generation"]["size"] = f"{dimensions[0]}x{dimensions[1]}"
            item["generation"]["actual_size"] = f"{dimensions[0]}x{dimensions[1]}"
            item["actual_width"], item["actual_height"] = dimensions
        if prompt.get("output_sha256"):
            item["sha256"] = prompt["output_sha256"]
    data.update({"schema_version": 2, "status": "passed" if all_generated else "pending", "generation_contract": str(plan.get("generation_contract") or "prompt-v2"), "backend_contract": "visual-backend-v1", "assets": list(by_path.values())})
    source_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_visual_contract(article: Path, plan: dict) -> None:
    """Copy execution provenance into the semantic contract and brief."""
    contract_path = article / "visual-contract.json"
    if contract_path.is_file():
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            contract = {}
        by_id = {str(item.get("id")): item for item in plan.get("prompt_files", []) if isinstance(item, dict)}
        units = contract.get("units") if isinstance(contract.get("units"), list) else []
        for unit in units:
            if not isinstance(unit, dict):
                continue
            item = by_id.get(str(unit.get("id")))
            if not item:
                continue
            for key in ("status", "output", "diagram_source", "execution_provider", "execution_model", "execution_method", "output_sha256", "requested_provider", "content_signal", "public_brand", "requested_backend", "execution_backend", "fallback_reason", "skill_evaluation", "code_style", "cover_copy", "cover_background", "cover_background_sha256", "cover_overlay_source", "cover_motif"):
                if key in item:
                    unit[key] = item[key]
        contract["status"] = "generated" if plan.get("status") == "generated" else "partial"
        contract["updated_at"] = datetime.now(timezone.utc).isoformat()
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    brief_path = article / "visual-brief.yaml"
    if brief_path.is_file():
        brief = load_yaml(brief_path)
        statuses = {str(item.get("id")): str(item.get("status", "planned")) for item in plan.get("prompt_files", []) if isinstance(item, dict)}
        for item in brief.get("body_visuals", []) if isinstance(brief.get("body_visuals"), list) else []:
            if isinstance(item, dict) and str(item.get("id")) in statuses:
                item["status"] = statuses[str(item.get("id"))]
        try:
            import yaml  # type: ignore
            brief_path.write_text(yaml.safe_dump(brief, allow_unicode=True, sort_keys=False), encoding="utf-8")
        except ImportError:
            brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preserve_unselected_plan_records(plan: dict, previous_plan: dict, selected: set[str]) -> None:
    """Prevent ``--only cover`` from erasing completed body provenance.

    Compiling a fresh prompt plan intentionally starts every record in
    ``planned``.  That is correct for a full re-run, but a selective execution
    must be a patch operation: untouched deterministic assets keep their SVG
    source, output hash and execution receipt.  Without this merge, generating
    a replacement cover silently demoted every body visual and created false
    orphan reports.
    """
    if not selected:
        return
    old_records = {
        str(item.get("id") or ""): item
        for item in previous_plan.get("prompt_files", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    merged: list[dict] = []
    for item in plan.get("prompt_files", []) if isinstance(plan.get("prompt_files"), list) else []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "")
        if ident not in selected and ident in old_records:
            merged.append(old_records[ident])
        else:
            merged.append(item)
    plan["prompt_files"] = merged


def write_visual_run_manifest(article: Path, records: list[dict]) -> dict:
    """Record the successful render run after all ledgers have been updated."""
    inputs = ["visual-brief.yaml", "visual-contract.json", "image-generation-plan.json"]
    inputs.extend(
        str(item.get("path")) for item in records
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    )
    outputs: list[str] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        for key in ("output", "diagram_source", "cover_background", "cover_overlay_source"):
            value = str(item.get(key) or "").strip()
            if value and value not in outputs:
                outputs.append(value)
    return record_visual_run(
        article,
        stage="visual-render",
        command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        inputs=inputs,
        outputs=outputs,
        status="passed",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True)
    parser.add_argument("--provider", default="agnes", choices=("agnes", "local"))
    parser.add_argument("--model")
    parser.add_argument("--endpoint")
    parser.add_argument("--execute", action="store_true", help="实际调用 image_create.py；不传则只生成计划")
    parser.add_argument("--only", action="append", default=[], help="只执行指定 id，例如 body-01；可重复传入")
    parser.add_argument("--fallback-on-error", action="store_true", help="Agnes 不可达时仅对正文概念图使用语义本地渲染器；封面使用当前主题封面降级")
    parser.add_argument("--fallback-only", action="store_true", help="跳过外部 API，正文使用确定性语义渲染器，封面使用当前主题封面降级")
    parser.add_argument("--output-dir", type=Path, help="图片输出目录；默认使用文章 imgs/ 并覆盖对应资产")
    args = parser.parse_args()
    article = article_path(args.article)
    previous_errors: list[dict[str, str]] = []
    previous_plan: dict = {}
    previous_plan_path = article / "image-generation-plan.json"
    if previous_plan_path.is_file():
        try:
            previous_plan = json.loads(previous_plan_path.read_text(encoding="utf-8"))
            if isinstance(previous_plan.get("execution_errors"), list):
                previous_errors = [
                    {"id": str(item.get("id", "")), "error": clean_provider_error(str(item.get("error", "")))}
                    for item in previous_plan["execution_errors"]
                    if isinstance(item, dict)
                ]
        except (OSError, json.JSONDecodeError):
            previous_errors = []
    plan = compile_plan(article, args.provider, args.model, args.endpoint)
    selected = set(args.only)
    preserve_unselected_plan_records(plan, previous_plan, selected)
    records = [item for item in plan.get("prompt_files", []) if not selected or item.get("id") in selected]
    if args.only and not records:
        raise SystemExit(f"没有匹配的图片 id：{', '.join(sorted(selected))}")
    if not args.execute:
        update_sources(article, plan, executed=False)
        print(f"IMAGE PLAN ONLY: {len(records)} prompts; no external API call")
        return 0
    if args.provider != "agnes":
        raise SystemExit("当前执行器只允许 provider=agnes；正文本地渲染请使用 --fallback-only")
    ensure_visual_plan_ready(article)
    if args.fallback_only:
        args.fallback_on_error = True
    output_dir = (args.output_dir or (article / "imgs")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    article_meta = load_yaml(article / "article.yaml")
    account = str(article_meta.get("account") or _default_account())
    title = str(article_meta.get("title") or plan.get("title") or article.name)
    public_brand = str(plan.get("public_brand") or article_meta.get("public_brand") or "X超玩•未来智能")
    poster = ROOT / "skills" / "gzh-visual-assets" / "scripts" / "text_poster.py"

    def compose_cover(item: dict, output_path: Path) -> None:
        """Keep Agnes as the visual author, but render exact English locally."""
        copy = item.get("cover_copy") if isinstance(item.get("cover_copy"), dict) else {}
        required = ("eyebrow", "headline", "keywords", "caption", "motif")
        if not all(str(copy.get(field) or "").strip() for field in required):
            raise RuntimeError("cover 缺少可信英文标题合同（cover_copy）")
        background = output_path.with_name("cover-agnes-background.png")
        overlay = article / "imgs" / "diagram-sources" / "cover-overlay.svg"
        # Preserve raw Agnes bytes before replacing cover.png with the
        # composed deliverable.  Copy (rather than move) keeps recovery safe
        # if the compositor fails.
        shutil.copy2(output_path, background)
        command = [
            sys.executable, str(COVER_COMPOSITOR),
            "--background", str(background),
            "--output", str(output_path),
            "--svg-output", str(overlay),
            "--eyebrow", str(copy["eyebrow"]),
            "--headline", str(copy["headline"]),
            "--keywords", str(copy["keywords"]),
            "--caption", str(copy["caption"]),
            "--motif", str(copy["motif"]),
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if result.returncode or not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "封面英文叠字渲染失败")
        item["cover_background"] = str(background.relative_to(article)).replace("\\", "/")
        item["cover_background_sha256"] = sha256_file(background)
        item["cover_overlay_source"] = str(overlay.relative_to(article)).replace("\\", "/")
        source_method = "agnes-text-to-image" if str(item.get("execution_provider") or "").strip().lower() == "agnes" else "local-cover-background"
        item["execution_method"] = source_method + " + deterministic-English-overlay-chrome"

    def render_fallback(item: dict, output_path: Path) -> None:
        item_id = str(item.get("id") or "body-01")
        theme = "sentinel-radar" if account == "sentinel" else "thinktank-atlas"
        if item_id != "cover":
            raise RuntimeError("正文禁止使用 text_poster；请走语义确定性渲染器")
        command = [
            sys.executable, str(poster), "generate", "--title", title,
            "--subtitle", "当前主题视觉封面",
            "--tag", "AI视觉锚点", "--theme", theme,
            "--width", "900", "--height", "383", "-o", str(output_path),
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError((result.stdout + result.stderr).strip() or "text_poster.py 失败")
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError(f"本地降级输出无效：{output_path}")
        # 增强 2：fallback 渲染自检——尺寸必须满足 600x300 契约，早于门禁拦截。
        try:
            from PIL import Image as _PILImage

            with _PILImage.open(output_path) as im:
                _w, _h = im.size
                if _w < 600 or _h < 300:
                    raise RuntimeError(
                        f"本地降级输出尺寸不足 600x300：{item_id} {_w}x{_h}"
                    )
        except (ImportError, OSError) as exc:
            raise RuntimeError(f"本地降级输出无法校验尺寸：{item_id} -> {exc}")

    def render_deterministic(item: dict, output_path: Path) -> tuple[str, str | None]:
        """Render an editable semantic SVG; never hide a technical failure."""
        item_id = str(item.get("id") or "body-01")
        backend = str(item.get("requested_backend") or item.get("render_backend") or "").strip().lower()
        # katex / infographic / code-block 都产出 HTML 源文件，其余是可编辑 SVG。
        # 后缀必须与 render_visual_anchor 实际写出的文件一致，否则 provenance
        # 会指向一个不存在的路径。
        is_checklist = str(item.get("kind") or item.get("visual_type") or "").strip().lower() == "checklist"
        html_backends = backend.startswith("katex-") or backend in {"code-block", "formula-code-map"} or (backend == "deterministic-infographic" and not is_checklist)
        html_kinds = str(item.get("kind") or "").strip().lower() in {"code", "pseudocode", "formula-code-map"}
        source_suffix = ".html" if html_backends or html_kinds else ".svg"
        source_path = article / "imgs" / "diagram-sources" / f"{item_id}{source_suffix}"
        # Remove a wrapper produced by an older Mermaid route when the current
        # contract selects a pure SVG backend.  Leaving that stale file beside
        # the source makes auditors inspect an artifact that is no longer part
        # of the render path and can resurrect obsolete black-block evidence.
        if source_suffix == ".svg":
            stale_wrapper = source_path.with_suffix(".html")
            if stale_wrapper.is_file():
                stale_wrapper.unlink()
        command = [
            sys.executable,
            str(VISUAL_ANCHOR),
            "--title", str(item.get("section") or item.get("viewer_job") or item_id),
            "--description", str(item.get("viewer_job") or "一张图只承担一个认知动作"),
            "--kind", str(item.get("kind") or "architecture"),
            "--index", str(item_id.rsplit("-", 1)[-1] if "-" in item_id else 1),
            "--output", str(output_path),
            "--svg-output", str(source_path),
            "--account", account,
        ]
        contract_path = article / "visual-contract.json"
        if contract_path.is_file():
            command.extend(["--spec", str(contract_path), "--spec-id", item_id])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size >= 1024:
            if html_kinds or backend in {"code-block", "formula-code-map"}:
                method = "formula-code-map-html-chrome-render" if backend == "formula-code-map" or str(item.get("kind") or "").strip().lower() == "formula-code-map" else "code-html-chrome-render"
            elif source_suffix == ".html":
                method = "katex-html-chrome-render"
            else:
                method = "svg-chrome-render"
            return method, str(source_path.relative_to(article))
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(detail or f"确定性视觉渲染失败：{item_id}")

    execution_errors: list[dict[str, str]] = list(previous_errors)
    for item in records:
        prompt_path = article / str(item["path"])
        asset = str(item["asset"])
        # A candidate directory can be used to avoid silently replacing an
        # already-submitted draft.  Production runs should point at imgs/.
        output_path = output_dir / Path(asset).name
        deterministic_kind = str(item.get("generation_mode") or "").lower() == "deterministic" or str(item.get("kind") or "").lower() in {"qkv", "shape", "attention", "numeric", "multihead", "kv-cache", "architecture", "flow", "diagram", "checklist", "code", "pseudocode", "formula-code-map", "card-deck", "excalidraw-style", "data", "evidence-strip"}
        item["request_sha256"] = request_sha256(item, plan)
        if deterministic_kind:
            method, diagram_source = render_deterministic(item, output_path)
            item["diagram_source"] = diagram_source
            item["execution_provider"] = "local-deterministic"
            item["execution_model"] = {
                "katex-html-chrome-render": "render_math_visual",
                "code-html-chrome-render": "render_code_block",
                "formula-code-map-html-chrome-render": "render_formula_code_map",
                "svg-chrome-render": "render_visual_anchor",
            }.get(method, "render_visual_anchor")
            item["execution_method"] = method
            default_backend = {
                "katex-html-chrome-render": "katex-html-composite",
                "code-html-chrome-render": "code-block",
                "formula-code-map-html-chrome-render": "formula-code-map",
            }.get(method, "deterministic-svg")
            item["execution_backend"] = str(item.get("requested_backend") or item.get("render_backend") or "").strip() or default_backend
            if str(item.get("requested_backend") or item.get("render_backend") or "") != item["execution_backend"]:
                item["fallback_reason"] = f"requested backend {item.get('requested_backend') or item.get('render_backend')} 使用本地确定性适配器"
            item["status"] = "deterministic"
        elif args.fallback_only:
            if str(item.get("id")) != "cover":
                method, diagram_source = render_deterministic(item, output_path)
                item["diagram_source"] = diagram_source
                item["execution_provider"] = "local-fallback"
                item["execution_model"] = "render_visual_anchor"
                item["execution_method"] = method
                item["execution_backend"] = str(item.get("requested_backend") or item.get("render_backend") or "deterministic-svg")
                item["fallback_reason"] = "explicit --fallback-only: external provider skipped; semantic local renderer used"
                item["status"] = "fallback"
            else:
                render_fallback(item, output_path)
                item["execution_provider"] = "local-fallback"
                item["execution_model"] = "text_poster"
                item["execution_method"] = "deterministic-fallback"
                item["fallback_reason"] = "explicit --fallback-only: external provider skipped; current brand cover fallback used"
                item["status"] = "fallback"
        else:
            # Size, ratio and optional reference images are kept in the
            # prompt frontmatter so the personal Agnes skill's API contract
            # survives review, re-runs and provenance checks.
            command = [sys.executable, str(IMAGE_CREATE), "generate", str(prompt_path), "-o", str(output_path)]
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=child_env)
            if result.returncode != 0:
                if not args.fallback_on_error:
                    print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
                    return result.returncode or 1
                error_text = result.stderr.strip() or result.stdout.strip()
                execution_errors.append({"id": str(item.get("id")), "error": clean_provider_error(error_text)})
                print(f"[WARN] Agnes 生成失败，转入可审计本地降级：{item.get('id')}\n{error_text}", file=sys.stderr)
                if str(item.get("id")) == "cover":
                    render_fallback(item, output_path)
                else:
                    method, diagram_source = render_deterministic(item, output_path)
                    item["diagram_source"] = diagram_source
                    item["execution_method"] = method
                    item["execution_backend"] = str(item.get("requested_backend") or item.get("render_backend") or "deterministic-svg")
                item["execution_provider"] = "local-fallback"
                item["execution_model"] = "text_poster" if str(item.get("id")) == "cover" else "render_visual_anchor"
                item["fallback_reason"] = clean_provider_error(error_text)
                item["status"] = "fallback"
            elif not output_path.is_file() or output_path.stat().st_size < 1024:
                if not args.fallback_on_error:
                    raise SystemExit(f"生图输出无效：{output_path}")
                execution_errors.append({"id": str(item.get("id")), "error": "Agnes 返回的文件缺失或小于 1KB"})
                if str(item.get("id")) == "cover":
                    render_fallback(item, output_path)
                else:
                    method, diagram_source = render_deterministic(item, output_path)
                    item["diagram_source"] = diagram_source
                    item["execution_method"] = method
                    item["execution_backend"] = str(item.get("requested_backend") or item.get("render_backend") or "deterministic-svg")
                item["execution_provider"] = "local-fallback"
                item["execution_model"] = "text_poster" if str(item.get("id")) == "cover" else "render_visual_anchor"
                item["fallback_reason"] = "Agnes returned no valid output"
                item["status"] = "fallback"
            else:
                item["execution_provider"] = plan.get("provider")
                item["execution_model"] = plan.get("model")
                item["execution_method"] = "text-to-image"
                item["execution_backend"] = str(item.get("requested_backend") or item.get("render_backend") or "agnes")
                item["fallback_reason"] = ""
                item["status"] = "generated"
        if str(item.get("id")) == "cover":
            compose_cover(item, output_path)
        item["output"] = str(output_path.relative_to(article)) if output_path.is_relative_to(article) else str(output_path)
        item["output_sha256"] = sha256_file(output_path)
    update_sources(article, plan, executed=True)
    plan["status"] = "generated" if all(str(item.get("status")) in {"generated", "fallback", "deterministic"} for item in plan.get("prompt_files", [])) else "partial"
    plan["executed_at"] = datetime.now(timezone.utc).isoformat()
    statuses = {str(item.get("status")) for item in records}
    plan["execution_mode"] = "real" if statuses == {"generated"} else ("deterministic" if statuses == {"deterministic"} else "mixed")
    plan["execution_summary"] = {status: sum(1 for item in records if item.get("status") == status) for status in sorted(statuses)}
    plan["selected_ids"] = [item.get("id") for item in records]
    # Keep prior network failures when a later run explicitly uses the local
    # fallback; the audit trail must not erase the reason Agnes was skipped.
    deduped_errors: list[dict[str, str]] = []
    seen_errors: set[tuple[str, str]] = set()
    for error in execution_errors:
        key = (str(error.get("id", "")), str(error.get("error", "")))
        if key not in seen_errors:
            seen_errors.add(key)
            deduped_errors.append(error)
    plan["execution_errors"] = deduped_errors
    for item in plan.get("prompt_files", []):
        if isinstance(item, dict):
            item.setdefault("requested_provider", plan.get("requested_provider") or plan.get("provider"))
    (article / "image-generation-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_visual_contract(article, plan)
    write_visual_run_manifest(article, records)
    print(json.dumps({"status": "generated", "provider": args.provider, "count": len(records), "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
