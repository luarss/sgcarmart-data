import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from constants import DEFAULT_BROWSER_MAX_WORKERS, DEFAULT_MAX_WORKERS
from sgcarmart.core.downloader import process_dealer
from sgcarmart.core.year_navigator import discover_historical_pdfs
from sgcarmart.utils.file_utils import load_dealer_brand_mapping

load_dotenv(Path(__file__).parent / "analysis" / ".env")


def parse_year_range(year_arg: str) -> list:
    """
    Parse year argument into a list of years.

    Args:
        year_arg: Year string like '2024' or '2023-2025'

    Returns:
        List of year strings
    """
    if "-" in year_arg:
        start, end = year_arg.split("-")
        return [str(y) for y in range(int(start), int(end) + 1)]
    else:
        return [year_arg]


def process_dealer_historical(
    dealer_id: str, brand_name: str, years: list | None = None, auto_extract=False, extract_model="gemini-2.0-flash-exp"
) -> dict:
    """
    Process a dealer with historical PDF discovery and download.

    Args:
        dealer_id: Dealer ID
        brand_name: Brand name
        years: List of years to download (None = all years)
        extraction_pipeline: Optional ExtractionPipeline instance

    Returns:
        Dict with download results
    """
    from sgcarmart.core.downloader import download_pdf

    try:
        all_pdfs = discover_historical_pdfs(dealer_id, brand_name, headless=True, target_years=years)

        filtered_pdfs = {year: pdfs for year, pdfs in all_pdfs.items() if year in years} if years else all_pdfs

        downloaded = 0
        skipped = 0
        failed = 0

        for _year, pdfs in filtered_pdfs.items():
            for pdf_info in pdfs:
                result = download_pdf(
                    pdf_info["url"],
                    brand_name,
                    output_dir="data/pricelists",
                    auto_extract=auto_extract,
                    extract_model=extract_model,
                )

                if result["status"] == "success":
                    downloaded += 1
                elif result["status"] == "skipped":
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
            "pdfs": filtered_pdfs,
        }
    except Exception as e:
        return {"dealer_id": dealer_id, "brand_name": brand_name, "status": "error", "error": str(e)}


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
        """,
    )

    parser.add_argument("--test", action="store_true", help="Run in test mode (only download MG, Toyota, BMW)")

    parser.add_argument(
        "--year",
        type=str,
        help="Specify year or year range (e.g., 2024 or 2023-2025). If not specified, downloads only latest.",
    )

    parser.add_argument(
        "--browser-workers",
        type=int,
        default=DEFAULT_BROWSER_MAX_WORKERS,
        help=f"Number of parallel browser instances for historical downloads (default: {DEFAULT_BROWSER_MAX_WORKERS})",
    )

    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Disable automatic PDF extraction (default: enabled if GEMINI_API_KEY is set)",
    )

    parser.add_argument(
        "--extract-only", action="store_true", help="Extract existing PDFs without downloading new ones"
    )

    parser.add_argument(
        "--extract-model",
        type=str,
        default="gemini-2.0-flash-exp",
        help="Gemini model to use for extraction (default: gemini-2.0-flash-exp)",
    )

    parser.add_argument("--extract-workers", type=int, default=3, help="Number of concurrent extractions (default: 3)")

    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Force re-extraction of PDFs that already have JSON (only with --extract-only)",
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

    print(f"Total dealers to check: {len(dealer_brand_mapping)}")

    auto_extract = False
    extract_model = args.extract_model

    if args.extract_only:
        print("\nEXTRACT-ONLY MODE: Not yet implemented in simplified version")
        print("Use: uv run python analysis/batch_extract.py --brands <brand> --year 2025")
        return
    elif not args.no_extract and os.getenv("GEMINI_API_KEY"):
        auto_extract = True
        print(f"Extraction: ENABLED (model: {extract_model})")
    elif not args.no_extract and not os.getenv("GEMINI_API_KEY"):
        print("⚠ Warning: GEMINI_API_KEY not set. Skipping auto-extraction.")
        print("⚠ Set GEMINI_API_KEY environment variable to enable automatic extraction.")
    elif args.no_extract:
        print("Extraction: DISABLED (--no-extract flag)")

    print()

    results = []

    if mode == "historical":
        print(f"Processing dealers for historical PDFs with {args.browser_workers} parallel browsers...")
        with ThreadPoolExecutor(max_workers=args.browser_workers) as executor:
            futures = {
                executor.submit(
                    process_dealer_historical, dealer_id, brand_name, years_to_download, auto_extract, extract_model
                ): (dealer_id, brand_name)
                for dealer_id, brand_name in dealer_brand_mapping.items()
            }

            total = len(futures)

            for completed, future in enumerate(as_completed(futures), 1):
                dealer_id, brand_name = futures[future]

                try:
                    result = future.result()
                    results.append(result)

                    if result.get("status") == "success":
                        print(
                            f"[{completed}/{total}] ✓ {brand_name}: Downloaded: {result['downloaded']}, "
                            f"Skipped: {result['skipped']}, Failed: {result['failed']}"
                        )
                    else:
                        print(f"[{completed}/{total}] ✗ {brand_name}: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    print(f"[{completed}/{total}] ✗ {brand_name}: Exception: {e!s}")
                    results.append(
                        {"dealer_id": dealer_id, "brand_name": brand_name, "status": "error", "error": str(e)}
                    )
    else:
        print("Processing dealers in parallel...")
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_dealer, dealer_id, brand_name, auto_extract, extract_model): (
                    dealer_id,
                    brand_name,
                )
                for dealer_id, brand_name in dealer_brand_mapping.items()
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(".", end="", flush=True)
        print()

    report_file = f"data/download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
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

    print(f"\nDownload report: {report_file}")


if __name__ == "__main__":
    main()
