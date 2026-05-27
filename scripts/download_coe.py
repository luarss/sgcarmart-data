#!/usr/bin/env python3
"""Download COE bidding results from data.gov.sg and save one JSON file per year."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from sgcarmart.coe import fetch_coe_results, save_coe_data
from sgcarmart.coe.client import COEAPIError
from sgcarmart.constants import COE_OUTPUT_DIR

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main():
    parser = argparse.ArgumentParser(description="Download COE bidding results from data.gov.sg")
    parser.add_argument("--output-dir", default=COE_OUTPUT_DIR, help=f"Output directory (default: {COE_OUTPUT_DIR})")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print summary without writing files")
    args = parser.parse_args()

    print("COE Bidding Results Downloader")
    print("=" * 60)
    if os.environ.get("DATA_GOV_API_KEY"):
        print("API key: loaded")
    else:
        print("API key: not set (rate limits apply)")

    try:
        records = fetch_coe_results()
    except COEAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(records)} records from data.gov.sg")

    if args.dry_run:
        from sgcarmart.coe import group_by_year

        by_year = group_by_year(records)
        print()
        for year in sorted(by_year):
            print(f"  {year}: {len(by_year[year])} records")
        print()
        print("Dry run - no files written.")
        return

    summary = save_coe_data(records, args.output_dir)
    print(f"Saved to {args.output_dir}/")
    for year, count in sorted(summary.items()):
        print(f"  coe_results_{year}.json: {count} records")


if __name__ == "__main__":
    main()
