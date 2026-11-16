#!/usr/bin/env python3
"""Generate and render the six Huashu templates through the production compiler.

Every clip is TEST_ONLY: a short, silent generated visual-support MP4. The
metric source is explicitly labelled non-business test data. The evidence and
code sources are real, git-tracked repo files with byte-verified SHA-256.

Run from anywhere:
    python projects/e2e-huashu-six-templates/scripts/build_and_render.py

Emits one receipt per shot under receipts/ and a summary run receipt. It uses
``motion_planner.build_auto_plan`` for the specs (the same compiler M5 uses)
and ``scripts/huashu_render.py`` for the real Huashu Art Motion render.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from contentops.media import motion_planner  # noqa: E402
from contentops.media import animation_backend  # noqa: E402
from contentops.media.motion_sample import check_motion_sample  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402
import huashu_motion_adapter as adapter  # noqa: E402

DNA = json.loads((ROOT / "config" / "accounts" /
                  "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))

METRIC_RECORD = {
    "title": "Local clip tests",
    "unit": "passing tests",
    "citation": "Source: local non-business test receipt (no product metric)",
    "series": [
        {"label": "before", "value": 9},
        {"label": "after", "value": 21},
    ],
    "data_kind": "NON_BUSINESS_TEST_DATA",
    "note": "Values are local test counts used only to exercise the animation component; "
            "they are NOT a benchmark, user result or business performance claim.",
}

TEMPLATES = [
    {
        "id": "arch01", "type": "architecture_flow",
        "params": {"nodes": ["Query", "Recall", "Rerank", "Answer"]},
        "narration": "查询依次经过召回、重排，最后生成答案。",
    },
    {
        "id": "state01", "type": "state_transition",
        "params": {"states": ["idle", "running", "complete"],
                   "transition": "verified result", "success": "verified", "failure": "retry"},
        "narration": "代理从空闲进入运行，成功则完成，失败则重试。",
    },
    {
        "id": "code01", "type": "code_focus",
        "params": {"focus_rect": [0.10, 0.25, 0.45, 0.10], "focus_label": "source hash check"},
        "narration": "关键代码校验来源哈希后才放行。",
    },
    {
        "id": "evid01", "type": "evidence_zoom",
        "params": {"focus_rect": [0.12, 0.30, 0.50, 0.12], "focus_label": "real doctor output"},
        "narration": "放大已登记真实截图中的输出区域。",
    },
    {
        "id": "metric01", "type": "metric_transition",
        "params": {"title": METRIC_RECORD["title"], "unit": METRIC_RECORD["unit"],
                   "chart": "bar", "source_label": METRIC_RECORD["citation"],
                   "source_asset_id": "src-metric",
                   "series": METRIC_RECORD["series"], "highlight_index": 1},
        "narration": "本地测试数从九项增长到二十一项，这只是组件演示。",
    },
    {
        "id": "cmp01", "type": "comparison_reveal",
        "params": {"before": "unverified output", "after": "hash checked"},
        "narration": "对照未核验输出与哈希核验后的输出。",
    },
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def build_inputs() -> tuple[dict, dict]:
    sources_dir = PROJECT / "sources"
    assets_dir = PROJECT / "assets" / "anchors"
    sources_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Real, git-tracked screenshots for the evidence-led templates.
    evidence_src = ROOT / "projects" / "easel-review" / "sources" / "screenshots" / "11-easel-ping.png"
    code_src = ROOT / "projects" / "easel-review" / "sources" / "screenshots" / "14-easel-skills-dir.png"
    assert evidence_src.is_file() and code_src.is_file()
    metric_src = sources_dir / "metric-source.json"
    write_json(metric_src, METRIC_RECORD)

    def repo_rel(path: Path) -> str:
        return path.resolve().relative_to(ROOT).as_posix()

    source_rows = {
        "src-code": {
            "id": "src-code", "type": "CODE_SNAPSHOT",
            "repo_path": repo_rel(code_src), "sha256": sha(code_src),
            "permission": "CREATED_BY_OWNER",
            "usage_scope": "TEST_ONLY 解释性代码局部；来自已登记的真实截图",
            "source_document_sha256": sha(ROOT / "src" / "contentops" / "media" / "motion_planner.py"),
            "ocr_regions": [{"text": "skills builtin code", "confidence": 0.9,
                             "rect": [0.10, 0.25, 0.45, 0.10]}],
        },
        "src-evidence": {
            "id": "src-evidence", "type": "REAL_SCREENSHOT",
            "repo_path": repo_rel(evidence_src), "sha256": sha(evidence_src),
            "permission": "CREATED_BY_OWNER",
            "usage_scope": "TEST_ONLY 解释性放大；来自已登记的真实截图",
            "ocr_regions": [{"text": "version doctor result", "confidence": 0.9,
                             "rect": [0.12, 0.30, 0.50, 0.12]}],
        },
        "src-metric": {
            "id": "src-metric", "type": "REAL_DOCUMENT",
            "repo_path": repo_rel(metric_src), "sha256": sha(metric_src),
            "permission": "CREATED_BY_OWNER",
            "usage_scope": "TEST_ONLY 非业务测试数据",
        },
        "src-doc": {
            "id": "src-doc", "type": "REAL_DOCUMENT",
            "repo_path": "docs/PRD-ANIMATION-SKILLS-INTEGRATION.md",
            "sha256": sha(ROOT / "docs" / "PRD-ANIMATION-SKILLS-INTEGRATION.md"),
            "permission": "CREATED_BY_OWNER",
            "usage_scope": "TEST_ONLY 解释性内容来源",
        },
    }
    asset_map = {
        "src-code": "src-code", "src-evidence": "src-evidence",
        "src-metric": "src-metric", "src-doc": "src-doc",
    }
    return source_rows, asset_map


SOURCE_FOR_TYPE = {
    "architecture_flow": "src-doc",
    "state_transition": "src-doc",
    "code_focus": "src-code",
    "evidence_zoom": "src-evidence",
    "metric_transition": "src-metric",
    "comparison_reveal": "src-doc",
}


def build_specs(source_rows: dict) -> dict:
    lines = []
    timings = []
    for index, tpl in enumerate(TEMPLATES):
        source_id = SOURCE_FOR_TYPE[tpl["type"]]
        params = dict(tpl["params"])
        if tpl["type"] == "metric_transition":
            params["source_asset_id"] = source_id
        lines.append({
            "id": tpl["id"], "asset_id": source_id, "claim": f"C-{tpl['id']}",
            "narration": tpl["narration"], "source_refs": ["repo://project.yaml"],
            "animation_type": tpl["type"], "animation": params,
            "visual_focus": tpl["narration"],
        })
        timings.append({"start": float(index) * 6.0, "duration": 5.0})
    claims = [
        {"id": f"C-{tpl['id']}", "text": tpl["narration"],
         "artifacts": ["easel_pins"], "quotes": ["visual support only; TEST_ONLY"]}
        for tpl in TEMPLATES
    ]
    write_json(PROJECT / "script" / "script.json",
               {"schema": "contentops.script/v1", "language": "zh", "lines": lines})
    write_json(PROJECT / "script" / "claims.json",
               {"schema": "contentops.claims/v1", "claims": claims})
    write_json(PROJECT / "sources" / "assets.json",
               {"schema": "contentops.m5-asset-manifest/v1", "policy": "TEST_ONLY",
                "assets": list(source_rows.values())})
    write_json(PROJECT / "script" / "assets.json",
               {"schema": "contentops.script-assets/v1", "assets": {}})
    write_json(PROJECT / "sources" / "source-refs.json",
               {"schema": "contentops.source-refs/v1",
                "refs": [{"id": "easel_pins", "type": "lock_file",
                          "path": "runtime/easel-pins.json", "permission": "CREATED_BY_OWNER"}]})
    plan = motion_planner.build_auto_plan(
        project=PROJECT, account_id="x-superplay-future-intelligence",
        account_dna=DNA, script={"lines": lines}, narration={"lines": timings},
        source_assets=source_rows,
    )
    write_json(PROJECT / "script" / "shot-plan.json", plan["plan"])
    return plan["plan"]


def probe_and_extract(path: Path) -> dict:
    def run(args):
        return hidden_run(args, timeout=120)
    p = run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
             "-select_streams", "v:0", "-of", "json", str(path)])
    raw = json.loads(p.stdout or "{}")
    stream = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in raw.get("streams", []))
    frames_dir = PROJECT / "receipts" / "frames" / path.stem
    frames_dir.mkdir(parents=True, exist_ok=True)
    duration = float((raw.get("format") or {}).get("duration") or 0.0)
    times = [0.0, round(duration / 2, 3), max(0.0, round(duration - 0.1, 3))]
    extracted = []
    for idx, ts in enumerate(times):
        out = frames_dir / f"frame-{idx}.png"
        r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(ts),
                 "-i", str(path), "-frames:v", "1", str(out)])
        if r.returncode == 0 and out.is_file():
            extracted.append({"timestamp_s": ts, "path": out.relative_to(ROOT).as_posix()})
    return {
        "codec_name": stream.get("codec_name"), "width": stream.get("width"),
        "height": stream.get("height"), "pix_fmt": stream.get("pix_fmt"),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "duration_s": duration, "has_audio": audio, "frames": extracted,
    }


def main() -> int:
    started = time.time()
    source_rows, _ = build_inputs()
    plan = build_specs(source_rows)
    results = []
    for shot in plan["shots"]:
        spec_path = PROJECT / shot["spec"]
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        animation_type = spec["contentops_scene"]["animation_type"]
        out = PROJECT / "assets" / "generated" / "huashu" / f"{shot['asset_id']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        child_env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        proc = hidden_run([python_executable(), str(ROOT / "scripts" / "huashu_render.py"),
                           "--spec", str(spec_path), "--out", str(out)],
                          timeout=3600, cwd=str(ROOT), env=child_env)
        row = {
            "shot_id": shot["placement_id"], "animation_type": animation_type,
            "grammar": spec["grammar"], "spec": shot["spec"],
            "spec_sha256": sha(spec_path), "output": out.relative_to(ROOT).as_posix(),
            "exit_code": proc.returncode,
        }
        if proc.returncode == 0 and out.is_file():
            row["output_sha256"] = sha(out)
            row["ffprobe"] = probe_and_extract(out)
            sample = check_motion_sample(out, probe=adapter._ffprobe(out))
            row["motion_sample"] = {"state": sample.get("state"), "reason": sample.get("reason")}
            row["technical_check"] = {
                "state": "TECHNICALLY_CHECKED" if sample.get("state") == "TECHNICALLY_CHECKED" else "BLOCKED",
            }
            row["template_params"] = json.loads((PROJECT / "script" / "script.json").read_text(encoding="utf-8"))["lines"]
        else:
            row["error"] = (proc.stderr or proc.stdout or "")[-1200:]
        write_json(PROJECT / "receipts" / f"shot-{shot['placement_id']}.json", row)
        results.append(row)
        print(f"[{animation_type}] exit={proc.returncode} "
              f"{'SHA=' + row.get('output_sha256', '')[:12] if row.get('output_sha256') else row.get('error', '')[:80]}")
    summary = {
        "schema": "contentops.huashu-six-template-run/v1",
        "created_at": "2026-11-17T03:20:00Z",
        "elapsed_seconds": round(time.time() - started, 2),
        "runtime": {"skill": "huashu-art-motion", "version": "1.2.0",
                    "renderer": "shared-skill/scripts/engine/render.py"},
        "account_id": "x-superplay-future-intelligence",
        "backend": "huashu-art-motion",
        "generated": True, "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
        "counts_as_real_recording": False, "production_ready": False,
        "publish_authorized": False, "human_review": "PENDING_FOUNDER_REVIEW",
        "metric_data_kind": "NON_BUSINESS_TEST_DATA",
        "shots": results,
        "rendered_count": sum(1 for r in results if r.get("output_sha256")),
    }
    write_json(PROJECT / "receipts" / "run-summary.json", summary)
    print(f"rendered {summary['rendered_count']}/{len(results)} templates")
    return 0 if summary["rendered_count"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
