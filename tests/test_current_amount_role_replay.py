from dataclasses import replace
import json

import pytest

from scripts import rescore_current_amount_roles as replay


def test_all_88_attempts_catch_both_printed_distractors_without_new_false_reviews():
    result = replay.build_evidence()
    assert (result["source_scoring_version"], result["derived_scoring_version"], result["live_api_calls"]) == ("2", "3", 0)
    assert result["totals"] == {
        "attempts": 88, "silent_false_acceptance_before": 2, "silent_false_acceptance_after": 0,
        "new_false_reviews": 0, "flag_changes": 3, "status_changes": 2,
    }
    assert {(c["run"], c["bill"], c["repeat"], c["current_bill_amount"]) for c in result["changes"]} == {
        ("v4-dev", "bill_002", 3, "162.66"),
        ("v4-bill-002-repeat", "bill_002", 3, "162.66"),
        ("v4-bill-002-repeat", "bill_002", 13, "132.66"),
    }
    for change in result["changes"]:
        assert change["status_after"] == "needs_review"
        assert "current_bill_amount_role_unconfirmed" in change["flags_after"]
        assert change["flags_match_after"] is False  # Correct routing, still wrong extraction/reason.


def test_role_replay_refuses_modified_presence_baseline(monkeypatch):
    read = replay.Path.read_bytes

    def changed(path):
        data = read(path)
        if path.name == "printed-value-check.json":
            baseline = json.loads(data)
            baseline["totals"]["silent_false_acceptance_after"] = 0
            return json.dumps(baseline).encode()
        return data

    monkeypatch.setattr(replay.Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="scoring-2 baseline mismatch"):
        replay.build_evidence()


def test_role_replay_rechecks_its_document_identity(monkeypatch):
    load = replay.load_cases

    def changed(folder):
        return [replace(c, document=replace(c.document, file_sha256="0" * 64)) for c in load(folder)]

    monkeypatch.setattr(replay, "load_cases", changed)
    with pytest.raises(ValueError, match="dataset identity mismatch"):
        replay.build_evidence()


def test_role_replay_refuses_to_overwrite_saved_output(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        replay.main(["--output", str(path)])
    assert path.read_text(encoding="utf-8") == "original"
