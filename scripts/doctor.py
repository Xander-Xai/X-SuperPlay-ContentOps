# This is a V1 video ContentOps runtime for the X-SuperPlay accounts.
#
# Pipeline:
#   Source -> Script -> Storyboard -> Voice -> Subtitle -> Compose -> QC -> final.mp4
#
# Easel is the pinned upstream runtime. Do not edit it. Do not commit .runtime/.
#
# See AGENTS.md for the full operating rules.

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
GIT_MIN_VERSION = (2, 30)


def _red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m"


def _green(msg: str) -> str:
    return f"\033[32m{msg}\033[0m"


def _yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m"


def _cyan(msg: str) -> str:
    return f"\033[36m{msg}\033[0m"


def _check_tool(name: str, version_args: list[str], min_version: tuple = None) -> dict:
    path = shutil.which(name)
    if not path:
        return {"name": name, "ok": False, "reason": "not found in PATH"}
    try:
        out = subprocess.run(
            [name, *version_args],
            capture_output=True,
            text=True,
            timeout=15,
        )
        version_str = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else "?"
    except Exception as e:
        return {"name": name, "ok": False, "path": path, "reason": str(e)}

    ok = True
    if min_version:
        try:
            tokens = version_str.replace(",", " ").split()
            ver = None
            for tok in tokens:
                if tok[0].isdigit():
                    ver = tuple(int(x) for x in tok.split(".") if x.isdigit())
                    break
            if ver and ver < min_version:
                ok = False
        except Exception:
            pass

    return {
        "name": name,
        "ok": ok,
        "path": path,
        "version": version_str,
    }


def _check_python() -> dict:
    import sys as _s
    return {
        "name": "python",
        "ok": _s.version_info >= (3, 10),
        "path": _s.executable,
        "version": f"{_s.version_info.major}.{_s.version_info.minor}.{_s.version_info.micro}",
        "required": ">=3.10",
    }


def _check_node() -> dict:
    out = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
    ver_str = (out.stdout or out.stderr).strip().lstrip("v")
    try:
        major = int(ver_str.split(".")[0])
        ok = major >= 22
    except Exception:
        ok = False
    return {
        "name": "node",
        "ok": ok,
        "path": shutil.which("node"),
        "version": ver_str,
        "required": ">=22.19",
    }


def _check_ffmpeg() -> dict:
    return _check_tool("ffmpeg", ["-version"])


def _check_ffprobe() -> dict:
    return _check_tool("ffprobe", ["-version"])


def _check_easel_checkout() -> dict:
    """Verify the pinned Easel runtime via the shared resolver.

    Accepts either a git checkout whose HEAD is the pinned commit, or a
    release archive whose content matches the upstream tree (verified live
    here; run with --offline elsewhere to use recorded provenance). A
    directory whose remote is not ZJU-REAL/Easel is rejected, never treated
    as Easel (AGENTS.md §1.6 / V1 spec §3).
    """
    import resolve_easel as rez
    pin = rez.load_pin()
    res = rez.resolve_easel(live=True)
    if res["status"] == "OK":
        out = {
            "name": "easel_checkout", "ok": True,
            "path": res["easel_dir"], "release": pin["tag"],
            "expected_commit": pin["commit"],
            "acquisition": res["acquisition"],
            "verification": res["verification"],
        }
        for k in ("verified_blobs", "verified_at", "note"):
            if k in res:
                out[k] = res[k]
        return out
    return {
        "name": "easel_checkout", "ok": False,
        "release": pin["tag"], "expected_commit": pin["commit"],
        "reason": "; ".join(res.get("reasons", ["unresolved"])),
        "remedy": res.get("remedy"),
    }


def _check_repo_layout() -> dict:
    required = [
        ROOT / "scripts",
        ROOT / "templates",
        ROOT / "projects",
        ROOT / "outputs",
        ROOT / "runtime",
        ROOT / "docs",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    return {
        "name": "repo_layout",
        "ok": not missing,
        "missing": missing,
    }


def run(json_output: bool = False) -> int:
    checks = [
        _check_python(),
        _check_node(),
        _check_ffmpeg(),
        _check_ffprobe(),
        _check_tool("git", ["--version"]),
        _check_easel_checkout(),
        _check_repo_layout(),
    ]

    overall_ok = all(c.get("ok") for c in checks)

    if json_output:
        print(json.dumps({"ok": overall_ok, "checks": checks}, indent=2))
    else:
        print(_cyan("=== X-SuperPlay-ContentOps doctor ==="))
        for c in checks:
            mark = _green("OK ") if c.get("ok") else _red("FAIL")
            print(f"[{mark}] {c.get('name')}")
            for k, v in c.items():
                if k in ("name", "ok"):
                    continue
                print(f"        {k}: {v}")
        print()
        if overall_ok:
            print(_green("All checks passed."))
        else:
            print(_red("Some checks failed. See above."))

    return 0 if overall_ok else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    sys.exit(run(json_output=args.json))


if __name__ == "__main__":
    main()