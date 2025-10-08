import pytest
import os
import responses
from sgcarmart.core.downloader import download_all_pdfs_from_page
from constants import BASE_URL


@pytest.mark.integration
class TestDownloadAllPdfsFromPage:
    @responses.activate
    def test_download_all_pdfs_with_brand(self, temp_output_dir, valid_pdf_content, sample_html_with_pdfs):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, body=sample_html_with_pdfs, status=200)

        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-15.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-10.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2024-12-20.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        results = download_all_pdfs_from_page(page_url, "mg", temp_output_dir, max_workers=2)

        assert len(results) == 3
        assert all(r["status"] == "success" for r in results)
        assert all(r["dealer_id"] == "82" for r in results)

    @responses.activate
    def test_download_all_pdfs_auto_detect_brand(self, temp_output_dir, valid_pdf_content, sample_html_with_pdfs):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, body=sample_html_with_pdfs, status=200)

        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-15.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-10.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2024-12-20.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        results = download_all_pdfs_from_page(page_url, None, temp_output_dir)

        assert len(results) == 3

    @responses.activate
    def test_download_all_pdfs_no_pdfs_found(self, temp_output_dir, sample_html_no_pdfs):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, body=sample_html_no_pdfs, status=200)

        results = download_all_pdfs_from_page(page_url, "mg", temp_output_dir)

        assert len(results) == 0

    @responses.activate
    def test_download_all_pdfs_page_error(self, temp_output_dir):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, status=500)

        results = download_all_pdfs_from_page(page_url, "mg", temp_output_dir)

        assert len(results) == 0

    @responses.activate
    def test_download_all_pdfs_rate_limited(self, temp_output_dir):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, status=429)
        responses.add(responses.GET, page_url, status=429)
        responses.add(responses.GET, page_url, status=429)

        results = download_all_pdfs_from_page(page_url, "mg", temp_output_dir)

        assert len(results) == 0

    @responses.activate
    def test_download_all_pdfs_mixed_results(self, temp_output_dir, valid_pdf_content, sample_html_with_pdfs):
        page_url = f"{BASE_URL}/new-cars/pricelists/82/mg"

        responses.add(responses.GET, page_url, body=sample_html_with_pdfs, status=200)

        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-15.pdf",
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2025-01-10.pdf",
            status=404
        )
        responses.add(
            responses.GET,
            f"{BASE_URL}/new_cars/pricelist/82/2024-12-20.pdf",
            body=b"not a pdf",
            headers={"content-type": "text/html"},
            status=200
        )

        results = download_all_pdfs_from_page(page_url, "mg", temp_output_dir)

        assert len(results) == 3
        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] in ["error", "failed"])

        assert success_count == 1
        assert error_count == 2
