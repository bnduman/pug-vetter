"""One-off: generate js/item-2h.js for pug-vetter-web — the set of two-handed
weapon item IDs (InventoryType 17) from the Anniversary client's ItemSparse
table. GearScore weights 2H weapons at 2.0 vs 1.0 for one-handers, and WCL's
gear data only gives the slot, not the weapon type."""
import csv
import os
import pathlib

csv_path = pathlib.Path(os.environ["TEMP"]) / "itemsparse_anniversary.csv"
out_path = (pathlib.Path(os.environ["USERPROFILE"]) / "OneDrive" / "Masaüstü"
            / "pug-vetter-web" / "js" / "item-2h.js")

if not csv_path.exists():
    import urllib.request
    url = "https://wago.tools/db2/ItemSparse/csv?build=2.5.5.67852"
    print(f"downloading {url} ...")
    urllib.request.urlretrieve(url, csv_path)

ids = []
with open(csv_path, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    assert "InventoryType" in reader.fieldnames, f"no InventoryType column: {reader.fieldnames[:40]}"
    for row in reader:
        try:
            if int(row["InventoryType"] or 0) == 17:  # INVTYPE_2HWEAPON
                ids.append(int(row["ID"]))
        except ValueError:
            continue

print(f"two-handed weapons: {len(ids)}")
out_path.write_text(
    "// Generated from the TBC Anniversary client's ItemSparse table\n"
    "// (wago.tools build 2.5.5.67852) by pug-vetter/scripts/_gen_2h.py.\n"
    "// Item IDs with InventoryType 17 (two-handed weapons, incl. staves and\n"
    "// polearms). GearScore weights these 2.0 vs 1.0 for one-handers.\n"
    f"export const ITEM_2H = new Set([{','.join(map(str, sorted(ids)))}]);\n",
    encoding="utf-8",
)
print(f"wrote {out_path}")
