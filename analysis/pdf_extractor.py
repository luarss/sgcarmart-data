import base64
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from analysis.schema import APIUsageStats, SGCarMartPriceListExtraction

load_dotenv(Path(__file__).parent / ".env")


def _is_transient_api_error(error_str: str) -> bool:
    quota_error = "429" in error_str and ("quota" in error_str.lower() or "RESOURCE_EXHAUSTED" in error_str)
    unavailable_error = "503" in error_str and "UNAVAILABLE" in error_str
    return quota_error or unavailable_error


def _extract_metadata_from_path(pdf_path: Path) -> dict:
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


def _create_extraction_prompt() -> str:
    return """You are an expert data extraction assistant specialized in extracting car pricing \
information from Singapore dealer price lists.

Extract the following information from this PDF pricelist:

1. CAR MODELS:
   CRITICAL: Group ALL variants under a SINGLE model entry, regardless of powertrain type.
   DO NOT create duplicate model entries for different powertrains.

   For each car model in the pricelist, extract:
   - brand: Brand name (e.g., "Toyota", "BMW", "Mercedes-Benz")
   - model_name: Model name (e.g., "COROLLA ALTIS", "YARIS CROSS", "HARRIER")
   - category: Vehicle category - use these guidelines:
     * SEDAN: Traditional 4-door passenger cars with separate trunk (Corolla Altis, Camry, Crown)
     * SUV: Sport Utility Vehicles with higher ground clearance (Harrier, RAV4, Corolla Cross, \
Yaris Cross, Fortuner, Land Cruiser)
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
   - final_price: The final/guaranteed COE price (often labeled as "CLASSIC PRICE (W/O F&I REBATE)" \
or "CLASSIC PRICE (NON-GUARANTEED COE)" or similar)

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


def save_extraction(
    extraction: SGCarMartPriceListExtraction, output_dir: Path | None = None, format: str = "json"
) -> Path:
    if output_dir is None:
        brand_folder = extraction.metadata.brand_folder
        year_folder = str(extraction.metadata.year_folder)
        output_dir = Path("data/pricelists") / brand_folder / year_folder
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    brand_folder = extraction.metadata.brand_folder
    dealer_id = extraction.metadata.dealer_id
    pdf_date = extraction.metadata.pdf_date
    base_filename = f"{brand_folder}_{dealer_id}_{pdf_date}"

    if format == "json":
        output_path = output_dir / f"{base_filename}.json"
        with open(output_path, "w") as f:
            json.dump(extraction.model_dump(mode="json"), f, indent=2, default=str)
    else:
        raise ValueError(f"Unsupported format: {format}")

    print(f"✓ Saved extraction to: {output_path}")
    return output_path


class GeminiPDFExtractor:
    DEFAULT_MODEL: ClassVar[str] = "gemini-3.5-flash"
    FALLBACK_MODEL: ClassVar[str] = "gemini-2.5-flash-lite"

    PRICING: ClassVar = {
        "gemini-3.5-flash": {"input_per_million": 1.50, "output_per_million": 9.00, "is_free": False},
        "gemini-3-flash": {"input_per_million": 0.50, "output_per_million": 3.00, "is_free": False},
        "gemini-3-pro": {"input_per_million": 2.00, "output_per_million": 12.00, "is_free": False},
        "gemini-2.5-pro": {"input_per_million": 1.25, "output_per_million": 10.00, "is_free": False},
        "gemini-2.5-flash": {"input_per_million": 0.15, "output_per_million": 0.60, "is_free": False},
        "gemini-2.5-flash-lite": {"input_per_million": 0.10, "output_per_million": 0.40, "is_free": False},
        "gemini-2.0-flash": {"input_per_million": 0.10, "output_per_million": 0.40, "is_free": False},
        "gemini-2.0-flash-lite": {"input_per_million": 0.05, "output_per_million": 0.20, "is_free": False},
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or constructor")

        self.client = OpenAI(api_key=self.api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> APIUsageStats:
        pricing = self.PRICING.get(model, self.PRICING[self.DEFAULT_MODEL])

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
            is_free_tier=pricing.get("is_free", False),
        )

    def encode_pdf(self, pdf_path: Path) -> str:
        with open(pdf_path, "rb") as pdf_file:
            return base64.standard_b64encode(pdf_file.read()).decode("utf-8")

    def extract_metadata_from_path(self, pdf_path: Path) -> dict:
        return _extract_metadata_from_path(pdf_path)

    def create_extraction_prompt(self) -> str:
        return _create_extraction_prompt()

    def _call_api(self, model: str, pdf_base64: str, temperature: float) -> object:
        return self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _create_extraction_prompt()},
                        {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}},
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

    def extract_from_pdf(
        self,
        pdf_path: Path,
        model: str | None = None,
        temperature: float = 0.1,
        fallback_model: str | None = None,
    ) -> SGCarMartPriceListExtraction:
        if model is None:
            model = self.DEFAULT_MODEL
        if fallback_model is None:
            fallback_model = self.FALLBACK_MODEL
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        print(f"Encoding PDF: {pdf_path.name}...")
        pdf_base64 = self.encode_pdf(pdf_path)

        print("Extracting metadata from file path...")
        metadata_dict = _extract_metadata_from_path(pdf_path)

        current_model = model
        print(f"Calling Gemini API (model: {current_model})...")
        try:
            response = self._call_api(current_model, pdf_base64, temperature)
        except Exception as e:
            error_str = str(e)
            if _is_transient_api_error(error_str) and fallback_model != current_model:
                print(f"⚠ Gemini {current_model} unavailable: {error_str[:120]}")
                print(f"↻ Switching to fallback model: {fallback_model}")
                current_model = fallback_model
                response = self._call_api(current_model, pdf_base64, temperature)
            else:
                raise

        try:
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

            print("Calculating API costs...")
            api_usage = self.calculate_cost(current_model, input_tokens, output_tokens)

            metadata_dict["api_usage"] = api_usage.model_dump()
            extraction_data["metadata"] = metadata_dict

            print("Validating against schema...")
            extraction = SGCarMartPriceListExtraction(**extraction_data)

            print(f"✓ Extraction successful! Confidence: {extraction.extraction_confidence}")
            print(f"✓ Extracted {len(extraction.pricelist.models)} model(s)")
            print(
                f"✓ Tokens: {api_usage.total_tokens:,} "
                f"(in: {api_usage.input_tokens:,}, out: {api_usage.output_tokens:,})"
            )
            if api_usage.is_free_tier:
                print(f"✓ Cost: FREE (using {current_model} free tier)")
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
        self, extraction: SGCarMartPriceListExtraction, output_dir: Path | None = None, format: str = "json"
    ) -> Path:
        return save_extraction(extraction, output_dir, format)


class DeepSeekPDFExtractor:
    DEFAULT_MODEL: ClassVar[str] = "deepseek-v4-flash"
    BASE_URL: ClassVar[str] = "https://api.deepseek.com"

    PRICING: ClassVar = {
        "deepseek-v4-flash": {"input_per_million": 0.07, "output_per_million": 0.28, "is_free": False},
        "deepseek-chat": {"input_per_million": 0.27, "output_per_million": 1.10, "is_free": False},
        "deepseek-reasoner": {"input_per_million": 0.55, "output_per_million": 2.19, "is_free": False},
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment or constructor")
        self.client = OpenAI(api_key=self.api_key, base_url=self.BASE_URL)

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> APIUsageStats:
        pricing = self.PRICING.get(model, self.PRICING[self.DEFAULT_MODEL])
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
            is_free_tier=pricing.get("is_free", False),
        )

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        import re

        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p for p in pages if p.strip())

        # Detect custom-font PDFs where pypdf emits glyph IDs (/0 /1 /2...) instead of text.
        # These require vision-based extraction (Gemini) and cannot be decoded as plain text.
        tokens = text.split()
        if tokens:
            glyph_refs = sum(1 for t in tokens if re.fullmatch(r"/\d+", t))
            if glyph_refs / len(tokens) > 0.4:
                raise ValueError(
                    f"PDF uses custom font encoding — pypdf extracted glyph IDs only "
                    f"({glyph_refs}/{len(tokens)} tokens are glyph refs). "
                    "Requires vision-based extraction (Gemini), cannot use text-only fallback."
                )

        # Detect image-based PDFs that only contain a wrapper/template (e.g. TCPDF shell).
        # Real pricelists have dozens of model names, prices, and numbers; a sub-300 char
        # extraction means the actual content is embedded as images, not selectable text.
        if len(text.strip()) < 300:
            raise ValueError(
                f"PDF appears image-based — only {len(text.strip())} chars of text extracted "
                f"({text.strip()!r:.80}). Requires vision-based extraction (Gemini)."
            )

        return text

    def extract_from_pdf(
        self, pdf_path: Path, model: str | None = None, temperature: float = 0.1
    ) -> SGCarMartPriceListExtraction:
        if model is None:
            model = self.DEFAULT_MODEL
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        print(f"Extracting text from PDF (DeepSeek fallback): {pdf_path.name}...")
        pdf_text = self.extract_text_from_pdf(pdf_path)
        if not pdf_text.strip():
            raise ValueError(f"No extractable text in {pdf_path.name} (may be image-based PDF)")

        metadata_dict = _extract_metadata_from_path(pdf_path)

        schema = SGCarMartPriceListExtraction.model_json_schema()
        pricelist_schema = json.dumps(
            {k: schema[k] for k in ("properties", "required", "$defs") if k in schema}, indent=2
        )

        prompt = f"""{_create_extraction_prompt()}

Output ONLY valid JSON with these top-level fields: "pricelist" (with "models" array), \
"extraction_confidence" ("high"/"medium"/"low"), and optionally "extraction_notes" (array of strings).
Do NOT include "metadata" — it will be added separately.

Schema reference:
{pricelist_schema}

PDF TEXT:
{pdf_text}"""

        print(f"Calling DeepSeek API (model: {model})...")
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
        )

        response_content = response.choices[0].message.content
        if not response_content:
            raise ValueError("Empty response from DeepSeek API")

        extraction_data = json.loads(response_content)

        usage = response.usage
        if not usage:
            raise ValueError("No usage data in DeepSeek response")

        api_usage = self.calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
        metadata_dict["api_usage"] = api_usage.model_dump()
        extraction_data["metadata"] = metadata_dict

        try:
            extraction = SGCarMartPriceListExtraction(**extraction_data)
        except ValidationError as e:
            print(f"✗ DeepSeek validation error: {e}")
            raise

        print(f"✓ DeepSeek extraction successful! Confidence: {extraction.extraction_confidence}")
        print(f"✓ Extracted {len(extraction.pricelist.models)} model(s)")
        print(
            f"✓ Tokens: {api_usage.total_tokens:,} "
            f"(in: {api_usage.input_tokens:,}, out: {api_usage.output_tokens:,})"
        )
        print(f"✓ Cost: ${api_usage.total_cost_usd:.6f} USD")

        return extraction

    def save_extraction(
        self, extraction: SGCarMartPriceListExtraction, output_dir: Path | None = None, format: str = "json"
    ) -> Path:
        return save_extraction(extraction, output_dir, format)


class MimoPDFExtractor:
    DEFAULT_MODEL: ClassVar[str] = "mimo-v2.5"
    BASE_URL: ClassVar[str] = "https://api.xiaomimimo.com/v1"
    DPI: ClassVar[int] = 150
    MAX_TOKENS: ClassVar[int] = 8000

    # https://mimo.mi.com/docs/en-US/price/pay-as-you-go (overseas pricing, updated 2026-05-27)
    PRICING: ClassVar = {
        "mimo-v2.5": {"input_per_million": 0.14, "output_per_million": 0.28, "is_free": False},
        "mimo-v2.5-pro": {"input_per_million": 0.435, "output_per_million": 0.87, "is_free": False},
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("XIAOMI_API_KEY")
        if not self.api_key:
            raise ValueError("XIAOMI_API_KEY not found in environment or constructor")
        self.client = OpenAI(api_key=self.api_key, base_url=self.BASE_URL)

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> APIUsageStats:
        pricing = self.PRICING.get(model, self.PRICING[self.DEFAULT_MODEL])
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
            is_free_tier=pricing.get("is_free", False),
        )

    def render_pages(self, pdf_path: Path) -> list[str]:
        import fitz

        doc = fitz.open(str(pdf_path))
        return [
            base64.standard_b64encode(page.get_pixmap(dpi=self.DPI).tobytes("png")).decode()
            for page in doc
        ]

    def extract_from_pdf(
        self, pdf_path: Path, model: str | None = None, temperature: float = 0.1
    ) -> SGCarMartPriceListExtraction:
        if model is None:
            model = self.DEFAULT_MODEL
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        print(f"Rendering PDF pages to images (Mimo fallback): {pdf_path.name}...")
        images = self.render_pages(pdf_path)
        print(f"Rendered {len(images)} page(s)")

        metadata_dict = _extract_metadata_from_path(pdf_path)

        schema = SGCarMartPriceListExtraction.model_json_schema()
        pricelist_schema = json.dumps(
            {k: schema[k] for k in ("properties", "required", "$defs") if k in schema}, indent=2
        )

        content = [
            {
                "type": "text",
                "text": f"""{_create_extraction_prompt()}

Output ONLY valid JSON with these top-level fields: "pricelist" (with "models" array), \
"extraction_confidence" ("high"/"medium"/"low"), and optionally "extraction_notes" (array of strings).
Do NOT include "metadata" — it will be added separately.

Schema reference:
{pricelist_schema}""",
            }
        ]
        for img_b64 in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}})

        print(f"Calling Mimo API (model: {model})...")
        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=self.MAX_TOKENS,
            temperature=temperature,
        )

        response_content = response.choices[0].message.content
        if not response_content:
            raise ValueError("Empty response from Mimo API (reasoning may have exhausted max_tokens)")

        extraction_data = json.loads(response_content)

        usage = response.usage
        if not usage:
            raise ValueError("No usage data in Mimo response")

        api_usage = self.calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
        metadata_dict["api_usage"] = api_usage.model_dump()
        extraction_data["metadata"] = metadata_dict

        try:
            extraction = SGCarMartPriceListExtraction(**extraction_data)
        except ValidationError as e:
            print(f"✗ Mimo validation error: {e}")
            raise

        reasoning_tokens = (usage.completion_tokens_details.reasoning_tokens or 0) if usage.completion_tokens_details else 0
        print(f"✓ Mimo extraction successful! Confidence: {extraction.extraction_confidence}")
        print(f"✓ Extracted {len(extraction.pricelist.models)} model(s)")
        print(
            f"✓ Tokens: {api_usage.total_tokens:,} "
            f"(in: {api_usage.input_tokens:,}, out: {api_usage.output_tokens:,}, reasoning: {reasoning_tokens:,})"
        )
        print(f"✓ Cost: ${api_usage.total_cost_usd:.6f} USD")

        return extraction

    def save_extraction(
        self, extraction: SGCarMartPriceListExtraction, output_dir: Path | None = None, format: str = "json"
    ) -> Path:
        return save_extraction(extraction, output_dir, format)


def extract_pdf_with_fallback(
    pdf_path: Path,
    model: str | None = None,
    temperature: float = 0.1,
) -> SGCarMartPriceListExtraction:
    """Try Gemini first; fall back to DeepSeek (text) then Mimo (vision) on failure."""
    pdf_path = Path(pdf_path)
    gemini_key = os.getenv("GEMINI_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    xiaomi_key = os.getenv("XIAOMI_API_KEY")

    if not gemini_key and not deepseek_key and not xiaomi_key:
        raise RuntimeError("No API keys available — set GEMINI_API_KEY, DEEPSEEK_API_KEY, or XIAOMI_API_KEY")

    if gemini_key:
        try:
            extractor = GeminiPDFExtractor(api_key=gemini_key)
            return extractor.extract_from_pdf(pdf_path, model=model, temperature=temperature)
        except Exception as e:
            print(f"⚠ Gemini failed: {e}")

    # DeepSeek: fast, cheap, text-only. Raises ValueError for image-based/garbled PDFs.
    if deepseek_key:
        try:
            extractor = DeepSeekPDFExtractor(api_key=deepseek_key)
            return extractor.extract_from_pdf(pdf_path, temperature=temperature)
        except ValueError as e:
            print(f"⚠ DeepSeek text extraction not viable: {e}")
            print("↻ Falling back to Mimo (vision)...")
        except Exception as e:
            print(f"⚠ DeepSeek failed: {e}")
            print("↻ Falling back to Mimo (vision)...")

    if xiaomi_key:
        extractor = MimoPDFExtractor(api_key=xiaomi_key)
        return extractor.extract_from_pdf(pdf_path, temperature=temperature)

    raise RuntimeError("All extractors exhausted — no API keys available for remaining fallbacks")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract structured data from car dealer PDFs")
    parser.add_argument("pdf_path", type=str, help="Path to PDF file")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for extracted JSON (default: data/pricelists/<brand>/<year>)",
    )
    parser.add_argument("--model", type=str, default=GeminiPDFExtractor.DEFAULT_MODEL, help="Gemini model to use")
    parser.add_argument("--api-key", type=str, help="Gemini API key (or set GEMINI_API_KEY env var)")

    args = parser.parse_args()

    extractor = GeminiPDFExtractor(api_key=args.api_key)

    try:
        extraction = extractor.extract_from_pdf(pdf_path=args.pdf_path, model=args.model)

        output_path = extractor.save_extraction(extraction=extraction, output_dir=args.output_dir)

        print(f"\n{'=' * 60}")
        print("EXTRACTION SUMMARY")
        print(f"{'=' * 60}")
        print(f"Brand: {extraction.metadata.brand_folder}")
        print(f"Dealer ID: {extraction.metadata.dealer_id}")
        print(f"PDF Date: {extraction.metadata.pdf_date}")
        print(f"Models Extracted: {len(extraction.pricelist.models)}")
        print(f"Confidence: {extraction.extraction_confidence}")

        if extraction.metadata.api_usage:
            api = extraction.metadata.api_usage
            print("\nAPI Usage:")
            print(f"  Model: {api.model_name}")
            print(f"  Tokens: {api.total_tokens:,} (in: {api.input_tokens:,}, out: {api.output_tokens:,})")
            if api.is_free_tier:
                print("  Cost: FREE")
            else:
                print(f"  Cost: ${api.total_cost_usd:.6f} USD")

        print(f"\nOutput: {output_path}")
        print(f"{'=' * 60}\n")

    except Exception as e:
        print(f"\n✗ Failed to extract: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
