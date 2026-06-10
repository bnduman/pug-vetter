"""Dev helper: run a live /api/vet lookup through the Flask test client and
print the scorecard. Usage: python scripts/_live_check.py [name]"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.main import app

name = sys.argv[1] if len(sys.argv) > 1 else "sahmeran"
c = app.test_client()
d = c.get(f"/api/vet?name={name}").get_json()
if "error" in d:
    sys.exit(f"error: {d['error']}")
print(f"{d.get('name')} @ {d.get('realm')}-{d.get('region')} | found={d.get('found')}")
for x in d.get("raids", []):
    bp = x["best_parse"]
    bp = "-" if bp is None else round(bp, 1)
    print(f"  {x['name']:<24} {x['cleared']}/{x['total']:<3} perf avg {bp} [{x['tier']}]")
e = d.get("enchants")
if e:
    print(f"enchants: missing {e['missing_required']} | ilvl {e['avg_item_level']} | gems {e['gems_total']}")
    for s in e["slots"]:
        print(f"  [{s['status']:<9}] {s['slot']:<9} {s['enchant'] or ''}")
