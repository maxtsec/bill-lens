"""Offline holdout integrity; these tests do not measure model accuracy."""

from decimal import Decimal, ROUND_HALF_UP
from importlib.resources import files
import json
from pathlib import Path
import re

import pytest

from bill_lens.extraction import build_attempt
from bill_lens.extraction.openai_adapter import structured_schema
from bill_lens.validation import derive_flags, derive_status
from evals import compare, run
from evals.dataset import load_cases
from evals.reporting import render_report
from evals.scoring import FIELDS
from tests.helpers import ROOT, CASES

HOLDOUT = ROOT / "dataset/holdout"
NAMES = [f"holdout_{n:03}" for n in range(1, 7)]


@pytest.fixture(scope="module")
def heldout():
    return {case.name: case for case in load_cases(HOLDOUT)}


@pytest.mark.parametrize("name", NAMES)
def test_complete_labels_match_manual_flags_and_printed_values(heldout, name):
    case = heldout[name]
    label, fields = case.label, case.label.fields
    assert len(case.document.pages) == 1
    text = case.document.pages[0].text
    assert "SYNTHETIC SAMPLE - NOT PAYABLE" in text
    assert all(getattr(fields, key) is not None for key in FIELDS)
    assert fields.retailer in text
    assert derive_flags(fields) == set(label.expected_flags) == set()
    assert label.expected_status == derive_status(label.expected_flags) == "processed"
    assert re.search(r"Billing period \(inclusive\): (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", text).groups() == (
        fields.period_start.isoformat(), fields.period_end.isoformat())
    days = int(re.search(r"Billing days: (\d+)", text)[1])
    assert days == fields.stated_billing_days == (fields.period_end - fields.period_start).days + 1
    usage = re.search(r"Total imported usage: ([0-9.]+) kWh", text)[1]
    assert Decimal(usage) == Decimal(fields.total_usage_kwh)
    printed_rate = re.search(r"Supply: \d+ days at AUD ([0-9.]+)/day", text)[1]
    assert fields.daily_supply_rate.value == printed_rate
    assert fields.daily_supply_rate.unit == "AUD/day"
    assert "All rates and charges are GST inclusive." in text
    assert fields.daily_supply_rate.gst_basis == "inclusive"
    amount = re.search(r"Current bill amount: AUD ([0-9.]+)", text)[1]
    assert amount == fields.current_bill_amount


@pytest.mark.parametrize("name", NAMES)
def test_pdf_charge_lines_reconcile_independently_of_builder(heldout, name):
    case = heldout[name]
    text = case.document.pages[0].text
    usage_q, usage_rate, usage_charge = map(Decimal, re.search(
        r"Usage: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh = AUD ([0-9.]+)", text).groups())
    supply_q, supply_rate, supply_charge = map(Decimal, re.search(
        r"Supply: ([0-9.]+) days at AUD ([0-9.]+)/day = AUD ([0-9.]+)", text).groups())
    assert (usage_q * usage_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == usage_charge
    assert (supply_q * supply_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == supply_charge
    assert usage_q == Decimal(case.label.fields.total_usage_kwh)
    assert supply_q == case.label.fields.stated_billing_days
    current = Decimal(re.search(r"Current bill amount: AUD ([0-9.]+)", text)[1])
    due = Decimal(re.search(r"Amount due: AUD ([0-9.]+)", text)[1])
    assert usage_charge + supply_charge == current == due == Decimal(case.label.fields.current_bill_amount)


@pytest.mark.parametrize("name,source_fragment,expected_name", [
    ("holdout_001", "QSP", "Quillstone Sample Power"),
    ("holdout_002", "QVX", "QVX"),
    ("holdout_003", "Your distributor: Glass Orchard Sample Networks", "Vellum Kite Sample Energy"),
    ("holdout_004", "Issued by Mosaic Finch Sample Retail Pty Ltd | ABN 00 000 000 000", "Mosaic Finch Sample Power"),
    ("holdout_005", "Issued by Parchment Vale Sample Retail Pty Ltd", "Parchment Vale Sample Retail Pty Ltd"),
    ("holdout_006", "Cobalt Loom Sample Group", "Copper Wren Sample Electricity"),
])
def test_retailer_scenarios_are_actually_printed(heldout, name, source_fragment, expected_name):
    text = heldout[name].document.pages[0].text
    assert source_fragment in text and expected_name in text
    assert heldout[name].label.fields.retailer == expected_name
    if name == "holdout_001":
        assert text.index("Current bill amount") < text.index(expected_name) < text.index("QSP")
    if name == "holdout_004":
        assert "Legal notice" in text and "Pty Ltd" not in expected_name and "ABN" not in expected_name
    if name == "holdout_005":
        assert "ABN 00 000 000 000" in text and expected_name.endswith("Pty Ltd")


# Intentional, small guard against familiar real Australian retailers/networks;
# not a claim of comprehensive trademark/entity-registry verification.
REAL_NAMES = ("AGL", "Origin Energy", "EnergyAustralia", "Red Energy", "Alinta",
              "AusNet", "CitiPower", "Powercor", "Jemena", "United Energy", "SA Power Networks")


@pytest.mark.parametrize("name", NAMES)
def test_holdout_uses_no_names_from_real_company_denylist(heldout, name):
    text = heldout[name].document.pages[0].text + (HOLDOUT / name / "expected.json").read_text(encoding="utf-8")
    for real in REAL_NAMES:
        assert re.search(r"\b" + re.escape(real) + r"\b", text, re.IGNORECASE) is None


def test_holdout_generator_is_deterministic_and_label_independent(tmp_path, monkeypatch):
    from scripts import generate_holdout

    original = Path.read_text
    original_bytes = Path.read_bytes
    def guard(path, *args, **kwargs):
        assert path.name != "expected.json", "generator must not read labels"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guard)
    def guard_bytes(path, *args, **kwargs):
        assert path.name != "expected.json", "generator must not read labels"
        return original_bytes(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", guard_bytes)
    for builder in generate_holdout.BUILDERS:
        builder(tmp_path)
        rebuilt = tmp_path / builder.__name__
        assert (rebuilt / "bill.pdf").read_bytes() == (HOLDOUT / builder.__name__ / "bill.pdf").read_bytes()
        assert not (rebuilt / "expected.json").exists()


def test_no_dev_or_holdout_organisation_names_leak_into_model_instructions(heldout):
    prompt = files("bill_lens.extraction").joinpath("prompts/extract_v4.md").read_text(encoding="utf-8")
    schema = json.dumps(structured_schema())
    organisations = [case.label.fields.retailer for case in [*load_cases(ROOT / "dataset"), *heldout.values()]]
    organisations += ["LANTERN", "QSP", "Glass Orchard Sample Networks",
                      "Mosaic Finch Sample Retail Pty Ltd", "Cobalt Loom Sample Group"]
    for name in organisations:
        assert name.casefold() not in prompt.casefold()
        assert name.casefold() not in schema.casefold()


def test_fake_holdout_cli_scores_all_fields_and_keeps_dev_separate(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("fake mode cannot construct a real provider")
    monkeypatch.setattr(run, "OpenAIExtractor", forbidden)
    assert [case.name for case in load_cases(ROOT / "dataset")] == CASES
    out = tmp_path / "holdout"
    assert run.main(["--extractor", "fake", "--dataset", str(HOLDOUT), "--repeats", "3", "--output", str(out)]) == 0
    summary = compare.load_summary(out)
    assert summary["dataset_name"] == "holdout" and set(summary["dataset"]) == set(NAMES)
    assert summary["completed_attempts"] == {"count": 18, "total": 18}
    for key in FIELDS:
        assert summary["metrics"]["fields"][key]["correct"] == {"count": 18, "total": 18}
    for key in ("exact_bill_match", "flags_match", "status_match"):
        assert summary["metrics"][key] == {"count": 18, "total": 18}
    assert "Dataset: holdout; 6 synthetic bills" in (out / "report.md").read_text()
    dev = tmp_path / "dev"
    assert run.main(["--extractor", "fake", "--repeats", "3", "--output", str(dev)]) == 0
    dev_summary = compare.load_summary(dev)
    assert dev_summary["dataset_name"] == "dataset" and dev_summary["bill_count"] == 5
    assert "Dataset: dataset; 5 synthetic bills" in (dev / "report.md").read_text()
    with pytest.raises(ValueError, match="different dataset"):
        compare.compare_runs(dev_summary, summary)
    # Additive display metadata must not break access to the saved v2 baseline.
    del dev_summary["dataset_name"]
    assert "legacy (name not recorded)" in render_report(dev_summary)
    assert "legacy (name not recorded)" in compare.compare_runs(dev_summary, dev_summary)


def test_openai_holdout_cli_uses_the_same_dataset_with_offline_stub(heldout, tmp_path, monkeypatch):
    monkeypatch.setenv("BILL_LENS_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-only")
    by_hash = {case.document.file_sha256: case for case in heldout.values()}
    calls, closed = [], []
    class Stub:
        prompt_version = "extract-v4"
        def __init__(self, **kwargs):
            assert kwargs["model"] == "gpt-5.4-mini"
        def extract(self, document):
            calls.append(document.file_sha256)
            return build_attempt(provider="openai", model="gpt-5.4-mini", prompt_version=self.prompt_version,
                                 raw_response=by_hash[document.file_sha256].label.fields.model_dump_json(), latency_ms=0)
        def close(self):
            closed.append(True)
    monkeypatch.setattr(run, "OpenAIExtractor", Stub)
    out = tmp_path / "stubbed"
    assert run.main(["--extractor", "openai", "--model", "gpt-5.4-mini", "--dataset", str(HOLDOUT), "--output", str(out)]) == 0
    assert len(calls) == len(set(calls)) == 6 and closed == [True]
    summary = compare.load_summary(out)
    assert summary["dataset_name"] == "holdout" and summary["bill_count"] == 6


@pytest.mark.parametrize("name", ["holdout_bad name", "bill_bad name"])
def test_dataset_loader_rejects_unsafe_case_names(tmp_path, name):
    (tmp_path / name).mkdir()
    with pytest.raises(ValueError, match="case names"):
        load_cases(tmp_path)
