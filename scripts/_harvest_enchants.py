"""One-off: harvest every distinct (slot, permanentEnchant id, WCL name) actually
in use by ranked players across the current raid zones, to build a verification
work-list. Writes JSON to /tmp/enchant_harvest.json."""
import json
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from app.queries import REPORT_GEAR_QUERY
from app.wcl_client import post_graphql
from app.zones import get_raid_zones

SLOT_LABEL = {0: "Head", 1: "Neck", 2: "Shoulder", 3: "Shirt", 4: "Chest", 5: "Belt",
              6: "Legs", 7: "Feet", 8: "Wrist", 9: "Hands", 10: "Ring", 11: "Ring",
              12: "Trinket", 13: "Trinket", 14: "Back", 15: "MainHand", 16: "OffHand",
              17: "Ranged", 18: "Tabard"}

zones = get_raid_zones()
zone_q = "query($id:Int!){ worldData{ zone(id:$id){ encounters{ id name } } } }"
enc_q = "query($id:Int!){ worldData{ encounter(id:$id){ characterRankings(page:1) } } }"

# Gather candidate players (dedup by name), each with a report+fight to pull gear from.
candidates = {}  # name -> (code, fightID, class, spec)
for z in zones:
    encs = post_graphql(zone_q, {"id": z["id"]})["worldData"]["zone"]["encounters"]
    for e in encs:
        try:
            cr = post_graphql(enc_q, {"id": e["id"]})["worldData"]["encounter"]["characterRankings"]
        except Exception as ex:
            print("rankings fail", e["id"], ex); continue
        for rk in (cr.get("rankings") or [])[:8]:
            nm = rk.get("name")
            rep = rk.get("report") or {}
            if nm and nm not in candidates and rep.get("code") and rep.get("fightID") is not None:
                candidates[nm] = (rep["code"], rep["fightID"], rk.get("class"), rk.get("spec"))

print(f"distinct candidate players: {len(candidates)}")
cap = 90
items = list(candidates.items())[:cap]

# id -> {name, slots:set, classes:set, count}
seen = defaultdict(lambda: {"wcl_name": None, "slots": set(), "classes": set(), "count": 0})
players_scanned = 0
for nm, (code, fid, cls, spec) in items:
    try:
        g = post_graphql(REPORT_GEAR_QUERY, {"code": code, "fightIDs": [fid]})
    except Exception as ex:
        print("gear fail", nm, ex); continue
    pd = ((g.get("reportData") or {}).get("report") or {}).get("playerDetails")
    inner = pd["data"]["playerDetails"] if isinstance(pd, dict) and "data" in pd else pd
    if not isinstance(inner, dict):
        continue
    players = (inner.get("tanks") or []) + (inner.get("healers") or []) + (inner.get("dps") or [])
    me = next((p for p in players if (p.get("name") or "").lower() == nm.lower()), None)
    if not me:
        continue
    players_scanned += 1
    for it in (me.get("combatantInfo") or {}).get("gear") or []:
        eid = it.get("permanentEnchant")
        if not eid:
            continue
        rec = seen[eid]
        rec["wcl_name"] = it.get("permanentEnchantName") or rec["wcl_name"]
        rec["slots"].add(SLOT_LABEL.get(it.get("slot"), str(it.get("slot"))))
        if cls:
            rec["classes"].add(cls)
        rec["count"] += 1

out = []
for eid, rec in sorted(seen.items(), key=lambda kv: -kv[1]["count"]):
    out.append({"enchant_id": eid, "wcl_name": rec["wcl_name"],
                "slots": sorted(rec["slots"]), "classes": sorted(rec["classes"]),
                "count": rec["count"]})

print(f"players scanned: {players_scanned}")
print(f"distinct enchant ids: {len(out)}")
for r in out:
    print(f"  id={r['enchant_id']:<6} x{r['count']:<3} {str(r['slots']):28} {r['wcl_name']!r}")

with open("/tmp/enchant_harvest.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nwrote /tmp/enchant_harvest.json")
