import socket
from pathlib import Path

import pytest

from sgcarmart.utils import manifest as pdf_manifest

# ---------------------------------------------------------------------------
# Network isolation
#
# The default test run must be completely hermetic: no test may reach
# sgcarmart.com or any LLM provider. We enforce that by replacing the socket
# connect primitives with ones that raise, so a mock that silently stops
# matching production code fails loudly instead of quietly making live calls.
#
# Tests that genuinely need the network (live robots.txt / sitemap drift
# checks) opt in with @pytest.mark.network and only run under --run-network.
# ---------------------------------------------------------------------------

NETWORK_MARKER = "network"

_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

_real_socket_connect = socket.socket.connect
_real_socket_connect_ex = socket.socket.connect_ex
_real_create_connection = socket.create_connection


class NetworkAccessError(RuntimeError):
    """Raised when a test tries to open a real network connection."""


def _is_allowed_address(address):
    """Allow loopback and non-inet (e.g. AF_UNIX) sockets; block everything else."""
    if not isinstance(address, tuple) or not address:
        return True
    return str(address[0]) in _ALLOWED_HOSTS


def _blocked(address):
    return NetworkAccessError(
        f"Test attempted a real network connection to {address!r}. "
        "Tests must be hermetic - mock the boundary the production code actually calls, "
        "or mark the test with @pytest.mark.network and run with --run-network."
    )


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.network that make real network calls.",
    )


def pytest_configure(config):
    # Registered here (not in pyproject.toml) so --strict-markers stays happy.
    config.addinivalue_line(
        "markers",
        "network: test makes real network calls; skipped unless --run-network is passed",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip_network = pytest.mark.skip(reason="needs --run-network (makes real network calls)")
    for item in items:
        if item.get_closest_marker(NETWORK_MARKER):
            item.add_marker(skip_network)


@pytest.fixture(autouse=True)
def block_network(request):
    """Fail any test that opens a real socket, unless it is marked `network`."""
    if request.node.get_closest_marker(NETWORK_MARKER):
        yield
        return

    def guarded_connect(self, address):
        if _is_allowed_address(address):
            return _real_socket_connect(self, address)
        raise _blocked(address)

    def guarded_connect_ex(self, address):
        if _is_allowed_address(address):
            return _real_socket_connect_ex(self, address)
        raise _blocked(address)

    def guarded_create_connection(address, *args, **kwargs):
        if _is_allowed_address(address):
            return _real_create_connection(address, *args, **kwargs)
        raise _blocked(address)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    try:
        yield
    finally:
        socket.socket.connect = _real_socket_connect
        socket.socket.connect_ex = _real_socket_connect_ex
        socket.create_connection = _real_create_connection


@pytest.fixture(autouse=True)
def no_llm_api_keys(monkeypatch, request):
    """
    Strip provider credentials so an unmocked extractor fails fast and loudly
    instead of attempting a real LLM call with the developer's own keys.
    """
    if request.node.get_closest_marker(NETWORK_MARKER):
        return
    for key in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "XIAOMI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def no_crawl_delay(monkeypatch):
    """
    Neutralise the politeness delay (CRAWL_DELAY_SECONDS = 30) for the test run.

    `fetch_with_retry` sleeps up to 30s before *every* request, including fully
    mocked ones, and the last-request timestamp is process-global, so without
    this the suite stalls for minutes even though no packet leaves the machine.

    Tests that assert crawl-delay behaviour (tests/unit/test_http.py) re-patch
    the constant themselves inside the test body, which takes precedence.
    """
    import sgcarmart.utils.http as http_module

    monkeypatch.setattr(http_module, "CRAWL_DELAY_SECONDS", 0)
    monkeypatch.setattr(http_module, "_last_request_time", None)


@pytest.fixture(autouse=True)
def no_retry_backoff(monkeypatch):
    """
    Make tenacity's exponential backoff instantaneous.

    The 429 retry tests assert *how many* attempts happen, not how long they
    wait; without this each of them burns 15s of real sleeping in CI.
    """
    from sgcarmart.utils.http import fetch_with_retry

    monkeypatch.setattr(fetch_with_retry.retry, "sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def reset_manifest():
    pdf_manifest._manifest.clear()
    yield
    pdf_manifest._manifest.clear()


@pytest.fixture
def sample_dealer_mapping():
    return {
        "1": "alfa-romeo",
        "82": "mg",
        "44": "toyota",
        "4": "bmw"
    }


@pytest.fixture
def sample_html_with_pdfs():
    return """
    <html>
        <div class="styles_containerDatesContent__nOueF">
            <a class="styles_textPricelistLink__UvFUj" href="/new_cars/pricelist/82/2025-01-15.pdf">2025-01-15</a>
            <a class="styles_textPricelistLink__UvFUj" href="/new_cars/pricelist/82/2025-01-10.pdf">2025-01-10</a>
            <a class="styles_textPricelistLink__UvFUj" href="/new_cars/pricelist/82/2024-12-20.pdf">2024-12-20</a>
        </div>
    </html>
    """


@pytest.fixture
def sample_html_no_pdfs():
    return """
    <html>
        <div class="styles_containerDatesContent__nOueF">
            <p>No pricelists available</p>
        </div>
    </html>
    """


@pytest.fixture
def valid_pdf_content():
    return b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n' + b'0' * 2000


@pytest.fixture
def invalid_pdf_content():
    return b'<html>Not a PDF</html>'


@pytest.fixture
def temp_output_dir(tmp_path):
    output_dir = tmp_path / "test_pricelists"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"
