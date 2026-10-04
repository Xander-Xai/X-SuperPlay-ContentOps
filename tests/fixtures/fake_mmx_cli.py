#!/usr/bin/env python3
"""Local stand-in for the official MiniMax CLI, used by tests only.

It exists so the whole speech pipeline — billing gate, cache, normalisation, QC,
fingerprint, receipt — can be exercised end to end **without a provider request
and without spending quota**. It writes a locally synthesised tone instead of
real narration, so no test can accidentally assert something about voice quality.

Supported argv shapes:
    --version
    config show --output json
    speech synthesize ... --out <path> [--text <t>] ...
    speech transcribe --file <path> --output json
    image generate ... --out <path> [--width w] [--height h] ...

An empty transcript is returned on purpose: the semantic gate must degrade to
SKIPPED rather than invent a pass.

Setting ``FAKE_MMX_FAIL=1`` makes ``speech synthesize`` and ``image generate`` exit
non-zero without writing anything. That is how tests produce a genuine FAILED attempt
record, which is the evidence a retry has to reference.

Container behaviour
-------------------
``FAKE_MMX_IMAGE_CONTAINER`` controls what ``image generate`` actually writes, so a
test can reproduce the measured M2.0 defect on demand:

- ``png``  (default) a real PNG
- ``jpeg`` **JPEG bytes written to the path ContentOps asked to be PNG** — the trap
- ``webp`` a real WEBP
- ``garbage`` bytes with no recognisable container
- ``blank`` a valid PNG that is a flat mid-grey fill, which decodes but is unusable
- ``truncated`` a PNG header followed by nothing useful

Credential discovery mirrors the official CLI's priority so that binding tests are
meaningful: ``MINIMAX_API_KEY`` in the environment first, then ``~/.mmx/config.json``.
Setting ``FAKE_MMX_CREDENTIAL_REPORT`` writes the *class* and *source* it resolved
to a file. The credential value is never written, printed or logged.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# The repository's own subprocess policy applies to test fixtures too: every
# child process goes through process_utils, so no fixture can pop a console
# window on Windows. The policy gate scans tracked files and caught the direct
# subprocess.run this fixture originally used.
from process_utils import hidden_run  # noqa: E402


def _flag(argv, name, default=None):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return default


def _resolve_credential():
    """Model the official CLI's credential priority. Returns (key, source)."""
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if key:
        return key, "MINIMAX_API_KEY_ENV"
    config = Path.home() / ".mmx" / "config.json"
    if config.is_file():
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
            stored = str(payload.get("api_key") or "")
        except (json.JSONDecodeError, OSError):
            stored = ""
        if stored:
            return stored, "MMX_CONFIG"
    return "", "NONE"


def _credential_class(key):
    if not key:
        return "ABSENT"
    if key.startswith("sk-cp-"):
        return "SUBSCRIPTION"
    if key.startswith("sk-api-"):
        return "PAYG"
    return "UNKNOWN"


def _report_credential():
    path = os.environ.get("FAKE_MMX_CREDENTIAL_REPORT")
    if not path:
        return
    key, source = _resolve_credential()
    # class and source only: the value must never be persisted
    Path(path).write_text(
        json.dumps({"credential_class": _credential_class(key), "credential_source": source}),
        encoding="utf-8",
    )


def _write_image(out: str, kind: str, width: int, height: int) -> int:
    """Write a locally generated image of the requested container."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.stderr.write("fixture: Pillow is required to fake an image\n")
        return 3

    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)

    if kind == "garbage":
        path.write_bytes(b"not an image at all, not even close" * 8)
        return 0
    if kind == "truncated":
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        return 0

    if kind == "blank":
        # A flat fill decodes cleanly, so only pixel statistics catch it.
        image = Image.new("RGB", (width, height), (128, 128, 128))
        fmt = "PNG"
    else:
        # Structured, non-uniform content: bands plus shapes, so luminance
        # variance and edge density are realistic rather than degenerate.
        image = Image.new("RGB", (width, height), (18, 22, 34))
        draw = ImageDraw.Draw(image)
        for row in range(0, height, max(8, height // 24)):
            shade = 30 + (row * 7) % 200
            draw.rectangle(
                [0, row, width, row + max(4, height // 40)],
                fill=(shade, (shade * 3) % 255, (shade * 5) % 255),
            )
        for column in range(0, width, max(16, width // 9)):
            draw.ellipse(
                [column, height // 4, column + width // 14, height // 4 + width // 14],
                outline=(240, 240, 250), width=3,
            )
        draw.line([0, height - 1, width - 1, 0], fill=(255, 128, 64), width=5)
        fmt = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}.get(kind, "PNG")

    if fmt == "JPEG":
        # mode RGB is required; a JPEG with an alpha channel is not valid.
        image.save(path, format="JPEG", quality=92)
    elif fmt == "WEBP":
        image.save(path, format="WEBP", quality=92)
    else:
        image.save(path, format="PNG")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    _report_credential()

    if "--version" in argv:
        print("mmx 0.0.0-fixture")
        return 0

    if argv[:2] == ["config", "show"]:
        print(json.dumps({
            "region": "fixture",
            "base_url": "https://fixture.invalid",
            "output": "json",
        }))
        return 0

    if argv[:2] == ["speech", "transcribe"]:
        # No transcript: the semantic gate must report SKIPPED, never PASS.
        print(json.dumps({"text": "", "duration": 0}))
        return 0

    if argv[:2] == ["speech", "synthesize"]:
        out = _flag(argv, "--out")
        if not out:
            print("fixture: --out is required", file=sys.stderr)
            return 2
        if os.environ.get("FAKE_MMX_FAIL") == "1":
            # Deliberate provider failure: non-zero exit, nothing written.
            sys.stderr.write("fixture: simulated provider failure\n")
            return 7
        text = _flag(argv, "--text", "") or ""
        # ~6 characters per second keeps the duration plausible for the QC's
        # duration-plausibility window without pretending to be speech.
        seconds = max(1.0, min(20.0, len(text) / 6.0))
        result = hidden_run(
            ["ffmpeg", "-y", "-hide_banner", "-nostdin",
             "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds:.2f}",
             "-ar", "32000", "-ac", "1", "-c:a", "pcm_s16le", out],
            timeout=120,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr or "")
            return result.returncode
        print(out)
        return 0

    if argv[:2] == ["image", "generate"]:
        out = _flag(argv, "--out")
        if not out:
            print("fixture: --out is required", file=sys.stderr)
            return 2
        if os.environ.get("FAKE_MMX_FAIL") == "1":
            sys.stderr.write("fixture: simulated provider failure\n")
            return 7
        width = int(_flag(argv, "--width", "768") or 768)
        height = int(_flag(argv, "--height", "1360") or 1360)
        kind = os.environ.get("FAKE_MMX_IMAGE_CONTAINER", "png").strip().lower()
        if kind == "ignore-out":
            # Reproduces the measured "exit 0 but --out was ignored" defect.
            cwd_out = str(Path.cwd() / Path(out).name)
            code = _write_image(cwd_out, "png", width, height)
            if code == 0:
                print(cwd_out)
            return code
        if kind == "silent":
            # Exit 0, writes nothing at all.
            print(out)
            return 0
        code = _write_image(out, kind, width, height)
        if code == 0:
            print(out)
        return code

    sys.stderr.write(f"fixture: unsupported argv {argv!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())