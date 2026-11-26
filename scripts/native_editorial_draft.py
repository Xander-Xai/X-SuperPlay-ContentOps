#!/usr/bin/env python3
"""Create and inspect platform-native editorial drafts without changing approved copy."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from contentops.workflow import shared_copy
from contentops.platforms import graphic_specs

SCHEMA = "contentops.native-editorial-draft/v1"
# Editorial prompts, not platform-policy claims. X and XHS image remain excluded.
PROFILES = {
    "wechat_article": ("Reader problem and takeaway", "Context, evidence, implications", "Useful next step"),
    "zhihu": ("Specific question and direct answer", "Reasoning, evidence and limitations", "Practical conclusion"),
    "csdn": ("Engineering problem and outcome", "Reproduction, mechanism and caveats", "Next technical step"),
    "juejin": ("Developer problem and insight", "Implementation and trade-offs", "Actionable takeaway"),
    "toutiao": ("Concrete reader benefit", "Concise explanation and evidence", "Summary"),
    "weibo": ("One clear original observation", "Essential evidence and caveat", "Relevant closing"),
}


def current(root, project, platform):
    if platform not in PROFILES:
        raise ValueError("unsupported native editorial platform")
    project = Path(project).resolve()
    shared_copy.project_ref(root, project)
    package_path = shared_copy.inside(project, "receipts/graphic-package.json")
    package = shared_copy.document(package_path)
    lineage = shared_copy.verify_package(root, project, package)
    source = shared_copy.inside(root, lineage["source_project"])
    canonical = shared_copy.verify_video(root, source)
    beats = shared_copy.document(shared_copy.inside(source, "script/lines.json"))["beats"]
    if len(beats) != len(canonical["claim_lineage"]):
        raise ValueError("canonical beat count changed")
    rows = []
    for beat, claim in zip(beats, canonical["claim_lineage"]):
        if (beat["claim_id"] != claim["claim_id"] or
                shared_copy.digest(beat["text"].encode("utf-8")) != claim["text_sha256"]):
            raise ValueError("canonical beat changed")
        rows.append({"claim_id": claim["claim_id"], "revision": claim["revision"],
                     "source_text": beat["text"], "source_sha256": claim["text_sha256"],
                     "evidence": claim["evidence"], "draft_text": beat["text"],
                     "review_note": ""})
    spec = graphic_specs.rules(platform)
    return {"schema": SCHEMA, "platform": platform, "profile": list(PROFILES[platform]),
            "limits": {"title_max_hard": spec["title_max_hard"],
                       "body_max_hard": spec["body_max_hard"]},
            "binding": {"shared_copy_id": lineage["shared_copy_id"],
                        "copy_sha256": lineage["copy_sha256"],
                        "package_sha256": shared_copy.digest(package_path.read_bytes())},
            "original_title": canonical["title"], "title": canonical["title"],
            "title_review_note": "", "claims": rows,
            "reviewer": None, "status": "DRAFT_ONLY",
            "production_ready": False, "publish_authorized": False}


def review(root, project, platform, draft):
    expected = current(root, project, platform)
    if not isinstance(draft, dict) or draft.get("schema") != SCHEMA:
        raise ValueError("invalid draft schema")
    for k in ("platform", "profile", "limits", "binding", "original_title"):
        if draft.get(k) != expected[k]:
            raise ValueError("STALE or modified source binding: " + k)
    if draft.get("production_ready") is not False or draft.get("publish_authorized") is not False:
        raise ValueError("draft cannot authorize production or publication")
    if draft.get("status") != "DRAFT_ONLY":
        raise ValueError("review only an unapproved draft")
    reviewer = draft.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
        raise ValueError("named human reviewer required")
    def text(value, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError("missing or oversized editorial text/note")
        return value.strip()
    title = text(draft.get("title"), 1000)
    text(draft.get("title_review_note"), 1000)
    source = {r["claim_id"]: r for r in expected["claims"]}
    claims = draft.get("claims")
    if not isinstance(claims, list) or len(claims) != len(source):
        raise ValueError("retain every canonical claim exactly once in this pilot")
    seen, body = set(), []
    for row in claims:
        if not isinstance(row, dict):
            raise ValueError("invalid claim row")
        ident = row.get("claim_id")
        if not isinstance(ident, str) or ident not in source or ident in seen:
            raise ValueError("unknown or duplicate claim")
        seen.add(ident)
        for k in ("revision", "source_text", "source_sha256", "evidence"):
            if row.get(k) != source[ident][k]:
                raise ValueError("claim lineage modified: " + ident)
        body.append(text(row.get("draft_text"), 20000))
        text(row.get("review_note"), 1000)
    # Use existing platform rules; refuse a hard-limit rewrite rather than condense.
    shaped = graphic_specs.shape(platform, title, "\n\n".join(body))
    if shaped["blockers"]:
        raise ValueError("platform draft blocked: " + "; ".join(shaped["blockers"]))
    return {"schema": SCHEMA, "platform": platform, "binding": expected["binding"],
            "status": "REVIEWED_DRAFT_ONLY", "review_origin": "LOCAL_SELF_ATTESTED",
            "reviewer": reviewer, "draft_sha256": shared_copy.digest(shared_copy.encode(draft)),
            "native_preview": shaped, "claim_ids": [r["claim_id"] for r in claims],
            "limitation": "Human notes are not automated semantic entailment or copy approval. "
                          "Do not send this preview to the production/publish path.",
            "production_ready": False, "publish_authorized": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("plan", "review"))
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--platform", required=True, choices=sorted(PROFILES))
    p.add_argument("--draft", type=Path)
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    try:
        if a.command == "plan":
            if a.draft or a.confirm:
                raise ValueError("plan does not accept review arguments")
            result = current(ROOT, a.project, a.platform)
        else:
            if not a.confirm or a.draft is None:
                raise ValueError("human confirmation and local draft JSON required")
            import editorial_ops as ops
            if a.draft.is_symlink():
                raise ValueError("symlink draft refused")
            ops.local_dir(a.draft.resolve().parent)
            result = review(ROOT, a.project, a.platform, shared_copy.document(a.draft))
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        p.exit(4, "BLOCKED: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
