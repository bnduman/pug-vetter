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
        data = resp.json()
        _token["value"] = data["access_token"]
        _token["expiry"] = time.time() + data.get("expires_in", 3600)
        return _token["value"]


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
    """Run a GraphQL query and return its `data` object, raising WCLError on failure."""
    resp = _post(query, variables)
    if resp.status_code == 401:
        # Token may have expired early; drop it and retry once.
        _token["value"] = None
        resp = _post(query, variables)
    if resp.status_code == 429:
        raise WCLError("Rate limited by Warcraft Logs. Wait a bit and try again.")
    if resp.status_code != 200:
        raise WCLError(f"Warcraft Logs returned HTTP {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
        raise WCLError(f"Query error: {msgs}")
    return payload.get("data") or {}
