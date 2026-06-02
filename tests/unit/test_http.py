import pytest
import responses
import time
from unittest.mock import patch
from requests.exceptions import HTTPError
from sgcarmart.utils.http import (
    get_random_user_agent,
    fetch_with_retry,
    apply_crawl_delay,
    RateLimitError,
)
from sgcarmart.constants import USER_AGENTS


@pytest.fixture(autouse=True)
def reset_crawl_delay_state():
    import sgcarmart.utils.http as http_module
    http_module._last_request_time = None
    yield
    http_module._last_request_time = None


@pytest.mark.unit
class TestGetRandomUserAgent:
    def test_returns_user_agent(self):
        user_agent = get_random_user_agent()

        assert user_agent in USER_AGENTS
        assert isinstance(user_agent, str)
        assert len(user_agent) > 0

    def test_returns_different_agents(self):
        agents = [get_random_user_agent() for _ in range(100)]

        assert len(set(agents)) > 1


@pytest.mark.unit
class TestApplyCrawlDelay:
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_first_request_no_delay(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = None

        start_time = time.time()
        apply_crawl_delay()
        elapsed = time.time() - start_time

        assert elapsed < 0.05
        assert http_module._last_request_time is not None

    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_second_request_applies_delay(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = time.time()

        start_time = time.time()
        apply_crawl_delay()
        elapsed = time.time() - start_time

        assert elapsed >= 0.08
        assert elapsed <= 0.2

    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_subsequent_requests_respect_delay(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = None

        times = []
        for _ in range(3):
            apply_crawl_delay()
            times.append(time.time())

        for i in range(1, len(times)):
            delay = times[i] - times[i-1]
            assert delay >= 0.08
            assert delay <= 0.3

    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_delay_not_applied_if_time_already_passed(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = time.time() - 0.2

        start_time = time.time()
        apply_crawl_delay()
        elapsed = time.time() - start_time

        assert elapsed < 0.05


@pytest.mark.unit
class TestFetchWithRetry:
    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_successful_request(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, body="Success", status=200)

        response = fetch_with_retry(url, timeout=10)

        assert response.status_code == 200
        assert response.text == "Success"

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_rate_limit_raises_exception(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=429)

        with pytest.raises(RateLimitError):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_404_raises_http_error(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=404)

        with pytest.raises(HTTPError):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_500_raises_http_error(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=500)

        with pytest.raises(HTTPError):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_sets_user_agent_header(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, body="Success", status=200)

        response = fetch_with_retry(url, timeout=10)

        assert "User-Agent" in response.request.headers
        assert response.request.headers["User-Agent"] in USER_AGENTS

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.01)
    def test_retry_on_429(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=429)
        responses.add(responses.GET, url, status=429)
        responses.add(responses.GET, url, status=429)

        with pytest.raises(RateLimitError):
            fetch_with_retry(url, timeout=10)

        assert len(responses.calls) == 3

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_fetch_applies_crawl_delay(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = None

        url = "https://example.com/test"
        responses.add(responses.GET, url, body="Success", status=200)
        responses.add(responses.GET, url, body="Success", status=200)

        start_time = time.time()
        fetch_with_retry(url, timeout=10)
        first_request_time = time.time() - start_time

        fetch_with_retry(url, timeout=10)
        total_time = time.time() - start_time

        assert first_request_time < 0.2
        assert total_time >= 0.1

    @responses.activate
    @patch('sgcarmart.utils.http.CRAWL_DELAY_SECONDS', 0.1)
    def test_multiple_requests_respect_crawl_delay(self):
        import sgcarmart.utils.http as http_module
        http_module._last_request_time = None

        url = "https://example.com/test"
        for _ in range(3):
            responses.add(responses.GET, url, body="Success", status=200)

        start_time = time.time()
        for _ in range(3):
            fetch_with_retry(url, timeout=10)
        total_time = time.time() - start_time

        expected_min_time = 0.2
        assert total_time >= expected_min_time
