"""PR B dataset integrity only: never execute the current-amount role check."""

from decimal import Decimal, ROUND_HALF_UP
from importlib.resources import files
import json
from pathlib import Path
import re

import pytest

from bill_lens.document_validation import derive_document_flags, printed_number_occurrences
from bill_lens.extraction.openai_adapter import structured_schema
from bill_lens.validation import derive_flags, derive_status
from bill_lens.current_amount_role import CURRENT_LABELS  # Vocabulary membership only; no rule call.
from evals.dataset import load_cases
from evals.role_cases import RoleCase
from scripts import generate_role_holdout
from tests.helpers import CASES, ROOT


HOLDOUT = ROOT / "dataset/role-holdout"
NAMES = [f"holdout_r{n:02}" for n in range(1, 11)]
REAL_NAMES = ("AGL", "Origin Energy", "EnergyAustralia", "Red Energy", "Alinta",
              "AusNet", "CitiPower", "Powercor", "Jemena", "United Energy", "SA Power Networks")


@pytest.fixture(scope="module")
def cases():
    return {case.name: case for case in load_cases(HOLDOUT)}


@pytest.fixture(scope="module")
def role_cases():
    return {name: RoleCase.model_validate_json((HOLDOUT / name / "role_cases.json").read_bytes())
            for name in NAMES}


def lines(case):
    return [line for page in case.document.pages for line in page.text.splitlines()]


def account_amounts(case):
    """Read account amounts from PDF text, independently of generator figures."""
    rows = lines(case)
    amounts = {}
    for line in rows:
        match = re.fullmatch(r"(.+?): AUD (\d+\.\d{2})(?: (CR))?", line)
        if match:
            amount = Decimal(match[2])
            # A same-line "Account credit" prefix is a signed credit under the
            # shared tokenizer; a table's value-only row has no such prefix.
            amounts[match[1]] = -amount if match[3] or match[1] == "Account credit" else amount
    if case.name == "holdout_r02":
        header = "Previous balance Payment Account credit Current charges Amount Due"
        index = rows.index(header)
        values = rows[index + 1].split()
        assert len(values) == 5
        amounts.update(zip(("Previous balance", "Payment", "Account credit", "Current charges", "Amount Due"),
                           map(Decimal, values), strict=True))
    if case.name == "holdout_r03":
        index = rows.index("Total current charges Total amount due")
        values = re.fullmatch(r"AUD (\d+\.\d{2}) AUD (\d+\.\d{2})", rows[index - 1])
        assert values is not None
        amounts["Total current charges"] = Decimal(values[1])
        amounts["Total amount due"] = Decimal(values[2])
    return amounts


def charges_from_pdf(case):
    source = "\n".join(lines(case))
    usage = re.search(r"(?m)^Usage: (\d+) kWh x AUD (\d+\.\d{2})/kWh = AUD (\d+\.\d{2})$", source)
    supply = re.search(r"(?m)^Supply: (\d+) days x AUD (\d+\.\d{2})/day = AUD (\d+\.\d{2})$", source)
    assert usage is not None and supply is not None
    uq, ur, uc = map(Decimal, usage.groups())
    sq, sr, sc = map(Decimal, supply.groups())
    assert (uq * ur).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == uc
    assert (sq * sr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == sc
    return uq, sq, sr, uc + sc


def test_role_holdout_is_not_discovered_by_existing_dev_or_retailer_holdout_loaders(cases):
    assert [case.name for case in load_cases(ROOT / "dataset")] == CASES
    assert [case.name for case in load_cases(ROOT / "dataset/holdout")] == [f"holdout_{n:03}" for n in range(1, 7)]
    assert set(cases) == set(NAMES)
    assert all(path.is_dir() for path in (HOLDOUT / name for name in NAMES))


@pytest.mark.parametrize("name", NAMES)
def test_handwritten_fields_presence_flags_and_status_only(cases, role_cases, name):
    case, annotation = cases[name], role_cases[name]
    fields, label = case.label.fields, case.label
    assert len(case.document.pages) == (2 if name == "holdout_r08" else 1)
    source = "\n".join(lines(case))
    assert source.count("SYNTHETIC SAMPLE - NOT PAYABLE") == len(case.document.pages)
    assert fields.retailer in source
    assert "current_bill_amount_role_unconfirmed" not in label.expected_flags
    assert derive_flags(fields) | derive_document_flags(fields, case.document) == set(label.expected_flags)
    assert derive_status(label.expected_flags) == label.expected_status
    assert annotation.current_bill_amount == fields.current_bill_amount
    assert (annotation.current_label is None) == (fields.current_bill_amount is None)
    assert (annotation.shape == "G") == (fields.current_bill_amount is None)
    period = re.search(r"Service period: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}) \(inclusive\)", source)
    assert period is not None and period.groups() == (fields.period_start.isoformat(), fields.period_end.isoformat())
    assert int(re.search(r"Billing days: (\d+)", source)[1]) == fields.stated_billing_days
    assert fields.stated_billing_days == (fields.period_end - fields.period_start).days + 1
    assert Decimal(re.search(r"Imported usage total: (\d+) kWh", source)[1]) == Decimal(fields.total_usage_kwh)
    assert "GST inclusive" in source and fields.daily_supply_rate.gst_basis == "inclusive"
    rate = re.search(r"Daily supply rate: AUD (\d+\.\d{2})/day \(GST inclusive\)", source)
    assert rate is not None and fields.daily_supply_rate.unit == "AUD/day"
    assert fields.daily_supply_rate.value == rate[1]


@pytest.mark.parametrize("name", NAMES)
def test_every_account_amount_and_charge_line_reconciles_from_pdf(cases, role_cases, name):
    case, annotation = cases[name], role_cases[name]
    account = account_amounts(case)
    expected_labels = {row.printed_label for row in annotation.printed_distractors}
    if annotation.current_label is not None:
        expected_labels.add(annotation.current_label)
    assert set(account) == expected_labels  # No unlisted account-level amount.
    all_text = "\n".join(lines(case))
    printed = {occurrence.value for occurrence in printed_number_occurrences(case.document)}
    for row in annotation.printed_distractors:
        assert row.printed_label in all_text
        assert Decimal(row.value) == account[row.printed_label] in printed
        assert Decimal(row.value) != 0
        assert annotation.current_bill_amount is None or Decimal(row.value) != Decimal(annotation.current_bill_amount)
    if annotation.current_label is not None:
        assert annotation.current_label in all_text
        assert Decimal(annotation.current_bill_amount) == account[annotation.current_label] in printed
    usage_q, supply_q, supply_rate, current_from_lines = charges_from_pdf(case)
    assert usage_q == Decimal(case.label.fields.total_usage_kwh)
    assert supply_q == case.label.fields.stated_billing_days
    assert supply_rate == Decimal(case.label.fields.daily_supply_rate.value)
    if annotation.current_bill_amount is None:
        assert current_from_lines not in printed  # R07 never prints its aggregate.
    else:
        assert current_from_lines == Decimal(annotation.current_bill_amount)
    by_role = {row.role: account[row.printed_label] for row in annotation.printed_distractors}
    assert set(by_role) == {"previous_balance", "payment", "credit", "amount_due"}
    assert by_role["amount_due"] == (current_from_lines + by_role["previous_balance"]
                                     - abs(by_role["payment"]) - abs(by_role["credit"]))


def test_all_shapes_and_isolated_vocabulary_allocation(cases, role_cases):
    assert {name: role_cases[name].shape for name in NAMES} == dict(zip(NAMES, "ABCDEFGHEE", strict=True))
    def known(label):
        if label is None:
            return False
        return any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", label.casefold())
                   for term in CURRENT_LABELS)
    inside = [name for name in NAMES if known(role_cases[name].current_label)]
    outside = [name for name in NAMES if role_cases[name].current_label is not None
               and not known(role_cases[name].current_label)]
    assert inside == ["holdout_r01", "holdout_r02", "holdout_r03", "holdout_r04", "holdout_r06", "holdout_r08"]
    assert outside == ["holdout_r05", "holdout_r09", "holdout_r10"]
    assert all(role_cases[name].shape == "E" for name in outside)
    assert len({role_cases[name].current_label for name in outside}) == 3
    a = "\n".join(lines(cases["holdout_r01"]))
    assert "Opening balance: AUD" in a and "Payments received: AUD" in a
    b = lines(cases["holdout_r02"])
    header = b.index("Previous balance Payment Account credit Current charges Amount Due")
    assert len(re.findall(r"Previous balance|Payment|Account credit|Current charges|Amount Due", b[header])) >= 2
    assert not any(c.isdigit() for c in b[header])
    assert re.fullmatch(r"(?:\d+\.\d{2} ){4}\d+\.\d{2}", b[header + 1])
    c = lines(cases["holdout_r03"])
    caption = c.index("Total current charges Total amount due")
    assert re.fullmatch(r"AUD \d+\.\d{2} AUD \d+\.\d{2}", c[caption - 1])
    assert any(ch.isdigit() for ch in role_cases["holdout_r04"].current_label)
    assert not known(role_cases["holdout_r05"].current_label)
    assert "Balance carried forward: AUD 45.00 CR" in lines(cases["holdout_r06"])
    assert Decimal(role_cases["holdout_r06"].printed_distractors[2].value) < 0
    assert role_cases["holdout_r07"].current_bill_amount is None
    pages = cases["holdout_r08"].document.pages
    assert "Amount due: AUD 138.11" in pages[0].text
    assert "Current charges: AUD 103.11" in pages[1].text
    assert "103.11" not in pages[0].text and "138.11" not in pages[1].text


@pytest.mark.parametrize("name", NAMES)
def test_no_real_company_names_in_pdf_or_handwritten_labels(cases, name):
    source = "\n".join(lines(cases[name]))
    source += (HOLDOUT / name / "expected.json").read_text(encoding="utf-8")
    source += (HOLDOUT / name / "role_cases.json").read_text(encoding="utf-8")
    for real in REAL_NAMES:
        assert re.search(r"\b" + re.escape(real) + r"\b", source, re.IGNORECASE) is None


def test_generator_is_deterministic_and_never_reads_or_writes_labels(tmp_path, monkeypatch):
    original_read = Path.read_text
    original_bytes = Path.read_bytes
    original_write = Path.write_text
    def checked_read(path, *args, **kwargs):
        assert path.name not in {"expected.json", "role_cases.json"}
        return original_read(path, *args, **kwargs)
    def checked_bytes(path, *args, **kwargs):
        assert path.name not in {"expected.json", "role_cases.json"}
        return original_bytes(path, *args, **kwargs)
    def checked_write(path, *args, **kwargs):
        assert path.name not in {"expected.json", "role_cases.json"}
        return original_write(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", checked_read)
    monkeypatch.setattr(Path, "read_bytes", checked_bytes)
    monkeypatch.setattr(Path, "write_text", checked_write)
    for build in generate_role_holdout.BUILDERS:
        build(tmp_path)
        name = build.__name__
        assert (tmp_path / name / "bill.pdf").read_bytes() == (HOLDOUT / name / "bill.pdf").read_bytes()
        assert not (tmp_path / name / "expected.json").exists()
        assert not (tmp_path / name / "role_cases.json").exists()


def test_new_case_ids_and_retailer_names_do_not_enter_model_instructions(cases):
    prompt = files("bill_lens.extraction").joinpath("prompts/extract_v4.md").read_text(encoding="utf-8")
    schema = json.dumps(structured_schema())
    for name, case in cases.items():
        for fragment in (name, name.replace("holdout_r", "ROLE-R").upper(), case.label.fields.retailer):
            assert fragment.casefold() not in prompt.casefold()
            assert fragment.casefold() not in schema.casefold()
