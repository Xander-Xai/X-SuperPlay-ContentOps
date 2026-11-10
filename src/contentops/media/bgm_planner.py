"""Local-only BGM/SFX planning: rights, mood, loudness-aware mix, attribution.

This is a planning layer, not a new audio engine. It reuses
``contentops.media.audio.measure_audio`` for real LUFS / true-peak numbers and
``contentops.media.rights_gate`` for the rights decision, then emits an ffmpeg
filter description for the existing composer. No MoviePy, no paid music vendor,
no automatic download, and no fabricated rights review.

The decisive difference from a fixed ``bgm_volume`` percentage: the music gain
is derived from the *measured* integrated loudness of the narration and of the
track, and a sidechain duck reacts to the actual voice, not to a constant.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from contentops.media.audio import (
    NORMALISATION_TRUE_PEAK_DB,
    AudioMeasurements,
    measure_audio,
)
from contentops.media.rights_gate import RightsError, validate_declared_asset

SCHEMA = "contentops.bgm-plan/v1"
MANIFEST_SCHEMA = "contentops.m5-assets/v1"

MOODS = ("calm", "energetic", "cinematic", "focused", "tense")
ACCOUNT_MOOD_PREFERENCE: Dict[str, Sequence[str]] = {
    "x-superplay-1024": ("focused", "energetic", "cinematic"),
    "x-superplay-future-intelligence": ("calm", "focused", "cinematic"),
}
CONTENT_MOOD_PREFERENCE: Dict[str, Sequence[str]] = {
    "tech_review": ("calm", "focused"),
    "engineering_deep_dive": ("calm", "focused", "cinematic"),
    "product_demo": ("energetic", "focused"),
    "news": ("energetic", "tense"),
}

AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
DEFAULT_MAX_DB_BELOW_VOICE = 18.0
DEFAULT_TRUE_PEAK_CEILING_DB = NORMALISATION_TRUE_PEAK_DB


@dataclass
class TrackRecord:
    asset_id: str
    path: Path
    sha256: str = ""
    license_id: str = ""
    author: str = ""
    source_url: str = ""
    moods: List[str] = field(default_factory=list)
    duration_s: Optional[float] = None
    integrated_lufs: Optional[float] = None
    true_peak_db: Optional[float] = None
    peak_db: Optional[float] = None
    rights_state: str = "UNKNOWN"
    usable: bool = False
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id, "path": self.path.name, "sha256": self.sha256,
            "license_id": self.license_id, "author": self.author,
            "source_url": self.source_url, "moods": list(self.moods),
            "duration_s": self.duration_s, "integrated_lufs": self.integrated_lufs,
            "true_peak_db": self.true_peak_db, "peak_db": self.peak_db,
            "rights_state": self.rights_state, "usable": self.usable,
            "reasons": list(self.reasons),
        }


def _moods_from(row: Mapping[str, Any], path: Path) -> List[str]:
    raw = row.get("moods") or row.get("mood") or []
    if isinstance(raw, str):
        raw = [raw]
    declared = [str(m).strip().lower() for m in raw if str(m).strip()]
    if not declared:
        declared = [token for token in re.split(r"[^a-z]+", path.stem.lower())
                    if token in MOODS]
    return [m for m in declared if m in MOODS]


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_local_tracks(project_dir: Path, *,
                       manifest_path: Optional[Path] = None,
                       measure: Optional[Callable[[Path], AudioMeasurements]] = None
                       ) -> Dict[str, Any]:
    """Index rights-cleared local BGM tracks and their measured loudness.

    A track is only ``usable`` when its bytes match the recorded hash and the
    real Rights Gate clears it. Missing review records stay ``PENDING``; they
    are never silently upgraded into licensed music.
    """
    project = Path(project_dir).resolve()
    path = manifest_path or project / "sources" / "assets.json"
    meter = measure or measure_audio
    records: List[TrackRecord] = []
    if not path.is_file():
        return {"schema": SCHEMA, "state": "NO_LOCAL_TRACKS",
                "tracks": [], "reason": "sources/assets.json is absent"}

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema": SCHEMA, "state": "NO_LOCAL_TRACKS", "tracks": [],
                "reason": f"manifest unreadable: {exc}"}
    if manifest.get("schema") != MANIFEST_SCHEMA:
        return {"schema": SCHEMA, "state": "NO_LOCAL_TRACKS", "tracks": [],
                "reason": "unsupported manifest schema"}

    for row in manifest.get("assets") or []:
        if not isinstance(row, Mapping):
            continue
        blob = " ".join(str(row.get(k) or "") for k in ("type", "kind", "role", "id")).lower()
        if not ("bgm" in blob or "music" in blob or "soundtrack" in blob):
            continue
        rel = str(row.get("repo_relative_path") or row.get("repo_path") or "")
        candidate = (project / rel) if rel else None
        if candidate is None or not rel.lower().endswith(AUDIO_SUFFIXES):
            continue
        if not candidate.is_file() and (project.parent.parent / rel).is_file():
            candidate = project.parent.parent / rel
        record = TrackRecord(asset_id=str(row.get("id") or candidate.name),
                             path=candidate,
                             sha256=str(row.get("sha256") or ""),
                             license_id=str(row.get("license") or ""),
                             author=str(row.get("author") or ""),
                             source_url=str(row.get("source_url") or ""),
                             moods=_moods_from(row, candidate))
        if not candidate.is_file():
            record.reasons.append("reject: audio file missing")
            records.append(record)
            continue
        try:
            actual = _sha256(candidate)
        except OSError as exc:
            record.reasons.append(f"reject: unreadable bytes: {exc}")
            records.append(record)
            continue
        if record.sha256 and actual != record.sha256:
            record.reasons.append("reject: sha256 does not match the manifest")
            records.append(record)
            continue
        record.sha256 = actual

        try:
            validate_declared_asset(dict(row), project)
            record.rights_state = "CLEARED_LOCAL"
        except RightsError as exc:
            record.rights_state = "PENDING_HUMAN_REVIEW"
            record.reasons.append(f"reject: rights gate refused: {exc}")
            records.append(record)
            continue

        metrics = meter(candidate)
        record.duration_s = metrics.duration_s
        record.integrated_lufs = metrics.integrated_lufs
        record.true_peak_db = metrics.true_peak_db
        record.peak_db = metrics.peak_db
        if metrics.true_peak_db is not None and metrics.true_peak_db > -1.0:
            record.reasons.append(
                f"warn: true peak {metrics.true_peak_db:.1f} dBTP is above -1.0 dBTP")
        if not record.moods:
            record.reasons.append("warn: no mood tag; falls back to lowest priority")
        record.usable = True
        record.reasons.append("accept: local, hash-verified, rights-cleared, loudness measured")
        records.append(record)

    usable = [r for r in records if r.usable]
    return {
        "schema": SCHEMA,
        "state": "READY" if usable else "NO_LICENSED_TRACK",
        "tracks": [r.as_dict() for r in records],
        "usable_count": len(usable), "total_count": len(records),
        "license_policy": "local-only; no automatic download of third-party music",
    }


def select_track(index: Mapping[str, Any], *, account_slug: str,
                 content_type: str = "tech_review",
                 mood: Optional[str] = None) -> Dict[str, Any]:
    """Choose one track by mood, account DNA and content type, with reasons."""
    rows = [r for r in index.get("tracks") or [] if r.get("usable")]
    if not rows:
        return {"schema": SCHEMA, "state": "NO_LICENSED_TRACK", "selected": None,
                "reason": "no rights-cleared local track; output stays without BGM",
                "rejected": [{"asset_id": r.get("asset_id"), "reasons": r.get("reasons")}
                             for r in index.get("tracks") or []]}
    preferred: List[str] = []
    if mood:
        preferred.append(mood)
    preferred.extend(ACCOUNT_MOOD_PREFERENCE.get(account_slug, ()))
    preferred.extend(CONTENT_MOOD_PREFERENCE.get(content_type, ()))
    order = {name: i for i, name in enumerate(dict.fromkeys(preferred))}

    scored: List[Dict[str, Any]] = []
    for row in rows:
        moods = row.get("moods") or []
        hits = [(order[m], m) for m in moods if m in order]
        best = min(hits) if hits else (len(order) + 10, None)
        score = -float(best[0])
        if row.get("duration_s"):
            score += 0.5
        scored.append({"row": row, "score": score, "mood_match": best[1],
                       "reason": (f"mood {best[1]} matches {account_slug}/{content_type}"
                                  if best[1] else "no declared mood match; chosen last")})
    scored.sort(key=lambda item: -item["score"])
    winner = scored[0]
    return {
        "schema": SCHEMA, "state": "SELECTED", "selected": winner["row"],
        "selection_reason": winner["reason"],
        "rejected": [{"asset_id": s["row"].get("asset_id"),
                      "reason": s["reason"], "score": s["score"]}
                     for s in scored[1:]],
        "account_slug": account_slug, "content_type": content_type,
    }


def build_mix_plan(voice: AudioMeasurements, track: AudioMeasurements, *,
                   target_duration_s: float,
                   max_db_below_voice: float = DEFAULT_MAX_DB_BELOW_VOICE,
                   fade_in_s: float = 0.8, fade_out_s: float = 1.2,
                   true_peak_ceiling_db: float = DEFAULT_TRUE_PEAK_CEILING_DB,
                   track_asset_id: str = "") -> Dict[str, Any]:
    """Compute a loudness-derived gain and a voice-driven duck plan.

    Returns an ffmpeg filter description. It refuses to guess a gain when
    either side is unmeasured: a fixed percentage masquerading as a mix is
    exactly the failure this replaces.
    """
    if voice.integrated_lufs is None or track.integrated_lufs is None:
        return {
            "schema": SCHEMA, "state": "UNMEASURED_AUDIO",
            "reason": "integrated LUFS is missing for voice or music; "
                      "measure both before mixing (no fixed volume fallback)",
            "bgm_enabled": False,
        }
    voice_lufs = float(voice.integrated_lufs)
    track_lufs = float(track.integrated_lufs)
    target_lufs = voice_lufs - float(max_db_below_voice)
    gain_db = round(target_lufs - track_lufs, 2)

    checks: List[str] = []
    track_peak = track.true_peak_db if track.true_peak_db is not None else track.peak_db
    if track_peak is not None and track_peak + gain_db > true_peak_ceiling_db:
        clamped = round(true_peak_ceiling_db - track_peak, 2)
        checks.append(f"gain clamped {gain_db} -> {clamped} dB to respect "
                      f"{true_peak_ceiling_db} dBTP ceiling")
        gain_db = clamped
    else:
        checks.append("post-gain true peak stays within ceiling")
    if voice.true_peak_db is not None and voice.true_peak_db > -1.0:
        checks.append(f"voice true peak {voice.true_peak_db:.1f} dBTP needs review")

    # Duck depth follows the measured voice/music distance and the voice's own
    # dynamic range. A constant reduction would be a fixed percentage in disguise.
    loudness_gap = max(0.0, voice_lufs - track_lufs)
    voice_range = max(0.0, float(voice.loudness_range_lu or 0.0))
    duck_db = round(max(4.0, min(12.0, 4.0 + loudness_gap * 0.4 + voice_range * 0.2)), 2)
    threshold_db = round(voice_lufs - 6.0, 2)
    track_duration = track.duration_s or 0.0
    loop = track_duration > 0 and track_duration < target_duration_s - fade_out_s
    trim = max(0.0, target_duration_s - fade_in_s - fade_out_s)

    # A short track is looped at the *input* (-stream_loop -1), which works for
    # any sample rate; an in-filter aloop would need an exact sample count.
    filters = [
        f"[1:a]volume={gain_db}dB",
        f"atrim=0:{max(0.0, target_duration_s):.3f}",
        f"afade=t=in:st=0:d={fade_in_s:.3f}",
        f"afade=t=out:st={max(0.0, target_duration_s - fade_out_s):.3f}:d={fade_out_s:.3f}",
    ]
    music_chain = ",".join(filters) + "[music]"
    duck_chain = (
        f"[music][0:a]sidechaincompress=threshold={threshold_db}dB:ratio=4:"
        f"attack=20:release=400:makeup={duck_db}dB[ducked]"
    )
    mix_chain = "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[mixed]"
    return {
        "schema": SCHEMA, "state": "PLANNED", "bgm_enabled": True,
        "track_asset_id": track_asset_id,
        "voice_integrated_lufs": round(voice_lufs, 2),
        "track_integrated_lufs": round(track_lufs, 2),
        "target_track_lufs": round(target_lufs, 2),
        "gain_db": gain_db,
        "gain_basis": "measured voice LUFS minus max_db_below_voice minus measured track LUFS",
        "duck": {"threshold_db": threshold_db, "ratio": 4,
                 "attack_ms": 20, "release_ms": 400, "makeup_db": duck_db,
                 "key": "measured narration track",
                 "basis": "measured voice/music LUFS gap + measured voice loudness range"},
        "fades": {"fade_in_s": fade_in_s, "fade_out_s": fade_out_s},
        "input": {"stream_loop": -1 if loop else 0,
                  "note": "short tracks loop at input; long tracks are trimmed by atrim"},
        "duration": {"target_s": target_duration_s, "track_s": track_duration,
                     "loop": loop, "trim_s": round(trim, 3)},
        "loudness_checks": checks,
        "ffmpeg_filter_complex": ";".join((music_chain, duck_chain, mix_chain)),
        "note": "describes the mix for the existing composer; no audio is rendered here",
    }


def attribution_manifest(selection: Mapping[str, Any]) -> Dict[str, Any]:
    """Produce the credit list a published video needs, without inventing data."""
    chosen = selection.get("selected")
    if not chosen:
        return {"schema": f"{SCHEMA}/attribution", "state": "NO_BGM",
                "items": [], "credits_text": "No background music used."}
    item = {
        "asset_id": chosen.get("asset_id"),
        "title": chosen.get("path"),
        "author": chosen.get("author") or "unknown local author",
        "license_id": chosen.get("license_id") or "unrecorded",
        "source_url": chosen.get("source_url") or "",
        "sha256": chosen.get("sha256"),
    }
    parts = [f"Music: {item['title']} by {item['author']}"]
    if item["license_id"] != "unrecorded":
        parts.append(f"Licence: {item['license_id']}")
    if item["source_url"]:
        parts.append(f"Source: {item['source_url']}")
    return {"schema": f"{SCHEMA}/attribution", "state": "REQUIRED",
            "items": [item], "credits_text": " — ".join(parts),
            "human_review": "PENDING"}


def no_bgm_plan(reason: str) -> Dict[str, Any]:
    """Explicit, honest 'no music' outcome. Never downloads an unlicensed track."""
    return {"schema": SCHEMA, "state": "NO_BGM", "bgm_enabled": False,
            "reason": reason, "download_attempted": False,
            "attribution": attribution_manifest({})}
