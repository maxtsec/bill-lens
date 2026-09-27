import re
from decimal import Decimal, ROUND_HALF_UP

import pytest

from bill_lens.contract import ExpectedLabel
from bill_lens.validation import derive_flags, derive_status
from conftest import CASES, ROOT


def label_for(case):
    return ExpectedLabel.model_validate_json((ROOT / "dataset" / case / "expected.json").read_text())


def numbers(pattern, text):
    match = re.search(pattern, text)
    assert match is not None, f"Missing printed values: {pattern}"
    return tuple(Decimal(value) for value in match.groups())


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@pytest.mark.parametrize("case", CASES)
def test_labels_against_independent_expected_flags(case):
    label = label_for(case)
    assert derive_flags(label.fields) == set(label.expected_flags)
    assert label.expected_status == derive_status(label.expected_flags)


@pytest.mark.parametrize("case", CASES)
def test_pdf_has_extractable_core_values(case, pdf_texts):
    text = pdf_texts[case]
    fields = label_for(case).fields
    assert "SYNTHETIC SAMPLE - NOT PAYABLE" in text
    assert fields.retailer in text
    (usage,) = numbers(r"Total imported usage: ([0-9.]+) kWh", text)
    assert usage == Decimal(fields.total_usage_kwh)
    (days,) = numbers(r"Billing days: ([0-9]+)", text)
    assert days == fields.stated_billing_days
    # Check the printed rates, independent of the PDF builder's inputs.
    rate_pattern = {
        "bill_001": r"at ([0-9.]+) c/day",
        "bill_002": r"at \$([0-9.]+)/day",
        "bill_003": r"([0-9.]+) c per day",
        "bill_004": r"days at AUD ([0-9.]+)/day",
        "bill_005": r"at ([0-9.]+)¢/day",
    }[case]
    (rate,) = numbers(rate_pattern, text)
    assert rate == Decimal(fields.daily_supply_rate.value)
    assert fields.daily_supply_rate.unit == ("AUD/day" if case in {"bill_002", "bill_004"} else "cents/day")
    assert fields.daily_supply_rate.gst_basis == ("exclusive" if case == "bill_002" else "inclusive")
    assert ("rates exclude GST" if case == "bill_002" else "GST inclusive") in text


def test_all_displayed_charge_lines_reconcile(pdf_texts):
    # Read quantities, unit rates and charges from PDFs, not the generator.
    t = pdf_texts["bill_001"]
    q, r, usage = numbers(r"Usage: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh AUD ([0-9.]+)", t)
    assert money(q * r) == usage
    q, r, supply = numbers(r"Supply: ([0-9.]+) days at ([0-9.]+) c/day AUD ([0-9.]+)", t)
    assert money(q * r / 100) == supply
    (total,) = numbers(r"Current bill amount AUD ([0-9.]+)", t)
    assert total == usage + supply == Decimal(label_for("bill_001").fields.current_bill_amount)
    assert numbers(r"Amount due: AUD ([0-9.]+)", t) == (total,)

    t = pdf_texts["bill_002"]
    usage, q, r = numbers(r"AUD ([0-9.]+) Usage: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh", t)
    assert money(q * r) == usage
    supply, q, r = numbers(r"AUD ([0-9.]+) Supply: ([0-9.]+) days at \$([0-9.]+)/day", t)
    assert money(q * r) == supply
    (gst,) = numbers(r"AUD ([0-9.]+) GST on", t)
    assert gst == money((usage + supply) * Decimal("0.10"))
    (previous,) = numbers(r"Previous balance: AUD ([0-9.]+)", t)
    (payment,) = numbers(r"Payment received: AUD ([0-9.]+)", t)
    (due,) = numbers(r"AMOUNT DUE\nAUD ([0-9.]+)", t)
    assert due == usage + supply + gst + previous - payment
    assert "132.66" not in t
    assert "current bill amount" not in t.lower()
    assert label_for("bill_002").fields.current_bill_amount is None

    t = pdf_texts["bill_003"]
    pq, pr, peak = numbers(r"Peak ([0-9.]+) kWh AUD ([0-9.]+)/kWh AUD ([0-9.]+)", t)
    oq, rate, off_peak = numbers(r"Off-peak ([0-9.]+) kWh AUD ([0-9.]+)/kWh AUD ([0-9.]+)", t)
    assert money(pq * pr) == peak
    assert money(oq * rate) == off_peak
    assert pq + oq == Decimal(label_for("bill_003").fields.total_usage_kwh)
    q, r, supply = numbers(r"Supply ([0-9.]+) days ([0-9.]+) c per day AUD ([0-9.]+)", t)
    assert money(q * r / 100) == supply
    (total,) = numbers(r"Current bill amount: AUD ([0-9.]+)", t)
    (previous,) = numbers(r"Previous unpaid balance: AUD ([0-9.]+)", t)
    (due,) = numbers(r"Amount due: AUD ([0-9.]+)", t)
    assert total == peak + off_peak + supply == Decimal(label_for("bill_003").fields.current_bill_amount)
    assert due == total + previous
    assert due != total

    t = pdf_texts["bill_004"]
    q, r, usage = numbers(r"Usage: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh = AUD ([0-9.]+)", t)
    assert money(q * r) == usage
    q, r, supply = numbers(r"Supply: ([0-9.]+) days at AUD ([0-9.]+)/day = AUD ([0-9.]+)", t)
    assert money(q * r) == supply
    q, r, credit = numbers(r"Feed-in: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh = AUD ([0-9.]+) credit", t)
    assert money(q * r) == credit
    (printed_credit,) = numbers(r"AUD ([0-9.]+) CR", t)
    assert usage + supply - credit == -printed_credit == Decimal(label_for("bill_004").fields.current_bill_amount)

    t = pdf_texts["bill_005"]
    q, r = numbers(r"Usage: ([0-9.]+) kWh at AUD ([0-9.]+)/kWh", t)
    (usage,) = numbers(r"Usage charge: AUD ([0-9.]+)", t)
    assert money(q * r) == usage
    q, r = numbers(r"Supply: ([0-9.]+) days at ([0-9.]+)¢/day", t)
    (supply,) = numbers(r"Supply charge: AUD ([0-9.]+)", t)
    assert money(q * r / 100) == supply
    assert q == 31  # Preserve the deliberate conflict with the summary's 30 days.
    (total,) = numbers(r"Current bill amount Supply charge: AUD [0-9.]+\nAUD ([0-9.]+)", t)
    assert usage + supply == total == Decimal(label_for("bill_005").fields.current_bill_amount)
    assert numbers(r"Amount due: AUD ([0-9.]+)", t) == (total,)


@pytest.mark.parametrize("case,start,end,printed", [
    ("bill_001", "2026-04-01", "2026-04-30", ["1 April 2026 to 30 April 2026"]),
    ("bill_002", "2026-05-01", "2026-05-31", ["01 May 2026 - 31 May 2026"]),
    ("bill_003", "2026-06-05", "2026-07-04", ["DD/MM/YYYY", "05/06/2026 - 04/07/2026"]),
    ("bill_004", "2026-11-01", "2026-11-30", ["1 November 2026 to 30 November 2026"]),
    ("bill_005", "2026-08-01", "2026-08-31", ["1 August 2026 to", "31 August 2026"]),
])
def test_printed_periods_match_labels(case, start, end, printed, pdf_texts):
    fields = label_for(case).fields
    assert fields.period_start.isoformat() == start
    assert fields.period_end.isoformat() == end
    for fragment in printed:
        assert fragment in pdf_texts[case]


def test_generator_reproduces_committed_pdfs_without_writing_labels(tmp_path, monkeypatch):
    from scripts import generate_dataset

    monkeypatch.setattr(generate_dataset, "ROOT", tmp_path)
    for case in CASES:
        getattr(generate_dataset, case)()
        actual = tmp_path / "dataset" / case
        assert (actual / "bill.pdf").read_bytes() == (ROOT / "dataset" / case / "bill.pdf").read_bytes()
        assert not (actual / "expected.json").exists()
