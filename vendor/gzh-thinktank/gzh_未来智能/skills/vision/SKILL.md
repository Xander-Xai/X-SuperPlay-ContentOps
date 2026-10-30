---
name: vision
description: Call vision models (Agnes, Doubao, Qwen, OpenAI) to analyze images. Use when you need to understand screenshots, UI layouts, diagrams, or any image content. Supports png/jpg/webp/gif.
---

# vision

Multi-provider vision tool. Call a vision model with an image path and prompt,
then retain the returned review as a `vision-review-v1` receipt. If the host
already provides native multimodal image input, the agent may inspect images
directly, but it must still record the exact image SHA-256 and structured
judgement with `scripts/vision_review.py`.

## Responsibilities

- Use a text model for topic routing, research synthesis, article drafting,
  visual contracts and prompt plans.
- Use a native multimodal model, an external provider, or a signed human for
  pixel-level review: line intersections, black blocks, crop, hierarchy,
  typography and mobile readability.
- `--check-routing` only reports whether a route is available; it never proves
  that an image was inspected and must not be used as a passed review receipt.
- Technical diagrams, code cards and exact labels must remain deterministic
  SVG/HTML/KaTeX output; a vision model reviews them but does not redraw facts.

## Quick start

```bash
python skills/vision/vision.py [--provider <name>] <image_path> <prompt>
python scripts/vision_review.py --article <article_dir> record --reviewer-mode native --reviewer <reviewer> --capability <evidence>
python scripts/vision_review.py --article <article_dir> check
```

## Providers

### agnes (Agnes AI)

- API key: `AGNES_API_KEY`
- Default model: `agnes-2.5-flash`
- Base URL: `AGNES_BASE_URL` (default: `https://apihub.agnes-ai.com/v1`)

### doubao (Volcengine Ark)

- API key: `DOUBAO_API_KEY`
- Default model: `doubao-seed-2-0-pro-260215`
- Custom endpoint: `DOUBAO_BASE_URL`

### qwen (DashScope)

- API key: `DASHSCOPE_API_KEY`
- Default model: `qwen-vl-max`
- Custom endpoint: `DASHSCOPE_BASE_URL`

### openai

- API key: `OPENAI_API_KEY`
- Default model: `gpt-4o`
- Custom endpoint: `OPENAI_BASE_URL`

### anthropic

- API key: `ANTHROPIC_API_KEY`
- Default model: `claude-sonnet-5`
- Custom endpoint: `ANTHROPIC_BASE_URL`

### custom provider

Any other provider name is resolved from `{NAME}_API_KEY`,
`{NAME}_BASE_URL`, `{NAME}_MODEL` and optional `{NAME}_PROTOCOL`.

## Configuration

| Env Var | Scope | Default |
|---|---|---|
| `VISION_PROVIDER` | Default provider | auto-detect built-ins |
| `VISION_MODEL` | Global model override | provider default |
| `{PROVIDER}_MODEL` | Provider model override | provider default |
| `{PROVIDER}_BASE_URL` | Provider endpoint | built-in default |
| `{PROVIDER}_PROTOCOL` | Request shape | `openai` |
| `VISION_TEMPERATURE` | Response creativity | `0` |
| `VISION_MAX_TOKENS` | Response budget | `4096` |

## Review receipt contract

Every asset in `visual-semantic-review.json` must have a corresponding entry
in `vision-review.json` with:

- `image_sha256` matching the rendered bytes;
- `reader_job` and visible claim IDs;
- `reviewer_mode`: `native`, `external`, or `human`;
- `capability_evidence`, `contrast_status`, `legibility_status` and `defects`;
- external mode: provider/model/request/response fingerprints;
- human mode: reviewer, signed_by and approval_event_id.

Missing or stale receipts keep the illustrated/final gates blocked.
