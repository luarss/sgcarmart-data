import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from sgcarmart.core.downloader import _attempt_extraction, _setup_filepath


class TestSetupFilepath:
    def test_setup_filepath_basic(self, temp_output_dir):
        filepath, filename = _setup_filepath("Toyota", "44", "2025-01-15", temp_output_dir)

        assert filename == "dealer_44_2025-01-15.pdf"
        assert "toyota" in filepath
        assert "2025" in filepath
        assert filepath.endswith("dealer_44_2025-01-15.pdf")

    def test_setup_filepath_normalizes_brand(self, temp_output_dir):
        filepath, filename = _setup_filepath("Mercedes-Benz", "10", "2024-12-01", temp_output_dir)

        assert "mercedes-benz" in filepath
        assert "2024" in filepath

    def test_setup_filepath_creates_directories(self, temp_output_dir):
        filepath, filename = _setup_filepath("BMW", "4", "2025-01-15", temp_output_dir)

        brand_dir = Path(temp_output_dir) / "bmw"
        year_dir = brand_dir / "2025"

        assert brand_dir.exists()
        assert year_dir.exists()

    def test_setup_filepath_extracts_year_from_date(self, temp_output_dir):
        filepath, _ = _setup_filepath("Toyota", "44", "2023-06-15", temp_output_dir)
        assert "2023" in filepath

        filepath, _ = _setup_filepath("Toyota", "44", "20240101", temp_output_dir)
        assert "2024" in filepath


@pytest.mark.unit
class TestAttemptExtraction:
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_extraction_success(self, mock_extractor_class, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "toyota" / "2025" / "dealer_44_2025-01-15.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'%PDF-1.4\n')

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = str(pdf_path.parent / "toyota_44_2025-01-15.json")
        mock_extractor_class.return_value = mock_extractor

        status, output_path = _attempt_extraction(
            str(pdf_path), "Toyota", "44", "2025-01-15", "gemini-2.5-flash"
        )

        assert status == "success"
        assert output_path is not None
        assert "toyota_44_2025-01-15.json" in output_path
        mock_extractor.extract_from_pdf.assert_called_once()
        mock_extractor.save_extraction.assert_called_once()

    def test_extraction_skipped_when_json_exists(self, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "toyota" / "2025" / "dealer_44_2025-01-15.pdf"
        json_path = pdf_path.parent / "toyota_44_2025-01-15.json"

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'%PDF-1.4\n')
        json_path.write_text('{"test": "data"}')

        status, output_path = _attempt_extraction(
            str(pdf_path), "Toyota", "44", "2025-01-15", "gemini-2.5-flash"
        )

        assert status == "skipped"
        assert output_path is None

    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_extraction_with_different_models(self, mock_extractor_class, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "bmw" / "2025" / "dealer_4_2025-01-15.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'%PDF-1.4\n')

        mock_extractor = Mock()
        mock_extraction = Mock()
        mock_extractor.extract_from_pdf.return_value = mock_extraction
        mock_extractor.save_extraction.return_value = str(pdf_path.parent / "bmw_4_2025-01-15.json")
        mock_extractor_class.return_value = mock_extractor

        status, output_path = _attempt_extraction(
            str(pdf_path), "BMW", "4", "2025-01-15", "gemini-2.5-flash"
        )

        assert status == "success"
        mock_extractor.extract_from_pdf.assert_called_once_with(
            pdf_path, model="gemini-2.5-flash"
        )

    def test_extraction_normalizes_brand_name(self, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "mercedes-benz" / "2025" / "dealer_10_2025-01-15.pdf"
        json_path = pdf_path.parent / "mercedes-benz_10_2025-01-15.json"

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'%PDF-1.4\n')
        json_path.write_text('{"test": "data"}')

        status, output_path = _attempt_extraction(
            str(pdf_path), "Mercedes-Benz", "10", "2025-01-15", "gemini-2.5-flash"
        )

        assert status == "skipped"
        assert json_path.exists()


@pytest.mark.unit
class TestExtractionErrorHandling:
    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_extraction_handles_api_error(self, mock_extractor_class, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "toyota" / "2025" / "dealer_44_2025-01-15.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'%PDF-1.4\n')

        mock_extractor = Mock()
        mock_extractor.extract_from_pdf.side_effect = Exception("API timeout")
        mock_extractor_class.return_value = mock_extractor

        with pytest.raises(Exception, match="API timeout"):
            _attempt_extraction(
                str(pdf_path), "Toyota", "44", "2025-01-15", "gemini-2.5-flash"
            )

    @patch('analysis.pdf_extractor.GeminiPDFExtractor')
    def test_extraction_handles_invalid_pdf(self, mock_extractor_class, temp_output_dir):
        pdf_path = Path(temp_output_dir) / "toyota" / "2025" / "dealer_44_2025-01-15.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b'Invalid PDF content')

        mock_extractor = Mock()
        mock_extractor.extract_from_pdf.side_effect = ValueError("Invalid PDF format")
        mock_extractor_class.return_value = mock_extractor

        with pytest.raises(ValueError, match="Invalid PDF format"):
            _attempt_extraction(
                str(pdf_path), "Toyota", "44", "2025-01-15", "gemini-2.5-flash"
            )
