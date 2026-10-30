#!/usr/bin/env python3
"""Run the retention gate over every account project.

Exposes the measurable visual/ops problems: one visual held too long, a hook
that is too slow, missing captions, a missing cover, or a missing CTA. It writes
a receipt and updates the run state; it does not re-render anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402
from contentops.accounts import video_accounts  # noqa: E402
from contentops.optimization.retention import evaluate_retention  # noqa: E402


def probe_duration(path: Path) -> float:
    if not path.is_file():
        return 0.0
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ], timeout=60)
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        return 0.0


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_account(slug: str, dna_path: Path) -> dict:
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    project = ROOT / "projects" / slug
    storyboard = json.loads((project / "script" / "storyboard.json")
                            .read_text(encoding="utf-8"))
    receipt = json.loads((project / "receipts" / "variant-receipt.json")
                         .read_text(encoding="utf-8"))
    captions = receipt.get("captions") or {}
    intro = receipt.get("intro") or {}
    intro_path = ROOT / str(intro.get("used") or "")
    cover = (project / "final" / "cover.png").is_file()

    result = evaluate_retention(
        storyboard=storyboard,
        spec={"account": dna.get("account"), "cta": dna.get("narrative", {}).get("cta"),
              "retention": dna.get("retention") or {}},
        captions_burned=bool(captions.get("burned")),
        caption_cues=int(captions.get("cues") or 0),
        intro_duration=probe_duration(intro_path),
        cover_exists=cover,
    )
    write_json(project / "receipts" / "retention-check.json", result)

    state_path = project / "receipts" / "run-state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        stages = [stage for stage in state.get("stages", [])
                  if stage.get("name") != "RETENTION"]
        insert_at = next(
            (index for index, stage in enumerate(stages) if stage.get("name") == "EDITORIAL_QC"),
            len(stages) - 1,
        ) + 1
        stages.insert(insert_at, {
            "name": "RETENTION",
            "status": result["overall"],
            "evidence": "project://receipts/retention-check.json",
            "failures": result["failures"],
        })
        state["stages"] = stages
        write_json(state_path, state)

    checklist_path = project / "receipts" / "publish-checklist.json"
    if checklist_path.is_file():
        checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
        checks = [check for check in checklist.get("checks", [])
                  if check.get("id") != "retention"]
        checks.append({
            "id": "retention",
            "ok": result["overall"] == "PASS",
            "status": result["overall"],
            "failures": result["failures"],
        })
        checklist["checks"] = checks
        write_json(checklist_path, checklist)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    results = []
    # Retention measures a video project; the X account has no film to retain.
    for dna_path, dna in video_accounts(root=ROOT):
        results.append(run_account(dna["slug"], dna_path))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for result in results:
        print(
            f"{result['account']}: {result['overall']} · "
            f"longest visual {result['longest_visual_run_s']}s · "
            f"captions {result['caption_cues']}"
        )
        for failure in result["failures"]:
            detail = next(check for check in result["checks"] if check["id"] == failure)
            print(f"  - {failure}: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
