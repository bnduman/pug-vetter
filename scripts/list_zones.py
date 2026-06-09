"""Print every zone Warcraft Logs knows about, so you can find the correct
Anniversary raid zone IDs.

Run from the project root:

    python scripts/list_zones.py

Then, if name-matching is grabbing the wrong raids, copy the IDs you want into
RAID_ZONE_IDS in app/data/raids.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.wcl_client import WCLError  # noqa: E402
from app.zones import list_all_zones  # noqa: E402


def main() -> int:
    try:
        zones = list_all_zones()
    except WCLError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for z in zones:
        exp = z["expansion"] or "?"
        state = "frozen" if z["frozen"] else "LIVE"
        print(f'{z["id"]:>6}  [{exp:<22}] {state:<6}  {z["name"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
