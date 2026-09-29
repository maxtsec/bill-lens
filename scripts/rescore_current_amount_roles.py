"""Offline scoring-2 to scoring-3 comparison using the 88 preserved responses."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from bill_lens.current_amount_role import derive_current_amount_role_flags
from bill_lens.document_validation import derive_document_flags
from bill_lens.extraction import build_attempt
from bill_lens.validation import derive_flags, derive_status
from evals import SCORING_VERSION
from evals.dataset import load_cases
from evals.scoring import score_attempt
from scripts.rescore_printed_values import ROOT, SOURCE, build_evidence as rebuild_presence


BASELINE = Path("docs/learning/evidence/printed-value-check.json")


def build_evidence(root: Path = ROOT) -> dict:
    baseline_bytes = (root / BASELINE).read_bytes()
    baseline = json.loads(baseline_bytes)
    # The historical replay verifies all source artifact/PDF/label hashes,
    # coverage, original decisions and unchanged field outcomes before we use them.
    rebuilt = rebuild_presence(root)
    for key in ("source_scoring_version", "derived_scoring_version", "source_manifest_sha256",
                "live_api_calls", "per_run", "totals", "changes", "definitions"):
        if rebuilt[key] != baseline[key]:
            raise ValueError(f"scoring-2 baseline mismatch: {key}")
    if baseline["derived_scoring_version"] != "2" or SCORING_VERSION != "3":
        raise ValueError("this replay requires scoring 2 and 3")
    cases = {c.name: c for folder in ("dataset", "dataset/holdout") for c in load_cases(root / folder)}
    totals = dict(attempts=0, silent_false_acceptance_before=0, silent_false_acceptance_after=0,
                  new_false_reviews=0, flag_changes=0, status_changes=0)
    per_run, changes = {}, []
    for role in baseline["per_run"]:
        stats = dict.fromkeys(totals, 0)
        rows = (root / SOURCE / role / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        for line in rows:
            row = json.loads(line)
            case = cases[row["bill"]]
            if (case.document.file_sha256, case.label_sha256) != (row["pdf_sha256"], row["label_sha256"]):
                raise ValueError("dataset identity mismatch during role replay")
            attempt = build_attempt(provider=row["provider"], model=row["resolved_model"],
                                    prompt_version=row["prompt_version"], raw_response=row["raw_response"],
                                    error_code=row["error_code"], latency_ms=row["latency_ms"],
                                    input_tokens=row["input_tokens"], output_tokens=row["output_tokens"])
            before = sorted(derive_flags(attempt.fields) | derive_document_flags(attempt.fields, case.document)) if attempt.fields else None
            before_status = derive_status(before) if before is not None else "failed"
            added = sorted(derive_current_amount_role_flags(attempt.fields, case.document)) if attempt.fields else []
            after = score_attempt(attempt, case.label, case.document)
            for name in ("predicted", "expected", "expected_flags", "expected_status", "field_outcomes",
                         "supply_components", "exact_bill_match"):
                if row[name] != after[name]:
                    raise ValueError(f"unexpected field-scoring change: {name}")
            flags_changed, status_changed = after["flags"] != before, after["status"] != before_status
            stats["attempts"] += 1
            stats["silent_false_acceptance_before"] += int(row["expected_status"] == "needs_review" and before_status == "processed")
            stats["silent_false_acceptance_after"] += int(row["expected_status"] == "needs_review" and after["status"] == "processed")
            stats["new_false_reviews"] += int(row["exact_bill_match"] and bool(added))
            stats["flag_changes"] += int(flags_changed)
            stats["status_changes"] += int(status_changed)
            if flags_changed or status_changed:
                changes.append({"run": role, "run_id": row["run_id"], "bill": row["bill"], "repeat": row["repeat"],
                                "current_bill_amount": row["predicted"]["current_bill_amount"],
                                "flags_before": before, "flags_after": after["flags"],
                                "status_before": before_status, "status_after": after["status"],
                                "flags_match_after": after["flags_match"]})
        if (stats["attempts"], stats["silent_false_acceptance_before"]) != (
                baseline["per_run"][role]["attempts"], baseline["per_run"][role]["silent_false_acceptance_after"]):
            raise ValueError("replay does not reproduce scoring-2 decisions")
        per_run[role] = stats
        for name in totals:
            totals[name] += stats[name]
    if totals["attempts"] != 88:
        raise ValueError("expected all 88 preserved attempts")
    implementation = ("bill_lens/document_validation.py", "bill_lens/current_amount_role.py",
                      "bill_lens/validation.py", "bill_lens/contract.py", "evals/scoring.py",
                      "scripts/rescore_printed_values.py", "scripts/rescore_current_amount_roles.py")
    return {"source_scoring_version": "2", "derived_scoring_version": "3",
            "source_manifest_sha256": baseline["source_manifest_sha256"],
            "presence_evidence_sha256": sha256(baseline_bytes).hexdigest(),
            "implementation_lf_sha256": {name: sha256((root / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for name in implementation},
            "live_api_calls": 0, "per_run": per_run, "totals": totals, "changes": changes,
            "definitions": {"silent_false_acceptance": "expected needs_review, predicted processed",
                            "new_false_review": "original exact-bill-correct attempt now has a role flag"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new derived evidence file; refuses overwrite")
    args = parser.parse_args(argv)
    evidence = build_evidence()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence["totals"]))


if __name__ == "__main__":
    main()
