from uuid import uuid4

import pytest
from pydantic import ValidationError

from bill_lens.api.schemas import ReviewRequest
from bill_lens.contract import ExtractionFields


def review(name):
    return ReviewRequest(source_run_id=uuid4(), expected_review_id=None,
                         fields=dict.fromkeys(ExtractionFields.model_fields),
                         reviewer=name, acknowledged=True)


@pytest.mark.parametrize("name", [
    "", "  ", "\u200b", "Max\u200b", "\u200c\u200d", "\ufeff", "\u2060",
    "\u202eMax\u202c", "Max\u2066X\u2069", "Max\u2028Chan", "Max\u2029Chan",
    "Max\n", "\tMax", "Max\rChan", "Max\x00", "\ud800", "\u0301", "\ufe0f",
])
def test_reviewer_requires_visible_single_line_name(name):
    with pytest.raises(ValidationError):
        review(name)


@pytest.mark.parametrize("name", ["Max Chan", "陳大文", "José", "Jose\u0301", "محمد", "अमित", "O'Connor"])
def test_visible_international_names_remain_valid(name):
    assert review("  " + name + "  ").reviewer == name
