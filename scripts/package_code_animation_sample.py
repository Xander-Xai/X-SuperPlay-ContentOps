#!/usr/bin/env python3
"""Package a code-animation sample for human review.

Renders the cover through the shared card renderer (with the card-design
audit), then writes the three artefacts a cut needs before a person looks at
it: a cover receipt, a review bundle with an input fingerprint, and a
human-review stub whose every score is null.

It never records a score and never reports production readiness.

Usage::

    python scripts/package_code_animation_sample.py projects/easel-fi-what-is-agent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402

RENDER_CARD = ROOT / ".runtime" / "easel" / "skills" / "shared" / "scripts" / "render_card.py"
CARD_AUDIT = ROOT / ".runtime" / "easel" / "skills" / "openclaw" / "card-design" / "scripts" / "card_audit.py"

REVIEW_DIMENSIONS = [
    ("hook", 15), ("information_density", 15), ("evidence_quality", 15),
    ("voice_naturalness", 15), ("visual_quality", 15), ("pacing", 10),
    ("platform_fit", 10), ("trustworthiness", 5),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _card_python() -> str:
    """Interpreter for the shared card renderer.

    The renderer needs a Playwright build whose Chromium revision is present on
    this machine; the project venv's Playwright may expect one that is not.
    ``CONTENTOPS_CARD_PYTHON`` points the renderer at a matching interpreter.
    """
    return os.environ.get("CONTENTOPS_CARD_PYTHON") or python_executable()


def _run(command: List[str], cwd: Path) -> str:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = hidden_run(command, cwd=str(cwd), timeout=300, env=env)
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(command)}\n{text[-600:]}")
    return text


def _assert_review_is_pending(receipts_dir: Path, fingerprint: str) -> None:
    """Never replace a human decision with a freshly generated pending stub."""
    human_path = receipts_dir / "human-review.json"
    if not human_path.is_file():
        return
    try:
        human = json.loads(human_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot safely replace unreadable human review: {human_path}") from exc
    if human.get("status") not in (None, "PENDING_FOUNDER_REVIEW"):
        if human.get("review_bundle_fingerprint") != fingerprint:
            raise SystemExit("human review is bound to another review bundle; refusing overwrite")
        raise SystemExit("human review already exists; refusing to overwrite the decision")
    scores = human.get("scores")
    if isinstance(scores, dict) and any(value is not None for value in scores.values()):
        raise SystemExit("human review contains scores; refusing to overwrite the decision")


def _project_input(project: Path, name: str, logical_path: str) -> tuple[str, str]:
    """Hash a declared project asset without allowing paths outside the package."""
    relative = logical_path.removeprefix("project://")
    path = (project / relative).resolve()
    try:
        canonical = path.relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{name} path escapes the project: {logical_path}") from exc
    if not path.is_file():
        raise SystemExit(f"{name} is missing: {logical_path}")
    return f"project://{canonical}", _sha(path)


def _motion_inputs(project: Path, sample: Dict[str, Any]) -> Dict[str, tuple[str, str]]:
    """Bind the composition timeline and any declared presenter to review."""
    timeline_path = project / "motion" / "timeline.json"
    if not timeline_path.is_file():
        raise SystemExit("motion review package requires motion/timeline.json")
    inputs = {"timeline": ("project://motion/timeline.json", _sha(timeline_path))}

    presenter_contract_path = project / "motion" / "presenter" / "contract.json"
    presenter = (sample.get("voice") or {}).get("presenter") or {}
    has_presenter = bool(sample.get("timeline", {}).get("presenter"))
    if presenter_contract_path.is_file():
        inputs["presenter_contract"] = (
            "project://motion/presenter/contract.json", _sha(presenter_contract_path))
    elif has_presenter:
        raise SystemExit("presenter segment has no declared motion/presenter/contract.json")
    if has_presenter:
        for name, path_key, hash_key in (
                ("presenter_audio", "path", "wav_sha256"),
                ("presenter_media", "shot", "shot_sha256")):
            logical = presenter.get(path_key)
            expected_sha = presenter.get(hash_key)
            if not logical or not expected_sha:
                raise SystemExit(f"presenter record has no {name} path or recorded hash")
            bound_path, actual_sha = _project_input(project, name, logical)
            if actual_sha != expected_sha:
                raise SystemExit(f"presenter {name} differs from voice-lines.json hash")
            inputs[name] = (bound_path, actual_sha)
    return inputs


def _variant_io(variant: str) -> Dict[str, Path]:
    """Variant outputs stay in their own namespace; the baseline keeps its files."""
    if variant == "eras":
        return {"sample": Path("receipts/eras/sample.json"), "receipts": Path("receipts/eras"),
                "cover_png": Path("assets/covers/cover-eras.png")}
    return {"sample": Path("receipts/sample.json"), "receipts": Path("receipts"),
            "cover_png": Path("assets/covers/cover.png")}


def render_cover(project: Path, png_rel: Path = Path("assets/covers/cover.png"),
                 receipts: Path = Path("receipts")) -> Dict[str, Any]:
    html = project / "assets" / "covers" / "cover.html"
    png = project / png_rel
    if not html.is_file():
        return {}
    _run([_card_python(), str(RENDER_CARD), "--html", str(html),
          "--out", str(png), "--full-page", "--scale", "1",
          "--width", "1080", "--height", "1440"], ROOT / ".runtime" / "easel")
    audit = _run([_card_python(), str(CARD_AUDIT), "audit", "-f", str(png)],
                 ROOT / ".runtime" / "easel")
    passed = "✅" in audit or "PASS" in audit
    receipt = {
        "schema": "contentops.cover-receipt/v1",
        "platform": "douyin",
        "width": 1080,
        "height": 1440,
        "html": {"path": "project://assets/covers/cover.html", "sha256": _sha(html)},
        "png": {"path": f"project://{png_rel.as_posix()}", "sha256": _sha(png)},
        "audit": audit.strip(),
        "audit_passed": passed,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (project / receipts / "cover.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit(f"cover audit failed:\n{audit.strip()}")
    return receipt


def _runtime_receipt(package_id: str, sample: Dict[str, Any]) -> str:
    duration = float(sample["timeline"]["total_s"])
    visual = sample.get("visual_track", {})
    visual_line = (
        "- visual track: huashu eras full-film render, " + visual["path"]
        if visual.get("mode") == "full_film_eras"
        else "- visual track: measured beat clips assembled by ContentOps"
    )
    return "\n".join([
        "# Runtime receipt — " + package_id,
        "",
        "- engine: huashu-art-motion (MIT), `scripts/engine/render.py`, upstream `8a0d7d7`",
        "- interpreter: host Python; Playwright Chromium `D:\\DevCaches\\ms-playwright\\chromium-1223`",
        "- env: `PYTHONUTF8=1`; browser launch falls back bundled → Chrome → Edge",
        "- render: `render.py --spec motion/specs/p0N.json --out work/clips/p0N.mp4`",
        visual_line,
        "- compose: `python scripts/build_code_animation_sample.py " + package_id + "`",
        "- grade: `python scripts/qc_video.py " + package_id + " --video easel.mp4`",
        "",
        f"Measured duration: `{duration:.1f} s`.",
        "Verdict: technical QC is recorded separately; it never creates production approval.",
        "`production_ready: false`, `PENDING_FOUNDER_REVIEW`.",
    ]) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--variant", choices=("easel", "eras"), default="easel")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    io = _variant_io(args.variant)

    sample_path = project / io["sample"]
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    video = project / sample["output"]["path"].replace("project://", "")
    if _sha(video) != sample["output"]["sha256"]:
        raise SystemExit("final video changed after its sample receipt; re-run the composer")

    cover = render_cover(project, io["cover_png"], io["receipts"])

    qc_report = (project / "receipts" / "qc-report-eras.json" if args.variant == "eras"
                 else project / "receipts" / "qc-summary.json")
    inputs = {
        "video": ("project://" + video.relative_to(project).as_posix(), _sha(video)),
        "sample": (f"project://{io['sample'].as_posix()}", _sha(sample_path)),
        "qc": (f"project://{qc_report.relative_to(project).as_posix()}", _sha(qc_report)),
        "voice": ("project://receipts/voice-lines.json", _sha(project / "receipts" / "voice-lines.json")),
        "captions": (sample["captions"]["path"], sample["captions"]["sha256"]),
    }
    inputs.update(_motion_inputs(project, sample))

    # Bind the review package to the exact copy approval authorising its build.
    from contentops.workflow.copy_review import require_approved
    approval = require_approved(project)
    inputs["copy_review"] = (
        "project://receipts/script-review.json",
        _sha(project / "receipts" / "script-review.json"))
    if sample.get("visual_track", {}).get("mode") == "full_film_eras":
        film = project / sample["visual_track"]["path"].replace("project://", "")
        inputs["eras_film"] = (sample["visual_track"]["path"], _sha(film))
        for name in ("eras.js", "index.html", "render.py"):
            source = project / "motion" / "film" / name
            inputs[f"eras_source:{name}"] = (f"project://motion/film/{name}", _sha(source))
    if cover:
        inputs["cover"] = (f"project://{io['cover_png'].as_posix()}", cover["png"]["sha256"])
    for spec in sorted((project / "motion" / "specs").glob("p*.json")):
        inputs[f"spec:{spec.stem}"] = (f"project://motion/specs/{spec.name}", _sha(spec))

    fingerprint = hashlib.sha256(
        "".join(f"{name}:{digest}\n" for name, (_, digest) in sorted(inputs.items())).encode("utf-8")
    ).hexdigest()
    bundle = {
        "schema": "contentops.review-bundle/v1",
        "package_id": project.name,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {name: {"path": path, "sha256": digest} for name, (path, digest) in sorted(inputs.items())},
        "review_bundle_fingerprint": fingerprint,
        "score": None,
        "reviewer": None,
        "hard_fail": None,
        "status": "PENDING_HUMAN_REVIEW",
        "production_ready": False,
    }
    receipts_dir = project / io["receipts"]
    receipts_dir.mkdir(parents=True, exist_ok=True)
    _assert_review_is_pending(receipts_dir, fingerprint)
    (receipts_dir / "review-bundle.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    human = {
        "schema": "contentops.human-review/v1",
        "package_id": project.name,
        "review_bundle_fingerprint": fingerprint,
        "scores": {name: None for name, _ in REVIEW_DIMENSIONS},
        "weights": {name: weight for name, weight in REVIEW_DIMENSIONS},
        "total": None,
        "hard_fail": None,
        "notes": None,
        "reviewer": None,
        "reviewed_at": None,
        "status": "PENDING_FOUNDER_REVIEW",
        "production_ready": False,
    }
    (receipts_dir / "human-review.json").write_text(
        json.dumps(human, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    runtime = receipts_dir / "runtime-receipt.md"
    runtime.write_text(_runtime_receipt(project.name, sample), encoding="utf-8")

    print(json.dumps({
        "status": "OK",
        "cover": cover.get("audit_passed") if cover else "missing",
        "fingerprint": fingerprint,
        "review": "PENDING_HUMAN_REVIEW",
        "production_ready": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
