#!/usr/bin/env python3
"""Render each video account's Easel profile from its DNA and active pin."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DNA_SCHEMA = "contentops.account-dna/v2"
PROFILE_SCHEMA = "contentops.easel-profile/v1"


def active_runtime_pin(root: Path = ROOT) -> str:
    """Return the human-readable identity represented by the central pin registry."""
    registry = json.loads((root / "runtime" / "easel-pins.json").read_text(encoding="utf-8"))
    active = registry.get("active")
    engine = (registry.get("engines") or {}).get(active)
    if not isinstance(engine, dict) or not engine.get("commit"):
        raise ValueError(f"active Easel pin {active!r} has no registered commit")
    return f"Easel {active} / {engine['commit'][:7]}"


def _yaml(value: Any, indent: int = 0) -> list[str]:
    """Serialize the small JSON-shaped YAML subset used by Easel profiles."""
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                first, *rest = _yaml(item, indent + 2)
                lines.append(f"{pad}- {first.lstrip()}")
                lines.extend(rest)
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return lines
    raise TypeError(f"unsupported YAML value {type(value).__name__}")


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./ -]+", text) and not text.startswith(("-", "?", "@", "`")):
        return text
    return json.dumps(text, ensure_ascii=False)


def _profile_data(dna: dict[str, Any], root: Path) -> dict[str, Any]:
    if dna.get("schema") != DNA_SCHEMA:
        raise ValueError(f"unsupported account schema {dna.get('schema')!r}; expected {DNA_SCHEMA!r}")
    slug = dna.get("slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError(f"invalid account slug {slug!r}")
    render = dna.get("render") or {}
    pin = active_runtime_pin(root)
    dna_pin = render.get("runtime_pin")
    if dna_pin != pin:
        raise ValueError(f"DNA runtime pin {dna_pin!r} does not match active pin {pin!r}")

    palette = (((dna.get("visual") or {}).get("motion") or {}).get("motion_profile") or {}).get("palette") or {}
    if not palette:
        palette = (dna.get("brand") or {}).get("palette") or {}
    captions = (dna.get("visual") or {}).get("caption_style") or {}
    safe_zone = captions.get("safe_zone") or {}
    canvas = render.get("canvas") or {}
    fonts = render.get("fonts") or {}
    audio = render.get("audio") or {}
    evidence = dna.get("evidence") or {}
    qc_checks = list(render.get("qc_checks") or [])
    cover = (dna.get("visual") or {}).get("cover") or {}
    composition = (dna.get("visual") or {}).get("composition") or {}

    qc: dict[str, Any] = {
        "checks": qc_checks,
        "cover_whitespace_min_ratio": cover.get("whitespace_min_ratio"),
        "cover_title_lines": cover.get("title_lines"),
    }
    source_floor = next(
        (int(match.group(1)) / 100 for check in qc_checks
         if (match := re.fullmatch(r"real_source_ratio_min_(\d{1,3})", str(check)))),
        None,
    )
    if source_floor is not None:
        qc["real_source_ratio_min"] = source_floor

    profile = {
        "schema": PROFILE_SCHEMA,
        "generated_from": f"config/accounts/{slug}.json",
        "generated_note": "Generated from the account DNA. Edit the DNA, not this file.",
        "account": dna.get("account"),
        "slug": slug,
        "role": dna.get("role"),
        "canvas": {
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "orientation": canvas.get("orientation"),
            "fps": render.get("fps"),
        },
        "fonts": fonts,
        "colors": {
            "base": palette.get("bg", palette.get("base")),
            "accent": palette.get("accent"),
            "ink": palette.get("ink"),
            "muted": palette.get("sub", palette.get("muted")),
            "surface": palette.get("surface"),
            "problem": (dna.get("brand", {}).get("palette", {}) or {}).get("problem"),
            "code_theme": (dna.get("brand", {}).get("palette", {}) or {}).get("code_theme"),
        },
        "captions": {
            "font": captions.get("font"),
            "size_px": captions.get("size_px"),
            "max_chars_per_line": captions.get("max_chars_per_line"),
            "density": captions.get("density"),
            "highlight": captions.get("highlight"),
            "outline": captions.get("outline"),
            "shadow": captions.get("shadow"),
            "burn_style": captions.get("burn_style"),
            "safe_zone": {
                "margin_v_px": safe_zone.get("margin_v_px"),
                "side_margin_ratio": safe_zone.get("side_margin_ratio"),
            },
        },
        "audio": {
            "voice_provider": audio.get("voice_provider"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
            "bgm": audio.get("bgm"),
            "bgm_max_db_below_voice": (dna.get("audio", {}).get("bgm", {}) or {}).get("max_db_below_voice"),
        },
        "composition": {
            "basis": composition.get("basis"),
            "segments": composition.get("segments") or [],
        },
        "qc": qc,
        "evidence": {
            "mode": evidence.get("mode"),
            "manual_recording": evidence.get("manual_recording"),
            "required_evidence_class": evidence.get("required_evidence_class"),
        },
        "engine": render.get("engine"),
        "runtime_pin": pin,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    return profile


def render_easel_yaml(dna: dict[str, Any], root: Path = ROOT) -> str:
    """Return the complete deterministic YAML projection of one account DNA."""
    return "# Generated by scripts/export_easel_yaml.py from the account DNA.\n" \
           "# Do not edit by hand: the DNA is the source of truth.\n" \
           + "\n".join(_yaml(_profile_data(dna, root))) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", help="Account slug or path to its JSON DNA")
    args = parser.parse_args()
    candidate = Path(args.account)
    dna_path = candidate if candidate.is_file() else ROOT / "config" / "accounts" / f"{args.account}.json"
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    output = ROOT / "projects" / dna["slug"] / "easel.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_easel_yaml(dna, ROOT), encoding="utf-8", newline="\n")
    print(f"Wrote {output.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
