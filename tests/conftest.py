import pytest
import os
from pathlib import Path


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
