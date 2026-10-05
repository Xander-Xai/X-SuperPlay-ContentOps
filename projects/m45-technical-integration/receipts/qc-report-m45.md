# QC Report — m45-technical-integration

**Video**: `m45`

**Overall**: `WARN`

**Checked at**: 2026-10-05T12:08:11Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=D:\Projects\X-SuperPlay-ContentOps\projects\m45-technical-integration\final\m45.mp4 |
| file_size | OK | PASS | value_bytes=311323, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | FAIL | WARN | value_sec=18.0, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | FAIL | WARN |  |
| source_refs_recorded | OK | PASS | value_count=0 |
| caption_srt_present | FAIL | WARN | path=D:\Projects\X-SuperPlay-ContentOps\projects\m45-technical-integration\assets\captions\default.srt |
| script_exists | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\m45-technical-integration\script\master.md |
| storyboard_exists | OK | PASS | shot_count=5 |
| real_source_ratio | OK | PASS | value=0.8, min=0.7, real_shots=4, generated_shots=1, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | OK | PASS | missing_shot_indices=[] |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-20.7 dB, mean_volume_db=-28.9 dB |
| subtitle_burned_or_track | FAIL | WARN | method=none, note=no subtitle declared and none present |
| real_evidence_present | OK | PASS | value_count=1 |
| voice_quality_declared | OK | INFO | voice_provider=unknown, voice_quality=unknown, production_quality_warning=True, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
