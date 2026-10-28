# QC Report — easel-fi-what-is-agent

**Video**: `eras`

**Overall**: `WARN`

**Checked at**: 2026-10-28T09:10:09Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\final\eras.mp4 |
| file_size | OK | PASS | value_bytes=4572023, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=38.9, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=1 |
| caption_srt_present | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\assets\captions\eras.srt |
| script_exists | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\script\master.md |
| storyboard_exists | OK | PASS | shot_count=1 |
| real_source_ratio | FAIL | WARN | value=0.0, min=0.7, real_shots=0, generated_shots=0, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | FAIL | WARN | missing_shot_indices=[0] |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-4.2 dB, mean_volume_db=-21.7 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.01396 |
| real_evidence_present | FAIL | WARN | value_count=0 |
| voice_quality_declared | OK | INFO | voice_provider=minimax-mplan, voice_quality=configured_provider, production_quality_warning=False, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
