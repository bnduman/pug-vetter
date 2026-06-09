"""Tests for the Flask layer: input validation, the TTL/LRU cache, error
mapping to HTTP status, and the _do_vet / _fetch_enchants orchestration.

The WCL transport (post_graphql) and zone resolution are monkeypatched, so no
network is touched.
"""
import json
import pathlib

import pytest

from app import main
from app.wcl_client import WCLError

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def client():
    main.app.testing = True
    return main.app.test_client()


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    main._cache.clear()
    # Don't let a developer's real .env DEFAULT_REALM leak into validation tests.
    monkeypatch.setattr(main.config, "DEFAULT_REALM", "")
    monkeypatch.setattr(main.config, "DEFAULT_REGION", "US")
    yield
    main._cache.clear()


# --- /api/vet input validation ---------------------------------------------

def test_vet_requires_name(client):
    r = client.get("/api/vet")
    assert r.status_code == 400
    assert "name" in r.get_json()["error"].lower()


def test_vet_requires_realm(client):
    r = client.get("/api/vet?name=Foo")
    assert r.status_code == 400
    assert "realm" in r.get_json()["error"].lower()


def test_vet_uses_default_realm_and_uppercases_region(client, monkeypatch):
    monkeypatch.setattr(main.config, "DEFAULT_REALM", "Spineshatter")
    seen = {}

    def fake(name, realm, region):
        seen.update(name=name, realm=realm, region=region)
        return {"found": True}
    monkeypatch.setattr(main, "_do_vet", fake)

    r = client.get("/api/vet?name=Foo&region=eu")
    assert r.status_code == 200
    assert seen == {"name": "Foo", "realm": "Spineshatter", "region": "EU"}


# --- /api/vet caching & error mapping --------------------------------------

def test_vet_caches_second_lookup(client, monkeypatch):
    calls = []

    def fake(name, realm, region):
        calls.append((name, realm, region))
        return {"found": True, "name": name}
    monkeypatch.setattr(main, "_do_vet", fake)

    r1 = client.get("/api/vet?name=Foo&realm=Spineshatter&region=us")
    r2 = client.get("/api/vet?name=foo&realm=Spineshatter&region=US")  # same cache key
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json() == r2.get_json()
    assert len(calls) == 1  # second served from cache


def test_vet_distinct_realms_not_shared(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_do_vet",
                        lambda n, r, reg: calls.append((n, r, reg)) or {"found": True})
    client.get("/api/vet?name=Foo&realm=Spineshatter")
    client.get("/api/vet?name=Foo&realm=Nekrosh")
    assert len(calls) == 2


def test_vet_wcl_error_returns_502_and_is_not_cached(client, monkeypatch):
    calls = []

    def boom(name, realm, region):
        calls.append(1)
        raise WCLError("Warcraft Logs is down")
    monkeypatch.setattr(main, "_do_vet", boom)

    r1 = client.get("/api/vet?name=Foo&realm=Spineshatter")
    assert r1.status_code == 502
    assert r1.get_json()["error"] == "Warcraft Logs is down"
    client.get("/api/vet?name=Foo&realm=Spineshatter")  # error not cached -> re-runs
    assert len(calls) == 2


# --- cache helpers (TTL + LRU bound) ---------------------------------------

def test_cache_expires_after_ttl(monkeypatch):
    monkeypatch.setattr(main.config, "CACHE_TTL_SECONDS", 100)
    t = [1000.0]
    monkeypatch.setattr(main.time, "time", lambda: t[0])
    main._cache_set("k", {"v": 1})
    assert main._cache_get("k") == {"v": 1}
    t[0] += 101  # past TTL
    assert main._cache_get("k") is None
    assert "k" not in main._cache  # expired entry is dropped on read


def test_cache_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(main.config, "CACHE_TTL_SECONDS", 10_000)
    monkeypatch.setattr(main, "_CACHE_MAX_ENTRIES", 3)
    for i in range(3):
        main._cache_set(f"k{i}", {"i": i})
    main._cache_get("k0")          # touch k0 so k1 is now the LRU
    main._cache_set("k3", {"i": 3})  # over cap -> evict LRU (k1)
    assert set(main._cache) == {"k0", "k2", "k3"}
    assert len(main._cache) == 3


# --- _do_vet orchestration -------------------------------------------------

def test_do_vet_character_not_found(monkeypatch):
    monkeypatch.setattr(main, "get_raid_zones", lambda: [{"id": 1007, "name": "Karazhan"}])
    monkeypatch.setattr(main, "post_graphql",
                        lambda *a, **k: {"characterData": {"character": None}})
    out = main._do_vet("Ghost", "Spineshatter", "US")
    assert out == {"found": False, "name": "Ghost", "realm": "Spineshatter", "region": "US"}


def test_do_vet_builds_scorecard(monkeypatch):
    char = {
        "name": "Foo",
        "classID": 2,
        "z1007": {
            "rankings": [
                {"encounter": {"name": "Attumen"}, "totalKills": 3, "rankPercent": 80},
                {"encounter": {"name": "Curator"}, "totalKills": 0, "rankPercent": "-"},
            ],
            "bestPerformanceAverage": 80,
        },
        "recentReports": {"data": [{"code": "abc123", "startTime": 1717000000000}]},
    }
    monkeypatch.setattr(main, "get_raid_zones", lambda: [{"id": 1007, "name": "Karazhan"}])
    monkeypatch.setattr(main, "post_graphql",
                        lambda *a, **k: {"characterData": {"character": char}})
    monkeypatch.setattr(main, "_fetch_enchants",
                        lambda code, name: {"missing_required": 1, "slots": [], "avg_item_level": 110.0})

    out = main._do_vet("Foo", "Spineshatter", "US")
    assert out["found"] is True
    assert out["classID"] == 2
    assert out["last_log"] == 1717000000000
    assert out["enchants"]["missing_required"] == 1
    (raid,) = out["raids"]
    assert raid["name"] == "Karazhan"
    assert raid["cleared"] == 1 and raid["total"] == 2
    assert raid["best_parse"] == 80
    assert raid["tier"] == "epic"  # 80 -> epic band
    assert raid["color"] == "#a335ee"


def test_do_vet_swallows_enchant_failure(monkeypatch):
    char = {
        "name": "Foo", "classID": 2, "z1007": None,
        "recentReports": {"data": [{"code": "abc", "startTime": 1}]},
    }
    monkeypatch.setattr(main, "get_raid_zones", lambda: [{"id": 1007, "name": "Karazhan"}])
    monkeypatch.setattr(main, "post_graphql",
                        lambda *a, **k: {"characterData": {"character": char}})

    def boom(code, name):
        raise WCLError("gear fetch failed")
    monkeypatch.setattr(main, "_fetch_enchants", boom)

    out = main._do_vet("Foo", "Spineshatter", "US")
    assert out["found"] is True
    assert out["enchants"] is None  # gear is a bonus; never fails the lookup


def test_do_vet_no_recent_reports_means_no_enchants(monkeypatch):
    char = {"name": "Foo", "classID": 2, "z1007": None, "recentReports": {"data": []}}
    monkeypatch.setattr(main, "get_raid_zones", lambda: [{"id": 1007, "name": "Karazhan"}])
    monkeypatch.setattr(main, "post_graphql",
                        lambda *a, **k: {"characterData": {"character": char}})
    out = main._do_vet("Foo", "Spineshatter", "US")
    assert out["enchants"] is None and out["last_log"] is None


def test_do_vet_propagates_zone_error(monkeypatch):
    def boom():
        raise WCLError("CURRENT_EXPANSION_ID is stale")
    monkeypatch.setattr(main, "get_raid_zones", boom)
    with pytest.raises(WCLError, match="stale"):
        main._do_vet("Foo", "Spineshatter", "US")


# --- _fetch_enchants -------------------------------------------------------

def test_fetch_enchants_no_fights_returns_none(monkeypatch):
    monkeypatch.setattr(main, "post_graphql",
                        lambda *a, **k: {"reportData": {"report": {"fights": []}}})
    assert main._fetch_enchants("code", "Testchar") is None


def test_fetch_enchants_analyzes_real_gear(monkeypatch):
    responses = iter([
        {"reportData": {"report": {"fights": [{"id": 1}, {"id": 2}]}}},
        {"reportData": {"report": {"playerDetails": load("player_details.json")}}},
    ])
    monkeypatch.setattr(main, "post_graphql", lambda *a, **k: next(responses))
    en = main._fetch_enchants("code", "Testchar")
    assert en["missing_required"] == 3  # matches the analyze fixture (Shoulder/Wrist/Feet)
    assert en["avg_item_level"] == 115.8


def test_fetch_enchants_unknown_player_returns_none(monkeypatch):
    responses = iter([
        {"reportData": {"report": {"fights": [{"id": 1}]}}},
        {"reportData": {"report": {"playerDetails": load("player_details.json")}}},
    ])
    monkeypatch.setattr(main, "post_graphql", lambda *a, **k: next(responses))
    assert main._fetch_enchants("code", "SomeoneElse") is None


# --- index + /api/zones routes ---------------------------------------------

def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<" in r.data  # the SPA shell


def test_api_zones_ok(client, monkeypatch):
    monkeypatch.setattr(main, "list_all_zones",
                        lambda: [{"id": 1, "name": "MC", "expansion": "Classic", "frozen": True}])
    r = client.get("/api/zones")
    assert r.status_code == 200
    assert r.get_json()[0]["name"] == "MC"


def test_api_zones_error_returns_502(client, monkeypatch):
    def boom():
        raise WCLError("no creds")
    monkeypatch.setattr(main, "list_all_zones", boom)
    r = client.get("/api/zones")
    assert r.status_code == 502
    assert r.get_json()["error"] == "no creds"
