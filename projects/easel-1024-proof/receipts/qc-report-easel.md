# QC Report — easel-1024-proof

**Video**: `easel`

**Overall**: `PASS`

**Checked at**: 2026-10-29T18:03:12Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-1024-proof\final\easel.mp4 |
| file_size | OK | PASS | value_bytes=1042693, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | OK | PASS | value_sec=44.0, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=0 |
| graded_storyboard | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-1024-proof\work\storyboard.json |
| caption_srt_present | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-1024-proof\assets\captions\cut.srt |
| script_exists | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\easel-1024-proof\script\master.md |
| storyboard_exists | OK | PASS | shot_count=8 |
| real_source_ratio | OK | PASS | value=0.727, min=0.7, account_mode=EVIDENCE_LED, basis=cut_plan_duration, real_seconds=32.0, generated_seconds=0.0, real_shots=None, generated_shots=None, real_assets=4, generated_assets=0, note=AI-generated key visuals must not be the majority |
| generated_ratio | OK | PASS | value=0.0, max=0.3, account_mode=EVIDENCE_LED, basis=cut_plan_duration, note=a generated clip may illustrate a beat, never carry the cut |
| source_provenance_complete | OK | PASS | basis=cut_plan, assets_without_a_source=[] |
| engine_recorded | OK | PASS | value=easel |
| voice_not_silence | OK | PASS | max_volume_db=-4.3 dB, mean_volume_db=-23.3 dB |
| subtitle_burned_or_track | OK | PASS | method=burned_in_scan, source=caption_cues, note=max bright-pixel ratio across 5 samples = 0.01417 |
| real_evidence_present | OK | PASS | basis=cut_plan, assets=['A-DOCTOR', 'A-REV', 'A-SKILL', 'A-SUB'] |
| voice_quality_declared | OK | INFO | voice_provider=minimax-mplan, voice_quality=configured_provider, production_quality_warning=False, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
