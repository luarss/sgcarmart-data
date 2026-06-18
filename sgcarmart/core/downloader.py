import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sgcarmart.constants import (
    BASE_URL,
    DEFAULT_EXTRACT_MODEL,
    DEFAULT_PAGE_TIMEOUT,
    DEFAULT_PDF_MAX_WORKERS,
    DEFAULT_REQUEST_TIMEOUT,
    MAX_RETRIES,
    PRICELIST_URL_TEMPLATE,
)
from sgcarmart.core.scraper import scrape_pricelist_links
from sgcarmart.utils.file_utils import (
    ensure_directory,
    extract_metadata_from_url,
    normalize_brand_name,
)
from sgcarmart.utils.http import RateLimitError, fetch_with_retry
from sgcarmart.utils.manifest import is_known, record
from sgcarmart.utils.validation import validate_pdf

PRICELISTS_DIR = "data/pricelists"


def _setup_filepath(brand_name, dealer_id, date, output_dir):
    brand_dir = os.path.join(output_dir, normalize_brand_name(brand_name))
    ensure_directory(brand_dir)

    year = date.split("-")[0] if "-" in date else date[:4]
    year_dir = os.path.join(brand_dir, year)
    ensure_directory(year_dir)

    filename = f"dealer_{dealer_id}_{date}.pdf"
    filepath = os.path.join(year_dir, filename)

    return filepath, filename


def _attempt_extraction(filepath, brand_name, dealer_id, date, extract_model):
    from analysis.pdf_extractor import extract_pdf_with_fallback, save_extraction

    brand_normalized = normalize_brand_name(brand_name)
    json_filename = f"{brand_normalized}_{dealer_id}_{date}.json"
    json_path = Path(filepath).parent / json_filename

    if not json_path.exists():
        extraction = extract_pdf_with_fallback(Path(filepath), model=extract_model)
        output_path = save_extraction(extraction)
        return "success", str(output_path)
    else:
        return "skipped", None


def download_pricelist(pricelist_url, brand_name, dealer_id, date, output_dir=PRICELISTS_DIR):
    ensure_directory(output_dir)
    filepath, _ = _setup_filepath(brand_name, dealer_id, date, output_dir)

    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        return filepath, f"Already exists ({file_size} bytes)"

    try:
        response = fetch_with_retry(pricelist_url, DEFAULT_REQUEST_TIMEOUT)

        is_valid, message = validate_pdf(response)
        if not is_valid:
            return None, message

        with open(filepath, "wb") as f:
            f.write(response.content)

        file_size = len(response.content)
        return filepath, f"Downloaded ({file_size} bytes)"

    except RateLimitError:
        return None, f"429 Too Many Requests after {MAX_RETRIES} attempts"
    except Exception as e:
        return None, f"Failed: {e!s}"


def _make_result(pdf_url, filepath, filename, dealer_id, date, status, message):
    return {
        "url": pdf_url,
        "filepath": filepath,
        "filename": filename,
        "dealer_id": dealer_id,
        "date": date,
        "status": status,
        "message": message,
    }


def _maybe_extract(result, filepath, brand_name, dealer_id, date, extract_model):
    if not brand_name:
        return
    try:
        extraction_status, json_path = _attempt_extraction(filepath, brand_name, dealer_id, date, extract_model)
        result["extraction"] = extraction_status
        if json_path:
            result["json_path"] = json_path
    except Exception as e:
        result["extraction"] = "failed"
        result["extraction_error"] = str(e)
        print(f"⚠ Extraction failed for {result.get('filename', filepath)}: {e}")


def download_pdf(
    pdf_url, brand_name=None, output_dir=PRICELISTS_DIR, auto_extract=False, extract_model=DEFAULT_EXTRACT_MODEL
):
    metadata = extract_metadata_from_url(pdf_url)
    dealer_id = metadata["dealer_id"]
    date = metadata["date"]

    if brand_name:
        filepath, filename = _setup_filepath(brand_name, dealer_id, date, output_dir)
    else:
        ensure_directory(output_dir)
        filename = pdf_url.split("/")[-1]
        filepath = os.path.join(output_dir, filename)

    rel_key = str(Path(filepath).relative_to(output_dir))

    if is_known(rel_key):
        result = _make_result(pdf_url, filepath, filename, dealer_id, date, "skipped", "Already exists")
        if auto_extract:
            _maybe_extract(result, filepath, brand_name, dealer_id, date, extract_model)
        return result

    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        result = _make_result(
            pdf_url, filepath, filename, dealer_id, date, "skipped", f"Already exists ({file_size} bytes)"
        )
        if auto_extract:
            _maybe_extract(result, filepath, brand_name, dealer_id, date, extract_model)
        return result

    try:
        response = fetch_with_retry(pdf_url, DEFAULT_REQUEST_TIMEOUT)
        is_valid, message = validate_pdf(response)
        if not is_valid:
            return _make_result(pdf_url, None, filename, dealer_id, date, "failed", message)

        content = response.content
        record(rel_key, content)
        with open(filepath, "wb") as f:
            f.write(content)

        result = _make_result(
            pdf_url, filepath, filename, dealer_id, date, "success", f"Downloaded ({len(content)} bytes)"
        )
        if auto_extract:
            _maybe_extract(result, filepath, brand_name, dealer_id, date, extract_model)
        return result

    except RateLimitError:
        return _make_result(
            pdf_url, None, filename, dealer_id, date, "error", f"429 Too Many Requests after {MAX_RETRIES} attempts"
        )
    except Exception as e:
        return _make_result(pdf_url, None, filename, dealer_id, date, "error", str(e))


def process_dealer(dealer_id, brand_name, auto_extract=False, extract_model=DEFAULT_EXTRACT_MODEL, output_dir=PRICELISTS_DIR):
    brand_url = PRICELIST_URL_TEMPLATE.format(dealer_id=dealer_id, brand=normalize_brand_name(brand_name))

    try:
        response = fetch_with_retry(brand_url, DEFAULT_PAGE_TIMEOUT)
        html_content = response.text

        extracted_links = scrape_pricelist_links(html_content)

        if extracted_links:
            latest_url = extracted_links[0]
            full_url = latest_url if latest_url.startswith("http") else f"{BASE_URL}{latest_url}"

            result = download_pdf(full_url, brand_name, output_dir=output_dir, auto_extract=auto_extract, extract_model=extract_model)
            result["brand"] = brand_name
            return result
        else:
            return {"dealer_id": dealer_id, "brand": brand_name, "status": "not_found"}
    except RateLimitError:
        return {
            "dealer_id": dealer_id,
            "brand": brand_name,
            "status": "error",
            "error": f"429 Too Many Requests after {MAX_RETRIES} attempts",
        }
    except Exception as e:
        return {"dealer_id": dealer_id, "brand": brand_name, "status": "error", "error": str(e)}


def download_all_pdfs_from_page(
    page_url,
    brand_name=None,
    output_dir=PRICELISTS_DIR,
    max_workers=DEFAULT_PDF_MAX_WORKERS,
    auto_extract=False,
    extract_model=DEFAULT_EXTRACT_MODEL,
):
    from sgcarmart.core.scraper import extract_brand_from_url

    print(f"Fetching page: {page_url}")

    if not brand_name:
        brand_name = extract_brand_from_url(page_url)
        if brand_name:
            print(f"Detected brand: {brand_name}")

    try:
        response = fetch_with_retry(page_url, DEFAULT_PAGE_TIMEOUT)
        html_content = response.text
    except RateLimitError:
        print(f"Error: 429 Too Many Requests after {MAX_RETRIES} attempts")
        return []
    except Exception as e:
        print(f"Error fetching page: {e}")
        return []

    pdf_links = scrape_pricelist_links(html_content)

    if not pdf_links:
        print("No PDF links found on the page")
        return []

    full_urls = []
    for link in pdf_links:
        full_url = link if link.startswith("http") else f"{BASE_URL}{link}"
        full_urls.append(full_url)

    print(f"Found {len(full_urls)} PDF(s) on the page")
    if brand_name:
        print(f"Downloading to: {output_dir}/{normalize_brand_name(brand_name)}/<year>/")
    else:
        print(f"Downloading to: {output_dir}/")
    print()

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_pdf, url, brand_name, output_dir, auto_extract, extract_model): url
            for url in full_urls
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            _print_download_progress(result)

    return results


def _print_download_progress(result):
    status = result["status"]
    status_symbol = "✓" if status == "success" else "○" if status == "skipped" else "✗"
    display_name = result.get("filename", result["url"].split("/")[-1])
    if result.get("dealer_id") and result.get("date"):
        display_name = f"dealer_{result['dealer_id']}_{result['date']}.pdf"
    print(f"{status_symbol} {display_name}: {result['message']}")
