"""Extract per-page text from an uploaded PDF with pypdf.

Only the text layer is read: scanned (image-only) reports yield no text and are reported as
such; there is no OCR. The PDF itself is not stored, only its SHA-256 and extracted text.
"""

import hashlib
import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"


class PdfError(Exception):
    """The upload is not a readable PDF (or exceeds limits)."""


@dataclass(frozen=True)
class ExtractedPdf:
    sha256: str
    page_count: int
    pages: list[str]  # index 0 = page 1; empty string when a page has no text layer


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes, *, max_pages: int) -> ExtractedPdf:
    if not data.startswith(PDF_MAGIC):
        raise PdfError("file is not a PDF")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfError("encrypted PDFs are not supported")
        page_count = len(reader.pages)
        if page_count == 0:
            raise PdfError("PDF has no pages")
        if page_count > max_pages:
            raise PdfError(f"PDF has {page_count} pages; the limit is {max_pages}")
        pages = [_clean(page.extract_text() or "") for page in reader.pages]
    except PdfError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise PdfError("PDF could not be read") from exc
    return ExtractedPdf(hashlib.sha256(data).hexdigest(), page_count, pages)
