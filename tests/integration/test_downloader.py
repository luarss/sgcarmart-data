import pytest
import os
import responses
from unittest.mock import patch, mock_open
from sgcarmart.core.downloader import (
    download_pricelist,
    download_pdf,
    process_dealer,
)


@pytest.mark.integration
class TestDownloadPricelist:
    @responses.activate
    def test_download_new_pricelist(self, temp_output_dir, valid_pdf_content):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        filepath, message = download_pricelist(url, "mg", "82", "2025-01-15", temp_output_dir)

        assert filepath is not None
        assert os.path.exists(filepath)
        assert "Downloaded" in message
        assert os.path.getsize(filepath) == len(valid_pdf_content)

    @responses.activate
    def test_download_creates_brand_directory(self, temp_output_dir, valid_pdf_content):
        url = "https://www.sgcarmart.com/new_cars/pricelist/44/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        filepath, message = download_pricelist(url, "toyota", "44", "2025-01-15", temp_output_dir)

        brand_dir = os.path.join(temp_output_dir, "toyota")
        assert os.path.exists(brand_dir)
        assert os.path.isdir(brand_dir)

    def test_skip_existing_file(self, temp_output_dir):
        brand_dir = os.path.join(temp_output_dir, "bmw")
        year_dir = os.path.join(brand_dir, "2025")
        os.makedirs(year_dir, exist_ok=True)

        existing_file = os.path.join(year_dir, "dealer_4_2025-01-15.pdf")
        with open(existing_file, 'wb') as f:
            f.write(b'%PDF-existing')

        url = "https://www.sgcarmart.com/new_cars/pricelist/4/2025-01-15.pdf"
        filepath, message = download_pricelist(url, "bmw", "4", "2025-01-15", temp_output_dir)

        assert filepath == existing_file
        assert "Already exists" in message

    @responses.activate
    def test_download_invalid_content_type(self, temp_output_dir):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body="<html>Not a PDF</html>",
            headers={"content-type": "text/html"},
            status=200
        )

        filepath, message = download_pricelist(url, "mg", "82", "2025-01-15", temp_output_dir)

        assert filepath is None
        assert "Not a PDF file" in message

    @responses.activate
    def test_download_too_small_file(self, temp_output_dir):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=b'%PDF-small',
            headers={"content-type": "application/pdf"},
            status=200
        )

        filepath, message = download_pricelist(url, "mg", "82", "2025-01-15", temp_output_dir)

        assert filepath is None
        assert "File too small" in message


@pytest.mark.integration
class TestDownloadPdf:
    @responses.activate
    def test_download_pdf_with_metadata(self, temp_output_dir, valid_pdf_content):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        result = download_pdf(url, "mg", temp_output_dir)

        assert result["status"] == "success"
        assert result["dealer_id"] == "82"
        assert result["date"] == "2025-01-15"
        assert os.path.exists(result["filepath"])

    @responses.activate
    def test_download_pdf_skips_existing(self, temp_output_dir, valid_pdf_content):
        brand_dir = os.path.join(temp_output_dir, "mg")
        year_dir = os.path.join(brand_dir, "2025")
        os.makedirs(year_dir, exist_ok=True)

        existing_file = os.path.join(year_dir, "dealer_82_2025-01-15.pdf")
        with open(existing_file, 'wb') as f:
            f.write(valid_pdf_content)

        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        result = download_pdf(url, "mg", temp_output_dir)

        assert result["status"] == "skipped"
        assert "Already exists" in result["message"]

    @responses.activate
    def test_download_pdf_handles_errors(self, temp_output_dir):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(responses.GET, url, status=404)

        result = download_pdf(url, "mg", temp_output_dir)

        assert result["status"] == "error"
        assert result["filepath"] is None


@pytest.mark.integration
class TestProcessDealer:
    @responses.activate
    def test_process_dealer_success(self, valid_pdf_content, sample_html_with_pdfs):
        dealer_url = "https://www.sgcarmart.com/new-cars/pricelists/82/mg"
        pdf_url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"

        responses.add(responses.GET, dealer_url, body=sample_html_with_pdfs, status=200)
        responses.add(
            responses.GET,
            pdf_url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        result = process_dealer("82", "mg")

        assert result["status"] == "success"
        assert result["dealer_id"] == "82"
        assert result["brand"] == "mg"
        assert "filepath" in result

    @responses.activate
    def test_process_dealer_no_pdfs(self, sample_html_no_pdfs):
        dealer_url = "https://www.sgcarmart.com/new-cars/pricelists/82/mg"
        responses.add(responses.GET, dealer_url, body=sample_html_no_pdfs, status=200)

        result = process_dealer("82", "mg")

        assert result["status"] == "not_found"
        assert result["dealer_id"] == "82"
        assert result["brand"] == "mg"

    @responses.activate
    def test_process_dealer_http_error(self):
        dealer_url = "https://www.sgcarmart.com/new-cars/pricelists/82/mg"
        responses.add(responses.GET, dealer_url, status=500)

        result = process_dealer("82", "mg")

        assert result["status"] == "error"
        assert "error" in result
