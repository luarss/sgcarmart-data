import pytest
import requests
from urllib.robotparser import RobotFileParser
from constants import BASE_URL, SCRAPER_URL_PATTERNS


def generate_test_urls_from_patterns():
    """
    Generate test URLs from SCRAPER_URL_PATTERNS defined in constants.py.
    This is the single source of truth for all URL patterns our scraper uses.
    """
    test_cases = []

    test_data = {
        "dealer_id": ["1", "4", "44", "82"],
        "brand": ["mg", "toyota", "bmw", "alfa-romeo"],
        "date": ["2024-01-01", "2024-06-15", "2024-12-31", "2025-01-15"],
    }

    for pattern in SCRAPER_URL_PATTERNS:
        placeholders = []
        if "{dealer_id}" in pattern:
            placeholders.append("dealer_id")
        if "{brand}" in pattern:
            placeholders.append("brand")
        if "{date}" in pattern:
            placeholders.append("date")

        for dealer_id in test_data["dealer_id"]:
            params = {"dealer_id": dealer_id}

            if "brand" in placeholders:
                for brand in test_data["brand"]:
                    params["brand"] = brand
                    test_cases.append(pattern.format(**params))
            elif "date" in placeholders:
                for date in test_data["date"]:
                    params["date"] = date
                    test_cases.append(pattern.format(**params))
            else:
                test_cases.append(pattern.format(**params))

    return list(set(test_cases))


@pytest.fixture(scope="module")
def robot_parser():
    """Fetch and parse the live robots.txt from SGCarMart"""
    robots_url = f"{BASE_URL}/robots.txt"
    response = requests.get(robots_url, timeout=10)
    response.raise_for_status()

    rp = RobotFileParser()
    rp.parse(response.text.splitlines())
    return rp


@pytest.fixture
def scraper_paths():
    return generate_test_urls_from_patterns()


class TestRobotsCompliance:

    def test_all_scraper_url_patterns_compliant(self, robot_parser, scraper_paths):
        violations = []

        for path in scraper_paths:
            url = f"{BASE_URL}{path}"
            if not robot_parser.can_fetch("*", url):
                violations.append(path)

        assert len(violations) == 0, \
            f"Found {len(violations)} paths violating robots.txt: {violations}"

    def test_crawl_delay_implementation(self):
        pytest.skip("TODO: Implement crawl delay enforcement (TICKET-002)")
