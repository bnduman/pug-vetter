"""Thin synchronous Warcraft Logs API v2 client.

Handles the OAuth2 client-credentials token (fetch + cache + refresh) and
POSTing GraphQL queries. One module-level requests.Session is reused.
"""
import threading
import time

import requests

from . import config


class WCLError(Exception):
    """Any failure talking to Warcraft Logs, with a user-friendly message."""


_token = {"value": None, "expiry": 0.0}
_lock = threading.Lock()
_session = requests.Session()

# How many times to wait-and-retry a 429 before giving up.
_RATE_LIMIT_RETRIES = 2
# Fallback backoff (seconds) when WCL doesn't send a Retry-After header.
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
# Never block a request thread longer than this on a single 429; a larger
# Retry-After means we surface the rate-limit error immediately instead.
_MAX_RETRY_WAIT = 30.0


def _json(resp):
    """resp.json(), but a non-JSON body (e.g. an HTML maintenance page) becomes
    a friendly WCLError instead of an unwrapped JSONDecodeError/500."""
    try:
        return resp.json()
    except ValueError as exc:  # requests' JSONDecodeError subclasses ValueError
        raise WCLError(
            f"Warcraft Logs returned a non-JSON response (HTTP {resp.status_code}). "
            "It may be down for maintenance — please try again shortly."
        ) from exc


def _retry_after(resp, attempt: int) -> float:
    """Seconds to wait after a 429: honor the Retry-After header, else back off."""
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass  # Retry-After can be an HTTP-date; fall back to our schedule
    return _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]


def _get_token() -> str:
    with _lock:
        if _token["value"] and time.time() < _token["expiry"] - 60:
            return _token["value"]
        if not config.WCL_CLIENT_ID or not config.WCL_CLIENT_SECRET:
            raise WCLError(
                "Warcraft Logs credentials are not configured. Copy .env.example "
                "to .env and set WCL_CLIENT_ID and WCL_CLIENT_SECRET (see README)."
            )
        try:
            resp = _session.post(
                config.WCL_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(config.WCL_CLIENT_ID, config.WCL_CLIENT_SECRET),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise WCLError(f"Could not reach Warcraft Logs: {exc}") from exc
        if resp.status_code != 200:
            raise WCLError(
                f"Token request failed ({resp.status_code}). "
                "Check that your client id/secret are correct."
            )
        data = _json(resp)
        token = data.get("access_token")
        if not token:
            raise WCLError("Warcraft Logs token response did not contain an access_token.")
        _token["value"] = token
        _token["expiry"] = time.time() + data.get("expires_in", 3600)
        return token


def _post(query: str, variables: dict | None):
    token = _get_token()
    try:
        return _session.post(
            config.WCL_API_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise WCLError(f"Could not reach Warcraft Logs: {exc}") from exc


def post_graphql(query: str, variables: dict | None = None) -> dict:
    """Run a GraphQL query and return its `data` object, raising WCLError on failure.

    Retries once on 401 (expired token) and up to `_RATE_LIMIT_RETRIES` times on
    429 (rate limit), waiting per the Retry-After header or a backoff schedule.
    """
    token_retried = False
    rate_attempt = 0
    while True:
        resp = _post(query, variables)

        if resp.status_code == 401 and not token_retried:
            # Token may have expired early; drop it (under the lock) and retry once.
            with _lock:
                _token["value"] = None
            token_retried = True
            continue

        if resp.status_code == 429:
            wait = _retry_after(resp, rate_attempt)
            if rate_attempt < _RATE_LIMIT_RETRIES and wait <= _MAX_RETRY_WAIT:
                time.sleep(wait)
                rate_attempt += 1
                continue
            raise WCLError("Rate limited by Warcraft Logs. Wait a bit and try again.")

        if resp.status_code != 200:
            raise WCLError(f"Warcraft Logs returned HTTP {resp.status_code}: {resp.text[:300]}")

        payload = _json(resp)
        if payload.get("errors"):
            msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
            raise WCLError(f"Query error: {msgs}")
        return payload.get("data") or {}
