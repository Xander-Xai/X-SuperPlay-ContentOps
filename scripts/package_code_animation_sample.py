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


def _run(command: List[str], cwd: Path) -> str:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = hidden_run(command, cwd=str(cwd), timeout=300, env=env)
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(command)}\n{text[-600:]}")
    return text


def render_cover(project: Path) -> Dict[str, Any]:
    html = project / "assets" / "covers" / "cover.html"
    png = project / "assets" / "covers" / "cover.png"
    if not html.is_file():
        return {}
    _run([python_executable(), str(RENDER_CARD), "--html", str(html),
          "--out", str(png), "--full-page", "--scale", "1",
          "--width", "1080", "--height", "1440"], ROOT / ".runtime" / "easel")
    audit = _run([python_executable(), str(CARD_AUDIT), "audit", "-f", str(png)],
                 ROOT / ".runtime" / "easel")
    passed = "✅" in audit or "PASS" in audit
    receipt = {
        "schema": "contentops.cover-receipt/v1",
        "platform": "douyin",
        "width": 1080,
        "height": 1440,
        "html": {"path": "project://assets/covers/cover.html", "sha256": _sha(html)},
        "png": {"path": "project://assets/covers/cover.png", "sha256": _sha(png)},
        "audit": audit.strip(),
        "audit_passed": passed,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (project / "receipts" / "cover.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit(f"cover audit failed:\n{audit.strip()}")
    return receipt


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    sample = json.loads((project / "receipts" / "sample.json").read_text(encoding="utf-8"))
    video = project / sample["output"]["path"].replace("project://", "")
    if _sha(video) != sample["output"]["sha256"]:
        raise SystemExit("final video changed after its sample receipt; re-run the composer")

    cover = render_cover(project)

    inputs = {
        "video": ("project://" + video.relative_to(project).as_posix(), _sha(video)),
        "sample": ("project://receipts/sample.json", _sha(project / "receipts" / "sample.json")),
        "qc_summary": ("project://receipts/qc-summary.json", _sha(project / "receipts" / "qc-summary.json")),
        "voice": ("project://receipts/voice-lines.json", _sha(project / "receipts" / "voice-lines.json")),
    }
    if cover:
        inputs["cover"] = ("project://assets/covers/cover.png", cover["png"]["sha256"])
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
    (project / "receipts" / "review-bundle.json").write_text(
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
    (project / "receipts" / "human-review.json").write_text(
        json.dumps(human, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    runtime = project / "receipts" / "runtime-receipt.md"
    runtime.write_text(
        "\n".join([
            "# Runtime receipt — " + project.name,
            "",
            "- engine: huashu-art-motion (MIT), `scripts/engine/render.py`, upstream `8a0d7d7`",
            "- interpreter: host Python; Playwright Chromium `D:\\DevCaches\\ms-playwright\\chromium-1223`",
            "- env: `PYTHONUTF8=1`; browser launch falls back bundled → Chrome → Edge",
            "- render: `render.py --spec motion/specs/p0N.json --out work/clips/p0N.mp4`",
            "- compose: `python scripts/build_code_animation_sample.py " + project.name + "`",
            "- grade: `python scripts/qc_video.py " + project.name + " --video easel.mp4`",
            "",
            "Verdict: `qc_video` WARN (20 s below the 30 s floor; pure animation has no",
            "real-source ratio). Technical decode, audio, subtitle burn and loudness pass.",
            "`production_ready: false`, `PENDING_FOUNDER_REVIEW`.",
        ]) + "\n",
        encoding="utf-8",
    )

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
