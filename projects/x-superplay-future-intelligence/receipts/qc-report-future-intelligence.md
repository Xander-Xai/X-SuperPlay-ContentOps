# QC Report — x-superplay-future-intelligence

**Currency**: `CURRENT`
**Graded target**: `project://final/future-intelligence.mp4`
**Overall**: `WARN`
**Checked at**: 2026-10-27T09:07:34Z

**Paths**: logical references (project://, repo://); no absolute paths

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=project://final/future-intelligence.mp4 |
| file_size | OK | PASS | value_bytes=4150458, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=106.4, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=0 |
| caption_srt_present | FAIL | WARN | path=project://assets/captions/default.srt |
| script_exists | OK | PASS | path=project://script/master.md |
| storyboard_exists | OK | PASS | shot_count=9 |
| real_source_ratio | OK | PASS | value=1.0, min=0.7, real_shots=9, generated_shots=0, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | OK | PASS |  |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-4.2 dB, mean_volume_db=-19.6 dB |
| subtitle_burned_or_track | FAIL | WARN | method=none, note=no subtitle declared and none present |
| real_evidence_present | FAIL | WARN | value_count=0 |
| voice_quality_declared | OK | INFO | voice_provider=minimax_m_plan/speech-2.8-hd (v3 full, founder clone), voice_quality=configured_provider, production_quality_warning=False, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
