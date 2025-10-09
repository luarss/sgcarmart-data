#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from sgcarmart.core.downloader import process_dealer
from sgcarmart.core.year_navigator import discover_historical_pdfs
from sgcarmart.utils.file_utils import load_dealer_brand_mapping

from constants import DEFAULT_MAX_WORKERS


def parse_year_range(year_arg: str) -> list:
    """
    Parse year argument into a list of years.

    Args:
        year_arg: Year string like '2024' or '2023-2025'

    Returns:
        List of year strings
    """
    if '-' in year_arg:
        start, end = year_arg.split('-')
        return [str(y) for y in range(int(start), int(end) + 1)]
    else:
        return [year_arg]


def process_dealer_historical(dealer_id: str, brand_name: str, years: list = None) -> dict:
    """
    Process a dealer with historical PDF discovery and download.

    Args:
        dealer_id: Dealer ID
        brand_name: Brand name
        years: List of years to download (None = all years)

    Returns:
        Dict with download results
    """
    from sgcarmart.core.downloader import download_pdf

    try:
        all_pdfs = discover_historical_pdfs(dealer_id, brand_name, headless=True)

        if years:
            filtered_pdfs = {year: pdfs for year, pdfs in all_pdfs.items() if year in years}
        else:
            filtered_pdfs = all_pdfs

        downloaded = 0
        skipped = 0
        failed = 0

        for year, pdfs in filtered_pdfs.items():
            for pdf_info in pdfs:
                result = download_pdf(pdf_info['url'], brand_name, output_dir="data/pricelists")

                if result['status'] == 'success':
                    downloaded += 1
                elif result['status'] == 'skipped':
                    skipped += 1
                else:
                    failed += 1
                    print(f"    ✗ {result['filename']}: {result['message']}")

        total_pdfs = sum(len(pdfs) for pdfs in filtered_pdfs.values())

        return {
            "dealer_id": dealer_id,
            "brand_name": brand_name,
            "status": "success",
            "years": list(filtered_pdfs.keys()),
            "total_pdfs": total_pdfs,
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
            "pdfs": filtered_pdfs
        }
    except Exception as e:
        return {
            "dealer_id": dealer_id,
            "brand_name": brand_name,
            "status": "error",
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description="SGCarMart Pricelist Downloader - Download latest pricelists for dealers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --test
  %(prog)s --year 2024
  %(prog)s --year 2023-2025
        """
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (only download MG, Toyota, BMW)"
    )

    parser.add_argument(
        "--year",
        type=str,
        help="Specify year or year range (e.g., 2024 or 2023-2025). If not specified, downloads only latest."
    )

    args = parser.parse_args()

    dealer_brand_mapping = load_dealer_brand_mapping()

    print("SGCarMart Pricelist Downloader")
    print("=" * 60)

    if args.test:
        test_dealers = {"82": "mg", "44": "toyota", "4": "bmw"}
        dealer_brand_mapping = test_dealers
        print("TEST MODE: Processing only MG, Toyota, BMW")

    years_to_download = None
    if args.year:
        years_to_download = parse_year_range(args.year)
        print(f"HISTORICAL MODE: Downloading years {years_to_download}")
        mode = "historical"
    else:
        print("LATEST MODE: Downloading only latest pricelists")
        mode = "latest"

    print(f"Total dealers to check: {len(dealer_brand_mapping)}\n")

    results = []

    if mode == "historical":
        print("Processing dealers for historical PDFs...")
        for dealer_id, brand_name in dealer_brand_mapping.items():
            print(f"\nProcessing {brand_name} (dealer {dealer_id})...")
            result = process_dealer_historical(dealer_id, brand_name, years_to_download)
            results.append(result)
            if result.get("status") == "success":
                print(f"  ✓ Downloaded: {result['downloaded']}, Skipped: {result['skipped']}, Failed: {result['failed']}")
            else:
                print(f"  ✗ Error: {result.get('error')}")
    else:
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

    report_file = f"data/download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total dealers scanned: {len(dealer_brand_mapping)}")

    if mode == "historical":
        total_pdfs = sum(r.get("total_pdfs", 0) for r in results if r.get("status") == "success")
        success_count = sum(1 for r in results if r.get("status") == "success")
        print(f"Successful dealers: {success_count}")
        print(f"Total PDFs discovered: {total_pdfs}")
    else:
        downloaded_count = sum(1 for r in results if r.get("status") == "success")
        found_count = sum(1 for r in results if r.get("status") in ["success", "failed"])
        print(f"Pricelists found: {found_count}")
        print(f"Successfully downloaded: {downloaded_count}")

    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    main()
