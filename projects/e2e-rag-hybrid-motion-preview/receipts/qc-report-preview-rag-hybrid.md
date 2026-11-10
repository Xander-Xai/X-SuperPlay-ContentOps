# QC Report — e2e-rag-hybrid-motion-preview

**Video**: `preview-rag-hybrid`

**Overall**: `WARN`

**Checked at**: 2026-11-07T18:46:40Z

| Check | Status | Severity | Detail |
|---|---|---|---|
| _video | OK | INFO | path=D:\Projects\X-SuperPlay-ContentOps\projects\e2e-rag-hybrid-motion-preview\final\preview-rag-hybrid.mp4 |
| file_size | OK | PASS | value_bytes=750777, min_bytes=102400 |
| ffprobe_parse | OK | PASS |  |
| resolution | OK | PASS | value=1080x1920, expected=1080x1920 |
| aspect_ratio_9_16 | OK | PASS | value=1080:1920 |
| duration_range | FAIL | WARN | value_sec=14.27, expected_range_sec=[30.0, 120.0] |
| video_codec_h264 | OK | PASS | value=h264 |
| audio_present | OK | PASS |  |
| audio_codec_aac | OK | PASS | value=aac |
| project_yaml | OK | PASS |  |
| source_refs_recorded | OK | PASS | value_count=0 |
| caption_srt_present | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\e2e-rag-hybrid-motion-preview\assets\captions\default.srt |
| script_exists | OK | PASS | path=D:\Projects\X-SuperPlay-ContentOps\projects\e2e-rag-hybrid-motion-preview\script\master.md |
| storyboard_exists | OK | PASS | shot_count=3 |
| real_source_ratio | OK | PASS | value=0.0, min=0.0, evidence_mode=EXPLANATORY, real_shots=0, generated_shots=0, note=historical shot-count diagnostic, kept for comparison; the gate is real_source_duration_ratio |
| real_source_duration_ratio | OK | PASS | state=PASS, required=True, value=0.0, min=0.0, real_seconds=0.0, required_seconds=0.0, undeclared_tail_s=0.0, code=None, detail=None, note=real visible seconds / measured output seconds; diagrams, cards, generated and motion visuals do not count as evidence |
| source_provenance_complete | OK | PASS | missing_shot_indices=[] |
| engine_recorded | OK | PASS | value=huashu-art-motion clips + ffmpeg concat/mux |
| voice_not_silence | OK | PASS | max_volume_db=-1.8 dB, mean_volume_db=-24.9 dB |
| subtitle_burned_or_track | OK | PASS | method=subtitle_stream, note= |
| real_evidence_present | FAIL | WARN | value_count=0, from_manifest=0 |
| voice_quality_declared | OK | INFO | voice_provider=windows_sapi/Microsoft Huihui Desktop (zh-CN), voice_quality=fallback, production_quality_warning=True, note=mechanical/fallback voice keeps the render at READY_FOR_HUMAN_REVIEW; only a human can accept it as production (V1 spec §11) |
