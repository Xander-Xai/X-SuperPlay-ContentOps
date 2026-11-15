"""Admit a hand-made screen recording as evidence, or refuse it before the cut.

Why this module exists
----------------------
The VIDEO line already had every piece except the doorway. ``claim_coverage`` counts
``screen_capture`` as a real-evidence kind, ``cut_qc`` enforces a 70% real-source floor on
evidence-led accounts, and ``cut_plan`` binds each placement to the claims it may assert.
But the only importer that accepted a user's own recording — ``media.local_assets`` — marked
it ``evidence_capable: false`` and ``LOCAL_PREVIEW_ONLY``, because that importer exists for
"show me my footage next to my preview" and must never imply distribution rights.

Both behaviours are correct in isolation. Together they made one account impossible to satisfy:
``x-superplay-1024`` asks for 70% recording evidence while declaring manual recording
``ALLOWED_CROPPED``, and the only door into the project said such footage could not be
evidence. The honest workaround was hand-editing ``sources/assets.json``, which bypasses every
gate downstream.

So this module is a separate doorway with a narrower promise than the preview importer and a
wider one than nothing:

* the recording is the Founder's own capture of a real screen, and it is admitted as
  **evidence of what that screen displayed** — not as a licence to distribute it;
* the account DNA decides whether recording is allowed at all, and at intake rather than
  after a render (a ``FORBIDDEN`` account is refused here, where nothing has been spent);
* an ``ALLOWED_CROPPED`` account must supply the crop rectangle, because the account's rule is
  that desktop chrome, stray windows and credentials are removed before the frame is used;
* every file is bound to at least one claim id, so "the picture shows A while the narration
  says B" becomes a contract violation rather than a review note.

What this module does not do: it does not judge whether the crop actually hides what it
claims to hide, it does not decide rights, and it never authorises publication. The receipt
says so in every verdict.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set

from contentops.media.media_paths import serialize_media_path
from contentops.paths import trusted_project_root

__all__ = [
    "ACCEPTED",
    "BLOCKED",
    "REFUSED",
    "MANIFEST",
    "RECEIPT",
    "SCHEMA",
    "RecordingIntakeError",
    "RecordingRequest",
    "account_policy",
    "intake",
]

SCHEMA = "contentops.recording-intake/v1"
MANIFEST_SCHEMA = "contentops.m5-assets/v1"
RECEIPT = Path("receipts") / "recording-intake.json"
MANIFEST = Path("sources") / "assets.json"
CLAIM_MAP = Path("script") / "claim-map.json"
ASSET_DIR = Path("assets") / "recordings"

ACCEPTED = "ACCEPTED"
BLOCKED = "BLOCKED"
REFUSED = "REFUSED"

#: Permissions whose meaning is "this person may record their own screen". Anything else —
#: including a missing value — is a policy this module does not understand, and an
#: unreadable policy is not permission.
RECORDING_ALLOWED = {"ALLOWED": False, "ALLOWED_CROPPED": True}

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}

#: The minimum a clip must last to be usable as a shot. Below this the editor cannot hold
#: a frame long enough to be read, so admitting it would only move the failure downstream.
MIN_DURATION_S = 0.5


class RecordingIntakeError(ValueError):
    """The request itself is malformed (not a policy verdict)."""


@dataclass
class RecordingRequest:
    """One recording the Founder wants admitted into one project."""

    path: Path
    claim_ids: Sequence[str]
    #: ``{"x", "y", "width", "height"}`` in source pixels. Required when the account's
    #: policy is ``ALLOWED_CROPPED``.
    crop: Optional[Dict[str, int]] = None
    #: What the footage shows: a URL, a ``repo://`` path, or a short description. Bound to
    #: the claims so the evidence is not anonymous.
    source_ref: str = ""
    #: Inclusive start / exclusive end of the usable region, in milliseconds.
    in_ms: Optional[int] = None
    out_ms: Optional[int] = None
    notes: str = ""

    def normalized_claims(self) -> List[str]:
        seen: List[str] = []
        for item in self.claim_ids or []:
            text = str(item or "").strip()
            if text and text not in seen:
                seen.append(text)
        return seen


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip(".-_")
    return (stem or "recording")[:64]


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _project_yaml_scalar(project: Path, key: str) -> str:
    path = project / "project.yaml"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return ""


def account_policy(project: Path, *, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """The account's recording policy, or an explicit "not declared".

    The DNA is the only source. A project that names no account is not defaulted to some
    permissive profile: that default is how a banned format reaches a render.
    """
    project = Path(project)
    slug = _project_yaml_scalar(project, "account_slug")
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
    if not slug:
        return {"declared": False, "slug": "", "manual_recording": "",
                "evidence_mode": "", "reason": "project.yaml 未声明 account_slug"}
    dna_path = root / "config" / "accounts" / f"{slug}.json"
    dna = _load_json(dna_path)
    if dna is None:
        return {"declared": False, "slug": slug, "manual_recording": "",
                "evidence_mode": "", "reason": f"账号 DNA 不可读: config/accounts/{slug}.json"}
    evidence = dna.get("evidence") if isinstance(dna.get("evidence"), dict) else {}
    return {
        "declared": True,
        "slug": slug,
        "manual_recording": str(evidence.get("manual_recording") or ""),
        "evidence_mode": str(evidence.get("mode") or ""),
        "reason": "",
    }


def _default_probe(path: Path) -> Dict[str, Any]:
    from contentops.media.transport import ffprobe_json

    return ffprobe_json(path)


def _measure(probe: Mapping[str, Any]) -> Dict[str, Any]:
    """Duration and frame size from an ffprobe document, without inventing defaults."""
    duration = 0.0
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    video: Dict[str, Any] = {}
    for stream in probe.get("streams") or []:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            video = stream
            break
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if duration <= 0:
        try:
            duration = float(video.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
    return {"duration_s": round(duration, 3), "width": width, "height": height,
            "codec": str(video.get("codec_name") or "unknown")}


def _crop_verdict(crop: Optional[Mapping[str, Any]], width: int, height: int) -> Optional[str]:
    """Return a reason code when the crop cannot be honoured, else ``None``."""
    if crop is None:
        return "CROP_REQUIRED"
    for axis in ("x", "y", "width", "height"):
        value = crop.get(axis)
        if not isinstance(value, int) or isinstance(value, bool):
            return "CROP_INVALID"
        if value < 0:
            return "CROP_INVALID"
    if crop["width"] <= 0 or crop["height"] <= 0:
        return "CROP_INVALID"
    if width and height:
        if crop["x"] + crop["width"] > width or crop["y"] + crop["height"] > height:
            return "CROP_OUT_OF_BOUNDS"
    return None


def _known_claims(project: Path) -> Optional[Set[str]]:
    document = _load_json(project / CLAIM_MAP)
    if document is None:
        return None
    items = document.get("claims")
    ids: Set[str] = set()
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                value = item.get("claim_id") or item.get("id")
                if value:
                    ids.add(str(value))
    elif isinstance(document.get("by_id"), dict):
        ids.update(str(key) for key in document["by_id"])
    return ids


def _read_manifest(project: Path) -> Dict[str, Any]:
    path = project / MANIFEST
    if not path.is_file():
        return {
            "schema": MANIFEST_SCHEMA,
            "policy": "Every row states its own evidence and distribution scope. A recording "
                      "registered here is evidence of what a screen displayed; it is not a "
                      "distribution licence.",
            "assets": [],
        }
    document = _load_json(path)
    if document is None or document.get("schema") != MANIFEST_SCHEMA \
            or not isinstance(document.get("assets"), list):
        raise RecordingIntakeError(
            f"{MANIFEST.as_posix()} is unreadable or uses an unsupported schema")
    return document


def _receipt(project: Path, request: RecordingRequest, policy: Mapping[str, Any], *,
             verdict: str, reason_code: str, reason: str,
             files: Optional[List[Dict[str, Any]]] = None,
             bindings: Optional[List[Dict[str, Any]]] = None,
             extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "verdict": verdict,
        "reason_code": reason_code,
        "reason": reason,
        "account": {"slug": policy.get("slug", ""),
                    "manual_recording": policy.get("manual_recording", ""),
                    "evidence_mode": policy.get("evidence_mode", "")},
        "request": {
            "source_name": Path(request.path).name if request.path else "",
            "claim_ids": request.normalized_claims(),
            "crop": request.crop,
            "trim_ms": [request.in_ms, request.out_ms]
            if request.in_ms is not None or request.out_ms is not None else None,
            "source_ref": request.source_ref,
        },
        "files": files or [],
        "bindings": bindings or [],
        # Both flags are structural, not ceremonial: admitting evidence never makes a film
        # publishable, and no automated check in this repository may grant that.
        "production_ready": False,
        "publish_authorized": False,
        "does_not_claim": "This receipt admits material as evidence of what a screen "
                          "displayed. It does not clear third-party rights, does not approve "
                          "the cut, and does not authorise distribution.",
    }
    if extra:
        payload.update(extra)
    return payload


def _write_receipt(project: Path, payload: Dict[str, Any]) -> Path:
    target = project / RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def intake(project: Path, request: RecordingRequest, *,
           repo_root: Optional[Path] = None,
           probe: Optional[Callable[[Path], Mapping[str, Any]]] = None,
           apply: bool = True,
           write: bool = True) -> Dict[str, Any]:
    """Decide whether one recording may enter the project, and register it if so.

    ``apply=False`` stops after the verdict: nothing is copied and the manifest is left
    untouched, which is what a dry run must mean. A ``BLOCKED`` or ``REFUSED`` verdict still
    writes a receipt, because a refusal that leaves no trace is indistinguishable from a
    request nobody made.
    """
    project = Path(project).expanduser().resolve()
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    if trusted_project_root(project, root) is None:
        raise RecordingIntakeError(
            "project directory must stay inside the repository or the configured output root")

    policy = account_policy(project, repo_root=root)

    def refuse(code: str, reason: str, **kwargs: Any) -> Dict[str, Any]:
        payload = _receipt(project, request, policy, verdict=REFUSED,
                           reason_code=code, reason=reason, **kwargs)
        if write:
            _write_receipt(project, payload)
        return payload

    def block(code: str, reason: str, **kwargs: Any) -> Dict[str, Any]:
        payload = _receipt(project, request, policy, verdict=BLOCKED,
                           reason_code=code, reason=reason, **kwargs)
        if write:
            _write_receipt(project, payload)
        return payload

    # 1. Policy first: on a FORBIDDEN account nothing else about the file matters.
    if not policy["declared"]:
        return block("ACCOUNT_UNANNOUNCED",
                     f"账号未声明：{policy['reason']}。没有账号 DNA 就没有录屏策略，"
                     "此处不放行任何默认值。")
    permission = policy["manual_recording"]
    if permission == "FORBIDDEN":
        return refuse("RECORDING_FORBIDDEN_BY_DNA",
                      f"账号 {policy['slug']} 的 evidence.manual_recording=FORBIDDEN，"
                      "本账号禁止任何手动录屏素材；改用动画或代码截图解释同一句话。")
    if permission not in RECORDING_ALLOWED:
        return block("POLICY_UNKNOWN",
                     f"账号 {policy['slug']} 的 manual_recording={permission!r} 不在已知取值内，"
                     "未知策略不放行。")
    needs_crop = RECORDING_ALLOWED[permission]

    # 2. The file itself.
    source = Path(request.path).expanduser()
    if not source.is_file():
        return block("FILE_MISSING", f"找不到录屏文件：{source}")
    if source.suffix.casefold() not in VIDEO_SUFFIXES:
        return block("FILE_UNSUPPORTED",
                     f"只接受 {sorted(VIDEO_SUFFIXES)} 的视频文件，收到 {source.suffix!r}")
    measure = probe or _default_probe
    try:
        summary = _measure(measure(source))
    except Exception as exc:  # noqa: BLE001 - any probe failure is "cannot measure"
        return block("PROBE_FAILED", f"无法测量录屏：{exc}。无法测量即无法证明，故不放行。")
    if summary["duration_s"] < MIN_DURATION_S:
        return block("DURATION_INVALID",
                     f"录屏时长 {summary['duration_s']}s 低于可用下限 {MIN_DURATION_S}s")

    # 3. Trim window, when given.
    if request.in_ms is not None or request.out_ms is not None:
        start = request.in_ms if request.in_ms is not None else 0
        end = request.out_ms if request.out_ms is not None \
            else int(summary["duration_s"] * 1000)
        if start < 0 or end <= start or end > int(summary["duration_s"] * 1000) + 1:
            return block("TRIM_OUT_OF_RANGE",
                         f"trim [{start}, {end}]ms 不在 0–{int(summary['duration_s'] * 1000)}ms 内")

    # 4. Crop: the account's rule, checked structurally.
    if needs_crop or request.crop is not None:
        reason_code = _crop_verdict(request.crop, summary["width"], summary["height"])
        if reason_code == "CROP_REQUIRED":
            return block("CROP_REQUIRED",
                         f"账号 {policy['slug']} 要求录屏裁切后再用，但请求未给裁切矩形")
        if reason_code == "CROP_INVALID":
            return block("CROP_INVALID", "裁切矩形必须是 4 个非负整数 x/y/width/height")
        if reason_code == "CROP_OUT_OF_BOUNDS":
            return block("CROP_OUT_OF_BOUNDS",
                         f"裁切矩形超出源画面 {summary['width']}×{summary['height']}")

    # 5. Claim binding: evidence without a claim cannot support anything.
    claims = request.normalized_claims()
    if not claims:
        return block("CLAIM_REQUIRED", "每条录屏必须绑定至少一个 claim_id")
    known = _known_claims(project)
    bindings: List[Dict[str, Any]] = []
    unknown = [item for item in claims if known is not None and item not in known]
    for item in claims:
        bindings.append({"claim_id": item,
                         "resolved": known is None or item in known})
    if unknown:
        return block("CLAIM_UNKNOWN",
                     f"claim-map 中不存在这些 claim_id：{unknown}",
                     bindings=bindings)

    # 6. Admit.
    manifest = _read_manifest(project)
    digest = _sha(source)
    asset_id = f"rec-{digest[:16]}"
    existing = next((row for row in manifest["assets"]
                     if isinstance(row, dict) and str(row.get("id")) == asset_id), None)

    files: List[Dict[str, Any]] = []
    idempotent = existing is not None
    if existing is not None:
        files.append({"asset_id": asset_id, "sha256": digest,
                      "repo_path": existing.get("repo_path"),
                      "source_name": source.name, "idempotent": True,
                      "duration_s": summary["duration_s"],
                      "frame_size": {"width": summary["width"], "height": summary["height"]},
                      "codec": summary["codec"], "crop": request.crop,
                      "trim_ms": [request.in_ms, request.out_ms]})
    elif not apply:
        planned = project / ASSET_DIR / \
            f"{digest[:12]}-{_safe_name(source.name)}{source.suffix.casefold()}"
        reference = serialize_media_path(planned, repo_root=root, project_root=project)
        files.append({"asset_id": asset_id, "sha256": digest, "repo_path": reference,
                      "source_name": source.name, "idempotent": False, "planned": True,
                      "duration_s": summary["duration_s"],
                      "frame_size": {"width": summary["width"], "height": summary["height"]},
                      "codec": summary["codec"], "crop": request.crop,
                      "trim_ms": [request.in_ms, request.out_ms]})
    else:
        target_dir = project / ASSET_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest[:12]}-{_safe_name(source.name)}{source.suffix.casefold()}"
        try:
            target.resolve().relative_to(project)
        except ValueError:
            raise RecordingIntakeError("recording destination resolves outside the project")
        if target.is_symlink():
            raise RecordingIntakeError(f"refusing symlinked destination {target.name}")
        target.write_bytes(source.read_bytes())
        reference = serialize_media_path(target, repo_root=root, project_root=project)
        if reference is None:
            target.unlink(missing_ok=True)
            return block("PATH_SERIALIZATION_FAILED",
                         "录屏落在仓库与项目根之外，无法生成可移植引用")
        row = {
            "id": asset_id,
            "sha256": digest,
            "type": "recording",
            "origin": "SELF_CAPTURED",
            "permission": "SELF_CAPTURED_CROPPED" if request.crop else "SELF_CAPTURED",
            "usage_scope": "EVIDENCE_REVIEW_REQUIRED",
            "evidence_capable": True,
            "distribution_authorized": False,
            "requires_human_review": True,
            "repo_path": reference,
            "source_name": source.name,
            "frame_size": {"width": summary["width"], "height": summary["height"]},
            "crop": request.crop,
            "trim_ms": [request.in_ms, request.out_ms]
            if request.in_ms is not None or request.out_ms is not None else None,
            "claim_ids": claims,
            "source_ref": request.source_ref,
            "captured_by": "FOUNDER_MANUAL",
            "notes": request.notes,
        }
        manifest["assets"].append(row)
        manifest_path = project / MANIFEST
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        files.append({"asset_id": asset_id, "sha256": digest, "repo_path": reference,
                      "source_name": source.name, "idempotent": False,
                      "duration_s": summary["duration_s"],
                      "frame_size": {"width": summary["width"], "height": summary["height"]},
                      "codec": summary["codec"], "crop": request.crop,
                      "trim_ms": [request.in_ms, request.out_ms]})

    payload = _receipt(
        project, request, policy, verdict=ACCEPTED, reason_code="ADMITTED",
        reason=f"账号 {policy['slug']} 允许录屏（{permission}），素材已登记为可作证据",
        files=files, bindings=bindings,
        extra={"manifest": MANIFEST.as_posix(),
               "idempotent": idempotent,
               "applied": bool(apply and existing is None),
               "still_required": ["人工确认裁切后桌面/弹窗/凭据已移除",
                                  "CutPlan 把该素材绑到同一 claim",
                                  "QC 的 70% 真实素材门与人工复核"]})
    if write:
        _write_receipt(project, payload)
    return payload
