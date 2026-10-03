# Media Provider Contract

> Defines the interface for all media generation providers (MiniMax, future providers).

## Interface

```python
class MediaProvider:
    def capabilities(self) -> dict:          # what this provider can do
    def health(self) -> dict:                 # is it reachable right now?
    def quota(self) -> dict:                 # remaining subscription quota

    def generate_image(self, req) -> Asset: ...
    def generate_video(self, req) -> Asset: ...
    def synthesize_speech(self, req) -> Asset: ...

    def get_job(self, job_id) -> Job: ...
    def cancel_job(self, job_id) -> bool: ...  # only if supported
    def download_asset(self, job_id) -> bytes: ...

    def receipt(self, job_id) -> Receipt: ...  # full provenance
```

## Provider Implementations

| Provider | Role | Status |
|---|---|---|
| `MiniMaxPlanProvider` | Subscription-key API for image/voice/video | PROPOSED (pending M2.0) |
| `LocalFallbackProvider` | edge-tts / ffmpeg fallback | EXISTS (in run_v1.py) |
| `ManualImportProvider` | Human-generated assets imported into pipeline | PLANNED |

## Capability Matrix

```yaml
provider: minimax_plan
capabilities:
  text: true            # to verify
  image: true           # to verify
  voice: true           # to verify
  video: conditional    # to verify
limits:
  video_daily: null     # to verify
  rate_limit: null      # to verify
automation:
  programmatic: null    # to verify
  browser_assisted: null # to verify
  manual: null           # to verify
```

## Receipt Schema

```json
{
  "provider": "minimax",
  "entitlement": "token_plan",
  "billing_mode": "subscription",
  "plan": "...",
  "model": "...",
  "request_id": "...",
  "started_at": "...",
  "finished_at": "...",
  "quota_before": {},
  "quota_after": {},
  "output": "path/to/asset",
  "sha256": "...",
  "status": "OK",
  "prompt": "...",
  "input_asset_hash": "...",
  "retries": 0,
  "generation_fingerprint": "hash(prompt + model + input_hash + params)"
}
```

## Rules

- `billing_mode: subscription`, `allow_payg: false`
- Idempotent: same generation fingerprint → reuse, don't re-charge
- Fallback recorded with `quality_impact` and `requires_human_review: true`
- Quota exhaustion → route to real assets, NOT PAYG
