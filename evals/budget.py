"""Sequential reservation ledger for opt-in, dated-price spend ceilings."""

from decimal import Decimal
from importlib.resources import files
import json
from pathlib import Path

from bill_lens.extraction.openai_adapter import (
    MAX_OUTPUT_TOKENS, document_message, structured_schema,
)
from .pricing import PRICE_DATE, PRICES, estimate_cost

# Same conservative allowance as the preserved bill_002 repeat experiment.
# Complete text/schema JSON must fit half this allowance; no remote token count.
INPUT_TOKEN_ALLOWANCE = 32768
REQUEST_BYTE_LIMIT = 16384


class BudgetStopped(ValueError):
    """A safe reason; never include document text or SDK diagnostics."""


def request_bytes(document) -> int:
    instructions = files("bill_lens.extraction").joinpath("prompts/extract_v4.md").read_text(encoding="utf-8")
    request = {"instructions": instructions,
               "input": [{"role": "user", "content": document_message(document)}],
               "text": {"format": {"type": "json_schema", "name": "bill_fields",
                                   "strict": True, "schema": structured_schema()}}}
    return len(json.dumps(request, ensure_ascii=True).encode("utf-8"))


class Budget:
    def __init__(self, cap: Decimal, *, provider: str, model: str):
        if not cap.is_finite() or cap <= 0:
            raise ValueError("budget must be a finite positive USD amount")
        if provider not in {"openai", "fake"} or (provider == "openai" and model not in PRICES):
            raise ValueError("budget requires a supported provider and dated model price")
        self.provider, self.model = provider, model
        self.reservation = (estimate_cost(model, model, INPUT_TOKEN_ALLOWANCE, MAX_OUTPUT_TOKENS)
                            if provider == "openai" else Decimal(0))
        self.data = {"schema_version": 1, "limit_usd": str(cap), "price_date": PRICE_DATE,
                     "requested_model": model, "provider": provider,
                     "prices_per_million_usd": [str(p) for p in PRICES[model]] if provider == "openai" else None,
                     "input_token_allowance": INPUT_TOKEN_ALLOWANCE,
                     "request_byte_limit": REQUEST_BYTE_LIMIT, "output_token_cap": MAX_OUTPUT_TOKENS,
                     "reservation_per_call_usd": str(self.reservation), "spent_usd": "0",
                     "known_settled_usd": "0", "calls": [], "stopped_before": None}

    def save(self, output: Path) -> None:
        target = output / "budget.json"
        temporary = output / "budget.json.tmp"
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)

    def reserve(self, bill: str, repeat: int, document, output: Path) -> None:
        size = request_bytes(document) if self.provider == "openai" else 0
        before = Decimal(self.data["spent_usd"])
        total = before + self.reservation
        reason = ("request_allowance_exceeded" if size > REQUEST_BYTE_LIMIT else
                  "budget_exhausted" if total > Decimal(self.data["limit_usd"]) else None)
        if reason:
            self.data["stopped_before"] = {"bill": bill, "repeat": repeat, "reason": reason,
                                           "request_bytes": size, "required_total_usd": str(total)}
            self.save(output)
            raise BudgetStopped(reason)
        self.data["calls"].append({"bill": bill, "repeat": repeat, "state": "reserved",
                                   "request_bytes": size, "spent_before_usd": str(before),
                                   "reserved_usd": str(self.reservation), "reserved_total_usd": str(total),
                                   "settled_usd": None, "cumulative_usd": str(total)})
        self.data["spent_usd"] = str(total)
        self.save(output)  # Before any provider call; unknown charges stay reserved.

    def settle(self, attempt, output: Path) -> str | None:
        row = self.data["calls"][-1]
        cost = (estimate_cost(self.model, attempt.model, attempt.input_tokens, attempt.output_tokens)
                if self.provider == "openai" else Decimal(0))
        exceeds_allowance = self.provider == "openai" and (
            (attempt.input_tokens is not None and attempt.input_tokens > INPUT_TOKEN_ALLOWANCE)
            or (attempt.output_tokens is not None and attempt.output_tokens > MAX_OUTPUT_TOKENS))
        reason = ("usage_exceeds_reservation" if exceeds_allowance else
                  "usage_or_model_unknown" if cost is None else None)
        row.update(input_tokens=attempt.input_tokens, output_tokens=attempt.output_tokens,
                   resolved_model=attempt.model, settled_usd=str(cost) if cost is not None else None,
                   state="reserved_unknown" if reason else "settled", stop_reason=reason)
        if not reason:
            self.data["spent_usd"] = str(Decimal(row["spent_before_usd"]) + cost)
            self.data["known_settled_usd"] = str(Decimal(self.data["known_settled_usd"]) + cost)
        row["cumulative_usd"] = self.data["spent_usd"]
        self.save(output)
        return reason


def verify_ledger(data: dict, records: list[dict], *, completed: bool) -> None:
    """Check saved reservations/settlements without treating missing usage as zero."""
    reference = Budget(Decimal(data["limit_usd"]), provider=data["provider"], model=data["requested_model"])
    for key in ("schema_version", "price_date", "prices_per_million_usd", "input_token_allowance",
                "request_byte_limit", "output_token_cap", "reservation_per_call_usd"):
        if data[key] != reference.data[key]:
            raise ValueError(f"budget policy mismatch: {key}")
    calls = data["calls"]
    if len(calls) != len(records) and (completed or len(calls) != len(records) + 1):
        raise ValueError("budget call coverage mismatch")
    spent, settled = Decimal(0), Decimal(0)
    for index, call in enumerate(calls):
        reserved = reference.reservation
        if (Decimal(call["spent_before_usd"]) != spent or Decimal(call["reserved_usd"]) != reserved
                or Decimal(call["reserved_total_usd"]) != spent + reserved
                or spent + reserved > Decimal(data["limit_usd"])
                or not 0 <= call["request_bytes"] <= REQUEST_BYTE_LIMIT):
            raise ValueError("invalid budget reservation")
        if index < len(records):
            row = records[index]
            if any(call[key] != row[key] for key in
                   ("bill", "repeat", "input_tokens", "output_tokens", "resolved_model")):
                raise ValueError("budget settlement does not match attempt")
            expected_cost = (estimate_cost(reference.model, row["resolved_model"], row["input_tokens"], row["output_tokens"])
                             if reference.provider == "openai" else Decimal(0))
            if call["settled_usd"] != (str(expected_cost) if expected_cost is not None else None):
                raise ValueError("budget cost mismatch")
            if call["state"] == "settled":
                if expected_cost is None or expected_cost > reserved or call["stop_reason"] is not None:
                    raise ValueError("invalid budget settlement")
                spent += expected_cost
                settled += expected_cost
            elif call["state"] == "reserved_unknown" and call["stop_reason"] in {
                    "usage_or_model_unknown", "usage_exceeds_reservation"} and not completed and index == len(calls) - 1:
                spent += reserved
            else:
                raise ValueError("invalid budget call state")
        else:
            if call["state"] != "reserved" or call["settled_usd"] is not None:
                raise ValueError("unrecorded call must retain its reservation")
            spent += reserved
        if Decimal(call["cumulative_usd"]) != spent:
            raise ValueError("budget cumulative mismatch")
    if Decimal(data["spent_usd"]) != spent or Decimal(data["known_settled_usd"]) != settled:
        raise ValueError("budget totals mismatch")
