"""The text-free persistence boundary must not weaken field-rule integrity."""
import json

import pytest

from bill_lens.db.repository import _validated_run
from bill_lens.document_validation import DOCUMENT_FLAG_FIELDS
from bill_lens.extraction import build_attempt


def attempt(fields):
    return build_attempt(provider="fake", model="fake-v1", prompt_version="fixture-v1",
                         raw_response=json.dumps(fields), latency_ms=0)


@pytest.mark.parametrize("flag", DOCUMENT_FLAG_FIELDS)
def test_repository_preserves_known_document_flag_for_non_null_field(valid_fields, flag):
    run = _validated_run(attempt(valid_fields), {flag}, "needs_review")
    assert run.review_flags == [flag] and run.status == "needs_review"


@pytest.mark.parametrize("flags,status", [
    ({"made_up_not_printed"}, "needs_review"),
    ({"retailer_missing"}, "needs_review"),  # Unearned field-derived flag.
    ({"current_bill_amount_not_printed"}, "processed"),
    (set(), "needs_review"),
])
def test_repository_rejects_unknown_flags_extra_field_flags_and_wrong_status(valid_fields, flags, status):
    with pytest.raises(ValueError):
        _validated_run(attempt(valid_fields), flags, status)


def test_document_flag_cannot_replace_a_required_field_flag(valid_fields):
    valid_fields['retailer'] = None
    with pytest.raises(ValueError):
        _validated_run(attempt(valid_fields), {"current_bill_amount_not_printed"}, "needs_review")
    saved = _validated_run(attempt(valid_fields), {"retailer_missing", "current_bill_amount_not_printed"}, "needs_review")
    assert saved.review_flags == ["current_bill_amount_not_printed", "retailer_missing"]


@pytest.mark.parametrize("flag,name", DOCUMENT_FLAG_FIELDS.items())
def test_null_field_cannot_have_a_document_flag(valid_fields, flag, name):
    from bill_lens.validation import derive_flags
    valid_fields[name] = None
    item = attempt(valid_fields)
    with pytest.raises(ValueError):
        _validated_run(item, derive_flags(item.fields) | {flag}, "needs_review")


def test_failed_attempt_still_rejects_document_flags():
    item = build_attempt(provider="fake", model="m", prompt_version="v", raw_response=None,
                         error_code="timeout", latency_ms=0)
    with pytest.raises(ValueError):
        _validated_run(item, {"retailer_not_printed"}, "failed")
