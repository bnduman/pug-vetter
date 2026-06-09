"""GraphQL query builders / strings for the WCL v2 API."""


def build_character_query(zone_ids: list[int]) -> str:
    """One request: per-raid zoneRankings (via aliases) + the latest report.

    `zoneRankings` returns a JSON scalar, so we get the whole blob (rankings[],
    bestPerformanceAverage, ...) per zone. recentReports gives us a report to
    pull gear/enchants from.
    """
    aliases = "\n".join(f"      z{zid}: zoneRankings(zoneID: {zid})" for zid in zone_ids)
    return (
        "query($name: String!, $serverSlug: String!, $serverRegion: String!) {\n"
        "  characterData {\n"
        "    character(name: $name, serverSlug: $serverSlug, serverRegion: $serverRegion) {\n"
        "      id\n"
        "      name\n"
        "      classID\n"
        "      recentReports(limit: 1) { data { code startTime zone { id name } } }\n"
        f"{aliases}\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


# Boss fights in a report (needed because playerDetails requires fight IDs).
REPORT_FIGHTS_QUERY = """
query($code: String!) {
  reportData {
    report(code: $code) {
      fights(killType: Encounters) { id }
    }
  }
}
"""

# Gear/enchants from combatant info across the given fights.
REPORT_GEAR_QUERY = """
query($code: String!, $fightIDs: [Int]!) {
  reportData {
    report(code: $code) {
      playerDetails(fightIDs: $fightIDs, includeCombatantInfo: true)
    }
  }
}
"""
