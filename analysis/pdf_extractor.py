import base64
import json
import os
import sys
from pathlib import Path
from datetime import date
from typing import Optional

from openai import OpenAI
from pydantic import ValidationError
from dotenv import load_dotenv

from analysis.schema import SGCarMartPriceListExtraction, APIUsageStats

load_dotenv(Path(__file__).parent / ".env")


class GeminiPDFExtractor:
    PRICING = {
        "gemini-2.0-flash-exp": {
            "input_per_million": 0.00,
            "output_per_million": 0.00,
            "is_free": True,
            "free_until": "2025-05-31"
        },
        "gemini-2.0-flash": {
            "input_per_million": 0.10,
            "output_per_million": 0.40,
            "is_free": False
        },
        "gemini-1.5-flash": {
            "input_per_million": 0.075,
            "output_per_million": 0.30,
            "is_free": False
        },
        "gemini-1.5-flash-8b": {
            "input_per_million": 0.0375,
            "output_per_million": 0.15,
            "is_free": False
        },
        "gemini-1.5-pro": {
            "input_per_million": 1.25,
            "output_per_million": 5.00,
            "is_free": False
        },
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or constructor")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> APIUsageStats:
        pricing = self.PRICING.get(model, self.PRICING["gemini-2.0-flash"])

        input_cost = (input_tokens / 1_000_000) * pricing["input_per_million"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]
        total_cost = input_cost + output_cost

        return APIUsageStats(
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_cost,
            is_free_tier=pricing.get("is_free", False)
        )

    def encode_pdf(self, pdf_path: Path) -> str:
        with open(pdf_path, "rb") as pdf_file:
            return base64.standard_b64encode(pdf_file.read()).decode("utf-8")

    def extract_metadata_from_path(self, pdf_path: Path) -> dict:
        parts = pdf_path.parts
        filename = pdf_path.name

        brand_folder = parts[-3] if len(parts) >= 3 else "unknown"
        year_folder = int(parts[-2]) if len(parts) >= 2 and parts[-2].isdigit() else 2025

        filename_parts = filename.replace(".pdf", "").split("_")
        dealer_id = filename_parts[1] if len(filename_parts) > 1 else "unknown"
        pdf_date_str = filename_parts[2] if len(filename_parts) > 2 else str(date.today())

        try:
            pdf_date = date.fromisoformat(pdf_date_str)
        except ValueError:
            pdf_date = date.today()

        pdf_size_kb = pdf_path.stat().st_size / 1024

        return {
            "source_filename": filename,
            "extraction_date": date.today(),
            "dealer_id": dealer_id,
            "pdf_date": pdf_date,
            "brand_folder": brand_folder,
            "year_folder": year_folder,
            "pdf_size_kb": pdf_size_kb,
        }

    def create_extraction_prompt(self) -> str:
        return """You are an expert data extraction assistant specialized in extracting car pricing information from Singapore dealer price lists.

Extract the following information from this PDF pricelist:

1. CAR MODELS:
   CRITICAL: Group ALL variants under a SINGLE model entry, regardless of powertrain type.
   DO NOT create duplicate model entries for different powertrains.

   For each car model in the pricelist, extract:
   - brand: Brand name (e.g., "Toyota", "BMW", "Mercedes-Benz")
   - model_name: Model name (e.g., "COROLLA ALTIS", "YARIS CROSS", "HARRIER")
   - category: Vehicle category - use these guidelines:
     * SEDAN: Traditional 4-door passenger cars with separate trunk (Corolla Altis, Camry, Crown)
     * SUV: Sport Utility Vehicles with higher ground clearance (Harrier, RAV4, Corolla Cross, Yaris Cross, Fortuner, Land Cruiser)
     * MPV: Multi-Purpose Vehicles, people movers (Alphard, Vellfire, Sienta, Noah, Voxy, Granace)
     * HATCHBACK: Compact cars with rear door/liftback (Yaris, Aqua)
     * SPORTS: Performance-oriented vehicles (GR86, GR Supra, GR Yaris)
     * VAN: Commercial or passenger vans (HiAce, Proace)
     * COMMERCIAL: Work vehicles, trucks, light commercial vehicles

2. VARIANTS:
   For each variant/trim level of a model:
   - variant_name: Full variant name (e.g., "1.6 STANDARD", "1.8 HYBRID", "2.5 PREMIUM HYBRID")
   - engine_size: Engine size if mentioned (e.g., "1.6", "2.0", "3.0L")
   - vehicle_type: Powertrain type for THIS SPECIFIC VARIANT:
     * "ICE" for gasoline/diesel engines (e.g., "1.6 STANDARD", "2.0 TURBO")
     * "Hybrid" for hybrid variants (e.g., "1.8 HYBRID", "2.5 PREMIUM HYBRID")
     * "Electric" for fully electric vehicles (e.g., "bZ4X", "eT3")
   - list_price: The base list price WITHOUT COE (often labeled as "LIST PRICE W/O COE")
   - final_price: The final/guaranteed COE price (often labeled as "CLASSIC PRICE (W/O F&I REBATE)" or "CLASSIC PRICE (NON-GUARANTEED COE)" or similar)

CRITICAL EXTRACTION RULES:

1. MODEL GROUPING:
   - A model like "COROLLA ALTIS" should appear ONCE with ALL its variants
   - Example: COROLLA ALTIS has "1.6 STANDARD" (ICE) and "1.8 HYBRID" (Hybrid) variants
   - DO NOT create separate "COROLLA ALTIS" entries for ICE and Hybrid
   - Group by model_name, NOT by powertrain type

2. CATEGORY CLASSIFICATION:
   - Harrier → SUV (not sedan, not commercial)
   - Alphard → MPV (not sports, not sedan)
   - Vellfire → MPV (not sports)
   - Yaris Cross → SUV (not hatchback)
   - Corolla Cross → SUV (not sedan)
   - When uncertain, consider: body style, seating position, ground clearance, and intended use

3. VEHICLE TYPE (POWERTRAIN):
   - Determine powertrain for EACH VARIANT individually
   - Look for keywords: "HYBRID", "ELECTRIC", "EV", "PLUG-IN"
   - If no keyword, assume "ICE" (conventional gasoline/diesel)
   - DO NOT put vehicle_type at model level - it belongs to each variant

4. PRICE EXTRACTION:
   - Extract BOTH list_price and final_price if available
   - list_price is typically the higher base price (left column)
   - final_price is typically the lower guaranteed COE price (right column, often labeled as "CLASSIC PRICE")
   - Extract numbers only, no currency symbols or commas
   - If only one price is available, put it in list_price and set final_price to null

5. QUALITY ASSURANCE:
   - Extract EVERY model and variant mentioned
   - If a field is not present, set it to null
   - Set extraction_confidence to "high", "medium", or "low" based on data clarity
   - Add any extraction issues to extraction_notes
   - Check for duplicate models before finalizing

Extract the data now from the provided PDF."""

    def extract_from_pdf(
        self,
        pdf_path: Path,
        model: str = "gemini-2.0-flash-exp",
        temperature: float = 0.1,
    ) -> SGCarMartPriceListExtraction:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        print(f"Encoding PDF: {pdf_path.name}...")
        pdf_base64 = self.encode_pdf(pdf_path)

        print("Extracting metadata from file path...")
        metadata_dict = self.extract_metadata_from_path(pdf_path)

        print(f"Calling Gemini API (model: {model})...")
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.create_extraction_prompt(),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:application/pdf;base64,{pdf_base64}"
                                },
                            },
                        ],
                    }
                ],
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "pricelist_extraction",
                        "schema": SGCarMartPriceListExtraction.model_json_schema(),
                    },
                },
            )

            print("Parsing response...")
            response_content = response.choices[0].message.content
            if not response_content:
                raise ValueError("Empty response from API")
            extraction_data = json.loads(response_content)

            usage = response.usage
            if not usage:
                raise ValueError("No usage data in API response")
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens

            print(f"Calculating API costs...")
            api_usage = self.calculate_cost(model, input_tokens, output_tokens)

            metadata_dict["api_usage"] = api_usage.model_dump()
            extraction_data["metadata"] = metadata_dict

            print("Validating against schema...")
            extraction = SGCarMartPriceListExtraction(**extraction_data)

            print(f"✓ Extraction successful! Confidence: {extraction.extraction_confidence}")
            print(f"✓ Extracted {len(extraction.pricelist.models)} model(s)")
            print(f"✓ Tokens: {api_usage.total_tokens:,} (in: {api_usage.input_tokens:,}, out: {api_usage.output_tokens:,})")
            if api_usage.is_free_tier:
                print(f"✓ Cost: FREE (using {model} free tier)")
            else:
                print(f"✓ Cost: ${api_usage.total_cost_usd:.6f} USD")

            return extraction

        except ValidationError as e:
            print(f"✗ Validation error: {e}")
            raise
        except Exception as e:
            print(f"✗ Extraction error: {e}")
            raise

    def save_extraction(
        self,
        extraction: SGCarMartPriceListExtraction,
        output_dir: Optional[Path] = None,
        format: str = "json"
    ) -> Path:
        if output_dir is None:
            output_dir = Path("data/pricelists") / extraction.metadata.brand_folder / str(extraction.metadata.year_folder)
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        base_filename = f"{extraction.metadata.brand_folder}_{extraction.metadata.dealer_id}_{extraction.metadata.pdf_date}"

        if format == "json":
            output_path = output_dir / f"{base_filename}.json"
            with open(output_path, "w") as f:
                json.dump(
                    extraction.model_dump(mode="json"),
                    f,
                    indent=2,
                    default=str
                )
        else:
            raise ValueError(f"Unsupported format: {format}")

        print(f"✓ Saved extraction to: {output_path}")
        return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract structured data from car dealer PDFs")
    parser.add_argument("pdf_path", type=str, help="Path to PDF file")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for extracted JSON (default: same directory as PDF)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.0-flash-exp",
        help="Gemini model to use"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Gemini API key (or set GEMINI_API_KEY env var)"
    )

    args = parser.parse_args()

    extractor = GeminiPDFExtractor(api_key=args.api_key)

    try:
        extraction = extractor.extract_from_pdf(
            pdf_path=args.pdf_path,
            model=args.model
        )

        output_path = extractor.save_extraction(
            extraction=extraction,
            output_dir=args.output_dir
        )

        print(f"\n{'='*60}")
        print("EXTRACTION SUMMARY")
        print(f"{'='*60}")
        print(f"Brand: {extraction.metadata.brand_folder}")
        print(f"Dealer ID: {extraction.metadata.dealer_id}")
        print(f"PDF Date: {extraction.metadata.pdf_date}")
        print(f"Models Extracted: {len(extraction.pricelist.models)}")
        print(f"Confidence: {extraction.extraction_confidence}")

        if extraction.metadata.api_usage:
            api = extraction.metadata.api_usage
            print(f"\nAPI Usage:")
            print(f"  Model: {api.model_name}")
            print(f"  Tokens: {api.total_tokens:,} (in: {api.input_tokens:,}, out: {api.output_tokens:,})")
            if api.is_free_tier:
                print(f"  Cost: FREE")
            else:
                print(f"  Cost: ${api.total_cost_usd:.6f} USD")

        print(f"\nOutput: {output_path}")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n✗ Failed to extract: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
