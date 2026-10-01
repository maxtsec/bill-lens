"""Pre-registered offline analysis; never extract, call a model or edit a run."""

import argparse
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

from bill_lens.document_validation import printed_number_occurrences
from bill_lens.extraction import build_attempt
from bill_lens.pdf_text import PageText, PdfText
from evals import HARNESS_VERSION, SCORING_VERSION
from evals.budget import verify_ledger
from evals.dataset import load_cases, manifest
from evals.role_cases import RoleCase
from evals.reporting import summarize
from evals.scoring import FIELDS, score_attempt

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset/role-holdout"
REFERENCE = ROOT / "docs/learning/evidence/role-holdout-measurement.json"
REFERENCE_SHA256 = "720ebbaf80b14122f5a4337603d7c10315dc2b5c402bb9aa264cc2fd8ef2e91e"
ROLE_FLAG = "current_bill_amount_role_unconfirmed"
MODEL = "gpt-5.4-mini"
PROMPT_SHA256 = "3c6762fc560688769faa74c2866b719beeccf047986f3765929873e0a575a02a"


def verified_inputs(dataset: Path) -> tuple[dict, dict, dict]:
    raw = REFERENCE.read_bytes()
    if sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("PR C evidence hash mismatch")
    reference = json.loads(raw)
    if sha256((ROOT / "bill_lens/extraction/prompts/extract_v4.md").read_bytes()).hexdigest() != PROMPT_SHA256:
        raise ValueError("frozen extract-v4 prompt mismatch")
    names = set(reference["input_hashes"])
    if {p.name for p in dataset.glob("holdout_*") if p.is_dir()} != names:
        raise ValueError("role holdout must contain exactly the ten PR C cases")
    annotations = {}
    for name, hashes in reference["input_hashes"].items():
        for filename, digest in hashes.items():
            if sha256((dataset / name / filename).read_bytes()).hexdigest() != digest:
                raise ValueError(f"input hash mismatch: {name}/{filename}")
        annotations[name] = RoleCase.model_validate_json((dataset / name / "role_cases.json").read_bytes())
    # Keep the production rule frozen, not just the source inputs.
    for name, digest in reference["implementation_lf_sha256"].items():
        if name.startswith("scripts/"):
            continue  # Historical measurement runner is record-only.
        if sha256((ROOT / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"frozen implementation mismatch: {name}")
    cases = {case.name: case for case in load_cases(dataset)}
    return cases, annotations, reference


def classify_amount(value: str | None, expected: str | None, annotation: RoleCase) -> dict:
    if value is None:
        return {"category": "null", "correct": expected is None, "distractor_matches": []}
    number = Decimal(value)
    if expected is not None and number == Decimal(expected):
        return {"category": "correct", "correct": True, "distractor_matches": []}
    matches = []
    for item in annotation.printed_distractors:
        signed = Decimal(item.value)
        sign = ("signed" if number == signed else
                "unsigned_magnitude" if item.role == "credit" and signed < 0 and number == abs(signed) else None)
        if sign:
            matches.append({**item.model_dump(), "matched_sign": sign})
    # Preserve every matching role if annotated values collide; do not pick one.
    roles = sorted({item["role"] for item in matches})
    category = "distractor:" + "+".join(roles) if roles else "other_wrong"
    return {"category": category, "correct": False, "distractor_matches": matches}


def occurrences(document: PdfText, value: str | None) -> list[dict]:
    if value is None:
        return []
    found = []
    for page in document.pages:
        for line_number, line in enumerate(page.text.splitlines(), 1):
            single = PdfText(document.file_sha256, (PageText(page.page_number, line),))
            if any(item.value == Decimal(value) for item in printed_number_occurrences(single)):
                found.append({"page": page.page_number, "line_number": line_number, "line": line})
    return found


def counts(rows: list[dict], planned: int) -> dict:
    completed = len(rows)
    return {"observed_attempts": completed, "planned_attempts": planned,
            "categories": dict(sorted(Counter(row["category"] for row in rows).items())),
            **{key: {"count": sum(row[key] for row in rows), "total": completed}
               for key in ("correct", "incorrect_current", "null", "wrong_value", "caught", "silent_false_acceptance", "false_review", "no_fields")}}


def analyse(run: Path, dataset: Path = DATASET) -> dict:
    cases, annotations, reference = verified_inputs(dataset)
    summary_raw = (run / "summary.json").read_bytes()
    attempts_raw = (run / "attempts.jsonl").read_bytes()
    summary = json.loads(summary_raw)
    expected_manifest = manifest(list(cases.values()))
    if (summary["dataset"] != expected_manifest or summary["repeats"] != 3
            or summary["planned_attempts"] != 30 or summary["bill_count"] != 10):
        raise ValueError("run must describe the verified ten cases with three repeats")
    if (summary["provider"] != "openai" or summary["requested_model"] != MODEL
            or summary["configured_prompt_version"] != "extract-v4" or summary["reasoning_effort"] != "low"
            or summary["harness_version"] != HARNESS_VERSION or summary["scoring_version"] != SCORING_VERSION):
        raise ValueError("run settings differ from the pre-registered profile")
    if summary["git"]["dirty"] is not False or not summary["git"]["commit"]:
        raise ValueError("run must record a clean commit")
    budget_raw = (run / "budget.json").read_bytes()
    budget = json.loads(budget_raw)
    if (summary.get("budget") != budget or Decimal(budget["limit_usd"]) != Decimal("0.30")
            or budget["provider"] != "openai" or budget["requested_model"] != MODEL):
        raise ValueError("run must include the matching US$0.30 budget ledger")
    if Decimal(budget["spent_usd"]) > Decimal(budget["limit_usd"]):
        raise ValueError("ledger exceeds the authorised budget")
    records = [json.loads(line) for line in attempts_raw.splitlines()]
    planned_pairs = {(name, repeat) for repeat in range(1, 4) for name in cases}
    expected_order = [(name, repeat) for repeat in range(1, 4) for name in sorted(cases)]
    pairs = [(row["bill"], row["repeat"]) for row in records]
    if len(set(pairs)) != len(pairs) or pairs != expected_order[:len(pairs)] or not set(pairs) <= planned_pairs:
        raise ValueError("attempt coverage/order contains duplicates or unexpected cases/repeats")
    if summary["completed_attempts"] != {"count": len(records), "total": 30}:
        raise ValueError("summary attempt coverage mismatch")
    if summary["completed"] and len(records) != 30:
        raise ValueError("complete run must have all thirty attempts")
    verify_ledger(budget, records, completed=summary["completed"])
    results, scored_rows = [], []
    for row in records:
        case = cases[row["bill"]]
        if (row["run_id"] != summary["run_id"] or row["provider"] != "openai"
                or row["requested_model"] != MODEL or row["prompt_version"] != "extract-v4"
                or row["reasoning_effort"] != "low"
                or re.fullmatch(re.escape(MODEL) + r"(?:-\d{4}-\d{2}-\d{2})?", row["resolved_model"]) is None
                or any(row[key] != digest for key, digest in expected_manifest[case.name].items())):
            raise ValueError("attempt provenance/settings mismatch")
        attempt = build_attempt(provider=row["provider"], model=row["resolved_model"],
                                prompt_version=row["prompt_version"], raw_response=row["raw_response"],
                                error_code=row["error_code"], latency_ms=row["latency_ms"],
                                input_tokens=row["input_tokens"], output_tokens=row["output_tokens"])
        scored = score_attempt(attempt, case.label, case.document)
        if any(row[key] != value for key, value in scored.items()):
            raise ValueError("attempt scoring does not reproduce from the preserved raw response")
        scored_rows.append(scored)
        value = attempt.fields.current_bill_amount if attempt.fields else None
        result = (classify_amount(value, case.label.fields.current_bill_amount, annotations[case.name])
                  if attempt.fields else {"category": "no_fields", "correct": False, "distractor_matches": []})
        for match in result["distractor_matches"]:
            # Retain the signed credit's printed location even for an unsigned
            # model answer that has no equal signed occurrence of its own.
            match["occurrences"] = occurrences(case.document, match["value"])
        wrong_value = attempt.fields is not None and value is not None and not result["correct"]
        flags = row["flags"] or []
        result.update(bill=case.name, repeat=row["repeat"], shape=annotations[case.name].shape,
                      value=value, expected=case.label.fields.current_bill_amount,
                      flags=row["flags"], status=row["status"], error_code=row["error_code"],
                      wrong_value=wrong_value, no_fields=attempt.fields is None,
                      silent_false_acceptance=wrong_value and row["status"] == "processed",
                      caught=wrong_value and row["status"] == "needs_review",
                      false_review=value is not None and result["correct"] and ROLE_FLAG in flags,
                      current_amount_presence_flag="current_bill_amount_not_printed" in flags,
                      current_amount_role_flag=ROLE_FLAG in flags,
                      null=value is None and attempt.fields is not None,
                      incorrect_current=not result["correct"],
                      occurrences=occurrences(case.document, value),
                      r07_computed_87_20=case.name == "holdout_r07" and value is not None and Decimal(value) == Decimal("87.20"))
        results.append(result)
    rebuilt_summary = summarize(summary, records, completed=summary["completed"], abort_reason=summary["abort_reason"])
    for key in ("metrics", "per_bill", "resolved_models", "prompt_versions", "input_tokens", "output_tokens", "cost", "latency_ms"):
        if summary[key] != rebuilt_summary[key]:
            raise ValueError(f"summary does not reproduce from attempts: {key}")
    printed = [row for row in results if row["expected"] is not None]
    missing = [row for row in results if row["bill"] == "holdout_r07"]
    return {"schema_version": 1, "run_id": summary["run_id"], "git": summary["git"],
            "completed": summary["completed"], "abort_reason": summary["abort_reason"],
            "live_api_calls_by_analysis": 0, "reference_sha256": REFERENCE_SHA256,
            "analysis_script_lf_sha256": sha256(Path(__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
            "prompt_sha256": PROMPT_SHA256,
            "input_hashes": reference["input_hashes"],
            "source_sha256": {"summary.json": sha256(summary_raw).hexdigest(),
                              "attempts.jsonl": sha256(attempts_raw).hexdigest(),
                              "budget.json": sha256(budget_raw).hexdigest()},
            "budget": budget, "per_attempt": results, "totals": counts(results, 30),
            "printed_current": counts(printed, 27), "r07": counts(missing, 3),
            "per_case": {name: counts([r for r in results if r["bill"] == name], 3) for name in cases},
            "per_shape": {shape: counts([r for r in results if r["shape"] == shape],
                                       3 * sum(a.shape == shape for a in annotations.values()))
                          for shape in sorted({a.shape for a in annotations.values()})},
            "other_fields": {name: {"correct": sum(r["field_outcomes"][name] == "correct" for r in scored_rows),
                                    "total": len(records)} for name in FIELDS if name != "current_bill_amount"}}


def render_report(result: dict) -> str:
    lines = [f"# Role holdout live analysis: {result['run_id']}", "",
             f"Complete={result['completed']}; abort={result['abort_reason']}",
             "Selected synthetic bills; repeats are not independent layouts. No population error-rate claim.", "",
             "| Group | Observed / planned | Correct | Wrong numeric value | Caught | Silent false acceptance | False review | No fields |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    groups = [("Printed current", result["printed_current"]), ("r07", result["r07"]),
              *result["per_case"].items(), *[(f"Shape {s}", v) for s, v in result["per_shape"].items()]]
    for name, stats in groups:
        values = [f"{stats[k]['count']}/{stats[k]['total']}" for k in
                  ("correct", "wrong_value", "caught", "silent_false_acceptance", "false_review", "no_fields")]
        lines.append(f"| {name} | {stats['observed_attempts']}/{stats['planned_attempts']} | " + " | ".join(values) + " |")
    lines += ["", "## Every attempt", "", "| Bill / repeat | Value | Category | Status | Flags | Credit sign match |",
              "| --- | --- | --- | --- | --- | --- |"]
    for row in result["per_attempt"]:
        signs = ", ".join(m["matched_sign"] for m in row["distractor_matches"]) or "—"
        lines.append(f"| {row['bill']} / {row['repeat']} | {row['value']} | {row['category']} | {row['status']} | "
                     f"{', '.join(row['flags'] or [])} | {signs} |")
        if row["r07_computed_87_20"]:
            lines.append("\n**r07: returned the reconstructable but unprinted 87.20.**\n")
    lines += ["", "## Other fields (separate)", ""]
    lines += [f"- {name}: {stats['correct']}/{stats['total']} correct." for name, stats in result["other_fields"].items()]
    budget = result["budget"]
    lines += ["", f"Dated-price known settled cost US${budget['known_settled_usd']}; "
              f"conservative charged/reserved total US${budget['spent_usd']}; cap US${budget['limit_usd']}.",
              "These are standard-price estimates, not an account invoice; unresolved reservations are not fabricated zeros."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, required=True, help="new analysis directory; never edits original artifacts")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    result = analyse(args.run, args.dataset)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text(render_report(result), encoding="utf-8")


if __name__ == "__main__":
    main()
