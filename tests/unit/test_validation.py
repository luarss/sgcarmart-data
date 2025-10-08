import pytest
from unittest.mock import Mock
from sgcarmart.utils.validation import (
    is_valid_pdf_content,
    validate_pdf,
)


@pytest.mark.unit
class TestIsValidPdfContent:
    def test_valid_pdf_with_correct_header(self, valid_pdf_content):
        is_valid, message = is_valid_pdf_content(valid_pdf_content, "application/pdf")

        assert is_valid is True
        assert message == "Valid PDF"

    def test_invalid_content_type(self, valid_pdf_content):
        is_valid, message = is_valid_pdf_content(valid_pdf_content, "text/html")

        assert is_valid is False
        assert "Not a PDF file" in message
        assert "text/html" in message

    def test_content_too_small(self):
        small_content = b'%PDF-1.4\n'
        is_valid, message = is_valid_pdf_content(small_content, "application/pdf")

        assert is_valid is False
        assert "File too small" in message

    def test_invalid_pdf_header(self):
        invalid_content = b'<html>Not a PDF</html>' + b'0' * 2000
        is_valid, message = is_valid_pdf_content(invalid_content, "application/pdf")

        assert is_valid is False
        assert "Invalid PDF header" in message

    def test_no_content_type_provided(self, valid_pdf_content):
        is_valid, message = is_valid_pdf_content(valid_pdf_content, None)

        assert is_valid is True
        assert message == "Valid PDF"

    def test_content_type_case_insensitive(self, valid_pdf_content):
        is_valid, message = is_valid_pdf_content(valid_pdf_content, "APPLICATION/PDF")

        assert is_valid is True

    def test_content_type_with_charset(self, valid_pdf_content):
        is_valid, message = is_valid_pdf_content(valid_pdf_content, "application/pdf; charset=utf-8")

        assert is_valid is True


@pytest.mark.unit
class TestValidatePdf:
    def test_validate_valid_response(self, valid_pdf_content):
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf'}
        mock_response.content = valid_pdf_content

        is_valid, message = validate_pdf(mock_response)

        assert is_valid is True
        assert message == "Valid PDF"

    def test_validate_invalid_response(self, invalid_pdf_content):
        mock_response = Mock()
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.content = invalid_pdf_content

        is_valid, message = validate_pdf(mock_response)

        assert is_valid is False
        assert "Not a PDF file" in message

    def test_validate_response_without_content_type(self, valid_pdf_content):
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.content = valid_pdf_content

        is_valid, message = validate_pdf(mock_response)

        assert is_valid is True

    def test_validate_small_pdf(self):
        mock_response = Mock()
        mock_response.headers = {'content-type': 'application/pdf'}
        mock_response.content = b'%PDF-1.4\n'

        is_valid, message = validate_pdf(mock_response)

        assert is_valid is False
        assert "File too small" in message
