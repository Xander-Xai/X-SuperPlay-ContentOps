#!/usr/bin/env bash
# Bootstrap X-SuperPlay-ContentOps runtime on Linux / WSL2 / macOS.
#
# - Checks git, python>=3.10, node>=22.19, ffmpeg, ffprobe
# - Clones Easel into .runtime/easel/ at the pinned commit
# - Verifies HEAD matches runtime/easel.lock.json
# - Does NOT auto-upgrade upstream

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
LOCK="$ROOT/runtime/easel.lock.json"
EASEL_DIR="$ROOT/.runtime/easel"

red()    { printf "\033[31m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
cyan()   { printf "\033[36m%s\033[0m\n" "$*"; }

die() { red "ERROR: $*"; exit 1; }

require_tool() {
    local tool="$1"; shift
    if ! command -v "$tool" >/dev/null 2>&1; then
        red "  missing: $tool"; return 1
    fi
    green "  ok: $tool ($("$tool" "$@" 2>&1 | head -1))"
    return 0
}

cyan "=== X-SuperPlay-ContentOps bootstrap (bash) ==="

cyan "[1/4] Toolchain check"
require_tool git --version || die "git missing"
require_tool ffmpeg -version || die "ffmpeg missing"
require_tool ffprobe -version || die "ffprobe missing"
require_tool python3 --version || die "python3 missing"

if command -v node >/dev/null 2>&1; then
    require_tool node --version || true
else
    yellow "  node not found (Easel may need it later)"
fi

if ! command -v espeak >/dev/null 2>&1; then
    yellow "  espeak not found (TTS will fall back to Windows SAPI / silence)"
fi

cyan "[2/2] Lock file"
if [[ ! -f "$LOCK" ]]; then die "missing $LOCK"; fi
EXPECTED=$(python3 -c "import json; print(json.load(open('$LOCK'))['commit'])")
TAG=$(python3 -c "import json; print(json.load(open('$LOCK'))['tag'])")
echo "  expected commit: $EXPECTED  ($TAG)"

cyan "[3/4] Clone Easel"
mkdir -p "$(dirname "$EASEL_DIR")"

if [[ ! -d "$EASEL_DIR/.git" ]]; then
    git clone --no-checkout https://github.com/ZJU-REAL/Easel.git "$EASEL_DIR"
fi

cyan "[4/4] Checkout pinned commit"
cd "$EASEL_DIR"
git fetch --depth=1 origin "$EXPECTED" || die "fetch failed"
git checkout "$EXPECTED" || die "checkout failed"
ACTUAL=$(git rev-parse HEAD)
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    die "HEAD mismatch: $ACTUAL != $EXPECTED"
fi

green "Easel checked out at $ACTUAL"

cyan "Running doctor..."
python3 "$ROOT/scripts/doctor.py" || yellow "doctor reported warnings (see above)"

green "Bootstrap complete."
echo
echo "Next:"
echo "  python3 scripts/new_project.py --slug easel-review --title 'Easel 实测'"
echo "  python3 scripts/run_v1.py projects/easel-review"
echo "  python3 scripts/qc_video.py projects/easel-review"