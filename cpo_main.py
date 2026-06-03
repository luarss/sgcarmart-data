"""
CLI for scraping certified pre-owned (CPO) car listings.

Usage:
    uv run cpo_main.py                         # scrape all sites
    uv run cpo_main.py --site ic_preowned      # one site
    uv run cpo_main.py --test                  # test mode (3 sites)
    uv run cpo_main.py --workers 2             # limit parallel browsers
    uv run cpo_main.py --no-headless           # show browser windows
"""
import argparse
import sys

from sgcarmart.core.cpo import _TEST_SITES, ALL_SCRAPERS, run_all, save_results


def main() -> None:
    parser = argparse.ArgumentParser(description="CPO car listing scraper")
    parser.add_argument(
        "--site",
        nargs="+",
        choices=list(ALL_SCRAPERS.keys()),
        metavar="SITE",
        help=f"Sites to scrape (default: all). Choices: {', '.join(ALL_SCRAPERS)}",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help=f"Test mode: scrape only {', '.join(_TEST_SITES)}",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Parallel browser instances (default: 3)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser windows (useful for debugging)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/cpo",
        help="Output directory (default: data/cpo)",
    )
    args = parser.parse_args()

    sites = args.site
    if args.test:
        sites = _TEST_SITES

    headless = not args.no_headless

    print(f"Scraping {'test sites' if args.test else sites or 'all sites'}...")
    listings, site_results = run_all(sites=sites, headless=headless, max_workers=args.workers)

    path = save_results(listings, site_results, output_dir=args.output_dir)
    print(f"\nTotal: {len(listings)} listings → {path}")

    failed = [name for name, r in site_results.items() if r["status"] == "error"]
    if failed:
        print(f"Failed sites: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
