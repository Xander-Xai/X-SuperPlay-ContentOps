---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
---

# B-roll route matrix

Use the route that can communicate the editorial job with the least factual risk.

| Route | Trigger | Preferred source | `fact_status` | Default owner | Fallback |
|---|---|---|---|---|---|
| `original` | User test, product capture, own video, own post | User-owned file or screen recording | `evidence` | `media-delivery` | designed card marked illustrative |
| `receipts` | Current claim, discourse, review, launch, complaint, metric | Official post, primary page, dated headline, review, search capture | `evidence` | `media-delivery` | exact source card with URL/date |
| `entity` | Named person, company action, physical product, place, historical event | Official channel/page or directly licensed footage | `evidence` | `media-delivery` | public-domain or exact screenshot |
| `product-ui` | Feature, workflow, command, interface, benchmark | Real screen recording or official docs capture | `evidence` | `media-delivery` | editable diagram; never fake UI |
| `concept-motion` | Abstract process, mental model, comparison without source pixels | HyperFrames, Remotion, deterministic SVG/HTML | `illustrative` or `exact` | one selected motion owner | plugin-native rerun required; otherwise skip/block |
| `generated-gap` | Non-factual atmosphere or approved illustrative shot with no usable real source | Approved image/video model named in plan | `illustrative` | named generator | concept-motion or skip |
| `cultural` | Meme, reaction, creator clip where taste decides | User library or supplied exemplar | `opinion` | user/editor | skip |

## Beat interpretation

- “People are saying” → receipts, not a generic logo.
- A number or benchmark → source the exact figure, chart, pricing page, or test output.
- “How it works” → real product flow, terminal, or editable diagram.
- A quote → original post/article or the speaker saying that thing.
- A person mention → the relevant action or event, not a random face shot.
- A metaphor → use only if it sharpens the point; otherwise skip.
- A reaction/punchline → propose the moment and register; do not fetch a meme automatically.

## Candidate scoring

Score each candidate 0–5 before presenting it:

`total = 0.30 relevance + 0.20 authority + 0.15 rights clarity + 0.15 recency + 0.10 format fit + 0.10 visual readability`

Drop candidates with an unresolved rights status, obvious watermark, wrong product/person, burned-in captions that conflict with the edit, or a score below 3.0. A high score never overrides the user's taste or a hard ban.

## Timing and composition defaults

- Place the cutaway at `trigger_word_end + 0.20–0.50s` when word-level timing exists.
- Keep a single cutaway long enough to read; avoid split-second face flashes.
- For a 9:16 delivery, preserve the center 80% safe area and reframe dense 16:9 evidence rather than shrinking it into an unreadable card.
- Strip source audio unless the plan explicitly says the source sound is evidence or part of the story.
- Use a subtle, deterministic Ken Burns move for approved stills only when it improves readability; never add random motion.

## Rights minimum

Every external or generated item needs: direct source URL or local path, creator/owner, actual license or permission reference, capture date, intended time range, attribution text, fact status, and approval status. “Royalty-free” alone is not a license. Generated items also need model/provider, exact prompt, references, seed when available, and generated-media disclosure.
