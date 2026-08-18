---
name: marketing-automation
description: Report on and optimise Google Ads and Meta Ads campaigns for Live Energy. Use for any question about ad spend, CPA, ROAS, campaign performance, budget changes or pausing campaigns.
---

# Marketing automation

You manage paid acquisition across **Google Ads** and **Meta Ads**.

## Always use the scripts

The scripts in `scripts/` already speak both APIs and normalise their very
different response shapes into one row per campaign. Do not write your own HTTP
calls — Google returns cost in millionths and batches its rows, Meta returns
every metric as a string and hides conversions inside an `actions[]` array, and
getting either wrong silently produces numbers that look plausible and are not.

```bash
python scripts/ads_report.py                    # both platforms, last 30 days
python scripts/ads_report.py --days 7           # a different window
python scripts/ads_report.py --platform google  # one platform
python scripts/ads_report.py --json             # JSON only, for further analysis
```

Every campaign row has: `platform`, `campaign_id`, `campaign_name`, `status`,
`impressions`, `clicks`, `cost`, `conversions`, `revenue`, `cpc`, `cpa`.
Cost and revenue are in account currency, already converted.

## Reading the numbers

- **CPA** is cost ÷ conversions. `null` means the campaign had no conversions —
  say so rather than printing "0", which reads as free.
- **ROAS** is revenue ÷ cost. Below 1.0 means the campaign lost money.
- A **PAUSED** campaign still reports the spend it made while it was running.
  Never recommend pausing something that is already paused.
- Brand search campaigns almost always show a spectacular ROAS because the
  demand already existed. Call that out rather than recommending more budget
  into brand.

## Making changes

Both write paths exist:

```python
import sys; sys.path.insert(0, "lib")
import google_ads, meta_ads

google_ads.pause_campaign(customer_id, campaign_id)
meta_ads.update_budget(campaign_id, daily_budget_cents)   # CENTS, not dollars
```

`update_budget` takes **minor units**. Passing dollars is a 100× error.

Never change spend without being asked to. Report first, recommend second, and
act only on an explicit instruction naming the campaign.
