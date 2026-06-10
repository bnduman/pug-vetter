"""One-off: harvest every distinct (slot, permanentEnchant id, WCL name) actually
in use by ranked players across the current raid zones, to build a verification
work-list for app/data/enchant_names.py.

Efficient: playerDetails returns EVERY player in a report, so we dedupe by
report code and pull whole raids at once (~25 players per API call).

Writes JSON next to this script: scripts/enchant_harvest.json
"""
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.queries import REPORT_GEAR_QUERY
from app.wcl_client import post_graphql
from app.zones import get_raid_zones

OUT_PATH = pathlib.Path(__file__).resolve().parent / "enchant_harvest.json"

SLOT_LABEL = {0: "Head", 1: "Neck", 2: "Shoulder", 3: "Shirt", 4: "Chest", 5: "Belt",
              6: "Legs", 7: "Feet", 8: "Wrist", 9: "Hands", 10: "Ring", 11: "Ring",
              12: "Trinket", 13: "Trinket", 14: "Back", 15: "MainHand", 16: "OffHand",
              17: "Ranged", 18: "Tabard"}

zone_q = "query($id:Int!){ worldData{ zone(id:$id){ encounters{ id name } } } }"
enc_q = "query($id:Int!){ worldData{ encounter(id:$id){ characterRankings(page:1) } } }"

# Collect distinct report codes from the top rankings of a few encounters per zone.
reports = {}  # code -> fightID (any boss fight in it works for combatantInfo)
for z in get_raid_zones():
    encs = post_graphql(zone_q, {"id": z["id"]})["worldData"]["zone"]["encounters"]
    for e in encs[:3]:  # a few encounters per zone is plenty for coverage
        try:
            cr = post_graphql(enc_q, {"id": e["id"]})["worldData"]["encounter"]["characterRankings"]
        except Exception as ex:
            print("rankings fail", e["id"], ex)
            continue
        for rk in (cr.get("rankings") or []):
            rep = rk.get("report") or {}
            code, fid = rep.get("code"), rep.get("fightID")
            if code and fid is not None and code not in reports:
                reports[code] = fid

cap = 12  # each report yields a whole raid's gear, so a dozen covers hundreds of players
print(f"distinct reports: {len(reports)}, scanning first {cap}")

# id -> {wcl_name, slots:set, count}
seen = defaultdict(lambda: {"wcl_name": None, "slots": set(), "count": 0})
players_scanned = 0
for code, fid in list(reports.items())[:cap]:
    try:
        g = post_graphql(REPORT_GEAR_QUERY, {"code": code, "fightIDs": [fid]})
    except Exception as ex:
        print("gear fail", code, ex)
        continue
    pd = ((g.get("reportData") or {}).get("report") or {}).get("playerDetails")
    inner = pd["data"]["playerDetails"] if isinstance(pd, dict) and "data" in pd else pd
    if not isinstance(inner, dict):
        continue
    for p in (inner.get("tanks") or []) + (inner.get("healers") or []) + (inner.get("dps") or []):
        players_scanned += 1
        for it in (p.get("combatantInfo") or {}).get("gear") or []:
            eid = it.get("permanentEnchant")
            if not eid:
                continue
            rec = seen[eid]
            rec["wcl_name"] = it.get("permanentEnchantName") or rec["wcl_name"]
            rec["slots"].add(SLOT_LABEL.get(it.get("slot"), str(it.get("slot"))))
            rec["count"] += 1

out = [{"enchant_id": eid, "wcl_name": rec["wcl_name"],
        "slots": sorted(rec["slots"]), "count": rec["count"]}
       for eid, rec in sorted(seen.items(), key=lambda kv: -kv[1]["count"])]

print(f"players scanned: {players_scanned}")
print(f"distinct enchant ids: {len(out)}")
for r in out:
    print(f"  id={r['enchant_id']:<6} x{r['count']:<4} {str(r['slots']):30} {r['wcl_name']!r}")

OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"\nwrote {OUT_PATH}")
