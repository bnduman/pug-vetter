"""Pure functions that turn raw Warcraft Logs JSON into a vetting scorecard.

No network or framework imports here, so this is the easy part to unit-test.
"""
from .data.enchant_rules import ENCHANT_SLOTS, NON_ILVL_SLOTS


def parse_color(pct):
    """Return (tier_name, hex_color) for a parse percentile, or ("none", grey)."""
    if pct is None:
        return ("none", "#6b6b6b")
    p = round(pct)
    if p >= 100:
        return ("artifact", "#e5cc80")
    if p >= 99:
        return ("astounding", "#e268a8")
    if p >= 95:
        return ("legendary", "#ff8000")
    if p >= 75:
        return ("epic", "#a335ee")
    if p >= 50:
        return ("rare", "#0070ff")
    if p >= 25:
        return ("uncommon", "#1eff00")
    return ("common", "#9d9d9d")


def summarize_zone(zone_name, zone_rankings):
    """Reduce a zoneRankings JSON blob to {name, cleared, total, best_parse, encounters}.

    Tolerates the {"error": "..."} blob WCL returns for an unsupported zone.
    """
    base = {"name": zone_name, "cleared": 0, "total": 0, "best_parse": None, "encounters": []}
    if not isinstance(zone_rankings, dict) or "rankings" not in zone_rankings:
        return base

    rankings = zone_rankings.get("rankings") or []
    encounters = []
    cleared = 0
    parses = []
    for r in rankings:
        if not isinstance(r, dict):
            continue
        kills = r.get("totalKills") or 0
        rp = r.get("rankPercent")
        if not isinstance(rp, (int, float)):  # WCL uses "-" for unranked
            rp = None
        name = (r.get("encounter") or {}).get("name", "?")
        if kills > 0:
            cleared += 1
        if rp is not None:
            parses.append(rp)
        encounters.append({"name": name, "kills": kills, "parse": rp})

    best = zone_rankings.get("bestPerformanceAverage")
    if not isinstance(best, (int, float)):
        best = max(parses) if parses else None

    base.update(cleared=cleared, total=len(encounters), best_parse=best, encounters=encounters)
    return base


def find_player_gear(player_details, char_name):
    """Locate `char_name`'s gear array inside a playerDetails JSON blob, or None.

    WCL wraps the payload as {"data": {"playerDetails": {tanks, healers, dps}}}.
    """
    pd = player_details
    if isinstance(pd, dict) and "data" in pd and isinstance(pd["data"], dict):
        pd = pd["data"].get("playerDetails", pd)
    if not isinstance(pd, dict):
        return None
    target = (char_name or "").lower()
    for role in ("tanks", "healers", "dps"):
        for player in pd.get(role) or []:
            if (player.get("name") or "").lower() == target:
                return (player.get("combatantInfo") or {}).get("gear") or []
    return None


def _gear_by_slot(gear):
    """Collapse the gear array to one item per slot.

    The array can contain several fights' worth of gear (duplicate slots); keep
    the highest-item-level entry per slot so a transient swap doesn't misreport.
    """
    best = {}
    for item in gear or []:
        if not isinstance(item, dict):
            continue
        slot = item.get("slot")
        if slot is None:
            continue
        cur = best.get(slot)
        if cur is None or (item.get("itemLevel") or 0) > (cur.get("itemLevel") or 0):
            best[slot] = item
    return best


def _gem_count(item):
    """How many gems are socketed in an item. WCL lists socketed gems but does
    NOT expose empty sockets, so this is a 'did they gem' signal, not a
    per-socket audit."""
    return len(item.get("gems") or []) if item else 0


def analyze_enchants(gear):
    """From a gear array, report enchant status + gem count per slot, the average
    item level, and the total number of gems socketed across all gear."""
    by_slot = _gear_by_slot(gear)
    slots = []
    missing_required = 0
    for rule in ENCHANT_SLOTS:
        item = by_slot.get(rule["slot"])
        gems = _gem_count(item)
        if not item or not item.get("id"):
            slots.append({"slot": rule["label"], "status": "empty",
                          "enchant": None, "gems": gems, "required": rule["required"]})
            continue
        ench_id = item.get("permanentEnchant") or 0
        if ench_id:
            slots.append({"slot": rule["label"], "status": "enchanted",
                          "enchant": item.get("permanentEnchantName") or f"#{ench_id}",
                          "gems": gems, "required": rule["required"]})
        else:
            slots.append({"slot": rule["label"], "status": "missing",
                          "enchant": None, "gems": gems, "required": rule["required"]})
            if rule["required"]:
                missing_required += 1

    ilvls = []
    for slot, item in by_slot.items():
        if slot in NON_ILVL_SLOTS or not item.get("id"):
            continue
        lvl = item.get("itemLevel")
        if lvl and lvl > 1:
            ilvls.append(lvl)
    avg_ilvl = round(sum(ilvls) / len(ilvls), 1) if ilvls else None

    # Total gems across all gear (rings/neck/etc. included, not just enchant slots).
    gems_total = sum(_gem_count(item) for item in by_slot.values())

    return {"slots": slots, "missing_required": missing_required,
            "avg_item_level": avg_ilvl, "gems_total": gems_total}
