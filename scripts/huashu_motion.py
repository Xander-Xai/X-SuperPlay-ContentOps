"""Pin check and explicit handoff for an existing huashu-motion MP4.

Never installs or invokes the external skill. A human-approved local environment
runs om check/render/qa separately. This CLI only verifies the exported bytes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for base in (ROOT / "src", ROOT / "scripts"):
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

from contentops.media.huashu_motion import (  # noqa: E402
    HuashuMotionError, make_handoff, verify_runtime,
)
from check_motion_sample import _probe  # noqa: E402
from process_utils import hidden_run  # noqa: E402

LOCK = ROOT / "runtime" / "huashu-motion.lock.json"
DEFAULT_RUNTIME = ROOT / ".runtime" / "huashu-motion"


def _identity(runtime: Path) -> dict:
    if not runtime.is_dir():
        raise HuashuMotionError("HUASHU_RUNTIME_MISSING", str(runtime))
    result = hidden_run(["git", "-C", str(runtime), "rev-parse", "HEAD"],
                        timeout=20)
    if result.returncode != 0:
        raise HuashuMotionError("HUASHU_RUNTIME_UNVERIFIED",
                                "could not read local git HEAD")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    return verify_runtime(runtime=runtime, lock=lock,
                          observed_commit=result.stdout.strip())


def _project_path(project: Path, relative: str) -> Path:
    text = str(relative or "").replace("\\", "/")
    if (not text or text.startswith("/") or ".." in text.split("/")
            or ":" in text):
        raise HuashuMotionError("HUASHU_REQUEST_PATH", "require project-relative path")
    result = (project / text).resolve()
    if not result.is_relative_to(project.resolve()):
        raise HuashuMotionError("HUASHU_REQUEST_PATH", "path escapes project")
    return result


def _append_candidate(project: Path, candidate: dict) -> None:
    path = project / "sources" / "assets.json"
    if not path.is_file():
        raise HuashuMotionError("HUASHU_M5_MANIFEST_MISSING", str(path))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
        raise HuashuMotionError("HUASHU_M5_MANIFEST_SCHEMA", "missing assets array")
    if any(str(item.get("id")) == candidate["id"] for item in manifest["assets"]):
        raise HuashuMotionError("HUASHU_M5_DUPLICATE", candidate["id"])
    manifest["assets"].append(candidate)
    # Atomic replacement, rather than truncating the only source asset record.
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".huashu.tmp",
            prefix=".assets-", dir=path.parent, delete=False
        ) as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            tmp = Path(stream.name)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "package"))
    parser.add_argument("project", nargs="?")
    parser.add_argument("--request", default="motion/huashu-request.json")
    parser.add_argument("--runtime", default=str(DEFAULT_RUNTIME))
    parser.add_argument("--apply-m5", action="store_true")
    args = parser.parse_args(argv)
    try:
        identity = _identity(Path(args.runtime))
        if args.command == "doctor":
            executables = {
                name: bool(shutil.which(name))
                for name in ("node", "ffmpeg", "ffprobe")
            }
            executables["browser_on_path"] = bool(
                any(shutil.which(x) for x in
                    ("chrome", "chromium", "msedge", "chrome.exe", "msedge.exe"))
            )
            result = {
                "state": "PIN_VERIFIED",
                "runtime": identity,
                "executables": executables,
                "note": "Does not prove rendering or host execution authorization.",
            }
        else:
            if not args.project:
                raise HuashuMotionError("HUASHU_PROJECT_REQUIRED", "supply a project")
            project = (ROOT / args.project).resolve()
            if not project.is_dir() or not project.is_relative_to(ROOT):
                raise HuashuMotionError("HUASHU_PROJECT_INVALID", str(project))
            request_path = _project_path(project, args.request)
            request = json.loads(request_path.read_text(encoding="utf-8"))
            output = str(request.get("output") or "")
            if not output.startswith("project://"):
                raise HuashuMotionError("HUASHU_PATH_SCHEME", "output must be project://")
            video = _project_path(project, output[len("project://"):])
            handoff = make_handoff(
                project=project, repo_root=ROOT, request=request,
                runtime_identity=identity, probe=_probe(video)
            )
            if args.apply_m5:
                _append_candidate(project, handoff["m5_asset_candidate"])
            receipt = project / "receipts" / "huashu-motion-handoff.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(
                json.dumps(handoff, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = {
                "state": handoff["state"],
                "receipt": "project://receipts/huashu-motion-handoff.json",
                "m5_asset_added": bool(args.apply_m5),
                "human_review": "PENDING_FOUNDER_REVIEW",
                "production_ready": False,
                "publish_authorized": False,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HuashuMotionError, OSError, ValueError, KeyError) as exc:
        code = exc.code if isinstance(exc, HuashuMotionError) else "HUASHU_INPUT_INVALID"
        print(json.dumps({"state": "BLOCKED", "error": code, "detail": str(exc)},
                         ensure_ascii=False))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
