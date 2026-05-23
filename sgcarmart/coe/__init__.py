"""COE bidding results fetcher from data.gov.sg."""

import json
import os
from collections import defaultdict

from sgcarmart.coe.client import COEAPIError, fetch_coe_results
from sgcarmart.coe.models import COERecord
from sgcarmart.utils.file_utils import ensure_directory

__all__ = [
    "COEAPIError",
    "COERecord",
    "fetch_coe_results",
    "group_by_year",
    "save_coe_data",
]


def group_by_year(records: list[dict]) -> dict[str, list[dict]]:
    by_year: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        month = record.get("month", "")
        if not month:
            continue
        year = month[:4]
        by_year[year].append(record)
    return dict(by_year)


def save_coe_data(records: list[dict], output_dir: str = "data/coe") -> dict[str, int]:
    ensure_directory(output_dir)
    by_year = group_by_year(records)
    summary = {}

    for year, year_records in sorted(by_year.items()):
        filepath = os.path.join(output_dir, f"coe_results_{year}.json")
        with open(filepath, "w") as f:
            json.dump(year_records, f, indent=2)
        summary[year] = len(year_records)

    return summary
