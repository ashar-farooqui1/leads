# Lead Generator (US/UK, 100% free)

Finds sales leads for web dev / SMM services from two free, keyless(-ish) sources:

1. **OpenStreetMap (Overpass API)** — existing businesses (restaurants, cafes, dentists,
   gyms, salons, lawyers, real estate agents, accountants, shops, etc.) that have **no
   website** listed on their map entry. No signup, no API key.
2. **UK Companies House API** — UK companies incorporated in the last N days matching an
   industry keyword (e.g. "marketing", "software"). Free API key, no cost, no card required.

Everything runs on a daily schedule via **GitHub Actions** for $0 — no server, no paid APIs,
works even if your laptop is off. This tool only *finds and lists* leads to a CSV; it does
**not** call, text, or email anyone.

## Project layout

```
overpass_leads.py           Overpass (OSM) "no website" business finder
companies_house_leads.py    Companies House "new company" finder
dedupe_and_merge.py         Merges both sources into data/leads.csv, dedupes, flags contacted
run_daily.py                Orchestrator: runs everything above for all targets.json entries
http_utils.py                Shared retry/backoff helper for flaky free APIs
csv_utils.py                 Shared CSV read/append/write helpers
targets.json                 Your editable list of cities/categories/keywords to search
data/leads.csv                Master output — the file you actually work leads from
data/contacted.csv            You maintain this by hand (see below)
.github/workflows/daily-leads.yml   Runs everything once a day for free
```

## 1. Get a free Companies House API key

1. Go to https://developer.company-information.service.gov.uk/ and sign up (free).
2. Under "Manage Applications", create a new application (choose **Live**).
3. Open the application and copy its **REST API key** — this is what goes in
   `COMPANIES_HOUSE_API_KEY`.

The key is sent as an HTTP Basic Auth username with a blank password — that's just how this
particular API authenticates, there's nothing else to configure.

## 2. Editing `targets.json`

This is the only file you need to touch to change *what* gets searched.

```json
{
  "overpass": [
    { "city": "London", "country": "GB", "categories": ["restaurant", "cafe", "dentist"] }
  ],
  "companies_house": [
    { "keyword": "marketing", "days_back": 14 }
  ]
}
```

- `city` / `country` — any city name; `country` accepts `"US"`, `"GB"`, `"United States"`,
  `"United Kingdom"`, etc. (see `COUNTRY_ISO_ALIASES` in `overpass_leads.py` to add more).
- `categories` — pick from: `restaurant`, `cafe`, `dentist`, `clinic`, `gym`, `salon`,
  `lawyer`, `real_estate`, `accountant`, `shop` (or omit `categories` entirely to search all
  of them). These map to OpenStreetMap tags in `CATEGORY_TAGS` in `overpass_leads.py` if you
  want to add your own.
- `keyword` — matched against UK company *names* (e.g. `"marketing"` matches "Acme Marketing
  Ltd"). `days_back` — how many days back to look for newly incorporated companies.

Add as many entries as you like to either list.

## 3. Running locally

```bash
python -m venv .venv
.venv\Scripts\activate        # (Windows) — use `source .venv/bin/activate` on Mac/Linux
pip install -r requirements.txt

# Companies House needs the key as an environment variable:
setx COMPANIES_HOUSE_API_KEY "your-key-here"   # Windows (restart terminal after)
# or: export COMPANIES_HOUSE_API_KEY=your-key-here   (Mac/Linux, current session only)

python run_daily.py
```

This reads `targets.json`, appends any new leads to `data/leads_overpass.csv` and
`data/leads_companies_house.csv`, merges everything into `data/leads.csv`, and prints a
summary like:

```
Summary: 14 new lead(s) found today
  - cafe: 3
  - marketing: 2
  - restaurant: 9
```

You can also run either finder on its own, e.g. to test one city without touching
`targets.json`:

```bash
python overpass_leads.py --city "London" --country "GB" --categories restaurant,cafe
python companies_house_leads.py --keyword marketing --days-back 7
python dedupe_and_merge.py
```

### Marking leads as contacted

`data/contacted.csv` is **yours to maintain by hand** — it's a single-column CSV:

```csv
name
Acme Marketing Ltd
Joe's Cafe
```

Every time you run `dedupe_and_merge.py` (directly, or via `run_daily.py`), every row in
`data/leads.csv` gets its `contacted` column recalculated against this file (case-insensitive
name match). So: after you reach out to a lead, just add its exact name to `contacted.csv`.

## 4. How the GitHub Actions automation works

`.github/workflows/daily-leads.yml` runs `run_daily.py` on a schedule and commits the updated
CSVs back to the repo, for free, using GitHub's hosted runners.

**Setup:**
1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions → New repository secret**, name it
   `COMPANIES_HOUSE_API_KEY`, and paste your key. It's never written into any file, only read
   from this secret at run time.
3. That's it — the workflow already has `permissions: contents: write`, so it can commit
   `data/leads.csv` back to the repo after each run.

**Changing the schedule:** edit the `cron:` line in the workflow file. Cron times are always
**UTC**. For example `'0 7 * * *'` = 07:00 UTC every day; `'30 18 * * *'` = 18:30 UTC.

**Running it manually:** the workflow also has `workflow_dispatch` enabled, so you can go to
the **Actions** tab on GitHub, select "Daily Lead Generation", and click **Run workflow**
any time, instead of waiting for the schedule.

## Notes & limits

- Overpass is a shared, donated public service — queries are intentionally scoped to one
  city/category at a time, and `http_utils.py` retries with backoff on 429/504 responses
  (which happen fairly often under load). Avoid adding dozens of huge cities at once.
- Companies House's advanced search matches the **keyword against company names**, not a
  formal industry/SIC classification — e.g. `"software"` will match "XYZ Software Ltd" but
  not necessarily every software company. You can extend `companies_house_leads.py` to filter
  by `sic_codes` instead if you want stricter industry matching.
- This tool does not call, email, or text anyone — it only produces `data/leads.csv` for you
  to work manually.
