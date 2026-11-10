"""Render the source-bound RAG motion preview end to end, without paid APIs."""
from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import m5_production  # noqa: E402
import qc_video  # noqa: E402
import huashu_motion_adapter  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def run() -> dict:
    started = time.monotonic()
    wall_start = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    runtime = huashu_motion_adapter._runtime()
    plan_path = PROJECT / "script" / "shot-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    script_path = PROJECT / "script" / "script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))

    narration = m5_production.stage_narration(PROJECT, script)
    subtitles = m5_production.stage_subtitles(PROJECT, script, narration)
    if len(plan["shots"]) != len(script["lines"]) or len(plan["shots"]) != len(narration["lines"]):
        raise RuntimeError("shot plan, script and measured narration line counts differ")

    shot_receipts = []
    for index, shot in enumerate(plan["shots"]):
        spec_path = PROJECT / "motion" / "shots" / f"{shot['id']}.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        timing = narration["lines"][index]
        expected = float(timing["duration"]) + (0.0 if index == 0 else m5_production.SILENCE_SECONDS)
        if abs(float(spec["duration"]) - expected) > 0.05:
            spec["duration"] = round(expected, 3)
            write_json(spec_path, spec)
            shot["duration_s"] = round(expected, 3)
            shot["timing_adjustment"] = "UPDATED_FROM_LOCAL_SAPI_LINE_TIMING"
        output = PROJECT / shot["render_path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        staged = output.with_name(f"{output.stem}.pending-{uuid.uuid4().hex[:8]}.mp4")
        attempt_receipts = []
        elapsed = 0.0
        for attempt in range(1, 3):
            command = [python_executable(), str(ROOT / "scripts" / "huashu_render.py"),
                       "--spec", str(spec_path), "--out", str(staged)]
            t0 = time.monotonic()
            result = hidden_run(command, timeout=3600, cwd=str(ROOT))
            attempt_s = round(time.monotonic() - t0, 3)
            elapsed += attempt_s
            attempt_receipts.append({"attempt": attempt, "elapsed_s": attempt_s,
                                     "exit_code": result.returncode})
            if result.returncode == 0 and staged.is_file():
                staged.replace(output)
                break
            detail = (result.stderr or result.stdout)[-1200:]
            if attempt == 1 and "NetworkError" in detail:
                continue
            raise RuntimeError(f"Huashua render failed for {shot['id']}: "
                               f"exit={result.returncode}; {detail}")
        shot_receipts.append({"shot_id": shot["id"], "backend": "huashu-art-motion",
                              "grammar": spec["grammar"], "spec": spec_path.relative_to(PROJECT).as_posix(),
                              "spec_sha256": sha(spec_path), "output": output.relative_to(PROJECT).as_posix(),
                              "output_sha256": sha(output), "duration_s": round(expected, 3),
                              "render_seconds": elapsed, "source_refs": shot["source_refs"],
                              "attempts": attempt_receipts,
                              "narration_line_id": script["lines"][index]["id"],
                              "content_point": shot["content_point"]})
        write_json(PROJECT / "sources" / "assets.json", {
            "schema": "contentops.m5-assets/v1",
            "assets": [{"id": item["shot_id"], "type": "generated_video",
                        "repo_path": f"projects/{PROJECT.name}/{item['output']}",
                        "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
                        "sha256": item["output_sha256"]} for item in shot_receipts],
        })
    write_json(PROJECT / "script" / "shot-plan.json", plan)

    final = PROJECT / "final" / "preview-rag-hybrid.mp4"
    inputs = [str(PROJECT / item["output"]) for item in shot_receipts]
    audio = PROJECT / narration["audio"]
    srt = PROJECT / subtitles["path"]
    args = ["ffmpeg", "-y"]
    for item in inputs:
        args.extend(["-i", item])
    args.extend(["-i", str(audio), "-i", str(srt)])
    graph = "".join(f"[{index}:v]" for index in range(len(inputs)))
    graph += f"concat=n={len(inputs)}:v=1:a=0[v]"
    args.extend(["-filter_complex", graph, "-map", "[v]",
                 "-map", f"{len(inputs)}:a", "-map", f"{len(inputs) + 1}:s",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac",
                 "-b:a", "128k", "-c:s", "mov_text", "-metadata:s:s:0",
                 "language=zho", "-shortest", str(final)])
    compose_start = time.monotonic()
    composed = hidden_run(args, timeout=900, cwd=str(ROOT))
    compose_seconds = round(time.monotonic() - compose_start, 3)
    if composed.returncode or not final.is_file():
        raise RuntimeError(f"preview composition failed: {(composed.stderr or composed.stdout)[-800:]}")

    qc = qc_video.qc(PROJECT, target=final.name)
    total = round(time.monotonic() - started, 3)
    receipt = {
        "schema": "contentops.motion-preview-run/v1",
        "run_id": f"{PROJECT.name}-{sha(plan_path)[:12]}",
        "started_at": wall_start,
        "elapsed_seconds": total,
        "engine": "huashu-art-motion",
        "runtime": runtime,
        "shot_renders": shot_receipts,
        "narration": {"engine": narration["engine"], "provider": narration["voice_provider"],
                      "network": narration["network"], "cost": narration["cost"],
                      "duration_s": narration["duration_s"], "lines": narration["lines"]},
        "subtitles": subtitles,
        "composer": {"name": "ffmpeg", "seconds": compose_seconds},
        "output": {"path": f"project://final/{final.name}", "sha256": sha(final),
                   "bytes": final.stat().st_size},
        "technical_qc": {"overall": qc["overall"],
                         "checks": [{"id": item["id"], "severity": item["severity"],
                                     "ok": item["ok"]} for item in qc.get("checks", [])]},
        "visual_qc": "REVIEW_REQUIRED_WITH_DOCUMENTED_ISSUES",
        "external_provider_calls": 0,
        "external_cost": 0,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
    }
    write_json(PROJECT / "receipts" / "motion-preview-run.json", receipt)
    return {"run_id": receipt["run_id"], "elapsed_seconds": total,
            "output": receipt["output"], "technical_qc": qc["overall"],
            "visual_qc": receipt["visual_qc"], "production_ready": False,
            "publish_authorized": False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
