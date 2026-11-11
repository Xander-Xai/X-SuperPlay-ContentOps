#!/usr/bin/env python3
"""One preflight contract for every content production run.

The repository already implements account DNA, copy review, evidence links,
MiniMax voice clone, H3 bookends and Huashu motion. All of them are *conditional*:
they fire only when ``project.yaml`` names ``account_slug`` and the operator
remembers to pass the right flags. A run that skips those steps still produces
media, silently degraded. This module turns the conditions into a fail-closed
contract:

    answer  -> receipts/production-intent.json (+ idempotent project.yaml blocks)
    check   -> six gates, all must pass before any producer is invoked
    run     -> check, then delegate to the existing produce_video.produce()

It calls no provider, starts no host, spends no quota and publishes nothing.
A green check is not a production approval: the receipt keeps
``production_ready: false`` / ``publish_authorized: false``.

Usage:
    python scripts/make_content.py answer --project projects/my-video \
        --account explorer --asset-policy supplement \
        --avatar-intro no --avatar-outro no \
        --narration minimax-clone --motion huashu-art-motion --confirm
    python scripts/make_content.py check --project projects/my-video
    python scripts/make_content.py run --project projects/my-video --mode STRICT
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

SCHEMA = "contentops.production-intent/v1"
CHECK_SCHEMA = "contentops.production-gate-check/v1"
INTENT_FILE = Path("receipts") / "production-intent.json"
BACKUP_FILE = Path("receipts") / "project-yaml-before-preflight.yaml"

# Bundle account_treatments use role names; account DNA uses slugs. The two
# vocabularies were never mapped, which is why a handoff could name "thinktank"
# and still leave account_slug unset downstream.
ACCOUNT_ALIASES = {
    "explorer": "x-superplay-1024",
    "thinktank": "x-superplay-future-intelligence",
}

GATES = (
    "account",
    "copy_review",
    "evidence_links",
    "asset_sufficiency",
    "avatar_bookends",
    "style_audio",
    "runtime_readiness",
)

ASSET_POLICIES = ("supplement", "local-free", "minimax-authorized")
BGM_POLICIES = ("none", "local-asset")
NARRATION_CHOICES = ("minimax-clone", "sapi")
MOTION_CHOICES = ("huashu-art-motion", "huashu-motion", "none")
YES_NO = ("yes", "no")


class GateError(RuntimeError):
    """A production gate refused the run; nothing was produced."""

    def __init__(self, code: str, detail: str, report: Optional[Dict[str, Any]] = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.report = report


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def resolve_account(value: str, root: Path = ROOT) -> str:
    """Resolve a Bundle role name or a DNA slug into a verified DNA slug."""
    if not value or not isinstance(value, str):
        raise GateError("ACCOUNT_REQUIRED", "no account was named for this run")
    slug = ACCOUNT_ALIASES.get(value.strip(), value.strip())
    dna = root / "config" / "accounts" / f"{slug}.json"
    payload = _read_json(dna)
    if payload is None:
        raise GateError("ACCOUNT_DNA_MISSING", f"no account DNA at {dna}")
    if payload.get("schema") != "contentops.account-dna/v2":
        raise GateError("ACCOUNT_DNA_MALFORMED",
                        f"{dna} is not contentops.account-dna/v2")
    return slug


def _yaml_top_level(text: str, key: str) -> Optional[str]:
    match = re.search(rf"^{re.escape(key)}\s*:\s*(\S.*)?$", text, re.MULTILINE)
    return match.group(1).strip() if match and match.group(1) else (match.group(0) if match else None)


def _project_yaml_value(project: Path, key: str) -> Optional[str]:
    text = (project / "project.yaml").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip('"\'') if match else None


def apply_project_config(project: Path, intent: Dict[str, Any]) -> Dict[str, Any]:
    """Idempotently write the blocks that silently default to degraded paths.

    ``account_slug`` is the load-bearing one: m5_production._resolve_narration_defaults,
    _load_digital_presenter_profile and stage_motion all read account DNA through it.
    Without it the run silently uses Windows SAPI, no avatar and NOT_CONFIGURED motion.
    ``media_use`` is deliberately NOT written here: enabling it requires reviewed
    rights sidecars, and inventing one would fail the real rights gate.
    """
    path = project / "project.yaml"
    if path.is_file():
        original = path.read_text(encoding="utf-8")
    else:
        # A GRAPHIC_TEXT project may have no project.yaml at all; create the
        # minimum so the same account contract applies to both lines.
        original = f"id: {project.name}\ntitle: {project.name}\nstatus: initialized\n"
        path.write_text(original, encoding="utf-8")
    additions: List[str] = []
    slug = intent["account_slug"]

    current = _project_yaml_value(project, "account_slug")
    if current and current != slug:
        raise GateError("ACCOUNT_CONFLICT",
                        f"project.yaml already names {current!r}, intent names {slug!r}")
    if not current:
        additions.append(f"account_slug: {slug}")

    motion = str(intent.get("motion_backend") or "none")
    if motion != "none" and not re.search(r"^motion\s*:", original, re.MULTILINE):
        additions.append(f"motion:\n  backend: {motion}")

    if not additions:
        return {"changed": False, "added": [], "backup": None}

    backup = project / BACKUP_FILE
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    path.write_text(original.rstrip() + "\n\n# Added by production_gates.apply_project_config\n"
                    + "\n".join(additions) + "\n", encoding="utf-8")
    return {"changed": True, "added": additions,
            "backup": backup.relative_to(project).as_posix()}


def load_intent(project: Path) -> Optional[Dict[str, Any]]:
    payload = _read_json(project / INTENT_FILE)
    if payload is None or payload.get("schema") != SCHEMA:
        return None
    return payload


def write_intent(project: Path, *, account: str, asset_policy: str,
                 avatar_intro: str, avatar_outro: str,
                 avatar_quota_budget: Optional[str], narration: str,
                 motion_backend: str, reviewer: str, opinion: str,
                 bgm_policy: str = "none",
                 root: Path = ROOT) -> Dict[str, Any]:
    """Record the human decisions. This never signs copy review on their behalf."""
    slug = resolve_account(account, root)
    if asset_policy not in ASSET_POLICIES:
        raise GateError("ASSET_POLICY_INVALID", f"choose one of {ASSET_POLICIES}")
    if bgm_policy not in BGM_POLICIES:
        raise GateError("BGM_POLICY_INVALID", f"choose one of {BGM_POLICIES}")
    if asset_policy == "minimax-authorized":
        # Recording an option that can never pass is a dead end, not a gate.
        # Refuse it here and name the two ways to make it real.
        boundary = minimax_policy(root)
        has_key = (_env_has("MINIMAX_SUBSCRIPTION_KEY", root)
                   or _env_has("MINIMAX_API_KEY", root))
        if boundary["state"] != "OK" or not has_key:
            raise GateError(
                "MINIMAX_NOT_AVAILABLE",
                f"cannot record MiniMax asset generation: {boundary['detail']}; "
                f"subscription key configured: {has_key}. Configure the key and lift "
                "ADR-014, or answer supplement/local-free.")
    if avatar_intro not in YES_NO or avatar_outro not in YES_NO:
        raise GateError("AVATAR_DECISION_REQUIRED",
                        "both --avatar-intro and --avatar-outro need an explicit yes/no")
    if (avatar_intro == "yes" or avatar_outro == "yes") and not avatar_quota_budget:
        raise GateError("AVATAR_QUOTA_REQUIRED",
                        "H3 bookends need --avatar-quota-budget (7pp per clip)")
    if narration not in NARRATION_CHOICES:
        raise GateError("NARRATION_INVALID", f"choose one of {NARRATION_CHOICES}")
    if motion_backend not in MOTION_CHOICES:
        raise GateError("MOTION_INVALID", f"choose one of {MOTION_CHOICES}")
    if not reviewer.strip() or not opinion.strip():
        raise GateError("REVIEWER_REQUIRED",
                        "name the person who answers these gates and record an opinion")

    intent = {
        "schema": SCHEMA,
        "project": project.name,
        "created_at": _now(),
        "answered_by": reviewer.strip(),
        "opinion": opinion.strip(),
        "account": account.strip(),
        "account_slug": slug,
        "asset_policy": asset_policy,
        "bgm_policy": bgm_policy,
        "avatar_intro": avatar_intro,
        "avatar_outro": avatar_outro,
        "avatar_quota_budget": avatar_quota_budget,
        "narration": narration,
        "motion_backend": motion_backend,
        "minimax_extra_assets_authorized": asset_policy == "minimax-authorized",
        "requested_provider": "minimax-image/video" if asset_policy == "minimax-authorized" else None,
        "fallback_reason": None,
        "requires_human_review": True,
        "production_ready": False,
        "publish_authorized": False,
        "note": ("A recorded intent is not an approval to spend quota. MiniMax generation "
                 "remains subject to ADR-014, BillingGuard and an interactive H3 confirmation."),
    }
    _write_json(project / INTENT_FILE, intent)
    return intent


def asset_sufficiency(project: Path) -> Dict[str, Any]:
    """Compare declared visuals with narration beats; never invent assets."""
    assets = _read_json(project / "sources" / "assets.json") or {}
    script = _read_json(project / "script" / "script.json") or {}
    rows = assets.get("assets") if isinstance(assets.get("assets"), list) else []
    lines = script.get("lines") if isinstance(script.get("lines"), list) else []
    missing_ids = sorted({str(line.get("asset_id")) for line in lines
                          if isinstance(line, dict) and line.get("asset_id")}
                         - {str(row.get("id")) for row in rows if isinstance(row, dict)})
    ok = bool(rows) and not missing_ids
    return {"ok": ok, "asset_count": len(rows), "line_count": len(lines),
            "undeclared_asset_ids": missing_ids,
            "detail": "every narration beat has a declared asset" if ok
                      else f"{len(missing_ids)} beat(s) have no declared asset"}


def evidence_links(project: Path) -> Dict[str, Any]:
    """Every cited evidence item needs a real link and a pinned digest."""
    pack_path = project / "00_brief" / "evidence-pack.json"
    pack = _read_json(pack_path)
    if pack is None:
        return {"ok": False, "state": "EVIDENCE_PACK_MISSING",
                "detail": "00_brief/evidence-pack.json is absent; copy cannot be traced"}
    items = pack.get("items") if isinstance(pack.get("items"), list) else []
    broken = [str(item.get("evidence_id") or "(no id)") for item in items
              if not isinstance(item, dict)
              or not str(item.get("url") or "").strip()
              or not str(item.get("sha256") or item.get("excerpt") or "").strip()]
    if not items:
        return {"ok": False, "state": "EVIDENCE_EMPTY",
                "detail": "evidence pack has no items"}

    # A pack nobody cites does not prove the copy carries a citation. master.md
    # is rewritten by M5 stage_script with one link per claim; count them.
    master = project / "script" / "master.md"
    claims_doc = _read_json(project / "script" / "claims.json") or {}
    claim_count = len(claims_doc.get("claims") or [])
    links = _markdown_links(master.read_text(encoding="utf-8")) if master.is_file() else 0

    if not broken and claim_count and links < claim_count:
        return {"ok": False, "state": "COPY_LINKS_MISSING", "items": len(items),
                "claims": claim_count, "links": links,
                "detail": (f"script/master.md has {links} citation link(s) for "
                           f"{claim_count} claim(s); every claim needs [title](url)")}

    ok = not broken
    return {"ok": ok, "state": "OK" if ok else "EVIDENCE_INCOMPLETE",
            "items": len(items), "incomplete": broken, "claims": claim_count,
            "links": links,
            "detail": ("every evidence item has a link and pinned content, and the "
                       "copy cites them" if ok else f"incomplete: {broken}")}


def minimax_policy(root: Path = ROOT) -> Dict[str, Any]:
    """Read-only statement of the current MiniMax boundary; no credentials read."""
    adr = root / "docs" / "adr" / "ADR-014-delivery-validation-hold.md"
    present = adr.is_file()
    return {
        "state": "BLOCKED_BY_POLICY" if present else "UNKNOWN_POLICY",
        "policy_ref": "docs/adr/ADR-014-delivery-validation-hold.md" if present else None,
        "detail": ("ADR-014 does not authorize new MiniMax generation requests or paid "
                   "digital-human experiments; recording consent does not lift it."
                   if present else "the hold decision could not be found"),
        "payg_allowed": False,
    }


def _env_has(key: str, root: Path) -> bool:
    """Whether a provider key is configured. Never reads or prints its value."""
    import os

    if os.environ.get(key):
        return True
    try:
        text = (root / ".env").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^{re.escape(key)}\s*=\s*\S", text, re.MULTILINE) is not None


def _motion_runtime_present(root: Path = ROOT) -> bool:
    """True when the pinned Huashu motion runtime is discoverable on this host.

    A seam, not a shortcut: CI runners never install the runtime, so the gate
    logic is exercised with this stubbed while the probe itself is tested
    directly (``HostProbeTests``).
    """
    try:
        from contentops.media.huashu_runtime import find_runtime

        find_runtime(root)
        return True
    except Exception:  # noqa: BLE001 - any discovery failure means "absent"
        return False


def _graphic_validator_present(root: Path = ROOT) -> bool:
    """True when the pinned GZH HTML validator exists in the runtime tree."""
    validator = (root / ".runtime" / "easel" / "skills" / "openclaw"
                 / "gzh-design" / "scripts" / "validate_gzh_html.py")
    return validator.is_file()


def runtime_readiness(project: Path, intent: Dict[str, Any],
                      root: Path = ROOT) -> Dict[str, Any]:
    """Can this machine actually execute the capabilities the gates just approved?

    A green decision gate is not an executable run. The 2026-11-12 acceptance run
    passed all six gates and then spent 89 seconds before M5 blocked on a missing
    SILICONFLOW_API_KEY. This gate moves those failures forward, before any render.
    """
    problems: List[str] = []

    for rel in ("script/script.json", "sources/assets.json", "script/claims.json"):
        if not (project / rel).is_file():
            problems.append(f"{rel} is missing")

    if intent.get("narration") == "minimax-clone":
        if not (_env_has("MINIMAX_SUBSCRIPTION_KEY", root)
                or _env_has("MINIMAX_API_KEY", root)):
            problems.append("narration=minimax-clone requires MINIMAX_SUBSCRIPTION_KEY "
                            "or MINIMAX_API_KEY (neither is configured)")

    if intent.get("account_slug") and not _env_has("SILICONFLOW_API_KEY", root):
        problems.append("an account-bound run forces the ASR backcheck, which requires "
                        "SILICONFLOW_API_KEY (not configured)")

    if str(intent.get("motion_backend") or "none") != "none":
        if not (project / "sources" / "source-refs.json").is_file():
            problems.append("a motion backend needs sources/source-refs.json "
                            "(written by brief_to_m5; absent here)")
        if not _motion_runtime_present(root):
            problems.append("the Huashu motion runtime is not discoverable on this host")

    if intent.get("bgm_policy") == "local-asset":
        import os

        lock = os.environ.get("CONTENTOPS_MEDIA_USE_RUNTIME_LOCK") or ""
        if not lock or not Path(lock).is_file():
            problems.append("bgm=local-asset needs CONTENTOPS_MEDIA_USE_RUNTIME_LOCK "
                            "pointing at a verified media-use runtime (RUNBOOK §10)")

    return {"ok": not problems,
            "state": "OK" if not problems else "RUNTIME_NOT_READY",
            "problems": problems,
            "detail": ("runtime prerequisites present" if not problems
                       else "cannot execute: " + "; ".join(problems))}


def _is_graphic_line(project: Path) -> bool:
    """A GRAPHIC_TEXT project has no M5 script; this preflight only covers VIDEO."""
    return (not (project / "script" / "script.json").is_file()
            and ((project / "draft.md").is_file()
                 or (project / "graphic-input.json").is_file()))


def _project_refs(project: Path) -> List[Dict[str, Any]]:
    """Read ``source_refs`` from project.yaml without needing a second parser."""
    import yaml

    try:
        data = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return []
    refs = data.get("source_refs") if isinstance(data.get("source_refs"), list) else []
    return [row for row in refs
            if isinstance(row, dict) and row.get("id") and row.get("path")]


def ensure_evidence_pack(project: Path, root: Path = ROOT) -> Dict[str, Any]:
    """Build ``00_brief/evidence-pack.json`` from project.yaml's source_refs.

    The pack is what makes "copy cites a link" checkable. Requiring a human to
    hand-write it was the reason the old gate could pass while the copy carried
    no citation at all.
    """
    target = project / "00_brief" / "evidence-pack.json"
    existing = _read_json(target)
    if existing and existing.get("items"):
        return {"changed": False, "items": len(existing["items"])}
    items = []
    for ref in _project_refs(project):
        relative = str(ref["path"])
        source = root / relative
        if not source.is_file():
            continue
        items.append({
            "evidence_id": str(ref["id"]),
            "kind": str(ref.get("type") or "document"),
            "title": str(ref.get("title") or ref["id"]),
            "url": str(ref.get("url") or f"repo://{relative}"),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "document": relative,
            "excerpt": "pinned by project.yaml source_refs",
        })
    if not items:
        # A GRAPHIC_TEXT project has no source_refs block; its citations live in
        # draft.md. Derive the pack from those links so the same evidence gate
        # applies to both lines.
        draft = project / "draft.md"
        if draft.is_file():
            for index, match in enumerate(
                    re.finditer(r"\[([^\]]+)\]\((<?)([^)\s>]+)\2\)",
                                draft.read_text(encoding="utf-8")), start=1):
                title, url = match.group(1), match.group(3)
                items.append({
                    "evidence_id": f"E-{index:02d}",
                    "kind": "link",
                    "title": title.strip()[:120],
                    "url": url,
                    "sha256": "",
                    "document": "",
                    "excerpt": match.group(0)[:200],
                })
    if not items:
        # Last resort for a graphic package: every declared image carries its
        # own rights source, which is the evidence a reviewer can actually open.
        graphic = _read_json(project / "graphic-input.json") or {}
        for index, image in enumerate(graphic.get("images") or [], start=1):
            if not isinstance(image, dict):
                continue
            rights = image.get("rights") or {}
            url = str(rights.get("source_url") or "")
            if not url:
                continue
            items.append({
                "evidence_id": f"IMG-{index:02d}",
                "kind": "image_rights",
                "title": str(image.get("alt") or image.get("asset_id")
                             or f"image {index}")[:120],
                "url": url,
                "sha256": "",
                "document": str(image.get("path") or ""),
                "excerpt": str(rights.get("license_id") or "")[:200],
            })
    if not items:
        # Not fatal here: the check gate reports it as EVIDENCE_PACK_MISSING with
        # the remedy. Bootstrap must not crash before the operator can answer.
        return {"changed": False, "skipped": "no project.yaml source_refs resolve to a file"}
    _write_json(target, {"schema": "contentops.evidence-pack/v1", "items": items})
    return {"changed": True, "items": len(items), "path": "00_brief/evidence-pack.json"}


def ensure_source_refs(project: Path, root: Path = ROOT) -> Dict[str, Any]:
    """Build ``sources/source-refs.json``, the file ``stage_motion`` needs.

    Without it the Huashu auto shot plan calls json.loads on a missing file and
    the whole motion stage blocks — the reason a correctly configured account
    still produced a static-card film.
    """
    target = project / "sources" / "source-refs.json"
    existing = _read_json(target)
    if existing and existing.get("refs"):
        return {"changed": False, "refs": len(existing["refs"])}
    refs = []
    for ref in _project_refs(project):
        relative = str(ref["path"])
        if not (root / relative).is_file():
            continue
        # Mirror the project.yaml row byte-for-byte. M5 merges the two
        # declarations and refuses a duplicate id whose payload differs, so
        # adding a derived field here would block every run.
        refs.append(dict(ref))
    if not refs:
        return {"changed": False, "skipped": "no project.yaml source_refs resolve to a file"}
    _write_json(target, {"schema": "contentops.m5-source-refs/v1", "refs": refs})
    return {"changed": True, "refs": len(refs)}


def ensure_inputs(project: Path, root: Path = ROOT) -> Dict[str, Any]:
    """Idempotently materialise both derived contracts, with one receipt."""
    result = {
        "evidence_pack": ensure_evidence_pack(project, root),
        "source_refs": ensure_source_refs(project, root),
    }
    _write_json(project / "receipts" / "inputs-bootstrap.json", {
        "schema": "contentops.inputs-bootstrap/v1", "created_at": _now(), **result,
    })
    return result


def _markdown_links(text: str) -> int:
    return len(re.findall(r"\]\(<?(?:https?://|repo://|[^)\s]+\.md)", text))


def _graphic_asset_rights(project: Path) -> Dict[str, Any]:
    data = _read_json(project / "graphic-input.json") or {}
    images = data.get("images") if isinstance(data.get("images"), list) else []
    problems: List[str] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        asset_id = str(image.get("asset_id") or "(no id)")
        if not str(image.get("alt") or "").strip():
            problems.append(f"{asset_id}: missing ALT text")
        rights = image.get("rights") or {}
        if not rights.get("license_id"):
            problems.append(f"{asset_id}: missing license_id")
        evidence = str(rights.get("review_evidence") or "")
        if evidence and not (project / evidence).is_file():
            problems.append(f"{asset_id}: review_evidence {evidence} is missing")
        path = str(image.get("path") or "")
        if path and not path.startswith("repo://") and not (project / path).is_file():
            problems.append(f"{asset_id}: image file {path} is missing")
    return {"ok": bool(images) and not problems, "images": len(images),
            "problems": problems}


def check_graphic(project: Path, intent: Dict[str, Any],
                  root: Path = ROOT) -> Dict[str, Any]:
    """The GRAPHIC_TEXT line gets its own gate set, not a fake video pass."""
    rows: List[Dict[str, Any]] = []

    def add(gate: str, ok: bool, detail: str, **extra):
        rows.append({"gate": gate, "ok": bool(ok), "detail": detail, **extra})

    try:
        slug = resolve_account(intent.get("account", ""), root)
        add("account", slug == intent.get("account_slug"),
            f"DNA {slug}" if slug == intent.get("account_slug")
            else f"DNA resolves to {slug} but intent names {intent.get('account_slug')!r}")
    except GateError as exc:
        add("account", False, str(exc))

    review = _copy_review_state(project)
    add("copy_review", review["ok"],
        "draft review APPROVED and fingerprint current" if review["ok"]
        else f"{review['state']}: {review['detail']}")

    evidence = evidence_links(project)
    draft = project / "draft.md"
    links = _markdown_links(draft.read_text(encoding="utf-8")) if draft.is_file() else 0
    ok = evidence["ok"] and draft.is_file() and links >= 3
    detail = evidence["detail"]
    if not draft.is_file():
        detail += "; draft.md is missing"
    elif links < 3:
        detail += f"; draft.md has {links} citation link(s), need at least 3"
    add("evidence_links", ok, detail)

    rights = _graphic_asset_rights(project)
    add("asset_rights", rights["ok"],
        f"{rights['images']} image(s) with ALT, licence and file" if rights["ok"]
        else "; ".join(rights["problems"][:4]) or "no images declared")

    problems: List[str] = []
    if not (project / "graphic-input.json").is_file():
        problems.append("graphic-input.json is missing")
    if not _graphic_validator_present(root):
        problems.append("gzh-design validator is absent from the pinned runtime")
    add("runtime_readiness", not problems,
        "graphic runtime prerequisites present" if not problems else "; ".join(problems))

    ok = all(row["ok"] for row in rows)
    return {"schema": CHECK_SCHEMA, "ok": ok, "project": project.name,
            "checked_at": _now(), "format": "GRAPHIC_TEXT", "gates": rows,
            "production_ready": False, "publish_authorized": False,
            "note": "A green preflight is not a publication approval."}


def _copy_review_state(project: Path) -> Dict[str, Any]:
    from contentops.workflow import copy_review

    gate = copy_review.status(project)
    return {"ok": bool(gate.get("ok")), "state": gate.get("state"),
            "detail": gate.get("detail") or gate.get("remedy") or ""}


def _dna_has(project: Path, intent: Dict[str, Any], root: Path) -> Dict[str, Any]:
    dna = _read_json(root / "config" / "accounts" / f"{intent['account_slug']}.json") or {}
    audio = dna.get("audio") if isinstance(dna.get("audio"), dict) else {}
    voice = audio.get("voice") if isinstance(audio.get("voice"), dict) else {}
    visual = dna.get("visual") if isinstance(dna.get("visual"), dict) else {}
    profile = (visual.get("motion") or {}).get("motion_profile") if isinstance(
        visual.get("motion"), dict) else None
    hints = {
        "voice_provider_hint": voice.get("provider_hint"),
        "voice_alias": voice.get("voice_alias"),
        "motion_backend": profile.get("backend") if isinstance(profile, dict) else None,
        "digital_presenter_enabled": bool(
            (audio.get("digital_presenter") or {}).get("enabled")),
    }
    problems = []
    if intent.get("narration") == "minimax-clone" and not hints["voice_provider_hint"]:
        problems.append("account DNA has no narration provider_hint for voice clone")
    if intent.get("motion_backend") != "none" and not hints["motion_backend"]:
        problems.append("account DNA has no motion_profile.backend")
    return {"ok": not problems, "hints": hints, "problems": problems}


def check(project: Path, *, root: Path = ROOT,
          intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a six-gate report. Never raises for an ordinary missing answer."""
    project = Path(project).resolve()
    intent = intent if intent is not None else load_intent(project)
    results: List[Dict[str, Any]] = []

    def add(gate: str, ok: bool, detail: str, **extra):
        results.append({"gate": gate, "ok": bool(ok), "detail": detail, **extra})

    if intent is None:
        add("intent", False, "no production intent; run make_content.py answer first")
        return {"schema": CHECK_SCHEMA, "ok": False, "project": project.name,
                "checked_at": _now(), "gates": results,
                "production_ready": False, "publish_authorized": False}

    # GRAPHIC_TEXT has no M5 script; it gets its own gate set rather than a
    # misleading video result or a blanket refusal.
    if _is_graphic_line(project):
        return check_graphic(project, intent, root)

    # 1. Account: the single field that makes DNA-driven capabilities fire.
    try:
        slug = resolve_account(intent.get("account", ""), root)
        configured = _project_yaml_value(project, "account_slug") if (
            project / "project.yaml").is_file() else None
        ok = slug == intent.get("account_slug") and configured == slug
        add("account", ok,
            f"DNA {slug}; project.yaml account_slug={configured!r}" if ok
            else f"DNA resolves to {slug} but project.yaml has {configured!r}; re-run answer")
    except GateError as exc:
        add("account", False, str(exc))

    # 2. Copy review: hard human gate, independent of the brief-driven exemption.
    review = _copy_review_state(project)
    add("copy_review", review["ok"],
        f"{review['state']}: {review['detail']}" if not review["ok"]
        else "copy review APPROVED and fingerprint current")

    # 3. Evidence links: copy must cite a real link and pinned content.
    evidence = evidence_links(project)
    add("evidence_links", evidence["ok"], evidence["detail"])

    # 4. Asset sufficiency, including the explicit MiniMax consent gate.
    suff = asset_sufficiency(project)
    policy = intent.get("asset_policy")
    if suff["ok"]:
        add("asset_sufficiency", True, suff["detail"])
    elif policy in ("supplement", "local-free"):
        add("asset_sufficiency", False,
            f"assets still insufficient ({suff['detail']}); policy={policy} requires "
            "the missing material to be collected before production",
            asset_state=suff)
    elif policy == "minimax-authorized":
        boundary = minimax_policy(root)
        add("asset_sufficiency", False,
            f"consent recorded, but {boundary['state']}: {boundary['detail']}",
            asset_state=suff, minimax=boundary)
    else:
        add("asset_sufficiency", False,
            f"assets insufficient ({suff['detail']}) and no --asset-policy answered",
            asset_state=suff)

    # 5. Digital-human bookends: an explicit yes/no for each end of the film.
    intro, outro = intent.get("avatar_intro"), intent.get("avatar_outro")
    if intro in YES_NO and outro in YES_NO:
        needs_quota = intro == "yes" or outro == "yes"
        ok = not needs_quota or bool(intent.get("avatar_quota_budget"))
        add("avatar_bookends", ok,
            f"intro={intro}, outro={outro}, quota_budget={intent.get('avatar_quota_budget')!r}")
    else:
        add("avatar_bookends", False,
            "both bookend decisions must be an explicit yes/no")

    # 6. Style and narration: DNA must actually declare the chosen capabilities.
    dna = _dna_has(project, intent, root)
    add("style_audio", dna["ok"],
        "DNA declares the requested voice and motion backends" if dna["ok"]
        else "; ".join(dna["problems"]), hints=dna["hints"])

    # 7. Runtime readiness: an approved decision is not an executable run.
    runtime = runtime_readiness(project, intent, root)
    add("runtime_readiness", runtime["ok"], runtime["detail"],
        problems=runtime["problems"])

    ok = all(row["ok"] for row in results)
    report = {
        "schema": CHECK_SCHEMA, "ok": ok, "project": project.name,
        "checked_at": _now(), "gates": results,
        "intent_sha256": hashlib.sha256(
            (project / INTENT_FILE).read_bytes()).hexdigest() if (
                project / INTENT_FILE).is_file() else None,
        "production_ready": False, "publish_authorized": False,
        "note": "A green preflight is not a production approval or a spend authorization.",
    }
    return report


def require(project: Path, *, root: Path = ROOT) -> Dict[str, Any]:
    """Fail-closed wrapper used by the stable entry point."""
    report = check(project, root=root)
    if not report["ok"]:
        failed = [row["gate"] for row in report["gates"] if not row["ok"]]
        raise GateError("PRODUCTION_GATES_BLOCKED", ", ".join(failed), report)
    return report
