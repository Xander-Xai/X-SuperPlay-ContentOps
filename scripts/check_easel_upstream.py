#!/usr/bin/env python3
"""Easel upstream compatibility watch script.

Compares the pinned Easel release in runtime/easel.lock.json against:
  1. The latest stable release on ZJU-REAL/Easel
  2. The latest commit on Easel main

Classifies upstream changes by impact on ContentOps integration areas.
Outputs a JSON report. Never modifies the lock file or opens PRs.

This script is READ-ONLY. It DETECTS, CLASSIFIES, and REPORTS.
It does NOT ADOPT or UPGRADE.

Stdlib only. Uses urllib for GitHub API (no external dependency).
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EASEL_REPO = "ZJU-REAL/Easel"
API_BASE = "https://api.github.com/repos"

WATCHED_PATHS = {
    "runtime": ["easel/", "commands/", "scripts/"],
    "video": ["skills/shared/", "video", "assemble"],
    "speech": ["speech", "tts"],
    "provider": ["model_registry", "provider", "publish"],
    "windows": ["setup.ps1", "setup.sh", "subprocess", "encoding", "utf-8", "windows"],
    "security": ["security", "auth", "token", "secret"],
    "publishing": ["publish", "upload"],
    "docs_only": ["README", "CHANGELOG", "docs/"],
}


def _api_get(path):
    url = f"{API_BASE}/{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "X-SuperPlay-ContentOps-upstream-watch",
    })
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_message": e.reason}
    except Exception as e:
        return {"_error": str(e)}


def load_pin():
    lock_path = ROOT / "runtime" / "easel.lock.json"
    if not lock_path.exists():
        return {"_error": "lock file missing"}
    return json.loads(lock_path.read_text(encoding="utf-8"))


def get_latest_release():
    data = _api_get(f"{EASEL_REPO}/releases/latest")
    if "_error" in data:
        return data
    tag = data.get("tag_name", "unknown")
    tag_data = _api_get(f"{EASEL_REPO}/git/refs/tags/{tag}")
    commit = ""
    if "object" in tag_data:
        if tag_data["object"].get("type") == "commit":
            commit = tag_data["object"].get("sha", "")
        else:
            sha = tag_data["object"].get("sha", "")
            if sha:
                tag_obj = _api_get(f"{EASEL_REPO}/git/tags/{sha}")
                commit = tag_obj.get("object", {}).get("sha", "")
    return {
        "tag": tag,
        "commit": commit,
        "published": data.get("published_at", ""),
    }


def get_main_commit():
    data = _api_get(f"{EASEL_REPO}/commits/main")
    if "_error" in data:
        return data
    msg = data.get("commit", {}).get("message", "")
    first_line = msg.split("\n")[0] if msg else ""
    return {
        "commit": data.get("sha", ""),
        "date": data.get("commit", {}).get("committer", {}).get("date", ""),
        "message": first_line,
    }


def get_commit_list(since, until, per_page=100):
    data = _api_get(f"{EASEL_REPO}/compare/{since}...{until}?per_page={per_page}")
    if "_error" in data:
        return []
    return data.get("commits", [])


def get_commit_files(sha):
    """Get changed file paths for a specific commit."""
    data = _api_get(f"{EASEL_REPO}/commits/{sha}")
    if "_error" in data:
        return []
    return [f.get("filename", "") for f in data.get("files", [])]


def classify_commit(message, files=None):
    """Classify a commit impact based on message AND changed file paths.

    Even if the message is generic (e.g. 'fix #123'), changed files
    in watched paths still trigger the correct impact classification.
    """
    msg_lower = message.lower()
    files_lower = [str(f).lower() for f in (files or [])]
    impacts = []
    for area, keywords in WATCHED_PATHS.items():
        for kw in keywords:
            kw_lower = kw.lower()
            # Match keyword in commit message OR in changed file path
            if kw_lower in msg_lower or any(kw_lower in f for f in files_lower):
                if area not in impacts:
                    impacts.append(area)
                break
    if not impacts:
        impacts.append("docs_only")
    return impacts


def determine_impact_level(areas, is_new_release, has_api_error=False):
    if has_api_error:
        return "UNKNOWN"
    if is_new_release:
        return "HIGH"
    high_areas = {"security"}
    medium_areas = {"windows", "speech", "video", "provider", "runtime"}
    if any(a in high_areas for a in areas):
        return "HIGH"
    if any(a in medium_areas for a in areas):
        return "MEDIUM"
    if "docs_only" in areas and len(areas) == 1:
        return "NONE"
    return "LOW"


def main():
    p = argparse.ArgumentParser(description="Easel upstream compatibility watch")
    p.add_argument("--quiet", action="store_true", help="Exit code only")
    args = p.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    pin = load_pin()
    latest_release = get_latest_release()
    upstream_main = get_main_commit()

    # Detect API errors and propagate as warning in report
    has_api_error = False
    if "_error" in latest_release:
        has_api_error = True
    if "_error" in upstream_main:
        has_api_error = True

    pinned_tag = pin.get("tag", "unknown")
    pinned_commit = pin.get("commit", "")
    release_tag = latest_release.get("tag", "unknown")
    release_commit = latest_release.get("commit", "")
    main_commit = upstream_main.get("commit", "")

    release_update = release_tag != pinned_tag and release_tag != "unknown"

    ahead = 0
    impact_areas = []
    if pinned_commit and main_commit and pinned_commit != main_commit and not has_api_error:
        commits = get_commit_list(pinned_commit, main_commit)
        ahead = len(commits)
        for c in commits:
            sha = c.get("sha", "")
            msg = c.get("commit", {}).get("message", "")
            # Fetch changed files for accurate classification (B2 fix)
            files = get_commit_files(sha) if sha else []
            areas = classify_commit(msg, files)
            for a in areas:
                if a not in impact_areas:
                    impact_areas.append(a)

    if not impact_areas:
        impact_areas = ["docs_only"]

    impact_level = determine_impact_level(impact_areas, release_update, has_api_error)

    if has_api_error:
        recommendation = "API_ERROR"
    elif release_update:
        recommendation = "EVALUATE_NEW_RELEASE"
    elif impact_level in ("MEDIUM", "HIGH"):
        recommendation = "WATCH"
    else:
        recommendation = "NO_ACTION"

    report = {
        "checked_at": now,
        "pinned": {"tag": pinned_tag, "commit": pinned_commit},
        "latest_release": {
            "tag": release_tag,
            "commit": release_commit,
            "published": latest_release.get("published", ""),
            "_error": latest_release.get("_error"),
        },
        "upstream_main": {
            "commit": main_commit,
            "date": upstream_main.get("date", ""),
            "message": upstream_main.get("message", ""),
            "_error": upstream_main.get("_error"),
        },
        "ahead_from_pinned": ahead,
        "release_update_available": release_update,
        "api_error": has_api_error,
        "impact": {"areas": impact_areas, "level": impact_level},
        "recommendation": recommendation,
    }

    if args.quiet:
        sys.exit(0 if recommendation in ("NO_ACTION", "API_ERROR") else 1)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())