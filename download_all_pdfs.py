#!/usr/bin/env python3
import argparse
import json
import requests
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from constants import (
    BASE_URL,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_PAGE_TIMEOUT,
    DEFAULT_PDF_MAX_WORKERS,
    MIN_PDF_SIZE_BYTES,
    PDF_MAGIC_HEADER,
    PDF_CONTENT_TYPE,
    DEALER_BRAND_MAPPING_FILE,
    MAX_RETRIES,
    INITIAL_RETRY_DELAY,
)
from common import get_random_user_agent, scrape_pricelist_links, normalize_brand_name

def load_dealer_brand_mapping():
    with open(DEALER_BRAND_MAPPING_FILE, 'r') as f:
        return json.load(f)

def extract_metadata_from_url(pdf_url):
    parts = pdf_url.rstrip('/').split('/')
    filename = parts[-1].replace('.pdf', '')
    dealer_id = None

    if 'pricelist' in pdf_url:
        pricelist_index = parts.index('pricelist')
        if pricelist_index + 1 < len(parts):
            dealer_id = parts[pricelist_index + 1]

    return {
        'filename': filename,
        'dealer_id': dealer_id,
        'date': filename
    }

class RateLimitException(Exception):
    pass

@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=INITIAL_RETRY_DELAY, min=INITIAL_RETRY_DELAY, max=60),
    retry=retry_if_exception_type(RateLimitException),
    reraise=True
)
def fetch_with_retry(url, timeout):
    headers = {"User-Agent": get_random_user_agent()}
    response = requests.get(url, headers=headers, timeout=timeout)

    if response.status_code == 429:
        raise RateLimitException("Rate limited")

    response.raise_for_status()
    return response

def download_pdf(pdf_url, brand_name=None, output_dir="data/pricelists"):
    metadata = extract_metadata_from_url(pdf_url)
    dealer_id = metadata['dealer_id']
    date = metadata['date']

    if brand_name:
        brand_dir = os.path.join(output_dir, normalize_brand_name(brand_name))
        os.makedirs(brand_dir, exist_ok=True)

        if dealer_id:
            filename = f"dealer_{dealer_id}_{date}.pdf"
        else:
            filename = f"{date}.pdf"

        filepath = os.path.join(brand_dir, filename)
    else:
        os.makedirs(output_dir, exist_ok=True)
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

        content_type = response.headers.get('content-type', '').lower()
        if PDF_CONTENT_TYPE not in content_type:
            return {
                "url": pdf_url,
                "filepath": None,
                "filename": filename,
                "dealer_id": dealer_id,
                "date": date,
                "status": "failed",
                "message": f"Not a PDF file (content-type: {content_type})"
            }

        if len(response.content) < MIN_PDF_SIZE_BYTES:
            return {
                "url": pdf_url,
                "filepath": None,
                "filename": filename,
                "dealer_id": dealer_id,
                "date": date,
                "status": "failed",
                "message": f"File too small ({len(response.content)} bytes)"
            }

        if response.content[:4] != PDF_MAGIC_HEADER:
            return {
                "url": pdf_url,
                "filepath": None,
                "filename": filename,
                "dealer_id": dealer_id,
                "date": date,
                "status": "failed",
                "message": "Invalid PDF header"
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

def extract_brand_from_url(page_url):
    parts = page_url.rstrip('/').split('/')
    if 'pricelists' in parts:
        pricelists_index = parts.index('pricelists')
        if pricelists_index + 2 < len(parts):
            return parts[pricelists_index + 2]
    return None

def download_all_pdfs_from_page(page_url, brand_name=None, output_dir="data/pricelists", max_workers=DEFAULT_PDF_MAX_WORKERS):
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
        print(f"Downloading to: {output_dir}/{normalize_brand_name(brand_name)}/")
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SGCarMart PDF Downloader - Download all pricelists for dealers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all
  %(prog)s --brand mg
  %(prog)s --brand toyota
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Download all PDFs for all dealers"
    )
    group.add_argument(
        "--brand",
        type=str,
        metavar="NAME",
        help="Download all PDFs for specific brand"
    )

    args = parser.parse_args()

    print("SGCarMart PDF Downloader")
    print("=" * 60)

    dealer_brand_mapping = load_dealer_brand_mapping()
    all_results = []
    output_dir = "data/pricelists"

    if args.all:
        print(f"Downloading PDFs for all {len(dealer_brand_mapping)} dealers\n")

        for did, dbrand in dealer_brand_mapping.items():
            purl = f"{BASE_URL}/new-cars/pricelists/{did}/{normalize_brand_name(dbrand)}"
            print(f"\n[Dealer {did} - {dbrand}]")
            results = download_all_pdfs_from_page(purl, dbrand, output_dir)
            all_results.extend(results)

    elif args.brand:
        matching_dealers = {did: dbrand for did, dbrand in dealer_brand_mapping.items()
                          if normalize_brand_name(dbrand) == normalize_brand_name(args.brand)}

        if not matching_dealers:
            print(f"Error: No dealers found for brand '{args.brand}'")
            print(f"\nAvailable brands: {', '.join(sorted(set(dealer_brand_mapping.values())))}")
            sys.exit(1)

        print(f"Downloading PDFs for brand '{args.brand}' ({len(matching_dealers)} dealer(s))\n")

        for did, dbrand in matching_dealers.items():
            purl = f"{BASE_URL}/new-cars/pricelists/{did}/{normalize_brand_name(dbrand)}"
            print(f"\n[Dealer {did} - {dbrand}]")
            results = download_all_pdfs_from_page(purl, dbrand, output_dir)
            all_results.extend(results)

    success_count = sum(1 for r in all_results if r["status"] == "success")
    skipped_count = sum(1 for r in all_results if r["status"] == "skipped")
    failed_count = sum(1 for r in all_results if r["status"] in ["failed", "error"])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total PDFs found: {len(all_results)}")
    print(f"Downloaded: {success_count}")
    print(f"Skipped (already exist): {skipped_count}")
    print(f"Failed: {failed_count}")

    report_file = f"data/pdf_download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("data", exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump({
            "mode": "all" if args.all else "brand",
            "brand_filter": args.brand if args.brand else None,
            "output_directory": output_dir,
            "timestamp": datetime.now().isoformat(),
            "results": all_results,
            "summary": {
                "total": len(all_results),
                "downloaded": success_count,
                "skipped": skipped_count,
                "failed": failed_count
            }
        }, f, indent=2)

    print(f"\nReport saved to: {report_file}")
