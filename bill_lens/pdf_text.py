"""Extract inspectable page text; never interpret bill fields or repair content."""

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Literal

import pdfplumber

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT_CHARACTERS = 100_000

PdfErrorCode = Literal[
    "empty_file", "file_too_large", "invalid_pdf_signature", "unreadable_pdf",
    "encrypted_pdf", "no_pages", "too_many_pages", "page_without_text", "text_too_long",
]


class PdfTextError(ValueError):
    """Stable failure code, without document text or parser diagnostics in the message."""

    def __init__(
        self, code: PdfErrorCode, *, page_number: int | None = None,
        parser_error: str | None = None,
    ):
        self.code = code
        self.page_number = page_number
        self.parser_error = parser_error
        super().__init__(code)


def _parser_call[T](operation: Callable[[], T]) -> T:
    """Translate exceptions only around a parser operation, not application logic."""
    try:
        return operation()
    except Exception as error:
        error_type = type(error).__name__
    # Outside the handler: do not retain the parser exception as __context__.
    raise PdfTextError("unreadable_pdf", parser_error=error_type)


def _close_parser(pdf: pdfplumber.PDF) -> str | None:
    """Capture cleanup failure without replacing an already active failure."""
    try:
        pdf.close()
    except Exception as error:
        return type(error).__name__
    return None


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
    with BytesIO(data) as stream:
        pdf = _parser_call(lambda: pdfplumber.open(stream))
        try:
            # PDFs that require a password fail at open as unreadable_pdf. Also
            # reject encryption that happens to allow opening with an empty password.
            if _parser_call(lambda: bool(pdf.doc.encryption)):
                raise PdfTextError("encrypted_pdf")
            source_pages = _parser_call(lambda: pdf.pages)
            if not source_pages:
                raise PdfTextError("no_pages")
            if len(source_pages) > MAX_PAGES:
                raise PdfTextError("too_many_pages")
            for page_number, page in enumerate(source_pages, start=1):
                text = _parser_call(lambda: page.extract_text()) or ""
                if not text.strip():
                    raise PdfTextError("page_without_text", page_number=page_number)
                characters += len(text) + (2 if pages else 0)
                if characters > MAX_TEXT_CHARACTERS:
                    raise PdfTextError("text_too_long", page_number=page_number)
                pages.append(PageText(page_number, text))
                _parser_call(lambda: page.close())
        finally:
            close_error = _close_parser(pdf)
        # Reached only if parsing and application checks succeeded. Otherwise the
        # original failure propagates, even when cleanup also fails.
        if close_error:
            raise PdfTextError("unreadable_pdf", parser_error=close_error)

    return PdfText(file_sha256=sha256(data).hexdigest(), pages=tuple(pages))
