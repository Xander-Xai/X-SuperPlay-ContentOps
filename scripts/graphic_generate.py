#!/usr/bin/env python3
"""Generate one graphic support image through an explicitly selected method.

This command makes one provider attempt only when both ``--execute`` and
``--authorize-provider-usage`` are present. It never retries or falls back.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_popen  # noqa: E402
from contentops.graphic.image_methods import CODEX_METHODS, IMAGE_METHODS, IAN_SKILL_ID, MINIMAX_METHOD  # noqa: E402
from contentops.graphic.image_generation import (  # noqa: E402
    ASPECT_RATIO,
    GraphicImageGenerationError,
    copy_new_image,
    create_generation_receipt,
    load_ian_prompt,
    prompt_sha256,
    run_codex_image,
    validate_prompt,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--method", required=True, choices=IMAGE_METHODS)
    parser.add_argument("--project", required=True, help="graphic project directory")
    parser.add_argument("--asset-id", required=True, help="safe asset identifier; one image per run")
    parser.add_argument("--prompt-file", help="project-relative UTF-8 prompt file (Codex or MiniMax)")
    parser.add_argument("--article", help="Ian route: project-relative approved article path")
    parser.add_argument("--skill-output", help="Ian route: project-relative JSON returned by the host Skill")
    parser.add_argument("--scratch-root", help="operator-selected temporary root for Codex work and MiniMax cache")
    parser.add_argument("--width", type=int, default=1024, help="MiniMax width; image-01 requires multiples of 8")
    parser.add_argument("--height", type=int, default=576, help="MiniMax height; image-01 requires multiples of 8")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=900, help="Codex timeout in seconds; no retry")
    parser.add_argument("--execute", action="store_true", help="perform the selected generation")
    parser.add_argument("--authorize-provider-usage", action="store_true",
                        help="explicitly authorize one subscription/provider attempt")
    return parser


def _project_file(project: Path, value: str, label: str) -> Path:
    relative = Path(str(value or ""))
    if not value or relative.is_absolute() or ".." in relative.parts:
        raise GraphicImageGenerationError("INPUT_PATH_INVALID", f"{label} must be project-relative")
    raw = project / relative
    current = project
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise GraphicImageGenerationError("INPUT_PATH_INVALID", f"{label} must not use symlinks")
    resolved = raw.resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError:
        raise GraphicImageGenerationError("INPUT_PATH_INVALID", f"{label} escapes the project") from None
    if not resolved.is_file():
        raise GraphicImageGenerationError("INPUT_FILE_MISSING", f"{label} does not exist")
    return resolved


def _codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME", "").strip()
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".codex").resolve()


def _run_codex_process(prompt: str, cwd: Path, timeout: int):
    executable = shutil.which("codex")
    if not executable:
        raise GraphicImageGenerationError("CODEX_NOT_INSTALLED", "codex executable was not found on PATH")
    command = [
        executable, "exec", "--ephemeral", "--sandbox", "workspace-write",
        "--skip-git-repo-check", "--ignore-user-config", "--json", "-",
    ]
    try:
        process = hidden_popen(
            command, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
    except OSError:
        raise GraphicImageGenerationError("CODEX_START_FAILED", "Codex could not be started; no retry attempted") from None
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise GraphicImageGenerationError("CODEX_TIMEOUT", "Codex timed out; no retry attempted") from None
    return SimpleNamespace(returncode=process.returncode, stdout=stdout, stderr=stderr)


def _read_prompt(project: Path, prompt_file: str) -> str:
    path = _project_file(project, prompt_file, "prompt file")
    try:
        return validate_prompt(path.read_text(encoding="utf-8"))
    except UnicodeError:
        raise GraphicImageGenerationError("PROMPT_NOT_UTF8", "prompt file must be UTF-8") from None


def _minimax_generate(project: Path, scratch_root: Path, prompt: str,
                      width: int, height: int, seed, generation_id: str):
    if not width or not height or abs((width / height) - ASPECT_RATIO) / ASPECT_RATIO > 0.02:
        raise GraphicImageGenerationError("IMAGE_ASPECT_INVALID", "MiniMax graphic requests must be 16:9 within 2%")
    from contentops.media.image_fingerprint import DimensionRejected, validate_dimensions

    try:
        validate_dimensions(width, height)
    except DimensionRejected as exc:
        raise GraphicImageGenerationError("DIMENSIONS_REJECTED_LOCALLY", str(exc)) from None

    import generate_image

    output_dir = scratch_root / "minimax-cache"
    if output_dir.is_symlink():
        raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "MiniMax cache directory must not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.resolve().relative_to(scratch_root.resolve())
    except ValueError:
        raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "MiniMax cache escaped scratch root") from None
    argv = [
        "--prompt", prompt,
        "--out-dir", str(output_dir),
        "--model", "image-01",
        "--width", str(width), "--height", str(height),
    ]
    if seed is not None:
        argv.extend(("--seed", str(seed)))
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = generate_image.main(argv)
    try:
        payload = json.loads(captured.getvalue())
    except ValueError:
        raise GraphicImageGenerationError("MINIMAX_RECEIPT_INVALID", "provider wrapper returned invalid JSON") from None
    if code != 0 or payload.get("status") != "OK":
        verdict = str(payload.get("verdict") or payload.get("status") or "FAILED")
        raise GraphicImageGenerationError("MINIMAX_GENERATION_BLOCKED", f"MiniMax returned {verdict}; no fallback attempted")
    output = Path(str(payload.get("canonical_path") or "")).resolve()
    try:
        output.relative_to(scratch_root.resolve())
    except ValueError:
        raise GraphicImageGenerationError("MINIMAX_OUTPUT_PATH_INVALID", "MiniMax output escaped scratch root") from None
    if not output.is_file():
        raise GraphicImageGenerationError("MINIMAX_OUTPUT_MISSING", "MiniMax receipt names no image file")
    from contentops.media.transport import sidecar_for
    raw_receipt_path = sidecar_for(output)
    if raw_receipt_path.is_symlink() or not raw_receipt_path.is_file():
        raise GraphicImageGenerationError("MINIMAX_RECEIPT_INVALID", "MiniMax provider receipt is missing or linked")
    try:
        source_receipt_path = raw_receipt_path.resolve().relative_to(scratch_root.resolve()).as_posix()
    except ValueError:
        raise GraphicImageGenerationError("MINIMAX_RECEIPT_INVALID", "MiniMax receipt escaped scratch root") from None
    raw_receipt = raw_receipt_path.read_bytes()
    summary = {
        "schema": "contentops.graphic-minimax-provider-observation/v1",
        "generation_id": generation_id,
        "provider_receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(),
        "provider_receipt_source": source_receipt_path,
        "provider": "minimax_m_plan",
        "model": "image-01",
        "billing_mode": payload.get("billing_mode"),
        "payg_allowed": payload.get("payg_allowed"),
        "credit_pack_allowed": payload.get("credit_pack_allowed"),
        "billing_guard_verdict": payload.get("billing_guard_verdict"),
        "quota_before": payload.get("quota_before"),
        "quota_after": payload.get("quota_after"),
        "provider_call": payload.get("provider_call"),
        "reused": payload.get("reused"),
        "prompt_sha256": payload.get("prompt_sha256"),
        "output_sha256": payload.get("output_sha256"),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "generated": payload.get("generated"),
        "evidence_capable": payload.get("evidence_capable"),
    }
    receipts = project / "receipts"
    if receipts.is_symlink():
        raise GraphicImageGenerationError("RECEIPT_PATH_INVALID", "project receipts directory must not be a symlink")
    receipts.mkdir(parents=True, exist_ok=True)
    summary_path = receipts / f"graphic-minimax-provider-{generation_id}.json"
    with summary_path.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return output, payload, summary_path, summary


def _resolve_request(args, project: Path):
    if args.method == "ian_xiaohei_codex":
        if not args.article or not args.skill_output or args.prompt_file:
            raise GraphicImageGenerationError(
                "IAN_INPUT_REQUIRED", "Ian route requires --article and --skill-output, not --prompt-file")
        article = _project_file(project, args.article, "article")
        skill_output = _project_file(project, args.skill_output, "Skill output")
        selected = load_ian_prompt(project, args.article, skill_output, args.asset_id)
        if article.read_bytes() == b"":
            raise GraphicImageGenerationError("ARTICLE_EMPTY", "article has no content")
        return selected["prompt"], selected["alt"], selected["article_sha256"]
    if args.article or args.skill_output:
        raise GraphicImageGenerationError("IAN_INPUT_UNEXPECTED", "--article/--skill-output are Ian-route only")
    if not args.prompt_file:
        raise GraphicImageGenerationError("PROMPT_REQUIRED", "--prompt-file is required")
    return _read_prompt(project, args.prompt_file), "", None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project = Path(args.project).resolve()
        if not project.is_dir():
            raise GraphicImageGenerationError("PROJECT_MISSING", "project directory does not exist")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.asset_id):
            raise GraphicImageGenerationError("ASSET_ID_INVALID", "asset_id must be a safe 1..64 character identifier")
        if not 1 <= args.timeout <= 3600:
            raise GraphicImageGenerationError("TIMEOUT_INVALID", "timeout must be between 1 and 3600 seconds")
        if args.method in CODEX_METHODS:
            if not args.scratch_root:
                raise GraphicImageGenerationError("SCRATCH_ROOT_REQUIRED", "Codex requires an explicit scratch root")
            if args.width != 1024 or args.height != 576 or args.seed is not None:
                raise GraphicImageGenerationError("CODEX_OPTIONS_UNSUPPORTED", "width/height/seed flags are MiniMax-only")
        elif args.method == MINIMAX_METHOD:
            if not args.scratch_root:
                raise GraphicImageGenerationError("SCRATCH_ROOT_REQUIRED", "MiniMax cache requires an explicit scratch root")
            if args.timeout != 900:
                raise GraphicImageGenerationError("MINIMAX_OPTIONS_INVALID", "timeout is Codex-only")
        prompt, alt, article_sha = _resolve_request(args, project)
        if args.execute != args.authorize_provider_usage:
            raise GraphicImageGenerationError(
                "EXPLICIT_AUTHORIZATION_REQUIRED",
                "real generation needs both --execute and --authorize-provider-usage; one image only",
            )
        if not args.execute:
            print(json.dumps({
                "state": "READY_FOR_EXPLICIT_EXECUTION",
                "method": args.method,
                "asset_id": args.asset_id,
                "prompt_sha256": prompt_sha256(prompt),
                "images_to_generate": 1,
                "provider_call": False,
                "publish_authorized": False,
            }, ensure_ascii=False, indent=2))
            return 0
        run_id = uuid.uuid4().hex[:24]
        scratch_input = Path(args.scratch_root).expanduser()
        if not scratch_input.is_absolute() or scratch_input.is_symlink():
            raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "scratch root must be an absolute, non-symlink path")
        scratch_root = scratch_input.resolve()
        try:
            scratch_root.relative_to(project.resolve())
        except ValueError:
            pass
        else:
            raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "scratch root must be outside the project")
        try:
            project.resolve().relative_to(scratch_root)
        except ValueError:
            pass
        else:
            raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "scratch root must not contain the project")
        try:
            scratch_root.relative_to(ROOT.resolve())
        except ValueError:
            pass
        else:
            raise GraphicImageGenerationError("SCRATCH_ROOT_INVALID", "scratch root must be outside the repository")
        scratch_root.mkdir(parents=True, exist_ok=True)
        skill_id = IAN_SKILL_ID if args.method == "ian_xiaohei_codex" else None
        provider_receipt = None
        provider_receipt_path = None
        if args.method in CODEX_METHODS:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            scratch = scratch_root / f"graphic-codex-{stamp}-{run_id[:8]}"
            generated = run_codex_image(
                prompt, _codex_home() / "generated_images", scratch,
                lambda text: _run_codex_process(text, scratch, args.timeout),
            )
            output = copy_new_image(generated, project, args.asset_id, run_id)
            provider, model = "openai-codex", "not_reported"
        elif args.method == MINIMAX_METHOD:
            source, _, provider_receipt_path, provider_receipt = _minimax_generate(
                project, scratch_root, prompt, args.width, args.height, args.seed, run_id)
            output = copy_new_image(source, project, args.asset_id, run_id)
            provider, model = "minimax", "image-01"
        else:  # pragma: no cover - argparse restricts choices
            raise GraphicImageGenerationError("IMAGE_METHOD_UNKNOWN", args.method)

        receipt = create_generation_receipt(
            project, method=args.method, provider=provider, model=model,
            prompt=prompt, output_path=output, skill_id=skill_id,
            article_path=args.article if args.method == "ian_xiaohei_codex" else None,
            article_sha256=article_sha,
            generation_id=run_id, provider_receipt=provider_receipt,
            provider_receipt_path=provider_receipt_path,
        )
        relative_output = output.relative_to(project).as_posix()
        payload = {
            "state": "GENERATED_PENDING_REVIEW",
            "method": args.method,
            "asset_id": args.asset_id,
            "image": {
                "path": relative_output,
                "alt": alt,
                "generation": {
                    "receipt": receipt["receipt_path"],
                    "generation_id": receipt["generation_id"],
                },
            },
            "generation_receipt": receipt["receipt_path"],
            "generation_id": receipt["generation_id"],
            "prompt_sha256": receipt["prompt_sha256"],
            "output_sha256": receipt["output_sha256"],
            "dimensions": {"width": receipt["width"], "height": receipt["height"]},
            "rights_review_status": "REQUIRED",
            "human_review": "NOT_STARTED",
            "generated": True,
            "evidence_capable": False,
            "production_ready": False,
            "publish_authorized": False,
            "article_sha256": article_sha,
        }
        if provider_receipt:
            payload["provider_call"] = provider_receipt.get("provider_call")
            payload["reused"] = provider_receipt.get("reused")
        else:
            payload["provider_call"] = True
            payload["quota_delta"] = "NOT_REPORTED_BY_CODEX_CLI"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except GraphicImageGenerationError as exc:
        print(json.dumps({"state": "BLOCKED", "error": exc.code,
                          "detail": exc.detail, "generated": False,
                          "publish_authorized": False}, ensure_ascii=False, indent=2))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
