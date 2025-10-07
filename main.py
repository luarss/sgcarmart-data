#!/usr/bin/env python3
from bs4 import BeautifulSoup
import json
import requests
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DEALER_BRAND_MAPPING_FILE = "data/dealer_brand_mapping.json"

def normalize_brand_name(brand):
    return brand.lower().replace(" ", "-").replace("_", "-")

def load_dealer_brand_mapping():
    with open(DEALER_BRAND_MAPPING_FILE, 'r') as f:
        return json.load(f)

def download_pricelist(pricelist_url, brand_name, dealer_id, date, output_dir="data/pricelists"):
    os.makedirs(output_dir, exist_ok=True)

    brand_dir = os.path.join(output_dir, normalize_brand_name(brand_name))
    os.makedirs(brand_dir, exist_ok=True)

    filename = f"dealer_{dealer_id}_{date}.pdf"
    filepath = os.path.join(brand_dir, filename)

    if os.path.exists(filepath):
        file_size = os.path.getsize(filepath)
        return filepath, f"Already exists ({file_size} bytes)"

    try:
        response = requests.get(pricelist_url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        if 'application/pdf' not in content_type:
            return None, f"Not a PDF file (content-type: {content_type})"

        if len(response.content) < 1000:
            return None, f"File too small ({len(response.content)} bytes)"

        if response.content[:4] != b'%PDF':
            return None, "Invalid PDF header"

        with open(filepath, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        return filepath, f"Downloaded ({file_size} bytes)"

    except Exception as e:
        return None, f"Failed: {str(e)}"

def scrape_pricelist_links(html_content):
    """
    Parses the given HTML content to extract PDF links for the price lists.

    Args:
        html_content: A string containing the HTML source code of the page.

    Returns:
        A list of strings, where each string is a URL to a PDF price list.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    pricelist_links = []

    links_container = soup.find('div', class_='styles_containerDatesContent__nOueF')

    if links_container:
        for link in links_container.find_all('a', class_='styles_textPricelistLink__UvFUj'):
            pdf_url = link.get('href')
            if pdf_url and isinstance(pdf_url, str) and pdf_url.endswith('.pdf'):
                pricelist_links.append(pdf_url)

    return pricelist_links

def process_dealer(dealer_id, brand_name):
    brand_url = f"https://www.sgcarmart.com/new-cars/pricelists/{dealer_id}/{normalize_brand_name(brand_name)}"

    try:
        response = requests.get(brand_url, timeout=10)
        response.raise_for_status()
        html_content = response.text

        extracted_links = scrape_pricelist_links(html_content)

        if extracted_links:
            latest_url = extracted_links[0]
            full_url = latest_url if latest_url.startswith('http') else f"https://www.sgcarmart.com{latest_url}"
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
    except Exception as e:
        return {
            "dealer_id": dealer_id,
            "brand": brand_name,
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    dealer_brand_mapping = load_dealer_brand_mapping()

    print("SGCarMart Pricelist Downloader")
    print("=" * 60)
    print(f"Total dealers to check: {len(dealer_brand_mapping)}\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_dealers = {"82": "mg", "44": "toyota", "4": "bmw"}
        dealer_brand_mapping = test_dealers
        print("TEST MODE: Processing only MG, Toyota, BMW\n")

    results = []
    max_workers = 10

    print("Processing dealers in parallel...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_dealer, dealer_id, brand_name): (dealer_id, brand_name)
            for dealer_id, brand_name in dealer_brand_mapping.items()
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(".", end="", flush=True)
    print()

    downloaded_count = sum(1 for r in results if r.get("status") == "success")
    found_count = sum(1 for r in results if r.get("status") in ["success", "failed"])

    report_file = f"data/download_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total dealers scanned: {len(dealer_brand_mapping)}")
    print(f"Pricelists found: {found_count}")
    print(f"Successfully downloaded: {downloaded_count}")
    print(f"\nReport saved to: {report_file}")