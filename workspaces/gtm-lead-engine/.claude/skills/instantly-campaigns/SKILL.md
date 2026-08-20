---
name: instantly-campaigns
description: "Read and control Live Energy's Instantly.ai cold-email campaigns over the v2 REST API — list campaigns and their status, read reply/bounce/open analytics, list sending mailboxes and their warmup state, add leads to a campaign, and pause or activate a campaign. Use for any request about outreach campaigns, sequences, sending accounts, mailboxes, deliverability, bounces, replies, opens, or emailing prospects. Not for finding or qualifying leads — that is the Lead Engine."
---

# Instantly.ai — campaigns and sending

Instantly is where Live Energy's cold outreach actually sends from. The Lead
Engine decides *who* is worth contacting; Instantly decides *what gets sent and
from which mailbox*.

## Connection

```
INSTANTLY_BASE_URL = https://api.instantly.ai/api/v2
INSTANTLY_TOKEN    = <workspace connection secret>
```

```bash
curl -s -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/campaigns?limit=10"
```

Every endpoint needs the bearer token; there is no public health check.

## The one thing that makes this different from every other API here

**A write here sends email to a real person, and email cannot be recalled.**

The Lead Engine's dangerous endpoints spend money. This one spends *reputation*.
Live Energy sends from ~85 mailboxes across a dozen lookalike domains
(`liveenergyquote.com`, `liveenergybidpro.com`, …). Those domains exist because
cold outreach burns them. A bad send — wrong person, duplicate sequence, high
bounce rate — degrades the domain for every future campaign, and the damage is
not undoable by deleting the lead afterwards.

So: **never add leads to a campaign, activate a campaign, or change a sequence
unless the user asked for it in that specific turn.** Reading is always fine.

## Campaigns

```bash
curl -s -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/campaigns?limit=100" \
  | jq -r '.items[] | "\(.id)  status=\(.status)  \(.name)"'
```

`status` is an integer, and it is the first thing to check before touching a
campaign:

| status | meaning | adding a lead means |
|---|---|---|
| 0 | draft | queued; nothing sends until it is activated |
| 1 | **active** | **enters the sending queue immediately** |
| 2 | paused | queued; sends resume when unpaused |
| 3 | completed | queued but dormant |
| 4 | running subsequences | active for follow-ups |

Paging uses `starting_after` with the last id, not an offset. `limit` maxes at
100.

### Control

```bash
curl -s -X POST -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/campaigns/<id>/pause"
curl -s -X POST -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/campaigns/<id>/activate"
```

Pausing is safe and reversible — reach for it when something looks wrong.
Activating starts sending. Ask first.

## Analytics — read this before judging a campaign

```bash
curl -s -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/campaigns/analytics?id=<campaign_id>" | jq .
```

Returns `leads_count`, `contacted_count`, `emails_sent_count`, `reply_count`,
`reply_count_unique`, `bounced_count`, `unsubscribed_count`,
`total_opportunities`, `total_opportunity_value`.

Reading it honestly:

- **`open_count` is often 0 and that is not a bug.** Open tracking needs a
  tracking pixel, which many of these campaigns disable because pixels hurt
  deliverability. Do not report "0% open rate" as a finding — report that opens
  are not tracked.
- **`reply_count` counts every reply; `reply_count_unique` counts people.** Use
  the unique figure when quoting a reply rate.
- **`reply_count_automatic` is out-of-office and bounce autoresponders**, not
  interest. It is frequently *larger* than the real reply count. Never add it in.
- **Bounce rate = `bounced_count / emails_sent_count`.** Above ~3% is a
  deliverability problem worth raising; above 5% risks the domain.

## Sending mailboxes

```bash
curl -s -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  "$INSTANTLY_BASE_URL/accounts?limit=100" \
  | jq -r '.items[] | "\(.email)  status=\(.status)  warmup=\(.warmup_status)  limit=\(.daily_limit)"'
```

`status`: `1` active, `2` paused, `-1` **error — the mailbox is disconnected and
sending nothing**. A campaign can look healthy while half its mailboxes are at
`-1`; when send volume is unexpectedly low, check here first.

`daily_limit` is per mailbox (30–50 here). Total daily capacity is the sum over
*active* mailboxes assigned to that campaign — that is the real ceiling on how
fast a list gets worked through, not anything in the campaign settings.

## Adding leads

Prefer the bulk endpoint. It is transactional in its reporting, tells you
exactly what it skipped, and takes up to 1000 leads in one call.

```bash
curl -s -X POST -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "campaign_id": "<uuid>",
        "leads": [{"email":"a@b.com","first_name":"Ada","company_name":"B Corp"}],
        "skip_if_in_workspace": true,
        "skip_if_in_campaign": true
      }' \
  "$INSTANTLY_BASE_URL/leads/add"
```

Lead fields: `email`, `first_name`, `last_name`, `company_name`, `job_title`,
`phone`, `website`, `personalization`, `custom_variables`.

**`custom_variables` values must be primitives** — string, number, boolean,
null. A nested object or array is rejected, and the whole request fails, not
just that lead.

**Always set `skip_if_in_workspace: true`.** Without it, a contact already in
another campaign gets a second sequence from a second Live Energy domain. The
recipient sees two strangers from two companies with the same pitch; the
receiving mail server sees a pattern it filters on.

The response is the honest record of what happened — read it rather than
assuming success:

```
{"leads_uploaded": 22, "skipped_count": 2, "duplicated_leads": [...],
 "invalid_email_count": 0, "in_blocklist": 0, "total_sent": 24}
```

`total_sent` is how many you submitted, **not** how many were accepted.
`leads_uploaded` is the real number.

### Reading a campaign's leads

`POST` despite being a read:

```bash
curl -s -X POST -H "Authorization: Bearer $INSTANTLY_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"campaign_id":"<uuid>","limit":100}' \
  "$INSTANTLY_BASE_URL/leads/list"
```

Page with `starting_after` set to the previous page's last id.

## Gotchas

- **`GET /campaigns` returns the full sequence bodies.** A 20-campaign account
  is ~60KB of HTML email templates. Always `jq` down to the fields you need
  rather than reading the raw response.
- **Campaign names are not unique and several are near-identical**
  ("Instantly | Renewal Visibility" vs "Instantly | Electricity Renewal"). Match
  on id. If the user names a campaign ambiguously, list the candidates with
  their status and lead counts and ask which one.
- **A completed campaign (status 3) still accepts leads.** They sit there
  unsent, looking like a successful push. Check status before adding.
- **Adding a lead does not send immediately** even on an active campaign — it
  enters a queue governed by the schedule and the mailboxes' daily limits. "It
  went out" is not confirmable from the add response; check analytics later.
