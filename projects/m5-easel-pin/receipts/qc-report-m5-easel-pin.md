# QC Report — m5-easel-pin

**Currency**: `CURRENT`
**Graded target**: `project://final/m5-easel-pin.mp4`
**Overall**: `PASS`
**Checked at**: 2026-10-31T11:46:36Z

**Paths**: logical references (project://, repo://); no absolute paths

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=project://final/m5-easel-pin.mp4 |
| file_size | OK | PASS | value_bytes=1098055, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=45.14, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=4 |
| caption_srt_present | OK | PASS | path=project://assets/captions/default.srt |
| script_exists | OK | PASS | path=project://script/master.md |
| storyboard_exists | OK | PASS | shot_count=7 |
| real_source_ratio | OK | PASS | value=1.0, min=0.7, real_shots=7, generated_shots=0, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | OK | PASS |  |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-3.7 dB, mean_volume_db=-27.8 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.01092 |
| real_evidence_present | OK | PASS | value_count=3, from_manifest=3 |
| voice_quality_declared | OK | INFO | voice_provider=windows-sapi/Huihui (offline), voice_quality=fallback, production_quality_warning=True, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
