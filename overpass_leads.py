"""
overpass_leads.py
------------------
Finds real businesses (via OpenStreetMap's free Overpass API) in a given
city/country that have NO website listed - these are good leads for a
web dev / SMM freelancer, since they clearly don't have an online presence
yet (at least not one they've bothered to add to their map listing).

No API key is required. Overpass is a public, donated service though, so be
polite: don't hammer it with huge queries, and let `http_utils.request_with_retry`
handle the occasional 429 (rate limited) / 504 (timeout) response.

Can be run standalone:
    python overpass_leads.py --city "London" --country "GB" --categories restaurant,cafe

...or imported and called from run_daily.py via `run_for_target()`.
"""

import argparse
from datetime import date

from http_utils import request_with_retry
from csv_utils import read_existing_keys, append_rows

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Column order for the output CSV.
FIELDNAMES = ["name", "phone", "address", "category", "city", "country", "reason", "date_found"]

# Maps our human-friendly category names to OpenStreetMap tags.
# A category can map to more than one tag (e.g. "salon" could be tagged
# shop=hairdresser OR shop=beauty on OSM) - all listed tags are searched
# and the results combined.
# A value of "*" means "any value for this key" (used for the generic "shop" category).
CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "dentist": [("amenity", "dentist")],
    "clinic": [("amenity", "clinic")],
    "gym": [("leisure", "fitness_centre")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "lawyer": [("office", "lawyer")],
    "real_estate": [("office", "estate_agent")],
    "accountant": [("office", "accountant")],
    "shop": [("shop", "*")],
}

# A few common ways people might type a country - normalized to the ISO
# 3166-1 alpha-2 code that OpenStreetMap's ["ISO3166-1"=...] tag expects.
COUNTRY_ISO_ALIASES = {
    "US": "US", "USA": "US", "U.S.": "US", "U.S.A.": "US",
    "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US",
    "UK": "GB", "GB": "GB", "U.K.": "GB",
    "UNITED KINGDOM": "GB", "GREAT BRITAIN": "GB", "BRITAIN": "GB",
}


def normalize_country(country):
    """Turn a user-typed country name into the 2-letter ISO code Overpass expects."""
    key = country.strip().upper()
    if key in COUNTRY_ISO_ALIASES:
        return COUNTRY_ISO_ALIASES[key]
    if len(key) == 2:
        # Assume the caller already passed a valid ISO code (e.g. "DE", "FR").
        return key
    raise ValueError(
        f"Don't recognize country '{country}'. Use a 2-letter ISO code (e.g. 'US', 'GB') "
        f"or one of: {sorted(set(COUNTRY_ISO_ALIASES))}"
    )


def build_overpass_query(city, iso_code, tag_pairs, timeout=180):
    """
    Build the Overpass QL query text.

    Overpass QL reads like a little query language: `area[...]->.name` finds
    a named area and stores it under `.name` so later lines can reference it.
    Chaining `(area.a)(area.b)` after node/way means "in area a AND in area b" -
    that's how we narrow "a place called London" down to "London, in GB"
    (city names alone aren't unique worldwide).
    `[!"website"]` means "this tag is absent" - that's our "no website" filter.
    """
    lines = [
        f"[out:json][timeout:{timeout}];",
        f'area["ISO3166-1"="{iso_code}"]["admin_level"="2"]->.country;',
        f'area["name"="{city}"]->.searchArea;',
        "(",
    ]
    for key, value in tag_pairs:
        tag_filter = f'["{key}"]' if value == "*" else f'["{key}"="{value}"]'
        no_website_filter = '[!"website"][!"contact:website"]'
        common = f"(area.searchArea)(area.country){tag_filter}{no_website_filter}"
        lines.append(f"  node{common};")
        lines.append(f"  way{common};")
    lines.append(");")
    lines.append("out center tags;")
    return "\n".join(lines)


def _first_present(tags, keys):
    """Return the first non-empty value found in `tags` for any of `keys`."""
    for key in keys:
        value = tags.get(key)
        if value:
            return value
    return ""


def _build_address(tags, fallback_city):
    housenumber = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    city = tags.get("addr:city", fallback_city)
    postcode = tags.get("addr:postcode", "")

    street_line = f"{housenumber} {street}".strip()
    parts = [part for part in [street_line, city, postcode] if part]
    return ", ".join(parts)


def parse_elements(elements, category, city, country):
    """Turn raw Overpass JSON elements into row dicts matching FIELDNAMES."""
    today = date.today().isoformat()
    rows = []
    for element in elements:
        tags = element.get("tags", {}) or {}
        name = tags.get("name", "").strip()
        if not name:
            continue  # Skip unnamed entries - not usable as a lead.

        rows.append({
            "name": name,
            "phone": _first_present(tags, ["phone", "contact:phone"]),
            "address": _build_address(tags, city),
            "category": category,
            "city": city,
            "country": country,
            "reason": (
                f"No website listed on OpenStreetMap for this {category.replace('_', ' ')} "
                f"- potential web design / marketing lead."
            ),
            "date_found": today,
        })
    return rows


def fetch_businesses_without_website(city, country, category):
    """Query Overpass for one category in one city/country. Returns raw row dicts."""
    if category not in CATEGORY_TAGS:
        raise ValueError(f"Unknown category '{category}'. Supported: {sorted(CATEGORY_TAGS)}")

    iso_code = normalize_country(country)
    query = build_overpass_query(city, iso_code, CATEGORY_TAGS[category])

    # Overpass accepts the query as a POST body under the "data" field.
    response = request_with_retry("POST", OVERPASS_URL, data={"data": query})
    response.raise_for_status()
    payload = response.json()
    elements = payload.get("elements", [])
    return parse_elements(elements, category, city, country)


def run_for_target(city, country, category, output_csv):
    """
    Fetch leads for one (city, country, category) combo and append any new
    ones to output_csv (skipping rows already present, matched on name+address).

    Returns the list of newly-added row dicts (useful for reporting counts).
    """
    candidate_rows = fetch_businesses_without_website(city, country, category)

    def dedupe_key(row):
        return (row.get("name", "").strip().lower(), row.get("address", "").strip().lower())

    existing_keys = read_existing_keys(output_csv, dedupe_key)

    new_rows = []
    seen_this_run = set()
    for row in candidate_rows:
        key = dedupe_key(row)
        if key in existing_keys or key in seen_this_run:
            continue
        seen_this_run.add(key)
        new_rows.append(row)

    append_rows(output_csv, FIELDNAMES, new_rows)
    return new_rows


def main():
    parser = argparse.ArgumentParser(description="Find businesses with no website via OpenStreetMap.")
    parser.add_argument("--city", required=True, help='e.g. "London"')
    parser.add_argument("--country", required=True, help='2-letter ISO code or name, e.g. "GB" / "United Kingdom"')
    parser.add_argument(
        "--categories",
        default="all",
        help=f"Comma-separated categories, or 'all'. Supported: {sorted(CATEGORY_TAGS)}",
    )
    parser.add_argument("--output", default="data/leads_overpass.csv")
    args = parser.parse_args()

    categories = list(CATEGORY_TAGS) if args.categories == "all" else [c.strip() for c in args.categories.split(",")]

    total_new = 0
    for category in categories:
        print(f"Searching {category} in {args.city}, {args.country}...")
        new_rows = run_for_target(args.city, args.country, category, args.output)
        print(f"  -> {len(new_rows)} new lead(s)")
        total_new += len(new_rows)

    print(f"Done. {total_new} new lead(s) written to {args.output}")


if __name__ == "__main__":
    main()
