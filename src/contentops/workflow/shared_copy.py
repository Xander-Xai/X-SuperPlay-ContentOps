"""One reviewed source for the VIDEO and GRAPHIC_TEXT lines.

Only the existing routed, approved brief + signed research + copy-review gate
may supply copy. First release permits verbatim claim projection, not free
rewriting. A shared receipt never approves production or publication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contentops.content_kernel.handoff import (
    HANDOFF_SCHEMA, VIDEO, GRAPHIC_TEXT, verify_bundle_unchanged, handoff_filename,
)
from contentops.evidence.claim_map import ClaimMap
from contentops.evidence.source_artifact import EVIDENCE_CAPABLE_PERMISSIONS
from contentops.routing import handoff as brief_handoff
from contentops.script import draft as script_draft
from contentops.script import m5_bridge
from contentops.workflow import copy_review, preresearch

SCHEMA = "contentops.shared-copy/v1"
VIDEO_RECORD = Path("receipts/shared-copy-video.json")
GRAPHIC_RECORD = Path("receipts/shared-copy-graphic.json")
GRAPHIC_DRAFT = Path("shared-copy.md")
MAX_BYTES = 2_000_000


class SharedCopyError(ValueError):
    pass


def repository_root():
    return Path(__file__).resolve().parents[3]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def inside(base, relative):
    base = Path(base).resolve()
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise SharedCopyError("unsafe relative path")
    path = (base / value).resolve()
    if base not in path.parents:
        raise SharedCopyError("path escapes scope")
    return path


def project_ref(root, project):
    root, project = Path(root).resolve(), Path(project).resolve()
    try:
        relative = project.relative_to(root)
    except ValueError:
        raise SharedCopyError("shared-copy projects must be within the repository projects/ tree") from None
    if len(relative.parts) < 2 or relative.parts[0] != "projects" or not project.is_dir():
        raise SharedCopyError("shared-copy projects must be within the repository projects/ tree")
    return relative.as_posix()


def read(path):
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise SharedCopyError("missing or oversized artifact: " + path.name)
    return path.read_bytes()


def document(path):
    raw = json.loads(read(path).decode("utf-8"))
    if not isinstance(raw, dict):
        raise SharedCopyError("expected JSON object: " + path.name)
    return raw


def handoff_for(root, project, fmt):
    value = document(inside(project, Path("receipts") / handoff_filename(fmt)))
    if (value.get("schema") != HANDOFF_SCHEMA or value.get("content_format") != fmt
            or value.get("project_slug") != project.name or value.get("publish_authorized") is not False
            or value.get("production_ready") is not False):
        raise SharedCopyError("invalid or unauthorized bundle handoff")
    bundle = verify_bundle_unchanged(value, repo_root=root, project_dir=project)
    if value.get("bundle_id") != bundle.get("bundle_id") or value.get("source_id") != (bundle.get("source") or {}).get("source_id"):
        raise SharedCopyError("handoff identity differs from actual Bundle")
    treatment = (bundle.get("account_treatments") or {}).get(value.get("account"))
    if not isinstance(treatment, dict) or any(value.get(key) != treatment.get(key) for key in ("role", "production_lane")):
        raise SharedCopyError("handoff treatment differs from actual Bundle")
    return value, bundle


def binding(value):
    return {key: value.get(key) for key in (
        "bundle_id", "bundle_sha256", "source_id", "source_map", "account", "role",
        "production_lane", "execution_profile_hint",
    )}


def snapshot(root, source):
    root, source = Path(root).resolve(), Path(source).resolve()
    ref = project_ref(root, source)
    try:
        brief = brief_handoff.read_brief(source)
        gate = brief_handoff.check(brief)
        if not gate["ok"]:
            raise SharedCopyError("brief approval not current: " + gate["reason"])
        research = preresearch.require(source)
        if research.get("intent_bound_to_brief") is not True:
            raise SharedCopyError("signed research must bind the exact routed intent")
        approval = copy_review.require_approved(source)
        if not approval.get("reviewer") or not approval.get("opinion"):
            raise SharedCopyError("copy review needs named human and opinion")
        validated = script_draft.check(source)
        if not validated["ok"]:
            raise SharedCopyError("canonical script claim validation failed")
        video, bundle = handoff_for(root, source, VIDEO)
        intent = brief.get("intent") or {}
        title = str(intent.get("topic") or "").strip()
        account = str(intent.get("account_id") or "").strip()
        if not title or not account or title != str((bundle.get("source") or {}).get("topic_thesis") or "").strip():
            raise SharedCopyError("Bundle thesis must match the approved topic in this first-release exact-copy path")
        if intent.get("target_pipeline") != VIDEO:
            raise SharedCopyError("canonical source must be a routed VIDEO project")
        claims = ClaimMap.from_dict(document(inside(source, "script/claim-map.json"))).require_publishable()
        lines = document(inside(source, "script/lines.json")).get("beats")
        if not isinstance(lines, list) or not lines:
            raise SharedCopyError("canonical beats missing")
        permissions = m5_bridge._permissions(source)
        by_id = {c.claim_id: c for c in claims.claims}
        texts, lineage, seen = [], [], set()
        for beat in lines:
            claim = by_id.get(beat.get("claim_id")) if isinstance(beat, dict) else None
            if (claim is None or claim.claim_id in seen or beat.get("text") != claim.text
                    or claim.permission_scope != "publishable" or claim.support_status != "SUPPORTED"):
                raise SharedCopyError("unbound, repeated, unsupported or non-publishable claim")
            seen.add(claim.claim_id)
            refs = []
            for item in claim.evidence:
                eid = item["evidence_id"]
                record = permissions.get(eid)
                if (not isinstance(record, dict) or record.get("permission") not in EVIDENCE_CAPABLE_PERMISSIONS
                        or item.get("permission_scope") != "publishable"):
                    raise SharedCopyError("source permission not current: " + eid)
                logical = item["logical_path"]
                base, rel = (source, logical[len("project://"):]) if logical.startswith("project://") else (root, logical[len("repo://"):])
                actual = inside(base, rel)
                if digest(read(actual)) != item["sha256"]:
                    raise SharedCopyError("source evidence drift: " + eid)
                if claim.kind == "source" and item["kind"] == "document":
                    if not m5_bridge.quote_occurs(claim.text, actual.read_text(encoding="utf-8"), actual.name):
                        raise SharedCopyError("source quote not found: " + eid)
                refs.append({"evidence_id": eid, "sha256": item["sha256"]})
            if claim.kind not in ("editorial_transition", "cta") and not refs:
                raise SharedCopyError("factual claim has no evidence")
            texts.append(claim.text)
            lineage.append({"claim_id": claim.claim_id, "revision": claim.revision,
                            "text_sha256": digest(claim.text.encode("utf-8")), "evidence": refs})
        if not any(row["evidence"] for row in lineage):
            raise SharedCopyError("no factual evidence in shared copy")
        body = ("\n\n".join(texts) + "\n").encode("utf-8")
        record = {"schema": SCHEMA, "source_project": ref, "account_id": account,
                  "brief_id": brief.get("brief_id"), "brief_sha256": gate["content_digest"],
                  "research_sha256": research["artifacts_sha256"], "copy_sha256": approval["copy_sha256"],
                  "permissions_sha256": digest(read(inside(source, m5_bridge.PERMISSIONS_FILE))),
                  "bundle_binding": binding(video), "title": title, "claim_lineage": lineage,
                  "draft_sha256": digest(body), "production_ready": False, "publish_authorized": False}
        record["shared_copy_id"] = "SC-" + digest(encode(record))[:24]
        return record, body
    except SharedCopyError:
        raise
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, m5_bridge.BridgeBlocked,
            copy_review.CopyReviewRequired, preresearch.PreresearchError) as exc:
        raise SharedCopyError("shared copy blocked: " + str(exc)) from None


def write_once(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise SharedCopyError("existing shared artifact differs; archive and rebind after review")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(payload)


def json_bytes(record):
    return (json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def prepare(root, source, graphic):
    root, source, graphic = map(lambda p: Path(p).resolve(), (root, source, graphic))
    target_ref = project_ref(root, graphic)
    if source == graphic:
        raise SharedCopyError("video and graphic projects must remain independent")
    record, body = snapshot(root, source)
    target, _ = handoff_for(root, graphic, GRAPHIC_TEXT)
    if binding(target) != record["bundle_binding"]:
        raise SharedCopyError("the two handoffs must use one Bundle, source map and account treatment")
    if (target.get("platform") or {}).get("platform_id") not in {"wechat_article", "zhihu", "csdn"}:
        raise SharedCopyError("shared graphic package requires an existing non-X editorial registry row")
    derived = {"schema": SCHEMA, "shared_copy_id": record["shared_copy_id"],
               "source_project": record["source_project"], "graphic_project": target_ref,
               "source_record_sha256": digest(json_bytes(record)), "draft_sha256": digest(body),
               "production_ready": False, "publish_authorized": False}
    outputs = [(inside(source, VIDEO_RECORD), json_bytes(record)),
               (inside(graphic, GRAPHIC_RECORD), json_bytes(derived)),
               (inside(graphic, GRAPHIC_DRAFT), body)]
    # Detect all existing conflicts before creating any new output.
    for path, payload in outputs:
        if path.exists() and path.read_bytes() != payload:
            raise SharedCopyError("existing shared artifact differs; archive and rebind after review")
    for path, payload in outputs:
        write_once(path, payload)
    return record


def verify_video(root, source):
    record, _ = snapshot(root, source)
    stored = document(inside(source, VIDEO_RECORD))
    if stored != record:
        raise SharedCopyError("shared copy review is stale; rebind after current review")
    return record


def verify_graphic(root, graphic, *, handoff, title, draft):
    root, graphic = Path(root).resolve(), Path(graphic).resolve()
    target_ref = project_ref(root, graphic)
    stored = document(inside(graphic, GRAPHIC_RECORD))
    if stored.get("schema") != SCHEMA or stored.get("graphic_project") != target_ref:
        raise SharedCopyError("invalid graphic shared-copy binding")
    source = inside(root, stored["source_project"])
    record = verify_video(root, source)
    target, _ = handoff_for(root, graphic, GRAPHIC_TEXT)
    if handoff != target or binding(target) != record["bundle_binding"]:
        raise SharedCopyError("graphic handoff differs from current shared Bundle")
    expected = {"schema": SCHEMA, "shared_copy_id": record["shared_copy_id"],
                "source_project": record["source_project"], "graphic_project": target_ref,
                "source_record_sha256": digest(json_bytes(record)), "draft_sha256": record["draft_sha256"],
                "production_ready": False, "publish_authorized": False}
    if (stored != expected or title != record["title"]
            or Path(draft).resolve() != inside(graphic, GRAPHIC_DRAFT)
            or digest(read(Path(draft))) != record["draft_sha256"]):
        raise SharedCopyError("graphic copy, title or lineage changed after shared review")
    return {"shared_copy_id": record["shared_copy_id"], "copy_sha256": record["copy_sha256"],
            "source_project": record["source_project"], "claim_lineage": record["claim_lineage"],
            "draft_sha256": record["draft_sha256"]}


def verify_package(root, graphic, package):
    graphic = Path(graphic).resolve()
    current, _ = handoff_for(root, graphic, GRAPHIC_TEXT)
    draft = package.get("draft") or {}
    lineage = verify_graphic(root, graphic, handoff=current, title=package.get("title"),
                             draft=inside(graphic, draft.get("path") or ""))
    if (package.get("shared_copy") != lineage or package.get("bundle_sha256") != current.get("bundle_sha256")
            or package.get("account") != current.get("account") or draft.get("sha256") != lineage["draft_sha256"]):
        raise SharedCopyError("graphic package lineage is stale or missing")
    return lineage
