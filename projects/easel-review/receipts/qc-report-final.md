# QC Report — easel-review

**Video**: `final`

**Overall**: `FAIL`

**Checked at**: 2026-11-08T22:34:30Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-review\final\final.mp4 |
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
| real_source_ratio | OK | PASS | value=1.0, min=0.0, evidence_mode=EXPLANATORY, content_type=tech_review, real_shots=6, generated_shots=0, note=historical shot-count diagnostic, kept for comparison; the gate is real_source_duration_ratio |
| real_source_duration_ratio | FAIL | FAIL | state=BLOCKED, required=True, value=None, min=None, real_seconds=None, required_seconds=None, undeclared_tail_s=None, code=SHOT_DURATION_MISSING, detail=shot-0 has no measured duration, note=capture duration is format-specific; verified claims and source provenance remain separately required |
| source_provenance_complete | OK | PASS | missing_shot_indices=[] |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-3.5 dB, mean_volume_db=-27.0 dB |
| subtitle_burned_or_track | FAIL | WARN | method=burned_in_scan, note=max bright-pixel ratio across 6 samples = 0.00000 |
| real_evidence_present | OK | PASS | value_count=10, from_manifest=0 |
| voice_quality_declared | OK | INFO | voice_provider=easel/tts-voiceover (edge-tts, zh-CN-YunxiNeural), voice_quality=edge_tts_fallback, production_quality_warning=True, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
