# Car Data in Singapore

A Python web scraper that downloads and archives car price list PDFs from SGCarMart for all dealers and brands.

## Disclaimer

This project is for **educational purposes only** and **not for profit**. The data collected is intended for learning web scraping techniques, data analysis, and software development practices. This project respects the terms of service of all data sources and is not intended for commercial use or redistribution.

## Setup

1. Install dependencies using `uv`:
```bash
uv venv
uv sync
```

## Usage

Download price lists for all dealers:

```bash
uv run main.py
```

Downloaded PDFs are saved to `data/pricelists/{brand}/` and a JSON report is generated in `data/`.

## License

See [LICENSE](LICENSE) file for details.
