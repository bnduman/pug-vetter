"""Flask app: serves the UI and the /api/vet JSON endpoint."""
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import config
from .analyze import (
    analyze_enchants,
    find_player_gear,
    parse_color,
    summarize_zone,
)
from .queries import REPORT_FIGHTS_QUERY, REPORT_GEAR_QUERY, build_character_query
from .util import slugify_realm
from .wcl_client import WCLError, post_graphql
from .zones import get_raid_zones, list_all_zones

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=None)

# --- tiny TTL cache so repeated invites don't re-hit the WCL rate limit ---
_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _cache_set(key: str, value: dict):
    _cache[key] = (time.time(), value)


# --- routes ---
@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC, filename)


@app.get("/api/vet")
def vet():
    name = (request.args.get("name") or "").strip()
    realm = (request.args.get("realm") or config.DEFAULT_REALM or "").strip()
    region = (request.args.get("region") or config.DEFAULT_REGION or "US").strip().upper()

    if not name:
        return jsonify({"error": "Enter a character name."}), 400
    if not realm:
        return jsonify({"error": "Enter a realm (or set DEFAULT_REALM in .env)."}), 400

    key = f"{region}/{slugify_realm(realm)}/{name.lower()}"
    cached = _cache_get(key)
    if cached is not None:
        return jsonify(cached)

    try:
        result = _do_vet(name, realm, region)
    except WCLError as exc:
        return jsonify({"error": str(exc)}), 502

    _cache_set(key, result)
    return jsonify(result)


def _do_vet(name: str, realm: str, region: str) -> dict:
    zones = get_raid_zones()
    if not zones:
        raise WCLError(
            "Couldn't resolve any raid zones from Warcraft Logs. Run "
            "`python scripts/list_zones.py` and set RAID_ZONE_IDS in app/data/raids.py."
        )

    zone_ids = [z["id"] for z in zones]
    query = build_character_query(zone_ids)
    data = post_graphql(
        query,
        {"name": name, "serverSlug": slugify_realm(realm), "serverRegion": region},
    )
    char = (data.get("characterData") or {}).get("character")
    if not char:
        return {"found": False, "name": name, "realm": realm, "region": region}

    raids = []
    for z in zones:
        summary = summarize_zone(z["name"], char.get(f"z{z['id']}"))
        tier, color = parse_color(summary["best_parse"])
        summary["tier"] = tier
        summary["color"] = color
        raids.append(summary)

    # Gear/enchants from the character's most recent logged raid.
    enchants = None
    last_log = None
    recent = ((char.get("recentReports") or {}).get("data")) or []
    if recent:
        last_log = recent[0].get("startTime")
        code = recent[0].get("code")
        if code:
            try:
                enchants = _fetch_enchants(code, name)
            except WCLError:
                enchants = None  # gear is a bonus; never fail the lookup over it

    return {
        "found": True,
        "name": char.get("name", name),
        "realm": realm,
        "region": region,
        "classID": char.get("classID"),
        "raids": raids,
        "enchants": enchants,
        "last_log": last_log,
    }


def _fetch_enchants(report_code: str, char_name: str):
    """Pull a character's gear from a report and analyze its enchants, or None."""
    fdata = post_graphql(REPORT_FIGHTS_QUERY, {"code": report_code})
    fights = ((fdata.get("reportData") or {}).get("report") or {}).get("fights") or []
    fight_ids = [f["id"] for f in fights if f.get("id") is not None]
    if not fight_ids:
        return None
    gdata = post_graphql(REPORT_GEAR_QUERY, {"code": report_code, "fightIDs": fight_ids})
    details = ((gdata.get("reportData") or {}).get("report") or {}).get("playerDetails")
    gear = find_player_gear(details, char_name)
    return analyze_enchants(gear) if gear else None


@app.get("/api/zones")
def api_zones():
    """Debug helper: list every zone WCL knows (also exposed via scripts/list_zones.py)."""
    try:
        return jsonify(list_all_zones())
    except WCLError as exc:
        return jsonify({"error": str(exc)}), 502
