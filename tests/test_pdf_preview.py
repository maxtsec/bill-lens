from io import BytesIO

from PIL import Image
import pytest

from bill_lens.api.errors import UploadError
from bill_lens.api.preview import render_page
from tests.test_pdf_text import make_pdf


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
