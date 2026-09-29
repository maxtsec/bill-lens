"""Owner-run paid smoke check. Importing this module never constructs a client."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path

from bill_lens.contract import ExpectedLabel
from bill_lens.extraction.openai_adapter import OpenAIExtractor, REASONING_EFFORT
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_review_flags, derive_status
from evals.pricing import PRICE_DATE, PRICES, estimate_cost
from evals.scoring import field_matches


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
                flags = derive_review_flags(attempt.fields, document) if attempt.fields else set()
                cost = estimate_cost(model, attempt.model, attempt.input_tokens, attempt.output_tokens)
                input_total += attempt.input_tokens or 0
                output_total += attempt.output_tokens or 0
                missing_usage += int(attempt.input_tokens is None or attempt.output_tokens is None)
                unknown_cost += int(cost is None)
                total_cost += cost or Decimal(0)
                print(json.dumps({
                    "bill": name, "requested_model": model, "model": attempt.model,
                    "prompt_version": attempt.prompt_version,
                    "reasoning_effort": REASONING_EFFORT,
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
