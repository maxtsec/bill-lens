"""Count actual ASGI bytes before multipart parsing, then cap the selected file."""

from typing import BinaryIO

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bill_lens.pdf_text import MAX_PDF_BYTES, PdfTextError

CHUNK_BYTES = 64 * 1024
MAX_REQUEST_BYTES = MAX_PDF_BYTES + 64 * 1024  # Multipart headers/boundaries too.


class UploadBodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        lengths = [value for key, value in scope["headers"] if key == b"content-length"]
        if lengths:
            value = lengths[0]
            if len(lengths) != 1 or not value.isdigit() or len(value) > 20:
                return await JSONResponse({"error": "invalid_request"}, 400)(scope, receive, send)
            if int(value) > MAX_REQUEST_BYTES:
                return await JSONResponse({"error": "file_too_large"}, 413)(scope, receive, send)
        total = 0

        async def capped_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > MAX_REQUEST_BYTES:
                    # Starlette closes multipart temp files when stream reading fails.
                    # FastAPI's HTTPException handler returns our stable JSON body.
                    raise HTTPException(413)
            return message

        await self.app(scope, capped_receive, send)


def read_pdf(stream: BinaryIO) -> bytes:
    data = bytearray()
    while chunk := stream.read(min(CHUNK_BYTES, MAX_PDF_BYTES + 1 - len(data))):
        data.extend(chunk)
        if len(data) > MAX_PDF_BYTES:
            raise PdfTextError("file_too_large")
    return bytes(data)
