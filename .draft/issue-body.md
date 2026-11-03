## Why

The content router (hot-spot discovery + user topic) was developed on a long-lived
stacked branch that was never opened as a PR. The production branch has no router,
and an approved, drafted episode had no path into the M5 renderer because the two
sides use different script contracts.

## Scope

- Land the router layer on a fresh branch off `main`: account DNA, hot-list sources,
  the two entrances, the draft stage and the producer CLIs they name.
- Add the missing seam: `brief_to_m5` converts an approved draft into the M5
  contract (`script.json`, `claims.json`, `source-refs.json`).
- Refuse, with a named blocker, a missing asset mapping, a missing source
  permission, an unverifiable quote or an unapproved brief.
- Enforce the copy review for router projects at the M5 entry.

## Not in scope

No vendor content, no research archive, no historical project outputs, no
publication, no provider spend, no credentials, no real sample or render. The
layer is offline and fixture-driven.

## Verification

`python scripts/dev_check.py` plus the router suites and the existing M5,
copy-review, gate and driver suites.
