#!/usr/bin/env python3
"""
Cross-platform ad performance report.

Pulls campaign performance from Google Ads and Meta Ads, normalises both into
one row shape, and prints a ranked table plus a JSON blob the agent can reason
over.

  python scripts/ads_report.py                      # both platforms, 30 days
  python scripts/ads_report.py --days 7
  python scripts/ads_report.py --platform google
  python scripts/ads_report.py --json               # machine-readable only

The two APIs disagree about almost everything — Google returns cost in millionths
and batches its rows, Meta returns every number as a string and buries
conversions in an actions[] array — so the normalising lives in lib/ and every
script above it sees one shape.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import google_ads  # noqa: E402
import meta_ads  # noqa: E402
from ads_transport import AdsError  # noqa: E402

GOOGLE_CUSTOMER_ID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "4820193756")
META_AD_ACCOUNT_ID = os.environ.get("META_ADS_ACCOUNT_ID", "918204571")


def collect(platform: str, days: int) -> list[dict]:
    rows: list[dict] = []
    if platform in ("google", "both"):
        rows += google_ads.campaign_performance(GOOGLE_CUSTOMER_ID, days=days)
    if platform in ("meta", "both"):
        rows += meta_ads.campaign_performance(META_AD_ACCOUNT_ID, days=days)
    return rows


def summarise(rows: list[dict]) -> dict:
    spend = sum(r["cost"] for r in rows)
    conversions = sum(r["conversions"] for r in rows)
    revenue = sum(r["revenue"] for r in rows)
    return {
        "campaigns": len(rows),
        "spend": round(spend, 2),
        "clicks": sum(r["clicks"] for r in rows),
        "impressions": sum(r["impressions"] for r in rows),
        "conversions": round(conversions, 1),
        "revenue": round(revenue, 2),
        "blended_cpa": round(spend / conversions, 2) if conversions else None,
        "roas": round(revenue / spend, 2) if spend else None,
    }


def table(rows: list[dict]) -> str:
    header = f"{'PLATFORM':<12}{'CAMPAIGN':<46}{'SPEND':>11}{'CONV':>7}{'CPA':>9}{'ROAS':>7}"
    lines = [header, "-" * len(header)]
    for r in sorted(rows, key=lambda x: x["cost"], reverse=True):
        roas = r["revenue"] / r["cost"] if r["cost"] else 0
        cpa = f"${r['cpa']:,.2f}" if r["cpa"] is not None else "—"
        name = r["campaign_name"][:44]
        lines.append(
            f"{r['platform']:<12}{name:<46}${r['cost']:>10,.2f}"
            f"{r['conversions']:>7.0f}{cpa:>9}{roas:>7.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Cross-platform ad performance report")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--platform", choices=["google", "meta", "both"], default="both")
    p.add_argument("--json", action="store_true", help="print JSON only")
    args = p.parse_args()

    try:
        rows = collect(args.platform, args.days)
    except AdsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    summary = summarise(rows)
    payload = {"window_days": args.days, "summary": summary, "campaigns": rows}

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"\nAd performance — last {args.days} days\n")
    print(table(rows))
    print(
        f"\n{summary['campaigns']} campaigns  ·  ${summary['spend']:,.2f} spend  ·  "
        f"{summary['conversions']:.0f} conversions  ·  "
        f"blended CPA ${summary['blended_cpa']:,.2f}  ·  ROAS {summary['roas']}x\n"
    )
    print("JSON:")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
