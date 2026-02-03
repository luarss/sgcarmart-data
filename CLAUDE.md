# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python web scraper that downloads and archives car price list PDFs from SGCarMart for all dealers and brands. The project includes automatic PDF extraction using Gemini AI to convert pricelists into structured JSON data.

**Educational purposes only** - not for profit or commercial use.

## Development Commands

### Setup
```bash
# Install dependencies
uv sync

# Install with dev dependencies
uv sync --all-extras
# or
make sync
```

### Running the Scraper
```bash
# Download latest pricelists for all dealers
uv run main.py

# Test mode (only MG, Toyota, BMW)
uv run main.py --test

# Download historical pricelists for specific year(s)
uv run main.py --year 2024
uv run main.py --year 2023-2025

# Disable automatic extraction
uv run main.py --no-extract

# Use specific Gemini model for extraction
uv run main.py --extract-model gemini-2.0-flash

# Control parallel browser instances for historical downloads
uv run main.py --year 2024 --browser-workers 5
```

### PDF Extraction
```bash
# Extract existing PDFs (batch processing)
uv run python analysis/batch_extract.py --brands toyota bmw --year 2025

# Extract with specific model
uv run python analysis/batch_extract.py --brands toyota --year 2025 --model gemini-2.0-flash
```

### Code Quality
```bash
# Format and fix code
make format
# or
ruff format .
ruff check --fix .

# Check code without fixing
make check
# or
ruff check .
```

### Testing
```bash
# Run tests with coverage (target: 80%+)
uv run pytest

# Run specific test markers
uv run pytest -m unit
uv run pytest -m integration

# Run specific test file
uv run pytest tests/unit/test_scraper.py

# Run without coverage
uv run pytest --no-cov
```

## Architecture

### Module Structure

```
sgcarmart/               # Main package
├── core/               # Core scraping and downloading logic
│   ├── scraper.py      # Pricelist link extraction from HTML
│   ├── downloader.py   # PDF download with retry logic
│   └── year_navigator.py  # Historical PDF discovery using Playwright
└── utils/              # Shared utilities
    ├── http.py         # HTTP requests with rate limiting
    ├── file_utils.py   # File operations and path handling
    ├── validation.py   # PDF validation (magic bytes, size)
    └── pdf_checker.py  # PDF corruption detection

analysis/               # AI-powered extraction (separate from scraper)
├── pdf_extractor.py    # Gemini-based PDF text extraction
├── batch_extract.py    # Batch processing script
└── schema.py           # Pydantic models for structured data

constants.py            # Global configuration (URLs, timeouts, workers)
main.py                 # CLI entry point
```

### Key Components

**Scraping Pipeline:**
1. `scraper.py`: Scrapes SGCarMart HTML pages for pricelist links
2. `downloader.py`: Downloads PDFs with validation and retry logic
3. `year_navigator.py`: Uses Playwright to navigate year dropdowns for historical data

**Extraction Pipeline:**
1. `pdf_extractor.py`: Uses Gemini vision models to extract structured data from PDFs
2. `schema.py`: Defines Pydantic models for car models, variants, prices, and metadata
3. `batch_extract.py`: Processes multiple PDFs in parallel

### Data Flow

**Download Mode (main.py):**
```
load_dealer_brand_mapping()
  → scrape_pricelist_links(dealer_id, brand)
  → download_pdf(url, brand)
  → validate_pdf()
  → [optional] auto-extract via GeminiPDFExtractor
  → save to data/pricelists/{brand}/{year}/dealer_{id}_{date}.pdf
```

**Historical Mode (main.py --year):**
```
discover_historical_pdfs(dealer_id, brand, years) [uses Playwright]
  → extract date options from dropdown
  → construct PDF URLs
  → download_pdf() for each URL
  → [optional] auto-extract
```

**Extraction Mode (batch_extract.py):**
```
find PDFs in data/pricelists/{brand}/{year}/
  → GeminiPDFExtractor.extract_from_pdf()
  → parse with Pydantic schema
  → save as {brand}_{dealer_id}_{date}.json
  → track API usage and costs
```

### Configuration

**constants.py** - All scraper configuration in one place:
- `BASE_URL`, `PRICELIST_URL_TEMPLATE`, `PDF_URL_TEMPLATE`
- Concurrency: `DEFAULT_MAX_WORKERS=10`, `DEFAULT_BROWSER_MAX_WORKERS=5`
- Validation: `MIN_PDF_SIZE_BYTES=1000`, `PDF_MAGIC_HEADER=b"%PDF"`
- Retry logic: `MAX_RETRIES=3`, `INITIAL_RETRY_DELAY=5`
- `EXCLUDED_BRANDS`: Premium brands excluded from scraping

**data/dealer_brand_mapping.json** - Maps dealer IDs to brand names (e.g., `"4": "bmw"`)

### Environment Variables

Set in `analysis/.env`:
- `GEMINI_API_KEY`: Required for automatic PDF extraction (optional for downloads only)

GitHub Actions uses `GEMINI_API_KEY` secret for automated daily downloads.

### Output Structure

```
data/
├── dealer_brand_mapping.json              # Dealer-to-brand lookup
├── download_report_{timestamp}.json       # Download results per run
└── pricelists/
    └── {brand}/                           # e.g., toyota/
        └── {year}/                        # e.g., 2025/
            ├── dealer_{id}_{date}.pdf     # Raw PDF
            └── {brand}_{id}_{date}.json   # Extracted structured data
```

### Extraction Schema

See `analysis/schema.py` for complete Pydantic models:

**PriceListDocument:**
- Contains list of `CarModel` objects

**CarModel:**
- `brand`, `model_name`, `category` (sedan/SUV/etc)
- `variants`: List of trim levels

**Variant:**
- `variant_name`, `engine_size`, `vehicle_type` (ICE/Hybrid/Electric)
- `list_price`, `final_price`

**ExtractionMetadata:**
- Tracks source filename, dates, dealer/brand info
- `api_usage`: Token counts and cost tracking for Gemini API

### Testing Strategy

**Unit tests** (`tests/unit/`):
- Test individual functions with mocked dependencies
- HTTP utilities, file operations, validation logic

**Integration tests** (`tests/integration/`):
- Test full workflows (scraping, downloading, extraction)
- Use Playwright for browser automation tests
- Mock external HTTP calls with `responses` library

Coverage target: 80%+ (enforced by pytest config)

### GitHub Actions Workflow

`.github/workflows/download-pricelists.yml`:
- **Schedule**: Runs daily at 2:00 AM UTC (10:00 AM SGT)
- **Process**: Download latest pricelists → auto-extract → commit to repo
- **Artifacts**: PDFs and JSON files committed with message `chore: update pricelists YYYY-MM-DD`

## Important Implementation Notes

### Concurrency

- **Latest mode**: Uses `ThreadPoolExecutor` with `DEFAULT_MAX_WORKERS=10` for parallel HTTP downloads
- **Historical mode**: Uses `DEFAULT_BROWSER_MAX_WORKERS=5` for parallel Playwright browser instances (more resource-intensive)
- PDF extraction can be enabled/disabled via `--no-extract` flag

### Robots.txt Compliance

All scraping respects SGCarMart's robots.txt. Tests verify compliance (`test_robots_compliance.py`).

### Rate Limiting

`http.py` implements retry logic with exponential backoff for failed requests. Raises `RateLimitError` when rate limited.

### PDF Validation

Two-stage validation:
1. **Basic**: Magic bytes (`%PDF`) and minimum size check
2. **Corruption**: Uses pypdf to detect malformed PDFs (`pdf_checker.py`)

### File Naming Convention

All files follow pattern: `{brand}_{dealer_id}_{date}.{ext}`
- PDFs: `dealer_44_2025-01-15.pdf`
- JSON: `toyota_44_2025-01-15.json`

### Brand Name Normalization

`normalize_brand_name()` converts brand names to lowercase with hyphens (e.g., "Mercedes-Benz" → "mercedes-benz") for consistent directory/file naming.
