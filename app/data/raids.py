"""Which raids count as "current Anniversary content" for vetting.

Warcraft Logs groups zones under expansions, and marks the currently-progressing
zones as live (frozen = false). The Anniversary realms map to one expansion at a
time, so we auto-detect the live, non-aggregate raids under CURRENT_EXPANSION_ID.
This means new raid tiers light up automatically as they release, with no code
change.

WCL expansion IDs (verified via scripts/list_zones.py):
    1000 Classic · 1001 The Burning Crusade · 1002 Wrath · 1003 Cataclysm · 1004 MoP

As of June 2026 the Anniversary realms are in The Burning Crusade (Karazhan /
Gruul / SSC-TK). When they advance to Wrath, change this to 1002.
"""

CURRENT_EXPANSION_ID = 1001  # The Burning Crusade

# Hard override: if non-empty, these exact zone IDs are used and auto-detection
# is skipped. Discover IDs with `python scripts/list_zones.py`.
RAID_ZONE_IDS: list[int] = []

# Aggregate / non-raid zones to skip when auto-detecting (matched as substrings).
EXCLUDE_ZONE_PATTERNS = ["Complete Raid", "Heroic Dungeon", "Challenge Mode"]
