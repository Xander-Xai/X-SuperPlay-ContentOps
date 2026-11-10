# QC Report — huashu-p01-bridge-technical-20261107

**Currency**: `CURRENT`
**Graded target**: `project://final/huashu-p01-bridge-technical-20261107.mp4`
**Overall**: `WARN`
**Checked at**: 2026-11-06T19:16:26Z

**Paths**: logical references (project://, repo://); no absolute paths

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=project://final/huashu-p01-bridge-technical-20261107.mp4 |
| file_size | OK | PASS | value_bytes=711728, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | FAIL | WARN | value_sec=4.0, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | FAIL | WARN | value_count=0 |
| caption_srt_present | OK | PASS | path=project://assets/captions/default.srt |
| script_exists | OK | PASS | path=project://script/master.md |
| storyboard_exists | OK | PASS | shot_count=1 |
| real_source_ratio | FAIL | WARN | value=0.0, min=0.7, real_shots=0, generated_shots=0, note=historical shot-count diagnostic, kept for comparison; the gate is real_source_duration_ratio |
| real_source_duration_ratio | FAIL | WARN | required=False, state=FAIL, value=0.0, min=0.7, real_seconds=0.0, required_seconds=2.8, undeclared_tail_s=0.0, note=legacy project without account DNA; ratio is diagnostic |
| source_provenance_complete | OK | PASS |  |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-7.0 dB, mean_volume_db=-30.1 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.97165 |
| real_evidence_present | FAIL | WARN | value_count=0, from_manifest=0 |
| voice_quality_declared | OK | INFO | voice_provider=existing/Microsoft Huihui Desktop (zh-CN), voice_quality=configured_provider, production_quality_warning=False, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
