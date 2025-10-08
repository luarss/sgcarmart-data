from constants import (
    MIN_PDF_SIZE_BYTES,
    PDF_MAGIC_HEADER,
    PDF_CONTENT_TYPE,
)


def is_valid_pdf_content(content, content_type=None):
    if content_type and PDF_CONTENT_TYPE not in content_type.lower():
        return False, f"Not a PDF file (content-type: {content_type})"

    if len(content) < MIN_PDF_SIZE_BYTES:
        return False, f"File too small ({len(content)} bytes)"

    if content[:4] != PDF_MAGIC_HEADER:
        return False, "Invalid PDF header"

    return True, "Valid PDF"


def validate_pdf(response):
    content_type = response.headers.get('content-type', '')
    return is_valid_pdf_content(response.content, content_type)
