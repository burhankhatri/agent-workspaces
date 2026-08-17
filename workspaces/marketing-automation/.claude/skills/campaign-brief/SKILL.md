---
name: campaign-brief
description: "Turns a target segment into a short campaign brief for Live Energy outreach. Use when asked to plan a campaign, draft outreach, write a brief, or segment prospects. Triggers on 'campaign', 'brief', 'outreach', 'segment', 'messaging'."
---

# Campaign brief

Produce a brief with exactly these sections, in this order:

1. **Segment** — who, and the one attribute that makes them worth contacting now.
2. **Trigger** — why now (contract expiration window, rate movement, usage change).
3. **Message** — three sentences maximum. No adjectives that a broker would not say out loud.
4. **Proof** — the single number that makes the claim credible.
5. **Ask** — one call to action.

## Rules
- Energy procurement is a considered purchase. No urgency theatre.
- Never state a savings figure you were not given. Write `TBD` instead.
- Run `scripts/segment_summary.py` first if a segment file was provided.
