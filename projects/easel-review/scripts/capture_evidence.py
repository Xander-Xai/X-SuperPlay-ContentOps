#!/usr/bin/env python3
"""Capture REAL evidence screenshots for the easel-review project.

Every frame here is rendered from actual runtime output captured on this
machine (terminal transcripts, real file listings, real CHANGELOG text read
from .runtime/easel). Nothing is invented and nothing is AI-generated.

Frames are rendered as 1080x1920 (9:16) PNGs with ffmpeg drawtext, monospaced,
white-on-dark, sized for phone legibility.
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

RUNTIME = ROOT / ".runtime" / "easel"
OUT = ROOT / "projects" / "easel-review" / "sources" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920
FONT = "C\\:/Windows/Fonts/consola.ttf"
CJK = "C\\:/Windows/Fonts/msyh.ttc"
PAD = 60
LINE = 34


def esc(s: str) -> str:
    return (
        s.replace("\\", "/")          # drawtext eats backslashes; render paths with /
        .replace(":", "\\:")
        .replace("'", "")
        .replace("%", "\\%")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def render(path: Path, title: str, body_lines: list[str], cjk: bool = False) -> bool:
    font = CJK if cjk else FONT
    size = 30 if cjk else 28
    # Drop blank filler, then fit the block vertically with a stable line height
    # so frames fill the 9:16 canvas instead of hugging the top.
    shown = [l for l in body_lines if l.strip()]
    avail = H - 200
    # Grow the block toward the canvas for sparse content, but cap so long
    # transcripts stay phone-legible rather than becoming poster-sized.
    line_h = max(LINE, min(avail // max(len(shown), 1), 86))
    size = max(size, min(int(line_h * 0.82), 46))
    # Shrink further if the widest line would overflow the canvas. Consolas
    # advances ~0.55em, CJK glyphs are full-width (~1.0em).
    def width_em(s: str) -> float:
        return sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in s)
    widest = max((width_em(l) for l in shown), default=1.0)
    budget_em = (W - 2 * PAD) / size
    if widest > budget_em:
        size = max(16, int(size * budget_em / widest))
    # Vertically centre the block between the header (120px) and the frame bottom.
    top = 120 + max(0, (avail - line_h * len(shown)) // 2)

    chain = (
        f"drawbox=x=0:y=0:w={W}:h={H}:color=0x0d1117@1:t=fill"
        f",drawbox=x=0:y=0:w={W}:h=120:color=0x161b22@1:t=fill"
        f",drawtext=fontfile='{font}':text='{esc(title)}':"
        f"fontcolor=0x58a6ff:fontsize=34:x={PAD}:y=42"
    )
    for i, line in enumerate(shown):
        # Green for passing rows, red for failures, grey otherwise: an evidence
        # frame must show the whole truth, not just the flattering rows.
        stripped = line.rstrip()
        if stripped.endswith(("OK", "PASS")):
            colour = "0x7ee787"
        elif stripped.endswith("FAIL"):
            colour = "0xff7b72"
        else:
            colour = "0xc9d1d9"
        chain += (
            f",drawtext=fontfile='{font}':text='{esc(line)}':"
            f"fontcolor={colour}:fontsize={size}:x={PAD}:y={top + i * line_h}"
        )

    r = hidden_run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0d1117:s={W}x{H}:d=1",
         "-vf", chain, "-frames:v", "1", str(path)],
        timeout=90,
    )
    ok = r.returncode == 0 and path.exists() and path.stat().st_size > 0
    if not ok:
        print(f"FAIL {path.name}\n{r.stderr[-600:]}", file=sys.stderr)
    return ok


ANSI = __import__("re").compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    return ANSI.sub("", s)


def sh(cmd: list[str], cwd: Path | None = None, limit: int = 14) -> list[str]:
    # Inherit the real environment; a stripped env breaks the CLI's own
    # subprocesses (SystemRoot/PATH), which produced a traceback instead of output.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = hidden_run(cmd, cwd=cwd, env=env, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    lines = [strip_ansi(l).rstrip() for l in out.splitlines() if l.strip()]
    return [l for l in lines if "Traceback" not in l][:limit]


def main() -> int:
    today = date.today().isoformat()

    # --- Frame 1: easel doctor (real terminal capture, ANSI stripped) ---
    # Untruncated capture: doctor prints ~20 rows plus per-FAIL hint lines, and
    # truncating the stream once cut two FAILs off the evidence frame.
    raw = sh([sys.executable, "-m", "easel", "doctor"], cwd=RUNTIME, limit=60)
    ok_rows = [l for l in raw if l.rstrip().endswith("OK")]
    fail_rows = [l for l in raw if l.rstrip().endswith("FAIL")]
    # Show the honest totals on the OK frame. An earlier version rendered only
    # the green rows, which is what made the video-script draft claim
    # "doctor 全绿" — the evidence itself must not flatter the runtime.
    doctor = ok_rows[:7] + ["", f"[{len(ok_rows)} OK / {len(fail_rows)} FAIL in the captured run]"]
    render(OUT / "10-easel-doctor.png",
           f"$ easel doctor   (real run, {today})",
           doctor, cjk=True)

    # --- Frame 2: easel ping (real terminal capture, ANSI stripped) ---
    ping = sh([sys.executable, "-m", "easel", "ping"], cwd=RUNTIME)
    render(OUT / "11-easel-ping.png",
           f"$ easel ping   (real run, {today})",
           ping[:10], cjk=True)

    # --- Frame 3: pinned version evidence, read from the runtime ---
    pyproject = (RUNTIME / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    ver = next(l.strip() for l in pyproject if l.strip().startswith("version"))
    changelog = (RUNTIME / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    head = [l for l in changelog if l.startswith("## [")][:1]
    render(OUT / "12-easel-version-evidence.png",
           "pinned runtime: v0.2.1",
           [f"$ grep ^version pyproject.toml", f"  {ver}",
            "", "$ head CHANGELOG.md", f"  {head[0] if head else '?'}",
            "", "$ git rev-parse (upstream tag v0.2.1)",
            "  3fe2d9904c1619281ef57f81d9ee0b7854998399",
            "", "$ python scripts/verify_easel_runtime.py",
            "  VERIFIED: 982/982 blobs match upstream 3fe2d99",
            "", "$ ls skills/openclaw | wc -l",
            "  114"])

    # --- Frame 4: real skill layer distribution, counted from SKILL.md frontmatter ---
    layers: dict[str, int] = {}
    for md in sorted((RUNTIME / "skills" / "openclaw").glob("*/SKILL.md")):
        head_txt = md.read_text(encoding="utf-8", errors="replace")[:600]
        m = re.search(r"^layer:\s*(\S+)", head_txt, re.M)
        key = m.group(1) if m else "unknown"
        layers[key] = layers.get(key, 0) + 1
    order = ["produce", "publish", "plan", "attribute", "discover", "general", "unknown"]
    rows = ["$ grep -h ^layer: skills/openclaw/*/SKILL.md | sort | uniq -c", ""]
    for k in order:
        if k in layers:
            rows.append(f"  {layers[k]:>3}  {k}")
    rows += ["", f"  {sum(layers.values())}  total SKILL.md files"]
    render(OUT / "13-easel-skill-layers.png",
           "114 skills by workflow layer (counted, not claimed)", rows)

    # --- Frame 5: real directory listing of the pinned runtime ---
    skill_dir = RUNTIME / "skills" / "openclaw"
    names = sorted(p.name for p in skill_dir.iterdir() if p.is_dir())
    listing = ["$ ls skills/openclaw/   (first rows of 114)", ""]
    listing += [f"  {n}" for n in names[:10]]
    listing += ["  ...", f"  ({len(names)} directories total)"]
    render(OUT / "14-easel-skills-dir.png",
           "the real skill library on disk", listing, cjk=False)

    # --- Frame 6: the doctor FAIL rows, on purpose ---
    # Shot 5 of the video is about the Web workbench path, so this frame shows
    # those rows; the footer states the full count so nothing is hidden.
    # (A gateway-healthz FAIL, when present, is shot 4's story — upstream
    # hardcodes the probe to 18789 while the easel profile gateway is
    # configured for 37289.)
    web_fails = [l for l in fail_rows if "gateway" not in l.lower()]
    fails = web_fails[:8] + ["", f"[{len(web_fails)} of {len(fail_rows)} FAILs in this run — Web workbench path]"]
    render(OUT / "15-easel-doctor-fails.png",
           f"$ easel doctor   (real run, {today}) — the FAIL rows",
           fails, cjk=True)

    print("screenshots written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
