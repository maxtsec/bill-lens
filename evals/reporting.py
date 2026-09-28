"""Counts with explicit denominators; no hidden exclusion of failed attempts."""

from collections import Counter
from decimal import Decimal
from statistics import median
from typing import get_args

from bill_lens.extraction import ExtractionErrorCode
from . import LIMITATION
from .scoring import FIELDS, OUTCOMES


def ratio(count, total):
    return {"count": count, "total": total}


def metrics(records: list[dict]) -> dict:
    total = len(records)
    fields = {name: {outcome: ratio(sum(r["field_outcomes"][name] == outcome for r in records), total)
                     for outcome in OUTCOMES} for name in FIELDS}
    components = {}
    for name in ("rate_value", "gst_basis"):
        values = [r["supply_components"][name] for r in records if r["supply_components"][name] is not None]
        components[name] = {"matched": ratio(sum(values), len(values)),
                            "unavailable": ratio(total - len(values), total)}
    errors = Counter(r["error_code"] or "none" for r in records)
    return {"attempts": total, "fields": fields, "supply_components": components,
            "exact_bill_match": ratio(sum(r["exact_bill_match"] for r in records), total),
            "flags_match": ratio(sum(r["flags_match"] for r in records), total),
            "status_match": ratio(sum(r["status_match"] for r in records), total),
            "attempt_outcomes": {key: ratio(errors[key], total) for key in ("none", *get_args(ExtractionErrorCode))}}


def summarize(metadata: dict, records: list[dict], *, completed: bool, abort_reason: str | None) -> dict:
    result = metadata | {"completed": completed, "abort_reason": abort_reason,
                         "completed_attempts": ratio(len(records), metadata["planned_attempts"]),
                         "metrics": metrics(records), "limitation": LIMITATION}
    result["resolved_models"] = sorted({r["resolved_model"] for r in records})
    result["prompt_versions"] = sorted({r["prompt_version"] for r in records})
    result["per_bill"] = {name: metrics([r for r in records if r["bill"] == name]) for name in metadata["dataset"]}
    for kind in ("input_tokens", "output_tokens"):
        known = [r[kind] for r in records if r[kind] is not None]
        result[kind] = {"known_total": sum(known), "calls_with_usage": ratio(len(known), len(records)),
                        "total": sum(known) if completed and len(known) == len(records) else None}
    costs = [Decimal(r["estimated_cost_usd"]) for r in records if r["estimated_cost_usd"] is not None]
    result["cost"] = {"known_estimated_usd": str(sum(costs, Decimal(0))),
                      "calls_with_estimate": ratio(len(costs), len(records)),
                      "total_estimated_usd": str(sum(costs, Decimal(0))) if completed and len(costs) == len(records) else None}
    latencies = [r["latency_ms"] for r in records]
    result["latency_ms"] = {"median": median(latencies) if latencies else None, "max": max(latencies) if latencies else None}
    return result


def fraction(value: dict) -> str:
    return f"{value['count']}/{value['total']}"


def render_report(summary: dict) -> str:
    m = summary["metrics"]
    lines = [f"# Evaluation {summary['run_id']}", "",
             f"Run: {summary['provider']} / requested {summary['requested_model']} / resolved {', '.join(summary['resolved_models']) or 'none'}",
             f"Prompt: {', '.join(summary['prompt_versions']) or 'none'}; effort: {summary['reasoning_effort']}",
             f"Harness/scoring: {summary['harness_version']}/{summary['scoring_version']}; started: {summary['started_at']}",
             f"Code: {summary['git']['commit']} (dirty={summary['git']['dirty']})",
             f"Dataset: {summary.get('dataset_name', 'legacy (name not recorded)')}; {summary['bill_count']} synthetic bills @ {summary['dataset_git']['commit']}; repeats: {summary['repeats']}",
             f"Completed attempts: {fraction(summary['completed_attempts'])}; complete={summary['completed']}; abort={summary['abort_reason']}",
             "", LIMITATION, "", "## Fields", "",
             "| Field | correct | wrong_value | missing | false_extraction | no_fields |",
             "| --- | --- | --- | --- | --- | --- |"]
    for name in FIELDS:
        lines.append(f"| {name} | " + " | ".join(fraction(m["fields"][name][o]) for o in OUTCOMES) + " |")
    lines += ["", f"Exact bill match: {fraction(m['exact_bill_match'])}",
              f"Review decision: flags {fraction(m['flags_match'])}; status {fraction(m['status_match'])}"]
    for name, values in m["supply_components"].items():
        lines.append(f"Supply {name}: {fraction(values['matched'])} matched when both rates exist; {fraction(values['unavailable'])} unavailable")
    lines += ["Attempt outcomes: " + "; ".join(f"{key} {fraction(value)}" for key, value in m["attempt_outcomes"].items()), "",
              "## Per-bill correctness across repeats", "",
              "Counts below use completed repeats; see planned/completed totals above.", "",
              "| Bill | Exact | Flags | Status | " + " | ".join(FIELDS) + " |",
              "| --- | --- | --- | --- | " + " | ".join(["---"] * len(FIELDS)) + " |"]
    for name, per in summary["per_bill"].items():
        values = [per[key] for key in ("exact_bill_match", "flags_match", "status_match")]
        values += [per["fields"][field]["correct"] for field in FIELDS]
        lines.append(f"| {name} | " + " | ".join(fraction(v) for v in values) + " |")
    lines += ["", "## Usage and latency", ""]
    for kind in ("input_tokens", "output_tokens"):
        value = summary[kind]
        lines.append(f"{kind}: total={value['total']}; known subtotal={value['known_total']}; coverage={fraction(value['calls_with_usage'])}")
    lines += [f"Latency ms: median={summary['latency_ms']['median']}; max={summary['latency_ms']['max']}",
              f"Estimated cost US$: {summary['cost']['total_estimated_usd']}; known subtotal={summary['cost']['known_estimated_usd']}; coverage={fraction(summary['cost']['calls_with_estimate'])}",
              f"Prices dated {summary['price_date']}; uncached standard-price estimate, not actual billing. Fake costs zero; absent usage stays unknown.",
              "", "## Dataset hashes", "", "| Bill | PDF SHA-256 | Label SHA-256 |", "| --- | --- | --- |"]
    lines += [f"| {name} | {hashes['pdf_sha256']} | {hashes['label_sha256']} |" for name, hashes in summary["dataset"].items()]
    return "\n".join(lines) + "\n"
