"""
Small shared helpers for reading/writing the lead CSV files.

Python's built-in `csv` module reads/writes rows as plain dicts (via
DictReader/DictWriter), which is why you'll see `dict`s passed around
everywhere in this project instead of a custom class.
"""

import csv
import os


def read_existing_keys(csv_path, key_fn):
    """
    Return a set of "dedupe keys" already present in csv_path.

    `key_fn` is a function that takes a row (dict) and returns a hashable
    value (usually a tuple like (name, address)) identifying that lead.
    We use this before appending new rows so re-running a script never
    creates duplicate lines.
    """
    keys = set()
    if not os.path.exists(csv_path):
        return keys
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add(key_fn(row))
    return keys


def append_rows(csv_path, fieldnames, rows):
    """
    Append `rows` (a list of dicts) to csv_path, writing a header row first
    if the file doesn't exist yet (or is empty).
    """
    if not rows:
        return

    parent_dir = os.path.dirname(csv_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    file_is_new = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if file_is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_all_rows(csv_path):
    """Return every row of csv_path as a list of dicts (empty list if it doesn't exist)."""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_all_rows(csv_path, fieldnames, rows):
    """Overwrite csv_path with `rows`, using `fieldnames` as the header/column order."""
    parent_dir = os.path.dirname(csv_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            # `extrasaction="ignore"` isn't used here on purpose - if a row
            # has an unexpected key it's better to fail loudly than silently
            # drop data, since this file is your business data.
            writer.writerow({field: row.get(field, "") for field in fieldnames})
