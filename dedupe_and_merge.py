"""
dedupe_and_merge.py
---------------------
Merges the two source CSVs (Overpass + Companies House) into one master
`leads.csv`, with a unified set of columns. A lead is considered a duplicate
if it matches an existing master row on (name, address) - both sources are
checked against the master file and against each other in the same run.

Also flags leads you've already contacted: `contacted.csv` is a file *you*
maintain by hand (just one column, "name") - any master row whose name
matches (case-insensitive) gets contacted=yes.

Can be run standalone:
    python dedupe_and_merge.py
...or imported and called from run_daily.py via `merge_all()`.
"""

import argparse

from csv_utils import read_all_rows, write_all_rows

# Unified column set for the master file. Fields that don't apply to a given
# source (e.g. Overpass leads have no company_number) are left blank.
MASTER_FIELDNAMES = [
    "source", "name", "phone", "address", "category", "city", "country",
    "company_number", "incorporated_on", "status", "keyword",
    "reason", "date_found", "contacted",
]


def _get(row, key):
    return (row.get(key) or "").strip()


def _dedupe_key(row):
    return (_get(row, "name").lower(), _get(row, "address").lower())


def normalize_overpass_row(row):
    return {
        "source": "overpass",
        "name": _get(row, "name"),
        "phone": _get(row, "phone"),
        "address": _get(row, "address"),
        "category": _get(row, "category"),
        "city": _get(row, "city"),
        "country": _get(row, "country"),
        "company_number": "",
        "incorporated_on": "",
        "status": "",
        "keyword": "",
        "reason": _get(row, "reason"),
        "date_found": _get(row, "date_found"),
    }


def normalize_companies_house_row(row):
    return {
        "source": "companies_house",
        "name": _get(row, "name"),
        "phone": "",
        "address": _get(row, "address"),
        "category": _get(row, "keyword"),  # used as the "category" for summary breakdowns
        "city": "",
        "country": "GB",
        "company_number": _get(row, "company_number"),
        "incorporated_on": _get(row, "incorporated_on"),
        "status": _get(row, "status"),
        "keyword": _get(row, "keyword"),
        "reason": _get(row, "reason"),
        "date_found": _get(row, "date_found"),
    }


def merge_all(overpass_csv, companies_house_csv, master_csv, contacted_csv):
    """
    Merge the two source CSVs into master_csv, deduplicating and applying the
    contacted flag. Returns {"total_new": int, "by_category": {category: count}}.
    """
    existing_rows = read_all_rows(master_csv)
    existing_keys = {_dedupe_key(row) for row in existing_rows}

    new_rows = []

    for raw_row in read_all_rows(overpass_csv):
        row = normalize_overpass_row(raw_row)
        key = _dedupe_key(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_rows.append(row)

    for raw_row in read_all_rows(companies_house_csv):
        row = normalize_companies_house_row(raw_row)
        key = _dedupe_key(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_rows.append(row)

    all_rows = existing_rows + new_rows

    # contacted.csv is hand-maintained by the user - just a "name" column.
    contacted_names = {_get(row, "name").lower() for row in read_all_rows(contacted_csv)}
    for row in all_rows:
        row["contacted"] = "yes" if _get(row, "name").lower() in contacted_names else "no"

    write_all_rows(master_csv, MASTER_FIELDNAMES, all_rows)

    by_category = {}
    for row in new_rows:
        category = row.get("category") or "uncategorized"
        by_category[category] = by_category.get(category, 0) + 1

    return {"total_new": len(new_rows), "by_category": by_category}


def main():
    parser = argparse.ArgumentParser(description="Merge and dedupe lead CSVs into a master leads.csv.")
    parser.add_argument("--overpass-csv", default="data/leads_overpass.csv")
    parser.add_argument("--companies-house-csv", default="data/leads_companies_house.csv")
    parser.add_argument("--master-csv", default="data/leads.csv")
    parser.add_argument("--contacted-csv", default="data/contacted.csv")
    args = parser.parse_args()

    summary = merge_all(args.overpass_csv, args.companies_house_csv, args.master_csv, args.contacted_csv)

    print(f"{summary['total_new']} new lead(s) merged into {args.master_csv}")
    for category, count in sorted(summary["by_category"].items()):
        print(f"  - {category}: {count}")


if __name__ == "__main__":
    main()
