from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest
import requests

from sgcarmart.constants import BASE_URL, SCRAPER_URL_PATTERNS

# Recorded copy of https://www.sgcarmart.com/robots.txt.
# The default run checks compliance against this snapshot so the suite stays
# hermetic; `pytest --run-network` re-checks against the live file and tells us
# when the snapshot has drifted.
RECORDED_ROBOTS_TXT = Path(__file__).parent.parent / "fixtures" / "sgcarmart_robots.txt"


def _generate_urls_for_pattern(pattern, test_data):
    """Generate all test URLs for a single URL pattern."""
    cases = []
    placeholders = [p for p in ["dealer_id", "brand", "date"] if f"{{{p}}}" in pattern]

    for dealer_id in test_data["dealer_id"]:
        params = {"dealer_id": dealer_id}

        if "brand" in placeholders:
            for brand in test_data["brand"]:
                params["brand"] = brand
                cases.append(pattern.format(**params))
        elif "date" in placeholders:
            for date in test_data["date"]:
                params["date"] = date
                cases.append(pattern.format(**params))
        else:
            cases.append(pattern.format(**params))

    return cases


def generate_test_urls_from_patterns():
    """
    Generate test URLs from SCRAPER_URL_PATTERNS defined in constants.py.
    This is the single source of truth for all URL patterns our scraper uses.
    """
    test_data = {
        "dealer_id": ["1", "4", "44", "82"],
        "brand": ["mg", "toyota", "bmw", "alfa-romeo"],
        "date": ["2024-01-01", "2024-06-15", "2024-12-31", "2025-01-15"],
    }

    test_cases = []
    for pattern in SCRAPER_URL_PATTERNS:
        test_cases.extend(_generate_urls_for_pattern(pattern, test_data))

    return list(set(test_cases))


def _merge_wildcard_groups(robots_text):
    """Collapse every `User-agent: *` group into one.

    SGCarMart's robots.txt declares `User-agent: *` twice with different rules.
    urllib's RobotFileParser keeps only the first such group, which would let us
    pass compliance while ignoring half the site's wildcard restrictions. Merging
    them makes the check strictly stricter, matching how real crawlers behave.
    """
    merged = []
    other = []
    in_wildcard_group = False

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()

        if field == "user-agent":
            in_wildcard_group = value == "*"
            if not in_wildcard_group:
                other.append(f"User-agent: {value}")
            continue

        (merged if in_wildcard_group else other).append(f"{field}: {value}")

    return "\n".join(["User-agent: *", *merged, "", *other])


def _parser_for(robots_text):
    rp = RobotFileParser()
    rp.parse(_merge_wildcard_groups(robots_text).splitlines())
    return rp


def _find_violations(robot_parser, paths):
    return [path for path in paths if not robot_parser.can_fetch("*", f"{BASE_URL}{path}")]


@pytest.fixture(scope="module")
def recorded_robots_text():
    return RECORDED_ROBOTS_TXT.read_text()


@pytest.fixture
def robot_parser(recorded_robots_text):
    """Parse the recorded robots.txt snapshot. No network access."""
    return _parser_for(recorded_robots_text)


@pytest.fixture
def scraper_paths():
    return generate_test_urls_from_patterns()


class TestRobotsCompliance:

    def test_recorded_robots_snapshot_is_present_and_parseable(self, robot_parser):
        """Guards against the snapshot being emptied, truncated or mis-parsed,
        which would make the compliance assertions below vacuously pass."""
        assert RECORDED_ROBOTS_TXT.exists()
        # Paths the merged wildcard rules explicitly disallow - proves rules loaded.
        assert not robot_parser.can_fetch("*", f"{BASE_URL}/used-cars/api")
        assert not robot_parser.can_fetch("*", f"{BASE_URL}/dealer/anything")
        # A non-wildcard group, proving the whole file (not just the first group) parsed.
        assert not robot_parser.can_fetch("ia_archiver", f"{BASE_URL}/")
        assert robot_parser.crawl_delay("*") is not None

    def test_all_scraper_url_patterns_compliant(self, robot_parser, scraper_paths):
        assert scraper_paths, "No scraper URL patterns generated"
        violations = _find_violations(robot_parser, scraper_paths)

        assert len(violations) == 0, \
            f"Found {len(violations)} paths violating robots.txt: {violations}"

    @pytest.mark.network
    def test_live_robots_txt_matches_recorded_snapshot(self, recorded_robots_text, scraper_paths):
        """Opt-in (`pytest --run-network`): re-check against the live robots.txt.

        Fails if SGCarMart tightened its rules against our URL patterns, and
        warns if the recorded snapshot has drifted and should be re-recorded.
        """
        response = requests.get(f"{BASE_URL}/robots.txt", timeout=10)
        response.raise_for_status()

        violations = _find_violations(_parser_for(response.text), scraper_paths)
        assert len(violations) == 0, \
            f"Live robots.txt now disallows {len(violations)} scraper paths: {violations}"

        assert response.text.strip() == recorded_robots_text.strip(), (
            f"Live robots.txt differs from the recorded snapshot. Re-record it:\n"
            f"  curl -sS {BASE_URL}/robots.txt -o {RECORDED_ROBOTS_TXT}"
        )

    def test_crawl_delay_implementation(self):
        pytest.skip("TODO: Implement crawl delay enforcement (TICKET-002)")
