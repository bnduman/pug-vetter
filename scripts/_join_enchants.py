"""Step 2 of the enchant-name refresh pipeline (after _harvest_enchants.py):
join harvested enchant IDs against the TBC Anniversary client's
SpellItemEnchantment table to get the true in-game names, then paste any new
IDs into app/data/enchant_names.py.

Downloads the client DB CSV from wago.tools on first run (cached next to this
script). When a new client build ships, update BUILD below — list builds at
https://wago.tools/api/builds (product "wow_anniversary").
"""
import csv
import json
import pathlib
import sys
import urllib.request

BUILD = "2.5.5.67852"  # TBC Anniversary client

here = pathlib.Path(__file__).resolve().parent
harvest_path = here / "enchant_harvest.json"
csv_path = here / f"SpellItemEnchantment_{BUILD}.csv"

if not harvest_path.exists():
    sys.exit("Run scripts/_harvest_enchants.py first (produces enchant_harvest.json).")
harvest = json.loads(harvest_path.read_text(encoding="utf-8"))

if not csv_path.exists():
    url = f"https://wago.tools/db2/SpellItemEnchantment/csv?build={BUILD}"
    print(f"downloading {url} ...")
    urllib.request.urlretrieve(url, csv_path)

names = {}
with open(csv_path, encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        try:
            names[int(row["ID"])] = row["Name_lang"]
        except (ValueError, KeyError):
            continue

print(f"client DB rows: {len(names)}\n")
missing = 0
for r in harvest:
    eid = r["enchant_id"]
    game = names.get(eid)
    if game is None:
        missing += 1
        game = "<NOT IN CLIENT DB>"
    mark = " " if game.strip() == (r["wcl_name"] or "").strip() else "!"
    print(f"{mark} id={eid:<6} x{r['count']:<4} {str(r['slots']):28} WCL={r['wcl_name']!r:50} GAME={game!r}")
print(f"\nmissing from client DB: {missing}")
print("Lines marked '!' have a wrong WCL name -> ensure the id is in app/data/enchant_names.py")
