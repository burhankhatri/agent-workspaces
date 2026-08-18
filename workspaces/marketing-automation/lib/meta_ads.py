"""
Meta (Facebook/Instagram) Ads client.

Wraps the Marketing API's Insights endpoint. Live calls go to META_ADS_BASE_URL
with META_ADS_TOKEN, both injected by the workspace connection.

Meta returns every metric as a STRING and nests actions in a list of
{action_type, value} objects, so the normalising here is not incidental — it is
what makes a Meta row comparable with a Google row.
"""

from __future__ import annotations

from ads_transport import AdsError, call

PLATFORM = "meta_ads"
BASE_URL_ENV = "META_ADS_BASE_URL"
TOKEN_ENV = "META_ADS_TOKEN"


def _action_value(actions: list[dict] | None, wanted: str) -> float:
    for a in actions or []:
        if a.get("action_type") == wanted:
            return float(a.get("value", 0))
    return 0.0


def campaign_performance(ad_account_id: str, days: int = 30) -> list[dict]:
    """
    Spend, clicks and purchases per campaign, in the same shape the Google Ads
    client returns so the two can be concatenated.
    """
    payload = call(
        PLATFORM,
        "campaign_performance",
        base_url_env=BASE_URL_ENV,
        token_env=TOKEN_ENV,
        path=f"act_{ad_account_id}/insights",
    )

    out: list[dict] = []
    for row in payload.get("data", []):
        spend = float(row.get("spend", 0))
        clicks = int(row.get("clicks", 0))
        purchases = _action_value(row.get("actions"), "purchase")
        revenue = _action_value(row.get("action_values"), "purchase")
        out.append(
            {
                "platform": "meta_ads",
                "campaign_id": row.get("campaign_id", ""),
                "campaign_name": row.get("campaign_name", ""),
                "status": row.get("effective_status", ""),
                "impressions": int(row.get("impressions", 0)),
                "clicks": clicks,
                "cost": round(spend, 2),
                "conversions": purchases,
                "revenue": round(revenue, 2),
                "cpc": round(spend / clicks, 2) if clicks else 0.0,
                "cpa": round(spend / purchases, 2) if purchases else None,
            }
        )
    return out


def update_budget(campaign_id: str, daily_budget_cents: int) -> dict:
    """
    Change a campaign's daily budget. Meta takes budgets in minor units, so the
    argument is cents deliberately — passing dollars here is a 100x error and
    the name is the only thing standing between you and it.
    """
    return call(
        PLATFORM,
        "update_budget",
        base_url_env=BASE_URL_ENV,
        token_env=TOKEN_ENV,
        path=campaign_id,
        payload={"daily_budget": daily_budget_cents},
    )


__all__ = ["campaign_performance", "update_budget", "AdsError"]
