import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.pdf_extractor import GeminiPDFExtractor
from sgcarmart.constants import EXCLUDED_BRANDS

load_dotenv(Path(__file__).parent / ".env")


def _process_single_pdf(extractor, pdf_file, model, output_dir):
    """Extract a single PDF and return the file result dict."""
    extraction = extractor.extract_from_pdf(pdf_file, model=model)
    output_path = extractor.save_extraction(extraction=extraction, output_dir=output_dir)

    file_result = {
        "filename": pdf_file.name,
        "status": "success",
        "confidence": extraction.extraction_confidence,
        "models_extracted": len(extraction.pricelist.models),
        "output_path": str(output_path),
    }

    if extraction.metadata.api_usage:
        api = extraction.metadata.api_usage
        file_result["api_usage"] = {
            "model": api.model_name,
            "tokens": api.total_tokens,
            "cost_usd": float(api.total_cost_usd),
            "is_free": api.is_free_tier,
        }

    return file_result, extraction.metadata.api_usage


def _print_batch_summary(results):
    """Print batch extraction summary and cost breakdown."""
    cost = results["cost_summary"]
    print(f"\n\n{'=' * 60}")
    print("BATCH EXTRACTION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Attempted: {results['summary']['total_attempted']}")
    print(f"Total Successful: {results['summary']['total_successful']}")
    print(f"Total Failed: {results['summary']['total_failed']}")

    print("\nCost Summary:")
    print(f"  Total Tokens: {cost['total_tokens']:,}")
    print(f"  Input Tokens: {cost['total_input_tokens']:,}")
    print(f"  Output Tokens: {cost['total_output_tokens']:,}")
    print(f"  Free Tier Requests: {cost['free_tier_requests']}")
    print(f"  Paid Requests: {cost['paid_requests']}")
    if cost["total_cost_usd"] == 0:
        print("  Total Cost: FREE")
    else:
        print(f"  Total Cost: ${cost['total_cost_usd']:.6f} USD")
    print(f"{'=' * 60}\n")


def extract_brand_samples(
    brands: list[str],
    base_dir: Path = Path("data/pricelists"),
    year: int = 2025,
    max_per_brand: int = 1,
    output_dir: Path | None = None,
    model: str = GeminiPDFExtractor.DEFAULT_MODEL,
):
    extractor = GeminiPDFExtractor()

    results = {
        "extraction_run": datetime.now().isoformat(),
        "brands": [],
        "summary": {
            "total_attempted": 0,
            "total_successful": 0,
            "total_failed": 0,
        },
        "cost_summary": {
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "free_tier_requests": 0,
            "paid_requests": 0,
        },
    }

    for brand in brands:
        if brand in EXCLUDED_BRANDS:
            print(f"\n{'=' * 60}")
            print(f"❌ ERROR: Brand '{brand}' is in EXCLUDED list")
            print(f"{'=' * 60}")
            continue

        brand_dir = base_dir / brand / str(year)

        if not brand_dir.exists():
            print(f"⚠ Brand directory not found: {brand_dir}")
            continue

        pdf_files = sorted(brand_dir.glob("*.pdf"))[:max_per_brand]

        if not pdf_files:
            print(f"⚠ No PDFs found for {brand}")
            continue

        brand_results = {"brand": brand, "files": []}

        for pdf_file in pdf_files:
            results["summary"]["total_attempted"] += 1
            print(f"\n{'=' * 60}")
            print(f"Processing: {brand} - {pdf_file.name}")
            print(f"{'=' * 60}")

            try:
                file_result, api_usage = _process_single_pdf(extractor, pdf_file, model, output_dir)

                if api_usage:
                    results["cost_summary"]["total_tokens"] += api_usage.total_tokens
                    results["cost_summary"]["total_input_tokens"] += api_usage.input_tokens
                    results["cost_summary"]["total_output_tokens"] += api_usage.output_tokens
                    results["cost_summary"]["total_cost_usd"] += float(api_usage.total_cost_usd)

                    if api_usage.is_free_tier:
                        results["cost_summary"]["free_tier_requests"] += 1
                    else:
                        results["cost_summary"]["paid_requests"] += 1

                brand_results["files"].append(file_result)
                results["summary"]["total_successful"] += 1

            except Exception as e:
                print(f"✗ Failed: {e}")
                brand_results["files"].append({"filename": pdf_file.name, "status": "failed", "error": str(e)})
                results["summary"]["total_failed"] += 1

        results["brands"].append(brand_results)

    _print_batch_summary(results)
    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch extract PDFs for multiple brands")
    parser.add_argument(
        "--brands", nargs="+", default=["toyota", "mercedes-benz", "byd"], help="List of brands to process"
    )
    parser.add_argument("--year", type=int, default=2025, help="Year to process")
    parser.add_argument("--max-per-brand", type=int, default=1, help="Maximum PDFs to process per brand")
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Output directory (default: same directory as PDFs)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=GeminiPDFExtractor.DEFAULT_MODEL,
        help=f"Gemini model to use (e.g., {GeminiPDFExtractor.DEFAULT_MODEL}, gemini-2.5-flash-lite)",
    )

    args = parser.parse_args()

    extract_brand_samples(
        brands=args.brands,
        year=args.year,
        max_per_brand=args.max_per_brand,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        model=args.model,
    )


if __name__ == "__main__":
    main()
