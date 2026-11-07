"""Synthesize a local SAPI narration preview through the existing M5 helper."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import m5_production  # noqa: E402

script = json.loads((PROJECT / "script" / "script.json").read_text(encoding="utf-8"))
result = m5_production.stage_narration(PROJECT, script)
subtitles = m5_production.stage_subtitles(PROJECT, script, result)
print(json.dumps({"engine": result["engine"], "duration_s": result["duration_s"],
                  "lines": result["lines"], "audio": result["audio"],
                  "subtitles": subtitles},
                 ensure_ascii=False, indent=2))
