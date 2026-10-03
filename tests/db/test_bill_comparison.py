from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from bill_lens.api.app import create_app
from bill_lens.api import comparison
from bill_lens.api.reviews import save_review
from bill_lens.api.schemas import ReviewRequest
from bill_lens.db.repository import append_extraction_run
from bill_lens.extraction import FakeExtractor
from bill_lens.pdf_text import extract_pdf_text
from tests.db.test_bill_reviews import upload, save, request
from tests.helpers import ROOT

pytestmark = pytest.mark.db


@pytest.fixture
def client(db_engine, tmp_path):
    with TestClient(create_app(engine=db_engine, storage_root=tmp_path)) as client:
        yield client


def compare(client, a, b, **overrides):
    return client.get("/comparisons", params={"baseline_id": a["id"], "comparison_id": b["id"], "same_household": "true"} | overrides)


def test_comparison_requires_different_existing_reviewed_bills_and_acknowledgement(client):
    a, b = upload(client), upload(client, "bill_003")
    assert compare(client, a, b, same_household="false").json()["error"] == "comparison_household_required"
    assert compare(client, a, a).json()["error"] == "comparison_requires_two_bills"
    assert compare(client, a, b).status_code == 409
    assert save(client, a).status_code == 201
    assert compare(client, a, b).status_code == 409
    assert compare(client, a, {"id": str(uuid4())}).status_code == 404
    assert compare(client, a, {"id": "invalid"}).status_code == 422


def test_comparison_uses_latest_review_values_and_is_read_only(client, db_engine):
    a, b = upload(client), upload(client, "bill_003")
    first = save(client, a).json()
    corrected = request(a, expected_review_id=first["id"])
    corrected["fields"]["current_bill_amount"] = "100.00"
    assert save(client, a, corrected).status_code == 201
    assert save(client, b).status_code == 201
    result = compare(client, a, b)
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["baseline"]["review"]["revision"] == 2
    assert result["baseline"]["fields"]["current_bill_amount"] == "108.07"
    metric = next(m for m in result["metrics"] if m["key"] == "current_charges")
    assert metric["baseline"] == "100.00" and metric["delta"] == "13.40"
    assert result["warnings"]  # Corrected amount still carries its review warnings.
    assert "raw_response" not in str(result)
    with Session(db_engine) as session:
        assert session.scalar(text("select count(*) from bill_reviews")) == 3
        assert session.scalar(text("select count(*) from extraction_runs")) == 2


def test_new_success_since_picker_load_requires_review_again(client, db_engine):
    a, b = upload(client), upload(client, "bill_003")
    assert save(client, a).status_code == save(client, b).status_code == 201
    attempt = FakeExtractor.from_dataset(ROOT / "dataset").extract(extract_pdf_text((ROOT / "dataset/bill_001/bill.pdf").read_bytes()))
    with Session(db_engine) as session, session.begin():
        append_extraction_run(session, bill_id=UUID(a["id"]), attempt=attempt, flags=[], status="processed")
    response = compare(client, a, b)
    assert response.status_code == 409 and response.json()["error"] == "comparison_requires_review"


def test_both_bills_use_one_snapshot_when_another_review_commits(client, db_engine, tmp_path, monkeypatch):
    a, b = upload(client), upload(client, "bill_003")
    assert save(client, a).status_code == 201
    old = save(client, b).json()
    original = comparison.detail_in_session
    calls = []

    def interleaved(session, bill_id):
        detail = original(session, bill_id)
        calls.append(bill_id)
        if len(calls) == 1:
            payload = request(b, expected_review_id=old["id"])
            payload["fields"]["total_usage_kwh"] = "12345"
            save_review(db_engine, tmp_path, UUID(b["id"]), ReviewRequest.model_validate(payload))
        return detail

    monkeypatch.setattr(comparison, "detail_in_session", interleaved)
    result = compare(client, a, b).json()
    assert result["comparison"]["review"]["id"] == old["id"]
    assert result["comparison"]["effective_fields"] == old["fields"]
    latest = client.get(f'/bills/{b["id"]}/detail').json()
    assert latest["review"]["revision"] == 2


def test_missing_values_and_overlapping_periods_are_explicit(client):
    a, b = upload(client), upload(client, "bill_002")
    assert save(client, a).status_code == save(client, b).status_code == 201
    result = compare(client, a, b).json()
    amount = next(m for m in result["metrics"] if m["key"] == "current_charges")
    assert amount["comparison"] is None and amount["delta"] is None
    payload = request(b, expected_review_id=result["comparison"]["review"]["id"])
    payload["fields"].update(period_start=a["fields"]["period_start"], period_end=a["fields"]["period_end"], stated_billing_days=30)
    assert save(client, b, payload).status_code == 201
    assert any("overlap" in warning for warning in compare(client, a, b).json()["warnings"])
