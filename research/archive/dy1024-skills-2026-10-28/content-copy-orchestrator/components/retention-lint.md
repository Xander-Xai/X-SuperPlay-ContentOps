---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
---

# Retention lint

Input: canonical script and duration tier.

Check that the opening delivers a concrete value proposition, each beat earns
the next beat, information changes are visible in the timing map, and the CTA
has one action. Use duration-aware heuristics; never reject a 90- or 180-second
script merely because a 60-second template exists.

Report warnings and precise rewrite locations, including hook-window,
information-change and single-CTA checks. Do not rewrite the canonical script
in a second pass.
