"""Reproduce the frozen offline evidence and reject altered holdout inputs."""

from hashlib import sha256
import json
import shutil

import pytest

from evals.dataset import load_cases
from scripts import measure_role_holdout as measure


SAVED = measure.ROOT / measure.SAVED_EVIDENCE
SAVED_SHA256 = "720ebbaf80b14122f5a4337603d7c10315dc2b5c402bb9aa264cc2fd8ef2e91e"


def _require_original_implementation(saved: dict, current: dict | None = None) -> None:
    current = current if current is not None else measure._implementation_hashes(measure.ROOT)
    recorded = saved["implementation_lf_sha256"]
    changed = sorted(name for name in set(recorded) | set(current) if recorded.get(name) != current.get(name))
    if changed:
        pytest.skip("Measured at a8f5706 with the frozen rule; implementation has changed "
                    f"({', '.join(changed)}). Reproduce from that commit; do not regenerate saved evidence.")


def test_saved_measurement_matches_fresh_output_byte_for_byte(tmp_path):
    _require_original_implementation(json.loads(SAVED.read_bytes()))
    fresh = tmp_path / "role-holdout-measurement.json"
    measure.main(["--output", str(fresh)])
    assert fresh.read_bytes() == SAVED.read_bytes()


def test_changed_implementation_skips_byte_replay_without_changing_evidence():
    saved = json.loads(SAVED.read_bytes())
    changed = dict(saved["implementation_lf_sha256"])
    changed["bill_lens/contract.py"] = "0" * 64
    with pytest.raises(pytest.skip.Exception, match="Measured at a8f5706"):
        _require_original_implementation(saved, changed)


def test_preserved_evidence_and_prediction_hashes_are_always_checked():
    raw = SAVED.read_bytes()
    assert sha256(raw).hexdigest() == SAVED_SHA256
    saved = json.loads(raw)
    prediction_bytes = (measure.ROOT / measure.PREDICTIONS).read_bytes()
    assert sha256(prediction_bytes).hexdigest() == saved["prediction_sha256"]


def test_all_49_items_and_r07_are_accounted_for_with_page_provenance():
    result = json.loads(SAVED.read_bytes())
    assert result["live_api_calls"] == 0
    assert result["prediction_commit"] == measure.PREDICTION_COMMIT
    assert result["input_manifest_sha256"] == measure.FROZEN_INPUT_MANIFEST_SHA256
    assert result["totals"] == {
        "correct_total": 9, "false_reviews": 6, "distractors_total": 40,
        "caught": 40, "missed": 0, "silent_false_acceptances": 0,
        "prediction_items": 49, "prediction_mismatches": 0,
    }
    assert len(result["per_case"]) == 10
    assert {row["case_id"] for row in result["per_case"]} == set(measure.CASE_NAMES)
    assert sum(row["correct"]["value"] is not None for row in result["per_case"]) == 9
    assert sum(len(row["distractors"]) for row in result["per_case"]) == 40
    assert result["r07_decision"] == {
        "case_id": "holdout_r07", "role_flags": [],
        "combined_flags": ["current_bill_amount_missing"], "status": "needs_review",
        "matches_label": True, "prediction_match": True,
    }
    cases = {case.name: case for case in load_cases(measure.ROOT / measure.DATASET)}
    for row in result["per_case"]:
        document = cases[row["case_id"]].document
        for item in ([row["correct"]] if row["correct"]["value"] is not None else []) + row["distractors"]:
            assert item["occurrences"]
            for occurrence in item["occurrences"]:
                page = document.pages[occurrence["page"] - 1]
                lines = page.text.splitlines()
                assert lines[occurrence["line_number"] - 1] == occurrence["line"]
                assert occurrence["previous_non_empty_line"] == next(
                    (line for line in reversed(lines[:occurrence["line_number"] - 1]) if line.strip()), "")
    assert result["prediction_mismatches"] == []


def test_every_input_hash_is_preserved_in_evidence():
    result = json.loads(SAVED.read_bytes())
    canonical = json.dumps(result["input_hashes"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert sha256(canonical).hexdigest() == result["input_manifest_sha256"]
    for case_name, files in result["input_hashes"].items():
        assert set(files) == set(measure.INPUT_FILES)
        for filename, digest in files.items():
            source = measure.ROOT / measure.DATASET / case_name / filename
            assert sha256(source.read_bytes()).hexdigest() == digest


def test_changed_role_case_value_is_rejected_with_file_hash_mismatch(tmp_path):
    dataset = tmp_path / "dataset"
    shutil.copytree(measure.ROOT / measure.DATASET, dataset)
    path = dataset / "holdout_r06" / "role_cases.json"
    contents = json.loads(path.read_bytes())
    contents["printed_distractors"][0]["value"] = "41.00"
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(ValueError, match=r"input hash mismatch: holdout_r06/role_cases\.json"):
        measure.build_evidence(dataset=dataset)


def test_missing_case_is_rejected_before_measurement(tmp_path):
    dataset = tmp_path / "dataset"
    shutil.copytree(measure.ROOT / measure.DATASET, dataset,
                    ignore=shutil.ignore_patterns("holdout_r10"))
    with pytest.raises(ValueError, match="missing or unexpected role-holdout case"):
        measure.build_evidence(dataset=dataset)


def test_cli_refuses_to_overwrite_output(tmp_path):
    output = tmp_path / "existing.json"
    output.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        measure.main(["--output", str(output)])
    assert output.read_text(encoding="utf-8") == "original"


def test_changed_implementation_refuses_replay_and_names_original_commit():
    saved = json.loads(SAVED.read_bytes())
    changed = dict(saved["implementation_lf_sha256"])
    changed["bill_lens/contract.py"] = "0" * 64
    with pytest.raises(ValueError, match="a8f5706.*do not regenerate"):
        measure._check_implementation(measure.ROOT, changed)
