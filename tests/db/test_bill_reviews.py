from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from bill_lens.api.app import create_app
from bill_lens.api import reviews
from bill_lens.db.models import Bill, BillReview, ExtractionRun
from bill_lens.db.repository import append_extraction_run
from bill_lens.extraction import FakeExtractor, ScriptedResponse
from bill_lens.pdf_text import extract_pdf_text
from tests.helpers import ROOT

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_engine, tmp_path):
    with TestClient(create_app(engine=db_engine, storage_root=tmp_path), raise_server_exceptions=False) as client:
        yield client


def upload(client, case="bill_001"):
    response = client.post("/bills", files={"file": ("bill.pdf", (ROOT / "dataset" / case / "bill.pdf").read_bytes(), "application/pdf")})
    assert response.status_code == 201, response.text
    return response.json()


def request(bill, **overrides):
    return dict(source_run_id=bill["run"]["id"], expected_review_id=None,
                fields=deepcopy(bill["fields"]), reviewer="Max", note="Checked against PDF", acknowledged=True) | overrides


def save(client, bill, payload=None):
    return client.post(f'/bills/{bill["id"]}/reviews', json=payload or request(bill))


def test_confirm_preserves_original_and_adds_independent_review_state(client, db_engine):
    bill = upload(client, "bill_002")
    before = client.get(f'/bills/{bill["id"]}').json()
    with Session(db_engine) as session:
        raw = session.get(ExtractionRun, UUID(bill["run"]["id"])).raw_response
    response = save(client, bill)
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["revision"] == 1 and review["action"] == "confirmed"
    assert review["review_flags"] == ["current_bill_amount_missing"]
    detail = client.get(f'/bills/{bill["id"]}/detail').json()
    assert detail["review_state"] == "reviewed"
    assert detail["status"] == "needs_review"
    assert detail["flags"] == before["flags"]
    assert detail["fields"] == detail["effective_fields"] == before["fields"]
    assert detail["latest_review_id"] == detail["review"]["id"] == review["id"]
    assert detail["updated_at"] != before["updated_at"]
    with Session(db_engine) as session:
        run = session.get(ExtractionRun, UUID(bill["run"]["id"]))
        assert run.raw_response == raw and run.fields == bill["fields"]
        assert session.scalar(text("select count(*) from extraction_runs")) == 1


def test_correct_then_confirm_revision_and_history(client):
    bill = upload(client)
    payload = request(bill)
    payload["fields"]["current_bill_amount"] = "0.000"
    first = save(client, bill, payload)
    assert first.status_code == 201, first.text
    first = first.json()
    assert first["action"] == "corrected"
    assert "current_bill_amount_role_unconfirmed" in first["review_flags"]
    second = save(client, bill, payload | {"expected_review_id": first["id"], "note": "Confirmed revision 1"})
    assert second.status_code == 201, second.text
    assert second.json()["action"] == "confirmed" and second.json()["revision"] == 2
    detail = client.get(f'/bills/{bill["id"]}/detail').json()
    assert detail["fields"]["current_bill_amount"] == "108.07"
    assert detail["effective_fields"]["current_bill_amount"] == "0.000"
    history = client.get(f'/bills/{bill["id"]}/reviews?limit=1').json()
    assert history["total"] == 2 and history["items"] == [second.json()]
    assert client.get(f'/bills/{bill["id"]}/reviews?limit=1&offset=1').json()["items"] == [first]


def test_list_pagination_and_independent_filters(client):
    one, two, three = [upload(client, case) for case in ("bill_001", "bill_002", "bill_003")]
    assert save(client, two).status_code == 201
    page = client.get("/bills?limit=2").json()
    assert page["total"] == 3 and len(page["items"]) == 2
    rest = client.get("/bills?limit=2&offset=2").json()
    assert len(rest["items"]) == 1
    assert len({b["id"] for b in page["items"] + rest["items"]}) == 3
    filtered = client.get("/bills?status=needs_review&review_state=reviewed").json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == two["id"]
    assert client.get("/bills?review_state=pending").json()["total"] == 2
    assert client.get("/bills?offset=100").json()["items"] == []


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "status=typo", "review_state=typo"])
def test_invalid_list_queries(client, query):
    assert client.get("/bills?" + query).status_code == 422


@pytest.mark.parametrize("changes", [{"reviewer": "  "}, {"reviewer": "bad\u0000name"},
                                    {"note": "\ud800"}, {"note": "x" * 2001},
                                    {"acknowledged": False}, {"acknowledged": "true"},
                                    {"extra": "not allowed"}])
def test_invalid_review_does_not_write(client, db_engine, changes):
    bill = upload(client)
    # ensure_ascii transports the unpaired surrogate to the schema validator.
    import json
    response = client.post(f'/bills/{bill["id"]}/reviews', content=json.dumps(request(bill, **changes)),
                           headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text
    with Session(db_engine) as session:
        assert session.scalar(text("select count(*) from bill_reviews")) == 0


def test_invalid_fields_and_missing_version_token_rejected(client):
    bill = upload(client)
    payload = request(bill)
    payload["fields"]["total_usage_kwh"] = "-1"
    assert save(client, bill, payload).status_code == 422
    payload = request(bill)
    del payload["expected_review_id"]
    assert save(client, bill, payload).status_code == 422


def test_stale_review_and_cross_bill_run_rejected(client):
    bill, other = upload(client), upload(client, "bill_002")
    assert save(client, bill, request(bill, source_run_id=other["run"]["id"])).status_code == 409
    assert save(client, bill).status_code == 201
    stale = save(client, bill)
    assert stale.status_code == 409 and stale.json()["error"] == "review_conflict"
    assert client.get(f'/bills/{bill["id"]}/reviews').json()["total"] == 1


def test_new_current_run_invalidates_human_review_without_deleting_history(client, db_engine):
    bill = upload(client)
    first = save(client, bill).json()
    document = extract_pdf_text((ROOT / "dataset/bill_001/bill.pdf").read_bytes())
    attempt = FakeExtractor.from_dataset(ROOT / "dataset").extract(document)
    with Session(db_engine) as session, session.begin():
        append_extraction_run(session, bill_id=UUID(bill["id"]), attempt=attempt, flags=[], status="processed")
    detail = client.get(f'/bills/{bill["id"]}/detail').json()
    assert detail["review_state"] == "pending" and detail["review"] is None
    assert detail["latest_review_id"] == first["id"]
    assert client.get("/bills?review_state=reviewed").json()["total"] == 0
    assert save(client, bill, request(bill, expected_review_id=first["id"])).status_code == 409
    new = request(detail, expected_review_id=first["id"])
    response = save(client, detail, new)
    assert response.status_code == 201 and response.json()["revision"] == 2


def test_two_simultaneous_reviewers_cannot_overwrite(client, db_engine, monkeypatch):
    bill = upload(client)
    barrier = Barrier(2)
    original = reviews.extract_pdf_text

    def together(data):
        document = original(data)
        barrier.wait(timeout=10)
        return document

    monkeypatch.setattr(reviews, "extract_pdf_text", together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: save(client, bill, request(bill, reviewer=name)), ["Alice", "Bob"]))
    assert sorted(r.status_code for r in results) == [201, 409]
    with Session(db_engine) as session:
        rows = session.scalars(select(BillReview)).all()
        assert len(rows) == 1 and rows[0].revision == 1


def test_pdf_route_and_missing_resource(client, db_engine, tmp_path):
    bill = upload(client)
    response = client.get(f'/bills/{bill["id"]}/pdf')
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content == (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["cache-control"] == "no-store"
    preview = client.get(f'/bills/{bill["id"]}/preview/1')
    assert preview.status_code == 200 and preview.content.startswith(b'\x89PNG')
    assert preview.headers["x-page-count"] == "1"
    for page in (0, 2):
        assert client.get(f'/bills/{bill["id"]}/preview/{page}').status_code == 404
    with Session(db_engine) as session:
        key = session.get(Bill, UUID(bill["id"])).storage_key
    (tmp_path / key).unlink()
    assert client.get(f'/bills/{bill["id"]}/pdf').status_code == 404
    for suffix in ("detail", "pdf", "reviews"):
        assert client.get(f"/bills/{uuid4()}/{suffix}").status_code == 404


def test_tampered_pdf_cannot_be_reviewed(client, db_engine, tmp_path):
    bill = upload(client)
    with Session(db_engine) as session:
        key = session.get(Bill, UUID(bill["id"])).storage_key
    (tmp_path / key).write_bytes((ROOT / "dataset/bill_003/bill.pdf").read_bytes())
    response = save(client, bill)
    assert response.status_code == 409 and response.json()["error"] == "pdf_integrity_error"


def test_workbench_assets_are_served_without_remote_dependencies(client):
    response = client.get("/")
    assert response.status_code == 200 and 'lang="zh-Hant"' in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    for asset in ("app.js", "styles.css"):
        assert client.get("/assets/" + asset).status_code == 200


def test_failed_extraction_can_be_reviewed_without_changing_failure(db_engine, tmp_path, valid_fields):
    data = (ROOT / "dataset/bill_001/bill.pdf").read_bytes()
    document = extract_pdf_text(data)
    extractor = FakeExtractor({document.file_sha256: ScriptedResponse(raw_response=None, error_code="timeout")})
    with TestClient(create_app(engine=db_engine, storage_root=tmp_path, extractor=extractor)) as client:
        bill = upload(client)
        assert bill["status"] == "failed" and bill["fields"] is None
        response = save(client, bill, request(bill, fields=valid_fields))
        assert response.status_code == 201
        detail = client.get(f'/bills/{bill["id"]}/detail').json()
        assert detail["status"] == "failed" and detail["fields"] is None
        assert detail["review_state"] == "reviewed" and detail["effective_fields"] == valid_fields
        assert detail["run"]["error_code"] == "timeout"


def test_late_failure_does_not_invalidate_review(client, db_engine):
    from bill_lens.extraction import build_attempt
    bill = upload(client)
    first = save(client, bill).json()
    failure = build_attempt(provider="test", model="m", prompt_version="v", raw_response=None,
                            error_code="timeout", latency_ms=0)
    with Session(db_engine) as session, session.begin():
        append_extraction_run(session, bill_id=UUID(bill["id"]), attempt=failure, flags=[], status="failed")
    detail = client.get(f'/bills/{bill["id"]}/detail').json()
    assert detail["review_state"] == "reviewed" and detail["review"]["id"] == first["id"]
    assert client.get("/bills?status=processed&review_state=reviewed").json()["total"] == 1
