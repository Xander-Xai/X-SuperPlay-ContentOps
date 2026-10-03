#!/usr/bin/env python3
"""RESEARCH PROBE ONLY -- NOT A PRODUCTION PROVIDER.

Purpose
-------
Collect *evidence* about the MiniMax M Plan Explore subscription for
X-SuperPlay-ContentOps Issue #4 (M2.0). This script proves what the current
official interfaces can and cannot do, and refuses to spend entitlement it
cannot account for.

This file must never be imported by production pipeline code. The M2-M4
provider work (#5) builds a real provider module; this probe is the evidence
that decides whether such a module may exist at all, and for which modalities.

Billing invariants this probe enforces
--------------------------------------
```
billing_mode:            subscription
allow_payg:              false
allow_credit_pack_fallback: false
```

Every generating mode runs a pre-flight gate first. The gate is fail-closed: if
any of the following cannot be proven, the generation request is NOT sent and
the verdict is ``BLOCKED_BILLING_SOURCE_UNCERTAIN``:

- the credential in use is a Subscription Key, not a pay-as-you-go key
- the pay-as-you-go cash balance is exactly zero
- the Credit Pack balance is exactly zero
- no outstanding amount is owed
- included-plan usage is still remaining in the weekly window

Rationale, from current official documentation: a Subscription Key draws on
included plan usage *and* Credit Packs, and Credit Pack overspend happens
"by default" once plan usage is exhausted. There is no documented switch to
disable that fallback. The only provable way to exclude it is to show the
Credit Pack balance is zero, which is what the pre-flight does.

Modes
-----
``--inspect``   transport, credential class, quota, pre-flight. Default. Spends
                nothing and generates nothing.
``--quota``     quota windows and balances only.
``--speech``    pre-flight, then ONE minimal speech sample per language.
``--image``     pre-flight, then ONE image.
``--video``     refuses by default. H3 entitlement is contradicted between two
                current official pages, so a paid generation cannot be
                justified until a human decides otherwise.

Security
--------
No credential value is ever printed, logged, or written. Credential reporting is
limited to a class (``SUBSCRIPTION`` / ``PAYG`` / ``ABSENT`` / ``UNKNOWN``) and
a boolean. Nothing here is a secret store: the key is read from the official
CLI's own config location at runtime and held in memory for the request only.

Usage
-----
```
python scripts/minimax_capability_probe.py
python scripts/minimax_capability_probe.py --quota
python scripts/minimax_capability_probe.py --speech --out-dir .verify-tmp/m2.0
python scripts/minimax_capability_probe.py --image --out-dir .verify-tmp/m2.0
python scripts/minimax_capability_probe.py --video --confirm-h3-unverified
```

Related: research/providers/minimax-mplan-explore-capability.md
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from process_utils import (  # noqa: E402
    hidden_run,
    interactive_run,
    is_interactive_command,
    python_executable,
)

PROBE_STATUS_VERIFIED = "VERIFIED"
PROBE_STATUS_BLOCKED = "BLOCKED"
BLOCKED_BILLING = "BLOCKED_BILLING_SOURCE_UNCERTAIN"
BLOCKED_H3 = "BLOCKED_H3_ENTITLEMENT_UNVERIFIED"

CLI = "mmx"
HTTP_TIMEOUT = 60
DEFAULT_SPEECH_MODEL = "speech-2.8-hd"
DEFAULT_IMAGE_MODEL = "image-01"


# --------------------------------------------------------------------------
# Sanitisation
# --------------------------------------------------------------------------

def scrub(text: str) -> str:
    """Remove anything key-shaped from text bound for stdout or a receipt."""
    import re

    text = re.sub(r"sk-[A-Za-z0-9\-_]{4,}", "sk-***REDACTED***", text)
    text = re.sub(r"(?i)(bearer)\s+[A-Za-z0-9\-_.]{8,}", r"\1 ***REDACTED***", text)
    return text


def emit(payload: Dict[str, Any]) -> None:
    print(scrub(json.dumps(payload, indent=2, ensure_ascii=False)))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Transport discovery
# --------------------------------------------------------------------------

def cli_path() -> Optional[str]:
    return shutil.which(CLI)


def _exe() -> str:
    """Absolute path to the CLI launcher.

    On Windows the npm install produces ``mmx.cmd`` / ``mmx.ps1`` shims, and
    CreateProcess cannot resolve a bare ``mmx`` to those. Resolution therefore
    happens once here, while classification keeps using the logical command
    name ``mmx`` -- see the ".cmd shim" note in the research doc.
    """
    return cli_path() or CLI


def cli_version() -> str:
    r = hidden_run([_exe(), "--version"], timeout=60)
    return (r.stdout or "").strip() or "UNKNOWN"


def cli_config() -> Dict[str, Any]:
    """Ask the official CLI for its resolved config.

    The base URL is taken from the CLI rather than hard-coded here, so this
    repository never carries a provider endpoint literal.
    """
    r = hidden_run([_exe(), "config", "show", "--output", "json"], timeout=60)
    if r.returncode != 0:
        return {}
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def read_credential() -> Dict[str, Any]:
    """Classify the configured credential without revealing it."""
    env_key = os.environ.get("MINIMAX_SUBSCRIPTION_KEY") or os.environ.get("MINIMAX_API_KEY")
    source = "env"
    key = env_key or ""

    if not key:
        source = "mmx-config"
        cfg = Path.home() / ".mmx" / "config.json"
        if cfg.is_file():
            try:
                key = str(json.loads(cfg.read_text(encoding="utf-8")).get("api_key") or "")
            except (json.JSONDecodeError, OSError):
                key = ""

    if not key:
        klass = "ABSENT"
    elif key.startswith("sk-cp-"):
        klass = "SUBSCRIPTION"
    elif key.startswith("sk-api-"):
        klass = "PAYG"
    elif key.startswith("sk-"):
        klass = "UNKNOWN"
    else:
        klass = "UNKNOWN"

    return {
        "credential_class": klass,
        "subscription_credential_present": klass == "SUBSCRIPTION",
        "source": source,
        "_secret": key,
    }


# --------------------------------------------------------------------------
# Read-only HTTP (stdlib only; no subprocess, no provider SDK)
# --------------------------------------------------------------------------

def _get_json(url: str, key: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def plan_quota(base_url: str, key: str) -> Dict[str, Any]:
    """Included-plan usage windows. Read-only."""
    try:
        return _get_json(base_url.rstrip("/") + "/v1/token_plan/remains", key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return {"error": type(e).__name__, "detail": scrub(str(e))}


def balances(base_url: str, key: str) -> Dict[str, Any]:
    """PAYG cash / Credit Pack / voucher / owed amounts. Read-only.

    This is a first-party endpoint that the official CLI (mmx-cli) itself calls
    for the same purpose; it is not part of the public documentation index, so
    the pre-flight treats any failure to read it as a hard block rather than
    assuming a zero balance.
    """
    try:
        return _get_json(base_url.rstrip("/") + "/account/query_balance", key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return {"error": type(e).__name__, "detail": scrub(str(e))}


def _num(value: Any) -> Optional[float]:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def summarise_quota(quota: Dict[str, Any]) -> Dict[str, Any]:
    rows = quota.get("model_remains") or []
    if not rows:
        return {"available": False, "raw_keys": sorted(quota.keys())}
    row = rows[0]
    return {
        "available": True,
        "bucket": row.get("model_name"),
        "interval_5h_remaining_percent": row.get("current_interval_remaining_percent"),
        "weekly_remaining_percent": row.get("current_weekly_remaining_percent"),
        "interval_window_ends_in_ms": row.get("remains_time"),
        "weekly_window_ends_in_ms": row.get("weekly_remains_time"),
        "buckets_reported": len(rows),
        "modality_breakdown_exposed": len(rows) > 1,
    }


def preflight(cfg: Dict[str, Any], cred: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed billing gate. Returns a verdict plus its reasons."""
    reasons: List[str] = []
    base_url = str(cfg.get("base_url") or "")
    key = cred.get("_secret") or ""

    if not base_url:
        reasons.append("no base_url resolved from the official CLI")
    if cred["credential_class"] != "SUBSCRIPTION":
        reasons.append(
            f"credential class is {cred['credential_class']}, not a Subscription Key"
        )

    bal = balances(base_url, key) if base_url and key else {"error": "no_request"}
    cash = _num(bal.get("cash_balance"))
    credit = _num(bal.get("credit_balance"))
    voucher = _num(bal.get("voucher_balance"))
    owed = _num(bal.get("owed_amount"))

    if credit is None:
        reasons.append("Credit Pack balance unreadable; fallback cannot be excluded")
    elif credit != 0:
        reasons.append(f"Credit Pack balance is {credit}, so overspend could draw on it")
    if cash is None:
        reasons.append("pay-as-you-go cash balance unreadable")
    elif cash != 0:
        reasons.append(f"pay-as-you-go cash balance is {cash}")
    if voucher not in (None, 0):
        reasons.append(f"voucher balance is {voucher}")
    if owed not in (None, 0):
        reasons.append(f"outstanding amount owed is {owed}")

    quota = plan_quota(base_url, key) if base_url and key else {}
    q = summarise_quota(quota)
    if not q.get("available"):
        reasons.append("included-plan usage unreadable")
    else:
        weekly = _num(q.get("weekly_remaining_percent"))
        if weekly is None:
            reasons.append("weekly remaining usage unknown")
        elif weekly <= 0:
            reasons.append("weekly plan window exhausted")

    verdict = BLOCKED_BILLING if reasons else PROBE_STATUS_VERIFIED
    return {
        "verdict": verdict,
        "reasons": reasons,
        "payg_balance": bal.get("cash_balance"),
        "credit_pack_balance": bal.get("credit_balance"),
        "voucher_balance": bal.get("voucher_balance"),
        "owed_amount": bal.get("owed_amount"),
        "plan_usage": q,
        "balance_endpoint_first_party": True,
    }


# --------------------------------------------------------------------------
# Media generation (each guarded by the pre-flight)
# --------------------------------------------------------------------------

def speech_texts() -> List[Dict[str, str]]:
    return [
        {
            "id": "zh",
            "voice": "Chinese (Mandarin)_Reliable_Executive",
            "text": "你好，这是 X-SuperPlay ContentOps 的 MiniMax M Plan 语音能力测试。",
        },
        {
            "id": "en",
            "voice": "English_expressive_narrator",
            "text": (
                "Hello, this is the X-SuperPlay ContentOps MiniMax M Plan "
                "speech capability test."
            ),
        },
    ]


def probe_media(
    mode: str,
    gate: Dict[str, Any],
    out_dir: Path,
    ack_h3: bool,
) -> Dict[str, Any]:
    if gate["verdict"] != PROBE_STATUS_VERIFIED:
        return {
            "mode": mode,
            "status": PROBE_STATUS_BLOCKED,
            "verdict": gate["verdict"],
            "reasons": gate["reasons"],
            "generation_attempted": False,
        }

    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "speech":
        return _probe_speech(gate, out_dir)
    if mode == "image":
        return _probe_image(gate, out_dir)
    if mode == "video":
        if not ack_h3:
            return {
                "mode": "video",
                "status": PROBE_STATUS_BLOCKED,
                "verdict": BLOCKED_H3,
                "reasons": [
                    "current official M Plan pages state Explore includes H3, "
                    "while the current official Video Generation pages state H3 "
                    "requires the pay-as-you-go API",
                    "H3 is the most expensive modality in the plan and the "
                    "contradiction is unresolved, so no generation is justified",
                    "re-run with --confirm-h3-unverified only if a human accepts "
                    "that cost and the entitlement risk",
                ],
                "generation_attempted": False,
            }
        return _probe_video(gate, out_dir)
    return {"mode": mode, "status": "UNKNOWN_MODE"}


def _probe_speech(gate: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    results = []
    for item in speech_texts():
        path = out_dir / f"m2-speech-{item['id']}.wav"
        r = hidden_run(
            [
                _exe(), "speech", "synthesize",
                "--model", DEFAULT_SPEECH_MODEL,
                "--text", item["text"],
                "--voice", item["voice"],
                "--format", "wav",
                "--out", str(path),
                "--quiet", "--non-interactive",
            ],
            timeout=300,
        )
        entry: Dict[str, Any] = {
            "language": item["id"],
            "model": DEFAULT_SPEECH_MODEL,
            "voice_id": item["voice"],
            "returncode": r.returncode,
            "generated": path.is_file(),
        }
        if r.returncode != 0:
            entry["error"] = scrub((r.stderr or "")[:600])
            results.append(entry)
            continue
        entry["sha256"] = sha256_of(path)
        entry["bytes"] = path.stat().st_size
        entry.update(_probe_audio(path))
        results.append(entry)

    ok = all(e.get("generated") and e.get("ffprobe_ok") for e in results)
    return {
        "mode": "speech",
        "status": PROBE_STATUS_VERIFIED if ok else "GENERATION_FAILED",
        "generation_attempted": True,
        "preflight": _gate_brief(gate),
        "results": results,
    }


def _probe_audio(path: Path) -> Dict[str, Any]:
    """Technical QC with ffprobe. No transcription, no judgement of quality."""
    if not shutil.which("ffprobe"):
        return {"ffprobe_ok": False, "ffprobe": "not installed"}
    r = hidden_run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_name,sample_rate,channels,bits_per_sample",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        timeout=120,
    )
    if r.returncode != 0:
        return {"ffprobe_ok": False, "error": scrub((r.stderr or "")[:300])}
    try:
        info = json.loads(r.stdout or "{}")
    except json.JSONDecodeError as e:
        return {"ffprobe_ok": False, "error": str(e)}
    stream = (info.get("streams") or [{}])[0]
    duration = (info.get("format") or {}).get("duration")
    out = {
        "ffprobe_ok": True,
        "codec": stream.get("codec_name"),
        "sample_rate_hz": stream.get("sample_rate"),
        "channels": stream.get("channels"),
        "duration_s": round(float(duration), 3) if duration else None,
    }
    out.update(_audio_peak_db(path))
    return out


def _audio_peak_db(path: Path) -> Dict[str, Any]:
    """Clipping / silence signal via ffmpeg volumedetect."""
    if not shutil.which("ffmpeg"):
        return {"volume_probe": "ffmpeg not installed"}
    r = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", "volumedetect", "-f", "null", "-"],
        timeout=120,
    )
    text = (r.stderr or "")
    peak = None
    mean = None
    for line in text.splitlines():
        if "max_volume:" in line:
            peak = line.split("max_volume:")[1].strip()
        if "mean_volume:" in line:
            mean = line.split("mean_volume:")[1].strip()
    return {"max_volume_db": peak, "mean_volume_db": mean}


def _probe_image(gate: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    path = out_dir / "m2-image-portrait.png"
    r = hidden_run(
        [
            _exe(), "image", "generate",
            "--model", DEFAULT_IMAGE_MODEL,
            "--prompt", (
                "A neutral studio photograph of a plain matte grey cube resting "
                "on a light grey seamless background, soft even lighting, no "
                "text, no logos, no interface elements"
            ),
            "--width", "768",
            "--height", "1360",
            "--seed", "42",
            "--out", str(path),
            "--quiet", "--non-interactive",
        ],
        timeout=600,
    )
    entry: Dict[str, Any] = {
        "model": DEFAULT_IMAGE_MODEL,
        "requested_width": 768,
        "requested_height": 1360,
        "requested_aspect_ratio": "9:16",
        "seed": 42,
        "returncode": r.returncode,
        "generated": path.is_file(),
    }
    if r.returncode != 0 or not path.is_file():
        entry["error"] = scrub((r.stderr or "")[:600])
        return {
            "mode": "image",
            "status": "GENERATION_FAILED",
            "generation_attempted": True,
            "preflight": _gate_brief(gate),
            "results": [entry],
        }
    entry["sha256"] = sha256_of(path)
    entry["bytes"] = path.stat().st_size
    entry.update(_probe_image_dims(path))
    return {
        "mode": "image",
        "status": PROBE_STATUS_VERIFIED,
        "generation_attempted": True,
        "preflight": _gate_brief(gate),
        "results": [entry],
    }


def _probe_image_dims(path: Path) -> Dict[str, Any]:
    """Detect the real container and dimensions; never trust the extension.

    Measured on the first M2.0 image smoke: the CLI was asked for a ``.png``
    path and wrote JPEG bytes into it. Anything downstream that picks a decoder
    from the filename would therefore fail on a perfectly valid asset, so the
    container is sniffed from the bytes and the extension is only reported.
    """
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        container = "png"
    elif data[:2] == b"\xff\xd8":
        container = "jpeg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        container = "webp"
    else:
        container = "unknown"

    declared = path.suffix.lstrip(".").lower()
    mismatch = bool(declared and container != "unknown" and declared != container)

    out: Dict[str, Any] = {
        "declared_extension": declared,
        "detected_container": container,
        "extension_mismatch": mismatch,
    }
    if shutil.which("ffprobe"):
        r = hidden_run(
            ["ffprobe", "-v", "error",
             "-show_entries", "stream=codec_name,width,height",
             "-of", "json", str(path)],
            timeout=120,
        )
        if r.returncode == 0:
            try:
                streams = (json.loads(r.stdout or "{}").get("streams") or [{}])
            except json.JSONDecodeError:
                streams = [{}]
            stream = streams[0]
            w, h = stream.get("width"), stream.get("height")
            out["codec"] = stream.get("codec_name")
            out["dimensions"] = {"width": w, "height": h} if w and h else None
            out["aspect_ratio"] = round(w / h, 4) if w and h else None
            out["decodable"] = True
            return out
    out["decodable"] = False
    return out


def _probe_video(gate: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    """One minimal H3 text-to-video job. Only reachable with explicit consent."""
    path = out_dir / "m2-video-h3.mp4"
    r = hidden_run(
        [
            _exe(), "video", "generate",
            "--model", "MiniMax-H3",
            "--prompt", "Static close-up of a single candle flame on a dark table.",
            "--duration", "4",
            "--ratio", "9:16",
            "--download", str(path),
            "--quiet", "--non-interactive",
        ],
        timeout=1800,
    )
    entry: Dict[str, Any] = {
        "model": "MiniMax-H3",
        "mode": "text-to-video",
        "duration_s": 4,
        "ratio": "9:16",
        "returncode": r.returncode,
        "generated": path.is_file(),
    }
    if path.is_file():
        entry["sha256"] = sha256_of(path)
        entry["bytes"] = path.stat().st_size
    else:
        entry["error"] = scrub((r.stderr or "")[:600])
    return {
        "mode": "video",
        "status": PROBE_STATUS_VERIFIED if entry["generated"] else "GENERATION_FAILED",
        "generation_attempted": True,
        "entitlement_acknowledged_unverified": True,
        "preflight": _gate_brief(gate),
        "results": [entry],
    }


def _gate_brief(gate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "verdict": gate["verdict"],
        "payg_balance": gate["payg_balance"],
        "credit_pack_balance": gate["credit_pack_balance"],
        "weekly_remaining_percent": gate["plan_usage"].get("weekly_remaining_percent"),
    }


# --------------------------------------------------------------------------
# Interactive login
# --------------------------------------------------------------------------

def auth_login() -> Dict[str, Any]:
    """Genuinely interactive: a human must complete it in their own terminal.

    Uses process_utils.interactive_run so the console stays visible and the
    prompt is reachable. Never called automatically.
    """
    cmd = [_exe(), "auth", "login"]
    visible = is_interactive_command(cmd)
    if not visible:
        return {
            "status": "REFUSED",
            "reason": "auth login is not classified INTERACTIVE_VISIBLE",
        }
    r = interactive_run(cmd)
    return {"status": "COMPLETED", "returncode": r.returncode}


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="RESEARCH PROBE ONLY -- MiniMax M Plan capability evidence",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true", help="default; spends nothing")
    mode.add_argument("--quota", action="store_true", help="quota and balances only")
    mode.add_argument("--speech", action="store_true", help="one minimal speech sample")
    mode.add_argument("--image", action="store_true", help="one image")
    mode.add_argument("--video", action="store_true", help="one H3 job; blocked by default")
    p.add_argument("--auth-login", action="store_true",
                   help="run the interactive login; requires a human at the terminal")
    p.add_argument("--confirm-h3-unverified", action="store_true",
                   help="accept that H3 entitlement is contradicted and may cost quota")
    p.add_argument("--out-dir", default=".verify-tmp/minimax-m2",
                   help="where generated media is written (gitignored)")
    p.add_argument("--save-receipt", default="",
                   help="write the sanitized JSON result to this path")
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.auth_login:
        emit(auth_login())
        return 0

    if not cli_path():
        emit({
            "status": "TRANSPORT_ABSENT",
            "detail": "official MiniMax CLI not found on PATH",
            "install": "npm install -g mmx-cli",
        })
        return 2

    cfg = cli_config()
    cred = read_credential()
    gate = preflight(cfg, cred)

    result: Dict[str, Any] = {
        "probe": "RESEARCH PROBE ONLY -- NOT A PRODUCTION PROVIDER",
        "checked_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "transport": {
            "name": "MiniMax CLI (official)",
            "executable": CLI,
            "version": cli_version(),
            "package": "mmx-cli",
            "region": cfg.get("region"),
        },
        "auth": {
            "credential_class": cred["credential_class"],
            "subscription_credential_present": cred["subscription_credential_present"],
            "auth_source": cred["source"],
        },
        "interactive_login_classification": {
            "mmx auth login": is_interactive_command([CLI, "auth", "login"]),
            "mmx auth status": is_interactive_command([CLI, "auth", "status"]),
        },
        "billing_preflight": gate,
    }

    mode = ("speech" if args.speech else "image" if args.image
            else "video" if args.video else None)
    if mode:
        result["probe_result"] = probe_media(
            mode, gate, Path(args.out_dir), args.confirm_h3_unverified,
        )

    emit(result)

    if args.save_receipt:
        target = Path(args.save_receipt)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            scrub(json.dumps(result, indent=2, ensure_ascii=False)) + "\n",
            encoding="utf-8",
        )

    block = result.get("billing_preflight", {}).get("verdict")
    return 0 if block == PROBE_STATUS_VERIFIED else 1


if __name__ == "__main__":
    sys.exit(main())