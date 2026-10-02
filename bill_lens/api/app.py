import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Engine
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from bill_lens.api.errors import UploadError
from bill_lens.api.limits import UploadBodyLimit, read_pdf
from bill_lens.api.schemas import BillResponse, BillDetail, BillList, ReviewHistory, ReviewRequest, ReviewResponse
from bill_lens.api import reviews
from bill_lens.api.preview import render_page
from bill_lens.api.service import get_bill, upload_bill
from bill_lens.db.config import make_engine
from bill_lens.extraction import BillExtractor
from bill_lens.extraction.config import configured_extractor
from bill_lens.extraction.openai_adapter import OpenAIExtractor
from bill_lens.extraction.fake import UnknownFixture
from bill_lens.pdf_text import PdfTextError


def get_extractor(request: Request) -> BillExtractor:
    return request.app.state.extractor


def create_app(*, engine: Engine | None = None, storage_root: Path | None = None,
               extractor: BillExtractor | None = None) -> FastAPI:
    owns_engine = engine is None
    database = engine if engine is not None else make_engine()
    root = (storage_root if storage_root is not None
            else Path(os.environ.get("BILL_STORAGE_ROOT", "var/uploads"))).resolve()
    try:
        adapter = extractor if extractor is not None else configured_extractor()
    except Exception:
        if owns_engine:
            database.dispose()
        raise

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            try:
                if extractor is None and isinstance(adapter, OpenAIExtractor):
                    adapter.close()
            finally:
                if owns_engine:
                    database.dispose()

    app = FastAPI(title="Bill Lens", lifespan=lifespan)
    app.state.extractor = adapter
    app.add_middleware(UploadBodyLimit)
    static_root = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")

    @app.get("/", include_in_schema=False)
    def workbench():
        return FileResponse(static_root / "index.html", headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
            "X-Content-Type-Options": "nosniff",
        })

    @app.exception_handler(PdfTextError)
    async def pdf_error(request, error):
        status = {"file_too_large": 413, "invalid_pdf_signature": 415}.get(error.code, 422)
        return JSONResponse({"error": error.code}, status)

    @app.exception_handler(UnknownFixture)
    async def unknown_fixture(request, error):
        return JSONResponse({"error": "unsupported_fixture"}, 422)

    @app.exception_handler(UploadError)
    async def upload_error(request, error):
        return JSONResponse({"error": error.code}, error.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse({"error": "invalid_request"}, 422)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        code = "file_too_large" if error.status_code == 413 else "invalid_request"
        return JSONResponse({"error": code}, error.status_code, headers=error.headers)

    @app.exception_handler(Exception)
    async def internal_error(request, error):
        return JSONResponse({"error": "internal_error"}, 500)

    @app.post("/bills", response_model=BillResponse, status_code=201,
              responses={200: {"model": BillResponse}})
    def post_bill(file: UploadFile, response: Response,
                  extractor: Annotated[BillExtractor, Depends(get_extractor)]):
        result, created = upload_bill(read_pdf(file.file), engine=database,
                                      storage_root=root, extractor=extractor)
        response.status_code = 201 if created else 200
        response.headers["Location"] = f"/bills/{result.id}"
        return result

    @app.get("/bills", response_model=BillList)
    def list_bills(limit: Annotated[int, Query(ge=1, le=100)] = 20,
                   offset: Annotated[int, Query(ge=0)] = 0,
                   status: Literal["processed", "needs_review", "failed"] | None = None,
                   review_state: Literal["pending", "reviewed"] | None = None):
        return reviews.list_bills(database, limit=limit, offset=offset, status=status, review_state=review_state)

    @app.get("/bills/{bill_id}", response_model=BillResponse)
    def read_bill(bill_id: UUID):
        return get_bill(database, bill_id)

    @app.get("/bills/{bill_id}/detail", response_model=BillDetail)
    def read_detail(bill_id: UUID):
        return reviews.get_detail(database, bill_id)

    @app.get("/bills/{bill_id}/pdf")
    def read_pdf_file(bill_id: UUID):
        return FileResponse(reviews.get_pdf(database, bill_id, root), media_type="application/pdf",
                            filename=f"bill-{bill_id}.pdf", content_disposition_type="inline",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/bills/{bill_id}/preview/{page_number}")
    def preview(bill_id: UUID, page_number: int):
        png, count = render_page(reviews.get_pdf(database, bill_id, root), page_number)
        return Response(png, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Page-Count": str(count),
        })

    @app.get("/bills/{bill_id}/reviews", response_model=ReviewHistory)
    def read_reviews(bill_id: UUID, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                     offset: Annotated[int, Query(ge=0)] = 0):
        return reviews.history(database, bill_id, limit=limit, offset=offset)

    @app.post("/bills/{bill_id}/reviews", response_model=ReviewResponse, status_code=201)
    def write_review(bill_id: UUID, request: ReviewRequest):
        return reviews.save_review(database, root, bill_id, request)

    return app
