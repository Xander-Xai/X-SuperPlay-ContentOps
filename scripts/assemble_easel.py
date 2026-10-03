#!/usr/bin/env python3
"""Run upstream Easel's assemble.py for a project, working around its Windows
subtitle-path bug WITHOUT modifying upstream.

Upstream `auto-short-video/scripts/assemble.py` escapes the subtitle path like:

    escaped = str(ass_path).replace("'", "\\\\'").replace(":", "\\\\:")
    _run(["ffmpeg", ..., "-vf", f"subtitles='{escaped}'", ...])

That escapes the drive-letter colon but leaves Windows path separators bare.
ffmpeg's filter parser then eats the backslashes, so
`D:\\Temp\\tmp123\\sub.ass` arrives as `D:Temptmp123sub.ass` and the subtitles
filter aborts:

    [Parsed_subtitles_0] Unable to open D:Temptmp0kbmkti2sub.ass
    [AVFilterGraph] Error initializing filters

Strategy (orchestration only, upstream file untouched):
  1. Run upstream assemble.py with the subtitle field REMOVED from a temp copy
     of the storyboard. Everything upstream does — per-shot composition, padding,
     concat, narration/BGM mixing — runs on the real upstream code path.
  2. Burn the subtitles ourselves in one extra ffmpeg pass, using forward slashes
     plus an escaped colon (the form proven to work in
     projects/easel-review/receipts/runtime-receipt.md).

The recipe mirrors upstream's own subtitle styling knobs (--sub-font / --sub-size
/ --sub-margin-v default to the same values upstream would have used).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SUB_FONT = "Noto Sans CJK SC"


def _upstream_assemble() -> Path:
    """The pinned runtime's assemble.py, via the shared resolver (offline mode:
    recorded provenance; doctor.py re-verifies live). Never an unpinned tree."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resolve_easel import resolve_easel
    res = resolve_easel(live=False)
    if res["status"] != "OK":
        raise RuntimeError("Easel runtime not usable: "
                           + "; ".join(res.get("reasons", ["unknown"])))
    return Path(res["easel_dir"]) / "skills" / "openclaw" / "auto-short-video" / "scripts" / "assemble.py"


def _subtitle_vf(ass_path: Path) -> str:
    # Forward slashes survive ffmpeg's filter parser; the drive colon must be escaped.
    posix = ass_path.resolve().as_posix()
    return f"subtitles=filename='{posix.replace(':', chr(92) + ':')}'"


def _ms(stamp: str) -> int:
    stamp = stamp.replace(",", ".")
    h, m, s = stamp.split(":")
    return int(h) * 3600000 + int(m) * 60000 + int(float(s) * 1000)


def _wrap(text: str, width_px: int, font_size: int) -> str:
    """Break a cue into lines of at most width_px, joined with ASS \\N.

    Measured advance widths (libass, CJK face): a full-width glyph advances
    ~font_size px, a latin glyph ~font_size/2 px (ratio 2.02:1 measured at 54).
    """
    cjk_px = font_size
    lat_px = font_size / 2.0

    def px(s: str) -> float:
        return sum(cjk_px if ord(c) > 0x2E80 else lat_px for c in s)

    lines, cur, cur_px = [], "", 0.0
    for ch in text:
        wpx = cjk_px if ord(ch) > 0x2E80 else lat_px
        if cur and cur_px + wpx > width_px:
            lines.append(cur)
            cur, cur_px = "", 0.0
        cur += ch
        cur_px += wpx
    if cur:
        lines.append(cur)
    return lines


def _fit(text: str, width_px: int, font_size: int, max_lines: int = 2) -> tuple[int, str]:
    """Shrink the font until the cue fits in max_lines. Returns (size, body).

    Uses an inline ASS override so each cue can carry its own size; the style's
    default stays at font_size.
    """
    size = font_size
    floor = max(22, int(font_size * 0.6))
    while size >= floor:
        lines = _wrap(text, width_px, size)
        if len(lines) <= max_lines:
            return size, "\\N".join(lines)
        size -= 2
    lines = _wrap(text, width_px, floor)
    return floor, "\\N".join(lines[:max_lines])


def _srt_to_ass(srt_path: Path, ass_path: Path, w: int, h: int,
                font: str, font_size: int, margin_v: int) -> None:
    """Mirror upstream _srt_to_ass styling (bottom-centre, wrapped at 2 lines)."""
    def ts(ms: int) -> str:
        h_, rem = divmod(ms, 3600000)
        m_, rem = divmod(rem, 60000)
        s_, ms_ = divmod(rem, 1000)
        return f"{h_}:{m_:02d}:{s_:02d}.{ms_:02d}"

    cues = []
    blocks = srt_path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        if len(lines) >= 2 and "-->" in lines[1]:
            idx = lines[0]
            start, _, end = lines[1].partition("-->")
            text = " ".join(lines[2:])
            cues.append((ts(_ms(start.strip())), ts(_ms(end.strip())), text))

    # edge-tts emits cues that can overlap by a few hundred ms; clamp so two
    # lines never render stacked on top of each other.
    fixed = []
    for i, (s, e, t) in enumerate(cues):
        start, end = _ms(s), _ms(e)
        if fixed and start < _ms(fixed[-1][1]):
            start = _ms(fixed[-1][1])
        if end <= start:
            end = start + 600
        fixed.append((ts(start), ts(end), t))

    # WrapStyle 2 disables libass auto-wrap, so the wrap width is fully
    # determined here: 86% of frame width leaves a clear side margin.
    width_px = int(w * 0.86)
    body = ""
    for s, e, t in fixed:
        size, text = _fit(t, width_px, font_size)
        override = "" if size == font_size else f"{{\\fs{size}}}"
        body += f"Dialogue: 0,{s},{e},D,,0,0,0,,{override}{text}\n"

    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "ScaledBorderAndShadow: yes\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: D,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,0,0,0,0,100,100,0,0,1,{max(2, font_size // 12)},0,2,"
        f"0,0,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    ass_path.write_text(head + body, encoding="utf-8")


def run(project: Path, out_name: str = "easel") -> dict:
    project = project.resolve()
    storyboard = project / "script" / "storyboard.json"
    if not storyboard.exists():
        return {"status": "BLOCKED", "reason": f"storyboard missing: {storyboard}"}
    try:
        upstream_assemble = _upstream_assemble()
    except RuntimeError as e:
        return {"status": "BLOCKED", "reason": str(e)}

    sb = json.loads(storyboard.read_text(encoding="utf-8"))
    sub_rel = sb.get("subtitle")
    size = sb.get("size", "1080x1920")
    w, h = (int(x) for x in size.split("x"))

    # Upstream requires the output to live under outputs/<topic>/; keep it there,
    # then copy into the project so the project owns its deliverable.
    # assemble.py is <easel>/skills/openclaw/auto-short-video/scripts/assemble.py
    easel_dir = upstream_assemble.parents[4]
    topic_out = easel_dir / "outputs" / project.name
    topic_out.mkdir(parents=True, exist_ok=True)
    upstream_out = topic_out / "final.mp4"

    with tempfile.TemporaryDirectory() as td:
        tmp_sb = Path(td) / "storyboard.json"
        # Strip BOTH the explicit subtitle and the per-shot captions: upstream
        # falls back to auto-generating a subtitle from `caption`
        # (assemble.py: `elif any(s.get("caption")...)`), which would re-enter the
        # same broken burn. We do that step ourselves, correctly, below.
        no_sub = dict(sb)
        no_sub.pop("subtitle", None)
        no_sub["shots"] = [
            {k: v for k, v in shot.items() if k != "caption"}
            for shot in no_sub.get("shots", [])
        ]
        tmp_sb.write_text(json.dumps(no_sub, ensure_ascii=False), encoding="utf-8")

        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [sys.executable, str(upstream_assemble), "assemble",
             "--storyboard", str(tmp_sb), "-o", str(upstream_out)],
            cwd=str(ROOT), capture_output=True, encoding="utf-8",
            errors="replace", env=env, timeout=1800,
        )
        if proc.returncode != 0 or not upstream_out.exists():
            return {"status": "BLOCKED", "stage": "upstream_assemble",
                    "reason": (proc.stderr or proc.stdout or "")[-800:]}

        final_dir = project / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = final_dir / f"{out_name}.mp4"

        if not sub_rel:
            out_mp4.write_bytes(upstream_out.read_bytes())
            return {"status": "OK", "video": str(out_mp4), "subtitles_burned": False,
                    "upstream": str(upstream_assemble)}

        # --- our one extra pass: burn subtitles (upstream's step that breaks on Windows)
        raw = Path(sub_rel)
        candidates = [raw] if raw.is_absolute() else [project / raw, ROOT / raw]
        sub_path = next((c for c in candidates if c.is_file()), None)
        if sub_path is None:
            return {"status": "BLOCKED", "reason": f"subtitle not found: {sub_rel}"}

        ass_path = Path(td) / "sub.ass"
        _srt_to_ass(sub_path, ass_path, w, h, DEFAULT_SUB_FONT,
                    int(w * 0.05), int(h * 0.07))

        burn = subprocess.run(
            ["ffmpeg", "-y", "-i", str(upstream_out),
             "-vf", _subtitle_vf(ass_path), "-c:a", "copy", str(out_mp4)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=900,
        )
        if burn.returncode != 0 or not out_mp4.exists():
            return {"status": "BLOCKED", "stage": "subtitle_burn",
                    "reason": (burn.stderr or "")[-800:]}

    return {
        "status": "OK",
        "video": str(out_mp4),
        "subtitles_burned": True,
        "upstream": str(upstream_assemble),
        "upstream_intermediate": str(upstream_out),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--out-name", default="easel", help="final/<name>.mp4")
    args = p.parse_args()
    proj = Path(args.project)
    if not proj.is_absolute():
        proj = (ROOT / args.project).resolve()
    res = run(proj, out_name=args.out_name)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("status") == "OK" else 4


if __name__ == "__main__":
    sys.exit(main())
