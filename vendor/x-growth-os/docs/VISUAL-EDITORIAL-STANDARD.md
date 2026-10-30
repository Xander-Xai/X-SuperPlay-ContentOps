# X Visual Editorial Standard V1
Date: 2026-10-25. For X-SuperPlay-X-Growth-OS English visuals.

## What was wrong with the previous OpenShell card?
Dark neon gradients, generic AI robot/security icons, too many outlined panels, big all-caps slogans and tiny explanations made the graphic look like a mass-produced AI SaaS advertisement. This is an **editorial critique**, not a claim that AI generated images are inherently inferior.

## Mandatory publication artifact

As of V0.9, **all posts must have post text + a real PNG/JPG image + English ALT, delivered together**. This supersedes old optional-image language. The source SVG is not itself an accepted X upload file. See [post-image delivery gate](POST-IMAGE-DELIVERY-GATE.md).

## Choose the medium from the evidence
| Situation | Preferred output |
|---|---|
| Actual code, log, release or UI change | Real permitted screenshot + one annotation; never invent a screenshot |
| Technical mechanism, security boundary, trade-off | Restrained, **editable vector diagram** with few nodes, short exact labels |
| Verified numerical result | Real chart with time period, units, source and baseline |
| Metaphor/illustration | Image generation is fine, but typeset final factual text separately |
| Image adds no new information | Design a concise, subject-specific editorial image that adds a visual explanation; **never omit the required image** |

## Anti-template principles
- One meaningful visual claim; readable in roughly three seconds.
- Type first: large legible headline, 0–3 supporting labels, strong negative space, 16:9 composition.
- Prefer evidence/causal diagram over decorations, glows, robots, floating shields or icon clutter.
- Avoid universal palettes. Light editorial, genuine screenshot, or technical monochrome can each work when topic-appropriate.
- No automatic blue/purple cyber gradient, uniform rounded SaaS cards, fake performance badge, invented star count or `100x` promise.
- Never make a simulated UI or conceptual architecture look like a verified screenshot.
- Distinguish source fact, illustration and independent interpretation.
- **Hard reject**: wrong product image, incorrect logo, misspelled label, fake data, unreadable mobile type, broken arrows or misrepresented factual status.

## Lightweight V0 production
1. After writing the X thesis, draft two competing visual directions: (a) real source evidence, (b) minimalist editorial diagram. Select the clearer.
2. Specify a subject-specific one-line aesthetic direction; choose one focal point, up to two typefaces, one accent and semantic colors only if needed.
3. For accurate text, code and diagrams, compose a controlled SVG/vector. Use image generation/editing for illustration, not to hallucinate evidence.
4. Render and inspect at 1600x900 and at ~400px width; verify every arrow, word, project name, source and image ALT. If the generated image belongs to a different project, discard it.
5. If it fails, revise the visual, use a verified source image or controlled SVG and export PNG. If all fail, mark draft/image_missing; **do not publish text-only**. Accuracy still outranks aesthetic quota.

## QA: five areas, 0–2 each
Message in 3 seconds; topic specificity; hierarchy/space; mobile readability; exact text/facts. Recommend >=8/10 with factual accuracy=2. This is editorial judgment, not an X engagement predictor.

## GitHub references
- [Anthropic canvas-design](https://github.com/anthropics/skills/blob/main/skills/canvas-design/SKILL.md) — visual philosophy, spatial communication, minimal words.
- [Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) — avoid templated defaults; subject-driven typography/layout.
- [Microsoft frontend-design-review](https://github.com/microsoft/skills/blob/main/.github/skills/frontend-design-review/SKILL.md) — structured quality and trust review.
- [OpenAI image generation/editing cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/Generate_Images_With_GPT_Image.ipynb).
- [Diffusers ControlNet](https://github.com/huggingface/diffusers/blob/main/docs/source/en/using-diffusers/controlnet.md) — structural image conditioning for a later advanced phase.
- [Excalidraw](https://github.com/excalidraw/excalidraw), [Mermaid](https://github.com/mermaid-js/mermaid), [resvg](https://github.com/linebender/resvg) — controllable diagrams and SVG rendering; no installation required now.

## OpenShell revision
Old visual: [cyber infographic](../assets/2026-10-25-openshell-authority.svg).
Replacement direction: **permission boundary, not a robot**; typeset approval/denial paths with low visual noise. The conversation contains a new generated off-white editorial example. Preserve the old visual for comparison, and only declare a replacement in the post record if the new file is actually available. 
