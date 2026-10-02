from io import BytesIO

from PIL import Image
import pytest

from bill_lens.api.errors import UploadError
from bill_lens.api.preview import render_page
from bill_lens.api import preview
from tests.test_pdf_text import make_pdf


@pytest.fixture(autouse=True)
def clear_cache():
    preview.clear_preview_cache()
    yield
    preview.clear_preview_cache()


def test_preview_page_selection_and_image_bound(tmp_path):
    path = tmp_path / "two.pdf"
    path.write_bytes(make_pdf("First page", "Second page"))
    first, count = render_page(path, 1)
    second, count2 = render_page(path, 2)
    assert count == count2 == 2 and first != second
    with Image.open(BytesIO(first)) as image:
        assert max(image.size) <= 1601  # Native renderer rounds pixel dimensions.
    with pytest.raises(UploadError, match="page_not_found"):
        render_page(path, 3)


def test_bad_preview_is_classified(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF- not a valid document")
    with pytest.raises(UploadError, match="preview_unavailable"):
        render_page(path, 1)


def test_pages_reuse_parsed_document_and_cached_png(tmp_path, monkeypatch):
    path = tmp_path / "cached.pdf"
    path.write_bytes(make_pdf("First page", "Second page"))
    original = preview.pypdfium2.PdfDocument
    documents = []

    def counted(data):
        document = original(data)
        documents.append(document)
        return document

    monkeypatch.setattr(preview.pypdfium2, "PdfDocument", counted)
    first = render_page(path, 1)
    render_page(path, 2)
    assert len(documents) == 1
    # A cached PNG is independent of the native renderer lock.
    with preview._render_lock:
        assert render_page(path, 1) == first
    path.write_bytes(make_pdf("Replacement page"))
    changed = render_page(path, 1)
    assert changed != first and changed[1] == 1
    assert len(documents) == 2


def test_document_eviction_closes_native_handles(tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "MAX_CACHED_DOCUMENTS", 1)
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    first.write_bytes(make_pdf("One"))
    second.write_bytes(make_pdf("Two"))
    render_page(first, 1)
    evicted = next(iter(preview._documents.values()))
    render_page(second, 1)
    assert len(preview._documents) == 1 and not evicted.raw
    retained = next(iter(preview._documents.values()))
    preview.clear_preview_cache()
    assert not retained.raw and not preview._documents and not preview._pages


def test_png_cache_obeys_byte_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(preview, "MAX_CACHED_PNG_BYTES", 1)
    path = tmp_path / "large.png.pdf"
    path.write_bytes(make_pdf("Not cached"))
    assert render_page(path, 1)[1] == 1
    assert preview._page_bytes == 0 and not preview._pages


def test_concurrent_previews_are_consistent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / "concurrent.pdf"
    path.write_bytes(make_pdf("Page one", "Page two"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda page: render_page(path, page), [1, 2, 1, 2]))
    assert results[0] == results[2] and results[1] == results[3]
    assert len(preview._documents) == 1
