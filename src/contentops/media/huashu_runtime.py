"""Locate a verified local Huashu Art Motion skill installation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def runtime_candidates(repo_root: Path, environ: Mapping[str, str] | None = None,
                       home: Path | None = None) -> list[Path]:
    """Return ordered runtime locations without binding the repo to one machine."""
    env = os.environ if environ is None else environ
    configured = str(env.get("HUASHU_ART_MOTION_ROOT") or "").strip()
    if configured:
        return [Path(configured).expanduser()]

    user_home = (home or Path.home()).expanduser()
    candidates = [
        repo_root / ".runtime" / "huashu-art-motion",
        user_home / ".agents" / "skills" / "huashu-art-motion",
        user_home / ".codex" / "skills" / "huashu-art-motion",
        user_home / ".claude" / "skills" / "huashu-art-motion",
    ]
    # Preserve order while avoiding repeated paths (common on Windows).
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate.resolve(strict=False)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def find_runtime(repo_root: Path, environ: Mapping[str, str] | None = None,
                 home: Path | None = None) -> Path:
    """Find a skill root containing its skill metadata and renderer."""
    candidates = runtime_candidates(repo_root, environ=environ, home=home)
    for candidate in candidates:
        if ((candidate / "SKILL.md").is_file()
                and (candidate / "scripts" / "engine" / "render.py").is_file()):
            return candidate
    configured = bool((environ or os.environ).get("HUASHU_ART_MOTION_ROOT"))
    detail = "configured HUASHU_ART_MOTION_ROOT is invalid" if configured else "no supported local installation found"
    raise FileNotFoundError(detail + "; searched: " + ", ".join(map(str, candidates)))
