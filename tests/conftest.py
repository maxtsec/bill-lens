import pdfplumber
import pytest

from tests.helpers import CASES, ROOT


@pytest.fixture
def valid_fields():
    return {
        "retailer": "Example Energy",
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "stated_billing_days": 30,
        "total_usage_kwh": "250",
        "daily_supply_rate": {"value": "110.23", "unit": "cents/day", "gst_basis": "inclusive"},
        "current_bill_amount": "108.07",
    }


@pytest.fixture(scope="session")
def pdf_texts():
    result = {}
    for case in CASES:
        with pdfplumber.open(ROOT / "dataset" / case / "bill.pdf") as pdf:
            assert len(pdf.pages) == 1
            result[case] = pdf.pages[0].extract_text()
    return result
