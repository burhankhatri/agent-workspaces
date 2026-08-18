# Marketing Automation workspace

Cross-platform reporting and optimisation over **Google Ads** and **Meta Ads**.

## How the connections work

The two connections registered on this workspace point at the real production
endpoints:

| Connection | Base URL | Env injected |
|---|---|---|
| `google-ads` | `https://googleads.googleapis.com/v18` | `GOOGLE_ADS_BASE_URL`, `GOOGLE_ADS_TOKEN` |
| `meta-ads` | `https://graph.facebook.com/v21.0` | `META_ADS_BASE_URL`, `META_ADS_TOKEN` |

`lib/ads_transport.py` decides where a call actually goes:

- **`MARKETING_MOCK=1`** (default) — served from `fixtures/`, which hold real
  API response shapes: Google's batched `searchStream` with `costMicros`, Meta's
  stringified metrics with conversions inside `actions[]`.
- **`MARKETING_MOCK=0`** — the same call goes over HTTPS to the connection's
  base URL with its token.

Both paths take the same arguments, return the same shapes and raise the same
`AdsError`, so going live is an environment change, not a code change: set
`MARKETING_MOCK=0` and replace the connection secrets with real credentials.

The fixtures are deliberately in the platforms' own response shapes. A fixture
that invents its own shape proves nothing about the real integration — the
normalising in `lib/google_ads.py` and `lib/meta_ads.py` is the part most likely
to be wrong against production, so it is the part the mock exercises.

## Layout

```
workspace.yaml                                   name, agent, system prompt
.claude/skills/marketing-automation/SKILL.md     how the agent uses the scripts
lib/ads_transport.py                             mock-or-live transport
lib/google_ads.py                                Google Ads client + normaliser
lib/meta_ads.py                                  Meta Ads client + normaliser
fixtures/google_ads/*.json                       canned responses, real shapes
fixtures/meta_ads/*.json
scripts/ads_report.py                            cross-platform report
```

## Try it

```bash
python scripts/ads_report.py
python scripts/ads_report.py --platform meta --days 7
python scripts/ads_report.py --json
```
