import json
import re

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from bill_lens.db.config import database_url
from bill_lens.db.models import ExtractionRun
from bill_lens.db.repository import create_bill_with_run, load_fields, new_storage_key
from bill_lens.extraction import build_attempt


def test_database_configuration_is_explicit(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        database_url()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///not-supported.db")
    with pytest.raises(ValueError, match="postgresql"):
        database_url()
    url = "postgresql+psycopg://localhost/bill_lens"
    monkeypatch.setenv("DATABASE_URL", url)
    assert database_url() == url


def test_storage_keys_are_generated_relative_and_unique():
    first, second = new_storage_key(), new_storage_key()
    assert first != second
    assert re.fullmatch(r"bills/[0-9a-f]{32}\.pdf", first)


def test_repository_requires_explicit_transaction(valid_fields):
    attempt = build_attempt(provider="fake", model="m", prompt_version="v",
                            raw_response=json.dumps(valid_fields), latency_ms=0)
    with Session() as session, pytest.raises(ValueError, match="active transaction"):
        create_bill_with_run(session, file_sha256="a" * 64, storage_key=new_storage_key(),
                             size_bytes=1, attempt=attempt, flags=[], status="processed")


@pytest.mark.parametrize("flags,status", [([], "failed"), (["retailer_missing"], "needs_review"), (["typo"], "needs_review")])
def test_repository_rejects_inconsistent_domain_decisions(valid_fields, flags, status):
    attempt = build_attempt(provider="fake", model="m", prompt_version="v",
                            raw_response=json.dumps(valid_fields), latency_ms=0)
    with Session() as session, session.begin(), pytest.raises(ValueError):
        create_bill_with_run(session, file_sha256="a" * 64, storage_key=new_storage_key(),
                             size_bytes=1, attempt=attempt, flags=flags, status=status)


def test_load_fields_rejects_unknown_versions_and_bad_json(valid_fields):
    assert load_fields(ExtractionRun(fields=None, fields_schema_version=None)) is None
    with pytest.raises(ValueError):
        load_fields(ExtractionRun(fields=None, fields_schema_version=1))
    with pytest.raises(ValueError):
        load_fields(ExtractionRun(fields=valid_fields, fields_schema_version=2))
    with pytest.raises(ValidationError):
        load_fields(ExtractionRun(fields={}, fields_schema_version=1))
