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
    """Get all paths from SCRAPER_URL_PATTERNS in constants.py"""
    return generate_test_urls_from_patterns()


class TestRobotsCompliance:

    def test_robots_txt_accessible(self):
        """Verify robots.txt is accessible and not empty"""
        robots_url = f"{BASE_URL}/robots.txt"
        response = requests.get(robots_url, timeout=10)
        assert response.status_code == 200, "robots.txt should be accessible"
        assert len(response.text) > 0, "robots.txt should not be empty"

    def test_all_scraper_url_patterns_compliant(self, robot_parser, scraper_paths):
        """
        Verify all URL patterns from SCRAPER_URL_PATTERNS (constants.py:25-28)
        are allowed by robots.txt
        """
        violations = []

        for path in scraper_paths:
            url = f"{BASE_URL}{path}"
            if not robot_parser.can_fetch("*", url):
                violations.append(path)

        assert len(violations) == 0, \
            f"Found {len(violations)} paths violating robots.txt: {violations}"

    def test_scraper_url_patterns_defined(self):
        """Verify SCRAPER_URL_PATTERNS is properly defined in constants.py"""
        assert SCRAPER_URL_PATTERNS is not None, \
            "SCRAPER_URL_PATTERNS must be defined in constants.py"
        assert len(SCRAPER_URL_PATTERNS) > 0, \
            "SCRAPER_URL_PATTERNS must contain at least one pattern"
        assert isinstance(SCRAPER_URL_PATTERNS, list), \
            "SCRAPER_URL_PATTERNS must be a list"

    def test_each_pattern_individually(self, robot_parser):
        """Test each pattern from SCRAPER_URL_PATTERNS individually"""
        for pattern in SCRAPER_URL_PATTERNS:
            sample_url = pattern.format(
                dealer_id="82",
                brand="mg",
                date="2024-10-14"
            )
            full_url = f"{BASE_URL}{sample_url}"

            assert robot_parser.can_fetch("*", full_url), \
                f"Pattern '{pattern}' generated disallowed URL: {sample_url}"

    def test_compliance_rate_100_percent(self, robot_parser, scraper_paths):
        """Ensure 100% compliance rate for all generated paths"""
        allowed_count = sum(
            1 for path in scraper_paths
            if robot_parser.can_fetch("*", f"{BASE_URL}{path}")
        )

        total_count = len(scraper_paths)
        compliance_rate = (allowed_count / total_count) * 100 if total_count > 0 else 0

        assert compliance_rate == 100.0, \
            f"Compliance must be 100%, found: {compliance_rate:.1f}% " \
            f"({allowed_count}/{total_count} paths allowed)"

    def test_crawl_delay_requirement(self, robot_parser):
        """Verify crawl delay is specified and meets minimum requirement"""
        crawl_delay = robot_parser.crawl_delay("*")

        assert crawl_delay is not None, \
            "robots.txt must specify a crawl delay"

        assert crawl_delay >= 5, \
            f"Crawl delay must be at least 5 seconds, found: {crawl_delay}s"

    def test_crawl_delay_documented(self):
        """Verify Crawl-delay directive exists in robots.txt"""
        robots_url = f"{BASE_URL}/robots.txt"
        response = requests.get(robots_url, timeout=10)
        content = response.text.lower()

        assert "crawl-delay" in content, \
            "robots.txt must contain Crawl-delay directive"

    def test_patterns_match_actual_codebase_usage(self):
        """
        Verify SCRAPER_URL_PATTERNS matches actual URL construction in codebase.
        This test documents where each pattern is used.
        """
        expected_patterns = {
            "/new-cars/pricelists/{dealer_id}/{brand}": [
                "constants.py:22 (PRICELIST_URL_TEMPLATE)",
                "downloader.py:147",
                "year_navigator.py:71, 108"
            ],
            "/new_cars/pricelist/{dealer_id}/{date}.pdf": [
                "constants.py:23 (PDF_URL_TEMPLATE)",
                "year_navigator.py:159"
            ]
        }

        for pattern in SCRAPER_URL_PATTERNS:
            assert pattern in expected_patterns, \
                f"Pattern '{pattern}' should be documented in expected_patterns"

        for pattern in expected_patterns:
            assert pattern in SCRAPER_URL_PATTERNS, \
                f"Expected pattern '{pattern}' missing from SCRAPER_URL_PATTERNS"


class TestCrawlDelayCompliance:

    def test_crawl_delay_minimum_5_seconds(self, robot_parser):
        """Verify crawl delay meets minimum 5 second requirement"""
        crawl_delay = robot_parser.crawl_delay("*")

        assert crawl_delay is not None, \
            "robots.txt must specify a crawl delay"

        assert crawl_delay >= 5, \
            f"Minimum crawl delay is 5 seconds, found: {crawl_delay}s"

    def test_current_implementation_respects_crawl_delay(self):
        """
        Document that current implementation needs to respect crawl delay.
        This is tracked in TICKET-002.
        """
        pass
