import pytest
import os
import responses
from pathlib import Path
from unittest.mock import Mock, patch
from sgcarmart.core.downloader import download_pdf, process_dealer


@pytest.mark.integration
class TestAutoExtractionInDownloadPdf:
    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_download_pdf_with_auto_extract_enabled(
        self, mock_extractor_class, temp_output_dir, valid_pdf_content
    ):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = os.path.join(
            temp_output_dir, "mg", "2025", "mg_82_2025-01-15.json"
        )
        mock_extractor_class.return_value = mock_extractor

        result = download_pdf(
            url,
            brand_name="mg",
            output_dir=temp_output_dir,
            auto_extract=True,
            extract_model="gemini-2.0-flash-exp"
        )

        assert result["status"] == "success"
        assert result["extraction"] == "success"
        assert "json_path" in result
        assert "mg_82_2025-01-15.json" in result["json_path"]
        mock_extractor.extract_from_pdf.assert_called_once()

    @responses.activate
    def test_download_pdf_with_auto_extract_disabled(
        self, temp_output_dir, valid_pdf_content
    ):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        result = download_pdf(
            url,
            brand_name="mg",
            output_dir=temp_output_dir,
            auto_extract=False
        )

        assert result["status"] == "success"
        assert "extraction" not in result
        assert "json_path" not in result

    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_download_pdf_skips_extraction_when_json_exists(
        self, mock_extractor_class, temp_output_dir, valid_pdf_content
    ):
        brand_dir = os.path.join(temp_output_dir, "mg")
        year_dir = os.path.join(brand_dir, "2025")
        os.makedirs(year_dir, exist_ok=True)

        existing_pdf = os.path.join(year_dir, "dealer_82_2025-01-15.pdf")
        existing_json = os.path.join(year_dir, "mg_82_2025-01-15.json")

        with open(existing_pdf, 'wb') as f:
            f.write(valid_pdf_content)
        with open(existing_json, 'w') as f:
            f.write('{"test": "data"}')

        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"

        result = download_pdf(
            url,
            brand_name="mg",
            output_dir=temp_output_dir,
            auto_extract=True,
            extract_model="gemini-2.0-flash-exp"
        )

        assert result["status"] == "skipped"
        assert result["extraction"] == "skipped"
        assert "json_path" not in result
        mock_extractor_class.assert_not_called()

    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_download_pdf_handles_extraction_failure(
        self, mock_extractor_class, temp_output_dir, valid_pdf_content
    ):
        url = "https://www.sgcarmart.com/new_cars/pricelist/82/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        mock_extractor = Mock()
        mock_extractor.extract_from_pdf.side_effect = Exception("API Error: Rate limit exceeded")
        mock_extractor_class.return_value = mock_extractor

        result = download_pdf(
            url,
            brand_name="mg",
            output_dir=temp_output_dir,
            auto_extract=True,
            extract_model="gemini-2.0-flash-exp"
        )

        assert result["status"] == "success"
        assert result["extraction"] == "failed"
        assert "extraction_error" in result
        assert "API Error" in result["extraction_error"]
        assert os.path.exists(result["filepath"])

    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_download_pdf_uses_specified_model(
        self, mock_extractor_class, temp_output_dir, valid_pdf_content
    ):
        url = "https://www.sgcarmart.com/new_cars/pricelist/44/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = os.path.join(
            temp_output_dir, "toyota", "2025", "toyota_44_2025-01-15.json"
        )
        mock_extractor_class.return_value = mock_extractor

        result = download_pdf(
            url,
            brand_name="toyota",
            output_dir=temp_output_dir,
            auto_extract=True,
            extract_model="gemini-2.0-flash"
        )

        assert result["status"] == "success"
        assert result["extraction"] == "success"

        call_args = mock_extractor.extract_from_pdf.call_args
        assert call_args[1]["model"] == "gemini-2.0-flash"


@pytest.mark.integration
class TestAutoExtractionInProcessDealer:
    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    @patch('sgcarmart.core.downloader.os.path.exists')
    def test_process_dealer_with_auto_extract(
        self, mock_exists, mock_extractor_class, valid_pdf_content, sample_html_with_pdfs, temp_output_dir
    ):
        mock_exists.return_value = False

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

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = "data/pricelists/mg/2025/mg_82_2025-01-15.json"
        mock_extractor_class.return_value = mock_extractor

        result = process_dealer("82", "mg", auto_extract=True, extract_model="gemini-2.0-flash-exp")

        assert result["status"] == "success"
        assert result["brand"] == "mg"
        assert result["extraction"] == "success"
        assert "json_path" in result
        mock_extractor.extract_from_pdf.assert_called_once()

    @responses.activate
    @patch('sgcarmart.core.downloader.os.path.exists')
    def test_process_dealer_without_auto_extract(
        self, mock_exists, valid_pdf_content, sample_html_with_pdfs
    ):
        mock_exists.return_value = False

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

        result = process_dealer("82", "mg", auto_extract=False)

        assert result["status"] == "success"
        assert "extraction" not in result
        assert "json_path" not in result

    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    @patch('sgcarmart.core.downloader.os.path.exists')
    def test_process_dealer_extraction_failure_does_not_block_download(
        self, mock_exists, mock_extractor_class, valid_pdf_content, sample_html_with_pdfs
    ):
        mock_exists.return_value = False

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

        mock_extractor = Mock()
        mock_extractor.extract_from_pdf.side_effect = Exception("Network timeout")
        mock_extractor_class.return_value = mock_extractor

        result = process_dealer("82", "mg", auto_extract=True)

        assert result["status"] == "success"
        assert result["extraction"] == "failed"
        assert "extraction_error" in result
        assert "filepath" in result


@pytest.mark.integration
class TestExtractionWithDifferentBrands:
    @responses.activate
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_extraction_with_normalized_brand_names(
        self, mock_extractor_class, temp_output_dir, valid_pdf_content
    ):
        url = "https://www.sgcarmart.com/new_cars/pricelist/10/2025-01-15.pdf"
        responses.add(
            responses.GET,
            url,
            body=valid_pdf_content,
            headers={"content-type": "application/pdf"},
            status=200
        )

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = os.path.join(
            temp_output_dir, "mercedes-benz", "2025", "mercedes-benz_10_2025-01-15.json"
        )
        mock_extractor_class.return_value = mock_extractor

        result = download_pdf(
            url,
            brand_name="Mercedes-Benz",
            output_dir=temp_output_dir,
            auto_extract=True,
            extract_model="gemini-2.0-flash-exp"
        )

        assert result["status"] == "success"
        assert result["extraction"] == "success"
        assert "mercedes-benz" in result["json_path"].lower()
