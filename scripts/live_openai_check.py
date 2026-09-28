"""Owner-run paid smoke check. Importing this module never constructs a client."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re

from bill_lens.contract import ExpectedLabel, ExtractionFields
from bill_lens.extraction.openai_adapter import OpenAIExtractor
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_flags, derive_status, supply_rate_aud

PRICE_DATE = "2026-09-29"
# USD per million uncached input / output tokens, standard processing <=272k input.
# Sources and estimation limitations are documented in ADR-006.
PRICES = {"gpt-5.4-mini": (Decimal("0.75"), Decimal("4.50")),
          "gpt-5.4": (Decimal("2.50"), Decimal("15.00"))}


def field_matches(actual: ExtractionFields | None, expected: ExtractionFields) -> dict[str, bool]:
    result = {}
    for name in ExtractionFields.model_fields:
        if actual is None:
            result[name] = False
            continue
        left, right = getattr(actual, name), getattr(expected, name)
        if left is None or right is None:
            result[name] = left is right
        elif name == "retailer":
            result[name] = " ".join(left.casefold().split()) == " ".join(right.casefold().split())
        elif name in {"total_usage_kwh", "current_bill_amount"}:
            result[name] = Decimal(left) == Decimal(right)
        elif name == "daily_supply_rate":
            result[name] = supply_rate_aud(left) == supply_rate_aud(right) and left.gst_basis == right.gst_basis
        else:
            result[name] = left == right
    return result


def estimate_cost(requested: str, resolved: str, input_tokens: int | None,
                  output_tokens: int | None) -> Decimal | None:
    if (input_tokens is None or output_tokens is None or input_tokens > 272_000
            or re.fullmatch(re.escape(requested) + r"(?:-\d{4}-\d{2}-\d{2})?", resolved) is None):
        return None
    input_price, output_price = PRICES[requested]
    return (input_price * input_tokens + output_price * output_tokens) / Decimal(1_000_000)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=list(PRICES), default=list(PRICES))
    parser.add_argument("--dataset", type=Path, default=Path("dataset"))
    args = parser.parse_args(argv)
    # Check both gates before reading bills or constructing any SDK client.
    if os.environ.get("BILL_LENS_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY", "").strip():
        parser.error("requires BILL_LENS_LIVE=1 and OPENAI_API_KEY; this check spends API credit")
    if len(args.models) != len(set(args.models)) or len(args.models) < 2:
        parser.error("choose both distinct baseline models (small and mid-tier)")
    cases = []
    for number in range(1, 6):
        case = args.dataset / f"bill_{number:03}"
        label = ExpectedLabel.model_validate_json((case / "expected.json").read_text(encoding="utf-8"))
        cases.append((case.name, extract_pdf_text((case / "bill.pdf").read_bytes()), label))
    print(json.dumps({"price_date": PRICE_DATE, "currency": "USD", "pricing": "standard, uncached-input estimate",
                      "prices_per_million": {key: [str(x) for x in value] for key, value in PRICES.items()}}))
    input_total = output_total = missing_usage = unknown_cost = 0
    total_cost = Decimal(0)
    for model in args.models:
        adapter = OpenAIExtractor(model=model, api_key=os.environ["OPENAI_API_KEY"])
        try:
            for name, document, label in cases:
                attempt = adapter.extract(document)
                flags = derive_flags(attempt.fields) if attempt.fields else set()
                cost = estimate_cost(model, attempt.model, attempt.input_tokens, attempt.output_tokens)
                input_total += attempt.input_tokens or 0
                output_total += attempt.output_tokens or 0
                missing_usage += int(attempt.input_tokens is None or attempt.output_tokens is None)
                unknown_cost += int(cost is None)
                total_cost += cost or Decimal(0)
                print(json.dumps({
                    "bill": name, "requested_model": model, "model": attempt.model,
                    "prompt_version": attempt.prompt_version,
                    "status": derive_status(flags) if attempt.fields else "failed",
                    "error_code": attempt.error_code, "flags": sorted(flags),
                    "field_matches": field_matches(attempt.fields, label.fields),
                    "input_tokens": attempt.input_tokens, "output_tokens": attempt.output_tokens,
                    "latency_ms": attempt.latency_ms, "estimated_cost_usd": str(cost) if cost is not None else None,
                }))
        finally:
            adapter.close()
    print(json.dumps({"known_input_tokens": input_total, "known_output_tokens": output_total,
                      "calls_missing_usage": missing_usage, "calls_without_cost_estimate": unknown_cost,
                      "known_estimated_cost_usd": str(total_cost),
                      "total_estimated_cost_usd": str(total_cost) if unknown_cost == 0 else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
