"""Bounded PNG previews for browsers without an embedded PDF viewer."""
from io import BytesIO
from contextlib import closing
from collections import OrderedDict
from hashlib import sha256
import atexit
import math
from pathlib import Path
from threading import Lock

import pypdfium2

from bill_lens.api.errors import UploadError
from bill_lens.pdf_text import MAX_PAGES, MAX_PDF_BYTES

# PDFium is not thread-safe. Serialize its calls within each API worker.
_render_lock = Lock()
_cache_lock = Lock()
_documents = OrderedDict()
_pages = OrderedDict()
_page_bytes = 0
MAX_CACHED_DOCUMENTS = 4
MAX_CACHED_PNG_BYTES = 16 * 1024 * 1024


def clear_preview_cache():
    global _page_bytes
    with _render_lock:
        for document in _documents.values():
            document.close()
        _documents.clear()
        with _cache_lock:
            _pages.clear()
            _page_bytes = 0


atexit.register(clear_preview_cache)


def _cached_page(key):
    with _cache_lock:
        if key in _pages:
            _pages.move_to_end(key)
            return _pages[key]
    return None


def _cache_page(key, result):
    global _page_bytes
    size = len(result[0])
    if size > MAX_CACHED_PNG_BYTES:
        return
    with _cache_lock:
        if key in _pages:
            _page_bytes -= len(_pages.pop(key)[0])
        while _pages and _page_bytes + size > MAX_CACHED_PNG_BYTES:
            _page_bytes -= len(_pages.popitem(last=False)[1][0])
        _pages[key] = result
        _page_bytes += size


def render_page(path: Path, page_number: int) -> tuple[bytes, int]:
    with path.open("rb") as stream:
        data = stream.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise UploadError("preview_unavailable", 422)
    # Content identity prevents stale previews even after a same-size file edit.
    digest = sha256(data).digest()
    key = (digest, page_number)
    cached = _cached_page(key)
    if cached is not None:
        return cached
    with _render_lock:
        try:
            cached = _cached_page(key)
            if cached is not None:
                return cached
            document = _documents.get(digest)
            if document is None:
                while len(_documents) >= MAX_CACHED_DOCUMENTS:
                    _documents.popitem(last=False)[1].close()
                document = pypdfium2.PdfDocument(data)
                if len(document) > MAX_PAGES:
                    document.close()
                    raise UploadError("preview_unavailable", 422)
                _documents[digest] = document
            _documents.move_to_end(digest)
            count = len(document)
            if not 1 <= page_number <= count:
                raise UploadError("page_not_found", 404)
            with closing(document[page_number - 1]) as page:
                width, height = page.get_size()
                if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                    raise UploadError("preview_unavailable", 422)
                scale = min(2, 1600 / max(width, height))
                with closing(page.render(scale=scale)) as bitmap:
                    with bitmap.to_pil() as native_image:
                        image = native_image.copy()
        except UploadError:
            raise
        except Exception:
            raise UploadError("preview_unavailable", 422) from None
    # Only PDFium calls need serialization. Encode the independent pixels outside
    # its lock; cached pages bypass rendering and that lock entirely.
    try:
        with image:
            output = BytesIO()
            image.save(output, format="PNG")
            result = output.getvalue(), count
        _cache_page(key, result)
        return result
    except Exception:
        raise UploadError("preview_unavailable", 422) from None
