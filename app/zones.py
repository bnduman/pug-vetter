"""Resolve which WCL zone IDs to vet against (the live raids of the current
Anniversary expansion). Cached for a day.
"""
import time

from . import config  # noqa: F401  (ensures .env is loaded before any API call)
from .data.raids import CURRENT_EXPANSION_ID, EXCLUDE_ZONE_PATTERNS, RAID_ZONE_IDS
from .wcl_client import post_graphql

EXPANSIONS_QUERY = """
query {
  worldData {
    expansions {
      id
      name
      zones { id name frozen }
    }
  }
}
"""

_TTL = 86400
_cache = {"raids": None, "ts": 0.0}


def _expansions() -> list[dict]:
    data = post_graphql(EXPANSIONS_QUERY)
    return (data.get("worldData") or {}).get("expansions") or []


def list_all_zones() -> list[dict]:
    """Every zone across all expansions, with live/frozen flag (for list_zones.py)."""
    rows = []
    for exp in _expansions():
        for z in exp.get("zones") or []:
            rows.append({
                "id": z.get("id"),
                "name": z.get("name"),
                "expansion": exp.get("name"),
                "frozen": bool(z.get("frozen")),
            })
    rows.sort(key=lambda r: (r["expansion"] or "", r["id"] or 0))
    return rows


def _excluded(name: str) -> bool:
    return any(p.lower() in (name or "").lower() for p in EXCLUDE_ZONE_PATTERNS)


def get_raid_zones() -> list[dict]:
    """Raid zones to vet against: [{id, name}], cached."""
    if _cache["raids"] is not None and time.time() - _cache["ts"] < _TTL:
        return _cache["raids"]

    exps = _expansions()
    raids: list[dict] = []

    if RAID_ZONE_IDS:
        by_id = {z.get("id"): z for e in exps for z in (e.get("zones") or [])}
        for zid in RAID_ZONE_IDS:
            z = by_id.get(zid)
            if z:
                raids.append({"id": zid, "name": z.get("name")})
    else:
        target = next((e for e in exps if e.get("id") == CURRENT_EXPANSION_ID), None)
        if target:
            for z in target.get("zones") or []:
                if z.get("frozen") or _excluded(z.get("name") or ""):
                    continue
                raids.append({"id": z.get("id"), "name": z.get("name")})
        raids.sort(key=lambda r: r["id"] or 0)

    _cache["raids"] = raids
    _cache["ts"] = time.time()
    return raids
