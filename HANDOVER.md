# PuG Vetter — Project Handover

A complete brain-dump for picking this project up on another machine (or with a
fresh AI assistant that has none of the original conversation). Read top to
bottom once; after that the **Quick start** is all you need day to day.

---

## 1. What this is & why it exists

A **standalone local web app** for a WoW **Classic Anniversary** raid leader
(realm **Thunderstrike-EU**) to vet PuG raid applicants fast. Type a character
name → get their **raid clears**, **best parse %**, and **per-slot enchant
status**.

**Why standalone and not a WoW addon:** in-game addons run in a sandbox with
**no network access**, so an addon literally cannot fetch web data and can only
read gear for players physically next to you. A standalone program has full
network access, so it answers from just a name — which is the whole point.

**Data source:** the [Warcraft Logs v2 GraphQL API](https://www.warcraftlogs.com/api/docs).
Blizzard's own Classic profile API is a dead end (403/404), so WCL is the single
source of truth.

**The honest limitation:** coverage is 100% dependent on WCL. A player never
logged returns "no data" — that is NOT proof they've never raided. Enchant/gear
reflects their most recent **logged** fight, not necessarily what they're
wearing right now.

---

## 2. Quick start (macOS)

```bash
git clone https://github.com/bnduman/pug-vetter.git
cd pug-vetter
python3 -m venv .venv
source .venv/bin/activate            # do this each new terminal session
pip install -r requirements.txt
cp .env.example .env                 # then edit .env — see section 3
python run.py                        # open http://127.0.0.1:8000
```

On Windows it's the same idea: `python -m venv .venv`, `.venv\Scripts\activate`,
`pip install -r requirements.txt`, `python run.py`.

Run the tests anytime with `python -m pytest`.

---

## 3. Credentials (`.env`) — the one file NOT in the repo

`.env` is gitignored on purpose, so you recreate it per machine. Contents:

```
WCL_CLIENT_ID=a1fbfd44-d145-4121-a079-2d0b61968abb
WCL_CLIENT_SECRET=<your client secret>
DEFAULT_REGION=EU
DEFAULT_REALM=Thunderstrike
CACHE_TTL_SECONDS=600
```

- The **client id** above is the existing one. The **secret** is intentionally
  not committed — get it from <https://www.warcraftlogs.com/api/clients/>
  (your "addon test" client → it's shown there), or copy it from the `.env` on
  your other machine.
- To make a fresh client: that page → **Create Client** → name it, redirect
  `http://localhost`, leave **"Public Client" UNCHECKED** (public clients get no
  secret and won't work — we need the client-credentials flow).
- Rate limit is **3,600 points/hour** on a free account.

---

## 4. How it works (data flow)

```
Browser (static/index.html + app.js)
   │  GET /api/vet?name=X&realm=Y&region=Z
   ▼
Flask (app/main.py :: vet -> _do_vet)
   1. zones.get_raid_zones()      -> current live raid zone IDs (see §5)
   2. queries.build_character_query(zone_ids)
        characterData.character(name, serverSlug, serverRegion) {
          classID
          recentReports(limit:1){ data{ code startTime zone{id name} } }
          z<ID>: zoneRankings(zoneID: <ID>)   # one alias per raid
        }
   3. analyze.summarize_zone(zr)  -> {cleared, total, best_parse} per raid
   4. _fetch_enchants(reportCode, name):
        report.fights(killType: Encounters){ id }      # need fight IDs
        report.playerDetails(fightIDs, includeCombatantInfo:true)
        analyze.find_player_gear + analyze.analyze_enchants
   ▼
JSON scorecard -> app.js renders it
```

`wcl_client.py` handles the OAuth2 token (cache + refresh) and GraphQL POSTs to
`https://classic.warcraftlogs.com/api/v2/client`. Token endpoint is
`https://www.warcraftlogs.com/oauth/token`.

---

## 5. WCL API gotchas (hard-won — do not relearn these the hard way)

These cost real debugging time. They're encoded in the code, but know them:

1. **`worldData.zones` IDs are NOT the IDs `zoneRankings` accepts.** That list is
   the old 2019-Classic enumeration. The real current zone IDs are different —
   e.g. Anniversary **Karazhan is zone 1047, not 1007**. Querying a wrong/stale
   ID returns `{"error": "Unsupported zone specified."}`.

2. **Resolve zones via `worldData.expansions` instead.** Each expansion lists its
   zones with a `frozen` flag. The **current Anniversary content = the live
   (`frozen: false`), non-aggregate raids** of the current expansion.
   `app/zones.py` does exactly this, scoped to `CURRENT_EXPANSION_ID`.

3. **Anniversary is currently in The Burning Crusade** (as of June 2026):
   Karazhan (1047), Gruul/Magtheridon (1048), SSC/TK (1056). When the realms
   advance to Wrath, change `CURRENT_EXPANSION_ID` in `app/data/raids.py`
   from `1001` to `1002`. WCL expansion IDs: 1000 Classic · 1001 TBC ·
   1002 Wrath · 1003 Cata · 1004 MoP.

4. **`zoneRankings` returns a JSON scalar** — you can't select sub-fields; you get
   the whole blob: `bestPerformanceAverage` + `rankings[]` where each entry has
   `encounter{id,name}`, `totalKills` (cleared if > 0), `rankPercent` (parse %,
   sometimes the string `"-"` when unranked — handle that).

5. **Gear needs fight IDs.** `playerDetails` rejects a whole-report time range
   ("must provide fightIDs…"). Get boss fights first via
   `report.fights(killType: Encounters)`, then pass their IDs.

6. **`playerDetails` is wrapped:** the JSON is `{"data": {"playerDetails":
   {tanks:[], healers:[], dps:[]}}}`. Each player has
   `combatantInfo.gear[]`, and **each gear item carries an explicit `slot`
   number** (0 Head, 2 Shoulder, 4 Chest, 6 Legs, 7 Feet, 8 Wrist, 9 Hands,
   14 Back, 15 Main Hand, 16 Off Hand…) plus `permanentEnchant` /
   `permanentEnchantName` / `itemLevel` / `gems`. Match enchants on `slot`,
   not array position. The array can hold multiple fights' gear, so we keep the
   highest-ilvl item per slot.

---

## 6. File map

```
run.py                    launch the web app (python run.py)
HANDOVER.md               this file
README.md                 user-facing setup/usage
requirements.txt          Flask, requests, pytest
.env.example              template; copy to .env (gitignored)
app/
  main.py                 Flask routes, /api/vet, TTL cache, gear fetch
  wcl_client.py           OAuth token + GraphQL POST
  zones.py                resolve live raid zones from expansions
  queries.py              GraphQL query builders/strings
  analyze.py              pure: zoneRankings/gear JSON -> scorecard (tested)
  util.py                 slugify_realm
  config.py               env / .env loading (no pydantic, dependency-light)
  data/
    raids.py              CURRENT_EXPANSION_ID + RAID_ZONE_IDS override
    enchant_rules.py      which slots must be enchanted (TBC-tuned)
  static/                 index.html, app.js, style.css
scripts/list_zones.py     prints all zones/expansions + live/frozen flags
tests/                    pytest + JSON fixtures (no network needed)
```

---

## 7. Config knobs

- **Current raid tier:** `CURRENT_EXPANSION_ID` in `app/data/raids.py` (1001=TBC).
- **Force exact zones:** set `RAID_ZONE_IDS = [..]` in the same file (used
  verbatim when non-empty; discover IDs with `python scripts/list_zones.py`).
- **Which slots must be enchanted:** `app/data/enchant_rules.py` (`ENCHANT_SLOTS`,
  keyed by WCL slot number; `required=True` counts toward the missing-enchant
  warning). Currently TBC-tuned (head & shoulder enchants are standard).
- **Lookup cache TTL:** `CACHE_TTL_SECONDS` in `.env` (default 600s) — spares the
  rate limit on repeated invites.
- **Region dropdown:** edit the `<select>` in `app/static/index.html`.

---

## 8. Verified working state

Last confirmed against live data (Sahmeran-Thunderstrike-EU, a Prot Paladin):

| Raid | Cleared | Best parse |
|------|---------|-----------|
| Karazhan | 10/10 | 50.9 (blue) |
| Gruul / Magtheridon | 3/3 | 51.7 (blue) |
| SSC / TK | 9/10 | 36.2 (green) |

Enchants: 0 missing required, avg ilvl 117.9, all 9 slots enchanted. The unit
suite (`python -m pytest`) is green.

---

## 9. Troubleshooting

- **"WCL credentials are not configured"** → `.env` missing or empty. See §3.
- **Every raid shows 0/0** → zone IDs are wrong for the current game version
  (the "Unsupported zone specified" trap, §5.1). Run `python scripts/list_zones.py`,
  confirm the current expansion's live raids, and check `CURRENT_EXPANSION_ID`.
- **"No logs found"** for a real player → they're genuinely not on WCL, or the
  realm slug/region is off (we slugify the realm: lowercase, spaces→hyphens,
  apostrophes removed; `serverRegion` is EU/US uppercase).
- **No enchant section** → that character's latest report had no usable
  combatant info (gear is a bonus; the lookup never fails over it).
- **pip "externally-managed-environment" on macOS** → you skipped the venv; do
  `python3 -m venv .venv && source .venv/bin/activate` first.

---

## 10. Next-step ideas (not yet built)

- **Gem check** — gear data already includes `gems[]`; flag empty sockets.
- **World buffs / consumables** — readable from the logged fight (flask/elixir).
- **Class/spec label** in the header (data has `classID` + per-fight spec).
- **"Copy summary" button** — one-line verdict to paste into guild chat.
- **Batch vetting** — paste several names at once.

---

## 11. Git workflow

```bash
git pull            # if you worked on the other machine
# ...edit...
git add -A
git commit -m "message"
git push
```

Repo: <https://github.com/bnduman/pug-vetter> (public, branch `main`).
Commits authored as `bnduman <curseinvain@gmail.com>`.
