import argparse
import json
import logging
import sys
from pathlib import Path

from sgcarmart.utils.pdf_checker import check_pdf_corruption, check_pdfs_in_directory, print_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _handle_single_file(file_path, output_path):
    """Check a single PDF file and optionally save results to JSON."""
    logger.info(f"Checking single PDF: {file_path}")
    result = check_pdf_corruption(file_path)

    print(f"\nFile: {result.file_path}")
    print(f"Status: {'VALID' if result.is_valid else 'INVALID'}")

    if not result.is_valid:
        print(f"Error Type: {result.error_type}")
        print(f"Error Message: {result.error_message}")
    else:
        print(f"Page Count: {result.page_count}")
        print(f"Has Text: {result.has_text}")
        print(f"Is Encrypted: {result.is_encrypted}")

    if output_path:
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"Results saved to {output_path}")

    sys.exit(0 if result.is_valid else 1)


def _handle_directory_check(directory, output_path, verbose=False):
    """Check all PDFs in a directory and print results."""
    logger.info(f"Checking PDFs in: {directory}")
    results = check_pdfs_in_directory(directory)

    if verbose:
        print(f"\n{'=' * 80}")
        print("Detailed Results:")
        print(f"{'=' * 80}")
        for result in results:
            status = "VALID" if result.is_valid else f"INVALID ({result.error_type})"
            print(f"\n{result.file_path}: {status}")
            if result.is_valid:
                print(f"  Pages: {result.page_count}, Has Text: {result.has_text}, Encrypted: {result.is_encrypted}")
            else:
                print(f"  Error: {result.error_message}")

    print_summary(results)

    if output_path:
        with open(output_path, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)
        logger.info(f"Results saved to {output_path}")

    invalid_count = sum(1 for r in results if not r.is_valid)
    sys.exit(0 if invalid_count == 0 else 1)


def _resolve_directory(args):
    """Resolve the target directory based on --directory, --brand, and --year."""
    directory = Path(args.directory)

    if args.brand:
        directory = directory / args.brand
        if not directory.exists():
            logger.error(f"Brand directory not found: {directory}")
            sys.exit(1)
        logger.info(f"Checking PDFs for brand: {args.brand}")

    if args.year and not args.brand:
        pattern = f"**/{args.year}/*.pdf"
        logger.info(f"Checking PDFs for year: {args.year}")
        results = check_pdfs_in_directory(directory, pattern=pattern)
        print_summary(results)
        if args.output:
            with open(args.output, "w") as f:
                json.dump([r.to_dict() for r in results], f, indent=2)
            logger.info(f"Results saved to {args.output}")
        invalid_count = sum(1 for r in results if not r.is_valid)
        sys.exit(0 if invalid_count == 0 else 1)
        return None  # unreachable, but satisfies type checker

    if args.year and args.brand:
        directory = directory / args.year

    return directory


def main():
    parser = argparse.ArgumentParser(
        description="Check PDFs for corruption using pypdf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_pdfs.py                                    # Check all PDFs in data/pricelists
  python check_pdfs.py --directory data/pricelists/toyota # Check only Toyota PDFs
  python check_pdfs.py --file data/pricelists/toyota/2025/toyota_44_2025-01-10.pdf
  python check_pdfs.py --brand byd                        # Check only BYD PDFs
  python check_pdfs.py --year 2025                        # Check only 2025 PDFs
  python check_pdfs.py --output results.json              # Save results to JSON
        """,
    )

    parser.add_argument(
        "--directory",
        type=str,
        default="data/pricelists",
        help="Directory to check for PDFs (default: data/pricelists)",
    )
    parser.add_argument("--file", type=str, help="Check a single PDF file")
    parser.add_argument("--brand", type=str, help="Check only PDFs for a specific brand (e.g., toyota, byd)")
    parser.add_argument("--year", type=str, help="Check only PDFs from a specific year (e.g., 2025)")
    parser.add_argument("--output", type=str, help="Output results to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Show detailed information for all PDFs")

    args = parser.parse_args()

    if args.file:
        _handle_single_file(args.file, args.output)

    directory = _resolve_directory(args)
    if directory is not None:
        _handle_directory_check(directory, args.output, args.verbose)


if __name__ == "__main__":
    main()
