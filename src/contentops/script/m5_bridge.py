"""Turn a source-bound draft into the contract the M5 chain reads.

Why this exists
---------------
The router ends at ``script/lines.json`` and ``script/claim-map.json``; the M5
production entry reads ``script/script.json`` and ``script/claims.json``. The
two were written months apart and never met, so a router episode could be
approved, drafted and reviewed and still have no way into the renderer.

This module is that adapter and nothing more. It converts, it does not invent:

- every line keeps the narration the draft wrote;
- a factual claim keeps its evidence, and its quote is checked against the
  saved document before the M5 chain is allowed to see it;
- a line with no evidence is not given a claim id, so the M5 channel cannot
  treat an editorial transition as a fact;
- every line must name a registered visual asset, because M5 composes from the
  asset inventory and a missing picture is a blocker, not a blank frame.

What must still be resolved
----------------------------
``script/asset-map.json`` maps each placement to a registered asset id, and
``00_brief/source-permissions.json`` states the permission for each evidence
item. The bridge refuses with the exact missing entries rather than guessing a
licence or a picture. That is the same rule the rest of the repository follows:
a named gap is honest; a default is a fabrication. An explicit unapproved
preview conversion does not set copy or publication approval.

Copy review is not enforced here because the review has to cover the copy this
bridge produces. REVIEW and STRICT enforce it at production; AUTO can render a
local draft preview while review remains pending. Publication review remains
separate, and conversion never approves the copy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..routing import handoff
from ..evidence.source_artifact import EVIDENCE_CAPABLE_PERMISSIONS
from ..evidence.text_matching import quote_occurs
from ..media.local_assets import is_valid_local_preview_asset

SCHEMA = "contentops.brief-m5-bridge/v1"
REFS_SCHEMA = "contentops.m5-source-refs/v1"
M5_SCRIPT_SCHEMA = "contentops.m5-script/v1"
LEDGER_SCHEMA = "contentops.claim-ledger/v1"

ASSET_MAP_FILE = Path("script") / "asset-map.json"
PERMISSIONS_FILE = Path("00_brief") / "source-permissions.json"
REFS_FILE = Path("sources") / "source-refs.json"
LINES_FILE = Path("script") / "lines.json"
CLAIM_MAP_FILE = Path("script") / "claim-map.json"
RECEIPT_FILE = Path("receipts") / "brief-to-m5.json"
PERMISSIONS_SCHEMA = "contentops.source-permissions/v1"
ASSET_MAP_SCHEMA = "contentops.asset-map/v1"

#: The claim kinds that assert something about the world. A transition or a
#: CTA is deliberately absent: it may appear in narration, never as a fact.
FACTUAL_KINDS = ("runtime", "source", "historical", "judgement")

#: A claim-map evidence path is project-relative inside a project directory.
PROJECT_PREFIX = "project://"


class BridgeBlocked(Exception):
    """The draft cannot become M5 input, and this is the named reason."""

    def __init__(self, code: str, detail: str, blockers: Optional[List[str]] = None) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.blockers = list(blockers or [])


def _read_json(path: Path, code: str) -> Dict[str, Any]:
    if not path.is_file():
        raise BridgeBlocked(code, f"{path.as_posix()} is missing")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeBlocked(code, f"{path.as_posix()} is unreadable: {exc}") from None
    if not isinstance(document, dict):
        raise BridgeBlocked(code, f"{path.as_posix()} is not a JSON object")
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_root(module_file: Optional[Path] = None) -> Path:
    return (Path(module_file) if module_file else Path(__file__)).resolve().parents[3]


def _project_relative(project: Path, repo_root: Path) -> str:
    try:
        return project.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        raise BridgeBlocked(
            "PROJECT_OUTSIDE_REPO",
            f"{project.as_posix()} is outside the repository; M5 assets and source "
            f"refs are repository-relative") from None


def _logical_to_repo(logical: str, project_rel: str) -> str:
    if logical.startswith(PROJECT_PREFIX):
        return f"{project_rel}/{logical[len(PROJECT_PREFIX):].lstrip('/')}"
    if logical.startswith("repo://"):
        return logical[len("repo://"):].lstrip("/")
    raise BridgeBlocked(
        "NON_LOGICAL_PATH",
        f"evidence path {logical!r} must be project:// or repo://")


def _permissions(project: Path) -> Dict[str, Dict[str, Any]]:
    document = _read_json(project / PERMISSIONS_FILE, "SOURCE_PERMISSIONS_MISSING")
    if document.get("schema") != PERMISSIONS_SCHEMA:
        raise BridgeBlocked(
            "SOURCE_PERMISSIONS_SCHEMA",
            f"{PERMISSIONS_FILE.as_posix()} must declare schema {PERMISSIONS_SCHEMA!r}")
    permissions = document.get("permissions")
    if not isinstance(permissions, dict):
        raise BridgeBlocked("SOURCE_PERMISSIONS_INVALID",
                            "permissions must be a mapping of evidence_id to a record")
    return permissions


def _assets(project: Path, repo_root: Path) -> Dict[str, Dict[str, Any]]:
    manifest = _read_json(project / "sources" / "assets.json", "ASSETS_MISSING")
    assets: Dict[str, Dict[str, Any]] = {}
    for raw in manifest.get("assets") or []:
        asset_id = str(raw.get("id") or "")
        if not asset_id or asset_id in assets:
            raise BridgeBlocked("ASSET_ID_INVALID",
                                "every asset needs a unique non-empty id")
        assets[asset_id] = raw
    return assets


def _asset_map(project: Path) -> Dict[str, str]:
    document = _read_json(project / ASSET_MAP_FILE, "ASSET_MAP_MISSING")
    if document.get("schema") != ASSET_MAP_SCHEMA:
        raise BridgeBlocked(
            "ASSET_MAP_SCHEMA",
            f"{ASSET_MAP_FILE.as_posix()} must declare schema {ASSET_MAP_SCHEMA!r}")
    mapping = document.get("mapping")
    if not isinstance(mapping, dict):
        raise BridgeBlocked("ASSET_MAP_INVALID",
                            "mapping must be a placement_id to asset_id object")
    return {str(key): str(value) for key, value in mapping.items()}


def build(project: Path, *, repo_root: Optional[Path] = None,
          allow_unapproved_preview: bool = False) -> Dict[str, Any]:
    """Convert the draft; return what was written. Raises BridgeBlocked."""
    project = Path(project)
    root = Path(repo_root) if repo_root else _repo_root()
    project_rel = _project_relative(project, root)

    brief = handoff.read_brief(project)
    verdict = handoff.check(brief,
                            allow_unapproved_preview=allow_unapproved_preview)
    if not verdict["ok"]:
        raise BridgeBlocked(verdict["reason"], verdict["detail"])

    lines_doc = _read_json(project / LINES_FILE, "DRAFT_MISSING")
    claim_doc = _read_json(project / CLAIM_MAP_FILE, "DRAFT_MISSING")
    beats = lines_doc.get("beats")
    claims = claim_doc.get("claims")
    if not isinstance(beats, list) or not beats:
        raise BridgeBlocked("DRAFT_EMPTY", f"{LINES_FILE.as_posix()} has no beats")
    if not isinstance(claims, list) or not claims:
        raise BridgeBlocked("DRAFT_EMPTY", f"{CLAIM_MAP_FILE.as_posix()} has no claims")

    permissions = _permissions(project)
    assets = _assets(project, root)
    mapping = _asset_map(project)

    claim_by_id = {str(claim.get("claim_id")): claim for claim in claims if isinstance(claim, dict)}
    blockers: List[str] = []
    missing_permissions: List[str] = []
    missing_assets: List[str] = []
    unmapped: List[str] = []

    # The ledger only carries claims that assert something and name evidence.
    # A claim-map claim that asserts a fact with no evidence cannot be spoken.
    ledger_claims: List[Dict[str, Any]] = []
    refs: List[Dict[str, Any]] = []
    ref_ids: Dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or "")
        kind = str(claim.get("kind") or "")
        evidence = [item for item in claim.get("evidence") or [] if isinstance(item, dict)]
        if kind not in FACTUAL_KINDS:
            if evidence:
                blockers.append(f"{claim_id}: a {kind!r} claim carries evidence, which "
                                f"the claim contract does not allow")
            continue
        if str(claim.get("support_status")) != "SUPPORTED" or not evidence:
            blockers.append(
                f"{claim_id}: a factual claim is spoken without SUPPORTED evidence; "
                f"narrow the claim or collect the material")
            continue
        artifacts: List[str] = []
        for item in evidence:
            evidence_id = str(item.get("evidence_id") or "")
            logical = str(item.get("logical_path") or "")
            if not evidence_id:
                blockers.append(f"{claim_id}: an evidence item has no evidence_id")
                continue
            permission = permissions.get(evidence_id)
            if not isinstance(permission, dict) or not permission.get("permission"):
                missing_permissions.append(evidence_id)
                continue
            value = str(permission["permission"])
            if value not in EVIDENCE_CAPABLE_PERMISSIONS:
                blockers.append(
                    f"{evidence_id}: permission {value!r} cannot back a claim; use "
                    f"{sorted(EVIDENCE_CAPABLE_PERMISSIONS)}")
                continue
            repo_path = _logical_to_repo(logical, project_rel)
            target = root / repo_path
            if not target.is_file():
                blockers.append(f"{evidence_id}: evidence file missing: {repo_path}")
                continue
            recorded = str(item.get("sha256") or "")
            if recorded and _sha256(target) != recorded:
                blockers.append(f"{evidence_id}: evidence bytes changed since collection")
                continue
            text = None
            try:
                text = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                blockers.append(
                    f"{evidence_id}: {repo_path} is not readable text, so the quote "
                    f"cannot be verified")
            sentence = str(claim.get("text") or "")
            quote_found = quote_occurs(sentence, text or "", repo_path)
            if text is not None and sentence and not quote_found:
                blockers.append(
                    f"{claim_id}: the narration text does not occur verbatim in "
                    f"{repo_path}; a claim without a verifiable quote is an assertion")
            artifact_id = ref_ids.get(repo_path)
            if artifact_id is None:
                artifact_id = evidence_id
                ref_ids[repo_path] = artifact_id
                refs.append({
                    "id": artifact_id,
                    "type": str(item.get("kind") or "document"),
                    "title": str(permission.get("title") or evidence_id),
                    "path": repo_path,
                    "permission": value,
                    "notes": str(permission.get("note") or ""),
                })
            if artifact_id not in artifacts:
                artifacts.append(artifact_id)
        if artifacts:
            ledger_claims.append({
                "id": claim_id,
                "text": str(claim.get("text") or ""),
                "artifacts": artifacts,
                "quotes": [str(claim.get("text") or "")],
            })

    # Every beat must name a visual asset that exists, is registered and
    # verifies against its recorded digest.
    m5_lines: List[Dict[str, Any]] = []
    ledger_ids = {claim["id"] for claim in ledger_claims}
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        placement = str(beat.get("placement_id") or "")
        asset_id = mapping.get(placement, "")
        if not asset_id:
            unmapped.append(placement or "(no placement id)")
            asset_id = ""
        elif asset_id not in assets:
            missing_assets.append(f"{placement}: asset {asset_id!r} is not registered")
            asset_id = ""
        if asset_id:
            asset = assets[asset_id]
            repo_path = str(asset.get("repo_path") or "")
            target = root / repo_path if repo_path else None
            if target is None or not target.is_file():
                missing_assets.append(f"{asset_id}: file missing: {repo_path}")
            elif asset.get("sha256") and _sha256(target) != str(asset.get("sha256")):
                missing_assets.append(f"{asset_id}: sha256 differs from the manifest")
            # Visual rights and claim evidence are separate contracts. A user
            # media import may appear in a local preview when its import receipt
            # binds the bytes and explicitly withholds distribution rights. It
            # still cannot enter the claim ledger above.
            local_preview = is_valid_local_preview_asset(asset, project, root)
            if (asset.get("permission") not in
                    {"OWNED", "CREATED_BY_OWNER", "LICENSED"} and not local_preview):
                missing_assets.append(
                    f"{asset_id}: permission {asset.get('permission')!r} is not usable for visual preview")
        claim = claim_by_id.get(str(beat.get("claim_id") or ""))
        claim_id = str(claim.get("claim_id")) if claim else ""
        m5_lines.append({
            "id": placement,
            "narration": str(beat.get("text") or ""),
            "caption": str(beat.get("text") or ""),
            "claim": claim_id if claim_id in ledger_ids else None,
            "asset_id": asset_id,
        })

    if missing_permissions:
        blockers.insert(0, "source permissions are missing for: "
                           + ", ".join(sorted(set(missing_permissions)))
                           + f" (declare them in {PERMISSIONS_FILE.as_posix()})")
    if unmapped:
        blockers.insert(0, "placements with no asset mapping: " + ", ".join(unmapped)
                           + f" (declare them in {ASSET_MAP_FILE.as_posix()})")
    if missing_assets:
        blockers.extend(missing_assets)

    if blockers:
        raise BridgeBlocked(
            "BRIDGE_BLOCKED",
            f"{len(blockers)} blocker(s) prevent the draft from reaching M5",
            blockers)

    script = {"schema": M5_SCRIPT_SCHEMA, "lines": m5_lines}
    ledger = {"schema": LEDGER_SCHEMA, "claims": ledger_claims}
    return {
        "project": project_rel,
        "brief_id": str((brief or {}).get("brief_id") or ""),
        "content_digest": verdict.get("content_digest"),
        "preview_only": bool(verdict.get("preview_only")),
        "script": script,
        "claims": ledger,
        "source_refs": {"schema": REFS_SCHEMA, "refs": refs},
        "counts": {"lines": len(m5_lines), "claims": len(ledger_claims),
                   "source_refs": len(refs)},
    }


def write(result: Dict[str, Any], project: Path) -> Dict[str, Path]:
    """Write the converted documents into the project. Nothing else changes."""
    project = Path(project)
    written: Dict[str, Path] = {}
    payloads = {
        LINES_FILE.parent / "script.json": result["script"],
        LINES_FILE.parent / "claims.json": result["claims"],
        REFS_FILE: result["source_refs"],
    }
    for relative, document in payloads.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        written[relative.as_posix()] = path
    receipt = {
        "schema": SCHEMA,
        "state": "CONVERTED_FOR_M5",
        "project": result["project"],
        "brief_id": result["brief_id"],
        "content_digest": result["content_digest"],
        "preview_only": bool(result.get("preview_only")),
        "counts": result["counts"],
        "note": ("The brief is unapproved. This conversion only prepares a local "
                 "draft preview; it grants no copy or publication approval."
                 if result.get("preview_only") else
                 "The M5 chain still ends at PENDING_FOUNDER_REVIEW; this conversion "
                 "grants no approval and publishes nothing."),
    }
    path = project / RECEIPT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    written[RECEIPT_FILE.as_posix()] = path
    return written


def check(project: Path, *, repo_root: Optional[Path] = None,
          allow_unapproved_preview: bool = False) -> Dict[str, Any]:
    """Whether the files on disk still match what the bridge would write."""
    project = Path(project)
    result = build(project, repo_root=repo_root,
                   allow_unapproved_preview=allow_unapproved_preview)
    problems: List[str] = []
    for relative, expected in (("script/script.json", result["script"]),
                               ("script/claims.json", result["claims"]),
                               ("sources/source-refs.json", result["source_refs"])):
        path = project / relative
        if not path.is_file():
            problems.append(f"{relative} is missing")
            continue
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != expected:
            problems.append(f"{relative} does not match the current draft")
    return {"ok": not problems, "problems": problems, "counts": result["counts"]}
