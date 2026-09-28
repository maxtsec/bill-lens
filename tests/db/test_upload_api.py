from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from threading import Barrier, Event
from typing import get_args
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from bill_lens import pdf_text
from bill_lens.api import service, storage
from bill_lens.api.app import create_app, get_extractor
from bill_lens.contract import ExpectedLabel
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.extraction import FakeExtractor, ScriptedResponse
from bill_lens.extraction.port import ExtractionErrorCode
from tests.helpers import ROOT
from tests.test_pdf_text import make_pdf

pytestmark = pytest.mark.db


@pytest.fixture
def app(db_engine, tmp_path):
    return create_app(engine=db_engine, storage_root=tmp_path,
                      extractor=FakeExtractor.from_dataset(ROOT / "dataset"))


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def post(client, data=None):
    if data is None:
        data = (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    return client.post("/bills", files={"file": ("../../PRIVATE-name.exe", data, "text/plain")})


def assert_empty(db_engine, tmp_path):
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM bills")) == 0
        assert connection.scalar(text("SELECT count(*) FROM extraction_runs")) == 0
    assert not list(tmp_path.rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("case,days,rate", [
    ("bill_001", "30", "1.1023"), ("bill_002", "31", "1.00"),
    ("bill_003", "30", "0.98"), ("bill_004", "30", "1.00"),
    ("bill_005", "31", "0.95"),
])
def test_golden_upload_read_duplicate(case, days, rate, app, client, db_engine, tmp_path):
    data = (ROOT / "dataset" / case / "bill.pdf").read_bytes()
    label = ExpectedLabel.model_validate_json((ROOT / "dataset" / case / "expected.json").read_text())
    response = post(client, data)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["fields"] == label.fields.model_dump(mode="json")
    assert body["status"] == label.expected_status
    assert body["flags"] == label.expected_flags
    assert body["file_sha256"] == sha256(data).hexdigest()
    assert body["billing_days"] == days
    assert body["daily_supply_rate_aud"] == rate
    assert body["run"]["provider"] == "fake"
    assert body["run"]["input_tokens"] is None
    assert body["run"]["latency_ms"] == 0
    assert "raw_response" not in response.text and "PRIVATE" not in response.text
    assert "storage_key" not in body
    assert client.get(response.headers["Location"]).json() == body

    class MustNotExtract:
        def extract(self, document):
            pytest.fail("duplicate must not extract again")

    app.dependency_overrides[get_extractor] = lambda: MustNotExtract()
    duplicate = post(client, data)
    assert duplicate.status_code == 200
    assert duplicate.json() == body
    with Session(db_engine) as session:
        bill = session.scalars(select(Bill)).one()
        run = session.scalars(select(ExtractionRun)).one()
        assert run.bill_id == bill.id
        assert (tmp_path / bill.storage_key).read_bytes() == data
        assert "PRIVATE" not in bill.storage_key
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


@pytest.mark.parametrize("code", get_args(pdf_text.PdfErrorCode))
def test_pdf_errors_leave_nothing(code, client, db_engine, tmp_path, monkeypatch):
    fixtures = {
        "empty_file": b"", "file_too_large": b"x" * (pdf_text.MAX_PDF_BYTES + 1),
        "invalid_pdf_signature": b"not a PDF", "unreadable_pdf": b"%PDF-broken",
        "encrypted_pdf": make_pdf("Private", encrypt=StandardEncryption("", ownerPassword="owner")),
        "no_pages": make_pdf(), "too_many_pages": make_pdf(*(["Page"] * 21)),
        "page_without_text": make_pdf(None), "text_too_long": make_pdf("Too long"),
    }
    if code == "text_too_long":
        monkeypatch.setattr(pdf_text, "MAX_TEXT_CHARACTERS", 2)
    response = post(client, fixtures[code])
    assert response.status_code == {"file_too_large": 413, "invalid_pdf_signature": 415}.get(code, 422)
    assert response.json() == {"error": code}
    assert_empty(db_engine, tmp_path)


@pytest.mark.parametrize("code", get_args(ExtractionErrorCode))
def test_failed_attempt_is_a_created_record(code, app, client, db_engine, tmp_path):
    data = (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    raw = "not JSON" if code == "invalid_output" else None
    fake = FakeExtractor({sha256(data).hexdigest(): ScriptedResponse(raw, code, 5, 7, 123)})
    app.dependency_overrides[get_extractor] = lambda: fake
    response = post(client, data)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed" and body["fields"] is None and body["flags"] == []
    assert body["billing_days"] is None and body["daily_supply_rate_aud"] is None
    assert body["run"]["error_code"] == code
    assert body["run"]["input_tokens"] == 5 and body["run"]["output_tokens"] == 7
    assert body["run"]["latency_ms"] == 123
    assert client.get(response.headers["Location"]).json() == body
    assert post(client, data).status_code == 200
    with Session(db_engine) as session:
        assert session.scalars(select(ExtractionRun)).one().raw_response == raw
        assert session.scalars(select(Bill)).one().processing_status == "failed"
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


@pytest.mark.parametrize("raw", ['{"retailer":"Example\\u0000Energy"}', "literal\x00", "\ud800", "\udfff"])
def test_special_character_attempt_survives_http_and_database(raw, app, client, db_engine):
    data = (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    if raw.startswith("{"):
        fields = json.loads((ROOT / "dataset/bill_001/expected.json").read_text())["fields"]
        fields["retailer"] = "Example\x00Energy"
        raw = json.dumps(fields)
    fake = FakeExtractor({sha256(data).hexdigest(): ScriptedResponse(raw)})
    app.dependency_overrides[get_extractor] = lambda: fake
    response = post(client, data)
    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["run"]["error_code"] == "invalid_output"
    assert client.get(response.headers["Location"]).json() == response.json()
    with Session(db_engine) as session:
        assert session.scalars(select(ExtractionRun)).one().raw_response == raw
        assert session.scalars(select(Bill)).one()


def test_unknown_fixture_and_invalid_requests(client, db_engine, tmp_path):
    assert post(client, make_pdf("Unknown bill")).json() == {"error": "unsupported_fixture"}
    assert post(client, make_pdf("Unknown bill")).status_code == 422
    assert client.get(f"/bills/{uuid4()}").status_code == 404
    assert client.get(f"/bills/{uuid4()}").json() == {"error": "bill_not_found"}
    assert client.get("/bills/not-a-uuid").status_code == 422
    assert client.post("/bills").json() == {"error": "invalid_request"}
    assert client.post("/bills", content=b"bad", headers={"Content-Type": "multipart/form-data"}).status_code == 400
    assert_empty(db_engine, tmp_path)


def test_concurrent_identical_uploads_persist_one_result(app, client, db_engine, tmp_path):
    entered, release = Barrier(3, timeout=10), Event()
    fake = FakeExtractor.from_dataset(ROOT / "dataset")
    calls = []

    class BlockingExtractor:
        def extract(self, document):
            calls.append(document.file_sha256)
            entered.wait()
            assert release.wait(10)
            return fake.extract(document)

    app.dependency_overrides[get_extractor] = lambda: BlockingExtractor()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post, client) for _ in range(2)]
        try:
            entered.wait()  # Both requests passed the lookup before either writes.
            assert db_engine.pool.checkedout() == 0
        finally:
            release.set()
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    assert all("Retry-After" not in response.headers for response in responses)
    assert "409" not in app.openapi()["paths"]["/bills"]["post"]["responses"]
    assert post(client).status_code == 200
    assert len(calls) == 2
    with Session(db_engine) as session:
        bill = session.scalars(select(Bill)).one()
        run = session.scalars(select(ExtractionRun)).one()
        assert run.bill_id == bill.id
        assert str(bill.id) == responses[0].json()["id"]
        assert str(run.id) == responses[0].json()["run"]["id"]
        assert list(tmp_path.rglob("*.pdf")) == [tmp_path / bill.storage_key]
        assert (tmp_path / bill.storage_key).read_bytes() == (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("upload_count", [2, 3])
def test_distinct_uploads_release_connections_during_extraction(upload_count, db_engine, tmp_path):
    # Reuse the migrated disposable schema, but give the app its own tiny pool.
    with db_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    engine = create_engine(
        db_engine.url, pool_size=2, max_overflow=0, pool_timeout=1,
        hide_parameters=True,
        connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000"},
    )
    entered, release = Barrier(upload_count + 1, timeout=10), Event()
    fake = FakeExtractor.from_dataset(ROOT / "dataset")
    data = [(ROOT / f"dataset/bill_{i:03}/bill.pdf").read_bytes()
            for i in range(1, upload_count + 1)]

    class BlockingExtractor:
        def extract(self, document):
            entered.wait()
            assert release.wait(10)
            return fake.extract(document)

    app = create_app(engine=engine, storage_root=tmp_path, extractor=BlockingExtractor())
    try:
        with TestClient(app, raise_server_exceptions=False) as client, ThreadPoolExecutor(upload_count) as pool:
            futures = [pool.submit(post, client, pdf) for pdf in data]
            try:
                entered.wait()  # All distinct uploads must reach extraction together.
                assert engine.pool.checkedout() == 0
                # A read must also progress while every extractor is blocked.
                assert client.get(f"/bills/{uuid4()}").status_code == 404
            finally:
                release.set()
            responses = [future.result(timeout=10) for future in futures]
        assert [response.status_code for response in responses] == [201] * upload_count
        assert len({response.json()["id"] for response in responses}) == upload_count
        assert len({response.json()["run"]["id"] for response in responses}) == upload_count
        with Session(engine) as session:
            bills = session.scalars(select(Bill)).all()
            runs = session.scalars(select(ExtractionRun)).all()
            assert len(bills) == len(runs) == upload_count
            assert {run.bill_id for run in runs} == {bill.id for bill in bills}
            assert {bill.file_sha256 for bill in bills} == {sha256(pdf).hexdigest() for pdf in data}
            assert set(tmp_path.rglob("*.pdf")) == {tmp_path / bill.storage_key for bill in bills}
            for bill in bills:
                assert sha256((tmp_path / bill.storage_key).read_bytes()).hexdigest() == bill.file_sha256
        assert not list(tmp_path.rglob("*.tmp"))
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure", ["extractor", "rename", "insert", "commit"])
def test_failures_clean_files_rows_and_allow_retry(failure, app, client, db_engine, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE diagnostic")

    with monkeypatch.context() as patch:
        if failure == "extractor":
            patch.setattr(app.state.extractor, "extract", fail)
        elif failure == "rename":
            patch.setattr(storage.Path, "rename", fail)
        elif failure == "insert":
            original = service.create_bill_with_run

            def fail_after_flush(*args, **kwargs):
                original(*args, **kwargs)
                fail()

            patch.setattr(service, "create_bill_with_run", fail_after_flush)
        else:
            from sqlalchemy import event
            def fail_outer_commit(session):
                if not session.in_nested_transaction():
                    fail()

            event.listen(Session, "before_commit", fail_outer_commit)
        try:
            response = post(client)
            assert response.status_code == 500
            assert response.json() == {"error": "internal_error"}
        finally:
            if failure == "commit":
                event.remove(Session, "before_commit", fail_outer_commit)
    assert_empty(db_engine, tmp_path)
    assert post(client).status_code == 201


def test_unique_race_with_writer_outside_api_removes_only_loser_file(client, db_engine, tmp_path, monkeypatch):
    original = service.create_bill_with_run
    winner = {}

    def competing_writer(session, **kwargs):
        key, path = storage.write_pdf(tmp_path, b"winner file")
        with Session(db_engine) as other, other.begin():
            bill = original(other, **(kwargs | {"storage_key": key}))
            winner.update(id=str(bill.id), path=path)
        return original(session, **kwargs)

    monkeypatch.setattr(service, "create_bill_with_run", competing_writer)
    response = post(client)
    assert response.status_code == 200
    assert response.json()["id"] == winner["id"]
    assert list(tmp_path.rglob("*.pdf")) == [winner["path"]]
    assert winner["path"].read_bytes() == b"winner file"


def test_get_validates_jsonb_again(client, db_engine):
    response = post(client)
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE extraction_runs SET fields = '{}'::jsonb"))
    result = client.get(response.headers["Location"])
    assert result.status_code == 500
    assert result.json() == {"error": "internal_error"}


def test_lost_commit_acknowledgement_keeps_committed_file(client, db_engine, tmp_path):
    from sqlalchemy import event

    def lost_ack(session):
        if not session.in_nested_transaction():
            raise RuntimeError("commit succeeded but acknowledgement was lost")

    event.listen(Session, "after_commit", lost_ack)
    try:
        assert post(client).status_code == 500
    finally:
        event.remove(Session, "after_commit", lost_ack)
    retry = post(client)
    assert retry.status_code == 200
    with Session(db_engine) as session:
        bill = session.scalars(select(Bill)).one()
        assert (tmp_path / bill.storage_key).exists()
        assert session.scalars(select(ExtractionRun)).one()


@pytest.mark.parametrize("declared_length", [None, b"1", b"99999999"])
def test_stream_limit_http_response_and_multipart_cleanup(
    declared_length, app, db_engine, tmp_path, monkeypatch,
):
    import asyncio
    from starlette import formparsers
    from bill_lens.api import limits

    monkeypatch.setattr(limits, "MAX_REQUEST_BYTES", 512)
    opened = []
    original = formparsers.SpooledTemporaryFile

    def track(*args, **kwargs):
        stream = original(*args, **kwargs)
        opened.append(stream)
        return stream

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", track)
    chunks = iter([
        b'--test\r\nContent-Disposition: form-data; name="file"; filename="private.pdf"\r\n'
        b'Content-Type: application/pdf\r\n\r\n%PDF-first',
        b"x" * 513,
    ])
    received, sent = [], []

    async def receive():
        chunk = next(chunks)
        received.append(chunk)
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        sent.append(message)

    headers = [(b"content-type", b"multipart/form-data; boundary=test")]
    if declared_length is not None:
        headers.append((b"content-length", declared_length))
    scope = {"type": "http", "http_version": "1.1", "method": "POST", "path": "/bills",
             "raw_path": b"/bills", "root_path": "", "scheme": "http", "query_string": b"",
             "headers": headers, "client": ("127.0.0.1", 1234), "server": ("test", 80)}
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 413
    assert json.loads(b"".join(item.get("body", b"") for item in sent)) == {"error": "file_too_large"}
    if declared_length == b"99999999":
        assert not received and not opened
    else:
        assert len(received) == 2 and len(opened) == 1
        assert opened[0].closed
    assert_empty(db_engine, tmp_path)
