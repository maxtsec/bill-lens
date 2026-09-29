from dataclasses import replace

import pytest

from scripts import rescore_printed_values as replay


def test_all_preserved_attempts_have_only_the_expected_decision_change():
    result = replay.build_evidence()
    assert result["live_api_calls"] == 0
    assert (result["source_scoring_version"], result["derived_scoring_version"]) == ("1", "2")
    assert result["totals"] == {
        "attempts": 88, "silent_false_acceptance_before": 3, "silent_false_acceptance_after": 2,
        "new_false_reviews": 0, "flag_changes": 1, "status_changes": 1,
    }
    assert len(result["changes"]) == 1
    changed = result["changes"][0]
    assert (changed["run"], changed["bill"], changed["repeat"], changed["current_bill_amount"]) == (
        "v4-bill-002-repeat", "bill_002", 13, "132.66")
    assert changed["flags_before"] == []
    assert changed["flags_after"] == ["current_bill_amount_not_printed"]
    assert (changed["status_before"], changed["status_after"]) == ("processed", "needs_review")
    # Flag reason is not the expected missing-value reason: no value was nulled.
    assert changed["flags_match_before"] is changed["flags_match_after"] is False


def test_replay_refuses_changed_document_hash(monkeypatch):
    real_load = replay.load_cases
    def changed_load(folder):
        cases = real_load(folder)
        return [replace(case, document=replace(case.document, file_sha256="0" * 64)) for case in cases]
    monkeypatch.setattr(replay, "load_cases", changed_load)
    with pytest.raises(ValueError, match="identity mismatch"):
        replay.build_evidence()


def test_replay_refuses_changed_source_artifact(monkeypatch):
    real_read = replay.Path.read_bytes
    def corrupt(path):
        data = real_read(path)
        return data + b" " if path.name == "attempts.jsonl" else data
    monkeypatch.setattr(replay.Path, "read_bytes", corrupt)
    with pytest.raises(ValueError, match="source artifact hash mismatch"):
        replay.build_evidence()
