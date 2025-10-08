import pytest
import responses
from requests.exceptions import HTTPError, Timeout
from sgcarmart.utils.http import (
    get_random_user_agent,
    fetch_with_retry,
    RateLimitException,
)
from constants import USER_AGENTS


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
class TestFetchWithRetry:
    @responses.activate
    def test_successful_request(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, body="Success", status=200)

        response = fetch_with_retry(url, timeout=10)

        assert response.status_code == 200
        assert response.text == "Success"

    @responses.activate
    def test_rate_limit_raises_exception(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=429)

        with pytest.raises(RateLimitException):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    def test_404_raises_http_error(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=404)

        with pytest.raises(HTTPError):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    def test_500_raises_http_error(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=500)

        with pytest.raises(HTTPError):
            fetch_with_retry(url, timeout=10)

    @responses.activate
    def test_sets_user_agent_header(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, body="Success", status=200)

        response = fetch_with_retry(url, timeout=10)

        assert "User-Agent" in response.request.headers
        assert response.request.headers["User-Agent"] in USER_AGENTS

    @responses.activate
    def test_retry_on_429(self):
        url = "https://example.com/test"
        responses.add(responses.GET, url, status=429)
        responses.add(responses.GET, url, status=429)
        responses.add(responses.GET, url, status=429)

        with pytest.raises(RateLimitException):
            fetch_with_retry(url, timeout=10)

        assert len(responses.calls) == 3
