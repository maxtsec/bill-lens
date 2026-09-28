import pdfplumber
import pytest


@pytest.fixture(autouse=True)
def offline_http_and_config(monkeypatch):
    """Every default test is offline, even if the developer has live credentials."""
    import httpx
    import httpx2

    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "BILL_EXTRACTOR", "BILL_LENS_LIVE"):
        monkeypatch.delenv(name, raising=False)
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("real HTTP transport is forbidden in tests")

    for module in (httpx, httpx2):
        monkeypatch.setattr(module.HTTPTransport, "handle_request", forbidden)
        monkeypatch.setattr(module.AsyncHTTPTransport, "handle_async_request", forbidden)
    yield
    # SDKs can catch transport exceptions; still fail the test if one was attempted.
    assert not attempts, "a test attempted real HTTP; use a stub or MockTransport"

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
