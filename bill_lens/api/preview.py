"""Bounded PNG previews for browsers without an embedded PDF viewer."""
from io import BytesIO
from contextlib import closing
import math
from pathlib import Path
from threading import Lock

import pypdfium2

from bill_lens.api.errors import UploadError
from bill_lens.pdf_text import MAX_PAGES, MAX_PDF_BYTES

# PDFium is not thread-safe. Serialize its calls within each API worker.
_render_lock = Lock()


def render_page(path: Path, page_number: int) -> tuple[bytes, int]:
    with path.open("rb") as stream:
        data = stream.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise UploadError("preview_unavailable", 422)
    with _render_lock:
        try:
            with pypdfium2.PdfDocument(data) as document:
                count = len(document)
                if count > MAX_PAGES:
                    raise UploadError("preview_unavailable", 422)
                if not 1 <= page_number <= count:
                    raise UploadError("page_not_found", 404)
                with closing(document[page_number - 1]) as page:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                        raise UploadError("preview_unavailable", 422)
                    # At most 1600 pixels per side; PDF inputs remain local-only.
                    scale = min(2, 1600 / max(width, height))
                    with closing(page.render(scale=scale)) as bitmap:
                        with bitmap.to_pil() as image:
                            output = BytesIO()
                            image.save(output, format="PNG")
                            return output.getvalue(), count
        except UploadError:
            raise
        except Exception:
            raise UploadError("preview_unavailable", 422) from None
