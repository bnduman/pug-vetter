import json
import pathlib

from app.analyze import (
    analyze_enchants,
    find_player_gear,
    parse_color,
    summarize_zone,
)
from app.util import slugify_realm

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_parse_color_bands():
    assert parse_color(None)[0] == "none"
    assert parse_color(100)[0] == "artifact"
    assert parse_color(99)[0] == "astounding"
    assert parse_color(95)[0] == "legendary"
    assert parse_color(82.5)[0] == "epic"
    assert parse_color(50)[0] == "rare"
    assert parse_color(25)[0] == "uncommon"
    assert parse_color(24)[0] == "common"


def test_summarize_zone():
    s = summarize_zone("Karazhan", load("zone_rankings.json"))
    assert s["cleared"] == 2
    assert s["total"] == 3
    assert s["best_parse"] == 82.5


def test_summarize_zone_handles_none():
    assert summarize_zone("MC", None) == {
        "name": "MC", "cleared": 0, "total": 0, "best_parse": None, "encounters": [],
    }


def test_summarize_zone_handles_unsupported_error():
    # WCL returns {"error": "..."} for an unsupported zone — treat as no data.
    s = summarize_zone("Bad", {"error": "Unsupported zone specified."})
    assert s["cleared"] == 0 and s["total"] == 0 and s["best_parse"] is None


def test_find_player_gear():
    pd = load("player_details.json")
    gear = find_player_gear(pd, "testchar")  # case-insensitive, found in "tanks"
    assert isinstance(gear, list)
    assert len(gear) == 20  # raw array incl. a duplicate legs entry
    assert find_player_gear(pd, "nobody") is None


def test_analyze_enchants():
    gear = find_player_gear(load("player_details.json"), "Testchar")
    en = analyze_enchants(gear)
    assert en["missing_required"] == 3  # Shoulder, Wrist, Feet
    assert en["avg_item_level"] == 115.8
    by_slot = {s["slot"]: s for s in en["slots"]}
    assert by_slot["Head"]["status"] == "enchanted"
    assert by_slot["Shoulder"]["status"] == "missing"
    assert by_slot["Wrist"]["status"] == "missing"
    assert by_slot["Feet"]["status"] == "missing"
    assert by_slot["Weapon"]["status"] == "enchanted"
    # dedup keeps the higher-ilvl (enchanted) legs over the unenchanted duplicate
    assert by_slot["Legs"]["status"] == "enchanted"


def test_analyze_gems_counts_sockets():
    gear = [
        {"id": 1, "slot": 0, "itemLevel": 120, "permanentEnchant": 5,
         "gems": [{"id": 10}, {"id": 11}]},          # Head: enchanted, 2 gems
        {"id": 2, "slot": 1, "itemLevel": 110, "gems": [{"id": 12}]},  # Neck: not an enchant slot, 1 gem
        {"id": 3, "slot": 2, "itemLevel": 120, "permanentEnchant": 0},  # Shoulder: no gems key
        {"id": 4, "slot": 6, "itemLevel": 120, "permanentEnchant": 7, "gems": []},  # Legs: empty gems list
    ]
    en = analyze_enchants(gear)
    assert en["gems_total"] == 3  # 2 (head) + 1 (neck) + 0 + 0, across ALL gear
    by_slot = {s["slot"]: s for s in en["slots"]}
    assert by_slot["Head"]["gems"] == 2
    assert by_slot["Shoulder"]["gems"] == 0  # missing key -> 0
    assert by_slot["Legs"]["gems"] == 0      # empty list -> 0
    assert by_slot["Feet"]["gems"] == 0      # slot absent entirely -> 0


def test_analyze_enchant_uses_client_db_names():
    # WCL's names are retail-mangled for TBC; the client-DB map must win.
    # 369: WCL says "+4 Intellect" -> really "+12 Intellect" (Bracer Major Int).
    # 2928: WCL says "+12 Intellect" -> really "+12 Spell Damage" (Ring Spellpower).
    gear = [
        {"id": 1, "slot": 8, "itemLevel": 115,
         "permanentEnchant": 369, "permanentEnchantName": "+4 Intellect"},
        {"id": 2, "slot": 4, "itemLevel": 115,
         "permanentEnchant": 2661, "permanentEnchantName": "+4 All Stats"},
    ]
    en = analyze_enchants(gear)
    by_slot = {s["slot"]: s for s in en["slots"]}
    assert by_slot["Wrist"]["enchant"] == "+12 Intellect"
    assert by_slot["Chest"]["enchant"] == "+6 All Stats"


def test_analyze_enchant_name_falls_back_to_wcl():
    # An enchant id we don't know keeps WCL's own name rather than vanishing.
    gear = [{"id": 1, "slot": 8, "itemLevel": 115,
             "permanentEnchant": 99999, "permanentEnchantName": "+15 Mystery Stat"}]
    wrist = next(s for s in analyze_enchants(gear)["slots"] if s["slot"] == "Wrist")
    assert wrist["enchant"] == "+15 Mystery Stat"


def test_analyze_gems_total_zero_when_none():
    gear = [{"id": 1, "slot": 0, "itemLevel": 120, "permanentEnchant": 5}]
    assert analyze_enchants(gear)["gems_total"] == 0


def test_slugify_realm():
    assert slugify_realm("Living Flame") == "living-flame"
    assert slugify_realm("Nek'rosh") == "nekrosh"
    assert slugify_realm("  Spineshatter ") == "spineshatter"
