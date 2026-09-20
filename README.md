# Car Data in Singapore

A Python data archive for the Singapore car market. Scrapers run on a daily/weekly schedule
via GitHub Actions and commit their output back into `data/`, so the repository doubles as
the time series.

## Disclaimer

This project is for **educational purposes only** and **not for profit**. The data collected is intended for learning web scraping techniques, data analysis, and software development practices. This project respects the terms of service of all data sources and is not intended for commercial use or redistribution.

## What it collects

| Pipeline | Source | Output |
| --- | --- | --- |
| **New car pricelists** | SGCarMart dealer pages | PDFs plus structured JSON extracted with LLM vision/text models |
| **Used car listings** | SGCarMart used car search | Daily snapshot and diff for a configured filter set |
| **Value watchlist** | Derived from the above | Used listings ranked by a COE-adjusted composite value score |
| **CPO listings** | ~8 Singapore dealer sites | Daily certified pre-owned inventory snapshot |
| **COE results** | data.gov.sg | Certificate of Entitlement bidding premiums, one file per year |

An [Observable Framework](https://observablehq.com/framework/) site under `site/` publishes
the value watchlist.

## Setup

1. Install dependencies using `uv`:

```bash
uv venv
uv sync
```

2. Install the Playwright browser used by the CPO scraper, historical pricelist downloads,
   and the used-car fallback path:

```bash
uv run playwright install chromium
```

3. Optional: copy `analysis/.env.example` to `analysis/.env` and fill in the API keys you
   need. Everything is optional — without keys you can still download PDFs (extraction is
   skipped) and scrape used car and CPO listings.

## Usage

Download the latest new car price lists for all dealers:

```bash
uv run main.py
```

PDFs are saved to `data/pricelists/{brand}/{year}/`, extracted JSON lands alongside them,
and a run report is written to `data/`.

Snapshot used car listings and build the value watchlist:

```bash
uv run python scripts/watch_used.py
uv run python scripts/watchlist.py --name sgd-passenger
```

Scrape certified pre-owned listings:

```bash
uv run cpo_main.py
```

Download COE bidding results:

```bash
uv run python scripts/download_coe.py
```

Preview the watchlist site:

```bash
cd site && npm install && npm run dev
```

See [CLAUDE.md](CLAUDE.md) for the full command reference, architecture notes, and
environment variable documentation.

## Development

```bash
make sync     # uv sync --all-extras
make format   # ruff format + ruff check --fix
make check    # ruff check
uv run pytest # tests with coverage
```

## License

See [LICENSE](LICENSE) file for details.
