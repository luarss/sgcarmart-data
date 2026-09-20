# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python data archive for the Singapore car market. Four independent pipelines scrape and
commit data on a schedule, plus an Observable Framework site that publishes a value watchlist:

1. **New car pricelists** — downloads dealer pricelist PDFs from SGCarMart and extracts them
   into structured JSON with LLM vision/text models.
2. **Used car listings** — daily snapshot and diff of SGCarMart used car listings for a
   configured filter set, then scored into a ranked value watchlist.
3. **CPO listings** — certified pre-owned inventory scraped from ~8 Singapore dealer sites.
4. **COE bidding results** — Certificate of Entitlement premiums from data.gov.sg.

All outputs are JSON committed into `data/`, so the repo doubles as the time series.

**Educational purposes only** - not for profit or commercial use.

## Development Commands

### Setup
```bash
# Install runtime dependencies
uv sync

# Install with dev + all optional extras (adds boto3 for R2 archival)
uv sync --all-extras
# or
make sync

# Playwright browsers (needed for CPO, historical pricelists, used-car fallback)
uv run playwright install chromium
```

### New Car Pricelists
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

# Use a specific extraction model
uv run main.py --extract-model gemini-3.5-flash

# Control parallel browser instances for historical downloads
uv run main.py --year 2024 --browser-workers 5
```

Note: `--extract-only` is declared but **not implemented** — it prints a message and returns.
Use `analysis/batch_extract.py` instead.

### PDF Extraction
```bash
# Extract existing PDFs (batch processing)
uv run python analysis/batch_extract.py --brands toyota bmw --year 2025

# Extract with specific model
uv run python analysis/batch_extract.py --brands toyota --year 2025 --model gemini-3.5-flash

# Extract a single PDF
uv run python analysis/pdf_extractor.py data/pricelists/toyota/2025/dealer_44_2025-01-15.pdf
```

### Used Cars
```bash
# Daily snapshot + diff against the previous snapshot
uv run python scripts/watch_used.py
uv run python scripts/watch_used.py --name sgd-passenger --json

# Rank the latest snapshot by composite value score
uv run python scripts/watchlist.py --name sgd-passenger
uv run python scripts/watchlist.py --top 50 --json
uv run python scripts/watchlist.py --date 2026-05-27   # backfill from a dated snapshot
```

### CPO Listings
```bash
uv run cpo_main.py                      # all sites
uv run cpo_main.py --site ic_preowned   # one site
uv run cpo_main.py --test               # ic_preowned, toyota, das_weltauto
uv run cpo_main.py --workers 2          # limit parallel browsers
uv run cpo_main.py --no-headless        # show browser windows (debugging)
```

### COE Results
```bash
uv run python scripts/download_coe.py
uv run python scripts/download_coe.py --dry-run
```

### Site (Observable Framework)
```bash
cd site
npm install
npm run dev     # observable preview
npm run build   # observable build
npm run clean
```

### Utility Scripts
```bash
# Detect corrupted PDFs
uv run python scripts/check_pdfs.py --directory data/pricelists

# Download every pricelist on a dealer page (not just the latest)
uv run python scripts/download_all_pdfs.py --brand toyota
uv run python scripts/download_all_pdfs.py --all

# Archive old PDFs to Cloudflare R2 (needs `uv sync --extra archive`)
uv run python scripts/archive_to_r2.py --dry-run
uv run python scripts/archive_to_r2.py --years 2021 2022 --delete

# List available Gemini model IDs
uv run python scripts/list_gemini_models.py
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

Ruff is configured with `line-length = 120`, `target-version = "py313"`, and
`extend-exclude = ["tests"]` — lint rules do not apply to the test suite.

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
├── constants.py        # Global configuration (URLs, timeouts, workers, COE/CPO paths)
├── core/               # Scrapers and downloaders
│   ├── scraper.py      # Pricelist link extraction from HTML
│   ├── downloader.py   # PDF download with retry, validation, manifest, auto-extract
│   ├── year_navigator.py  # Historical PDF discovery using Playwright
│   ├── used.py         # Used car scraper — HTTP/RSC primary, Playwright fallback
│   └── cpo.py          # Certified pre-owned scrapers for ~8 dealer sites
├── coe/                # COE bidding results from data.gov.sg
│   ├── client.py       # Paginated datastore_search fetch
│   ├── models.py       # COERecord pydantic model
│   └── __init__.py     # group_by_year(), save_coe_data()
└── utils/              # Shared utilities
    ├── http.py         # HTTP requests with retry / rate limiting
    ├── file_utils.py   # File operations and path handling
    ├── validation.py   # PDF validation (magic bytes, size)
    ├── pdf_checker.py  # PDF corruption detection
    └── manifest.py     # md5 manifest of downloaded PDFs (skip logic)

analysis/               # AI extraction + scoring (separate from scraping)
├── pdf_extractor.py    # Gemini / DeepSeek / Mimo extractors + fallback chain
├── batch_extract.py    # Batch processing script (Gemini only)
├── schema.py           # Pydantic models for structured pricelist data
├── value_scorer.py     # Weighted composite value scoring for used listings
└── *.ipynb             # Exploratory notebooks the scorer was derived from

scripts/                # Operational entry points
├── watch_used.py       # Daily used-car snapshot + diff
├── watchlist.py        # Value-ranked watchlist from the latest snapshot
├── download_coe.py     # COE results downloader
├── archive_to_r2.py    # Upload archived PDFs to Cloudflare R2
├── check_pdfs.py       # Corruption scan over stored PDFs
├── download_all_pdfs.py  # Download every pricelist on a dealer page
└── list_gemini_models.py

site/                   # Observable Framework site ("SGCM Value Watchlist")
├── observablehq.config.js
└── src/
    ├── index.md, history.md, detail.md, style.css
    └── data/           # Python data loaders (*.json.py) reading from data/

main.py                 # CLI entry point — new car pricelists
cpo_main.py             # CLI entry point — CPO listings
```

### Key Components

**New car pricelist pipeline:**
1. `scraper.py`: Scrapes SGCarMart HTML pages for pricelist links
2. `downloader.py`: Downloads PDFs with validation, manifest skip, and retry logic
3. `year_navigator.py`: Uses Playwright to navigate year dropdowns for historical data
4. `pdf_extractor.py`: Multi-provider extraction into the Pydantic schema

**Used car pipeline:**
1. `used.py`: Two independent scraping paths against the same listing URLs —
   `fetch_all_listings_http()` parses the Next.js RSC payload out of the server-rendered
   HTML (no browser), and `UsedCarSearch` drives Playwright + stealth as a fallback.
2. `watch_used.py`: Fetches, filters, diffs against the previous snapshot, writes both a
   dated snapshot and `latest.json`
3. `value_scorer.py`: COE-adjusted composite scoring
4. `watchlist.py`: Ranks and writes `watchlist.json`, which the site reads

**CPO pipeline:**
- `cpo.py` defines an abstract `CPOScraper` (Playwright + stealth + random UA) with one
  subclass per dealer site, registered in `ALL_SCRAPERS`. `ProgrammePageCPOScraper` covers
  sites that advertise a CPO programme but publish no inventory grid — these emit a single
  entry with `listing_type="programme_page"` instead of listings.

**COE pipeline:**
- `coe/client.py` walks data.gov.sg's paginated `datastore_search` API; `save_coe_data()`
  groups records by year into one file per year.

### Data Flow

**Download Mode (main.py):**
```
load_dealer_brand_mapping()
  → scrape_pricelist_links(dealer_id, brand)
  → download_pdf(url, brand)
  → manifest.is_known()? skip : validate_pdf() + manifest.record()
  → [optional] auto-extract via extract_pdf_with_fallback()
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

**Used Car Watch (scripts/watch_used.py):**
```
load data/used_cars/{name}/config.json (or DEFAULT_CONFIG)
  → fetch_all_listings_http(filters)         [HTTP/RSC path]
  → on failure/empty: UsedCarSearch Playwright fallback
  → retry whole fetch up to 3× (tenacity, 15s/30s waits)
  → 0 listings after all retries → raise DegenerateFetchError, write nothing
  → [optional] drop COE-renewed cars by title pattern
  → diff against latest.json (added / removed / price changes)
  → write data/used_cars/{name}/{date}.json + latest.json
```

**Value Watchlist (scripts/watchlist.py):**
```
load data/used_cars/{name}/latest.json
  → load_coe_lookup() from data/coe/coe_results_*.json
  → score_listings(): parse, exclude, derive 7 metrics, winsorize, min-max, weight
  → write data/used_cars/{name}/watchlist.json
```

**CPO Watch (cpo_main.py):**
```
run_all(sites) with ThreadPoolExecutor (1 browser per site, 1 retry each)
  → 0 listings across all sites → exit 1, write nothing
  → save_results(): write data/cpo/{date}.json
  → write data/cpo/latest.json unless 0 listings and a previous snapshot exists
  → exit 1 if any individual site errored
```

**COE (scripts/download_coe.py):**
```
fetch_coe_results() [paginated, 1s between pages]
  → group_by_year()
  → write data/coe/coe_results_{year}.json
```

### Configuration

**sgcarmart/constants.py** - All scraper configuration in one place:
- `BASE_URL`, `PRICELIST_URL_TEMPLATE`, `PDF_URL_TEMPLATE`
- Concurrency: `DEFAULT_MAX_WORKERS=10`, `DEFAULT_BROWSER_MAX_WORKERS=5`, `CPO_DEFAULT_MAX_WORKERS=3`
- Validation: `MIN_PDF_SIZE_BYTES=1000`, `PDF_MAGIC_HEADER=b"%PDF"`
- Retry logic: `MAX_RETRIES=3`, `INITIAL_RETRY_DELAY=5`
- Extraction: `DEFAULT_EXTRACT_MODEL="gemini-3.5-flash"`
- COE: `COE_RESOURCE_ID`, `COE_API_BASE_URL`, `COE_OUTPUT_DIR`
- CPO: `CPO_OUTPUT_DIR`
- `USER_AGENTS`: rotation pool used by the HTTP layer and CPO scrapers
- `EXCLUDED_BRANDS`: Premium brands excluded from scraping

**data/dealer_brand_mapping.json** - Maps dealer IDs to brand names (e.g., `"4": "bmw"`)

**data/used_cars/{name}/config.json** - Per-watch filters. Written back by `watch_used.py`
on every run, so edits persist but must use keys from `SEARCH_PARAMS` in
`sgcarmart/core/used.py` — unknown keys raise. The defaults live in `DEFAULT_CONFIG`
in `scripts/watch_used.py`.

### Environment Variables

There are **two** dotenv locations and they are not interchangeable:

- `analysis/.env` — loaded by `main.py`, `analysis/pdf_extractor.py`,
  `analysis/batch_extract.py`, `scripts/archive_to_r2.py`, `scripts/list_gemini_models.py`
- `./.env` (project root) — loaded **only** by `scripts/download_coe.py`

| Variable | Required | Read from | Purpose |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | For extraction | `analysis/.env` | Primary extractor. Also gates auto-extraction in `main.py`. |
| `DEEPSEEK_API_KEY` | Optional | `analysis/.env` | Fallback 1 — text-only extraction. |
| `XIAOMI_API_KEY` | Optional | `analysis/.env` | Fallback 2 — Mimo vision extraction. |
| `DATA_GOV_API_KEY` | Optional | root `.env` | Raises data.gov.sg rate limits (`x-api-key` header). |
| `R2_ACCOUNT_ID` | For R2 upload | `analysis/.env` | Cloudflare R2 endpoint. |
| `R2_ACCESS_KEY_ID` | For R2 upload | `analysis/.env` | Cloudflare R2 credentials. |
| `R2_SECRET_ACCESS_KEY` | For R2 upload | `analysis/.env` | Cloudflare R2 credentials. |
| `R2_BUCKET_NAME` | For R2 upload | `analysis/.env` | Target bucket. |
| `PROXY_SERVER` | Optional | real env only | Single proxy for the Playwright used-car path. |
| `PROXY_FALLBACKS` | Optional | real env only | Comma-separated proxy rotation list, capped at 10. |

`PROXY_SERVER` / `PROXY_FALLBACKS` are read via `os.environ` at **import time** in
`sgcarmart/core/used.py`, and nothing calls `load_dotenv()` on that path — putting them
in a `.env` file has no effect. Export them, or let the workflow set them.

See `analysis/.env.example` for the annotated template.

GitHub Actions secrets in use: `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `XIAOMI_API_KEY`
(pricelists) and `DATA_GOV_API_KEY` (COE). The used-car workflow builds `PROXY_FALLBACKS`
at runtime from proxyscrape.com rather than from a secret.

### Output Structure

```
data/
├── dealer_brand_mapping.json              # Dealer-to-brand lookup
├── download_report_{timestamp}.json       # Download results per run
├── pricelists/
│   ├── manifest.json                      # rel_path → md5 of downloaded PDFs
│   └── {brand}/{year}/
│       ├── dealer_{id}_{date}.pdf         # Raw PDF
│       └── {brand}_{id}_{date}.json       # Extracted structured data
├── used_cars/
│   └── {watch_name}/                      # e.g. sgd-passenger/
│       ├── config.json                    # Filters for this watch
│       ├── {date}.json                    # Daily snapshot (date, filters, listings)
│       ├── latest.json                    # Most recent listings, keyed by listing ID
│       └── watchlist.json                 # Value-ranked output for the site
├── cpo/
│   ├── {date}.json                        # Daily snapshot + per-site status
│   └── latest.json
└── coe/
    └── coe_results_{year}.json            # One file per year
```

### Extraction Schema

See `analysis/schema.py` for complete Pydantic models:

**SGCarMartPriceListExtraction** (top level):
- `metadata`, `pricelist`, `extraction_confidence` (high/medium/low), `extraction_notes`

**PriceListDocument:**
- Contains list of `CarModel` objects

**CarModel:**
- `brand`, `model_name`, `category` (`VehicleCategory` enum: SEDAN/SUV/MPV/...)
- `variants`: List of trim levels

**Variant:**
- `variant_name`, `engine_size`, `vehicle_type` (`VehicleType` enum: ICE/Hybrid/Electric)
- `list_price` (without COE), `final_price` (after rebates/promotions)

**ExtractionMetadata:**
- Tracks source filename, dates, dealer/brand info
- `api_usage`: `APIUsageStats` — token counts and cost tracking

### Value Scoring

`analysis/value_scorer.py` produces a composite 0–1 score per used listing.

- **Weights** live in `DEFAULT_WEIGHTS` and must sum to 1.0. Currently:
  `body_depreciation_rate` 0.30, `body_price_per_coe_year` 0.25, `depreciation_per_km` 0.18,
  `annual_mileage` 0.12, `days_on_market` 0.10, `price_per_owner` 0.05.
  `depreciation_rate` is weighted 0.00 — deliberately retained at zero because it correlates
  r=0.990 with `body_depreciation_rate` and double-counted depreciation.
- **COE adjustment**: `load_coe_lookup()` reads `data/coe/coe_results_*.json` to get the
  latest premium per category, so "body value" can be separated from the COE sunk cost.
  Category is assigned by engine capacity (≤1600cc → Category A, else Category B).
- **Exclusions**: niche/retro brands, classic model names, OPC (off-peak) cars, and diesels —
  each incomparable on these metrics. Counts are returned in the `stats` dict.
- **Normalization**: values are winsorized at the 2nd/98th percentile before min-max
  normalization so one outlier can't compress the rest of the distribution.

Entry points: `score_listings(listings, coe_lookup, reference_date)` and the convenience
`load_and_score(project_root, watch_name, reference_date)`.

### Testing Strategy

**Unit tests** (`tests/unit/`):
- Test individual functions with mocked dependencies
- HTTP utilities, file operations, validation logic, used-car parsing

**Integration tests** (`tests/integration/`):
- Test full workflows (scraping, downloading, extraction)
- Playwright is mocked, not driven — no real browser is launched
- Mock external HTTP calls with `responses` library

Coverage target: 80%+ (enforced by pytest config, `--cov=sgcarmart` only).
Note that `analysis/` and `scripts/` are not in the coverage scope.

### GitHub Actions Workflows

Five workflows, all committing results back to `main` via `git-auto-commit-action`.
All action versions are pinned to commit SHAs.

| Workflow | Schedule (UTC) | Runs | Commits |
| --- | --- | --- | --- |
| `download-pricelists.yml` | `13 20 * * *` daily | `main.py` (also a test job on push to main) | `data/pricelists/**` + `manifest.json` |
| `watch-cpo.yml` | `13 21 * * *` daily | `cpo_main.py` | `data/cpo/*.json` |
| `watch-used-cars.yml` | `13 22 * * *` daily | `watch_used.py` then `watchlist.py` | `data/used_cars/**` |
| `download-coe.yml` | `17 20 * * 0` weekly | `scripts/download_coe.py` | `data/coe/*.json` |
| `bump-watch-year.yml` | `37 20 1 1 *` annually | `jq` bump of `year_from` | `data/used_cars/*/config.json` |

Details worth knowing:
- The pricelist workflow uses **sparse checkout** excluding `data/pricelists/**/*.pdf`, so the
  PDFs are never fetched into the runner. `manifest.json` is what tells the downloader which
  PDFs already exist; without it every run would re-download everything.
- The pricelist workflow's `test` job currently has the pytest step commented out.
- `watch-used-cars.yml` fetches a fresh SG proxy list from proxyscrape.com and passes it as
  `PROXY_FALLBACKS`.
- `cpo_main.py` exits non-zero if any site errored, so a partial CPO scrape fails the job
  and the commit step is skipped — even though `save_results()` already wrote the snapshot.
- `archive_to_r2.py` is **not** wired into any workflow — it is run manually.

## Important Implementation Notes

### Concurrency

- **Latest pricelist mode**: `ThreadPoolExecutor` with `DEFAULT_MAX_WORKERS=10` for parallel HTTP downloads
- **Historical mode**: `DEFAULT_BROWSER_MAX_WORKERS=5` parallel Playwright browser instances (more resource-intensive)
- **CPO**: `CPO_DEFAULT_MAX_WORKERS=3` — one browser per site, each retried once on failure
- PDF extraction can be enabled/disabled via `--no-extract` flag

### Multi-Provider Extraction Fallback

`extract_pdf_with_fallback()` in `analysis/pdf_extractor.py` tries three providers in order:

1. **Gemini** (`GeminiPDFExtractor`) — vision, PDF sent base64
2. **DeepSeek** (`DeepSeekPDFExtractor`) — text-only via pypdf; raises `ValueError` for
   image-based or garbled PDFs, which explicitly triggers the next fallback
3. **Mimo** (`MimoPDFExtractor`) — vision; pages rendered to images with PyMuPDF (`fitz`)

All three talk to OpenAI-compatible endpoints through the `openai` SDK and populate the same
`SGCarMartPriceListExtraction` schema with per-provider cost tracking. Missing keys are
skipped rather than fatal; it only raises when no key is set at all.

Two caveats: `main.py` gates auto-extraction on `GEMINI_API_KEY` alone, so the DeepSeek/Mimo
fallbacks are unreachable from a download run without it. And `batch_extract.py` uses
`GeminiPDFExtractor` directly — it does **not** use the fallback chain.

### Download Manifest

`sgcarmart/utils/manifest.py` keeps `data/pricelists/manifest.json` as a `rel_path → md5`
map, guarded by a lock for thread-safe writes. `download_pdf()` checks `is_known()` before
fetching. This is what makes the sparse-checkout CI run work: the PDFs are absent from the
runner, so an on-disk existence check would fail and re-download everything.

`main.py` calls `manifest.load()` before the run and `manifest.save()` after.

### Used Car Scraping Strategy

The HTTP path is primary and needs no browser: it regex-extracts the `self.__next_f.push`
RSC chunks from the server-rendered Next.js HTML, JSON-decodes them, and bracket-matches the
`listing_data.data` array.

`_BlockedResponseError` is the important distinction — a page missing the RSC structure
entirely is a block/challenge page and is retried, whereas a present-but-empty data array is
a genuine end-of-pagination signal and stops cleanly. Per page, the whole proxy sweep is
retried 3× with linear backoff. A block on page 1 raises; a block on a later page keeps
whatever was collected.

### Proxy Rotation

Both used-car paths rotate proxies. The HTTP path tries the cached working proxy, then
direct, then each `PROXY_FALLBACKS` entry, caching the first that succeeds. The Playwright
path always tries direct first and restarts the browser per proxy attempt.
`PROXY_FALLBACKS` is capped at 10 entries to bound worst-case wait time.

### Degenerate-Result Guards

Both daily watches treat "zero results" as a scrape failure rather than data, because a
daily observation cannot be backfilled:

- `watch_used.py` raises `DegenerateFetchError` (non-zero exit) and writes **nothing** —
  no dated snapshot, and `latest.json` is left untouched so the next run still diffs
  against real data.
- `cpo_main.py` exits 1 before calling `save_results()` when every site came back empty,
  so nothing is written. It also exits 1 if any individual site errored, which keeps the
  workflow's commit step from running on a partial scrape.
- `cpo.py`'s `save_results()` keeps a second, independent guard: it writes the dated
  snapshot but skips overwriting `latest.json` when given 0 listings and a previous
  snapshot had data. This still matters for direct library callers.

Preserve this behaviour when changing either script.

### Robots.txt Compliance

All scraping respects SGCarMart's robots.txt. Tests verify compliance (`test_robots_compliance.py`).
`cpo.py` documents its exclusions in the module docstring — Tesla is excluded because its
robots.txt returns HTTP 403 and access cannot be verified.

### Rate Limiting

`http.py` implements retry logic with exponential backoff for failed requests. Raises
`RateLimitError` when rate limited. The COE client sleeps 1s between API pages.

### PDF Validation

Two-stage validation:
1. **Basic**: Magic bytes (`%PDF`) and minimum size check
2. **Corruption**: Uses pypdf to detect malformed PDFs (`pdf_checker.py`)

### File Naming Convention

Pricelist files follow: `{brand}_{dealer_id}_{date}.{ext}`
- PDFs: `dealer_44_2025-01-15.pdf`
- JSON: `toyota_44_2025-01-15.json`

Snapshot files (used cars, CPO) are named by ISO date: `2026-09-20.json`, with a
`latest.json` alongside.

### Brand Name Normalization

`normalize_brand_name()` converts brand names to lowercase with hyphens (e.g., "Mercedes-Benz" → "mercedes-benz") for consistent directory/file naming.

### Dependencies

`boto3`/`botocore` live in the `archive` optional extra, not the runtime deps — only
`scripts/archive_to_r2.py` needs them and no workflow runs it. Use
`uv sync --extra archive` (or `make sync` / `uv sync --all-extras`) before running it.
`requests[socks]` carries the `socks` extra because the proxy lists are socks5 URLs.
The `[dependency-groups] dev` block (jupyter, matplotlib, pandas, seaborn) exists for the
notebooks in `analysis/` and is not needed by any pipeline.
