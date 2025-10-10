import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from constants import (
    BASE_URL,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_PAGE_TIMEOUT,
    DEFAULT_PDF_MAX_WORKERS,
    MAX_RETRIES,
)
from sgcarmart.utils.http import fetch_with_retry, RateLimitException
from sgcarmart.utils.validation import validate_pdf
from sgcarmart.utils.file_utils import (
    normalize_brand_name,
    ensure_directory,
    extract_metadata_from_url,
)
from sgcarmart.core.scraper import scrape_pricelist_links


def download_pricelist(pricelist_url, brand_name, dealer_id, date, output_dir="data/pricelists"):
    ensure_directory(output_dir)

    brand_dir = os.path.join(output_dir, normalize_brand_name(brand_name))
    ensure_directory(brand_dir)

    # Extract year from date and create year folder
    year = date.split('-')[0] if '-' in date else date[:4]
    year_dir = os.path.join(brand_dir, year)
    ensure_directory(year_dir)

    filename = f"dealer_{dealer_id}_{date}.pdf"
    filepath = os.path.join(year_dir, filename)

    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        return filepath, f"Already exists ({file_size} bytes)"

    try:
        response = fetch_with_retry(pricelist_url, DEFAULT_REQUEST_TIMEOUT)

        is_valid, message = validate_pdf(response)
        if not is_valid:
            return None, message

        with open(filepath, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        return filepath, f"Downloaded ({file_size} bytes)"

    except RateLimitException:
        return None, f"429 Too Many Requests after {MAX_RETRIES} attempts"
    except Exception as e:
        return None, f"Failed: {str(e)}"


def download_pdf(pdf_url, brand_name=None, output_dir="data/pricelists"):
    metadata = extract_metadata_from_url(pdf_url)
    dealer_id = metadata['dealer_id']
    date = metadata['date']

    if brand_name:
        brand_dir = os.path.join(output_dir, normalize_brand_name(brand_name))
        ensure_directory(brand_dir)

        # Extract year from date and create year folder
        year = date.split('-')[0] if '-' in date else date[:4]
        year_dir = os.path.join(brand_dir, year)
        ensure_directory(year_dir)

        if dealer_id:
            filename = f"dealer_{dealer_id}_{date}.pdf"
        else:
            filename = f"{date}.pdf"

        filepath = os.path.join(year_dir, filename)
    else:
        ensure_directory(output_dir)
        filename = pdf_url.split('/')[-1]
        filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        return {
            "url": pdf_url,
            "filepath": filepath,
            "filename": filename,
            "dealer_id": dealer_id,
            "date": date,
            "status": "skipped",
            "message": f"Already exists ({file_size} bytes)"
        }

    try:
        response = fetch_with_retry(pdf_url, DEFAULT_REQUEST_TIMEOUT)

        is_valid, message = validate_pdf(response)
        if not is_valid:
            return {
                "url": pdf_url,
                "filepath": None,
                "filename": filename,
                "dealer_id": dealer_id,
                "date": date,
                "status": "failed",
                "message": message
            }

        with open(filepath, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        return {
            "url": pdf_url,
            "filepath": filepath,
            "filename": filename,
            "dealer_id": dealer_id,
            "date": date,
            "status": "success",
            "message": f"Downloaded ({file_size} bytes)"
        }

    except RateLimitException:
        return {
            "url": pdf_url,
            "filepath": None,
            "filename": filename,
            "dealer_id": dealer_id,
            "date": date,
            "status": "error",
            "message": f"429 Too Many Requests after {MAX_RETRIES} attempts"
        }
    except Exception as e:
        return {
            "url": pdf_url,
            "filepath": None,
            "filename": filename,
            "dealer_id": dealer_id,
            "date": date,
            "status": "error",
            "message": str(e)
        }


def process_dealer(dealer_id, brand_name):
    brand_url = f"https://www.sgcarmart.com/new-cars/pricelists/{dealer_id}/{normalize_brand_name(brand_name)}"

    try:
        response = fetch_with_retry(brand_url, DEFAULT_PAGE_TIMEOUT)
        html_content = response.text

        extracted_links = scrape_pricelist_links(html_content)

        if extracted_links:
            latest_url = extracted_links[0]
            full_url = latest_url if latest_url.startswith('http') else f"{BASE_URL}{latest_url}"
            date_match = latest_url.split('/')[-1].replace('.pdf', '')

            filepath, status = download_pricelist(full_url, brand_name, dealer_id, date_match)

            if filepath:
                return {
                    "dealer_id": dealer_id,
                    "brand": brand_name,
                    "url": full_url,
                    "date": date_match,
                    "filepath": filepath,
                    "status": "success"
                }
            else:
                return {
                    "dealer_id": dealer_id,
                    "brand": brand_name,
                    "url": full_url,
                    "date": date_match,
                    "status": "failed",
                    "error": status
                }
        else:
            return {
                "dealer_id": dealer_id,
                "brand": brand_name,
                "status": "not_found"
            }
    except RateLimitException:
        return {
            "dealer_id": dealer_id,
            "brand": brand_name,
            "status": "error",
            "error": f"429 Too Many Requests after {MAX_RETRIES} attempts"
        }
    except Exception as e:
        return {
            "dealer_id": dealer_id,
            "brand": brand_name,
            "status": "error",
            "error": str(e)
        }


def download_all_pdfs_from_page(page_url, brand_name=None, output_dir="data/pricelists", max_workers=DEFAULT_PDF_MAX_WORKERS):
    from sgcarmart.core.scraper import extract_brand_from_url

    print(f"Fetching page: {page_url}")

    if not brand_name:
        brand_name = extract_brand_from_url(page_url)
        if brand_name:
            print(f"Detected brand: {brand_name}")

    try:
        response = fetch_with_retry(page_url, DEFAULT_PAGE_TIMEOUT)
        html_content = response.text
    except RateLimitException:
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
        full_url = link if link.startswith('http') else f"{BASE_URL}{link}"
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
            executor.submit(download_pdf, url, brand_name, output_dir): url
            for url in full_urls
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            status_symbol = "✓" if result["status"] == "success" else "○" if result["status"] == "skipped" else "✗"
            display_name = result.get('filename', result['url'].split('/')[-1])
            if result.get('dealer_id') and result.get('date'):
                display_name = f"dealer_{result['dealer_id']}_{result['date']}.pdf"
            print(f"{status_symbol} {display_name}: {result['message']}")

    return results
