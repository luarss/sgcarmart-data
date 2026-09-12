import json
from unittest.mock import patch

import pytest
import responses

import sgcarmart.core.used as used
from sgcarmart.core.used import (
    _BlockedResponseError,
    _parse_rsc_listings,
    fetch_all_listings_http,
)

LISTING_URL = used.LISTING_URL
BLOCKED_HTML = "<html>captcha challenge page, no RSC payload here</html>"


def _rsc_html(items: list[dict]) -> str:
    """Build a minimal Next.js RSC payload embedding listing_data.data,
    matching the real page's minified (no-whitespace) JSON shape."""
    payload = json.dumps({"listing_data": {"data": items}}, separators=(",", ":"))
    escaped = json.dumps(payload)[1:-1]
    return f'<script>self.__next_f.push([1,"{escaped}"])</script>'


def _item(i: int) -> dict:
    return {
        "id": i,
        "car_model": "Test Car",
        "link": "/used-cars/info/test-car-1500000/",
        "price": 70000,
        "depreciation": 8000,
        "registration_date": "01-Jan-2020",
        "coeLeft": "3y 2m",
        "mileage": "10,000 km",
        "engine_capacity": "1500 cc",
        "owners": "1 Owner",
        "tag": "",
        "date": "01-Jan-2026",
        "description": "",
    }


@pytest.fixture(autouse=True)
def reset_proxy_state():
    used._http_working_proxy = None
    yield
    used._http_working_proxy = None


@pytest.fixture(autouse=True)
def no_sleep():
    with patch.object(used.time, "sleep", lambda _: None):
        yield


@pytest.mark.unit
class TestParseRscListings:
    def test_parses_real_payload(self):
        items = _parse_rsc_listings(_rsc_html([_item(1), _item(2)]))
        assert len(items) == 2

    def test_genuine_empty_page_returns_empty_list(self):
        assert _parse_rsc_listings(_rsc_html([])) == []

    def test_missing_rsc_chunk_raises_blocked_error(self):
        with pytest.raises(_BlockedResponseError):
            _parse_rsc_listings(BLOCKED_HTML)

    def test_missing_listing_data_key_raises_blocked_error(self):
        html = '<script>self.__next_f.push([1,"{\\"other\\":1}"])</script>'
        with pytest.raises(_BlockedResponseError):
            _parse_rsc_listings(html)


@pytest.mark.unit
class TestFetchAllListingsHttp:
    @responses.activate
    def test_stops_on_genuine_empty_page(self):
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([_item(i) for i in range(100)]))
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([_item(100 + i) for i in range(50)]))
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([]))

        results = fetch_all_listings_http({"limit": 100}, max_pages=5, rate_limit=0)

        assert len(results) == 150

    @responses.activate
    def test_recovers_from_transient_block_via_retry(self):
        # Page 1 succeeds immediately.
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([_item(i) for i in range(100)]))
        # Page 2: blocked on every candidate for two full sweeps (direct + 1 fallback
        # proxy = 2 attempts per sweep), then succeeds on the third sweep.
        for _ in range(4):
            responses.add(responses.GET, LISTING_URL, body=BLOCKED_HTML)
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([_item(1000 + i) for i in range(50)]))
        # Page 3: genuine end of results.
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([]))

        with patch.object(used, "_PROXY_FALLBACKS", ["socks5://proxy1:1080"]):
            results = fetch_all_listings_http({"limit": 100}, max_pages=5, rate_limit=0)

        assert len(results) == 150

    @responses.activate
    def test_preserves_partial_results_when_later_page_unrecoverable(self):
        responses.add(responses.GET, LISTING_URL, body=_rsc_html([_item(i) for i in range(100)]))
        # Page 2 is blocked on every attempt, every retry sweep — never recovers.
        for _ in range(20):
            responses.add(responses.GET, LISTING_URL, body=BLOCKED_HTML)

        results = fetch_all_listings_http({"limit": 100}, max_pages=5, rate_limit=0)

        assert len(results) == 100

    @responses.activate
    def test_raises_when_page_one_is_blocked(self):
        for _ in range(20):
            responses.add(responses.GET, LISTING_URL, body=BLOCKED_HTML)

        with pytest.raises(_BlockedResponseError):
            fetch_all_listings_http({"limit": 100}, max_pages=5, rate_limit=0)
