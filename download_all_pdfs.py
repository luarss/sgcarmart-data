#!/usr/bin/env python3
import argparse
import json
import sys
import os
from datetime import datetime

from constants import BASE_URL
from sgcarmart.utils.file_utils import load_dealer_brand_mapping, normalize_brand_name
from sgcarmart.core.downloader import download_all_pdfs_from_page


def main():
    parser = argparse.ArgumentParser(
        description="SGCarMart PDF Downloader - Download all pricelists for dealers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all
  %(prog)s --brand mg
  %(prog)s --brand toyota
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Download all PDFs for all dealers"
    )
    group.add_argument(
        "--brand",
        type=str,
        metavar="NAME",
        help="Download all PDFs for specific brand"
    )

    args = parser.parse_args()

    print("SGCarMart PDF Downloader")
    print("=" * 60)

    dealer_brand_mapping = load_dealer_brand_mapping()
    all_results = []
    output_dir = "data/pricelists"

    if args.all:
        print(f"Downloading PDFs for all {len(dealer_brand_mapping)} dealers\n")

        for did, dbrand in dealer_brand_mapping.items():
            purl = f"{BASE_URL}/new-cars/pricelists/{did}/{normalize_brand_name(dbrand)}"
            print(f"\n[Dealer {did} - {dbrand}]")
            results = download_all_pdfs_from_page(purl, dbrand, output_dir)
            all_results.extend(results)

    elif args.brand:
        matching_dealers = {did: dbrand for did, dbrand in dealer_brand_mapping.items()
                          if normalize_brand_name(dbrand) == normalize_brand_name(args.brand)}

        if not matching_dealers:
            print(f"Error: No dealers found for brand '{args.brand}'")
            print(f"\nAvailable brands: {', '.join(sorted(set(dealer_brand_mapping.values())))}")
            sys.exit(1)

        print(f"Downloading PDFs for brand '{args.brand}' ({len(matching_dealers)} dealer(s))\n")

        for did, dbrand in matching_dealers.items():
            purl = f"{BASE_URL}/new-cars/pricelists/{did}/{normalize_brand_name(dbrand)}"
            print(f"\n[Dealer {did} - {dbrand}]")
            results = download_all_pdfs_from_page(purl, dbrand, output_dir)
            all_results.extend(results)

    success_count = sum(1 for r in all_results if r["status"] == "success")
    skipped_count = sum(1 for r in all_results if r["status"] == "skipped")
    failed_count = sum(1 for r in all_results if r["status"] in ["failed", "error"])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total PDFs found: {len(all_results)}")
    print(f"Downloaded: {success_count}")
    print(f"Skipped (already exist): {skipped_count}")
    print(f"Failed: {failed_count}")

    report_file = f"data/pdf_download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("data", exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump({
            "mode": "all" if args.all else "brand",
            "brand_filter": args.brand if args.brand else None,
            "output_directory": output_dir,
            "timestamp": datetime.now().isoformat(),
            "results": all_results,
            "summary": {
                "total": len(all_results),
                "downloaded": success_count,
                "skipped": skipped_count,
                "failed": failed_count
            }
        }, f, indent=2)

    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    main()
