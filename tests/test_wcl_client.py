"""Tests for the Warcraft Logs transport layer: token caching/refresh, the
401 retry, 429 backoff, JSON guarding, and error wrapping.

Nothing here touches the network — the module-level requests.Session is
monkeypatched, and time.sleep is neutered so retries don't actually wait.
"""
import time

import pytest
import requests

from app import wcl_client
from app.wcl_client import WCLError


class FakeResp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status_code=200, json_data=None, text="", headers=None, bad_json=False):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.headers = headers or {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            # requests' real JSONDecodeError subclasses ValueError, which is what
            # wcl_client._json catches.
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Valid creds, an empty token, and instant (recorded) sleeps for every test."""
    monkeypatch.setattr(wcl_client.config, "WCL_CLIENT_ID", "id")
    monkeypatch.setattr(wcl_client.config, "WCL_CLIENT_SECRET", "secret")
    wcl_client._token["value"] = None
    wcl_client._token["expiry"] = 0.0
    sleeps = []
    monkeypatch.setattr(wcl_client.time, "sleep", lambda s: sleeps.append(s))
    yield sleeps
    wcl_client._token["value"] = None
    wcl_client._token["expiry"] = 0.0


def seed_token():
    wcl_client._token["value"] = "seeded"
    wcl_client._token["expiry"] = time.time() + 9999


def router(data_responses):
    """A fake _session.post: the OAuth endpoint always mints a fresh token, while
    the data endpoint yields the supplied responses in order. Returns (fn, calls)."""
    data_iter = iter(data_responses)
    calls = {"token": 0, "data": 0}

    def fake_post(url, **kw):
        if url == wcl_client.config.WCL_TOKEN_URL:
            calls["token"] += 1
            return FakeResp(200, {"access_token": f"tok-{calls['token']}", "expires_in": 3600})
        calls["data"] += 1
        return next(data_iter)

    return fake_post, calls


# --- token fetch / cache / refresh -----------------------------------------

def test_token_fetched_then_cached(monkeypatch):
    fake_post, calls = router([])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client._get_token() == "tok-1"
    assert wcl_client._get_token() == "tok-1"  # served from cache
    assert calls["token"] == 1


def test_token_refreshes_when_expired(monkeypatch):
    fake_post, calls = router([])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    wcl_client._get_token()
    wcl_client._token["expiry"] = time.time() - 1  # force expiry
    assert wcl_client._get_token() == "tok-2"
    assert calls["token"] == 2


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr(wcl_client.config, "WCL_CLIENT_ID", "")
    monkeypatch.setattr(wcl_client.config, "WCL_CLIENT_SECRET", "")
    with pytest.raises(WCLError, match="credentials are not configured"):
        wcl_client._get_token()


def test_token_http_error_raises(monkeypatch):
    monkeypatch.setattr(wcl_client._session, "post", lambda url, **kw: FakeResp(401))
    with pytest.raises(WCLError, match="Token request failed"):
        wcl_client._get_token()


def test_token_non_json_raises(monkeypatch):
    monkeypatch.setattr(wcl_client._session, "post",
                        lambda url, **kw: FakeResp(200, bad_json=True, text="<html>"))
    with pytest.raises(WCLError, match="non-JSON"):
        wcl_client._get_token()


def test_token_without_access_token_raises(monkeypatch):
    monkeypatch.setattr(wcl_client._session, "post",
                        lambda url, **kw: FakeResp(200, {"expires_in": 3600}))
    with pytest.raises(WCLError, match="did not contain an access_token"):
        wcl_client._get_token()


def test_token_network_error_wrapped(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError("dns go boom")
    monkeypatch.setattr(wcl_client._session, "post", boom)
    with pytest.raises(WCLError, match="Could not reach Warcraft Logs"):
        wcl_client._get_token()


# --- post_graphql happy paths ----------------------------------------------

def test_post_graphql_returns_data(monkeypatch):
    seed_token()
    fake_post, _ = router([FakeResp(200, {"data": {"hello": "world"}})])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client.post_graphql("query") == {"hello": "world"}


def test_post_graphql_empty_data_becomes_dict(monkeypatch):
    seed_token()
    fake_post, _ = router([FakeResp(200, {"data": None})])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client.post_graphql("query") == {}


def test_post_graphql_graphql_errors_raise(monkeypatch):
    seed_token()
    fake_post, _ = router([FakeResp(200, {"errors": [{"message": "bad field"}]})])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="bad field"):
        wcl_client.post_graphql("query")


# --- post_graphql failure / retry behavior ---------------------------------

def test_post_graphql_401_clears_token_and_retries_once(monkeypatch):
    seed_token()
    fake_post, calls = router([FakeResp(401), FakeResp(200, {"data": {"ok": 1}})])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client.post_graphql("query") == {"ok": 1}
    assert calls["data"] == 2   # original + one retry
    assert calls["token"] == 1  # token re-fetched after being cleared


def test_post_graphql_401_twice_gives_up(monkeypatch):
    seed_token()
    fake_post, calls = router([FakeResp(401), FakeResp(401, text="nope")])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="HTTP 401"):
        wcl_client.post_graphql("query")
    assert calls["data"] == 2  # only one 401 retry, then surfaced


def test_post_graphql_429_backs_off_then_succeeds(monkeypatch, fresh_state):
    seed_token()
    fake_post, calls = router([
        FakeResp(429), FakeResp(429), FakeResp(200, {"data": {"ok": 1}}),
    ])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client.post_graphql("query") == {"ok": 1}
    assert calls["data"] == 3
    assert fresh_state == [1.0, 2.0]  # two backoff sleeps from the schedule


def test_post_graphql_429_exhausts_retries(monkeypatch):
    seed_token()
    fake_post, calls = router([FakeResp(429)] * 4)
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="Rate limited"):
        wcl_client.post_graphql("query")
    assert calls["data"] == 1 + wcl_client._RATE_LIMIT_RETRIES  # initial + 2 retries


def test_post_graphql_429_honors_retry_after_header(monkeypatch, fresh_state):
    seed_token()
    fake_post, _ = router([
        FakeResp(429, headers={"Retry-After": "7"}),
        FakeResp(200, {"data": {"ok": 1}}),
    ])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    assert wcl_client.post_graphql("query") == {"ok": 1}
    assert fresh_state == [7.0]  # header wins over the backoff schedule


def test_post_graphql_429_huge_retry_after_fails_fast(monkeypatch, fresh_state):
    seed_token()
    fake_post, calls = router([FakeResp(429, headers={"Retry-After": "3600"})])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="Rate limited"):
        wcl_client.post_graphql("query")
    assert calls["data"] == 1   # no retry attempted...
    assert fresh_state == []     # ...and we never slept for an hour


def test_post_graphql_http_error_includes_body(monkeypatch):
    seed_token()
    fake_post, _ = router([FakeResp(503, text="maintenance window")])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="HTTP 503.*maintenance window"):
        wcl_client.post_graphql("query")


def test_post_graphql_non_json_body_wrapped(monkeypatch):
    seed_token()
    fake_post, _ = router([FakeResp(200, bad_json=True, text="<html>down</html>")])
    monkeypatch.setattr(wcl_client._session, "post", fake_post)
    with pytest.raises(WCLError, match="non-JSON"):
        wcl_client.post_graphql("query")


def test_post_graphql_network_error_wrapped(monkeypatch):
    seed_token()

    def boom(url, **kw):
        if url == wcl_client.config.WCL_API_URL:
            raise requests.Timeout("slow")
        return FakeResp(200, {"access_token": "t", "expires_in": 3600})
    monkeypatch.setattr(wcl_client._session, "post", boom)
    with pytest.raises(WCLError, match="Could not reach Warcraft Logs"):
        wcl_client.post_graphql("query")


# --- _retry_after unit -----------------------------------------------------

def test_retry_after_parses_numeric_header():
    assert wcl_client._retry_after(FakeResp(429, headers={"Retry-After": "12"}), 0) == 12.0


def test_retry_after_falls_back_on_http_date():
    # An HTTP-date Retry-After isn't a float; we fall back to the backoff schedule.
    resp = FakeResp(429, headers={"Retry-After": "Wed, 21 Oct 2025 07:28:00 GMT"})
    assert wcl_client._retry_after(resp, 0) == wcl_client._BACKOFF_SECONDS[0]


def test_retry_after_uses_schedule_then_caps():
    assert wcl_client._retry_after(FakeResp(429), 0) == wcl_client._BACKOFF_SECONDS[0]
    assert wcl_client._retry_after(FakeResp(429), 99) == wcl_client._BACKOFF_SECONDS[-1]
