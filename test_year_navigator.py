#!/usr/bin/env python3
"""
Test the simplified navigator
"""
import json
from sgcarmart.core.year_navigator import discover_historical_pdfs


def main():
    dealer_id = "2"
    brand_name = "aston%20martin"

    print(f"Testing simplified navigator for dealer {dealer_id} ({brand_name})")
    print("=" * 60)

    pdfs = discover_historical_pdfs(dealer_id, brand_name, headless=True)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    total_pdfs = sum(len(dates) for dates in pdfs.values())
    print(f"Total years found: {len(pdfs)}")
    print(f"Total PDFs found: {total_pdfs}")

    output_file = "data/simple_navigator_results.json"
    with open(output_file, 'w') as f:
        json.dump(pdfs, f, indent=2)

    print(f"\nFull results saved to: {output_file}")


if __name__ == "__main__":
    main()
