"""Dated, uncached standard-price estimates from ADR-006; not billing data."""

from decimal import Decimal
from math import ceil
import re

from bill_lens.extraction.openai_adapter import MAX_OUTPUT_TOKENS

PRICE_DATE = "2026-09-29"
PRICES = {"gpt-5.4-mini": (Decimal("0.75"), Decimal("4.50")),
          "gpt-5.4": (Decimal("2.50"), Decimal("15.00"))}


def estimate_cost(requested: str, resolved: str, input_tokens: int | None,
                  output_tokens: int | None) -> Decimal | None:
    if (requested not in PRICES or input_tokens is None or output_tokens is None
            or input_tokens > 272_000
            or re.fullmatch(re.escape(requested) + r"(?:-\d{4}-\d{2}-\d{2})?", resolved) is None):
        return None
    input_price, output_price = PRICES[requested]
    return (input_price * input_tokens + output_price * output_tokens) / Decimal(1_000_000)


def planned_cost(cases, repeats: int, model: str) -> dict:
    # Planning heuristic only: text UTF-8 bytes / 4, plus 2,000 input tokens for
    # instructions/schema/framing, and the full output cap. NOT a spend ceiling.
    inputs = [ceil(sum(len(page.text.encode("utf-8")) for page in case.document.pages) / 4) + 2000
              for case in cases]
    estimates = [estimate_cost(model, model, size, MAX_OUTPUT_TOKENS) for size in inputs]
    if any(value is None for value in estimates):
        raise ValueError("planning estimate is outside the dated price table")
    return {"price_date": PRICE_DATE, "currency": "USD", "models": 1,
            "planned_calls": len(cases) * repeats,
            "estimated_cost_usd": str(sum(estimates, Decimal(0)) * repeats),
            "assumptions": f"UTF-8 text bytes/4 + 2000 input tokens per bill; {MAX_OUTPUT_TOKENS} output tokens per call; uncached standard prices. Planning estimate, NOT a spending cap."}
