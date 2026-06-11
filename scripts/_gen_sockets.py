"""One-off: generate js/item-sockets.js for pug-vetter-web from the Anniversary
client's ItemSparse table (wago.tools CSV, cached in %TEMP%), and print the WCL
class-ID map to bake into js/wcl-classes.js."""
import csv
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.wcl_client import post_graphql

csv_path = pathlib.Path(os.environ["TEMP"]) / "itemsparse_anniversary.csv"
out_path = (pathlib.Path(os.environ["USERPROFILE"]) / "OneDrive" / "Masaüstü"
            / "pug-vetter-web" / "js" / "item-sockets.js")

sockets = {}
with open(csv_path, encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        try:
            count = sum(1 for i in range(3) if int(row[f"SocketType_{i}"] or 0) != 0)
            if count:
                sockets[int(row["ID"])] = count
        except (ValueError, KeyError):
            continue

print(f"items with sockets: {len(sockets)}")

entries = ",".join(f"{k}:{v}" for k, v in sorted(sockets.items()))
out_path.write_text(
    "// Generated from the TBC Anniversary client's ItemSparse table\n"
    "// (wago.tools build 2.5.5.67852) by pug-vetter/scripts/_gen_sockets.py.\n"
    "// itemID -> number of gem sockets. Items absent here have zero sockets.\n"
    "// Needed because WCL lists socketed gems but never empty sockets.\n"
    f"export const ITEM_SOCKETS = {{{entries}}};\n",
    encoding="utf-8",
)
print(f"wrote {out_path}")

classes = post_graphql("query { gameData { classes { id name slug } } }")
print("\nWCL classes:")
print(json.dumps(classes["gameData"]["classes"], indent=2))
