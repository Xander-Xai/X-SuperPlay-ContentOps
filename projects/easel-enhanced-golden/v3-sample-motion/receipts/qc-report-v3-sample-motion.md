# QC Report — v3-sample-motion

**Currency**: `CURRENT`
**Graded target**: `project://final/v3-sample-motion.mp4`
**Overall**: `WARN`
**Checked at**: 2026-10-27T02:40:03Z

**Paths**: logical references (project://, repo://); no absolute paths

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=project://final/v3-sample-motion.mp4 |
| file_size | OK | PASS | value_bytes=1439023, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | FAIL | WARN | value_sec=26.6, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | FAIL | WARN |  |
| source_refs_recorded | OK | PASS | value_count=0 |
| caption_srt_present | FAIL | WARN | path=project://assets/captions/default.srt |
| script_exists | OK | PASS | path=project://script/master.md |
| storyboard_exists | OK | PASS | shot_count=3 |
| real_source_ratio | OK | PASS | value=1.0, min=0.7, real_shots=3, generated_shots=0, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | OK | PASS |  |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-4.4 dB, mean_volume_db=-19.2 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.02514 |
| real_evidence_present | FAIL | WARN | value_count=0 |
| voice_quality_declared | OK | INFO | voice_provider=minimax_m_plan/speech-2.8-hd (v3 arm E), voice_quality=configured_provider, production_quality_warning=False, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
