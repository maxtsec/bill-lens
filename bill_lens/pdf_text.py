"""Extract inspectable page text; never interpret bill fields or repair content."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Literal
from zlib import error as ZlibError

import pdfplumber
from pdfminer.pdfexceptions import PDFException
from pdfminer.psparser import PSException
from pdfplumber.utils.exceptions import MalformedPDFException, PdfminerException

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT_CHARACTERS = 100_000

PdfErrorCode = Literal[
    "empty_file", "file_too_large", "invalid_pdf_signature", "unreadable_pdf",
    "encrypted_pdf", "no_pages", "too_many_pages", "page_without_text", "text_too_long",
]


class PdfTextError(ValueError):
    """Stable failure code, without document text or parser diagnostics in the message."""

    def __init__(self, code: PdfErrorCode, *, page_number: int | None = None):
        self.code = code
        self.page_number = page_number
        super().__init__(code)


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class PdfText:
    file_sha256: str
    pages: tuple[PageText, ...]

    @property
    def text(self) -> str:
        """Plain baseline text; page provenance remains available in pages."""
        return "\n\n".join(page.text for page in self.pages)


def extract_pdf_text(data: bytes) -> PdfText:
    """Read a complete PDF or raise PdfTextError; return no partial success.

    Limits bound accepted input/output, not parser CPU or peak memory. Future HTTP
    callers must enforce the byte limit while reading, before allocating all bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if not data:
        raise PdfTextError("empty_file")
    if len(data) > MAX_PDF_BYTES:
        raise PdfTextError("file_too_large")
    if not data.startswith(b"%PDF-"):
        raise PdfTextError("invalid_pdf_signature")

    pages = []
    characters = 0
    try:
        with BytesIO(data) as stream, pdfplumber.open(stream) as pdf:
            # PDFs that require a password fail at open as unreadable_pdf. Also
            # reject encryption that happens to allow opening with an empty password.
            if pdf.doc.encryption:
                raise PdfTextError("encrypted_pdf")
            if not pdf.pages:
                raise PdfTextError("no_pages")
            if len(pdf.pages) > MAX_PAGES:
                raise PdfTextError("too_many_pages")
            for page in pdf.pages:
                text = page.extract_text() or ""
                if not text.strip():
                    raise PdfTextError("page_without_text", page_number=page.page_number)
                characters += len(text) + (2 if pages else 0)
                if characters > MAX_TEXT_CHARACTERS:
                    raise PdfTextError("text_too_long", page_number=page.page_number)
                pages.append(PageText(page.page_number, text))
                page.close()
    except PdfTextError:
        raise
    except (PdfminerException, MalformedPDFException, PDFException,
            PSException, ValueError, ZlibError):
        # Do not return parser messages, which can contain document content.
        raise PdfTextError("unreadable_pdf") from None

    return PdfText(file_sha256=sha256(data).hexdigest(), pages=tuple(pages))
