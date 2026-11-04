# QC Report — e2e-rights-audit

**Currency**: `CURRENT`
**Graded target**: `project://final/e2e-rights-audit.mp4`
**Overall**: `PASS`
**Checked at**: 2026-11-04T01:10:34Z

**Paths**: logical references (project://, repo://); no absolute paths

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=project://final/e2e-rights-audit.mp4 |
| file_size | OK | PASS | value_bytes=767557, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=31.33, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=3 |
| caption_srt_present | OK | PASS | path=project://assets/captions/default.srt |
| script_exists | OK | PASS | path=project://script/master.md |
| storyboard_exists | OK | PASS | shot_count=3 |
| real_source_ratio | OK | PASS | value=1.0, min=0.7, real_shots=3, generated_shots=0, note=historical shot-count diagnostic, kept for comparison; the gate is real_source_duration_ratio |
| real_source_duration_ratio | OK | PASS | state=PASS, required=False, value=1.0, min=0.7, real_seconds=31.333, required_seconds=21.933, undeclared_tail_s=0.0, note=real visible seconds / measured output seconds; diagrams, cards, generated and motion visuals do not count |
| source_provenance_complete | OK | PASS |  |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-3.5 dB, mean_volume_db=-28.7 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.00872 |
| real_evidence_present | OK | PASS | value_count=3, from_manifest=3 |
| voice_quality_declared | OK | INFO | voice_provider=sapi/Microsoft Huihui Desktop (zh-CN), voice_quality=fallback, production_quality_warning=True, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
