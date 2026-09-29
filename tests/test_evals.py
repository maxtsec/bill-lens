from copy import deepcopy
from decimal import Decimal
import json
from typing import get_args

import pytest

from bill_lens.contract import ExtractionFields
from bill_lens.extraction import ExtractionErrorCode, FakeExtractor, ScriptedResponse, build_attempt
from bill_lens.extraction.openai_adapter import OpenAIConfigurationError
from evals import HARNESS_VERSION, SCORING_VERSION
from evals import compare, run
from evals.dataset import load_cases, manifest
from evals.pricing import planned_cost
from evals.scoring import FIELDS, OUTCOMES, score_attempt, score_fields
from scripts import live_openai_check
from tests.helpers import ROOT


@pytest.fixture
def cases():
    return load_cases(ROOT / "dataset")


def attempt(fields):
    return build_attempt(provider="fake", model="fake-v1", prompt_version="fixture-v1",
                         raw_response=json.dumps(fields), latency_ms=0)


def metadata(cases, repeats=1, **overrides):
    return {"run_id": "test-run", "harness_version": HARNESS_VERSION, "scoring_version": SCORING_VERSION,
            "started_at": "2026-09-29T00:00:00+00:00", "provider": "fake", "requested_model": "fake-v1",
            "reasoning_effort": None, "configured_prompt_version": "fixture-v1",
            "git": {"commit": "code-revision", "dirty": False},
            "dataset_git": {"commit": "dataset-revision", "dirty": False},
            "dataset_name": "dataset",
            "dataset": manifest(cases), "bill_count": len(cases), "repeats": repeats,
            "planned_attempts": len(cases) * repeats, "price_date": "2026-09-29", **overrides}


def fake(cases, overrides=None):
    return FakeExtractor({c.document.file_sha256: (overrides or {}).get(c.name, ScriptedResponse(c.label.fields.model_dump_json()))
                          for c in cases})


@pytest.mark.parametrize("case_index,field,value,outcome", [
    (1, "current_bill_amount", "132.66", "false_extraction"),
    (2, "current_bill_amount", "163.40", "wrong_value"),
    (3, "current_bill_amount", "4.00", "wrong_value"),
    (4, "stated_billing_days", 31, "wrong_value"),
    (0, "current_bill_amount", "108.070", "correct"),
    (0, "total_usage_kwh", "250.000", "correct"),
    (0, "retailer", "  EXAMPLE   ENERGY ", "correct"),
    (0, "retailer", "Example Energy Pty Ltd", "wrong_value"),
    (0, "retailer", None, "missing"),
    (0, "period_start", "2026-04-02", "wrong_value"),
    (0, "period_end", None, "missing"),
    (1, "current_bill_amount", None, "correct"),
])
def test_hand_authored_field_oracles(cases, case_index, field, value, outcome):
    label = cases[case_index].label
    predicted = label.fields.model_dump(mode="json") | {field: value}
    scored = score_attempt(attempt(predicted), label, cases[case_index].document)
    assert scored["field_outcomes"][field] == outcome
    assert set(scored["field_outcomes"]) == set(FIELDS)
    assert set(scored["field_outcomes"].values()) <= set(OUTCOMES)
    if case_index == 4:
        assert scored["flags"] == [] and scored["expected_flags"] == ["stated_days_mismatch"]
        assert not scored["flags_match"] and not scored["status_match"]
    if case_index == 2:
        # The printed amount due is now routed to review without repairing it.
        assert scored["flags"] == ["current_bill_amount_role_unconfirmed"]
        assert scored["status"] == "needs_review"
        assert not scored["flags_match"] and not scored["status_match"] and not scored["exact_bill_match"]


@pytest.mark.parametrize("rate,outcome,value_match,gst_match", [
    ({"value": "1.1023", "unit": "AUD/day", "gst_basis": "inclusive"}, "correct", True, True),
    ({"value": "1.1023", "unit": "AUD/day", "gst_basis": "exclusive"}, "wrong_value", True, False),
    ({"value": "110.23", "unit": "AUD/day", "gst_basis": "inclusive"}, "wrong_value", False, True),
    (None, "missing", None, None),
])
def test_supply_value_and_gst_are_separate_oracles(cases, rate, outcome, value_match, gst_match):
    expected = cases[0].label
    scored = score_attempt(attempt(expected.fields.model_dump(mode="json") | {"daily_supply_rate": rate}), expected, cases[0].document)
    assert scored["field_outcomes"]["daily_supply_rate"] == outcome
    assert scored["supply_components"] == {"rate_value": value_match, "gst_basis": gst_match}


def test_both_missing_rate_is_correct_but_components_unavailable(cases):
    expected = ExtractionFields.model_validate(cases[0].label.fields.model_dump(mode="json") | {"daily_supply_rate": None})
    result = score_fields(expected, expected)
    assert result["field_outcomes"]["daily_supply_rate"] == "correct"
    assert result["supply_components"] == {"rate_value": None, "gst_basis": None}
    result = score_fields(cases[0].label.fields, expected)
    assert result["field_outcomes"]["daily_supply_rate"] == "false_extraction"


@pytest.mark.parametrize("code", get_args(ExtractionErrorCode))
def test_scripted_errors_are_no_fields_and_not_false_review_success(cases, tmp_path, code):
    cases = cases[:1]  # Expected flags are empty; no fields must not earn a match.
    raw = 'invalid\x00\ud800 literal \\ud800'
    scripted = fake(cases, {cases[0].name: ScriptedResponse(raw, error_code=code)})
    summary = run.evaluate(cases, scripted, tmp_path / code, metadata(cases))
    saved = json.loads((tmp_path / code / "attempts.jsonl").read_text())
    assert saved["raw_response"] == raw and saved["predicted"] is None
    assert set(saved["field_outcomes"].values()) == {"no_fields"}
    assert saved["flags"] is None and saved["flags_match"] is False
    assert saved["status"] == "failed" and saved["status_match"] is False
    assert summary["metrics"]["attempt_outcomes"][code] == {"count": 1, "total": 1}
    for field in FIELDS:
        assert summary["metrics"]["fields"][field]["no_fields"] == {"count": 1, "total": 1}


def test_fake_harness_self_test_with_repeats(cases, tmp_path):
    out = tmp_path / "fake"
    summary = run.evaluate(cases, fake(cases), out, metadata(cases, repeats=3))
    assert summary["completed_attempts"] == {"count": 15, "total": 15}
    for field in FIELDS:
        assert summary["metrics"]["fields"][field]["correct"] == {"count": 15, "total": 15}
    for key in ("exact_bill_match", "flags_match", "status_match"):
        assert summary["metrics"][key] == {"count": 15, "total": 15}
    for component in ("rate_value", "gst_basis"):
        assert summary["metrics"]["supply_components"][component]["matched"] == {"count": 15, "total": 15}
    assert summary["metrics"]["attempt_outcomes"]["none"] == {"count": 15, "total": 15}
    assert summary["input_tokens"]["total"] is None  # Don't fabricate usage for fake.
    assert summary["cost"]["total_estimated_usd"] == "0"
    for per in summary["per_bill"].values():
        assert per["exact_bill_match"] == {"count": 3, "total": 3}
    records = [json.loads(line) for line in (out / "attempts.jsonl").read_text().splitlines()]
    assert len({(r["bill"], r["repeat"]) for r in records}) == 15
    assert all(r["pdf_sha256"] == summary["dataset"][r["bill"]]["pdf_sha256"] for r in records)


def test_report_and_summary_snapshot_for_mixed_repeats(cases, tmp_path):
    cases = cases[:1]
    good = cases[0].label.fields.model_dump(mode="json")
    replies = iter([attempt(good), attempt(good | {"current_bill_amount": "999.99"})])
    class Sequence:
        def extract(self, document):
            return next(replies)
    summary = run.evaluate(cases, Sequence(), tmp_path / "mixed", metadata(cases, repeats=2))
    assert summary["metrics"]["fields"]["current_bill_amount"] == {
        "correct": {"count": 1, "total": 2}, "wrong_value": {"count": 1, "total": 2},
        "missing": {"count": 0, "total": 2}, "false_extraction": {"count": 0, "total": 2}, "no_fields": {"count": 0, "total": 2},
    }
    assert summary["per_bill"]["bill_001"]["exact_bill_match"] == {"count": 1, "total": 2}
    report = (tmp_path / "mixed/report.md").read_text()
    for kind, digest in manifest(cases)["bill_001"].items():
        report = report.replace(digest, kind.upper())
    assert report == (ROOT / "tests/fixtures/eval-report.md").read_text()


@pytest.mark.parametrize("enabled,key", [(None, None), ("1", None), (None, "test-key"), ("0", "test-key")])
def test_live_gates_precede_files_and_client(enabled, key, monkeypatch):
    if enabled is not None:
        monkeypatch.setenv("BILL_LENS_LIVE", enabled)
    if key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    def forbidden(*args, **kwargs):
        pytest.fail("closed gates must prevent file reads and client construction")
    monkeypatch.setattr(run, "OpenAIExtractor", forbidden)
    monkeypatch.setattr(run, "load_cases", forbidden)
    with pytest.raises(SystemExit) as error:
        run.main(["--extractor", "openai", "--model", "gpt-5.4-mini"])
    assert error.value.code == 2


@pytest.mark.parametrize("extra", [["--repeats", "0"], ["--repeats", "-1"], ["--model", "gpt-5.4"]])
def test_invalid_fake_cli_configuration_is_rejected(extra):
    with pytest.raises(SystemExit):
        run.main(["--extractor", "fake", *extra])


def test_fake_cli_creates_artifacts_without_client_or_key(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("fake CLI must not construct a provider client")
    monkeypatch.setattr(run, "OpenAIExtractor", forbidden)
    out = tmp_path / "cli"
    assert run.main(["--extractor", "fake", "--output", str(out)]) == 0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["metrics"]["exact_bill_match"] == {"count": 5, "total": 5}
    assert len(summary["dataset"]) == 5 and summary["git"]["commit"]
    assert summary["configured_prompt_version"] == "fixture-v1" and summary["reasoning_effort"] is None
    assert '"planned_calls": 0' in capsys.readouterr().out
    original = (out / "attempts.jsonl").read_bytes()
    with pytest.raises(SystemExit):
        run.main(["--extractor", "fake", "--output", str(out)])
    assert (out / "attempts.jsonl").read_bytes() == original


def test_live_plan_precedes_stub_and_configuration_error_aborts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BILL_LENS_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    calls, closed = [], []
    class Stub:
        prompt_version = "extract-v2"
        def __init__(self, **kwargs):
            printed = capsys.readouterr().out
            assert '"planned_calls": 10' in printed and '"price_date": "2026-09-29"' in printed
            assert "NOT a spending cap" in printed
        def extract(self, document):
            calls.append(document.file_sha256)
            if len(calls) == 2:
                raise OpenAIConfigurationError("request_parameters_or_schema")
            return build_attempt(provider="openai", model="gpt-5.4-mini-2026-03-17", prompt_version="extract-v2",
                                 raw_response="bad JSON", latency_ms=20, input_tokens=100, output_tokens=10)
        def close(self):
            closed.append(True)
    monkeypatch.setattr(run, "OpenAIExtractor", Stub)
    out = tmp_path / "aborted"
    assert run.main(["--extractor", "openai", "--model", "gpt-5.4-mini", "--repeats", "2", "--output", str(out)]) == 1
    summary = json.loads((out / "summary.json").read_text())
    assert len(calls) == 2 and closed == [True]
    assert summary["completed"] is False and summary["completed_attempts"] == {"count": 1, "total": 10}
    assert summary["abort_reason"] == "OpenAIConfigurationError:request_parameters_or_schema"
    assert summary["cost"]["total_estimated_usd"] is None
    assert summary["input_tokens"]["total"] is None
    assert summary["metrics"]["attempt_outcomes"]["invalid_output"] == {"count": 1, "total": 1}
    assert all(summary["metrics"]["fields"][name]["no_fields"]["count"] == 1 for name in FIELDS)
    assert len((out / "attempts.jsonl").read_text().splitlines()) == 1
    with pytest.raises(ValueError, match="incomplete"):
        compare.load_summary(out)


def test_cost_plan_scales_with_calls_and_uses_dated_rates(cases):
    once = planned_cost(cases, 1, "gpt-5.4-mini")
    twice = planned_cost(cases, 2, "gpt-5.4-mini")
    assert once["planned_calls"] == 5 and twice["planned_calls"] == 10
    assert Decimal(twice["estimated_cost_usd"]) == 2 * Decimal(once["estimated_cost_usd"])
    assert once["price_date"] == "2026-09-29"


def test_missing_usage_and_unknown_resolved_model_keep_cost_unknown(cases, tmp_path):
    cases = cases[:3]
    replies = iter([
        build_attempt(provider="openai", model=model, prompt_version="extract-v2",
                      raw_response=case.label.fields.model_dump_json(), input_tokens=inp,
                      output_tokens=out, latency_ms=latency)
        for case, model, inp, out, latency in zip(cases,
            ["gpt-5.4-mini", "gpt-5.4-mini", "unpriced-model"], [100, None, 200], [10, 20, 30], [30, 10, 20])
    ])
    class Stub:
        def extract(self, document):
            return next(replies)
    summary = run.evaluate(cases, Stub(), tmp_path / "usage", metadata(
        cases, provider="openai", requested_model="gpt-5.4-mini", reasoning_effort="low"))
    assert summary["input_tokens"] == {"known_total": 300, "total": None, "calls_with_usage": {"count": 2, "total": 3}}
    assert summary["output_tokens"]["total"] == 60
    assert summary["cost"]["total_estimated_usd"] is None
    assert summary["cost"]["calls_with_estimate"] == {"count": 1, "total": 3}
    assert Decimal(summary["cost"]["known_estimated_usd"]) == Decimal("0.000120")
    assert summary["latency_ms"] == {"median": 20, "max": 30}


def test_compare_improvement_regression_and_unchanged(cases, tmp_path):
    wrong = cases[1].label.fields.model_dump(mode="json") | {"current_bill_amount": "132.66"}
    run.evaluate(cases, fake(cases, {"bill_002": ScriptedResponse(json.dumps(wrong))}), tmp_path / "a", metadata(cases))
    run.evaluate(cases, fake(cases), tmp_path / "b", metadata(cases))
    a, b = compare.load_summary(tmp_path / "a"), compare.load_summary(tmp_path / "b")
    forward, backward = compare.compare_runs(a, b), compare.compare_runs(b, a)
    assert "current_bill_amount | 4/5 | 5/5 | improved" in forward
    assert "current_bill_amount | 5/5 | 4/5 | regressed" in backward
    assert "bill_002 | exact_bill_match | 0/1 | 1/1 | improved" in forward
    assert "retailer | 5/5 | 5/5 | unchanged" in forward
    assert "not evidence of real-world accuracy or statistical significance" in forward
    assert compare.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    b["git"]["dirty"] = True
    assert "WARNING: dirty" in compare.compare_runs(a, b)


def test_compare_header_identifies_both_runs_and_multiple_changes(cases, tmp_path):
    a = run.evaluate(cases[:1], fake(cases[:1]), tmp_path / "a", metadata(cases[:1]))
    b = deepcopy(a)
    b.update(provider="openai", requested_model="requested-b", resolved_models=["resolved-b"],
             configured_prompt_version="configured-b", prompt_versions=["observed-b"], reasoning_effort="low",
             git={"commit": "commit-b", "dirty": False})
    report = compare.compare_runs(a, b)
    header = report.split("## Per-field correctness")[0]
    assert "| A | fake | fake-v1 | fake-v1 | fixture-v1 | fixture-v1 | None | code-revision |" in header
    assert "| B | openai | requested-b | resolved-b | configured-b | observed-b | low | commit-b |" in header
    assert "Changed dimensions: provider, model, prompt version, effort, commit." in header
    assert "WARNING: multiple configuration dimensions differ" in header
    assert "cannot be attributed to a single variable" in header
    identical = compare.compare_runs(a, a)
    assert "Changed dimensions: none." in identical
    assert "WARNING: multiple" not in identical


@pytest.mark.parametrize("updates,dimension", [
    ({"provider": "other"}, "provider"),
    ({"requested_model": "other"}, "model"),
    ({"resolved_models": ["other"]}, "model"),
    ({"requested_model": "other", "resolved_models": ["other-snapshot"]}, "model"),
    ({"configured_prompt_version": "other"}, "prompt version"),
    ({"prompt_versions": ["other"]}, "prompt version"),
    ({"configured_prompt_version": "other", "prompt_versions": ["other"]}, "prompt version"),
    ({"reasoning_effort": "high"}, "effort"),
    ({"git": {"commit": "other", "dirty": False}}, "commit"),
])
def test_compare_warns_only_after_a_second_dimension_changes(cases, tmp_path, updates, dimension):
    a = run.evaluate(cases[:1], fake(cases[:1]), tmp_path / "a", metadata(cases[:1]))
    b = deepcopy(a)
    b.update(updates)
    report = compare.compare_runs(a, b)
    assert f"Changed dimensions: {dimension}." in report
    assert "WARNING: multiple" not in report
    # Exactly two dimensions cross the warning threshold, even if correctness
    # is identical. Model/prompt configured+observed pairs count only once.
    b.update({"reasoning_effort": "other"} if dimension != "effort" else {"provider": "other"})
    assert "WARNING: multiple configuration dimensions differ" in compare.compare_runs(a, b)


def test_compare_per_bill_error_changes_survive_equal_aggregate_scores(cases, tmp_path):
    cases = [cases[0], cases[2]]  # Both expect processed, with no review flags.
    def replies(values):
        return {case.name: ScriptedResponse(json.dumps(case.label.fields.model_dump(mode="json") | {"retailer": value}))
                for case, value in zip(cases, values)}
    a = run.evaluate(cases, fake(cases, replies([None, "Wrong Retailer"])), tmp_path / "a", metadata(cases, repeats=3))
    b = run.evaluate(cases, fake(cases, replies(["Wrong Retailer", None])), tmp_path / "b", metadata(cases, repeats=3))
    assert a["metrics"] == b["metrics"]  # Aggregate counts hide the swap.
    report = compare.compare_runs(a, b)
    first = next(line for line in report.splitlines() if line.startswith("| bill_001 | retailer |"))
    second = next(line for line in report.splitlines() if line.startswith("| bill_003 | retailer |"))
    assert "| 0/3 | 0/3 | unchanged |" in first and "| 0/3 | 0/3 | unchanged |" in second
    assert "wrong_value: 0/3 -> 3/3; missing: 3/3 -> 0/3" in first
    assert "wrong_value: 3/3 -> 0/3; missing: 0/3 -> 3/3" in second
    assert "not paired attempt transitions" in report


def test_compare_per_bill_false_extraction_and_no_fields_counts(cases, tmp_path):
    cases = cases[1:2]
    invented = cases[0].label.fields.model_dump(mode="json") | {"current_bill_amount": "132.66"}
    a = run.evaluate(cases, fake(cases, {"bill_002": ScriptedResponse(json.dumps(invented))}),
                     tmp_path / "a", metadata(cases, repeats=3))
    b = run.evaluate(cases, fake(cases, {"bill_002": ScriptedResponse("", error_code="timeout")}),
                     tmp_path / "b", metadata(cases, repeats=3))
    row = next(line for line in compare.compare_runs(a, b).splitlines()
               if line.startswith("| bill_002 | current_bill_amount |"))
    assert "| 0/3 | 0/3 | unchanged |" in row
    assert "false_extraction: 3/3 -> 0/3; no_fields: 0/3 -> 3/3" in row


@pytest.mark.parametrize("difference", ["pdf", "label", "scoring_version", "harness_version", "repeats"])
def test_compare_refuses_incomparable_runs(cases, tmp_path, difference):
    a = run.evaluate(cases, fake(cases), tmp_path / "a", metadata(cases))
    b = deepcopy(a)
    if difference in {"pdf", "label"}:
        b["dataset"]["bill_001"][difference + "_sha256"] = "changed"
    else:
        b[difference] = "changed"
    with pytest.raises(ValueError, match="incomparable"):
        compare.compare_runs(a, b)


def test_compare_rejects_corrupt_denominators(cases, tmp_path):
    run.evaluate(cases, fake(cases), tmp_path / "a", metadata(cases))
    path = tmp_path / "a/summary.json"
    data = json.loads(path.read_text())
    data["metrics"]["fields"]["retailer"]["correct"]["total"] = 0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="denominator"):
        compare.load_summary(path)


def test_smoke_uses_the_same_scoring_function():
    from evals.scoring import field_matches
    assert live_openai_check.field_matches is field_matches


def test_old_scoring_artifacts_are_not_silently_reinterpreted(cases, tmp_path):
    assert SCORING_VERSION == "3"
    path = ROOT / "docs/learning/evidence/retailer-brand-v4/v4-dev"
    old = json.loads((path / "summary.json").read_text())
    assert old["scoring_version"] == "1"
    with pytest.raises(ValueError, match="unsupported harness/scoring version"):
        compare.load_summary(path)
    new = run.evaluate(cases, fake(cases), tmp_path / "new", metadata(cases, repeats=3))
    with pytest.raises(ValueError, match="different scoring_version"):
        compare.compare_runs(old, new)
    presence_only = new | {"scoring_version": "2"}
    with pytest.raises(ValueError, match="different scoring_version"):
        compare.compare_runs(presence_only, new)
    historical = tmp_path / "presence-only.json"
    historical.write_text(json.dumps(presence_only), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported harness/scoring version"):
        compare.load_summary(historical)
