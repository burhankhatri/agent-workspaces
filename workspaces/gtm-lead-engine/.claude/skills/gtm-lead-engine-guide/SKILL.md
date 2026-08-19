---
name: lead-engine-api
description: Query and manage Live Energy commercial-electricity leads via the Lead Engine REST API — list and filter leads by ZIP, square footage or verdict, find leads awaiting review, mark leads verified or done, add contacts through enrichment, generate new leads for a ZIP, and check CRM ownership. Use for any request about leads, prospects, buildings, ZIPs, square footage, qualified/review/disqualified verdicts, lead enrichment, or the lead dashboard. Not for general web browsing, other CRMs, or unrelated APIs.
---

# Live Energy Lead Engine — REST API

The Lead Engine finds large commercial buildings in deregulated US electricity
markets (Texas/ERCOT, Pennsylvania/PJM), measures each building's roof footprint
from satellite data to estimate its size, screens out multi-tenant properties,
and enriches decision-maker contacts. Bigger building → bigger electricity spend
→ better prospect for an energy broker.

This skill drives that platform over HTTP. Everything below is self-contained.

## Connection

```
LEAD_ENGINE_URL   = https://web-production-2acf.up.railway.app
LEAD_ENGINE_TOKEN = <shared secret; same value as API_TOKEN on the server>
```

Every request carries the token:

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" \
  "$LEAD_ENGINE_URL/api/leads?limit=5"
```

Confirm the connection first — this is the only endpoint needing no token:

```bash
curl -s "$LEAD_ENGINE_URL/api/health"
# {"ok":true,"store_backend":"upstash","auth":"enabled"}
```

- `auth: "enabled"` → token required and working.
- `auth: "disabled"` → **no token is set on the server and the API is open to
  the public internet.** Tell the user; anyone with the URL can read every lead
  and spend their API credits.

## Two endpoints cost real money

| Endpoint | What it spends |
|---|---|
| `POST /api/run` | One paid **Google Solar** call per building discovered. A single ZIP typically finds 150–240 buildings. |
| `POST /api/enrich` | **GetLeads/Apollo credits per contact.** Roughly 60% of leads come back with zero contacts — the credits are spent either way. |

Both require `"confirm": true` and are capped server-side (default 50 buildings
per run, 25 leads per enrichment batch).

**Never call either unless the user asks for it in that specific turn.** "Show
me the leads" is a request to read, not to generate. If you think a run is
warranted, say what it will cost and let the user decide.

Everything else — reading, filtering, verifying, marking done, bulk updates,
stats, exports, reclassify — is free. Prefer those.

## The lead model

One lead = one building, identified by its Google `place_id` (stable across
runs; it is the deduplication key).

```
place_id, company, address, city, zip, lat, lng, maps_link
sq_ft, footprint_source, size_decision      how big, and measured how
verdict                                      qualified | review | disqualified
phone, website, has_contact                  from Google Places (free)
contacts[], enriched, contact_count          from paid enrichment
in_crm, in_crm_review, in_crm_reason         CRM ownership
review_status, work_status                   workflow — see below
notes                                        free text
```

`verdict` is the **engine's** judgement about the building's size and tenancy,
not a workflow state:

- `qualified` — at or above the size floor (default 30,000 sq ft), standalone
- `review` — mid-band, or unmeasurable; a human should look
- `disqualified` — too small, or multi-tenant (a strip mall of small users)

An operator can override it, which sets `verdict_manual: true` and preserves the
engine's call in `verdict_original`.

### Two workflow axes

Separate on purpose — "has someone checked this?" and "how far has the work
got?" are different questions.

```
review_status:  unreviewed → verified | rejected
work_status:    new → in_progress → done | skipped
```

Both default to the first value when absent, so older records read correctly.
Every write stamps `<field>_at` (epoch seconds) and `<field>_by`. **Always pass
`by`** so the audit trail shows who acted.

## Recipes

### What needs reviewing?

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" \
  "$LEAD_ENGINE_URL/api/leads/pending?verdict=qualified&limit=20"
```

Returns `{total, count, limit, offset, leads}`. `total` is the full match count
before paging — use it to report "showing 20 of 143".

### Filter the lead list

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" \
  "$LEAD_ENGINE_URL/api/leads?verdict=qualified&zip=75201&enriched=false&min_sqft=30000&sort=sq_ft&order=desc&limit=25"
```

Filters AND together. `verdict`, `zip`, `review_status`, `work_status` accept
comma-separated values (OR within that field). **Always pass `limit`** — it
defaults to unlimited and the store holds hundreds of records.

### Verify a lead, then mark it done

```bash
curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"decision":"verified","by":"agent","note":"36k sqft standalone warehouse"}' \
  "$LEAD_ENGINE_URL/api/leads/<PLACE_ID>/verify"

curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"by":"agent"}' "$LEAD_ENGINE_URL/api/leads/<PLACE_ID>/done"
```

`decision` is `verified` or `rejected`.

### Update many at once — always prefer this

```bash
curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"place_ids":["ChIJa...","ChIJb..."],
       "patch":{"review_status":"verified","work_status":"done","by":"agent"}}' \
  "$LEAD_ENGINE_URL/api/leads/bulk"
# {"ok":true,"updated":2,"not_found":[]}
```

Each single `PATCH` costs a ~1.2s database round-trip. Twenty of them take half
a minute; one bulk call takes about a second. Touching more than one lead? Use
bulk.

### Generate leads for a ZIP — spends money, ask first

```bash
curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"zips":"75201","cap":10,"confirm":true}' "$LEAD_ENGINE_URL/api/run"
# {"job_id":"a1b2...","cost_note":"...","poll":"/api/jobs/a1b2..."}
```

Then poll — do **not** try to consume the SSE stream at `/events`:

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" "$LEAD_ENGINE_URL/api/jobs/a1b2..."
# {"done":true,"summary":{"generated":10,"qualified":4},"error":null,...}
```

Poll every few seconds until `done` is true, then check `error`. Optional
`industries` narrows the search: `manufacturing`, `warehouse`, `cold_storage`,
`hotel`, `hospital`, `data_center`, `grocery`, `office`.

Jobs live in one process's memory — snapshots don't survive a redeploy and
finished jobs are pruned when the next run starts. Poll to completion rather
than returning much later.

### Enrich contacts — spends money, ask first

```bash
curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"place_ids":["ChIJa..."],"confirm":true}' "$LEAD_ENGINE_URL/api/enrich"
```

Poll the returned `job_id` the same way. Max 25 leads per call.

### Fix verdicts after a threshold change — free

Size thresholds are configuration. Leads measured before a threshold was changed
carry labels from the old floor, so identical buildings in different ZIPs
disagree. This recomputes from each lead's stored `sq_ft` — no external calls:

```bash
curl -s -X POST -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" -H 'Content-Type: application/json' \
  -d '{}' "$LEAD_ENGINE_URL/api/leads/reclassify"
# {"applied":false,"would_change":161,"changes":[...]}
```

Dry-run by default; it uses the server's configured thresholds unless you pass
`min_sqft`/`disqualify_sqft`. **Show the user `would_change` and a sample before
adding `"apply": true`.** Leads with a manual verdict override are never touched.

### Portfolio overview

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" "$LEAD_ENGINE_URL/api/stats"
```

Totals plus `by_review_status`, `by_work_status`, `by_zip`.

### Export

```bash
curl -s -H "Authorization: Bearer $LEAD_ENGINE_TOKEN" \
  "$LEAD_ENGINE_URL/api/enriched/export.csv" -o leads.csv
```

`POST /api/enriched/export.xlsx` with `{"place_ids":[...]}` gives a styled
workbook; an empty list exports every enriched lead.

## Full endpoint list

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | no token needed; reports auth state |
| GET | `/api/leads` | filters: `verdict`, `review_status`, `work_status`, `enriched`, `in_crm`, `has_contact`, `zip`, `q`, `min_sqft`, `max_sqft`, `sort`, `order`, `limit`, `offset` |
| GET | `/api/leads/pending` | unreviewed only; same filters |
| GET | `/api/leads/{place_id}` | one lead |
| PATCH | `/api/leads/{place_id}` | `verdict`, `review_status`, `work_status`, `notes`, `by` |
| POST | `/api/leads/{place_id}/verify` | `{decision, by, note}` |
| POST | `/api/leads/{place_id}/done` | `{by, note}` |
| POST | `/api/leads/bulk` | `{place_ids, patch}` |
| PATCH | `/api/leads/{place_id}/crm` | `{in_crm}` — resolve an `in_crm_review` flag |
| POST | `/api/leads/reclassify` | `{min_sqft, disqualify_sqft, apply}` — free |
| POST | `/api/run` | **spends money** — `{zips, cap, industries, confirm}` |
| POST | `/api/enrich` | **spends money** — `{place_ids, confirm, provider}` |
| GET | `/api/jobs` · `/api/jobs/{job_id}` | job list / snapshot |
| POST | `/api/run/{job_id}/stop` | cancel a running job |
| GET | `/api/stats` | totals + breakdowns |
| GET | `/api/config` · `/api/settings` | feature flags; `POST /api/settings` writes |
| GET | `/api/industries` | valid `industries` values for a run |
| GET | `/api/enriched/export.csv` · POST `/api/enriched/export.xlsx` | exports |
| GET | `/api/crm-leads` · `/api/crm-leads/zips` | existing CRM person records |

`GET /openapi.json` returns the live machine-readable spec if you need to check
anything not covered here.

## Errors

| Code | Meaning |
|---|---|
| 400 | Bad input — invalid status, missing `confirm`, cap exceeded, unsupported bulk field |
| 401 | Missing or wrong token |
| 404 | Unknown `place_id` or `job_id` |
| 500 | Server-side store failure |

`400` and `404` bodies always carry `{"detail": "..."}` naming the problem and
the allowed values. Read it rather than guessing.

## Gotchas

- **`in_crm` leads are still returned by `/api/leads`** but excluded from the
  `total` in `/api/stats` — the CRM already owns those buildings, so they are not
  prospects. Pass `in_crm=false` when you want prospects only.
- **`in_crm_review`** means the CRM match was ambiguous and a human must rule on
  it via `PATCH /api/leads/{id}/crm`. Don't treat those as confirmed either way.
- **`sq_ft` can be `null`** when no source could measure the building; those land
  in `review`. Guard before comparing.
- **`enriched: true` with zero contacts is normal** — enrichment ran and found
  nobody. It has already been paid for; never re-run it hoping for a better result.
- **`verdict` vs `review_status`**: changing `verdict` overrides the engine's
  measurement. Recording that you checked a lead is `review_status`. Use
  `verify` unless the user is genuinely disputing the sizing.
- **Report counts honestly.** `total` is the number matching the filter; `count`
  is how many you actually received. Don't say "there are 20 qualified leads"
  when you fetched 20 of 143.