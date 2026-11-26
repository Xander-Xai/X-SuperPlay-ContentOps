#!/usr/bin/env python3
"""Read-only preflight for a GRAPHIC_TEXT project before packaging.

Why this exists
---------------
The graphic package gate fails late and one error at a time. A draft reaches
``graphic_package.py`` and is refused for a copy review that was never written,
an ``image_method`` that disagrees with the assets, a corrupted generation
receipt, or a rights record whose dates drifted from its input. Each failure is
legitimate — the gate is right to refuse — but discovering them one by one at
package time wastes a full review/retry cycle per mistake.

This command runs the *same* validators the package gate uses and reports every
problem at once, before anyone writes an approval. It edits nothing. In
particular it does NOT write a copy review: a human still records that decision
through ``scripts/copy_review.py`` after reading the draft.

What it checks (all read-only)
------------------------------
1. ``graphic-input.json`` parses and selects an existing UTF-8 draft.
2. copy review status: ``NOT_REVIEWED``/``STALE``/``CHANGES_REQUESTED`` is
   reported as a required human step, with the exact remedy command. Writing
   the review later changes no fingerprint this command depends on, because
   the GRAPHIC_TEXT copy fingerprint binds only draft bytes + editorial
   identity — never image_method, rights or generation metadata.
3. ``image_method`` is canonical and consistent with the images actually
   declared: a method in IMAGE_METHODS requires every synthetic image to carry
   a generation block; a non-generated (e.g. CC-BY screenshot) image under a
   generation method is called out as the conflict it is.
4. every generation receipt parses, is 64-hex clean, and matches its asset.
5. every rights block passes ``validate_request_rights`` with the same
   ``allow_remote_generated`` the package gate would use, so date/method drift
   between ``graphic-input.json`` and the evidence file is caught here.
6. platform / host blockers inherited from the handoff are reported as
   *delivery-time* facts, not content-quality failures: they do not block
   packaging and this command says so explicitly, so nobody "fixes" them by
   deleting an honest blocker.

Exit codes: 0 no problems (review may still be pending), 1 one or more
blocking problems, 2 misuse/unreadable project.

Usage
-----
    python scripts/check_graphic_input.py projects/my-article
    python scripts/check_graphic_input.py projects/my-article --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic.image_methods import IMAGE_METHODS, RETIRED_IMAGE_METHODS  # noqa: E402
from contentops.graphic.image_generation import validate_prompt, prompt_sha256  # noqa: E402
from contentops.media.rights_gate import RightsError, validate_request_rights  # noqa: E402
from contentops.workflow import copy_review  # noqa: E402

HEX64 = re.compile(r"[0-9a-f]{64}")


def _archived_prompt_hashes(project: Path) -> set[str]:
    """Hashes of prompt files kept in the project (the "prompt is traceable" basis).

    A generated image whose prompt exists only as a hash in the receipt cannot be
    reviewed or reproduced. Keeping the prompt text under ``**/prompts/`` and
    matching its hash back to the receipt is what makes "the prompt was derived
    from this article" auditable instead of an unverifiable claim.
    """
    found: set[str] = set()
    for path in project.rglob("*.md"):
        if "prompts" not in path.parts:
            continue
        try:
            found.add(prompt_sha256(validate_prompt(path.read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001 - an unreadable/invalid prompt file simply is not a match
            continue
    return found


def _load(path: Path, label: str, problems: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.append({"level": "block", "code": "FILE_MISSING", "where": label,
                         "detail": f"{path.name} does not exist"})
        return None
    except (OSError, ValueError) as exc:
        problems.append({"level": "block", "code": "FILE_UNREADABLE", "where": label,
                         "detail": f"{path.name}: {exc}"})
        return None
    if not isinstance(data, dict):
        problems.append({"level": "block", "code": "FILE_NOT_OBJECT", "where": label,
                         "detail": f"{path.name} must be a JSON object"})
        return None
    return data


def check(project: Path) -> Dict[str, Any]:
    project = project.resolve()
    problems: List[Dict[str, str]] = []
    info: Dict[str, Any] = {"project": str(project)}

    inp = _load(project / "graphic-input.json", "graphic-input.json", problems)
    if inp is None:
        return {"schema": "contentops.graphic-input-preflight/v1", "ok": False,
                "project": str(project), "problems": problems, "info": info}

    # 1. method declaration
    method = str(inp.get("image_method") or "").strip() or "legacy/unspecified"
    info["image_method"] = method
    if method in RETIRED_IMAGE_METHODS:
        problems.append({"level": "block", "code": "IMAGE_METHOD_RETIRED", "where": "image_method",
                         "detail": f"{method} is retired; choose one of {list(IMAGE_METHODS)}"})
    elif method not in (*IMAGE_METHODS, "legacy/unspecified"):
        problems.append({"level": "block", "code": "IMAGE_METHOD_UNKNOWN", "where": "image_method",
                         "detail": f"{method} is not a known method"})
    generation_method = method in IMAGE_METHODS

    # 2. draft selection
    draft_ref = str(inp.get("draft") or "").strip()
    draft_path = project / draft_ref if draft_ref and not draft_ref.startswith("repo://") else None
    if not draft_ref:
        problems.append({"level": "block", "code": "DRAFT_REQUIRED", "where": "draft",
                         "detail": "graphic-input.json must select a draft"})
    elif draft_path is not None:
        if not draft_path.is_file():
            problems.append({"level": "block", "code": "DRAFT_MISSING", "where": "draft",
                             "detail": f"{draft_ref} does not exist"})
        else:
            try:
                text = draft_path.read_text(encoding="utf-8")
                info["draft_bytes"] = len(text.encode("utf-8"))
                if not text.strip():
                    problems.append({"level": "block", "code": "DRAFT_EMPTY", "where": "draft",
                                     "detail": f"{draft_ref} is empty"})
            except UnicodeDecodeError:
                problems.append({"level": "block", "code": "DRAFT_NOT_UTF8", "where": "draft",
                                 "detail": f"{draft_ref} is not UTF-8"})

    # 3. copy review (reuses the real fingerprint; never writes it)
    try:
        gate = copy_review.status(project, projects_root=project.parent,
                                  graphic_input_path=project / "graphic-input.json")
        info["copy_review_state"] = gate.get("state")
        if not gate.get("ok"):
            level = "human" if gate.get("state") in ("NOT_REVIEWED", "CHANGES_REQUESTED") else "block"
            problems.append({
                "level": level,
                "code": f"COPY_REVIEW_{gate.get('state')}",
                "where": "receipts/script-review.json",
                "detail": gate.get("detail", ""),
                "remedy": gate.get("remedy", ""),
            })
    except (ValueError, OSError) as exc:
        problems.append({"level": "block", "code": "COPY_REVIEW_CHECK_FAILED",
                         "where": "graphic-input.json", "detail": str(exc)})

    # 4. images: rights + generation method consistency + receipts
    archived_prompts = _archived_prompt_hashes(project)
    info["archived_prompt_count"] = len(archived_prompts)
    images = inp.get("images")
    if not isinstance(images, list) or not images:
        problems.append({"level": "block", "code": "IMAGES_REQUIRED", "where": "images",
                         "detail": "a graphic package needs at least one image"})
    else:
        seen: set[str] = set()
        for index, image in enumerate(images):
            label = f"images[{index}]"
            if not isinstance(image, dict):
                problems.append({"level": "block", "code": "IMAGE_INVALID", "where": label,
                                 "detail": "image must be an object"})
                continue
            asset_id = str(image.get("asset_id") or "").strip()
            where = asset_id or label
            if not asset_id or asset_id in seen:
                problems.append({"level": "block", "code": "IMAGE_ID_INVALID", "where": label,
                                 "detail": "images need a unique non-empty asset_id"})
            seen.add(asset_id)

            rights = image.get("rights")
            if not isinstance(rights, dict) or not rights:
                problems.append({"level": "block", "code": "IMAGE_RIGHTS_MISSING", "where": where,
                                 "detail": "image needs a reviewed rights block"})
            else:
                try:
                    validate_request_rights(
                        {"rights": rights}, project, allow_remote_generated=generation_method)
                except RightsError as exc:
                    problems.append({"level": "block", "code": "IMAGE_RIGHTS_INVALID",
                                     "where": where, "detail": str(exc)})

            generation = image.get("generation")
            is_synthetic = bool((rights or {}).get("synthetic"))
            if generation_method:
                if not isinstance(generation, dict) or not generation.get("receipt"):
                    problems.append({
                        "level": "block", "code": "GENERATION_RECEIPT_REQUIRED", "where": where,
                        "detail": ("image_method requires a generation receipt for every image; "
                                   "a non-generated asset (e.g. a CC-BY screenshot) cannot be "
                                   "packaged under a generation method — remove it or switch method"),
                    })
                else:
                    receipt_rel = str(generation.get("receipt"))
                    receipt = _load(project / receipt_rel, receipt_rel, problems)
                    if receipt is not None:
                        prompt = str(receipt.get("prompt_sha256") or "")
                        if not HEX64.fullmatch(prompt):
                            problems.append({
                                "level": "block", "code": "PROMPT_DIGEST_INVALID", "where": where,
                                "detail": (f"prompt_sha256 must be 64 lowercase hex; got "
                                           f"{len(prompt)} chars — a copied receipt may be corrupted"),
                            })
                        elif prompt not in archived_prompts:
                            # The receipt's prompt hash must match a prompt file kept in the
                            # project. Without this, an image could be generated from an
                            # arbitrary prompt unrelated to the article and still package.
                            problems.append({
                                "level": "block", "code": "PROMPT_NOT_ARCHIVED", "where": where,
                                "detail": (f"no prompt file under a prompts/ folder hashes to "
                                           f"{prompt[:12]}… — keep the exact prompt that generated "
                                           f"this image in the project so it can be reviewed against "
                                           f"the article theme"),
                            })
            elif is_synthetic and generation:
                problems.append({
                    "level": "warn", "code": "SYNTHETIC_UNDER_LEGACY", "where": where,
                    "detail": ("a synthetic image with a generation receipt under legacy/unspecified "
                               "will be refused at package time; switch image_method to its "
                               "generation method or remove the image"),
                })

    # 5. handoff blockers: report as delivery-time facts, never as content failures
    handoff_path = project / "receipts" / "bundle-handoff-graphic_text.json"
    # A missing handoff is normal early in authoring; it is informational, never
    # a blocker. Read it without feeding errors into the shared problems list.
    handoff = None
    if handoff_path.is_file():
        handoff = _load(handoff_path, handoff_path.name, problems)
    else:
        problems.append({
            "level": "info", "code": "HANDOFF_ABSENT", "where": "handoff",
            "detail": ("no bundle handoff yet; one is needed before packaging. "
                       "Create it with scripts/bundle_handoff.py when the Bundle is ready."),
        })
    info["blockers"] = []
    if handoff is not None:
        blockers = handoff.get("blockers") or []
        info["blockers"] = list(blockers)
        info["handoff_state"] = handoff.get("state")
        if blockers:
            problems.append({
                "level": "info", "code": "DELIVERY_BLOCKERS_PRESENT", "where": "handoff",
                "detail": ("platform/host blockers are delivery-time facts, not content-quality "
                           "failures. The package may be built and reviewed; creating a platform "
                           "draft still requires resolving these (bind account, verify host "
                           "capability) plus the operator's explicit authorization. Do NOT delete "
                           "these blockers to make checks green."),
            })

    blocking = [p for p in problems if p["level"] == "block"]
    human = [p for p in problems if p["level"] == "human"]
    return {
        "schema": "contentops.graphic-input-preflight/v1",
        "ok": not blocking,
        "project": str(project),
        "counts": {"block": len(blocking), "human": len(human),
                   "warn": sum(p["level"] == "warn" for p in problems),
                   "info": sum(p["level"] == "info" for p in problems)},
        "problems": problems,
        "info": info,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="project directory under projects/<slug>")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    if not project.is_dir():
        print(json.dumps({"schema": "contentops.graphic-input-preflight/v1", "ok": False,
                          "error": "PROJECT_NOT_FOUND", "project": str(project)},
                         ensure_ascii=False, indent=2) if args.json else
              f"PROJECT_NOT_FOUND: {project}", file=sys.stderr)
        return 2

    result = check(project)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        c = result["counts"]
        print(f"project  {result['project']}")
        print(f"method   {result['info'].get('image_method')}")
        print(f"review   {result['info'].get('copy_review_state')}")
        print(f"result   {'OK' if result['ok'] else 'BLOCKED'} "
              f"(block={c['block']} human={c['human']} warn={c['warn']} info={c['info']})")
        for problem in result["problems"]:
            print(f"  [{problem['level']}] {problem['code']} @ {problem['where']}: "
                  f"{problem['detail']}")
            if problem.get("remedy"):
                print(f"          remedy: {problem['remedy']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
