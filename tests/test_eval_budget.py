from decimal import Decimal
import json

import pytest

from bill_lens.extraction import build_attempt
from bill_lens.extraction.openai_adapter import OpenAIConfigurationError
from bill_lens.pdf_text import PageText, PdfText
from evals import compare, run
from evals.budget import Budget, BudgetStopped, REQUEST_BYTE_LIMIT, request_bytes, verify_ledger
from evals.dataset import load_cases
from tests.helpers import ROOT
from tests.test_evals import metadata


@pytest.fixture
def cases():
    return load_cases(ROOT / "dataset")[:1]


class Stub:
    prompt_version = "extract-v4"

    def __init__(self, case, *, inputs=100, outputs=10, model="gpt-5.4-mini", error=None):
        self.case, self.inputs, self.outputs, self.model, self.error = case, inputs, outputs, model, error
        self.calls = 0

    def extract(self, document):
        self.calls += 1
        if self.error:
            raise self.error
        return build_attempt(provider="openai", model=self.model, prompt_version=self.prompt_version,
                             raw_response=self.case.label.fields.model_dump_json(), latency_ms=0,
                             input_tokens=self.inputs, output_tokens=self.outputs)


def live_metadata(cases, repeats=1):
    return metadata(cases, repeats, provider="openai", requested_model="gpt-5.4-mini",
                    configured_prompt_version="extract-v4", reasoning_effort="low")


def records(output):
    return [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]


def test_budget_stops_before_first_call_and_retains_partial_artifacts(cases, tmp_path):
    stub, output = Stub(cases[0]), tmp_path / "stopped"
    with pytest.raises(BudgetStopped, match="budget_exhausted"):
        run.evaluate(cases, stub, output, live_metadata(cases),
                     budget=Budget(Decimal("0.0430079"), provider="openai", model=stub.model))
    assert stub.calls == 0 and records(output) == []
    summary = json.loads((output / "summary.json").read_text())
    assert summary["completed"] is False
    assert summary["abort_reason"] == "BudgetStopped:budget_exhausted"
    assert summary["budget"]["calls"] == []
    assert "complete=False" in (output / "report.md").read_text()
    with pytest.raises(ValueError, match="incomplete"):
        compare.load_summary(output)


def test_exact_reservation_boundary_is_allowed_and_settled(cases, tmp_path):
    stub, output = Stub(cases[0]), tmp_path / "exact"
    budget = Budget(Decimal("0.043008"), provider="openai", model=stub.model)
    summary = run.evaluate(cases, stub, output, live_metadata(cases), budget=budget)
    assert stub.calls == 1 and summary["completed"]
    row = budget.data["calls"][0]
    assert row["reserved_usd"] == "0.043008"
    assert Decimal(row["settled_usd"]) == Decimal("0.00012")
    assert Decimal(budget.data["spent_usd"]) == Decimal("0.00012")
    verify_ledger(budget.data, records(output), completed=True)


def test_actual_settlement_releases_allowance_but_next_call_cannot_overspend(cases, tmp_path):
    stub, output = Stub(cases[0]), tmp_path / "next"
    budget = Budget(Decimal("0.043127"), provider="openai", model=stub.model)
    with pytest.raises(BudgetStopped, match="budget_exhausted"):
        run.evaluate(cases, stub, output, live_metadata(cases, 3), budget=budget)
    assert stub.calls == 1  # 0.00012 + 0.043008 > cap.
    assert len(records(output)) == 1 and budget.data["stopped_before"]["repeat"] == 2
    verify_ledger(budget.data, records(output), completed=False)


@pytest.mark.parametrize("inputs,outputs,model,reason", [
    (None, 10, "gpt-5.4-mini", "usage_or_model_unknown"),
    (100, None, "gpt-5.4-mini", "usage_or_model_unknown"),
    (100, 10, "other-model", "usage_or_model_unknown"),
    (32769, 10, "gpt-5.4-mini", "usage_exceeds_reservation"),
    (100, 4097, "gpt-5.4-mini", "usage_exceeds_reservation"),
])
def test_unknown_or_outside_allowance_stops_without_refunding_reservation(cases, tmp_path, inputs, outputs, model, reason):
    stub = Stub(cases[0], inputs=inputs, outputs=outputs, model=model)
    budget = Budget(Decimal("0.30"), provider="openai", model="gpt-5.4-mini")
    output = tmp_path / "unknown"
    with pytest.raises(BudgetStopped, match=reason):
        run.evaluate(cases, stub, output, live_metadata(cases, 3), budget=budget)
    assert stub.calls == 1 and len(records(output)) == 1
    assert budget.data["spent_usd"] == "0.043008"
    assert budget.data["calls"][0]["state"] == "reserved_unknown"
    verify_ledger(budget.data, records(output), completed=False)


@pytest.mark.parametrize("error", [OpenAIConfigurationError("authentication"), RuntimeError("private"), KeyboardInterrupt()])
def test_raised_call_retains_reservation_without_fabricating_attempt(cases, tmp_path, error):
    stub, output = Stub(cases[0], error=error), tmp_path / "raised"
    budget = Budget(Decimal("0.30"), provider="openai", model=stub.model)
    with pytest.raises(type(error)):
        run.evaluate(cases, stub, output, live_metadata(cases), budget=budget)
    assert stub.calls == 1 and records(output) == []
    assert budget.data["calls"][0]["state"] == "reserved"
    assert budget.data["spent_usd"] == "0.043008"
    summary = json.loads((output / "summary.json").read_text())
    assert not summary["completed"] and summary["abort_reason"]
    assert "private" not in json.dumps(summary)
    verify_ledger(budget.data, records(output), completed=False)


def test_oversized_request_is_refused_before_call(cases, tmp_path):
    budget = Budget(Decimal("0.30"), provider="openai", model="gpt-5.4-mini")
    document = PdfText("a" * 64, (PageText(1, "x" * REQUEST_BYTE_LIMIT),))
    assert request_bytes(document) > REQUEST_BYTE_LIMIT
    with pytest.raises(BudgetStopped, match="request_allowance_exceeded"):
        budget.reserve("oversized", 1, document, tmp_path)
    assert budget.data["calls"] == []


def test_reservation_is_on_disk_before_extractor_runs(cases, tmp_path):
    output = tmp_path / "before"
    class ReadingStub(Stub):
        def extract(self, document):
            ledger = json.loads((output / "budget.json").read_text())
            assert ledger["calls"][-1]["state"] == "reserved"
            assert ledger["spent_usd"] == "0.043008"
            return super().extract(document)
    stub = ReadingStub(cases[0])
    run.evaluate(cases, stub, output, live_metadata(cases),
                 budget=Budget(Decimal("0.30"), provider="openai", model=stub.model))


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "oops"])
def test_invalid_budget_cli_rejected_before_clients(value, monkeypatch):
    monkeypatch.setattr(run, "OpenAIExtractor", lambda **kwargs: pytest.fail("client constructed"))
    with pytest.raises(SystemExit):
        run.main(["--extractor", "fake", "--budget-usd", value])


def test_budgeted_live_cli_rejects_dirty_checkout_without_client(monkeypatch, tmp_path):
    monkeypatch.setenv("BILL_LENS_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    monkeypatch.setattr(run, "git_revision", lambda root: {"commit": "stub", "dirty": True})
    monkeypatch.setattr(run, "OpenAIExtractor", lambda **kwargs: pytest.fail("client constructed"))
    with pytest.raises(SystemExit):
        run.main(["--extractor", "openai", "--model", "gpt-5.4-mini", "--budget-usd", "0.30",
                  "--output", str(tmp_path / "dirty")])


def test_fake_budget_cli_costs_zero_without_key_or_client(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "OpenAIExtractor", lambda **kwargs: pytest.fail("client constructed"))
    output = tmp_path / "fake"
    assert run.main(["--extractor", "fake", "--budget-usd", "0.0001", "--output", str(output)]) == 0
    ledger = json.loads((output / "budget.json").read_text())
    assert len(ledger["calls"]) == 5 and Decimal(ledger["spent_usd"]) == 0
    verify_ledger(ledger, records(output), completed=True)


def test_budgeted_live_cli_returns_nonzero_and_closes_stub_on_budget_abort(cases, tmp_path, monkeypatch):
    monkeypatch.setenv("BILL_LENS_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
    monkeypatch.setattr(run, "git_revision", lambda root: {"commit": "stub-clean-commit", "dirty": False})
    stub, closed = Stub(cases[0]), []
    stub.close = lambda: closed.append(True)
    monkeypatch.setattr(run, "OpenAIExtractor", lambda **kwargs: stub)
    output = tmp_path / "cli-abort"
    assert run.main(["--extractor", "openai", "--model", "gpt-5.4-mini", "--budget-usd", "0.01",
                     "--output", str(output)]) == 1
    assert stub.calls == 0 and closed == [True]
    summary = json.loads((output / "summary.json").read_text())
    assert summary["git"]["dirty"] is False and not summary["completed"]
    assert summary["budget"]["spent_usd"] == "0"
