#!/usr/bin/env python3
"""Fixed local video operations; Huashu execution is always Owner-gated."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402
from contentops.media import huashu_motion  # noqa: E402
from contentops.media.manifest_m5_bridge import (  # noqa: E402
    ManifestBridgeError,
    build_m5_storyboard,
    validate_manifest_file,
)
from contentops.media.motion_manifest import (  # noqa: E402
    build_motion_manifest_entries,
    register_motion_clip,
)
from contentops.media.quality_gate import (  # noqa: E402
    AssetQualityGate,
    MediaManifest,
    TimelinePlacement,
)
from contentops.skills import huashu_execution  # noqa: E402

PROJECTS_ROOT = (ROOT / "projects").resolve()
NODE_EXE = Path(r"C:\Program Files\nodejs\node.exe")
FFMPEG_DIR = Path(
    r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages"
    r"\yt-dlp.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-N-124716-g054dffd133-win64-gpl\bin"
)
FFMPEG_EXE = FFMPEG_DIR / "ffmpeg.exe"
FFPROBE_EXE = FFMPEG_DIR / "ffprobe.exe"
DISPATCHER = Path(huashu_motion.DEFAULT_RUNTIME) / "cli" / "om.js"
ALLOWED_TASKS = {
    "runtime-status", "motion-check", "motion-still", "motion-render",
    "motion-qa", "motion-validate", "manifest-register", "easel-compose",
    "video-qc", "technical-preview", "recordly-intake",
}
_OPERATION_FOR_TASK = {
    "motion-check": "check", "motion-still": "still",
    "motion-render": "render", "motion-qa": "qa",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNTS = {"x-superplay-1024", "x-superplay-future-intelligence"}


class RunnerError(RuntimeError):
    """A fixed local operation was invalid or its preflight failed."""


def _git_probe(root: Path, *args: str) -> tuple[int, str]:
    result = hidden_run(["git", "-C", str(root), *args], timeout=30)
    return result.returncode, (result.stdout or "").strip()


def _project(value: str) -> Path:
    """Accept only a direct project slug, never an arbitrary filesystem path."""
    if not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise RunnerError("project must be one safe projects/<slug> name")
    candidate = PROJECTS_ROOT / value
    resolved = candidate.resolve(strict=True)
    if resolved.parent != PROJECTS_ROOT or not resolved.is_dir():
        raise RunnerError("project must be a direct child of the repository projects directory")
    if not (resolved / "project.yaml").is_file():
        raise RunnerError("project.yaml is required")
    return resolved


def _inside_project(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or any(part in ("..", "") for part in relative.parts):
        raise RunnerError("paths must be project-relative and cannot traverse directories")
    target = (project / relative).resolve(strict=False)
    if target == project or not target.is_relative_to(project):
        raise RunnerError("path resolves outside the project")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _minimal_env(project: Path) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    path = os.pathsep.join((str(NODE_EXE.parent), str(FFMPEG_DIR),
                            str(Path(system_root) / "System32")))
    temp = project / "work" / "runner-temp"
    temp.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": path,
        "SystemRoot": system_root,
        "WINDIR": system_root,
        "HOME": str(project),
        "USERPROFILE": str(project),
        "LOCALAPPDATA": str(project / "work" / "local-app-data"),
        "TEMP": str(temp), "TMP": str(temp), "CI": "1",
    }


def _decode_video(path: Path, project: Path) -> dict[str, Any]:
    if not path.is_file() or not path.resolve().is_relative_to(project):
        return {"state": "BLOCKED", "reason": "VIDEO_MISSING_OR_ESCAPED"}
    result = hidden_run(
        [str(FFMPEG_EXE), "-v", "error", "-xerror", "-i", str(path),
         "-f", "null", os.devnull],
        cwd=project, env=_minimal_env(project), timeout=180,
    )
    return {"state": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
            "stderr_tail": (result.stderr or "")[-2000:]}


def _probe_video(path: Path, project: Path) -> dict[str, Any]:
    if not path.is_file() or not path.resolve().is_relative_to(project):
        return {"error": "VIDEO_MISSING_OR_ESCAPED"}
    metadata = hidden_run(
        [str(FFPROBE_EXE), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        cwd=project, env=_minimal_env(project), timeout=45,
    )
    if metadata.returncode != 0:
        return {"error": "FFPROBE_FAILED", "detail": (metadata.stderr or "")[-1000:]}
    try:
        payload = json.loads(metadata.stdout or "{}")
    except ValueError:
        return {"error": "FFPROBE_INVALID_JSON"}
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        return {"error": "VIDEO_STREAM_MISSING"}
    frames = hidden_run(
        [str(FFPROBE_EXE), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)],
        cwd=project, env=_minimal_env(project), timeout=90,
    )
    timestamps: list[float] = []
    if frames.returncode == 0:
        for line in (frames.stdout or "").splitlines():
            try:
                timestamps.append(float(line.strip().rstrip(",")))
            except ValueError:
                continue
    try:
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration"))
    except (TypeError, ValueError):
        duration = None
    return {
        "duration_s": duration, "width": video.get("width"),
        "height": video.get("height"), "codec_name": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "avg_frame_rate": video.get("avg_frame_rate"),
        "r_frame_rate": video.get("r_frame_rate"),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "frame_timestamps": timestamps,
    }


class LocalHuashuRunner:
    """Run only the pinned dispatcher, fixed operations and contained outputs."""

    def __init__(self, *, project_dir: Path, projects_root: Path = PROJECTS_ROOT,
                 runtime_root: Path = huashu_motion.DEFAULT_RUNTIME,
                 node_executable: Path = NODE_EXE,
                 timeout_seconds: int = 900) -> None:
        self.projects_root = Path(projects_root).resolve(strict=False)
        self.project_dir = Path(project_dir).resolve(strict=True)
        self.runtime_root = Path(runtime_root).resolve(strict=False)
        self.node_executable = Path(node_executable).resolve(strict=False)
        if self.project_dir.parent != self.projects_root:
            raise RunnerError("project must be a direct child of the projects directory")
        if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 900:
            raise RunnerError("timeout must be between 1 and 900 seconds")
        self.timeout_seconds = timeout_seconds
        self.dispatcher = self.runtime_root / "cli" / "om.js"

    def preflight(self, operation: str, request: Any = None) -> None:
        if operation not in huashu_execution.ALLOWED_OPERATIONS:
            raise RunnerError("unsupported Huashu Motion operation")
        if not self.node_executable.is_file() or not self.dispatcher.is_file():
            raise RunnerError("fixed Node or pinned Huashu dispatcher is missing")
        if not FFMPEG_EXE.is_file() or not FFPROBE_EXE.is_file():
            raise RunnerError("fixed FFmpeg/ffprobe installation is missing")
        node = hidden_run([str(self.node_executable), "--version"], timeout=15,
                          cwd=self.project_dir, env=_minimal_env(self.project_dir))
        match = re.fullmatch(r"v(\d+)\.\d+\.\d+\s*", node.stdout or "")
        if node.returncode != 0 or not match or int(match.group(1)) < 22:
            raise RunnerError("fixed Node executable must be version 22 or newer")

    def _output(self, operation: str, request_id: str) -> Path:
        suffix = ".mp4" if operation == "render" else ".png"
        output = _inside_project(self.project_dir, f"out/contentops-{request_id}{suffix}")
        out_dir = output.parent
        if out_dir.exists() and not out_dir.resolve().is_relative_to(self.project_dir):
            raise RunnerError("output directory resolves outside the project")
        if output.exists():
            raise RunnerError("refusing to overwrite an existing operation output")
        return output

    def build_argv(self, operation: str, request_id: str,
                   options: Mapping[str, Any] | None = None) -> list[str]:
        if operation not in huashu_execution.ALLOWED_OPERATIONS:
            raise RunnerError("unsupported Huashu Motion operation")
        if not _SAFE_ID.fullmatch(str(request_id)):
            raise RunnerError("invalid request id")
        if options:
            raise RunnerError("operation options are fixed and cannot be overridden")
        base = [str(self.node_executable), str(self.dispatcher), operation, str(self.project_dir)]
        if operation == "check":
            return base + ["--samples", "5", "--json"]
        if operation == "still":
            return base + ["--at", "0,2.5", "--out", str(self._output(operation, request_id))]
        if operation == "render":
            return base + ["--out", str(self._output(operation, request_id)),
                           "--format", "mp4", "--fps", "30", "--workers", "2", "--silent"]
        return base

    def __call__(self, operation: str, request: Any) -> Mapping[str, Any]:
        request_id = str(getattr(request, "request_id", ""))
        self.preflight(operation, request)
        argv = self.build_argv(operation, request_id)
        if operation in {"render", "still"}:
            self._output(operation, request_id).parent.mkdir(parents=True, exist_ok=True)
        try:
            completed = hidden_run(argv, cwd=self.project_dir, env=_minimal_env(self.project_dir),
                                   timeout=self.timeout_seconds, capture_output=True,
                                   text=True, check=False)
        except Exception as exc:  # subprocess timeout/launch failures remain a recorded failure
            timed_out = isinstance(exc, __import__("subprocess").TimeoutExpired)
            stdout = getattr(exc, "stdout", None) or getattr(exc, "output", None) or ""
            stderr = getattr(exc, "stderr", None) or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            receipt = {
                "schema": "contentops.huashu-local-runner/v1",
                "operation": operation,
                "process_status": "TIMEOUT" if timed_out else "LAUNCH_FAILED",
                "runner_invoked": True,
                "execution_authorized": False,
                "production_ready": False,
                "publish_authorized": False,
                "human_review": "PENDING_FOUNDER_REVIEW",
                "stdout_tail": str(stdout)[-12000:],
                "stderr_tail": str(stderr)[-12000:],
            }
            return {"ok": False, "health": False,
                    "error": "local Huashu invocation timed out" if timed_out
                             else f"local Huashu invocation failed: {type(exc).__name__}",
                    "receipt": receipt}
        receipt: dict[str, Any] = {
            "schema": "contentops.huashu-local-runner/v1",
            "operation": operation,
            "process_status": "EXITED",
            "returncode": completed.returncode,
            "runner_invoked": True,
            "execution_authorized": False,
            "production_ready": False,
            "publish_authorized": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
            "stdout_tail": (completed.stdout or "")[-12000:],
            "stderr_tail": (completed.stderr or "")[-12000:],
        }
        if completed.returncode != 0:
            return {"ok": False, "health": False, "error": "Huashu operation failed",
                    "receipt": receipt}
        if operation == "render":
            output = _inside_project(
                self.project_dir, f"out/contentops-{request_id}.mp4")
            probe = _probe_video(output, self.project_dir)
            decode = _decode_video(output, self.project_dir)
            from contentops.media.motion_sample import check_motion_clip
            digest = _sha256(output) if output.is_file() else ""
            checked = check_motion_clip(output, probe=probe, expected_sha256=digest,
                                        min_duration_s=0.0, max_duration_s=8.0,
                                        reason_prefix="HUASHU_OUTPUT")
            if decode.get("state") != "PASS":
                checked = {"state": "BLOCKED", "reason": "FULL_DECODE_FAILED",
                           "decode": decode, "probe_validation": checked}
            if checked.get("state") != "TECHNICALLY_CHECKED":
                return {"ok": False, "health": False,
                        "error": "rendered MP4 failed technical validation",
                        "receipt": {**receipt, "decode": decode, "validation": checked}}
            receipt.update({"output": output.relative_to(self.project_dir).as_posix(),
                            "output_sha256": digest, "bytes": output.stat().st_size,
                            "decode": decode, "technical_validation": checked})
        elif operation == "still":
            output = _inside_project(
                self.project_dir, f"out/contentops-{request_id}.png")
            if not output.is_file():
                return {"ok": False, "health": False,
                        "error": "expected still image was not created", "receipt": receipt}
            receipt.update({"output": output.relative_to(self.project_dir).as_posix(),
                            "output_sha256": _sha256(output), "bytes": output.stat().st_size})
        return {"ok": True, "health": True, "receipt": receipt}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="task", required=True)
    sub.add_parser("runtime-status")
    for task in ("motion-check", "motion-still", "motion-render", "motion-qa"):
        command = sub.add_parser(task)
        command.add_argument("project", help="one project slug under projects/")
        command.add_argument("--account", required=True, choices=sorted(_ACCOUNTS))
        command.add_argument("--request-id", required=True)
    validate = sub.add_parser("motion-validate")
    validate.add_argument("project")
    validate.add_argument("--clip", required=True, help="project-relative MP4 path")
    validate.add_argument("--sha256", required=True)
    validate.add_argument("--spec-sha256", required=True)
    register = sub.add_parser("manifest-register")
    register.add_argument("project")
    register.add_argument("--source", choices=("huashu-motion-asset", "native-motion-preview"),
                          default="huashu-motion-asset",
                          help="the separately validated source receipt schema")
    register.add_argument("--asset-id", required=True)
    register.add_argument("--placement-id", required=True)
    register.add_argument("--audio-policy", choices=("MUTE", "REPLACE"), default="MUTE")
    for task in ("easel-compose", "video-qc", "technical-preview"):
        sub.add_parser(task).add_argument("project")
    intake = sub.add_parser("recordly-intake")
    intake.add_argument("project")
    intake.add_argument("--file", required=True, help="Owner-supplied original recording")
    return parser


def _motion_operation(args: argparse.Namespace) -> int:
    project = _project(args.project)
    operation = _OPERATION_FOR_TASK[args.task]
    request = huashu_execution.build_request(
        request_id=args.request_id, operation=operation, account=args.account,
        pipeline="M5", stage="motion",
        subject=os.environ.get("CONTENTOPS_EXECUTION_SUBJECT", ""),
    )
    result = huashu_execution.execute_huashu(
        request, project_dir=project,
        owner_identities=[part.strip() for part in
                          os.environ.get("CONTENTOPS_OWNER_IDENTITIES", "").split(",")
                          if part.strip()],
        runtime_root=huashu_motion.DEFAULT_RUNTIME,
        runner=LocalHuashuRunner(project_dir=project), git_probe=_git_probe,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, default=str))
    return 0 if result.execution.get("state") == "EXECUTED" else 2


def _motion_validate(args: argparse.Namespace) -> int:
    project = _project(args.project)
    clip = _inside_project(project, args.clip)
    if not _SHA256.fullmatch(args.sha256) or not _SHA256.fullmatch(args.spec_sha256):
        raise RunnerError("clip and spec digests must be lowercase SHA-256 values")
    from contentops.media.huashu_motion import validate_output
    record = validate_output(
        clip, project_root=project, expected_sha256=args.sha256,
        spec_sha256=args.spec_sha256, probe=_probe_video(clip, project),
        audio_policy="MUTE",
    )
    target = project / "receipts" / "huashu-motion-asset.json"
    if target.exists():
        raise RunnerError("refusing to overwrite an existing motion asset record")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": record["technical_status"],
                      "record": target.relative_to(project).as_posix(),
                      "clip_sha256": record["clip_sha256"],
                      "production_ready": False, "publish_authorized": False}, indent=2))
    return 0


def _manifest_register(args: argparse.Namespace) -> int:
    project = _project(args.project)
    record_name = ("p6-native-motion-preview.json" if args.source == "native-motion-preview"
                   else "huashu-motion-asset.json")
    record_path = project / "receipts" / record_name
    manifest_path = project / "receipts" / "media-manifest.json"
    if not record_path.is_file() or manifest_path.exists():
        raise RunnerError("a validated motion record is required and existing manifests are never overwritten")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    prefix = "project://"
    if record.get("schema") == "contentops.native-motion-preview/v1":
        clip_ref = str((record.get("output") or {}).get("path") or "")
    else:
        clip_ref = str(record.get("clip_path") or "")
    if not clip_ref.startswith(prefix):
        raise RunnerError("validated record must use a project:// clip path")
    clip = _inside_project(project, clip_ref[len(prefix):])
    registered = register_motion_clip(
        record, clip_path=clip, project_root=project, asset_id=args.asset_id,
        placement_id=args.placement_id, audio_policy=args.audio_policy,
    )
    config = __import__("m5_production")._read_yaml(project / "project.yaml")
    if config.get("fixture") is True:
        receipt = json.loads(registered.source_receipt_path.read_text(encoding="utf-8"))
        receipt.update({"fixture": True, "fixture_kind": "TECHNICAL_SAMPLE_ONLY"})
        registered.source_receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assets = build_motion_manifest_entries([registered])
    gate = AssetQualityGate()
    states = {asset.asset_id: gate.evaluate(asset, repo_root=ROOT,
                                             project_root=project).state for asset in assets}
    manifest = MediaManifest(
        assets=assets, gate_states=states,
        timeline=[TimelinePlacement(
            placement_id=args.placement_id, active_asset_id=registered.derived.asset_id,
            selection_reason=f"AudioPolicy {args.audio_policy} derived asset selected",
            superseded_asset_ids=[registered.source.asset_id],
        )],
        narration={"required": True, "reason": "M5 narration is independently muxed"},
        notes={"fixture": config.get("fixture") is True,
               "technical_sample_status": "TECHNICAL_SAMPLE_ONLY"
                    if config.get("fixture") is True else "NOT_A_FIXTURE",
               "production_ready": False, "publish_authorized": False,
               "source_clip_sha256": registered.clip_sha256},
    )
    manifest.write(manifest_path)
    print(json.dumps({"manifest": manifest_path.relative_to(project).as_posix(),
                      "assets": [asset.asset_id for asset in assets],
                      "active_asset": registered.derived.asset_id,
                      "gate_states": states,
                      "production_ready": False, "publish_authorized": False}, indent=2))
    return 0


def _easel_compose(args: argparse.Namespace) -> int:
    project = _project(args.project)
    if (project / "receipts" / "media-manifest.json").is_file() is False:
        raise RunnerError("canonical receipts/media-manifest.json is required")
    slug = project.name
    if (project / "final" / f"{slug}.mp4").exists():
        raise RunnerError("refusing to overwrite an existing final render")
    import m5_production
    result = m5_production.build(project, media_manifest=project / "receipts" / "media-manifest.json")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def _technical_preview(args: argparse.Namespace) -> int:
    """Compose a silent M4.5 preview without entering the formal M5 gates."""
    project = _project(args.project)
    manifest_path = project / "receipts" / "media-manifest.json"
    if not manifest_path.is_file():
        raise RunnerError("canonical receipts/media-manifest.json is required")
    slug = project.name
    out_name = f"{slug}-technical-preview"
    output = project / "final" / f"{out_name}.mp4"
    storyboard_path = project / "script" / "technical-preview-storyboard.json"
    receipt_path = project / "receipts" / "build-technical-preview-easel.json"
    existing = [path.exists() for path in (output, storyboard_path, receipt_path)]
    if all(existing):
        try:
            prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = {}
        same_inputs = (
            prior.get("status") == "PASS_TECHNICAL"
            and prior.get("input_manifest_sha256") == _sha256(manifest_path)
            and prior.get("storyboard_sha256") == _sha256(storyboard_path)
            and prior.get("output_sha256") == _sha256(output)
        )
        if same_inputs:
            print(json.dumps({"state": "ALREADY_BUILT", "output": str(output),
                              "sha256": prior["output_sha256"],
                              "receipt": str(receipt_path),
                              "production_ready": False, "publish_authorized": False},
                             ensure_ascii=False, indent=2))
            return 0
        raise RunnerError("existing technical preview artifacts do not match their receipt/input hashes")
    if any(existing):
        raise RunnerError("refusing to overwrite a partial technical preview artifact set")
    try:
        validated = validate_manifest_file(
            manifest_path, repo_root=ROOT, project_root=project
        )
        storyboard, bridge = build_m5_storyboard(
            validated, [], project_root=project, repo_root=ROOT,
            size="1080x1920", technical_preview=True,
        )
    except ManifestBridgeError as exc:
        raise RunnerError(f"technical preview manifest bridge blocked: {exc}") from None
    storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    import assemble_easel
    compose = assemble_easel.run(project, out_name=out_name, storyboard_path=storyboard_path)
    if compose.get("status") != "OK" or not output.is_file():
        raise RunnerError(f"pinned Easel compose failed: {compose.get('reason', compose)}")
    probe = _probe_video(output, project)
    decode = _decode_video(output, project)
    digest = _sha256(output)
    if decode.get("state") != "PASS":
        raise RunnerError(f"technical preview full decode failed: {decode}")
    qc = hidden_run(
        ["ffmpeg", "-hide_banner", "-i", str(output), "-vf", "blackdetect=d=0.1:pix_th=0.10",
         "-an", "-f", "null", "-"], timeout=300,
    )
    if qc.returncode != 0:
        raise RunnerError(f"technical preview black-frame scan failed: {(qc.stderr or '')[-500:]}")
    black_spans = re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", qc.stderr or "")
    source_checks = []
    assets_by_id = {asset.asset_id: asset for asset in validated.manifest.assets}
    for placement in bridge["placements"]:
        active = assets_by_id[placement["active_asset_id"]]
        source_id = active.derived_from or active.asset_id
        source_path = validated.asset_paths[source_id]
        compare = hidden_run(
            ["ffmpeg", "-hide_banner", "-i", str(source_path), "-i", str(output),
             "-lavfi", "[0:v]setpts=PTS-STARTPTS[ref];[1:v]setpts=PTS-STARTPTS[out];[ref][out]ssim",
             "-f", "null", "-"], timeout=300,
        )
        match = re.search(r"All:([0-9.]+)", compare.stderr or "")
        if compare.returncode != 0 or match is None:
            raise RunnerError(f"source visual comparison failed for {source_id}")
        source_checks.append({
            "source_asset_id": source_id,
            "source_sha256": validated.asset_sha256[source_id],
            "ssim_all": float(match.group(1)),
            "state": "PASS" if float(match.group(1)) >= 0.95 else "FAIL",
        })
    if any(item["state"] != "PASS" for item in source_checks):
        raise RunnerError(f"output does not visually match the M4.5 source: {source_checks}")
    receipt = {
        "schema": "contentops.technical-preview-build/v1",
        "status": "PASS_TECHNICAL",
        "project": f"projects/{slug}",
        "technical_sample_status": "TECHNICAL_SAMPLE_ONLY",
        "production_ready": False,
        "publish_authorized": False,
        "input_manifest": f"project://receipts/media-manifest.json",
        "input_manifest_sha256": validated.manifest_sha256,
        "input_manifest_fingerprint": validated.fingerprint,
        "bridge": bridge,
        "m5_storyboard_adapter": "contentops.media.manifest_m5_bridge.build_m5_storyboard(technical_preview=True)",
        "storyboard": "project://script/technical-preview-storyboard.json",
        "storyboard_sha256": _sha256(storyboard_path),
        "composer": {
            "status": compose.get("status"),
            "video": f"project://final/{output.name}",
            "upstream": "easel@v0.2.1:skills/openclaw/auto-short-video/scripts/assemble.py",
        },
        "easel": "v0.2.1 / 3fe2d9904c1619281ef57f81d9ee0b7854998399",
        "output": f"project://final/{output.name}",
        "output_sha256": digest,
        "output_bytes": output.stat().st_size,
        "probe": probe,
        "frame_count": len(probe.get("frame_timestamps") or []),
        "full_decode": decode,
        "black_detect_spans": black_spans,
        "source_visual_comparison": source_checks,
        "human_review": "PENDING_OWNER",
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print(json.dumps({"state": "PASS_TECHNICAL", "output": str(output),
                      "sha256": digest, "receipt": str(receipt_path),
                      "production_ready": False, "publish_authorized": False},
                     ensure_ascii=False, indent=2))
    return 0


def _recordly_intake(args: argparse.Namespace) -> int:
    """Preserve an Owner-supplied source take and record its technical facts."""
    project = _project(args.project)
    source = Path(args.file).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise RunnerError("--file must be an existing MP4, MOV, MKV, or WebM recording")
    recordings = project / "sources" / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source.name).strip("._") or "capture.mp4"
    target = recordings / f"recordly-original-{safe_name}"
    if target.exists():
        raise RunnerError(f"refusing to overwrite existing recording: {target.name}")
    receipt_path = project / "receipts" / "recordly-source-intake.json"
    if receipt_path.exists():
        raise RunnerError("refusing to overwrite existing recordly-source-intake.json")
    shutil.copy2(source, target)
    probe = _probe_video(target, project)
    if probe.get("error"):
        target.unlink()
        raise RunnerError(f"recording probe failed: {probe}")
    decode = _decode_video(target, project)
    if decode.get("state") != "PASS":
        raise RunnerError(f"recording full decode failed; original retained at {target}")
    receipt = {
        "schema": "contentops.recordly-source-intake/v1",
        "project": f"projects/{project.name}",
        "source_path": f"project://sources/recordings/{target.name}",
        "source_sha256": _sha256(target), "bytes": target.stat().st_size,
        "owner_supplied": True, "recordly_capture_claimed_by_owner": True,
        "probe": probe, "full_decode": decode,
        "shot_mapping": "PENDING_OWNER_REVIEW",
        "claim_mapping": "PENDING_OWNER_REVIEW",
        "rights_status": "PENDING_OWNER_REVIEW",
        "visible_current_source_seconds": "NOT_MEASURED",
        "production_ready": False, "publish_authorized": False,
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"state": "RECEIVED_TECHNICAL_CHECKED",
                      "recording": str(target), "sha256": receipt["source_sha256"],
                      "receipt": str(receipt_path), "rights_status": "PENDING_OWNER_REVIEW",
                      "production_ready": False, "publish_authorized": False},
                     ensure_ascii=False, indent=2))
    return 0


def _video_qc(args: argparse.Namespace) -> int:
    project = _project(args.project)
    video = project / "final" / f"{project.name}.mp4"
    if not video.is_file():
        raise RunnerError("the fixed final MP4 is missing")
    import qc_video
    return int(qc_video.main([str(project), "--video", video.name]))


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.task == "runtime-status":
            result = huashu_motion.verify_runtime(huashu_motion.DEFAULT_RUNTIME,
                                                  git_probe=_git_probe)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0 if result.get("status") == "TRUSTED_RUNTIME" else 2
        if args.task in _OPERATION_FOR_TASK:
            return _motion_operation(args)
        if args.task == "motion-validate":
            return _motion_validate(args)
        if args.task == "manifest-register":
            return _manifest_register(args)
        if args.task == "easel-compose":
            return _easel_compose(args)
        if args.task == "technical-preview":
            return _technical_preview(args)
        if args.task == "recordly-intake":
            return _recordly_intake(args)
        if args.task == "video-qc":
            return _video_qc(args)
        raise RunnerError("unsupported task")
    except (RunnerError, OSError, ValueError, ManifestBridgeError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": type(exc).__name__,
                          "detail": str(exc), "execution_authorized": False,
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
