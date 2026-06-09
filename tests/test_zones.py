"""Tests for raid-zone resolution: auto-detection from the current expansion,
the explicit RAID_ZONE_IDS override, frozen/excluded filtering, day-long
caching, and the precise config-pointing errors that replace a silent [].
"""
import pytest

from app import zones
from app.wcl_client import WCLError

EXPS = [
    {"id": 1000, "name": "Classic", "zones": [
        {"id": 1, "name": "Molten Core", "frozen": True},
    ]},
    {"id": 1001, "name": "The Burning Crusade", "zones": [
        {"id": 1007, "name": "Karazhan", "frozen": False},
        {"id": 1008, "name": "Gruul's Lair", "frozen": False},
        {"id": 1009, "name": "Old Frozen Raid", "frozen": True},          # frozen -> dropped
        {"id": 1010, "name": "Complete Raid (TBC)", "frozen": False},      # excluded by pattern
    ]},
    {"id": 1002, "name": "All Frozen", "zones": [
        {"id": 2001, "name": "Sealed", "frozen": True},
    ]},
]


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    zones._cache["raids"] = None
    zones._cache["ts"] = 0.0
    # Default: auto-detect TBC, no explicit override.
    monkeypatch.setattr(zones, "RAID_ZONE_IDS", [])
    monkeypatch.setattr(zones, "CURRENT_EXPANSION_ID", 1001)
    yield
    zones._cache["raids"] = None
    zones._cache["ts"] = 0.0


def use_expansions(monkeypatch, data=EXPS):
    """Stub the network call and count invocations."""
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return data
    monkeypatch.setattr(zones, "_expansions", fake)
    return calls


def test_auto_detect_drops_frozen_and_excluded(monkeypatch):
    use_expansions(monkeypatch)
    raids = zones.get_raid_zones()
    assert [r["id"] for r in raids] == [1007, 1008]  # sorted, frozen + excluded removed
    assert {r["name"] for r in raids} == {"Karazhan", "Gruul's Lair"}


def test_explicit_override_ignores_frozen(monkeypatch):
    monkeypatch.setattr(zones, "RAID_ZONE_IDS", [1009, 1])  # both frozen, but explicit
    use_expansions(monkeypatch)
    raids = zones.get_raid_zones()
    assert [r["id"] for r in raids] == [1009, 1]  # order follows RAID_ZONE_IDS
    assert raids[0]["name"] == "Old Frozen Raid"


def test_result_is_cached(monkeypatch):
    calls = use_expansions(monkeypatch)
    zones.get_raid_zones()
    zones.get_raid_zones()
    assert calls["n"] == 1  # second call served from the day-long cache


def test_unknown_expansion_id_raises_pointing_at_config(monkeypatch):
    monkeypatch.setattr(zones, "CURRENT_EXPANSION_ID", 9999)
    use_expansions(monkeypatch)
    with pytest.raises(WCLError, match="CURRENT_EXPANSION_ID=9999.*app/data/raids.py"):
        zones.get_raid_zones()


def test_unknown_expansion_lists_known_ids(monkeypatch):
    monkeypatch.setattr(zones, "CURRENT_EXPANSION_ID", 9999)
    use_expansions(monkeypatch)
    with pytest.raises(WCLError, match="1001"):  # known expansions surfaced for the operator
        zones.get_raid_zones()


def test_unmatched_override_ids_raise(monkeypatch):
    monkeypatch.setattr(zones, "RAID_ZONE_IDS", [55555])
    use_expansions(monkeypatch)
    with pytest.raises(WCLError, match="None of RAID_ZONE_IDS"):
        zones.get_raid_zones()


def test_all_zones_frozen_raises(monkeypatch):
    monkeypatch.setattr(zones, "CURRENT_EXPANSION_ID", 1002)  # only a frozen zone
    use_expansions(monkeypatch)
    with pytest.raises(WCLError, match="no live raid zones"):
        zones.get_raid_zones()


def test_errors_are_not_cached(monkeypatch):
    monkeypatch.setattr(zones, "CURRENT_EXPANSION_ID", 9999)
    calls = use_expansions(monkeypatch)
    for _ in range(2):
        with pytest.raises(WCLError):
            zones.get_raid_zones()
    assert calls["n"] == 2  # each failure re-fetches; nothing poisoned the cache


def test_list_all_zones_flattens_and_sorts(monkeypatch):
    use_expansions(monkeypatch)
    rows = zones.list_all_zones()
    assert len(rows) == 6  # every zone across all expansions
    assert all({"id", "name", "expansion", "frozen"} <= set(r) for r in rows)
    frozen = {r["id"]: r["frozen"] for r in rows}
    assert frozen[1] is True and frozen[1007] is False
