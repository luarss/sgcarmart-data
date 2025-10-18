import json
import re
from urllib.parse import unquote
from xml.etree import ElementTree

import pytest

from constants import DEALER_BRAND_MAPPING_FILE, BASE_URL, DEFAULT_PAGE_TIMEOUT
from sgcarmart.utils.http import fetch_with_retry


def parse_sitemap_for_dealers():
    sitemap_url = f"{BASE_URL}/sitemap.xml"
    response = fetch_with_retry(sitemap_url, DEFAULT_PAGE_TIMEOUT)

    dealer_brand_map = {}
    pattern = re.compile(r'/new-cars/pricelists/(\d+)/(.+?)(?:\?|$)')

    root = ElementTree.fromstring(response.content)

    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = root.findall('.//ns:url/ns:loc', namespace)

    if not urls:
        urls = root.findall('.//url/loc')

    for url_element in urls:
        url = url_element.text
        if url:
            match = pattern.search(url)
            if match:
                dealer_id = match.group(1)
                brand_raw = match.group(2)
                brand = unquote(brand_raw).lower()
                dealer_brand_map[dealer_id] = brand

    return dealer_brand_map


@pytest.mark.integration
def test_dealer_brand_mapping_is_up_to_date():
    with open(DEALER_BRAND_MAPPING_FILE, 'r') as f:
        current_map = json.load(f)

    sitemap_map = parse_sitemap_for_dealers()

    current_dealers = set(current_map.keys())
    sitemap_dealers = set(sitemap_map.keys())

    added_dealers = sitemap_dealers - current_dealers
    removed_dealers = current_dealers - sitemap_dealers

    changed_brands = {}
    for dealer_id in current_dealers & sitemap_dealers:
        if current_map[dealer_id] != sitemap_map[dealer_id]:
            changed_brands[dealer_id] = {
                'old': current_map[dealer_id],
                'new': sitemap_map[dealer_id]
            }

    if added_dealers or removed_dealers or changed_brands:
        error_msg = ["Dealer-brand mapping is out of date.", ""]

        if added_dealers:
            error_msg.append("Added dealers:")
            for dealer_id in sorted(added_dealers, key=int):
                error_msg.append(f"  + Dealer {dealer_id}: {sitemap_map[dealer_id]}")
            error_msg.append("")

        if removed_dealers:
            error_msg.append("Removed dealers:")
            for dealer_id in sorted(removed_dealers, key=int):
                error_msg.append(f"  - Dealer {dealer_id}: {current_map[dealer_id]}")
            error_msg.append("")

        if changed_brands:
            error_msg.append("Changed brands:")
            for dealer_id in sorted(changed_brands.keys(), key=int):
                old_brand = changed_brands[dealer_id]['old']
                new_brand = changed_brands[dealer_id]['new']
                error_msg.append(f"  ~ Dealer {dealer_id}: {old_brand} -> {new_brand}")
            error_msg.append("")

        error_msg.append("Run 'uv run python check_mapping_changes.py --update' to update it.")

        pytest.fail("\n".join(error_msg))
