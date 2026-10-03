"""Generate 4 placeholder 'real evidence' PNGs for the Easel smoke test.

These stand in for screenshots the user would normally drop in. They are
generated locally via ffmpeg (not AI), labeled with real Easel terminology,
and serve as `real_assets_first` evidence per the V1 policy.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

OUT = ROOT / "projects" / "easel-review" / "sources" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920
FONT = "C\\:/Windows/Fonts/msyh.ttc"

SHOTS = [
    ("01-easel-hero.png", "ZJU-REAL / Easel", "AI 自媒体工作流"),
    ("02-easel-features.png", "Discover Plan Produce Publish", "Attribute"),
    ("03-easel-architecture.png", "WebUI  CLI  Gateway  OpenClaw", "v0.2.1"),
    ("04-easel-skills.png", "video-script video-production", "quality-gate"),
]


def make_one(path: Path, line1: str, line2: str) -> bool:
    def esc(s: str) -> str:
        return (
            s.replace("\\", "\\\\")
              .replace(":", r"\:")
              .replace("'", r"\'")
              .replace("%", r"\%")
        )
    vf = (
        f"drawtext=fontfile='{FONT}':text='{esc(line1)}':"
        f"fontcolor=white:fontsize=78:x=(w-text_w)/2:y=(h-text_h)/2-90:"
        f"box=1:boxcolor=0x1f2937@0.6:boxborderw=40,"
        f"drawtext=fontfile='{FONT}':text='{esc(line2)}':"
        f"fontcolor=#93c5fd:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2+60:"
        f"box=1:boxcolor=0x111827@0.6:boxborderw=30"
    )
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x101828:s={W}x{H}:d=1",
        "-vf", vf,
        "-frames:v", "1", str(path),
    ]
    res = hidden_run(cmd, timeout=60)
    return res.returncode == 0 and path.exists() and path.stat().st_size > 0


def main() -> int:
    ok = True
    for name, l1, l2 in SHOTS:
        p = OUT / name
        if make_one(p, l1, l2):
            print(f"[ok] {name}  ({p.stat().st_size} bytes)")
        else:
            print(f"[FAIL] {name}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())