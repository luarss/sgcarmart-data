import json
import re
from urllib.parse import unquote
from xml.etree import ElementTree

import pytest

from sgcarmart.constants import DEALER_BRAND_MAPPING_FILE, BASE_URL, DEFAULT_PAGE_TIMEOUT
from sgcarmart.utils.http import fetch_with_retry


def parse_sitemap_for_dealers():
    sitemap_url = f"{BASE_URL}/sitemap.xml"
    response = fetch_with_retry(sitemap_url, DEFAULT_PAGE_TIMEOUT)

    dealer_brand_map = {}
    pattern = re.compile(r'/new-cars/pricelists/(\d+)/(.+?)(?:\?|$)')

    root = ElementTree.fromstring(response.content)

    namespace = {'ns': 'https://www.sitemaps.org/schemas/sitemap/0.9'}
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


def _build_mapping_error(added, removed, changed, current_map, sitemap_map):
    """Build error message for dealer-brand mapping drift."""
    error_msg = ["Dealer-brand mapping is out of date.", ""]

    if added:
        error_msg.append("Added dealers:")
        for dealer_id in sorted(added, key=int):
            error_msg.append(f"  + Dealer {dealer_id}: {sitemap_map[dealer_id]}")
        error_msg.append("")

    if removed:
        error_msg.append("Removed dealers:")
        for dealer_id in sorted(removed, key=int):
            error_msg.append(f"  - Dealer {dealer_id}: {current_map[dealer_id]}")
        error_msg.append("")

    if changed:
        error_msg.append("Changed brands:")
        for dealer_id in sorted(changed.keys(), key=int):
            error_msg.append(f"  ~ Dealer {dealer_id}: {changed[dealer_id]['old']} -> {changed[dealer_id]['new']}")
        error_msg.append("")

    error_msg.append("Run 'uv run python check_mapping_changes.py --update' to update it.")
    return "\n".join(error_msg)


@pytest.mark.integration
def test_dealer_brand_mapping_is_up_to_date():
    with open(DEALER_BRAND_MAPPING_FILE, 'r') as f:
        current_map = json.load(f)

    sitemap_map = parse_sitemap_for_dealers()

    current_dealers = set(current_map.keys())
    sitemap_dealers = set(sitemap_map.keys())

    added_dealers = sitemap_dealers - current_dealers
    removed_dealers = current_dealers - sitemap_dealers

    changed_brands = {
        dealer_id: {'old': current_map[dealer_id], 'new': sitemap_map[dealer_id]}
        for dealer_id in current_dealers & sitemap_dealers
        if current_map[dealer_id] != sitemap_map[dealer_id]
    }

    if added_dealers or removed_dealers or changed_brands:
        pytest.fail(_build_mapping_error(added_dealers, removed_dealers, changed_brands, current_map, sitemap_map))
