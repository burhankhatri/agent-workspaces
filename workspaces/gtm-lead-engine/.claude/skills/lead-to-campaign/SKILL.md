---
name: lead-to-campaign
description: "The end-to-end Live Energy outreach workflow — take qualified, enriched leads out of the Lead Engine and push them into an Instantly campaign, then mark them worked. Use whenever the user wants to put leads into a campaign, start outreach, email prospects, 'push leads to Instantly', 'run a campaign on these leads', or asks how many leads are actually ready to mail. Covers the mapping between the two systems and the eligibility rules."
---

# Lead Engine → Instantly

The handoff nobody else documents. The Lead Engine and Instantly each have a
skill describing their own API; this describes the seam between them, which is
where the mistakes live.

## Use the script

```bash
python3 scripts/push_to_instantly.py                          # dry run
python3 scripts/push_to_instantly.py --zip 75041              # narrowed
python3 scripts/push_to_instantly.py --campaign <id> --apply  # sends
```

Dry run is the default and writes nothing. Prefer this over hand-rolling curl:
the eligibility filter below is easy to get subtly wrong, and every way of
getting it wrong emails somebody who should not have been emailed.

## The two systems disagree about what a "lead" is

| | Lead Engine | Instantly |
|---|---|---|
| a record is | a **building** | a **person** |
| keyed by | Google `place_id` | email address |
| "qualified" means | the building is big and standalone | nothing — Instantly has no opinion |

So the handoff is a **fan-out and a narrowing at the same time**. One 462,000
sq ft fulfilment centre becomes three Instantly leads if enrichment found three
managers. Meanwhile most qualified leads produce *zero*, because qualification
measures a roof and says nothing about whether anyone's email is known.

Currently: **459 leads → 150 qualified → 142 not already in the CRM → 26
enriched → 11 with a real email address → 24 people.**

Quote the number that matters. "We have 142 qualified leads" is true and
useless; "24 people are mailable today" is the number that predicts what
happens when you press go.

## Eligibility — every filter is load-bearing

```
verdict = qualified      the building clears the size floor and is standalone
in_crm = false           Live Energy does not already own this account
enriched = true          enrichment has run
contacts[].email         at least one contact has a non-empty email
work_status = new        not already pushed by an earlier run
```

Two of these are easy to drop and expensive to drop:

- **`in_crm=false`.** `/api/leads` returns CRM-owned leads by default. Omit this
  and you cold-pitch existing customers, from a lookalike domain, as if you had
  never met them.
- **`contacts[].email`, not `has_contact`.** `has_contact` is a *Google Places*
  flag meaning the building has a phone number or website. It is `true` for 20
  of the current leads; only 11 of those have an email. Filtering on
  `has_contact` overstates the mailable set by nearly 2×.

## Field mapping

| Lead Engine | Instantly | note |
|---|---|---|
| `contacts[].email` | `email` | lowercased, trimmed |
| `contacts[].full_name` | `first_name` + `last_name` | **must be split** |
| `contacts[].title` | `job_title` | |
| `company` | `company_name` | note the rename |
| `website`, `phone` | `website`, `phone` | contact phone wins over building phone |
| `place_id`, `sq_ft`, `address`, `city`, `zip`, `maps_link` | `custom_variables` | primitives only |

**Splitting `full_name` is not cosmetic.** The sequences interpolate
`{{firstName}}`. Pass the whole name through and the email opens "hi Erik
Rockholt," — which announces itself as an untouched mail merge in the first
three words.

Carrying `place_id` in `custom_variables` is what makes a reply traceable back
to the building it came from. Keep it.

## The failure mode to watch for

**Enrichment sometimes matches the parent corporation instead of the building's
operator, and the result looks completely plausible.**

A real example from the current data: a 42,000 sq ft building named "Goldman
Sachs Health Center" enriched to the Chairman & CEO of Goldman Sachs. Correct
company name, correct-looking corporate email domain, senior title — and
entirely the wrong person to ask about a Texas electricity contract.

Comparing the email domain against the building's website catches only some of
these (that example passes the check; a same-company alias like
`andersencorp.com` vs `andersenwindows.com` fails it while being fine). There is
no automated test for this. **The dry-run preview is the check** — read the
company/title pairs and ask whether that person plausibly signs an energy
contract for that building.

Nothing in this data has been human-reviewed yet: `review_status` is
`unreviewed` for all 459 leads. Approving a dry run *is* the review. When the
team starts marking leads verified in the Lead Engine, `--verified-only` makes
that the gate instead.

## Closing the loop

On a successful push the script marks the source leads
`work_status=in_progress` via `/api/leads/bulk` — not `done`, because outreach
has started, not finished. This is what stops the next run re-pushing the same
people, and it is skipped when Instantly uploads nothing, so a failed attempt
retries cleanly.

`skip_if_in_workspace` on the Instantly side is the second, independent guard.
Keep both: the local one stops re-reading, the remote one stops a contact
receiving two sequences from two different Live Energy domains.

## Before pressing apply

Per `crm-write-safety`, enrolling anyone in outreach is a system-of-record
write, and more than 10 records needs explicit sign-off. A normal push here is
~24 people, so that sign-off is always required.

State plainly: how many people, how many companies, which campaign, and whether
that campaign is **active** (status 1 — they enter the sending queue at once) or
draft/paused (they wait). Then let the user decide.
