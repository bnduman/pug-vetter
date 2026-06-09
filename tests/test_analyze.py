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


def test_slugify_realm():
    assert slugify_realm("Living Flame") == "living-flame"
    assert slugify_realm("Nek'rosh") == "nekrosh"
    assert slugify_realm("  Spineshatter ") == "spineshatter"
