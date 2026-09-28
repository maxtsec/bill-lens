"""Compare completed runs descriptively; reject different data or scoring rules."""

import argparse
import json
from pathlib import Path

from . import HARNESS_VERSION, LIMITATION, SCORING_VERSION
from .reporting import fraction
from .scoring import FIELDS, OUTCOMES


def load_summary(path: Path) -> dict:
    summary = json.loads((path / "summary.json" if path.is_dir() else path).read_text(encoding="utf-8"))
    if not summary["completed"] or summary["completed_attempts"] != {"count": summary["planned_attempts"], "total": summary["planned_attempts"]}:
        raise ValueError("incomparable: run is incomplete or aborted")
    if summary["harness_version"] != HARNESS_VERSION or summary["scoring_version"] != SCORING_VERSION:
        raise ValueError("incomparable: unsupported harness/scoring version")
    if type(summary["repeats"]) is not int or summary["repeats"] < 1 or not summary["dataset"]:
        raise ValueError("invalid repeat count or dataset")
    if set(summary["per_bill"]) != set(summary["dataset"]) or summary["planned_attempts"] != len(summary["dataset"]) * summary["repeats"]:
        raise ValueError("invalid bill/attempt counts")
    for stats, total in [(summary["metrics"], summary["planned_attempts"]),
                          *((value, summary["repeats"]) for value in summary["per_bill"].values())]:
        if stats["attempts"] != total:
            raise ValueError("invalid metric denominator")
        for field in FIELDS:
            counts = stats["fields"][field]
            if any(type(counts[o]["count"]) is not int or not 0 <= counts[o]["count"] <= total
                   or counts[o]["total"] != total for o in OUTCOMES):
                raise ValueError("invalid field counts/denominators")
            if sum(counts[o]["count"] for o in OUTCOMES) != total:
                raise ValueError("field outcomes must partition attempts")
    return summary


def change(left: dict, right: dict) -> str:
    a, b = left["count"] * right["total"], right["count"] * left["total"]
    return "improved" if b > a else "regressed" if b < a else "unchanged"


def configuration(summary: dict) -> dict:
    # Requested/resolved values describe one model variable, not two independent
    # interventions. Likewise keep configured/observed prompt versions together.
    return {"provider": summary["provider"],
            "model": (summary["requested_model"], sorted(summary["resolved_models"])),
            "prompt version": (summary["configured_prompt_version"], sorted(summary["prompt_versions"])),
            "effort": summary["reasoning_effort"], "commit": summary["git"]["commit"]}


def outcome_changes(left: dict, right: dict) -> str:
    return "; ".join(f"{o}: {fraction(left[o])} -> {fraction(right[o])}" for o in OUTCOMES[1:])


def compare_runs(left: dict, right: dict) -> str:
    for key in ("dataset", "harness_version", "scoring_version", "repeats"):
        if left[key] != right[key]:
            raise ValueError(f"incomparable: different {key}")
    lines = [f"# Compare {left['run_id']} -> {right['run_id']}", "", LIMITATION,
             f"Dataset names: A={left.get('dataset_name', 'legacy (name not recorded)')}; B={right.get('dataset_name', 'legacy (name not recorded)')}",
             f"Dataset: {len(left['dataset'])} bills; repeats: {left['repeats']} each.", ""]
    lines += ["| Run | Provider | Requested model | Resolved models | Configured prompt | Observed prompts | Effort | Code commit |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for label, summary in (("A", left), ("B", right)):
        lines.append(f"| {label} | {summary['provider']} | {summary['requested_model']} | "
                     f"{', '.join(sorted(summary['resolved_models'])) or 'none'} | {summary['configured_prompt_version']} | "
                     f"{', '.join(sorted(summary['prompt_versions'])) or 'none'} | {summary['reasoning_effort']} | {summary['git']['commit']} |")
    a_config, b_config = configuration(left), configuration(right)
    changed = [key for key in a_config if a_config[key] != b_config[key]]
    lines += ["", "Changed dimensions: " + (", ".join(changed) or "none") + ".", ""]
    if len(changed) > 1:
        lines += ["WARNING: multiple configuration dimensions differ; score changes cannot be attributed to a single variable.", ""]
    if left["git"]["dirty"] or right["git"]["dirty"] or not left["git"]["commit"] or not right["git"]["commit"]:
        lines += ["WARNING: dirty or unavailable Git provenance; commit IDs alone cannot reproduce these runs.", ""]
    lines += ["## Per-field correctness", "", "| Field | A | B | Change | Other outcome counts A -> B |",
              "| --- | --- | --- | --- | --- |"]
    for field in FIELDS:
        a, b = left["metrics"]["fields"][field], right["metrics"]["fields"][field]
        details = outcome_changes(a, b)
        lines.append(f"| {field} | {fraction(a['correct'])} | {fraction(b['correct'])} | {change(a['correct'], b['correct'])} | {details} |")
    lines += ["", "## Per-bill changes", "",
              "Change describes correctness only; outcome counts can change even when correctness is unchanged.",
              "Counts compare distributions across repeats, not paired attempt transitions.", "",
              "| Bill | Metric | A | B | Change | Other outcome counts A -> B |", "| --- | --- | --- | --- | --- | --- |"]
    for bill in left["dataset"]:
        a, b = left["per_bill"][bill], right["per_bill"][bill]
        for key in ("exact_bill_match", "flags_match", "status_match", *FIELDS):
            x = a[key] if key not in FIELDS else a["fields"][key]["correct"]
            y = b[key] if key not in FIELDS else b["fields"][key]["correct"]
            details = outcome_changes(a["fields"][key], b["fields"][key]) if key in FIELDS else "—"
            lines.append(f"| {bill} | {key} | {fraction(x)} | {fraction(y)} | {change(x, y)} | {details} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_runs(load_summary(args.run_a), load_summary(args.run_b))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
