import asyncio
from io import BytesIO

import pytest
from starlette.exceptions import HTTPException

from bill_lens.api import limits
from bill_lens.pdf_text import PdfTextError


@pytest.mark.parametrize("size,accepted", [(8, True), (9, False)])
def test_file_limit_boundary_and_bounded_reads(monkeypatch, size, accepted):
    monkeypatch.setattr(limits, "MAX_PDF_BYTES", 8)
    monkeypatch.setattr(limits, "CHUNK_BYTES", 3)
    reads = []

    class Stream(BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert 0 < size <= 3
            return super().read(size)

    stream = Stream(b"x" * size)
    if accepted:
        assert limits.read_pdf(stream) == b"x" * size
    else:
        with pytest.raises(PdfTextError, match="file_too_large"):
            limits.read_pdf(stream)
    assert reads


@pytest.mark.parametrize("length", [None, b"1", b"9"])
def test_actual_chunked_bytes_stop_at_cap_even_with_false_length(monkeypatch, length):
    monkeypatch.setattr(limits, "MAX_REQUEST_BYTES", 8)
    messages = iter([
        {"type": "http.request", "body": b"aaaa", "more_body": True},
        {"type": "http.request", "body": b"bbbbb", "more_body": True},
        {"type": "http.request", "body": b"never read", "more_body": False},
    ])
    read, forwarded, sent = [], [], []

    async def receive():
        item = next(messages)
        read.append(item)
        return item

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        with pytest.raises(HTTPException) as error:
            while True:
                forwarded.append(await receive())
        assert error.value.status_code == 413

    headers = [] if length is None else [(b"content-length", length)]
    asyncio.run(limits.UploadBodyLimit(app)({"type": "http", "method": "POST", "headers": headers}, receive, send))
    if length == b"9":
        assert not read and sent[0]["status"] == 413
    else:
        assert len(read) == 2 and len(forwarded) == 1


def test_request_exact_limit_is_forwarded(monkeypatch):
    monkeypatch.setattr(limits, "MAX_REQUEST_BYTES", 8)

    async def receive():
        return {"type": "http.request", "body": b"12345678", "more_body": False}

    async def app(scope, receive, send):
        assert (await receive())["body"] == b"12345678"

    asyncio.run(limits.UploadBodyLimit(app)({"type": "http", "method": "POST", "headers": []}, receive, None))
