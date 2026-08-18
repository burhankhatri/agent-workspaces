"""
Transport for the ad-platform clients.

The point of this module is that nothing above it knows whether the data came
from Google/Meta or from a fixture. The clients build a request; this decides
where it goes.

MARKETING_MOCK=1  -> serve the committed fixtures in ../fixtures
MARKETING_MOCK=0  -> real HTTP against the connection's base URL and token

Both paths take the same arguments, return the same shapes, and raise the same
errors, so "make it live" is an environment change rather than a code change.
The fixtures are stored in the real APIs' response shapes for exactly that
reason — a fixture that invents its own shape proves nothing about the real
integration.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Kept as a function rather than a module constant so a test can flip the
# environment variable without re-importing.
def is_mock() -> bool:
    return os.environ.get("MARKETING_MOCK", "1") not in ("0", "", "false", "False")


class AdsError(RuntimeError):
    """A platform call failed. Same type in mock and live mode."""


def _fixture(platform: str, name: str) -> Any:
    path = FIXTURES / platform / f"{name}.json"
    if not path.exists():
        raise AdsError(
            f"No fixture for {platform}/{name}. "
            f"Add {path.relative_to(FIXTURES.parent)} or set MARKETING_MOCK=0."
        )
    return json.loads(path.read_text())


def _http(url: str, token: str, payload: dict | None, headers: dict[str, str]) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise AdsError(f"{url} returned {e.code}: {e.read()[:400]!r}") from e
    except urllib.error.URLError as e:
        raise AdsError(f"{url} unreachable: {e.reason}") from e


def call(
    platform: str,
    fixture: str,
    *,
    base_url_env: str,
    token_env: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """
    One platform call.

    `fixture` names the canned response used in mock mode; `path` is appended to
    the connection's base URL in live mode.
    """
    if is_mock():
        return _fixture(platform, fixture)

    base = os.environ.get(base_url_env)
    token = os.environ.get(token_env)
    if not base:
        raise AdsError(f"{base_url_env} is not set — is the connection attached to this workspace?")
    if not token:
        raise AdsError(f"{token_env} is not set — the connection has no secret.")

    return _http(f"{base.rstrip('/')}/{path.lstrip('/')}", token, payload, headers or {})
