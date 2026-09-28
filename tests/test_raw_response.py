import json

import pytest
from pydantic import ValidationError

from bill_lens.contract import ExtractionFields
from bill_lens.db.raw_response import RawResponseText
from bill_lens.extraction import build_attempt


# Entire Cc category (C0 + DEL + C1) and surrogate range boundaries.
@pytest.mark.parametrize("codepoint", [*range(0x20), *range(0x7F, 0xA0), 0xD800, 0xDBFF, 0xDC00, 0xDFFF])
def test_retailer_rejects_controls_and_surrogates(valid_fields, codepoint):
    valid_fields["retailer"] = "Example" + chr(codepoint) + "Energy"
    with pytest.raises(ValidationError):
        ExtractionFields.model_validate(valid_fields)
    raw = json.dumps(valid_fields)
    attempt = build_attempt(provider="test", model="m", prompt_version="v",
                            raw_response=raw, latency_ms=0)
    assert attempt.error_code == "invalid_output"
    assert attempt.fields is None
    assert attempt.raw_response == raw


@pytest.mark.parametrize("name", ["電力 ⚡ 😀", "E\u0301nergie", "Énergie", "Energy\u00a0Co", r"Example\u0000Energy"])
def test_normal_unicode_and_literal_escape_names_are_unchanged(valid_fields, name):
    valid_fields["retailer"] = name
    fields = ExtractionFields.model_validate_json(json.dumps(valid_fields))
    assert fields.retailer == name


@pytest.mark.parametrize("raw,encoded", [
    (None, None), ("", b""), ("a\x00b", b"a\x00b"),
    ("\ud800", b"\xed\xa0\x80"), ("\udfff", b"\xed\xbf\xbf"),
    ("\ud83d\ude00", b"\xed\xa0\xbd\xed\xb8\x80"),
    ("😀", b"\xf0\x9f\x98\x80"), (r"\ud800", b"\\ud800"),
])
def test_codec_has_known_bytes_and_exact_round_trip(raw, encoded):
    codec = RawResponseText()
    assert codec.process_bind_param(raw, None) == encoded
    assert codec.process_result_value(encoded, None) == raw


def test_codec_refuses_wrong_input_and_corrupt_bytes():
    codec = RawResponseText()
    with pytest.raises(TypeError):
        codec.process_bind_param(b"not a str", None)
    with pytest.raises(UnicodeDecodeError):
        codec.process_result_value(b"\xff", None)
