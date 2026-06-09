# PuG Vetter

A tiny local web app for raid leaders on WoW **Classic Anniversary** realms.
Type a character name and get back, at a glance:

- **Which raids they've cleared** (boss kill counts per raid)
- **Their best parse %** per raid, colour-coded like Warcraft Logs
- **Enchant check** — which gear slots are missing enchants (from their most
  recently logged raid), plus average item level

It's a standalone program, **not** an in-game addon, because WoW addons can't
make web requests. All data comes from the [Warcraft Logs](https://www.warcraftlogs.com)
public API.

---

## What it can and can't tell you

✅ Great for vetting players who raid and get logged.
⚠️ **Coverage is 100% dependent on Warcraft Logs.** A player who has never been
logged returns **"no data"** — that is *not* proof they've never cleared
content. Enchant/gear info reflects their **most recent logged fight**, which
may not be exactly what they're wearing right now.

---

## Setup (one time)

### 1. Install Python deps

```powershell
cd "$([Environment]::GetFolderPath('Desktop'))\pug-vetter"
python -m pip install -r requirements.txt
```

### 2. Get Warcraft Logs API credentials (free)

1. Go to <https://www.warcraftlogs.com/api/clients/> (log in to your WCL account).
2. Click **Create Client**, give it any name (e.g. `pug-vetter`), and set the
   redirect URL to `http://localhost` (it isn't used).
3. Copy the **Client ID** and **Client Secret**.

### 3. Create your `.env`

Copy `.env.example` to `.env` and fill it in:

```
WCL_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
WCL_CLIENT_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
DEFAULT_REGION=US
DEFAULT_REALM=Spineshatter
```

`DEFAULT_REALM` is optional — it just pre-fills the realm so you can search by
name alone.

---

## Run it

```powershell
python run.py
```

Then open <http://127.0.0.1:8000> in your browser. Type a name, hit **Vet**.
Recent lookups are remembered for quick re-checks during invite spam.

---

## Which raids it shows (and progressing tiers)

The app auto-detects the **live** raids of the current Anniversary expansion from
Warcraft Logs (frozen/old tiers are ignored), so new raid phases appear
automatically as they release. The expansion is set in
[`app/data/raids.py`](app/data/raids.py):

```python
CURRENT_EXPANSION_ID = 1001  # The Burning Crusade
```

When the Anniversary realms advance to the next expansion, bump this number
(`1000` Classic · `1001` TBC · `1002` Wrath · `1003` Cataclysm · `1004` MoP).

To see every zone/expansion and its live/frozen state:

```powershell
python scripts/list_zones.py
```

If auto-detection ever grabs the wrong zones, pin exact IDs in `RAID_ZONE_IDS`
in the same file — when non-empty it's used verbatim.

---

## Tests

```powershell
python -m pytest
```

The tests cover the scoring logic (`app/analyze.py`) against captured JSON
fixtures — no network or credentials required.

---

## Project layout

```
run.py                  launch the web app
app/
  main.py               Flask routes + /api/vet
  wcl_client.py         OAuth token + GraphQL POST
  zones.py              resolve raid zone IDs from WCL
  queries.py            GraphQL query builders
  analyze.py            raw WCL JSON -> scorecard (pure, tested)
  util.py               realm slugify
  config.py             env / .env loading
  data/
    raids.py            which raids to vet + zone-ID override
    enchant_rules.py    which slots should be enchanted
  static/               index.html, app.js, style.css
scripts/list_zones.py   helper to discover zone IDs
tests/                  pytest + JSON fixtures
```

---

## Notes / limitations

- Enchant detection relies on the positional gear-slot order WCL returns. If
  enchants ever look shifted by one slot, fix the indices in
  [`app/data/enchant_rules.py`](app/data/enchant_rules.py).
- Lookups are cached in memory for `CACHE_TTL_SECONDS` (default 10 min) to
  respect the WCL points-based rate limit.
- US/EU regions are in the dropdown; add others by editing the `<select>` in
  `app/static/index.html`.
