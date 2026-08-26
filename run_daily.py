"""
run_daily.py
-------------
Orchestrator: reads targets.json, runs the Overpass search for every
city/category combo and the Companies House search for every keyword, then
merges everything into data/leads.csv and prints a summary.

This is the single entry point the GitHub Actions workflow calls every day,
and it's also fine to run by hand:
    python run_daily.py
"""

import json
import os
import sys
from pathlib import Path

import overpass_leads
import companies_house_leads
import dedupe_and_merge

DATA_DIR = Path("data")
OVERPASS_CSV = DATA_DIR / "leads_overpass.csv"
COMPANIES_HOUSE_CSV = DATA_DIR / "leads_companies_house.csv"
MASTER_CSV = DATA_DIR / "leads.csv"
CONTACTED_CSV = DATA_DIR / "contacted.csv"


def load_targets(path="targets.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_overpass_targets(targets):
    for entry in targets.get("overpass", []):
        city = entry["city"]
        country = entry["country"]
        categories = entry.get("categories") or list(overpass_leads.CATEGORY_TAGS.keys())

        for category in categories:
            print(f"  Searching {category} in {city}, {country}...")
            try:
                new_rows = overpass_leads.run_for_target(city, country, category, str(OVERPASS_CSV))
                print(f"    -> {len(new_rows)} new lead(s)")
            except Exception as exc:  # noqa: BLE001 - one bad target shouldn't kill the whole run
                print(f"    ! Skipped ({exc})")


def run_companies_house_targets(targets):
    ch_targets = targets.get("companies_house", [])
    if not ch_targets:
        return

    api_key = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
    if not api_key:
        print("  ! COMPANIES_HOUSE_API_KEY is not set - skipping Companies House search.")
        print("    (see README.md for how to get a free key and set it locally / as a GitHub secret)")
        return

    for entry in ch_targets:
        keyword = entry["keyword"]
        days_back = entry.get("days_back", 14)
        print(f"  Searching companies matching '{keyword}' (last {days_back} days)...")
        try:
            new_rows = companies_house_leads.run_for_target(keyword, days_back, api_key, str(COMPANIES_HOUSE_CSV))
            print(f"    -> {len(new_rows)} new lead(s)")
        except Exception as exc:  # noqa: BLE001 - one bad target shouldn't kill the whole run
            print(f"    ! Skipped ({exc})")


def main():
    targets_path = sys.argv[1] if len(sys.argv) > 1 else "targets.json"
    targets = load_targets(targets_path)

    print("=== Step 1: Overpass (OpenStreetMap) business search ===")
    run_overpass_targets(targets)

    print("=== Step 2: Companies House new-company search ===")
    run_companies_house_targets(targets)

    print("=== Step 3: Dedupe + merge into master leads.csv ===")
    summary = dedupe_and_merge.merge_all(
        str(OVERPASS_CSV), str(COMPANIES_HOUSE_CSV), str(MASTER_CSV), str(CONTACTED_CSV)
    )

    print()
    print(f"Summary: {summary['total_new']} new lead(s) found today")
    for category, count in sorted(summary["by_category"].items()):
        print(f"  - {category}: {count}")


if __name__ == "__main__":
    main()
