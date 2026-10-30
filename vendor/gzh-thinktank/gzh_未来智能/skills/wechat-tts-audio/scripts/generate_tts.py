#!/usr/bin/env python3
"""Generate optional WeChat article audio with an auditable fallback report."""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import edge_tts
except ImportError:  # pragma: no cover - reported as a deterministic failure
    edge_tts = None


def clean_markdown(md_text: str) -> str:
    text = re.sub(r"```.*?```", " ", md_text, flags=re.S)
    text = re.sub(r"#+\s+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"[*_~`>|-]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _generate_once_worker(text: str, voice: str, output: str) -> None:
    """Run the provider in a child process so a stuck socket can be killed."""
    if edge_tts is None:
        raise RuntimeError("未安装 edge-tts")
    communicate = edge_tts.Communicate(text, voice)
    asyncio.run(communicate.save(output))


def generate(text: str, voice: str, output: Path, retries: int, timeout: int) -> None:
    """Generate audio with a hard process timeout per provider attempt."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if output.exists():
            output.unlink()
        worker = multiprocessing.Process(
            target=_generate_once_worker,
            args=(text, voice, str(output)),
            daemon=True,
        )
        worker.start()
        worker.join(max(1, timeout))
        if worker.is_alive():
            worker.terminate()
            worker.join(2)
            last_error = TimeoutError(f"TTS 供应商请求超过 {max(1, timeout)} 秒")
        elif worker.exitcode != 0:
            last_error = RuntimeError(f"TTS 子进程失败（exitcode={worker.exitcode}）")
        elif not output.is_file() or output.stat().st_size < 1024:
            last_error = RuntimeError("TTS 输出文件为空或过小")
        else:
            return
        if attempt < retries:
            import time

            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(str(last_error or "TTS 生成失败"))


def _write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_audio_card(path: Path, output: Path) -> None:
    card = (
        '<section style="margin:15px 0;padding:12px 16px;background:#f7f9fa;'
        'border-radius:8px;border:1px solid #e1e4e8;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">'
        f'<audio controls preload="none" src="{output.name}" style="width:100%;"></audio>'
        '<p style="margin:8px 0 0;color:#718096;font-size:12px;">'
        '<span leaf="">语音朗读为可选附件；正文内容以图文为准。</span></p></section>'
    )
    path.write_text(card + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="微信公众号文章可选 TTS 语音生成器")
    parser.add_argument("file", help="Markdown article file")
    parser.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS voice")
    parser.add_argument("--output", default="article_audio.mp3", help="Output mp3 path")
    parser.add_argument("--report", help="JSON report path; defaults beside the output")
    parser.add_argument("--retries", type=int, default=2, help="失败后的重试次数")
    parser.add_argument("--timeout", type=int, default=30, help="每次供应商请求的超时秒数")
    parser.add_argument("--optional", action="store_true", help="失败时写入降级回执并以 0 退出，不阻断图文流程")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    source = Path(args.file)
    output = Path(args.output)
    report_path = Path(args.report) if args.report else output.with_name("tts-report.json")
    if not source.is_file():
        report = {"schema_version": 1, "status": "failed", "reason": f"文件不存在：{source}", "checked_at": datetime.now(timezone.utc).isoformat()}
        _write_report(report_path, report)
        print(f"TTS BLOCKED: {source}", file=sys.stderr)
        return 0 if args.optional else 1

    content = source.read_text(encoding="utf-8", errors="ignore")
    plain_text = clean_markdown(content)
    print(f"[WeChat Matrix Pipeline] Generating optional TTS audio for {len(plain_text)} chars...")
    if not plain_text:
        error = "正文没有可朗读文本"
        _write_report(report_path, {"schema_version": 1, "status": "degraded", "provider": "edge-tts", "error": error, "fallback": "manual-audio-or-skip", "checked_at": datetime.now(timezone.utc).isoformat()})
        print(f"TTS DEGRADED: {error}", file=sys.stderr)
        return 0 if args.optional else 1

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        generate(plain_text, args.voice, output, max(0, args.retries), max(1, args.timeout))
    except Exception as exc:
        report = {
            "schema_version": 1,
            "status": "degraded",
            "provider": "edge-tts",
            "voice": args.voice,
            "error": str(exc),
            "fallback": "manual-audio-or-skip",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_report(report_path, report)
        print(f"TTS DEGRADED: {exc}", file=sys.stderr)
        return 0 if args.optional else 1

    card_path = output.with_name("audio-card.html")
    _write_audio_card(card_path, output)
    _write_report(report_path, {
        "schema_version": 1,
        "status": "passed",
        "provider": "edge-tts",
        "voice": args.voice,
        "audio": output.name,
        "card": card_path.name,
        "characters": len(plain_text),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[WeChat Matrix Pipeline] Audio generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
