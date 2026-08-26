"""
companies_house_leads.py
-------------------------
Finds UK companies incorporated in the last N days whose name matches an
industry keyword, using the free UK Companies House API. Freshly-incorporated
companies are good leads: they very likely don't have a website/socials set
up yet.

Requires a free API key from Companies House (see README.md for how to get
one). The key is passed as the HTTP Basic Auth *username*, with an empty
password - that's just how this particular API does auth, no OAuth needed.

Can be run standalone:
    python companies_house_leads.py --keyword marketing --days-back 14
(reads the key from the COMPANIES_HOUSE_API_KEY environment variable, or pass --api-key)

...or imported and called from run_daily.py via `run_for_target()`.
"""

import argparse
import os
from datetime import date, timedelta

from requests.auth import HTTPBasicAuth

from http_utils import request_with_retry
from csv_utils import read_existing_keys, append_rows

BASE_URL = "https://api.company-information.service.gov.uk/advanced-search/companies"

FIELDNAMES = ["name", "company_number", "incorporated_on", "status", "address", "keyword", "reason", "date_found"]

# Companies House caps how many results you can page through per search and
# per page - these are generous defaults for a daily keyword search.
PAGE_SIZE = 100
MAX_RESULTS = 500


def _build_address(registered_office_address):
    """Registered office address comes back as several optional fields - join whichever exist."""
    addr = registered_office_address or {}
    fields = ["premises", "address_line_1", "address_line_2", "locality", "region", "postal_code", "country"]
    parts = [addr.get(field) for field in fields if addr.get(field)]
    return ", ".join(parts)


def search_companies_house(keyword, days_back, api_key, max_results=MAX_RESULTS):
    """
    Query the Companies House advanced search API for companies whose name
    contains `keyword`, incorporated within the last `days_back` days.

    Returns a list of raw item dicts as returned by the API.
    """
    today = date.today()
    from_date = today - timedelta(days=days_back)
    auth = HTTPBasicAuth(api_key, "")  # API key goes in as the username; password is blank.

    all_items = []
    start_index = 0

    while len(all_items) < max_results:
        params = {
            "company_name_includes": keyword,
            "incorporated_from": from_date.isoformat(),
            "incorporated_to": today.isoformat(),
            "size": PAGE_SIZE,
            "start_index": start_index,
        }
        response = request_with_retry("GET", BASE_URL, params=params, auth=auth)

        if response.status_code == 401:
            raise RuntimeError(
                "Companies House API rejected the API key (401 Unauthorized). "
                "Check that COMPANIES_HOUSE_API_KEY is set correctly - see README.md."
            )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])
        if not items:
            break

        all_items.extend(items)
        total_hits = data.get("hits", len(all_items))
        start_index += PAGE_SIZE
        if start_index >= total_hits:
            break  # We've paged through everything the API has.

    return all_items[:max_results]


def item_to_row(item, keyword, days_back):
    today = date.today().isoformat()
    return {
        "name": item.get("company_name", ""),
        "company_number": item.get("company_number", ""),
        "incorporated_on": item.get("date_of_creation", ""),
        "status": item.get("company_status", ""),
        "address": _build_address(item.get("registered_office_address")),
        "keyword": keyword,
        "reason": (
            f"Newly incorporated company (within the last {days_back} days) matching "
            f"keyword '{keyword}' - likely needs a website, branding, or marketing help."
        ),
        "date_found": today,
    }


def run_for_target(keyword, days_back, api_key, output_csv):
    """
    Fetch new-company leads for one keyword and append any new ones to
    output_csv (skipping companies already present, matched on company_number
    since that's a stable unique ID Companies House assigns).

    Returns the list of newly-added row dicts.
    """
    if not api_key:
        raise ValueError("No Companies House API key provided (set COMPANIES_HOUSE_API_KEY).")

    items = search_companies_house(keyword, days_back, api_key)
    candidate_rows = [item_to_row(item, keyword, days_back) for item in items]

    def dedupe_key(row):
        return row.get("company_number", "").strip()

    existing_keys = read_existing_keys(output_csv, dedupe_key)

    new_rows = []
    seen_this_run = set()
    for row in candidate_rows:
        key = dedupe_key(row)
        if not key or key in existing_keys or key in seen_this_run:
            continue
        seen_this_run.add(key)
        new_rows.append(row)

    append_rows(output_csv, FIELDNAMES, new_rows)
    return new_rows


def main():
    parser = argparse.ArgumentParser(description="Find newly-incorporated UK companies via Companies House.")
    parser.add_argument("--keyword", required=True, help='Industry keyword to match in the company name, e.g. "marketing"')
    parser.add_argument("--days-back", type=int, default=14, help="Look at companies incorporated in the last N days (default 14)")
    parser.add_argument("--api-key", default=None, help="Overrides the COMPANIES_HOUSE_API_KEY environment variable")
    parser.add_argument("--output", default="data/leads_companies_house.csv")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("COMPANIES_HOUSE_API_KEY", "")

    print(f"Searching companies matching '{args.keyword}' incorporated in the last {args.days_back} days...")
    new_rows = run_for_target(args.keyword, args.days_back, api_key, args.output)
    print(f"Done. {len(new_rows)} new lead(s) written to {args.output}")


if __name__ == "__main__":
    main()
