import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Engine
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from bill_lens.api.errors import UploadError
from bill_lens.api.limits import UploadBodyLimit, read_pdf
from bill_lens.api.schemas import BillResponse
from bill_lens.api.service import get_bill, upload_bill
from bill_lens.db.config import make_engine
from bill_lens.extraction import BillExtractor, FakeExtractor
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
    adapter = extractor if extractor is not None else FakeExtractor.from_dataset(
        Path(os.environ.get("BILL_DATASET_ROOT", "dataset")))

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owns_engine:
                database.dispose()

    app = FastAPI(title="Bill Lens (local fake)", lifespan=lifespan)
    app.state.extractor = adapter
    app.add_middleware(UploadBodyLimit)

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

    @app.get("/bills/{bill_id}", response_model=BillResponse)
    def read_bill(bill_id: UUID):
        return get_bill(database, bill_id)

    return app
