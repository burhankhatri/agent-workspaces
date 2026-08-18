"""
Google Ads client.

Wraps the searchStream reporting endpoint, which is how nearly all Google Ads
reporting is actually done — you send GAQL and get rows back. Live calls go to
GOOGLE_ADS_BASE_URL with GOOGLE_ADS_TOKEN, both injected by the workspace
connection; mock calls read fixtures in the same response shape.
"""

from __future__ import annotations

from ads_transport import AdsError, call

PLATFORM = "google_ads"
BASE_URL_ENV = "GOOGLE_ADS_BASE_URL"
TOKEN_ENV = "GOOGLE_ADS_TOKEN"


def _rows(payload) -> list[dict]:
    """
    searchStream returns a LIST of batches, each with a `results` array. Callers
    want rows, so the batching is flattened here rather than in every script.
    """
    batches = payload if isinstance(payload, list) else [payload]
    rows: list[dict] = []
    for batch in batches:
        rows.extend(batch.get("results", []))
    return rows


def campaign_performance(customer_id: str, days: int = 30) -> list[dict]:
    """
    Cost, clicks, conversions per campaign over the last `days`.

    Returns flat dicts — the API nests everything under resource names, and every
    caller would otherwise repeat the same digging.
    """
    gaql = (
        "SELECT campaign.id, campaign.name, campaign.status, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        "FROM campaign "
        f"WHERE segments.date DURING LAST_{days}_DAYS"
    )
    payload = call(
        PLATFORM,
        "campaign_performance",
        base_url_env=BASE_URL_ENV,
        token_env=TOKEN_ENV,
        path=f"customers/{customer_id}/googleAds:searchStream",
        payload={"query": gaql},
    )

    out: list[dict] = []
    for row in _rows(payload):
        campaign = row.get("campaign", {})
        metrics = row.get("metrics", {})
        # cost_micros is millionths of the account currency. Every downstream
        # comparison against Meta's plain currency figures needs this converted
        # once, here, not per script.
        cost = int(metrics.get("costMicros", 0)) / 1_000_000
        clicks = int(metrics.get("clicks", 0))
        conversions = float(metrics.get("conversions", 0))
        out.append(
            {
                "platform": "google_ads",
                "campaign_id": str(campaign.get("id", "")),
                "campaign_name": campaign.get("name", ""),
                "status": campaign.get("status", ""),
                "impressions": int(metrics.get("impressions", 0)),
                "clicks": clicks,
                "cost": round(cost, 2),
                "conversions": conversions,
                "revenue": round(float(metrics.get("conversionsValue", 0)), 2),
                "cpc": round(cost / clicks, 2) if clicks else 0.0,
                "cpa": round(cost / conversions, 2) if conversions else None,
            }
        )
    return out


def pause_campaign(customer_id: str, campaign_id: str) -> dict:
    """
    Set a campaign to PAUSED.

    A write. In mock mode it returns the same mutate response shape without
    touching anything — which is the point of keeping writes on the same path as
    reads: the script that spends money is the script that was tested.
    """
    return call(
        PLATFORM,
        "pause_campaign",
        base_url_env=BASE_URL_ENV,
        token_env=TOKEN_ENV,
        path=f"customers/{customer_id}/campaigns:mutate",
        payload={
            "operations": [
                {
                    "update": {
                        "resourceName": f"customers/{customer_id}/campaigns/{campaign_id}",
                        "status": "PAUSED",
                    },
                    "updateMask": "status",
                }
            ]
        },
    )


__all__ = ["campaign_performance", "pause_campaign", "AdsError"]
