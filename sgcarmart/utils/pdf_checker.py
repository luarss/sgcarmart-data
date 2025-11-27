import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)


class PDFCheckResult:
    def __init__(
        self,
        file_path,
        is_valid=True,
        error_type=None,
        error_message=None,
        page_count=None,
        has_text=None,
        is_encrypted=False,
    ):
        self.file_path = file_path
        self.is_valid = is_valid
        self.error_type = error_type
        self.error_message = error_message
        self.page_count = page_count
        self.has_text = has_text
        self.is_encrypted = is_encrypted

    def __repr__(self):
        status = "VALID" if self.is_valid else f"INVALID ({self.error_type})"
        return f"<PDFCheckResult {self.file_path}: {status}>"

    def to_dict(self):
        return {
            "file_path": str(self.file_path),
            "is_valid": self.is_valid,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "page_count": self.page_count,
            "has_text": self.has_text,
            "is_encrypted": self.is_encrypted,
        }


def check_pdf_corruption(pdf_path):
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return PDFCheckResult(
            pdf_path, is_valid=False, error_type="FILE_NOT_FOUND", error_message=f"File does not exist: {pdf_path}"
        )

    if pdf_path.stat().st_size == 0:
        return PDFCheckResult(
            pdf_path, is_valid=False, error_type="EMPTY_FILE", error_message="File is empty (0 bytes)"
        )

    try:
        reader = PdfReader(pdf_path)

        page_count = len(reader.pages)
        is_encrypted = reader.is_encrypted

        has_text = False
        if page_count > 0:
            try:
                first_page_text = reader.pages[0].extract_text()
                has_text = bool(first_page_text and first_page_text.strip())
            except Exception as e:
                logger.warning(f"Could not extract text from {pdf_path}: {e}")
                has_text = None

        return PDFCheckResult(
            pdf_path, is_valid=True, page_count=page_count, has_text=has_text, is_encrypted=is_encrypted
        )

    except PdfReadError as e:
        return PDFCheckResult(pdf_path, is_valid=False, error_type="PDF_READ_ERROR", error_message=str(e))
    except Exception as e:
        return PDFCheckResult(pdf_path, is_valid=False, error_type="UNKNOWN_ERROR", error_message=str(e))


def check_pdfs_in_directory(directory, pattern="**/*.pdf", recursive=True):
    directory = Path(directory)

    if not directory.exists():
        logger.error(f"Directory does not exist: {directory}")
        return []

    pdf_files = list(directory.glob(pattern))
    logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

    results = []
    for pdf_file in pdf_files:
        result = check_pdf_corruption(pdf_file)
        results.append(result)

    return results


def print_summary(results):
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    invalid = total - valid

    print(f"\n{'=' * 80}")
    print("PDF Corruption Check Summary")
    print(f"{'=' * 80}")
    print(f"Total PDFs checked: {total}")
    print(f"Valid PDFs: {valid} ({valid / total * 100:.1f}%)" if total > 0 else "Valid PDFs: 0")
    print(
        f"Invalid/Corrupted PDFs: {invalid} ({invalid / total * 100:.1f}%)"
        if total > 0
        else "Invalid/Corrupted PDFs: 0"
    )

    if invalid > 0:
        print(f"\n{'=' * 80}")
        print("Invalid PDFs Details:")
        print(f"{'=' * 80}")

        error_types = {}
        for result in results:
            if not result.is_valid:
                error_type = result.error_type or "UNKNOWN"
                if error_type not in error_types:
                    error_types[error_type] = []
                error_types[error_type].append(result)

        for error_type, error_results in error_types.items():
            print(f"\n{error_type} ({len(error_results)} files):")
            for result in error_results[:10]:
                print(f"  - {result.file_path}")
                if result.error_message:
                    print(f"    Error: {result.error_message[:100]}")

            if len(error_results) > 10:
                print(f"  ... and {len(error_results) - 10} more")

    encrypted = [r for r in results if r.is_valid and r.is_encrypted]
    if encrypted:
        print(f"\n{'=' * 80}")
        print(f"Encrypted PDFs: {len(encrypted)}")
        print(f"{'=' * 80}")
        for result in encrypted[:5]:
            print(f"  - {result.file_path}")
        if len(encrypted) > 5:
            print(f"  ... and {len(encrypted) - 5} more")

    no_text = [r for r in results if r.is_valid and r.has_text is False]
    if no_text:
        print(f"\n{'=' * 80}")
        print(f"PDFs with no extractable text: {len(no_text)}")
        print(f"{'=' * 80}")
        for result in no_text[:5]:
            print(f"  - {result.file_path} ({result.page_count} pages)")
        if len(no_text) > 5:
            print(f"  ... and {len(no_text) - 5} more")
