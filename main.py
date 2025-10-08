#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from sgcarmart.core.downloader import process_dealer
from sgcarmart.utils.file_utils import load_dealer_brand_mapping

from constants import DEFAULT_MAX_WORKERS


def main():
    parser = argparse.ArgumentParser(
        description="SGCarMart Pricelist Downloader - Download latest pricelists for dealers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --test
        """
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (only download MG, Toyota, BMW)"
    )

    args = parser.parse_args()

    dealer_brand_mapping = load_dealer_brand_mapping()

    print("SGCarMart Pricelist Downloader")
    print("=" * 60)

    if args.test:
        test_dealers = {"82": "mg", "44": "toyota", "4": "bmw"}
        dealer_brand_mapping = test_dealers
        print("TEST MODE: Processing only MG, Toyota, BMW")

    print(f"Total dealers to check: {len(dealer_brand_mapping)}\n")

    results = []

    print("Processing dealers in parallel...")
    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_dealer, dealer_id, brand_name): (dealer_id, brand_name)
            for dealer_id, brand_name in dealer_brand_mapping.items()
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(".", end="", flush=True)
    print()

    downloaded_count = sum(1 for r in results if r.get("status") == "success")
    found_count = sum(1 for r in results if r.get("status") in ["success", "failed"])

    report_file = f"data/download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total dealers scanned: {len(dealer_brand_mapping)}")
    print(f"Pricelists found: {found_count}")
    print(f"Successfully downloaded: {downloaded_count}")
    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    main()
