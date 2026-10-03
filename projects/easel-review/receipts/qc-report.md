# QC Report — easel-review

**Overall**: `WARN`

**Checked at**: 2026-10-02T09:18:13Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| file_size | OK | PASS | value_bytes=552315, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=40.03, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=4 |
| caption_srt_present | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-review\assets\captions\default.srt |
| script_exists | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-review\script\master.md |
| storyboard_exists | OK | PASS | shot_count=6 |
| real_source_ratio | OK | PASS | value=1.0, min=0.7, real_shots=6, generated_shots=0, note=AI-generated key visuals must not be the majority |
| source_provenance_complete | OK | PASS | missing_shot_indices=[] |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-3.5 dB, mean_volume_db=-27.0 dB |
| subtitle_burned_or_track | FAIL | WARN | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.00000 |
| real_evidence_present | OK | PASS | value_count=9 |
| voice_quality_declared | OK | INFO | value=windows_sapi, note=fallback is acceptable for smoke test; not for production publish |
