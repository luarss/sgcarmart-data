from __future__ import annotations

import os
import time

from constants import COE_API_BASE_URL, COE_API_PAGE_LIMIT, COE_RESOURCE_ID, DEFAULT_REQUEST_TIMEOUT
from sgcarmart.utils.http import fetch_with_retry


class COEAPIError(Exception):
    pass


def _get_api_headers() -> dict | None:
    api_key = os.environ.get("DATA_GOV_API_KEY")
    if api_key:
        return {"x-api-key": api_key}
    return None


def fetch_coe_results(resource_id: str = COE_RESOURCE_ID) -> list[dict]:
    url = f"{COE_API_BASE_URL}?resource_id={resource_id}&limit={COE_API_PAGE_LIMIT}"
    all_records = []
    headers = _get_api_headers()

    while url:
        response = fetch_with_retry(url, timeout=DEFAULT_REQUEST_TIMEOUT, extra_headers=headers)

        try:
            data = response.json()
        except ValueError:
            raise COEAPIError("Invalid JSON response from COE API")

        if not data.get("success"):
            raise COEAPIError(f"COE API returned success=false: {data.get('error', 'unknown error')}")

        result = data.get("result", {})
        records = result.get("records", [])
        if not records:
            break
        all_records.extend(records)

        links = result.get("_links", {})
        next_url = links.get("next")
        if next_url and next_url.startswith("/"):
            next_url = f"https://data.gov.sg{next_url}"
        url = next_url

        if url:
            time.sleep(1.0)

    return all_records
