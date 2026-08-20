#!/usr/bin/env python3
"""
Push qualified, enriched Lead Engine leads into an Instantly campaign.

The two systems key on different things and neither knows about the other:

  Lead Engine   one record = one BUILDING, keyed by Google place_id
  Instantly     one record = one PERSON,   keyed by email

So this is a fan-out, not a copy: one 400,000 sq ft warehouse becomes three
Instantly leads if enrichment found three decision-makers. It is also a
narrowing — most "qualified" leads are not mailable, because qualification
measures the building and says nothing about whether anyone's email is known.

Dry run by default. Nothing is written anywhere without --apply.

  python3 scripts/push_to_instantly.py                      # what would go
  python3 scripts/push_to_instantly.py --campaign <id> --apply

Only the standard library is used, so this runs in a bare sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60

# Instantly campaign.status, from the v2 API.
CAMPAIGN_STATUS = {
    0: "draft",
    1: "ACTIVE",
    2: "paused",
    3: "completed",
    4: "running subsequences",
}

# Instantly caps a bulk add at 1000 leads per request.
INSTANTLY_BULK_MAX = 1000


class Fatal(Exception):
    """Something the operator has to fix; printed without a traceback."""


# ──────────────────────────── plumbing ────────────────────────────


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise Fatal(f"{method} {url} -> HTTP {e.code}\n{detail}") from None
    except urllib.error.URLError as e:
        raise Fatal(f"{method} {url} unreachable: {e.reason}") from None
    return json.loads(raw) if raw else {}


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise Fatal(
            f"${name} is not set. It comes from this workspace's connections — "
            f"check the Connections panel."
        )
    return value.strip()


# ──────────────────────────── the mapping ────────────────────────────


def split_name(full_name: str) -> tuple[str, str]:
    """
    "Erik Rockholt" -> ("Erik", "Rockholt")

    The Lead Engine stores one `full_name`; Instantly's sequences interpolate
    {{firstName}} on its own. Getting this wrong is visible in the send: the
    email opens "hi Erik Rockholt," which reads like a mail merge, which is
    exactly the impression cold outreach cannot afford.

    Everything after the first token is the surname. That mis-splits compound
    forenames, but the first token — the only part the sequences use — is right.
    """
    parts = (full_name or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def to_instantly_lead(lead: dict, contact: dict) -> dict:
    """One Lead Engine building + one enriched contact -> one Instantly lead."""
    first, last = split_name(contact.get("full_name", ""))

    # custom_variables values must be primitives — the API rejects nested
    # objects and arrays. Drop empties so the sequences can test for presence.
    custom = {
        "place_id": lead.get("place_id"),
        "sq_ft": lead.get("sq_ft"),
        "building_address": lead.get("address"),
        "city": lead.get("city"),
        "zip": lead.get("zip"),
        "maps_link": lead.get("maps_link"),
        "footprint_source": lead.get("footprint_source"),
        "linkedin_url": contact.get("linkedin_url"),
        "contact_source": contact.get("source_provider"),
    }
    custom = {k: v for k, v in custom.items() if v not in (None, "", [])}

    return {
        "email": contact["email"].strip().lower(),
        "first_name": first,
        "last_name": last,
        "job_title": contact.get("title") or None,
        "company_name": lead.get("company") or None,
        "website": lead.get("website") or None,
        "phone": contact.get("phone") or lead.get("phone") or None,
        "custom_variables": custom,
    }


def emailable_contacts(lead: dict) -> list[dict]:
    return [
        c
        for c in (lead.get("contacts") or [])
        if isinstance(c, dict) and (c.get("email") or "").strip()
    ]


# ──────────────────────────── the steps ────────────────────────────


def fetch_candidates(base: str, token: str, args) -> list[dict]:
    """
    Leads that are worth mailing.

    Each filter is load-bearing:

      verdict=qualified   the building is big enough and standalone
      in_crm=false        Live Energy does NOT already own this account.
                          /api/leads returns in_crm leads by default, so
                          omitting this mails existing customers.
      enriched=true       enrichment has run; without it contacts[] is empty
      work_status=new     not already pushed by an earlier run
    """
    params = {
        "verdict": "qualified",
        "in_crm": "false",
        "enriched": "true",
        "limit": str(args.limit),
        "sort": "sq_ft",
        "order": "desc",
    }
    if not args.include_pushed:
        params["work_status"] = "new"
    if args.zip:
        params["zip"] = args.zip
    if args.min_sqft:
        params["min_sqft"] = str(args.min_sqft)
    if args.verified_only:
        params["review_status"] = "verified"

    url = f"{base}/api/leads?" + urllib.parse.urlencode(params)
    payload = _request("GET", url, token)
    return payload.get("leads", [])


def build_batch(leads: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """
    Flatten buildings to people, dropping anything unmailable.

    Returns (instantly_leads, source_leads_used, stats). A lead is only counted
    as used if at least one of its contacts survived — otherwise marking it
    in_progress would hide a building that nobody has actually contacted.
    """
    out: list[dict] = []
    used: list[dict] = []
    seen_emails: set[str] = set()
    stats = {"no_contacts": 0, "duplicate_email": 0}

    for lead in leads:
        contacts = emailable_contacts(lead)
        if not contacts:
            stats["no_contacts"] += 1
            continue
        added_for_lead = 0
        for contact in contacts:
            mapped = to_instantly_lead(lead, contact)
            # One person can sit on two buildings (shared complexes are common
            # in this data). Mailing them twice from one push is our mistake,
            # not Instantly's, so collapse it here.
            if mapped["email"] in seen_emails:
                stats["duplicate_email"] += 1
                continue
            seen_emails.add(mapped["email"])
            out.append(mapped)
            added_for_lead += 1
        if added_for_lead:
            used.append(lead)

    return out, used, stats


def describe_campaign(inst_base: str, inst_token: str, campaign_id: str) -> dict:
    url = f"{inst_base}/campaigns/{campaign_id}"
    return _request("GET", url, inst_token)


def push(inst_base: str, inst_token: str, campaign_id: str, batch: list[dict], args) -> dict:
    body = {
        "campaign_id": campaign_id,
        "leads": batch,
        # Two independent guards. skip_if_in_workspace is the important one:
        # this account has ~85 sending mailboxes across a dozen domains, and a
        # contact enrolled in two campaigns gets two sequences from two
        # different Live Energy addresses. That reads as spam to the recipient
        # and to the receiving mail server.
        "skip_if_in_workspace": True,
        "skip_if_in_campaign": True,
    }
    if args.verify_emails:
        body["verify_leads_on_import"] = True
    return _request("POST", f"{inst_base}/leads/add", inst_token, body)


def mark_in_progress(base: str, token: str, leads: list[dict], by: str) -> dict:
    """
    Close the loop so the next run does not re-push these.

    in_progress, not done: the campaign has started, it has not finished. done
    is for a lead whose outreach has actually concluded.
    """
    place_ids = [l["place_id"] for l in leads if l.get("place_id")]
    if not place_ids:
        return {"updated": 0}
    body = {
        "place_ids": place_ids,
        "patch": {"work_status": "in_progress", "by": by},
    }
    return _request("POST", f"{base}/api/leads/bulk", token, body)


# ──────────────────────────── output ────────────────────────────


def print_preview(batch: list[dict], used: list[dict], source: list[dict], stats: dict) -> None:
    unreviewed = sum(1 for l in used if (l.get("review_status") or "unreviewed") == "unreviewed")

    print(f"\n  Lead Engine returned {len(source)} qualified, enriched, non-CRM leads.")
    print(f"  {len(used)} of them have at least one contact with an email address.")
    if stats["no_contacts"]:
        print(f"  {stats['no_contacts']} dropped: enrichment ran but found no email.")
    if stats["duplicate_email"]:
        print(f"  {stats['duplicate_email']} dropped: same person on more than one building.")
    print(f"\n  → {len(batch)} people would be added, across {len(used)} companies.\n")

    if unreviewed:
        print(f"  {unreviewed} of these {len(used)} buildings are still review_status=unreviewed.")
        print("  No human has checked them. Approving this push is that check.\n")

    by_company: dict[str, list[dict]] = {}
    for person in batch:
        by_company.setdefault(person.get("company_name") or "(no company)", []).append(person)

    for company, people in sorted(by_company.items(), key=lambda kv: -len(kv[1])):
        sq = next(
            (p["custom_variables"].get("sq_ft") for p in people if p.get("custom_variables")),
            None,
        )
        size = f"{int(sq):,} sq ft" if isinstance(sq, (int, float)) else "size unknown"
        print(f"  {company}  ({size})")
        for p in people:
            name = " ".join(x for x in [p["first_name"], p["last_name"]] if x) or "(no name)"
            title = p.get("job_title") or "no title"
            print(f"      {p['email']:<40} {name} — {title}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", help="Instantly campaign id (required with --apply)")
    ap.add_argument("--zip", help="only leads in this ZIP")
    ap.add_argument("--min-sqft", type=int, help="floor on building size")
    ap.add_argument("--limit", type=int, default=100, help="max leads to read (default 100)")
    ap.add_argument("--verified-only", action="store_true",
                    help="only leads a human marked review_status=verified")
    ap.add_argument("--include-pushed", action="store_true",
                    help="also consider leads already marked in_progress/done")
    ap.add_argument("--verify-emails", action="store_true",
                    help="have Instantly verify each address on import (costs credits)")
    ap.add_argument("--by", default="switchboard", help="audit trail actor")
    ap.add_argument("--apply", action="store_true", help="actually push. Sends real email.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    gtm_base = env("GTM_BASE_URL").rstrip("/")
    gtm_token = env("GTM_TOKEN")

    source = fetch_candidates(gtm_base, gtm_token, args)
    batch, used, stats = build_batch(source)

    if args.json and not args.apply:
        print(json.dumps({"would_add": len(batch), "companies": len(used),
                          "dropped": stats, "leads": batch}, indent=2))
        return 0

    if not args.apply:
        print_preview(batch, used, source, stats)
        if not batch:
            print("  Nothing to push.\n")
            return 0
        print("  Dry run — nothing was written.")
        print("  To send: --campaign <id> --apply\n")
        return 0

    # ── from here on, this writes ──
    if not batch:
        raise Fatal("Nothing to push — refusing to call Instantly with an empty batch.")
    if not args.campaign:
        raise Fatal("--apply needs --campaign <id>. Refusing to guess which campaign.")
    if len(batch) > INSTANTLY_BULK_MAX:
        raise Fatal(
            f"{len(batch)} leads exceeds Instantly's {INSTANTLY_BULK_MAX}-per-request cap. "
            f"Narrow with --zip or --limit."
        )

    inst_base = env("INSTANTLY_BASE_URL").rstrip("/")
    inst_token = env("INSTANTLY_TOKEN")

    campaign = describe_campaign(inst_base, inst_token, args.campaign)
    status = campaign.get("status")
    label = CAMPAIGN_STATUS.get(status, f"unknown({status})")
    print(f"\n  Campaign: {campaign.get('name')}  [{label}]")
    print(f"  Adding {len(batch)} people across {len(used)} companies.")
    if status == 1:
        print("  This campaign is ACTIVE — these people enter the sending queue immediately.")
    print()

    result = push(inst_base, inst_token, args.campaign, batch, args)
    print("  Instantly response:")
    for key in ("leads_uploaded", "skipped_count", "duplicated_leads",
                "invalid_email_count", "in_blocklist", "total_sent"):
        if key in result:
            print(f"    {key:<22} {result[key]}")

    uploaded = result.get("leads_uploaded", 0)
    if uploaded:
        marked = mark_in_progress(gtm_base, gtm_token, used, args.by)
        print(f"\n  Marked {marked.get('updated', 0)} Lead Engine leads work_status=in_progress.")
    else:
        print("\n  Nothing uploaded — Lead Engine left untouched so a retry is clean.")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fatal as e:
        print(f"\n  {e}\n", file=sys.stderr)
        sys.exit(1)
