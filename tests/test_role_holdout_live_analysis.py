from decimal import Decimal
from dataclasses import replace
from hashlib import sha256
import json
import shutil

import pytest

from bill_lens.extraction import build_attempt
from evals import run
from evals.budget import Budget
from evals.dataset import load_cases
from evals.role_cases import RoleCase
from scripts import analyse_role_holdout_live as analysis
from tests.test_evals import metadata


class RoleStub:
    prompt_version = "extract-v4"

    def __init__(self, cases, values=None, failure=None):
        self.cases = {case.document.file_sha256: case for case in cases}
        self.values = values or {}
        self.failure = failure

    def extract(self, document):
        case = self.cases[document.file_sha256]
        fields = case.label.fields.model_dump(mode="json")
        if case.name in self.values:
            fields["current_bill_amount"] = self.values[case.name]
        return build_attempt(provider="openai", model="gpt-5.4-mini-2026-03-17",
                             prompt_version="extract-v4", raw_response=json.dumps(fields) if not self.failure else None,
                             error_code=self.failure, latency_ms=0, input_tokens=100, output_tokens=10)


def prepare(tmp_path, values=None, failure=None):
    cases = load_cases(analysis.DATASET)
    output = tmp_path / "run"
    run.evaluate(cases, RoleStub(cases, values, failure), output,
                 metadata(cases, 3, provider="openai", requested_model="gpt-5.4-mini",
                          configured_prompt_version="extract-v4", reasoning_effort="low"),
                 budget=Budget(Decimal("0.30"), provider="openai", model="gpt-5.4-mini"))
    return output


@pytest.mark.parametrize("value,category,correct,sign", [
    (None, "null", True, None),
    ("112.20", "distractor:amount_due", False, "signed"),
    ("-5.00", "distractor:credit", False, "signed"),
    ("5.00", "distractor:credit", False, "unsigned_magnitude"),
    ("87.20", "other_wrong", False, None),
])
def test_r07_categories_and_credit_signs(value, category, correct, sign):
    annotation = RoleCase.model_validate_json((analysis.DATASET / "holdout_r07/role_cases.json").read_bytes())
    result = analysis.classify_amount(value, None, annotation)
    assert result["category"] == category and result["correct"] is correct
    if sign:
        assert result["distractor_matches"][0]["matched_sign"] == sign


def test_correct_decimal_equivalence_has_priority_and_missing_is_not_correct():
    annotation = RoleCase(current_bill_amount="90.15", current_label="Current charges", shape="A",
                          printed_distractors=[])
    assert analysis.classify_amount("90.150", "90.15", annotation)["category"] == "correct"
    assert not analysis.classify_amount(None, "90.15", annotation)["correct"]


def test_all_matching_roles_are_retained_instead_of_arbitrarily_selected():
    annotation = RoleCase(current_bill_amount="90.15", current_label="Current charges", shape="A",
                          printed_distractors=[{"value": "40", "printed_label": "Balance", "role": "previous_balance"},
                                               {"value": "40", "printed_label": "Amount due", "role": "amount_due"}])
    result = analysis.classify_amount("40", "90.15", annotation)
    assert result["category"] == "distractor:amount_due+previous_balance"
    assert len(result["distractor_matches"]) == 2


def test_full_correct_stub_run_keeps_27_and_3_denominators_and_false_review_cost(tmp_path):
    source = prepare(tmp_path)
    before = {p.name: sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    result = analysis.analyse(source)
    assert result["completed"] and result["totals"]["observed_attempts"] == 30
    assert result["printed_current"]["correct"] == {"count": 27, "total": 27}
    assert result["printed_current"]["false_review"] == {"count": 18, "total": 27}
    assert result["printed_current"]["wrong_value"] == {"count": 0, "total": 27}
    assert result["r07"]["categories"] == {"null": 3}
    assert result["r07"]["correct"] == {"count": 3, "total": 3}
    assert sum(s["observed_attempts"] for s in result["per_shape"].values()) == 30
    assert all(s == {"correct": 30, "total": 30} for s in result["other_fields"].values())
    output = tmp_path / "analysis"
    analysis.main([str(source), "--output", str(output)])
    report = (output / "report.md").read_text()
    assert "27/27" in report and "18/27" in report and "Shape E" in report
    assert before == {p.name: sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    with pytest.raises(FileExistsError):
        analysis.main([str(source), "--output", str(output)])


def test_wrong_due_unprinted_value_and_unsigned_credit_are_counted_with_flags(tmp_path):
    source = prepare(tmp_path, {"holdout_r01": "999.99", "holdout_r07": "112.20",
                                "holdout_r08": "5.00"})
    result = analysis.analyse(source)
    assert result["totals"]["wrong_value"] == {"count": 9, "total": 30}
    assert result["totals"]["caught"] == {"count": 9, "total": 30}
    assert result["totals"]["silent_false_acceptance"]["count"] == 0
    r07 = next(r for r in result["per_attempt"] if r["bill"] == "holdout_r07")
    assert r07["category"] == "distractor:amount_due" and r07["occurrences"]
    r01 = next(r for r in result["per_attempt"] if r["bill"] == "holdout_r01")
    assert r01["category"] == "other_wrong" and r01["current_amount_presence_flag"]


def test_silent_false_acceptance_is_nonzero_for_processed_wrong_numeric_value(tmp_path):
    # Stub response, not a live result. r04's unsigned credit magnitude 10.00
    # also occurs as 10% in a current-charges label, so the frozen rule confirms
    # it despite the handwritten current total being 95.60. Do not alter the
    # rule to manufacture a flag: this test needs a real processed wrong value.
    source = prepare(tmp_path, {"holdout_r04": "10.00"})
    result = analysis.analyse(source)
    wrong = [row for row in result["per_attempt"] if row["bill"] == "holdout_r04"]
    assert len(wrong) == 3
    assert all(row["wrong_value"] and row["status"] == "processed" and row["flags"] == [] for row in wrong)
    assert all(row["silent_false_acceptance"] and not row["caught"] for row in wrong)
    assert all(row["category"] == "distractor:credit" for row in wrong)
    assert result["totals"]["silent_false_acceptance"] == {"count": 3, "total": 30}
    assert result["printed_current"]["silent_false_acceptance"] == {"count": 3, "total": 27}
    assert result["per_case"]["holdout_r04"]["silent_false_acceptance"] == {"count": 3, "total": 3}
    assert result["per_shape"]["D"]["silent_false_acceptance"] == {"count": 3, "total": 3}
    report = analysis.render_report(result)
    assert "| holdout_r04 | 3/3 | 0/3 | 3/3 | 0/3 | 3/3 | 0/3 | 0/3 |" in report


@pytest.mark.parametrize("revision", [
    {"commit": "uncommitted-stub", "dirty": True},
    {"commit": "unknown-state-stub", "dirty": None},
    {"commit": None, "dirty": False},
])
def test_analysis_refuses_dirty_unknown_or_missing_commit(tmp_path, revision):
    source = prepare(tmp_path)
    path = source / "summary.json"
    summary = json.loads(path.read_text())
    summary["git"] = revision
    path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="run must record a clean commit"):
        analysis.analyse(source)


def test_r07_reconstructed_amount_is_explicitly_reported(tmp_path):
    result = analysis.analyse(prepare(tmp_path, {"holdout_r07": "87.20"}))
    r07 = [r for r in result["per_attempt"] if r["bill"] == "holdout_r07"]
    assert all(r["r07_computed_87_20"] and r["current_amount_presence_flag"] for r in r07)
    assert "unprinted 87.20" in analysis.render_report(result)


def test_failed_attempts_are_not_misclassified_as_null_or_removed(tmp_path):
    result = analysis.analyse(prepare(tmp_path, failure="timeout"))
    assert result["totals"]["categories"] == {"no_fields": 30}
    assert result["printed_current"]["no_fields"] == {"count": 27, "total": 27}
    assert result["r07"]["correct"] == {"count": 0, "total": 3}
    assert result["totals"]["wrong_value"]["count"] == 0


def test_partial_unknown_usage_run_reports_observed_and_planned_denominators(tmp_path):
    cases = load_cases(analysis.DATASET)
    class MissingUsage(RoleStub):
        def extract(self, document):
            return replace(super().extract(document), input_tokens=None)
    output = tmp_path / "partial"
    from evals.budget import BudgetStopped
    with pytest.raises(BudgetStopped, match="usage_or_model_unknown"):
        run.evaluate(cases, MissingUsage(cases), output,
                     metadata(cases, 3, provider="openai", requested_model="gpt-5.4-mini",
                              configured_prompt_version="extract-v4", reasoning_effort="low"),
                     budget=Budget(Decimal("0.30"), provider="openai", model="gpt-5.4-mini"))
    result = analysis.analyse(output)
    assert not result["completed"]
    assert result["totals"]["observed_attempts"] == 1 and result["totals"]["planned_attempts"] == 30
    assert result["printed_current"]["correct"] == {"count": 1, "total": 1}
    assert result["printed_current"]["planned_attempts"] == 27
    assert result["r07"]["observed_attempts"] == 0 and result["r07"]["planned_attempts"] == 3


@pytest.mark.parametrize("filename", ["bill.pdf", "expected.json", "role_cases.json"])
def test_any_changed_input_refused_against_pr_c_evidence(tmp_path, filename):
    dataset = tmp_path / "dataset"
    shutil.copytree(analysis.DATASET, dataset)
    with (dataset / "holdout_r01" / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="input hash mismatch"):
        analysis.verified_inputs(dataset)


@pytest.mark.parametrize("tamper", ["duplicate", "missing", "flags", "pdf_hash", "settings", "budget", "summary_metrics"])
def test_corrupt_run_provenance_coverage_scoring_or_ledger_is_rejected(tmp_path, tamper):
    source = prepare(tmp_path)
    path = source / "attempts.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if tamper == "duplicate":
        rows[1] = rows[0]
    elif tamper == "missing":
        rows.pop()
    elif tamper == "flags":
        rows[0]["flags"] = [analysis.ROLE_FLAG]
    elif tamper == "pdf_hash":
        rows[0]["pdf_sha256"] = "0" * 64
    elif tamper == "settings":
        rows[0]["prompt_version"] = "extract-v3"
    elif tamper == "budget":
        budget = json.loads((source / "budget.json").read_text())
        budget["calls"][0]["reserved_usd"] = "0"
        (source / "budget.json").write_text(json.dumps(budget))
        summary = json.loads((source / "summary.json").read_text())
        summary["budget"] = budget
        (source / "summary.json").write_text(json.dumps(summary))
    else:
        summary = json.loads((source / "summary.json").read_text())
        summary["metrics"]["exact_bill_match"]["count"] = 0
        (source / "summary.json").write_text(json.dumps(summary))
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError):
        analysis.analyse(source)
