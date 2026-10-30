#!/usr/bin/env python3
"""Observe a reference film, derive the episode budget, verify the finished cut.

This is the entrypoint the pipeline was missing: it turns a rights-cleared
reference into constraints an original episode must satisfy, and then refuses to
call a cut a replication unless it still honours them. It writes no copy, renders
nothing and approves nothing — the human review in ``copy_review`` stays the only
gate that unlocks production.

Usage:
    python scripts/replicate_reference.py projects/x-superplay-1024
    python scripts/replicate_reference.py projects/x-superplay-1024 --observe
    python scripts/replicate_reference.py projects/x-superplay-1024 --frames
    python scripts/replicate_reference.py projects/x-superplay-1024 --plan
    python scripts/replicate_reference.py projects/x-superplay-1024 --plan --target-seconds 48
    python scripts/replicate_reference.py projects/x-superplay-1024 --check

Exit codes: 0 pass, 1 the cut fails the contract, 4 nothing has been observed or
planned yet, 2 the inputs contradict each other.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import replication  # noqa: E402

RECEIPT = Path("receipts") / "replication.json"
#: Frames get their own receipt. They used to overwrite the derivation receipt,
#: which destroyed the plan and reference digests a later check needs to inherit.
FRAMES_RECEIPT = Path("receipts") / "replication-frames.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _route(dna: dict) -> dict:
    """The skill that owns the script structure, as the account DNA declares it.

    A receipt without a skill route is incomplete, so a missing route is an
    error rather than an empty field.
    """
    for entry in dna.get("skill_route") or []:
        if entry.get("step") == "script":
            return {"name": entry.get("skill"), "script": entry.get("script"),
                    "why": entry.get("why")}
    raise replication.ReplicationError(
        "the account DNA declares no 'script' skill_route entry, so this run "
        "cannot record which skill owns the copy")


def _receipt(project: Path, payload: dict, path: Path = RECEIPT) -> Path:
    path = project / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _account(project: Path) -> str:
    """The account this episode belongs to, and the one the reference was observed for.

    These are two independent declarations — ``project.yaml`` says who the
    episode is, the observation says who the reference was studied for — and a
    plan derived from one account's template must not be graded against another.
    """
    document = replication.load_observation(project) or {}
    slug = str(document.get("account_slug") or "")
    if not slug:
        raise replication.ReplicationError(
            f"{replication.OBSERVATION.as_posix()} must name account_slug")
    declared = replication.declared_account(project)
    if declared and declared != slug:
        raise replication.ReplicationError(
            f"the observation was written for {slug!r} but project.yaml declares "
            f"{declared!r}; a plan for one account cannot certify the other")
    return slug


def _frames(project: Path, args) -> int:
    """Cut the frames the observation claims were looked at, then prove they came out.

    Cutting and re-verifying are deliberately two passes. The first says "these
    timestamps produced these pixels"; the second re-cuts the same film at the
    same timestamps and compares the bytes. A shot list somebody typed produces
    no matching pixels and is refused here, before a plan can be derived from it.
    """
    errors = replication.extract_frames(project)
    if not errors:
        errors = replication.validate_observation(project)
    if not errors:
        errors = replication.probe_reference(project)
    document = replication.load_observation(project) or {}
    framed = [shot for shot in (document.get("shots") or [])
              if isinstance(shot, dict) and shot.get("frame_sha256")]
    payload = {
        "schema": "contentops.reference-observation-frames/v1",
        "stage": "frames",
        "project": project.name,
        "ok": not errors,
        "frames": len(framed),
        "directory": replication.FRAMES.as_posix(),
        "errors": errors,
    }
    _receipt(project, payload, FRAMES_RECEIPT)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if errors:
        print(f"\nBLOCKED: {len(errors)} problem(s) cutting frames from the reference.",
              file=sys.stderr)
        return 4
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--observe", action="store_true",
                        help="validate reference/observation.json and stop")
    action.add_argument("--frames", action="store_true",
                        help="cut the observed frames out of the reference film, then re-verify them")
    action.add_argument("--plan", action="store_true",
                        help="derive script/replication-plan.json from the observation")
    action.add_argument("--check", action="store_true",
                        help="verify the finished film and its storyboard against the plan")
    parser.add_argument("--target-seconds", type=float, default=None,
                        help="override the derived pacing budget")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    if args.frames:
        return _frames(project, args)

    if args.observe or not (args.plan or args.check):
        errors = replication.validate_observation(project)
        errors += replication.probe_reference(project)
        payload = {
            "schema": "contentops.reference-observation-check/v1",
            "project": project.name,
            "ok": not errors,
            "observation": replication.OBSERVATION.as_posix(),
            "errors": errors,
            "plan_present": (project / replication.PLAN).is_file(),
        }
        document = replication.load_observation(project)
        if not errors and document:
            payload["grammar"] = replication.shot_grammar(document)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if errors:
            print(f"\nBLOCKED: {len(errors)} problem(s) with the reference record. "
                  "Nothing here may be called an observation until they are fixed.",
                  file=sys.stderr)
            return 4
        return 0

    try:
        slug = _account(project)
        dna = replication.load_dna(slug)
        route = _route(dna)
    except replication.ReplicationError as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, ensure_ascii=False))
        return 2

    if args.plan:
        probe_errors = replication.probe_reference(project)
        if probe_errors:
            print(json.dumps({"status": "BLOCKED", "reason": "; ".join(probe_errors)},
                             ensure_ascii=False))
            return 4
        try:
            plan = replication.derive_plan(project, dna, target_s=args.target_seconds)
        except replication.ReplicationError as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
            return 4
        path = replication.write_plan(project, plan)
        receipt = {
            "schema": "contentops.replication-receipt/v1",
            "stage": "plan",
            "project": project.name,
            "account_slug": slug,
            "derived_at": _now(),
            "plan": path.relative_to(project).as_posix(),
            "plan_sha256": replication._sha256(path.read_bytes()),
            "reference_video_sha256": plan["reference"]["video_sha256"],
            "beats": len(plan["beats"]),
            "target_s": plan["pacing"]["target_s"],
            "reuse_reference_media": False,
            "skill_route": route,
            "status": "DERIVED",
            "note": "A derived budget is not an approval. The copy is still written "
                    "and reviewed through copy_review before anything renders.",
        }
        _receipt(project, receipt)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    result = replication.check(project, dna)
    result["checked_at"] = _now()
    rows = {row["id"]: row for row in result["checks"]}
    # A check receipt must not erase the derivation receipt it succeeds: the plan
    # digest, reference digest and skill route are the evidence that a plan came
    # from a verified observation. But it may not *copy* them either. The plan
    # this check graded is the file on disk, so its digest is read from that file
    # now: inheriting the previous receipt's digest would let a PASS name a plan
    # that no longer exists (re-derived at another target, or restored from
    # another branch). Only ``derived_at`` — a fact of the past that cannot be
    # recomputed — is carried over.
    receipt: dict = {}
    previous = project / RECEIPT
    if previous.is_file():
        try:
            prior = json.loads(previous.read_text(encoding="utf-8"))
        except ValueError:
            prior = {}
        if isinstance(prior, dict) and prior.get("derived_at"):
            receipt["derived_at"] = prior["derived_at"]
    plan_path = project / replication.PLAN
    if plan_path.is_file():
        plan_document = replication.load_plan(project) or {}
        reference = plan_document.get("reference") or {}
        receipt.update({
            "plan": replication.PLAN.as_posix(),
            "plan_sha256": replication._sha256(plan_path.read_bytes()),
            "target_s": (plan_document.get("pacing") or {}).get("target_s"),
            "beats": len(plan_document.get("beats") or []),
            "reference_video_sha256": reference.get("video_sha256"),
            "reuse_reference_media": plan_document.get("reuse_reference_media"),
        })
    receipt.update({
        "schema": "contentops.replication-receipt/v1",
        "project": project.name,
        "account_slug": slug,
        "skill_route": route,
        "checked_at": _now(),
        "status": result["overall"],
        "render": replication.RENDER.as_posix(),
        "render_present": bool(rows.get("render_present", {}).get("ok")),
        "checks": [row["id"] for row in result["checks"] if not row["ok"]],
    })
    receipt["stage"] = "check"
    _receipt(project, receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
